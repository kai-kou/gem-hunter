#!/usr/bin/env python3
"""
triage_improvements.py - 改善 Issue 棚卸し（grooming）支援ツール

self-improvement-loop スキル（整理モード）の「重い処理」層。type:improvement の Issue を一括取得し、
集計・カテゴリ自動分類・重複検出・priority/sp 欠損検出・Epic 候補抽出を行い、
機械可読 JSON と人間可読 Markdown レポートを出力する。

判断（実際のラベル付与・クローズ・Epic 作成）は SKILL.md 側で Claude（+ @owner PO）が行う。
本ツールは「現状をデータで可視化する」ことに徹し、副作用（Issue の変更）は持たない。

使い方:
  python3 tools/triage_improvements.py                  # Markdown レポートを stdout
  python3 tools/triage_improvements.py --json           # JSON を stdout
  python3 tools/triage_improvements.py --out report.md  # Markdown をファイル出力
  python3 tools/triage_improvements.py --label type:improvement --state open
  python3 tools/triage_improvements.py --self-test      # 純粋関数のセルフテスト

終了コード（`docs/rules/check-tool-design-rules.md` §1 の標準に準拠）:
  0: 正常終了（レポートを出力した）
  1: 取得は成功したが対象 Issue が 0 件（全件が `type:retro-try` で除外された場合を含む。
     fail-closed で合格 0 に丸めない。stderr の先頭記号は `❌`）
  2: 判定不能（gh も GH_TOKEN も使えない / REST API 取得に失敗した。stderr の先頭記号は `⚠️`）
  ※ self-test は 0 = 全 check PASS / 1 = FAIL あり

設計方針:
  - 副作用なし（読み取り専用）。GitHub への書き込みは一切しない
  - `type:retro-try` を持つ Issue は **既定ラベル（`type:improvement`）等での取得時に** 除外する
    （消化モード＝実装は振り返りレーンの専管・#160 / `docs/rules/improvement-lane-map.md` §2
    ルール 2）。除外は取得層（fetch_issues）で行い、gh 経路・REST API 経路のどちらを通っても
    同じ結果になるようにする（#418）。
    🔴 射程限定: 除外されるのは本ツールが担う **Step G-1 の `type:improvement` 集計** だけである。
    `--label type:retro-try` と明示指定されたときは除外しない（要求そのものを空振りさせないため）。
    整理モードのリファインメント（Step G-1.5 / G-6）は本ツールを使わず別クエリで取得するため、
    `type:retro-try` も従来どおり対象に含む（`improvement-lane-map.md` §2 ルール 5・#153）
  - gh CLI を主経路、不在時は GitHub API（urllib）にフォールバック
  - リポジトリは PROJECT_REPO / GITHUB_REPOSITORY env で解決（雛形プレースホルダにフォールバック）
  - カテゴリは「監査タグ（[監査PX/DOMAIN-NN]）」を最優先、なければキーワードクラスタ
  - 重複検出は ① 監査ドメインコードの重複 ② 正規化タイトルのトークン Jaccard 類似度
"""

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_slug import resolve_repo_slug  # noqa: E402
import github_api  # noqa: E402

# 優先順: bootstrap 済みプレースホルダ解決値（最優先・下流リポジトリの既定動作）→
# 未解決の場合のみ PROJECT_REPO → GITHUB_REPOSITORY → git remote の URL 解析 →
# 雛形プレースホルダのまま（解決ロジックの正本は tools/repo_slug.py・#215）。
REPO = resolve_repo_slug("kai-kou/gem-hunter", env_vars=("PROJECT_REPO", "GITHUB_REPOSITORY"))

# 監査タグ [監査PX/DOMAIN-NN] の DOMAIN コード → 日本語ラベル（任意機能）。
# 監査タグ運用を採るプロジェクトのみ意味を持つ。未知コードはコードのまま素通しするため、
# ここに無いコードを使っても破綻しない（ドメイン固有ラベルは各プロジェクトで追記する）。
DOMAIN_LABELS = {
    "QUAL": "品質/レビュー",
    "COST": "コスト/予算",
    "SAFE": "安全/セキュリティ",
    "SEC": "セキュリティ",
    "OBS": "可観測性",
    "TEST": "テスト",
    "A11Y": "アクセシビリティ",
    "DOC": "ドキュメント",
    "PIPE": "パイプライン基盤",
}

# 非監査 Issue 用のキーワードクラスタ（先勝ちで1カテゴリに割当）。
# 汎用 Claude Code 運用ベースの構成要素（ハーネス/ルール/スキル/ツール/CI 等）に基づく。
# プロジェクト固有のドメイン分類を増やしたい場合は本リストの先頭側に追記する。
KEYWORD_CLUSTERS = [
    ("ハーネス/フック", ["hook", "フック", "harness", "ハーネス", "pretooluse", "posttooluse",
                         "pre-tool", "post-tool", "stop-", "settings.json", "ガードレール"]),
    ("ルール/ドキュメント", ["rule", "ルール", "docs", "ドキュメント", "claude.md", "ssot",
                            "readme", "ガイド"]),
    ("スキル整備", ["skill", "スキル", "skill-creator", "description", "gotchas", "サブエージェント",
                   "subagent", "agent"]),
    ("ツール/スクリプト", ["tool", "ツール", "script", "スクリプト", "helper", "ヘルパー",
                         "リファクタ", "module", "モジュール", "共通化", "ユーティリティ"]),
    ("CI/テスト", ["test", "テスト", "self-test", "セルフテスト", "workflow", "ワークフロー",
                  "lint", "pytest", "アクション", "actions", "ci/"]),
    ("PR/レビュー", ["プルリク", "レビュー", "review", "merge", "マージ", "self-review",
                    "セルフレビュー", "pull request"]),
    ("Issue/バックログ運用", ["issue", "ラベル", "label", "milestone", "マイルストーン", "project",
                            "backlog", "バックログ", "sprint", "スプリント", "見積", "棚卸"]),
    ("計測/分析", ["analytics", "計測", "metric", "メトリク", "kpi", "cost", "コスト", "token",
                  "トークン", "ダッシュボード", "予算"]),
    ("セッション/安全", ["session", "セッション", "compaction", "圧縮", "checkpoint", "チェックポイント",
                       "timeout", "タイムアウト", "復帰", "コミット"]),
    ("通知/連携", ["slack", "通知", "notification", "mention", "メンション", "webhook", "連携"]),
    ("セキュリティ/認証", ["security", "セキュリティ", "secret", "シークレット", "credential",
                         "認証", "サンドボックス", "sandbox", "権限"]),
    ("リサーチ/調査", ["research", "リサーチ", "調査", "deep research", "deep-research"]),
]

