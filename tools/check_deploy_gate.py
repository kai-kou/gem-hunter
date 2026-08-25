#!/usr/bin/env python3
"""check_deploy_gate.py — 本番デプロイ実行前のゲート判定（読み取り専用・fail-closed）

【背景・設計の正本】
`content/discussions/sprint-env-lifecycle-20260820/whiteboard.md`（Issue #231・議論型レビュー
round 3・lead 判定「B: 本番デプロイの発火点」「C: 判定別の可否と fail-closed」）。要点:

  - 本番デプロイ（`npm run deploy`）は main 上に「スプリントレビュー判定が未確定、または
    直近判定が rejected（それを覆す新しい判定がまだ無い）」スプリント Issue が 1 件でも
    残っている間は実行しない（デプロイの直列化）。
  - 非スプリント PR（改善 Issue・retro-try・docs）のマージも main HEAD ごと本番へ出すため、
    **すべてのデプロイ実行前** に本ゲートを通す（スプリント PR 経由に限らない）。
  - accepted / accepted_with_conditions はゲートを塞がない。rejected と「判定コメントが
    まだ無い」は塞ぐ。

【判定ロジック】
  1. open かつ `status:in-progress` ラベルの Issue を列挙する。
  2. その中から「スプリント対象」を判定する: タイトルが `SP-\\d+` を含む、
     または **信頼できる投稿者**（`TRUSTED_VERDICT_AUTHOR_ASSOCIATIONS`）による
     Issue コメントに `## 🏃 Session Sprint Planning` があるもの
     （本文中の `SP-\\d+` 単純一致は判定に使わない。過去スプリントへの言及だけで
     誤ってゲート対象になる誤検知を防ぐ・Issue #218）。
  3. スプリント対象 Issue ごとに、`## 🔍 Sprint Review 判定` を含み
     `**結果**: accepted|accepted_with_conditions|rejected` の行を持つ **かつ投稿者権限が
     `TRUSTED_VERDICT_AUTHOR_ASSOCIATIONS`（OWNER/MEMBER/COLLABORATOR）のいずれかである**
     （#236）コメントのうち最新のもの（`created_at` 最大）を採用する。
       - 判定コメントが無い、または権限のない投稿者のものしかない → ゲートを塞ぐ（レビュー未実施）
       - 最新判定が `rejected` → ゲートを塞ぐ
       - 最新判定が `accepted` / `accepted_with_conditions` → 塞がない
  4. 塞ぐ Issue が 1 件でもあれば「待機」、無ければ「デプロイ可」。

【終了コード（fail-closed）】
  0 = デプロイ可（ゲートを塞いでいる Issue なし）
  1 = 待機（ゲートを塞いでいる Issue がある。stdout/stderr に理由と Issue 番号を出力）
  2 = 判定不能（GitHub API 到達不可・応答パース失敗等）。呼び出し側はこの場合デプロイしない
      （fail-closed。判定不能を「デプロイ可」の既定値にしない）

【API チャネル】
`gh` があれば `gh` を使い、失敗（非 0 終了・例外・クラウドでの未インストール）したら
`urllib` + `GH_TOKEN`/`GITHUB_TOKEN`（`https://api.github.com`）にフォールバックする
（`tools/sprint_backlog_sync.py` の多段フォールバックと同じパターン。SSOT:
`docs/rules/github-mcp-fallback-patterns.md`）。両方失敗したら exit code 2 で理由を出力する。

使い方:
    python3 tools/check_deploy_gate.py
    python3 tools/check_deploy_gate.py --json
    python3 tools/check_deploy_gate.py --repo owner/name
    python3 tools/check_deploy_gate.py --self-test    # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_slug import resolve_repo_slug  # noqa: E402

JST = timezone(timedelta(hours=9))

REPO = resolve_repo_slug()

# ──────────────────────────────────────────────
# 判定に使う定数・正規表現
# ──────────────────────────────────────────────

SPRINT_ID_RE = re.compile(r"SP-\d+")
SPRINT_PLANNING_MARKER = "## 🏃 Session Sprint Planning"
VERDICT_MARKER = "## 🔍 Sprint Review 判定"
# Sprint Review 判定コメントとして信頼する投稿者権限（#236）。
# これ以外（NONE/CONTRIBUTOR/FIRST_TIME_CONTRIBUTOR 等）の投稿者による判定コメントは無視する。
TRUSTED_VERDICT_AUTHOR_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
# accepted_with_conditions は "accepted" を部分文字列として含むため、
# 先に置かないと "accepted_with_conditions" 行が "accepted" と誤判定される。
VERDICT_RESULT_RE = re.compile(
    r"\*\*結果\*\*:\s*(accepted_with_conditions|accepted|rejected)"
)

REASON_NO_VERDICT = "Sprint Review 判定が未実施です"
REASON_REJECTED = "直近の Sprint Review 判定が rejected です"


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械処理には使わない（datetime-rules.md）。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def _validate_repo() -> None:
    owner, _, name = REPO.partition("/")
    if not owner or not name or "__" in REPO:
        print(
            f"ERROR: REPO の形式が不正です: '{REPO}'（owner/name 形式が必要。"
            "bootstrap.sh でプレースホルダを置換するか --repo で指定してください）",
            file=sys.stderr,
        )
        sys.exit(2)


# ──────────────────────────────────────────────
# API チャネル（gh → urllib + GH_TOKEN の多段フォールバック）
# GH_TOKEN の値はログ・エラー出力に一切出さない。
# ──────────────────────────────────────────────


def _run_gh(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return False, "gh コマンドが見つかりません"
    except subprocess.TimeoutExpired:
        return False, "gh コマンドがタイムアウトしました"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or f"gh 実行失敗: {' '.join(args)}"
    return True, result.stdout.strip()


def _http_get(url: str, token: str) -> tuple[bool, str]:
    """GitHub REST を GET する。token をサブプロセス引数に載せず Python プロセス内で
    ヘッダを組み立てる（`ps` / `/proc/<pid>/cmdline` 経由の露出防止・既存パターン踏襲）。
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gem-hunter-check-deploy-gate",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return True, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"接続失敗（{type(e).__name__}）"
    except TimeoutError:
        return False, "リクエストがタイムアウトしました"


def fetch_in_progress_sprint_candidates() -> tuple[list[dict], str | None]:
    """open かつ `status:in-progress` の Issue 一覧（number/title/body）を取得する。

    Returns (issues, error_reason)。取得失敗時は issues=[] で error_reason に理由を入れる
    （「取得失敗」を「0 件（ゲートなし）」と混同しない・fail-closed の前提）。
    """
    ok, out = _run_gh([
        "issue", "list", "-R", REPO, "--state", "open", "--label", "status:in-progress",
        "--json", "number,title,body", "--limit", "100",
    ])
    if ok:
        try:
            issues = json.loads(out)
            return [
                {"number": i["number"], "title": i.get("title", ""), "body": i.get("body") or ""}
                for i in issues
            ], None
        except (json.JSONDecodeError, KeyError, TypeError):
            ok = False
            out = "gh の JSON 応答が不正"
    gh_err = out

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return [], f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"

    label_q = urllib.parse.quote("status:in-progress", safe="")
    issues: list[dict] = []
    for page in range(1, 4):  # 100件 x 3ページ = 最大300件
        ok2, out2 = _http_get(
            f"https://api.github.com/repos/{REPO}/issues"
            f"?state=open&labels={label_q}&per_page=100&page={page}",
            token,
        )
        if not ok2:
            return [], f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
        try:
            batch = json.loads(out2)
        except json.JSONDecodeError:
            return [], f"gh 失敗（{gh_err}）・REST 応答のパースに失敗"
        if not batch:
            break
        # /issues エンドポイントは PR も含むため pull_request キーで除外する
        issues.extend(
            {"number": i["number"], "title": i.get("title", ""), "body": i.get("body") or ""}
            for i in batch
            if "pull_request" not in i
        )
        if len(batch) < 100:
            break
    return issues, None