# ストップワード（タイトル類似度計算で無視する一般語・記号語）
_STOPWORDS = {
    "improvement", "feat", "fix", "docs", "epic", "の", "を", "に", "と", "が", "は",
    "で", "improvement:", "監査", "追加", "実装", "対応", "強化", "改善", "見直し",
    "最適化", "化", "新設", "定義", "統一", "導入",
}


def run_gh(args):
    """gh CLI を実行して stdout を返す。失敗時は空文字。

    `tools/github_api.py` の共通実装への薄いラッパー（Issue #238）。元実装は
    `FileNotFoundError`/`TimeoutExpired`（gh 起動不能）では警告を出さず、非 0 終了時のみ
    stderr を警告表示する非対称な挙動だった。`github_api.run_gh()` は理由文字列を返すのみで
    例外種別を呼び出し元に開示しないため、固定の理由文字列で区別して元の非対称挙動を保つ
    （挙動を変えないための意図的な文字列比較。github_api.run_gh() のメッセージ文言が変われば
    ここも追従が必要）。
    """
    ok, out = github_api.run_gh(args, timeout=60)
    if not ok:
        if not github_api.is_gh_unavailable(out):
            print(f"WARNING: gh failed: gh {' '.join(args)}\n  {out}", file=sys.stderr)
        return ""
    return out


def _fetch_via_api(label, state):
    """gh 不在時のフォールバック（GitHub REST API・GH_TOKEN 必要）。

    取得できたら Issue のリスト、**取得自体が成立しなかったら `None`**（トークン不在・HTTP 失敗）
    を返す。呼び出し側はこの `None` を「対象 0 件」ではなく判定不能（exit 2）として扱う。

    per-page の HTTP 呼び出しは `github_api.http_get()` に委譲する（Issue #238）。
    ページネーションの継続判定（`max_pages` 上限を持たず空バッチで打ち切り）はファイル固有の
    既存挙動としてそのまま踏襲する（`github_rest.paginate_json_array` へは寄せない設計判断は
    `tools/github_api.py` docstring「集約しなかったもの」参照）。
    """
    token = github_api.resolve_token()
    if not token:
        print("⚠️ ERROR: gh CLI も GH_TOKEN も利用できません（判定不能）", file=sys.stderr)
        return None
    issues = []
    page = 1
    state_q = "all" if state == "all" else state
    while True:
        url = (
            f"https://api.github.com/repos/{REPO}/issues"
            f"?labels={urllib.parse.quote(label)}&state={state_q}&per_page=100&page={page}"
        )
        ok, out = github_api.http_get(url, token, user_agent="curl/8.5.0", timeout=60)
        if not ok:
            # 取得できなかったページがある時点で「対象を全部見た」と言えないため、
            # 部分結果を成功として返さず判定不能（None → exit 2）へ倒す（check-tool-design-rules.md §1）
            print(f"⚠️ ERROR: API fetch failed: {out}", file=sys.stderr)
            return None
        batch = json.loads(out)  # 元実装通り不正 JSON は無捕捉のまま例外伝播させる
        if not batch:
            break
        for it in batch:
            if "pull_request" in it:
                continue  # PR を除外
            issues.append({
                "number": it["number"],
                "title": it["title"],
                "labels": [{"name": l["name"]} for l in it.get("labels", [])],
                "createdAt": it.get("created_at"),
                "updatedAt": it.get("updated_at"),
                "milestone": ({"title": it["milestone"]["title"]} if it.get("milestone") else None),
                "comments": it.get("comments", 0),
            })
        page += 1
    return issues


def fetch_issues(label, state):
    """対象ラベルの Issue を取得する（gh 優先・API フォールバック）。

    返り値は `(issues, fetched_ok)`。`fetched_ok=False` は「取得自体が成立しなかった」
    （gh も GH_TOKEN も使えない / REST が失敗した）を表し、呼び出し側は判定不能（exit 2）へ
    倒す。取得が成功したうえでの 0 件（`fetched_ok=True` かつ空）とは区別する。

    🔴 取得経路にかかわらず、最後に `type:retro-try` を除外する（#418）。除外をこの 1 か所に
    置くことで「gh 経路だけ除外され API 経路では素通し」という経路差を作らない。
    ただし **`label` 自体が `type:retro-try` のときは除外しない**（明示的に要求されたラベルを
    取得層で全滅させると、取得は成功しているのに「0 件」と区別できなくなるため）。
    """
    issues = None
    out = run_gh([
        "issue", "list", "-R", REPO,
        "--label", label, "--state", state,
        "--limit", "500",
        "--json", "number,title,labels,createdAt,updatedAt,milestone,comments",
    ])
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            print("WARNING: gh 出力の JSON 解析に失敗。API へフォールバック", file=sys.stderr)
        else:
            if isinstance(parsed, list):
                issues = parsed
            else:
                # gh が配列以外（エラーオブジェクト等）を返した場合は「取得できた」とみなさない
                print("WARNING: gh 出力が配列でない。API へフォールバック", file=sys.stderr)
    if issues is None:
        issues = _fetch_via_api(label, state)
        if issues is None:
            return [], False

    if label.strip().casefold() == RETRO_TRY_LABEL:
        # 明示的に retro-try を要求されたときは除外しない（構造的に必ず 0 件になるのを防ぐ）
        return issues, True

    kept, excluded = exclude_retro_try(issues)
    if excluded:
        print(
            f"INFO: type:retro-try の Issue {excluded} 件を除外しました"
            "（Step G-1 の type:improvement 集計に限った除外。実装は振り返りレーンの専管・"
            "improvement-lane-map.md §2 ルール 2。棚卸し / リファインメントは"
            "同 §2 ルール 5 のとおり別クエリで retro-try も対象に含む）",
            file=sys.stderr,
        )
    return kept, True