def fetch_issue_comments(number: int) -> tuple[list[dict], str | None]:
    """Issue のコメント一覧（body / created_at / author_association）を取得する。
    順序は保証しないため、利用側（`latest_verdict`）で `created_at` によるソートを行う。
    `author_association` は投稿者権限検証（#236）に使う。取得できない場合は空文字を返し、
    `latest_verdict` 側で「信頼できない投稿者」として扱う（fail-closed）。
    """
    ok, out = _run_gh([
        "issue", "view", str(number), "-R", REPO,
        "--json", "comments",
    ])
    if ok:
        try:
            data = json.loads(out)
            return [
                {
                    "body": c.get("body", ""),
                    "created_at": c.get("createdAt", ""),
                    "author_association": c.get("authorAssociation", ""),
                }
                for c in data.get("comments", [])
            ], None
        except (json.JSONDecodeError, AttributeError):
            ok = False
            out = "gh の JSON 応答が不正"
    gh_err = out

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return [], f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"

    comments: list[dict] = []
    for page in range(1, 4):
        ok2, out2 = _http_get(
            f"https://api.github.com/repos/{REPO}/issues/{number}/comments"
            f"?per_page=100&page={page}",
            token,
        )
        if not ok2:
            return [], f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
        try:
            batch = json.loads(out2)
        except json.JSONDecodeError:
            return [], f"gh 失敗（{gh_err}）・REST 応答のパースに失敗"
        if not batch:
            break
        comments.extend(
            {
                "body": c.get("body", ""),
                "created_at": c.get("created_at", ""),
                "author_association": c.get("author_association", ""),
            }
            for c in batch
        )
        if len(batch) < 100:
            break
    return comments, None


# ──────────────────────────────────────────────
# 判定ロジック（純関数・API 非依存 = --self-test の対象）
# ──────────────────────────────────────────────


def is_sprint_issue(title: str, body: str, comments: list[dict]) -> bool:
    """スプリント対象 Issue かどうか（次の 2 条件のどちらかで判定する）。

    1. タイトルが `SP-n` を含む（例: `feat(SP-10): ...`）
    2. 信頼できる投稿者（`TRUSTED_VERDICT_AUTHOR_ASSOCIATIONS`）による Issue コメントに
       `## 🏃 Session Sprint Planning` がある（＝実際にスプリントとして着手された Issue）

    本文（`body`）中の `SP-n` 単純一致は判定に使わない: 過去スプリントに *言及しているだけ*
    の Issue（コメント 0 件）まで誤ってスプリント対象にしてしまい、Sprint Review 判定コメントが
    構造上つかないため open の間ずっとデプロイゲートを塞ぎ続ける（Issue #218 で実際に発生）。
    `body` 引数はシグネチャ互換のため残すが判定には使わない。

    権限のない投稿者による Sprint Planning マーカーは無視する（#236: 権限のない投稿者が
    任意の `status:in-progress` Issue をスプリント対象化し、正当な判定コメントが付かないまま
    デプロイゲートを恒久的に塞げてしまう欠陥の防止。`latest_verdict` の権限フィルタと対）。
    """
    del body  # 判定には使わない（本文の部分一致は撤廃。docstring 参照）
    if SPRINT_ID_RE.search(title):
        return True
    return any(
        SPRINT_PLANNING_MARKER in (c.get("body") or "")
        and c.get("author_association") in TRUSTED_VERDICT_AUTHOR_ASSOCIATIONS
        for c in comments
    )