def label_names(issue):
    """Issue のラベル名リストを返す（dict 形式 / 生文字列形式のどちらでも受ける）。

    gh の `--json labels` は `[{"name": ...}, ...]`、REST API 変換後も dict 形式だが、
    テスト・他ツールからは生文字列のリストが渡されうる。`labels` 欠落・None・
    `name` を持たない dict は「ラベル無し」として落とす（例外にしない）。

    🔴 `labels` が **カンマ結合の生文字列 1 本**（`"type:improvement,type:retro-try"`）で
    渡されることもある（`tools/gh_shim.py` の `gh issue list` 非 JSON テーブル出力がこの形）。
    そのまま反復すると 1 文字ずつに分解され、ラベル判定が常に偽になる fail-open へ倒れるため、
    明示的にカンマで分割する。
    """
    raw = issue.get("labels") or []
    if isinstance(raw, str):
        raw = [s for s in raw.split(",") if s]
    names = []
    for l in raw:
        if isinstance(l, dict):
            name = l.get("name")
        else:
            name = l
        if isinstance(name, str):
            names.append(name)
    return names


RETRO_TRY_LABEL = "type:retro-try"


def has_retro_try_label(issue):
    """Issue が `type:retro-try` ラベルを持つか（大文字小文字・前後空白を無視した完全一致）。

    完全一致で判定する（前方一致にすると `type:retro-try-x` のような別ラベルまで
    巻き込んで除外してしまう）。GitHub のラベル名は大文字小文字を区別せず一意なため、
    `casefold()` して比較する。
    """
    return any(n.strip().casefold() == RETRO_TRY_LABEL for n in label_names(issue))


def exclude_retro_try(issues):
    """`type:retro-try` を持つ Issue を落とし、(残った Issue, 除外件数) を返す。

    振り返りレーンの専管（#160）である `type:retro-try` が、`type:improvement` との
    二重ラベルによって改善 Issue レーンの棚卸し集計へ混入するのを防ぐ（#418）。
    """
    kept = [it for it in issues if not has_retro_try_label(it)]
    return kept, len(issues) - len(kept)


def get_tag(labels, prefix):
    for l in labels:
        if l.startswith(prefix):
            return l[len(prefix):]
    return None


def normalize_tokens(title):
    """タイトルを類似度計算用のトークン集合に正規化する。"""
    # 監査タグ・記号を除去
    t = re.sub(r"\[[^\]]*\]", " ", title)
    t = re.sub(r"[（）()【】・,，、。:：/／\-—–#0-9]", " ", t)
    t = t.lower()
    toks = {w for w in t.split() if len(w) >= 2 and w not in _STOPWORDS}
    return toks


def categorize(issue):
    """Issue を (カテゴリ名, 監査フェーズ or None) に分類する。"""
    title = issue["title"]
    labels = label_names(issue)
    if "[Epic]" in title or "type:epic" in labels:
        return ("（Epic/親追跡）", None)
    m = re.search(r"\[監査(P\d)/([A-Z0-9]+)", title)
    if m:
        phase = m.group(1)
        domain = re.match(r"[A-Z]+", m.group(2)).group(0)
        return (f"監査:{DOMAIN_LABELS.get(domain, domain)}", phase)
    low = title.lower()
    for name, kws in KEYWORD_CLUSTERS:
        if any(k in low for k in kws):
            return (name, None)
    return ("（その他/未分類）", None)


def detect_duplicates(rows):
    """重複/酷似ペアを検出する。"""
    dups = []
    # ① 監査ドメインコードの完全重複（例: SNS-12 が2件）
    code_map = defaultdict(list)
    for r in rows:
        m = re.search(r"\[監査P\d/([A-Z]+-?\d+)", r["title"])
        if m:
            code_map[m.group(1)].append(r["num"])
    for code, nums in code_map.items():
        if len(nums) > 1:
            dups.append({"type": "audit-code", "key": code, "issues": sorted(nums)})
    # ② タイトルトークンの Jaccard 類似度（>= 0.6 を酷似とみなす）
    toks = {r["num"]: normalize_tokens(r["title"]) for r in rows}
    nums = [r["num"] for r in rows]
    for i in range(len(nums)):
        a = nums[i]
        if not toks[a]:
            continue
        for j in range(i + 1, len(nums)):
            b = nums[j]
            if not toks[b]:
                continue
            inter = len(toks[a] & toks[b])
            union = len(toks[a] | toks[b])
            if union == 0:
                continue
            jac = inter / union
            if jac >= 0.6 and inter >= 2:
                dups.append({"type": "title-similar", "score": round(jac, 2), "issues": [a, b]})
    return dups


# ---------------------------------------------------------------------------
# 棚卸しの判定規則（#385 の議論型レビューで確定・SSOT はここ）
# 議論記録: content/discussions/issue-triage-20260822/whiteboard.md
# ---------------------------------------------------------------------------

# priority:high が全体に占める割合の上限。これを超えると「最優先」バケットが
# 順序付けの情報を持たなくなる（実質 medium の言い換えになる）。
HIGH_RATIO_CEILING = 0.30

# 「後回しでよい」ことを本文が明示しているシグナル。
_LOW_SIGNALS = ("低頻度", "稀", "代替手段", "影響範囲は限定", "限定的")

# 実際に発生した failure を示すシグナル（予防的・提案的表現と区別する）。
_FAILURE_SIGNALS = ("grep", "実測", "再現", "500", "落ち", "失敗", "エラー", "不整合")

# 実測された失敗事象が無い限り high に上げないカテゴリ（予防的検査・整合・計画）。
_PREVENTIVE_CATEGORIES = ("CHECK", "RULE", "BACKLOG")


def assign_priority(title, body, category=None):
    """priority ラベルが欠損している Issue へ付ける優先度を決める（#385）。

    優先度の高い順に評価し、最初に一致した規則を適用する（1 Issue につき 1 規則）。

      1. title が fix: / bug: 始まり かつ body に実測された失敗事象の記述がある → high
      2. body に「低頻度 / 稀 / 代替手段あり / 影響範囲は限定的」の記述がある     → low
      3. category が予防的（CHECK / RULE / BACKLOG）で実測失敗事象なし            → medium
      4. それ以外（判定材料不足）                                                 → medium

    一律 medium で埋めない理由: medium が全体の 7 割に膨らむと medium 自体が
    順序付けの情報を持たなくなるため（欠損 43 件を一律 medium にすると 127 件になった）。
    """
    title = title or ""
    body = body or ""
    head = title.strip().lower()
    if head.startswith(("fix:", "bug:")) and any(s in body for s in _FAILURE_SIGNALS):
        return "high"
    if any(s in body for s in _LOW_SIGNALS):
        return "low"
    if category in _PREVENTIVE_CATEGORIES:
        return "medium"
    return "medium"