def latest_verdict(comments: list[dict]) -> str | None:
    """コメント群から最新の Sprint Review 判定結果を返す（無ければ None）。

    `created_at` 昇順に安定ソートしてから走査し、最後に見つかった判定を採用する
    （`created_at` が空文字のコメントは取得順の相対位置を維持したまま先頭側に寄る。
    GitHub API は常に `created_at` を返すため実運用では欠落しない想定）。

    投稿者の `author_association` が `TRUSTED_VERDICT_AUTHOR_ASSOCIATIONS` に含まれない
    コメントは判定対象から除外する（#236: 権限のない投稿者がデプロイ可否を左右できる欠陥の修正）。
    """
    verdicts = []
    for c in sorted(comments, key=lambda c: c.get("created_at") or ""):
        body = c.get("body") or ""
        if VERDICT_MARKER not in body:
            continue
        if c.get("author_association") not in TRUSTED_VERDICT_AUTHOR_ASSOCIATIONS:
            continue
        m = VERDICT_RESULT_RE.search(body)
        if m:
            verdicts.append(m.group(1))
    return verdicts[-1] if verdicts else None


def evaluate_issue(issue: dict, comments: list[dict]) -> dict | None:
    """Issue 1 件を評価する。ゲートを塞ぐなら理由付き dict、塞がないなら None を返す。"""
    if not is_sprint_issue(issue["title"], issue.get("body", ""), comments):
        return None
    verdict = latest_verdict(comments)
    if verdict is None:
        return {"number": issue["number"], "title": issue["title"], "reason": REASON_NO_VERDICT}
    if verdict == "rejected":
        return {"number": issue["number"], "title": issue["title"], "reason": REASON_REJECTED}
    # accepted / accepted_with_conditions はゲートを塞がない
    return None


def decide(issues_with_comments: list[tuple[dict, list[dict]]]) -> dict:
    """全 Issue を集約してゲート判定を返す。

    Returns:
        {"can_deploy": bool, "blocking_issues": [{"number", "title", "reason"}, ...]}
    """
    blocking = []
    for issue, comments in issues_with_comments:
        r = evaluate_issue(issue, comments)
        if r is not None:
            blocking.append(r)
    return {"can_deploy": not blocking, "blocking_issues": blocking}


def exit_code_for(can_deploy: bool | None) -> int:
    """判定結果を終了コードへ写像する唯一の関数（0/1/2 のマッピングを一元化）。

    can_deploy=None は「判定不能」（API 到達不可等）を表し、fail-closed で 2 を返す
    （デプロイ可 0 を既定値にしない）。
    """
    if can_deploy is None:
        return 2
    return 0 if can_deploy else 1


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _issue(number: int = 1, title: str = "SP-1: 何かをする", body: str = "") -> dict:
    return {"number": number, "title": title, "body": body}


def _verdict_comment(
    result: str,
    created_at: str = "2026-08-20T10:00:00Z",
    author_association: str = "OWNER",
) -> dict:
    return {
        "body": f"{VERDICT_MARKER}\n\n**結果**: {result}\n",
        "created_at": created_at,
        "author_association": author_association,
    }


def _self_test_is_sprint_issue() -> list[str]:
    failures = []
    # タイトルに SP-n
    if not is_sprint_issue("SP-3: 検索機能", "", []):
        failures.append("is_sprint_issue: タイトルの SP-n を検知できていない")
    # タイトルに SP-n（feat(SP-10): 形式）
    if not is_sprint_issue("feat(SP-10): 何かを追加", "", []):
        failures.append("is_sprint_issue: feat(SP-n) 形式のタイトルを検知できていない")
    # コメントに Sprint Planning マーカー（タイトルに SP-n が無くても対象・#231 の形）
    # 信頼できる投稿者（OWNER）によるものであること（#236）
    comments = [{"body": f"{SPRINT_PLANNING_MARKER}\n- ゴール: ...", "created_at": "",
                 "author_association": "OWNER"}]
    if not is_sprint_issue("改善: 何か", "", comments):
        failures.append("is_sprint_issue: Session Sprint Planning コメントを検知できていない")
    # #236: 権限のない投稿者による Sprint Planning マーカーは無視する
    untrusted_comments = [{"body": f"{SPRINT_PLANNING_MARKER}\n- ゴール: ...", "created_at": "",
                            "author_association": "CONTRIBUTOR"}]
    if is_sprint_issue("改善: 何か", "", untrusted_comments):
        failures.append("is_sprint_issue: 権限のない投稿者の Sprint Planning コメントで誤検知している")
    # 本文で SP-n に言及しているだけ・コメント 0 件は対象外（#218 の再現・本文の部分一致は撤廃）
    if is_sprint_issue("improvement: MVP 後の開発方針を決める", "過去の SP-11 / SP-12 を踏まえて…", []):
        failures.append("is_sprint_issue: 本文の SP-n 言及だけで誤検知している（#218 再現ケース）")
    # いずれも無ければスプリント対象ではない（= ゲート対象外）
    if is_sprint_issue("bug: 何かが壊れている", "詳細説明", []):
        failures.append("is_sprint_issue: 非スプリント Issue を誤検知している")
    return failures