def should_demote_high(evidence):
    """priority:high から medium へ降格すべきかを判定する（#385）。

    判定軸: evidence に「実際に発生した failure・データ不整合・事故」の実測記述が無く、
    「〜すべき」「〜の可能性がある」「検知できるようにする」という予防的・提案的表現に
    留まるものは降格する。
    """
    evidence = evidence or ""
    if any(s in evidence for s in _FAILURE_SIGNALS):
        return False
    return True


def select_keep(a, b):
    """重複クラスタで残す（keep する）側を決める（#385）。

    引数はいずれも {"num", "requirements"} を持つ dict。`requirements` は
    対応方針・完了条件から抽出した要求の集合。

    基準: **要求が最も広い（他方を部分集合として包含する）方**を keep する。
    「常に新しい方」「常に履歴のある方」という単純ルールは採らない（#94 / #322 と
    #201 / #350 の 2 例で破綻したため）。包含関係が無い場合は None を返し、
    人（またはセッション）が本文を突き合わせて決める。

    包含関係があっても、**dup 側にしか無い要求は keep 側の本文へ追記してから統合する**
    （追記を怠ると要求が消える。#385 では 9 クラスタ中 4 組で発生した）。
    """
    ra, rb = set(a.get("requirements") or ()), set(b.get("requirements") or ())
    if ra and rb >= ra and rb != ra:
        return b["num"]
    if rb and ra >= rb and ra != rb:
        return a["num"]
    return None


def high_ratio_ok(high_count, total):
    """priority:high の比率が閾値内かを判定する（#385）。"""
    if total <= 0:
        return True
    return (high_count / total) <= HIGH_RATIO_CEILING


def build_report(issues, epic_threshold):
    rows = []
    for it in issues:
        labels = label_names(it)
        cat, phase = categorize(it)
        rows.append({
            "num": it["number"],
            "title": it["title"],
            "labels": labels,
            "priority": get_tag(labels, "priority:"),
            "sp": get_tag(labels, "sp:"),
            "milestone": (it["milestone"]["title"] if it.get("milestone") else None),
            "created": (it.get("createdAt") or "")[:10],
            "updated": (it.get("updatedAt") or "")[:10],
            "category": cat,
            "audit_phase": phase,
            "is_epic": "[Epic]" in it["title"],
        })
    rows.sort(key=lambda r: r["num"])

    pri = Counter(r["priority"] or "(なし)" for r in rows)
    sp = Counter(r["sp"] or "(なし)" for r in rows)
    phase = Counter(r["audit_phase"] for r in rows if r["audit_phase"])
    cats = Counter(r["category"] for r in rows)

    missing_priority = [r["num"] for r in rows if not r["priority"] and not r["is_epic"]]
    missing_sp = [r["num"] for r in rows if not r["sp"] and not r["is_epic"]]

    dups = detect_duplicates(rows)

    # Epic 候補: 同一カテゴリに閾値以上の非 Epic Issue が集中
    cat_members = defaultdict(list)
    for r in rows:
        if not r["is_epic"]:
            cat_members[r["category"]].append(r["num"])
    epic_candidates = {c: sorted(nums) for c, nums in cat_members.items()
                       if len(nums) >= epic_threshold and not c.startswith("（")}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": REPO,
        "total": len(rows),
        "priority_dist": dict(pri),
        "sp_dist": dict(sp),
        "audit_phase_dist": dict(phase),
        "category_dist": dict(cats),
        "missing_priority": missing_priority,
        "missing_sp": missing_sp,
        "duplicates": dups,
        "epic_candidates": epic_candidates,
        "rows": rows,
    }


def render_markdown(rep):
    L = []
    L.append(f"# 改善 Issue 棚卸しレポート（{rep['total']} 件）")
    L.append("")
    L.append(f"_生成: {rep['generated_at']}_")
    L.append("")
    L.append("## 集計")
    L.append("")
    L.append("| 軸 | 内訳 |")
    L.append("|----|------|")
    L.append(f"| priority | {_fmt(rep['priority_dist'])} |")
    L.append(f"| sp | {_fmt(rep['sp_dist'])} |")
    if rep["audit_phase_dist"]:
        L.append(f"| 監査フェーズ | {_fmt(rep['audit_phase_dist'])} |")
    L.append("")
    L.append("## カテゴリ別件数")
    L.append("")
    for c, n in sorted(rep["category_dist"].items(), key=lambda x: -x[1]):
        L.append(f"- **{c}**: {n} 件")
    L.append("")
    if rep["epic_candidates"]:
        L.append("## 🧩 Epic 統合候補（同一カテゴリ集中）")
        L.append("")
        for c, nums in sorted(rep["epic_candidates"].items(), key=lambda x: -len(x[1])):
            preview = ", ".join(f"#{n}" for n in nums[:12])
            more = f" …他 {len(nums)-12} 件" if len(nums) > 12 else ""
            L.append(f"- **{c}**（{len(nums)} 件）: {preview}{more}")
        L.append("")
    if rep["duplicates"]:
        L.append("## ⚠️ 重複/酷似の検出")
        L.append("")
        for d in rep["duplicates"]:
            if d["type"] == "audit-code":
                L.append(f"- 監査コード `{d['key']}` が重複: {', '.join('#'+str(n) for n in d['issues'])}")
            else:
                a, b = d["issues"]
                L.append(f"- 酷似（類似度 {d['score']}）: #{a} ↔ #{b}")
        L.append("")
    if rep["missing_priority"] or rep["missing_sp"]:
        L.append("## 🏷 ラベル欠損（@owner PO 補完対象）")
        L.append("")
        if rep["missing_priority"]:
            L.append(f"- **priority 未設定** {len(rep['missing_priority'])} 件: "
                     + ", ".join(f"#{n}" for n in rep["missing_priority"][:25])
                     + (" …" if len(rep["missing_priority"]) > 25 else ""))
        if rep["missing_sp"]:
            L.append(f"- **sp 未設定** {len(rep['missing_sp'])} 件: "
                     + ", ".join(f"#{n}" for n in rep["missing_sp"][:25])
                     + (" …" if len(rep["missing_sp"]) > 25 else ""))
        L.append("")
    return "\n".join(L)


def _fmt(d):
    return " / ".join(f"{k}={v}" for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0])))


class _FakeCompleted:
    """`subprocess.CompletedProcess` の最小スタブ（self-test 共有・重複定義しない）。"""

    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _self_test_run_gh_delegates_with_stderr_asymmetry():
    """`run_gh()` が `github_api.run_gh()` 経由で実際に `subprocess.run` へ到達すること、
    かつ元実装から意図的に保持している非対称挙動（gh 起動不能では無警告 / 非0終了では
    WARNING を出す）が実際に機能していることを実測する（PR #849 Layer1 指摘1・4）。

    従来の `_self_test()` は「純粋関数のみ」を対象にしており（モジュール docstring 明記）、
    `run_gh()` 自体は一度も呼ばれていなかった。`globals()["_run_gh"]` を丸ごと差し替える
    パターン（他ファイルの慣習）ではなく、`subprocess.run` そのものを差し替えて委譲コードを
    実行させる（#710 の fake runner argv 検証と同じ形）。
    """
    import subprocess

    failures = []
    orig_run = subprocess.run
    captured = []

    def fake_run_ok(cmd, **kwargs):
        captured.append({"cmd": cmd, "kwargs": kwargs})
        return _FakeCompleted(0, stdout="hello\n")

    def fake_run_not_found(cmd, **kwargs):
        captured.append({"cmd": cmd, "kwargs": kwargs})
        raise FileNotFoundError()

    def fake_run_fail(cmd, **kwargs):
        captured.append({"cmd": cmd, "kwargs": kwargs})
        return _FakeCompleted(1, stderr="HTTP 403: Forbidden\n")

    import io
    import contextlib

    try:
        # ① 成功: argv がそのまま subprocess.run に届く
        captured.clear()
        subprocess.run = fake_run_ok
        out = run_gh(["issue", "list", "-R", "o/r", "--label", "type:improvement"])
        if out != "hello":
            failures.append(f"run_gh 成功: 期待 'hello' だが {out!r}")
        if not captured or captured[0]["cmd"] != [
            "gh", "issue", "list", "-R", "o/r", "--label", "type:improvement",
        ]:
            failures.append(f"run_gh: argv が意図通りでない: {captured}")
        if captured and captured[0]["kwargs"].get("timeout") != 60:
            failures.append("run_gh: timeout=60 が subprocess.run に伝播していない")

        # ② gh 起動不能（FileNotFoundError）: 空文字を返し、WARNING を出さない（非対称挙動）
        captured.clear()
        subprocess.run = fake_run_not_found
        stderr_buf = io.StringIO()
        with contextlib.redirect_stderr(stderr_buf):
            out = run_gh(["issue", "list"])
        if out != "":
            failures.append(f"run_gh gh不在: 空文字を期待したが {out!r}")
        if "WARNING" in stderr_buf.getvalue():
            failures.append(
                f"run_gh gh不在: 非対称挙動（無警告）が壊れている。stderr={stderr_buf.getvalue()!r}"
            )

        # ③ 非0終了: 空文字を返し、WARNING を出す（非対称挙動のもう半分）
        captured.clear()
        subprocess.run = fake_run_fail
        stderr_buf = io.StringIO()
        with contextlib.redirect_stderr(stderr_buf):
            out = run_gh(["issue", "list"])
        if out != "":
            failures.append(f"run_gh 非0終了: 空文字を期待したが {out!r}")
        if "WARNING" not in stderr_buf.getvalue():
            failures.append(
                f"run_gh 非0終了: WARNING が出るべきだが出ていない。stderr={stderr_buf.getvalue()!r}"
            )
        if "HTTP 403: Forbidden" not in stderr_buf.getvalue():
            failures.append("run_gh 非0終了: WARNING に gh の失敗理由が含まれていない")
    finally:
        subprocess.run = orig_run
    return failures


def _self_test_is_gh_unavailable_equivalence():
    """`run_gh()` が使う `github_api.is_gh_unavailable()` の等価性契約（PR #849 指摘4）。

    旧実装は `("gh コマンドが見つかりません", "gh コマンドがタイムアウトしました")` を
    ここへ逐語コピーして固定比較していた（指摘3/5・github_api.py の `GH_UNAVAILABLE_REASONS`
    が唯一の SSOT になった後も、呼び出し元が正しく import して使っていることを裏付ける）。
    """
    failures = []
    if not github_api.is_gh_unavailable("gh コマンドが見つかりません"):
        failures.append("FileNotFoundError 文言が is_gh_unavailable=True にならない")
    if not github_api.is_gh_unavailable("gh コマンドがタイムアウトしました"):
        failures.append("TimeoutExpired 文言が is_gh_unavailable=True にならない")
    if github_api.is_gh_unavailable("HTTP 403: Forbidden"):
        failures.append("非0終了時の stderr 文言が誤って is_gh_unavailable=True になった")
    return failures