def _self_test_verdict_result_re() -> list[str]:
    """判定コメントのパース。accepted_with_conditions が accepted に化けないことを保証する。"""
    failures = []
    cases = [
        ("**結果**: accepted", "accepted"),
        ("**結果**: accepted_with_conditions", "accepted_with_conditions"),
        ("**結果**: rejected", "rejected"),
        ("前置き\n\n**結果**: accepted_with_conditions\n\n後続テキスト", "accepted_with_conditions"),
    ]
    for body, want in cases:
        m = VERDICT_RESULT_RE.search(body)
        got = m.group(1) if m else None
        if got != want:
            failures.append(f"VERDICT_RESULT_RE: {body!r} → {got!r}（期待 {want!r}）")
    # マーカー行が無い本文からは判定を抽出しない（latest_verdict 側の前提）
    no_marker = "本文中に **結果**: accepted があるが判定マーカーが無い"
    if VERDICT_MARKER in no_marker:
        failures.append("テスト前提が不正: no_marker に VERDICT_MARKER が混入している")
    return failures


def _self_test_latest_verdict_order() -> list[str]:
    """最新（created_at 最大）の判定が優先されることを保証する（優先順位の固定）。"""
    failures = []

    # 判定コメントが無い
    if latest_verdict([{"body": "ただの進捗コメント", "created_at": "2026-08-20T09:00:00Z"}]) is not None:
        failures.append("latest_verdict: 判定コメントが無いのに None 以外を返した")

    # 単一の判定コメント
    if latest_verdict([_verdict_comment("accepted")]) != "accepted":
        failures.append("latest_verdict: 単一 accepted 判定を正しく取れていない")

    # rejected → accepted の順（時系列どおり）で投稿 → 最新の accepted が勝つ
    comments = [
        _verdict_comment("rejected", "2026-08-20T09:00:00Z"),
        _verdict_comment("accepted", "2026-08-20T15:00:00Z"),
    ]
    if latest_verdict(comments) != "accepted":
        failures.append("latest_verdict: 新しい accepted が古い rejected に負けている")

    # 取得順が created_at と逆でも created_at でソートして最新を採用する
    comments_unordered = [
        _verdict_comment("accepted", "2026-08-20T15:00:00Z"),
        _verdict_comment("rejected", "2026-08-20T09:00:00Z"),
    ]
    if latest_verdict(comments_unordered) != "accepted":
        failures.append("latest_verdict: 取得順が逆でも created_at で最新判定を選べていない")

    # accepted → rejected（差し戻し）の順 → 最新の rejected が勝つ
    comments_rejected_last = [
        _verdict_comment("accepted", "2026-08-20T09:00:00Z"),
        _verdict_comment("rejected", "2026-08-20T15:00:00Z"),
    ]
    if latest_verdict(comments_rejected_last) != "rejected":
        failures.append("latest_verdict: 新しい rejected が古い accepted に負けている")

    return failures