def _self_test_retro_try_exclusion_variants():
    """`type:retro-try` 除外の入力バリアント（#418）。

    失敗経路（= retro-try が混入しうる経路）に対応させた:
      ① ラベルが dict 形式（gh --json / REST 変換後の実形式）
      ② ラベルが生文字列形式（他ツール・テストからの入力）
      ③ 大文字小文字違い（GitHub のラベル名は case-insensitive で一意）
      ④ 前後空白
      ⑤ `labels` キー欠落 / None / `name` を持たない dict（例外にせずラベル無し扱い）
      ⑥ 境界の外側: `type:retro-try-x` は別ラベルなので **除外されない**（前方一致退行の検知）
    """
    failures = []

    def kept_nums(issues):
        kept, _ = exclude_retro_try(issues)
        return [i["number"] for i in kept]

    # ① dict 形式（実運用の形）
    issues = [
        {"number": 1, "labels": [{"name": "type:improvement"}]},
        {"number": 2, "labels": [{"name": "type:improvement"}, {"name": "type:retro-try"}]},
    ]
    got = kept_nums(issues)
    if got != [1]:
        failures.append(f"① dict 形式で retro-try が除外されない: kept={got}")

    # ② 生文字列形式
    issues = [
        {"number": 3, "labels": ["type:improvement"]},
        {"number": 4, "labels": ["type:improvement", "type:retro-try"]},
    ]
    got = kept_nums(issues)
    if got != [3]:
        failures.append(f"② 生文字列形式で retro-try が除外されない: kept={got}")

    # ③ 大文字小文字違い
    issues = [
        {"number": 5, "labels": [{"name": "Type:Retro-Try"}]},
        {"number": 6, "labels": [{"name": "TYPE:RETRO-TRY"}]},
    ]
    got = kept_nums(issues)
    if got != []:
        failures.append(f"③ 大文字小文字違いが除外されない: kept={got}")

    # ④ 前後空白
    got = kept_nums([{"number": 7, "labels": [" type:retro-try "]}])
    if got != []:
        failures.append(f"④ 前後空白付きが除外されない: kept={got}")

    # ④-b `labels` がカンマ結合の生文字列 1 本（gh_shim.py のテーブル出力形式）
    #      1 文字ずつ分解されると判定が常に偽になり fail-open へ倒れる
    got = kept_nums([
        {"number": 71, "labels": "type:improvement"},
        {"number": 72, "labels": "type:improvement,type:retro-try"},
        {"number": 73, "labels": "type:improvement, type:retro-try "},
        {"number": 74, "labels": "type:retro-try-x"},
    ])
    if got != [71, 74]:
        failures.append(f"④-b カンマ結合の生文字列 labels で除外が効いていない: kept={got}")
    if label_names({"labels": "a,b,c"}) != ["a", "b", "c"]:
        failures.append(
            f"④-b 生文字列 labels が分割されていない: {label_names({'labels': 'a,b,c'})}"
        )

    # ⑤ labels 欠落 / None / name なし dict → ラベル無し扱いで残る（例外を出さない）
    try:
        got = kept_nums([
            {"number": 8},
            {"number": 9, "labels": None},
            {"number": 10, "labels": [{"color": "ff0000"}]},
        ])
    except Exception as e:  # noqa: BLE001
        failures.append(f"⑤ labels 欠落/None/name なしで例外: {e!r}")
    else:
        if got != [8, 9, 10]:
            failures.append(f"⑤ ラベル無し扱いの Issue が落ちた: kept={got}")

    # ⑥ 境界の外側（近似だが別カテゴリ）: 前方一致退行なら誤って除外される
    negatives = [
        {"number": 11, "labels": [{"name": "type:retro-try-x"}]},
        {"number": 12, "labels": [{"name": "type:retro-try/planning"}]},
        {"number": 13, "labels": [{"name": "type:retro"}]},
        {"number": 14, "labels": [{"name": "no-type:retro-try"}]},
        {"number": 15, "labels": [{"name": "type:improvement"}]},
    ]
    got = kept_nums(negatives)
    if got != [11, 12, 13, 14, 15]:
        failures.append(f"⑥ 別ラベルまで誤除外している（前方一致退行）: kept={got}")

    # 除外件数の報告値
    _, excluded = exclude_retro_try([
        {"number": 16, "labels": [{"name": "type:retro-try"}]},
        {"number": 17, "labels": [{"name": "type:improvement"}]},
    ])
    if excluded != 1:
        failures.append(f"除外件数が正しくない: {excluded}")
    return failures


def _self_test_retro_try_exclusion_end_to_end():
    """`main()` → 出力 / 終了コードまで貫通した除外の実測（#418・完了条件 1）。

    内部関数の直呼びでは「フィルタは実装されたが本判定の経路から呼ばれていない」退行を
    見逃すため、`sys.argv` を差し替えて `main()` を実際に走らせる。gh は `subprocess.run` を
    fake に差し替えて argv も検証する（#710）。fake は **想定外のコマンドを受けたら
    `AssertionError`** を出す形にし、全ケースで argv 検証が効くようにする。
    REST フォールバック経路・終了コード（0 / 1 / 2）も同じ経路で確認する。
    """
    import contextlib
    import io
    import subprocess

    failures = []
    orig_run = subprocess.run
    orig_argv = sys.argv
    orig_http_get = github_api.http_get
    orig_resolve = github_api.resolve_token
    captured = []

    def _issue(num, title, labels):
        return {
            "number": num, "title": title,
            "labels": [{"name": n} for n in labels],
            "createdAt": "2026-09-01T00:00:00Z", "updatedAt": "2026-09-01T00:00:00Z",
            "milestone": None, "comments": 0,
        }

    def _rest_issue(num, title, labels):
        return {
            "number": num, "title": title,
            "labels": [{"name": n} for n in labels],
            "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z",
            "milestone": None, "comments": 0,
        }

    def make_fake_gh(*, stdout=None, exc=None):
        """gh 呼び出しを記録する fake。想定外のコマンドは AssertionError（#710 argv 検証）。"""
        def fake_run(cmd, **kwargs):
            if not isinstance(cmd, list) or cmd[:2] != ["gh", "issue"] or "list" not in cmd:
                raise AssertionError(f"想定外のコマンドが呼ばれた: {cmd!r}")
            captured.append(cmd)
            if exc is not None:
                raise exc
            return _FakeCompleted(0, stdout=stdout)
        return fake_run

    def check_argv(tag, label):
        """直近の gh 呼び出し argv を検証する（全ケースで実行する）。"""
        if not captured:
            failures.append(f"{tag} subprocess.run が main() の経路から呼ばれていない")
            return
        cmd = captured[-1]
        for required in ("--label", label, "--state", "-R", "--json", "--limit"):
            if required not in cmd:
                failures.append(f"{tag} gh argv に {required} が無い: {cmd}")
        idx = cmd.index("--json") if "--json" in cmd else -1
        if idx < 0 or idx + 1 >= len(cmd):
            failures.append(f"{tag} --json の直後にフィールド指定が無い: {cmd}")
        elif "labels" not in cmd[idx + 1]:
            failures.append(f"{tag} --json に labels フィールドが無い（除外判定に必要）: {cmd}")

    def install_rest(pages):
        """REST フォールバック用の fake（呼び出し回数を数える）。"""
        calls = {"n": 0}

        def fake_http_get(url, token, **kwargs):
            i = calls["n"]
            calls["n"] += 1
            return True, json.dumps(pages[i] if i < len(pages) else [])

        github_api.http_get = fake_http_get
        github_api.resolve_token = lambda: "dummy-token"
        return calls

    def run_main(argv):
        """`main()` を実行し、(stdout 文字列, 終了コード or None) を返す。"""
        sys.argv = ["triage_improvements.py"] + argv
        buf = io.StringIO()
        code = None
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            try:
                main()
            except SystemExit as e:
                code = e.code
        return buf.getvalue(), code

    def rows_of(out, tag):
        try:
            return [r["num"] for r in json.loads(out)["rows"]]
        except Exception as e:  # noqa: BLE001
            failures.append(f"{tag} JSON レポートを解析できない: {e!r} / out={out[:120]!r}")
            return None

    try:
        # ① gh 経路: retro-try 二重ラベルがレポートから消える（exit 0）
        captured.clear()
        subprocess.run = make_fake_gh(stdout=json.dumps([
            _issue(101, "improvement: フックの統合", ["type:improvement"]),
            _issue(102, "retro-try: 手順を直す", ["type:improvement", "type:retro-try"]),
            _issue(103, "improvement: 近似ラベル", ["type:improvement", "type:retro-try-x"]),
        ]))
        out, code = run_main(["--json", "--label", "type:improvement"])
        if code not in (None, 0):
            failures.append(f"① 正常系の終了コードが 0 でない: {code}")
        nums = rows_of(out, "①")
        if nums is not None and nums != [101, 103]:
            failures.append(f"① main() 経由で retro-try が除外されていない: rows={nums}")
        check_argv("①", "type:improvement")

        # ①-b `--label type:retro-try` を明示指定したときは除外しない（構造的 0 件を作らない）
        captured.clear()
        subprocess.run = make_fake_gh(stdout=json.dumps([
            _issue(111, "retro-try: a", ["type:retro-try"]),
            _issue(112, "retro-try: b", ["type:improvement", "type:retro-try"]),
        ]))
        out, code = run_main(["--json", "--label", "type:retro-try"])
        if code not in (None, 0):
            failures.append(f"①-b --label type:retro-try で exit 0 にならない: {code}")
        nums = rows_of(out, "①-b")
        if nums is not None and nums != [111, 112]:
            failures.append(f"①-b 明示指定した type:retro-try まで除外された: rows={nums}")
        check_argv("①-b", "type:retro-try")

        # ①-c gh が配列以外の JSON（エラーオブジェクト）を返したら REST へフォールバックする
        captured.clear()
        subprocess.run = make_fake_gh(stdout='{"message":"Bad credentials"}')
        calls = install_rest([[_rest_issue(401, "improvement: a", ["type:improvement"])], []])
        out, code = run_main(["--json"])
        if calls["n"] == 0:
            failures.append("①-c gh の非配列 JSON を取得成功とみなし REST へフォールバックしていない")
        nums = rows_of(out, "①-c")
        if nums is not None and nums != [401]:
            failures.append(f"①-c REST フォールバックの結果が返っていない: rows={nums}")
        check_argv("①-c", "type:improvement")

        # ①-d gh が JSON でない文字列を返したときも REST へフォールバックする
        captured.clear()
        subprocess.run = make_fake_gh(stdout="not json")
        calls = install_rest([[_rest_issue(402, "improvement: b", ["type:improvement"])], []])
        out, code = run_main(["--json"])
        if calls["n"] == 0:
            failures.append("①-d gh の非 JSON 出力で REST へフォールバックしていない")
        nums = rows_of(out, "①-d")
        if nums is not None and nums != [402]:
            failures.append(f"①-d REST フォールバックの結果が返っていない: rows={nums}")
        check_argv("①-d", "type:improvement")

        github_api.http_get = orig_http_get
        github_api.resolve_token = orig_resolve

        # ② 全件が retro-try → 取得は成功しているが 0 件（fail-closed・exit 1）
        captured.clear()
        subprocess.run = make_fake_gh(stdout=json.dumps([
            _issue(201, "retro-try: a", ["type:improvement", "type:retro-try"]),
        ]))
        _, code = run_main(["--json"])
        if code != 1:
            failures.append(f"② 全件除外で 0 件のとき exit 1 でない（fail-closed 違反）: {code}")
        check_argv("②", "type:improvement")

        # ②-b gh も GH_TOKEN も使えない = 判定不能（exit 2・0 件と同じコードに畳まない）
        captured.clear()
        subprocess.run = make_fake_gh(exc=FileNotFoundError())
        github_api.resolve_token = lambda: ""
        _, code = run_main(["--json"])
        if code != 2:
            failures.append(f"②-b 取得失敗が判定不能(exit 2)になっていない: {code}")
        check_argv("②-b", "type:improvement")
        github_api.resolve_token = orig_resolve

        # ③ REST API フォールバック経路でも除外される（経路差を作らない）
        captured.clear()
        subprocess.run = make_fake_gh(exc=FileNotFoundError())
        calls = install_rest([
            [
                _rest_issue(301, "improvement: a", ["type:improvement"]),
                _rest_issue(302, "retro-try: b", ["type:improvement", "type:retro-try"]),
            ],
            [],
        ])
        out, code = run_main(["--json"])
        nums = rows_of(out, "③")
        if nums is not None and nums != [301]:
            failures.append(f"③ REST フォールバック経路で retro-try が除外されない: rows={nums}")
        check_argv("③", "type:improvement")
    finally:
        subprocess.run = orig_run
        sys.argv = orig_argv
        github_api.http_get = orig_http_get
        github_api.resolve_token = orig_resolve
    return failures