def _self_test_verdict_author_guard() -> list[str]:
    """#236: 権限のない投稿者の判定コメントは無視されることを保証する。"""
    failures = []

    # 権限のない投稿者（CONTRIBUTOR）の判定コメントのみ → 判定なし扱い（None）
    r = latest_verdict([_verdict_comment("accepted", author_association="CONTRIBUTOR")])
    if r is not None:
        failures.append(f"latest_verdict: CONTRIBUTOR の判定コメントが採用された（{r!r}）")

    # NONE（無関係な外部ユーザー）が rejected を投稿しても正当な accepted を覆せない
    comments = [
        _verdict_comment("accepted", "2026-08-20T09:00:00Z", author_association="OWNER"),
        _verdict_comment("rejected", "2026-08-20T15:00:00Z", author_association="NONE"),
    ]
    if latest_verdict(comments) != "accepted":
        failures.append("latest_verdict: 権限のない投稿者の rejected が正当な accepted を覆した")

    # author_association が空文字（フィールド取得に失敗した場合の既定値）→ fail-closed で除外
    r = latest_verdict([_verdict_comment("accepted", author_association="")])
    if r is not None:
        failures.append(f"latest_verdict: author_association 空文字の判定コメントが採用された（{r!r}）")

    # author_association キー自体が欠落（フォールバック実装の想定外入力）→ fail-closed で除外
    comment_missing_key = _verdict_comment("accepted")
    del comment_missing_key["author_association"]
    if latest_verdict([comment_missing_key]) is not None:
        failures.append("latest_verdict: author_association キー欠落の判定コメントが採用された")

    # 信頼される権限（MEMBER / COLLABORATOR）の判定は引き続き採用される
    for assoc in ("MEMBER", "COLLABORATOR"):
        r = latest_verdict([_verdict_comment("accepted", author_association=assoc)])
        if r != "accepted":
            failures.append(f"latest_verdict: {assoc} の判定コメントが採用されなかった（{r!r}）")

    return failures


def _self_test_evaluate_issue() -> list[str]:
    failures = []

    # 判定コメントが無いスプリント Issue → ゲートを塞ぐ（レビュー未実施）
    r = evaluate_issue(_issue(1, "SP-1: 検索"), [])
    if r is None or r["reason"] != REASON_NO_VERDICT:
        failures.append(f"evaluate_issue: 判定未実施は塞ぐことを期待したが {r}")

    # rejected → ゲートを塞ぐ
    r = evaluate_issue(_issue(2, "SP-2: 詳細"), [_verdict_comment("rejected")])
    if r is None or r["reason"] != REASON_REJECTED:
        failures.append(f"evaluate_issue: rejected は塞ぐことを期待したが {r}")

    # accepted → 塞がない
    r = evaluate_issue(_issue(3, "SP-3: 一覧"), [_verdict_comment("accepted")])
    if r is not None:
        failures.append(f"evaluate_issue: accepted は塞がないことを期待したが {r}")

    # accepted_with_conditions → 塞がない
    r = evaluate_issue(_issue(4, "SP-4: 通知"), [_verdict_comment("accepted_with_conditions")])
    if r is not None:
        failures.append(f"evaluate_issue: accepted_with_conditions は塞がないことを期待したが {r}")

    # 非スプリント Issue はコメント内容に関係なく塞がない（in-progress の bug 修正等）
    r = evaluate_issue(_issue(5, "fix: ログイン画面のバグ"), [_verdict_comment("rejected")])
    if r is not None:
        failures.append(f"evaluate_issue: 非スプリント Issue は塞がないことを期待したが {r}")

    return failures


def _self_test_decide_and_exit_code() -> list[str]:
    failures = []

    # 塞ぐ Issue が無い → デプロイ可（exit 0）
    result = decide([
        (_issue(1, "SP-1: a"), [_verdict_comment("accepted")]),
        (_issue(2, "fix: 無関係なバグ"), []),
    ])
    if result["can_deploy"] is not True or result["blocking_issues"]:
        failures.append(f"decide: 全 accepted で can_deploy=True を期待したが {result}")
    if exit_code_for(result["can_deploy"]) != 0:
        failures.append("exit_code_for: can_deploy=True は exit 0 を期待")

    # 1 件でも塞ぐ Issue があれば待機（exit 1）。塞がない Issue が混在していても変わらない
    result = decide([
        (_issue(1, "SP-1: a"), [_verdict_comment("accepted")]),
        (_issue(2, "SP-2: b"), [_verdict_comment("rejected")]),
        (_issue(3, "SP-3: c"), []),  # 判定未実施
    ])
    if result["can_deploy"] is not False:
        failures.append(f"decide: rejected/未実施混在で can_deploy=False を期待したが {result}")
    blocking_numbers = sorted(b["number"] for b in result["blocking_issues"])
    if blocking_numbers != [2, 3]:
        failures.append(f"decide: 塞ぐ Issue 番号が不一致: {blocking_numbers}（期待 [2, 3]）")
    if exit_code_for(result["can_deploy"]) != 1:
        failures.append("exit_code_for: can_deploy=False は exit 1 を期待")

    # 判定不能（API 到達不可等）は can_deploy=None → exit 2（fail-closed）
    if exit_code_for(None) != 2:
        failures.append("exit_code_for: can_deploy=None は exit 2（fail-closed）を期待")

    return failures


def run_self_test() -> int:
    groups = [
        ("スプリント対象判定", _self_test_is_sprint_issue),
        ("判定コメントのパース（accepted_with_conditions 優先）", _self_test_verdict_result_re),
        ("最新判定の優先順位", _self_test_latest_verdict_order),
        ("判定コメントの投稿者権限検証", _self_test_verdict_author_guard),
        ("Issue 単位のゲート判定", _self_test_evaluate_issue),
        ("集約判定と終了コードのマッピング", _self_test_decide_and_exit_code),
    ]
    failed_groups = 0
    total_failures = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed_groups += 1
            total_failures += len(failures)
            for f in failures:
                print(f"FAIL[{name}]: {f}")

    if total_failures:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed_groups} グループ失敗 "
              f"({total_failures} 件の不一致)")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="本番デプロイ実行前のゲート判定（読み取り専用・fail-closed）。"
                     "0=デプロイ可 / 1=待機 / 2=判定不能。",
    )
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument("--repo", default=None, help="owner/name（既定: git remote から解決）")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    global REPO
    if args.repo:
        REPO = args.repo
    _validate_repo()

    issues, err = fetch_in_progress_sprint_candidates()
    if err is not None:
        _emit_error(f"Issue 一覧の取得に失敗しました（{err}）", args.json)
        sys.exit(2)

    issues_with_comments: list[tuple[dict, list[dict]]] = []
    for issue in issues:
        comments, cerr = fetch_issue_comments(issue["number"])
        if cerr is not None:
            _emit_error(f"Issue #{issue['number']} のコメント取得に失敗しました（{cerr}）", args.json)
            sys.exit(2)
        issues_with_comments.append((issue, comments))

    result = decide(issues_with_comments)
    result["checked_at"] = now_jst_str()
    result["repo"] = REPO

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["can_deploy"]:
            print("デプロイ可: ゲートを塞いでいる Issue はありません")
        else:
            print("デプロイ待機: 以下の Issue がゲートを塞いでいます")
            for b in result["blocking_issues"]:
                print(f"  #{b['number']} {b['title']} — {b['reason']}")

    sys.exit(exit_code_for(result["can_deploy"]))


def _emit_error(message: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {"can_deploy": None, "error": message, "checked_at": now_jst_str(), "repo": REPO},
            ensure_ascii=False,
        ))
    else:
        print(f"ERROR: 判定不能: {message}", file=sys.stderr)


if __name__ == "__main__":
    main()