def _self_test():
    """純粋関数（API 非依存）のセルフテスト。"""
    fail = 0

    def check(cond, msg):
        nonlocal fail
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            fail += 1

    # categorize: 監査タグ優先
    cat, phase = categorize({"title": "[監査P2/SEC-03] 認証強化", "labels": []})
    check(cat == "監査:セキュリティ" and phase == "P2", f"audit tag categorize ({cat},{phase})")
    # categorize: 未知ドメインコードは素通し
    cat, _ = categorize({"title": "[監査P1/FOO-01] なにか", "labels": []})
    check(cat == "監査:FOO", f"unknown domain passthrough ({cat})")
    # categorize: キーワードクラスタ（汎用カテゴリ）
    cat, _ = categorize({"title": "improvement: stop-router フックの統合", "labels": []})
    check(cat == "ハーネス/フック", f"keyword cluster hook ({cat})")
    cat, _ = categorize({"title": "self-reviewer スキルの description 改善", "labels": []})
    check(cat == "スキル整備", f"keyword cluster skill ({cat})")
    # categorize: Epic
    cat, _ = categorize({"title": "[Epic] 改善統合追跡", "labels": []})
    check(cat == "（Epic/親追跡）", f"epic ({cat})")
    # categorize: 未分類
    cat, _ = categorize({"title": "なんらかのよくわからない件", "labels": []})
    check(cat == "（その他/未分類）", f"uncategorized ({cat})")
    # normalize_tokens: ストップワード・記号除去
    toks = normalize_tokens("[Epic] フック の 統合 improvement:")
    check("フック" in toks and "improvement" not in toks and "の" not in toks,
          f"normalize_tokens ({toks})")
    # detect_duplicates: 監査コード重複
    dups = detect_duplicates([
        {"num": 1, "title": "[監査P1/SEC-01] a"},
        {"num": 2, "title": "[監査P1/SEC-01] b"},
    ])
    check(any(d["type"] == "audit-code" for d in dups), f"dup audit-code ({dups})")
    # detect_duplicates: タイトル酷似
    dups = detect_duplicates([
        {"num": 3, "title": "stop-router フック 統合 改善"},
        {"num": 4, "title": "stop-router フック 統合 強化"},
    ])
    check(any(d["type"] == "title-similar" for d in dups), f"dup title-similar ({dups})")

    # assign_priority: 規則 1（fix: + 実測された失敗事象）
    check(assign_priority("fix: 一覧が 500 になる", "grep で再現手順を確認した") == "high",
          "assign_priority rule1")
    # assign_priority: 規則 1 は失敗事象の記述が無ければ発火しない
    check(assign_priority("fix: たぶん直したほうがよい", "気になる") == "medium",
          "assign_priority rule1 needs failure evidence")
    # assign_priority: 規則 2（後回しシグナル）が規則 3 より優先される
    check(assign_priority("improvement: 検査を足す", "低頻度なので急がない", "CHECK") == "low",
          "assign_priority rule2 precedence")
    # assign_priority: 規則 3（予防的カテゴリ）
    check(assign_priority("improvement: 検査を足す", "あると安全", "CHECK") == "medium",
          "assign_priority rule3")
    # assign_priority: 規則 4（判定材料不足の既定）
    check(assign_priority("improvement: なにか", "") == "medium", "assign_priority rule4")
    # should_demote_high: 予防的表現のみ → 降格
    check(should_demote_high("〜を検知できるようにすべき") is True, "should_demote_high preventive")
    # should_demote_high: 実測記述あり → 据え置き
    check(should_demote_high("grep 実測で 3 件の不整合を確認") is False, "should_demote_high measured")
    # select_keep: 要求の包含関係で決める（新しい / 古いでは決めない）
    check(select_keep({"num": 81, "requirements": {"strip"}},
                      {"num": 221, "requirements": {"strip", "lineno"}}) == 221,
          "select_keep superset")
    check(select_keep({"num": 201, "requirements": {"a", "b"}},
                      {"num": 350, "requirements": {"a"}}) == 201,
          "select_keep superset reversed")
    # select_keep: 包含関係が無ければ判定しない（人が本文を突き合わせる）
    check(select_keep({"num": 1, "requirements": {"a"}},
                      {"num": 2, "requirements": {"b"}}) is None,
          "select_keep no containment")
    # high_ratio_ok: 閾値
    check(high_ratio_ok(30, 100) is True, "high_ratio_ok under ceiling")
    check(high_ratio_ok(31, 100) is False, "high_ratio_ok over ceiling")
    check(high_ratio_ok(1, 0) is True, "high_ratio_ok empty")

    # gh/REST 委譲到達テスト（PR #849 Layer1 指摘1/4。実エントリポイント経由で実測する）
    for name, fn in (
        ("run_gh 委譲到達 + stderr 非対称挙動", _self_test_run_gh_delegates_with_stderr_asymmetry),
        ("is_gh_unavailable 等価性", _self_test_is_gh_unavailable_equivalence),
        ("type:retro-try 除外の入力バリアント (#418)", _self_test_retro_try_exclusion_variants),
        ("type:retro-try 除外の main() 貫通 (#418)", _self_test_retro_try_exclusion_end_to_end),
    ):
        # 個別テストが例外で落ちても未捕捉トレースバックにせず FAIL として報告する
        try:
            msgs = fn()
        except Exception as e:  # noqa: BLE001
            msgs = [f"テスト自体が例外で終了: {e!r}"]
        for msg in msgs:
            check(False, f"[{name}] {msg}")

    if fail == 0:
        print("PASS: triage_improvements self-test (24 checks + retro-try 除外 #418)")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description="改善 Issue 棚卸し支援ツール（読み取り専用）")
    ap.add_argument(
        "--label", default="type:improvement",
        help=("対象ラベル（既定: type:improvement）。取得結果からは type:retro-try を除外する"
              "（Step G-1 の集計に限った射程）。ただし --label type:retro-try と明示指定した"
              "ときは除外しない"),
    )
    ap.add_argument("--state", default="open", choices=["open", "closed", "all"], help="Issue 状態")
    ap.add_argument("--json", action="store_true", help="JSON を出力")
    ap.add_argument("--out", help="Markdown レポートの出力先パス")
    ap.add_argument("--epic-threshold", type=int, default=6,
                    help="Epic 統合候補とみなす同一カテゴリの最小件数（既定: 6）")
    ap.add_argument("--self-test", action="store_true", help="純粋関数のセルフテストを実行")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(_self_test())

    issues, fetched_ok = fetch_issues(args.label, args.state)
    if not fetched_ok:
        # 判定不能: 取得経路そのものが成立していない（gh 不在 + トークン不在 / REST 失敗）。
        # 「対象 0 件」と同じコードに畳むと、運用者が原因を切り分けられない（check-tool-design-rules.md §1）
        print(
            f"⚠️ Issue を取得できませんでした（判定不能 / label={args.label}）。"
            "gh CLI と GH_TOKEN の利用可否・ネットワークを確認してください",
            file=sys.stderr,
        )
        sys.exit(2)
    if not issues:
        # fail-closed: 取得は成功しているが対象 0 件（全件が type:retro-try で除外された場合を含む）。
        # 合格(0)へ丸めない（check-tool-design-rules.md §2）
        print(
            f"❌ 対象 Issue が 0 件でした（取得は成功 / label={args.label}）。"
            "ラベル指定が意図どおりか確認してください。"
            "既定ラベルでの取得では type:retro-try が除外されます（#418）",
            file=sys.stderr,
        )
        sys.exit(1)

    rep = build_report(issues, args.epic_threshold)

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return

    md = render_markdown(rep)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"レポートを {args.out} に出力しました（{rep['total']} 件）")
    else:
        print(md)


if __name__ == "__main__":
    main()
