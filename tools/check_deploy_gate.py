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

  🔴 **Issue #471（決定ログ `D-46`）による改訂**: CP-4（マルチセッション並行運用）前提のこの
  リポジトリでは、in-progress スプリントの並行度が上がるほどデプロイ窓が閉じ続ける問題が
  実測された（#470）。**「main HEAD にそのスプリントのコミットが含まれている」場合だけ塞ぐ**
  よう改める。まだ main にマージされていない in-progress スプリントは本番の中身に影響しない
  ため、デプロイを塞ぐ理由がない（判定未実施・rejected のどちらでも同じ）。

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
       - 判定コメントが無い、または権限のない投稿者のものしかない → 塞ぐ候補（レビュー未実施）
       - 最新判定が `rejected` → 塞ぐ候補
       - 最新判定が `accepted` / `accepted_with_conditions` → 塞がない（#471 改訂後もここは不変）
  4. **（#471 で追加）** 塞ぐ候補になった Issue だけ、追加で「main に反映済みか」を判定する
     （`is_merged_into_main`）: Issue タイトルの `SP-\\d+` を抽出し、**同じトークンをタイトルに
     含む merged PR** を検索、その `merge_commit_sha` が `origin/main` の祖先かどうかを
     `git merge-base --is-ancestor` で判定する。
       - merged PR が見つかり、その merge commit が main の祖先 → 反映済み（塞ぐ）
       - merged PR はあるが祖先ではない → 未マージと **確定できた** → 塞がない
       - **（#723 で追加）** merged PR が 0 件のとき、それだけでは「本当に未マージ」か
         「`SP-n` トークンがタイトルに無く検索でヒットしなかっただけ」かを区別できないため、
         **同じトークンで open PR も検索する**: open PR が見つかれば「未マージと確定できた」
         → 塞がない。open も merged も 0 件、または open PR 検索自体が失敗した場合は
         **判定不能** → 塞ぐ（fail-closed。旧実装はここを無条件で「未マージ確定」＝ fail-open
         にしていた欠陥があった）
       - **判定不能**（SP-n がタイトルに無い・PR 検索/取得の失敗・git 判定の失敗）→ 塞ぐ
         （fail-closed。判定不能を「未マージ」の既定値にしない）
  5. 塞ぐ Issue が 1 件でもあれば「待機」、無ければ「デプロイ可」。

  【採用した判定手段の理由・限界】 `merge_commit_sha` の祖先判定を採用した理由は、squash /
  merge / rebase のどのマージ方式でも本番に実際に反映されたかを一意に判定できる唯一の値
  だから（PR の `merged` フラグだけでは「マージ後に main から巻き戻された」ケースを見逃す）。
  **限界**: ① このリポジトリのスプリント PR は「Closes #N」を書かない運用（`pr-review-flow-
  summary.md`）のため GitHub の自動リンク（timeline cross-reference）に頼れず、Issue → PR の
  対応付けは「Issue タイトルと PR タイトルが同じ `SP-n` トークンを含む」という命名規約に依存
  する。Sprint Planning コメントのみでスプリント判定された Issue（タイトルに `SP-n` が無い）は
  対応する PR を機械的に特定できないため、常に判定不能 → fail-closed で塞ぐ（安全側に倒す）。
  ② PR タイトルに `SP-n` トークンを含めない運用に変えた場合も同様に判定不能になる。

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

# `fetch_issue_comments` の REST フォールバックが走査するページ数の上限（#237 レビュー指摘:
# 300 件の旧上限だと、gh 障害時に限りコメント 300 件超のスプリント Issue が status:in-progress
# のまま残る間ずっとゲートが恒久的に判定不能（exit 2）になる恐れがあった）。GitHub の issue
# comments には「最新だけ取得」の並び替えパラメータが無いため、実運用で遭遇しうる規模
# （1000 件）までは走査して取りこぼしを減らし、それでも超える場合だけ fail-closed でエラーに
# する（無制限に走査すると 1 Issue あたりの API 呼び出し数に上限が無くなるため）。
MAX_COMMENT_PAGES = 10  # 100 件 x 10 ページ = 最大 1000 件

# `fetch_in_progress_sprint_candidates` の REST フォールバックが走査するページ数の上限
# （レビュー指摘 WARNING 4）。実運用で同時に `status:in-progress` の Issue が 300 件を超える
# ことは通常運用の破綻シグナルであり、`MAX_COMMENT_PAGES` ほど緩める必要はないと判断し
# 300 件のまま維持する（用途が違うため定数名は分ける）。
MAX_IN_PROGRESS_ISSUE_PAGES = 3  # 100 件 x 3 ページ = 最大 300 件


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


def _fetch_paginated(url_template: str, token: str, max_pages: int) -> tuple[list, str | None]:
    """`url_template.format(page=N)` を `max_pages` ページまで REST 取得し、各ページの
    list を結合して返す（レビュー指摘 WARNING 4: `fetch_in_progress_sprint_candidates` と
    `fetch_issue_comments` で個別に実装していたページング打ち切り検知を共通化する）。

    Returns (items, error_reason)。次のいずれかで `error_reason` が非 None になる
    （fail-closed。「取得失敗／打ち切り」と「0 件」を混同しない）:
      - いずれかのページで REST 呼び出し自体が失敗した
      - いずれかのページの応答が JSON としてパースできない
      - いずれかのページの応答が list ではない（`{}` / `null` / 文字列等）
      - 最終ページ（`max_pages` ページ目）まで各ページが満杯（100 件）のまま終わった
        （＝続きがある可能性を排除できない・打ち切り疑い）
    """
    items: list = []
    last_batch_len = 0
    broke_early = False
    for page in range(1, max_pages + 1):
        ok, out = _http_get(url_template.format(page=page), token)
        if not ok:
            return [], f"REST も失敗（{out}）"
        try:
            batch = json.loads(out)
        except json.JSONDecodeError:
            return [], "REST 応答のパースに失敗"
        if not isinstance(batch, list):
            return [], f"REST 応答が配列ではありません（{type(batch).__name__}）"
        if not batch:
            broke_early = True
            break
        items.extend(batch)
        last_batch_len = len(batch)
        if len(batch) < 100:
            broke_early = True
            break
    if not broke_early and last_batch_len == 100:
        return [], (
            f"件数がページング上限（{max_pages * 100} 件）に到達した可能性があります"
            f"（取得済み {len(items)} 件・最終ページも満杯で終了）。"
            "判定不能として扱います（取りこぼしを避けるため）"
        )
    return items, None


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
            # レビュー指摘 CRITICAL 2: `issues` が list 以外（`{}` や `""` 等）だと、
            # 直後の内包表記が 0 回反復して例外を送出せず `([], None)` を返してしまう
            # （gh が exit 0 で想定外スキーマを返した場合に「0 件」へ fail-open する）。
            # 明示的に isinstance で弾き、下の except 節で REST フォールバックへ倒す。
            if not isinstance(issues, list):
                raise TypeError("gh issue list の応答が配列ではありません")
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

    # 【レビュー指摘 WARNING 4】gh 経路の `--limit 100` については打ち切り検知を実装しない。
    # gh の JSON 出力には総件数・次ページトークンが含まれないため超過を判別する手段が無く、
    # 実装するなら REST 経路と同様に追加のページング呼び出しが要る。gh 経路は `gh` CLI 自体が
    # 正常に動作している健全な経路であり、そこで in-progress Issue が 100 件ちょうどに達する
    # 事態は Issue 運用そのものが破綻しているシグナルと判断し、本関数のスコープ外として
    # 対象外にする（黙って見送るのではなく理由を明記。必要になれば別 Issue で対応する）。
    #
    # REST フォールバック側は打ち切り検知込みの共通ヘルパー `_fetch_paginated` を使う
    # （レビュー指摘 WARNING 4: 従来は `fetch_issue_comments` にしかこの検知が無く、REST
    # フォールバック時に 301 件目以降が無警告で捨てられる fail-open が残っていた）。
    # 入力境界表（MAX_IN_PROGRESS_ISSUE_PAGES=3 前提。ロジックは fetch_issue_comments の
    # 境界表と同型で、対象が Issue コメントではなく in-progress Issue 自体である点のみ異なる）:
    #   件数 0           → page1 が空 batch → 早期 break・エラーなし（[] を返す）
    #   件数 1〜99       → page1 が満杯未満 → 早期 break・エラーなし
    #   件数 100         → page1 満杯 → page2 が空 → 早期 break・エラーなし（100件）
    #   件数 101〜299    → 最終ページが満杯未満 → 早期 break・エラーなし
    #   件数 300         → 3 ページ目も満杯（100）のままループ終了 → 打ち切り疑い → エラー
    #   件数 301 以上    → 同上・エラー
    label_q = urllib.parse.quote("status:in-progress", safe="")
    url_template = (
        f"https://api.github.com/repos/{REPO}/issues"
        f"?state=open&labels={label_q}&per_page=100&page={{page}}"
    )
    batch_items, perr = _fetch_paginated(url_template, token, MAX_IN_PROGRESS_ISSUE_PAGES)
    if perr is not None:
        return [], f"gh 失敗（{gh_err}）・REST 側で失敗（{perr}）"
    # /issues エンドポイントは PR も含むため pull_request キーで除外する
    issues = [
        {"number": i["number"], "title": i.get("title", ""), "body": i.get("body") or ""}
        for i in batch_items
        if isinstance(i, dict) and "pull_request" not in i
    ]
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
            # レビュー指摘 CRITICAL 2: `data` が dict 以外（list/文字列/null 等）だと
            # `.get` が無く AttributeError で既に捕捉されていたが、明示的な isinstance で
            # 意図を明確にする（fetch_in_progress_sprint_candidates 側と対にする）。
            if not isinstance(data, dict):
                raise TypeError("gh issue view の応答がオブジェクトではありません")
            return [
                {
                    "body": c.get("body", ""),
                    "created_at": c.get("createdAt", ""),
                    "author_association": c.get("authorAssociation", ""),
                }
                for c in data.get("comments", [])
            ], None
        except (json.JSONDecodeError, AttributeError, TypeError):
            ok = False
            out = "gh の JSON 応答が不正"
    gh_err = out

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return [], f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"

    # 【#237】GitHub の issue comments は古い順に返る。長大スレッドで `MAX_COMMENT_PAGES x 100`
    # 件を超えると、最新の Sprint Review 判定コメントが打ち切りの外側に落ち、latest_verdict が
    # 「判定コメントが無い」と誤読して待機（exit 1）に倒れうる。最終ページが「まだ続きがある」
    # ことを示す満杯（100 件）で終わったときは、「0 件」や「全件取得できた」と区別できないため、
    # fail-closed としてエラーを返し呼び出し側で判定不能（exit 2）へ倒す。
    # 境界（入力境界表・MAX_COMMENT_PAGES=10 前提）:
    #   件数 0           → page1 が空 batch → 早期 break・エラーなし（[] を返す）
    #   件数 1〜99       → page1 が満杯未満 → 早期 break・エラーなし
    #   件数 100         → page1 満杯 → page2 取得、page2 が空 → 早期 break・エラーなし（100件）
    #   件数 101〜999    → 最終ページが満杯未満 → 早期 break・エラーなし
    #   件数 1000        → 10 ページ目も満杯（100）のままループ終了 → 打ち切り疑い → エラー
    #                       （実際には 1000 件ちょうどの可能性もあるが、REST 応答だけでは
    #                       「ちょうど 1000 件」と「1001 件以上」を区別できないため安全側で
    #                       エラー扱い）
    #   件数 1001 以上   → 同上・エラー
    # REST 応答が list 以外（`{}` / `null` / 文字列等）のときは「0 件」と誤読せず即エラーにする
    # （レビュー指摘 CONFIRMED 2: `if not batch:` の truthy 判定は `{}`/`None` も真になり
    # 「取得失敗」と「0 件」を区別できていなかった）。打ち切り検知は共通ヘルパー
    # `_fetch_paginated`（レビュー指摘 WARNING 4）に委譲する。
    url_template = (
        f"https://api.github.com/repos/{REPO}/issues/{number}/comments"
        f"?per_page=100&page={{page}}"
    )
    raw_items, perr = _fetch_paginated(url_template, token, MAX_COMMENT_PAGES)
    if perr is not None:
        return [], f"gh 失敗（{gh_err}）・REST 側で失敗（{perr}）"
    comments = [
        {
            "body": c.get("body", ""),
            "created_at": c.get("created_at", ""),
            "author_association": c.get("author_association", ""),
        }
        for c in raw_items
        if isinstance(c, dict)
    ]
    return comments, None


# ──────────────────────────────────────────────
# main 反映判定（#471）: Issue → PR 対応付け + merge_commit_sha の祖先判定
# ──────────────────────────────────────────────


def _sprint_id_token_in_title(title: str, sprint_id: str) -> bool:
    """`title` が `sprint_id`（例 "SP-1"）を独立したトークンとして含むかどうか。

    `sprint_id in title` の単純部分一致だと "SP-1" が "SP-10" の前方一致で誤ってマッチする
    （検索 API 側の `in:title` クエリは実データ検証上そう化けないことを確認済みだが、検索
    エンジンの挙動に依存しない defense-in-depth として呼び出し側で再確認する・#723 指摘3 NIT）。
    """
    return re.search(rf"{re.escape(sprint_id)}(?!\d)", title) is not None


def fetch_merged_pr_commit_shas(sprint_id: str) -> tuple[list[str], str | None]:
    """`sprint_id`（例 "SP-3"）をタイトルに含む merged PR の merge commit SHA 一覧を返す。

    Returns (shas, error_reason)。取得失敗時は shas=[] で error_reason に理由を入れる
    （「取得失敗」を「該当 PR 0 件（未マージ）」と混同しない・fail-closed の前提）。
    """
    query = f'"{sprint_id}" in:title'
    ok, out = _run_gh([
        "pr", "list", "-R", REPO, "--search", query, "--state", "merged",
        "--json", "number,mergeCommit,title", "--limit", "50",
    ])
    if ok:
        try:
            data = json.loads(out)
            if not isinstance(data, list):
                raise TypeError("gh pr list の応答が配列ではありません")
            shas = [
                d["mergeCommit"]["oid"]
                for d in data
                if isinstance(d, dict)
                and isinstance(d.get("mergeCommit"), dict)
                and d["mergeCommit"].get("oid")
                and _sprint_id_token_in_title(d.get("title") or "", sprint_id)
            ]
            return shas, None
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            ok = False
            out = "gh の JSON 応答が不正"
    gh_err = out

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return [], f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"

    # REST search で merged PR 番号を集め、各 PR の merge_commit_sha を個別取得する
    # （検索結果には merge_commit_sha が含まれないため）。
    search_q = urllib.parse.quote(f'repo:{REPO} is:pr is:merged {query}')
    ok2, out2 = _http_get(f"https://api.github.com/search/issues?q={search_q}&per_page=50", token)
    if not ok2:
        return [], f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
    try:
        data2 = json.loads(out2)
        if not isinstance(data2, dict):
            raise TypeError("search/issues の応答がオブジェクトではありません")
        numbers = [
            item["number"]
            for item in data2.get("items", [])
            if isinstance(item, dict)
            and "pull_request" in item
            and _sprint_id_token_in_title(item.get("title") or "", sprint_id)
        ]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return [], f"gh 失敗（{gh_err}）・REST 応答のパースに失敗"

    shas: list[str] = []
    for number in numbers:
        okp, outp = _http_get(f"https://api.github.com/repos/{REPO}/pulls/{number}", token)
        if not okp:
            return [], f"gh 失敗（{gh_err}）・PR #{number} の詳細取得に失敗（{outp}）"
        try:
            pr = json.loads(outp)
            if not isinstance(pr, dict):
                raise TypeError("PR 詳細の応答がオブジェクトではありません")
        except (json.JSONDecodeError, TypeError):
            return [], f"gh 失敗（{gh_err}）・PR #{number} 応答のパースに失敗"
        sha = pr.get("merge_commit_sha")
        if sha:
            shas.append(sha)
    return shas, None


def fetch_open_pr_numbers(sprint_id: str) -> tuple[list[int], str | None]:
    """`sprint_id`（例 "SP-3"）をタイトルに含む **open** PR 番号一覧を返す（#723 指摘1）。

    `fetch_merged_pr_commit_shas` が merged 0 件を返したとき、「本当に未マージ」なのか
    「`SP-n` トークンがタイトルに無く検索でヒットしなかっただけ」なのかを区別するために使う。
    Returns (numbers, error_reason)。取得失敗時は numbers=[] で error_reason に理由を入れる。
    """
    query = f'"{sprint_id}" in:title'
    ok, out = _run_gh([
        "pr", "list", "-R", REPO, "--search", query, "--state", "open",
        "--json", "number,title", "--limit", "50",
    ])
    if ok:
        try:
            data = json.loads(out)
            if not isinstance(data, list):
                raise TypeError("gh pr list の応答が配列ではありません")
            numbers = [
                d["number"]
                for d in data
                if isinstance(d, dict) and _sprint_id_token_in_title(d.get("title") or "", sprint_id)
            ]
            return numbers, None
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            ok = False
            out = "gh の JSON 応答が不正"
    gh_err = out

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return [], f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"

    search_q = urllib.parse.quote(f'repo:{REPO} is:pr is:open {query}')
    ok2, out2 = _http_get(f"https://api.github.com/search/issues?q={search_q}&per_page=50", token)
    if not ok2:
        return [], f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
    try:
        data2 = json.loads(out2)
        if not isinstance(data2, dict):
            raise TypeError("search/issues の応答がオブジェクトではありません")
        numbers = [
            item["number"]
            for item in data2.get("items", [])
            if isinstance(item, dict)
            and "pull_request" in item
            and _sprint_id_token_in_title(item.get("title") or "", sprint_id)
        ]
        return numbers, None
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return [], f"gh 失敗（{gh_err}）・REST 応答のパースに失敗"


# `origin/main` の fetch はプロセス内で最大 1 回だけ実行する（#723 指摘2）。
# `is_merged_into_main` は候補 Issue 1 件につき最大 50 件の merge commit SHA をループして
# `is_ancestor_of_main` を呼ぶため、メモ化しないと fetch が「候補 Issue 数 × SHA 数」だけ
# 重複発行され、そのどれか 1 回が失敗するだけで fail-closed 側に倒れる確率が上がる
# （#471 が減らそうとした「並行度が上がるほどデプロイ窓が閉じる」問題を別経路で再導入する）。
_main_fetch_done = False


def reset_main_fetch_cache() -> None:
    """テスト用: `_main_fetch_done` メモ化フラグをリセットする（self-test 間の相互汚染防止）。"""
    global _main_fetch_done
    _main_fetch_done = False


def ensure_main_fetched() -> bool:
    """`origin/main` を明示 refspec で fetch する（`session-safety-rules.md` G-1 と同じパターン。
    ローカルの参照が古いままだと未反映を誤って「祖先」と判定しうる）。

    プロセス内で成功が確認できたら以降は再実行しない（メモ化）。失敗時はメモ化せず、
    次回呼び出しで再試行できるようにする。Returns: fetch が成功した（または成功済み）か。
    """
    global _main_fetch_done
    if _main_fetch_done:
        return True
    try:
        fetch = subprocess.run(
            ["git", "fetch", "origin", "+main:refs/remotes/origin/main"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if fetch.returncode != 0:
        return False
    _main_fetch_done = True
    return True


def is_ancestor_of_main(sha: str) -> bool | None:
    """`sha` が `origin/main` の祖先かどうかを git で判定する（判定不能なら None）。

    fetch 自体は `ensure_main_fetched()`（プロセス内メモ化）に委譲し、ここでは
    ローカル参照に対する `merge-base --is-ancestor` の判定のみを行う（#723 指摘2）。
    """
    if not ensure_main_fetched():
        return None
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    # 128 等（無効な SHA・リポジトリ状態異常）は判定不能として fail-closed 側へ倒す
    return None


def is_merged_into_main(
    issue_title: str,
    fetch_fn=fetch_merged_pr_commit_shas,
    ancestor_fn=is_ancestor_of_main,
    open_pr_fn=fetch_open_pr_numbers,
) -> bool | None:
    """Issue タイトルから対応するスプリント PR を探し、main へ反映済みかを判定する。

    Returns:
        True  = 反映済み（merge commit が origin/main の祖先）
        False = 未反映と確定できた（merged PR の全てが祖先でない、または merged PR は
                無いが同じトークンの open PR が実在すると確認できた）
        None  = 判定不能（SP-n がタイトルに無い・PR 検索/取得の失敗・git 判定の失敗・
                merged/open のどちらの PR も見つからない）。
                fail-closed のため呼び出し側は None を「反映済み」と同様に扱うこと。

    `fetch_fn` / `ancestor_fn` / `open_pr_fn` はテスト用の差し替えポイント（既定は実際の
    gh/git 呼び出し）。

    【指摘1（#723・CRITICAL）で修正した見逃し経路】
    merged PR が 0 件のとき、旧実装は無条件で `False`（未マージ確定＝ゲートを塞がない）を
    返していた。これは次の 2 状況を区別できていなかった:
      (a) 本当に PR がまだ存在しない・まだ merge されていない（塞がなくてよい）
      (b) PR は存在し main へ merge 済みだが、**PR タイトルに `SP-n` トークンが無く**
          `fetch_merged_pr_commit_shas` の検索でヒットしなかった（本来は塞ぐべき）
    (b) を (a) と誤判定すると、main 上に rejected / 未レビューのコードが乗っているのに
    デプロイが許可されるサイレント fail-open になる。
    修正: merged PR が 0 件のときは追加で **同じトークンの open PR** を検索する。
      - open PR が見つかれば「(a) 本当に未マージ」と確定できる → False
      - open も merged も 0 件、または open PR 検索自体が失敗した場合は、(a)/(b) を
        区別できないため **判定不能 → None（fail-closed）** とし、無条件 False には戻さない
    """
    m = SPRINT_ID_RE.search(issue_title)
    if not m:
        return None
    sprint_id = m.group(0)
    shas, err = fetch_fn(sprint_id)
    if err is not None:
        return None
    if not shas:
        open_numbers, open_err = open_pr_fn(sprint_id)
        if open_err is not None:
            # open PR 検索自体が失敗 → (a)/(b) を区別できない → 判定不能（fail-closed）
            return None
        if open_numbers:
            # 同じトークンの open PR が実在する → 本当に未マージと確定できる
            return False
        # merged も open も 0 件 → 検索自体が SP-n トークン不一致等で機能していない
        # 可能性を排除できない → 判定不能（fail-closed。旧実装はここで無条件 False だった）
        return None
    saw_unknown = False
    for sha in shas:
        result = ancestor_fn(sha)
        if result is True:
            return True
        if result is None:
            saw_unknown = True
    if saw_unknown:
        return None
    return False


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


def evaluate_issue(issue: dict, comments: list[dict], merged_check=None) -> dict | None:
    """Issue 1 件を評価する。ゲートを塞ぐなら理由付き dict、塞がないなら None を返す。

    `merged_check`（省略時は `is_merged_into_main`）: 塞ぐ候補（判定未実施 / rejected）と
    なった Issue についてのみ呼び出し、`False`（未反映と確定）が返れば塞がない（#471）。
    `True` / `None`（反映済み・判定不能）は従来どおり塞ぐ（fail-closed）。
    """
    if merged_check is None:
        merged_check = is_merged_into_main
    if not is_sprint_issue(issue["title"], issue.get("body", ""), comments):
        return None
    verdict = latest_verdict(comments)
    if verdict is None:
        reason = REASON_NO_VERDICT
    elif verdict == "rejected":
        reason = REASON_REJECTED
    else:
        # accepted / accepted_with_conditions はゲートを塞がない（#471 改訂後も不変）
        return None

    merged = merged_check(issue["title"])
    if merged is False:
        # main にまだ反映されていない = 本番の中身に影響しないため塞がない（#471）
        return None
    # merged is True（反映済み）または None（判定不能）→ fail-closed で塞ぐ
    return {"number": issue["number"], "title": issue["title"], "reason": reason}


def decide(issues_with_comments: list[tuple[dict, list[dict]]], merged_check=None) -> dict:
    """全 Issue を集約してゲート判定を返す。

    Returns:
        {"can_deploy": bool, "blocking_issues": [{"number", "title", "reason"}, ...]}
    """
    blocking = []
    for issue, comments in issues_with_comments:
        r = evaluate_issue(issue, comments, merged_check=merged_check)
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
    """merged_check=(常に True) を明示注入し、#471 以前の挙動（main 反映済み前提）を保つ。
    #471 の main 反映判定そのものは `_self_test_merged_check_integration` /
    `_self_test_is_merged_into_main` が別途検証する。
    """
    failures = []
    always_merged = lambda title: True  # noqa: E731

    # 判定コメントが無いスプリント Issue → ゲートを塞ぐ（レビュー未実施）
    r = evaluate_issue(_issue(1, "SP-1: 検索"), [], merged_check=always_merged)
    if r is None or r["reason"] != REASON_NO_VERDICT:
        failures.append(f"evaluate_issue: 判定未実施は塞ぐことを期待したが {r}")

    # rejected → ゲートを塞ぐ
    r = evaluate_issue(_issue(2, "SP-2: 詳細"), [_verdict_comment("rejected")], merged_check=always_merged)
    if r is None or r["reason"] != REASON_REJECTED:
        failures.append(f"evaluate_issue: rejected は塞ぐことを期待したが {r}")

    # accepted → 塞がない（merged_check は呼ばれる必要すらない）
    r = evaluate_issue(_issue(3, "SP-3: 一覧"), [_verdict_comment("accepted")], merged_check=always_merged)
    if r is not None:
        failures.append(f"evaluate_issue: accepted は塞がないことを期待したが {r}")

    # accepted_with_conditions → 塞がない
    r = evaluate_issue(
        _issue(4, "SP-4: 通知"), [_verdict_comment("accepted_with_conditions")], merged_check=always_merged
    )
    if r is not None:
        failures.append(f"evaluate_issue: accepted_with_conditions は塞がないことを期待したが {r}")

    # 非スプリント Issue はコメント内容に関係なく塞がない（in-progress の bug 修正等）
    r = evaluate_issue(_issue(5, "fix: ログイン画面のバグ"), [_verdict_comment("rejected")], merged_check=always_merged)
    if r is not None:
        failures.append(f"evaluate_issue: 非スプリント Issue は塞がないことを期待したが {r}")

    return failures


def _self_test_merged_check_integration() -> list[str]:
    """#471: main 反映判定の統合（evaluate_issue が merged_check の結果をどう使うか）。"""
    failures = []

    # 判定未実施だが、main に未反映と確定できる（merged_check=False）→ 塞がない
    r = evaluate_issue(_issue(1, "SP-1: 検索"), [], merged_check=lambda t: False)
    if r is not None:
        failures.append(f"evaluate_issue: 未マージの判定未実施 Issue は塞がないことを期待したが {r}")

    # rejected だが main に未反映と確定できる（merged_check=False）→ 塞がない
    r = evaluate_issue(_issue(2, "SP-2: 詳細"), [_verdict_comment("rejected")], merged_check=lambda t: False)
    if r is not None:
        failures.append(f"evaluate_issue: 未マージの rejected Issue は塞がないことを期待したが {r}")

    # 判定未実施 + main に反映済み（merged_check=True）→ 引き続き塞ぐ
    r = evaluate_issue(_issue(3, "SP-3: 一覧"), [], merged_check=lambda t: True)
    if r is None or r["reason"] != REASON_NO_VERDICT:
        failures.append(f"evaluate_issue: 反映済み + 判定未実施は塞ぐことを期待したが {r}")

    # rejected + main 反映判定が不能（merged_check=None）→ fail-closed で塞ぐ
    r = evaluate_issue(_issue(4, "SP-4: 通知"), [_verdict_comment("rejected")], merged_check=lambda t: None)
    if r is None or r["reason"] != REASON_REJECTED:
        failures.append(f"evaluate_issue: main 反映判定不能の rejected は塞ぐ（fail-closed）ことを期待したが {r}")

    # 判定未実施 + main 反映判定が不能（merged_check=None）→ fail-closed で塞ぐ
    r = evaluate_issue(_issue(5, "SP-5: 一覧2"), [], merged_check=lambda t: None)
    if r is None or r["reason"] != REASON_NO_VERDICT:
        failures.append(f"evaluate_issue: main 反映判定不能の判定未実施は塞ぐ（fail-closed）ことを期待したが {r}")

    # accepted は merged_check の値に関係なく塞がない（True/False/None いずれでも）
    for mc in (lambda t: True, lambda t: False, lambda t: None):
        r = evaluate_issue(_issue(6, "SP-6: 承認済み"), [_verdict_comment("accepted")], merged_check=mc)
        if r is not None:
            failures.append(f"evaluate_issue: accepted は merged_check に関係なく塞がないことを期待したが {r}")

    return failures


def _self_test_is_merged_into_main() -> list[str]:
    """#471 / #723: is_merged_into_main の純ロジック（fetch_fn / ancestor_fn / open_pr_fn を注入）。

    入力バリアント: ① タイトルに SP-n が無い ②a merged/open とも 0 件（判定不能・#723 指摘1 の核心）
    ②b merged 0 件だが open PR が実在（未マージ確定） ②c merged 0 件・open 検索自体が失敗（判定不能）
    ③ 複数 PR が紐付き 1 件が main の祖先 ④ merged だが main に無い（squash 後の SHA 差異等）
    ⑥ merged 検索 API が失敗 ⑦ git 祖先判定が失敗（判定不能）
    """
    failures = []

    def make(shas=None, err=None, ancestor_results=None, open_numbers=None, open_err=None):
        shas = shas if shas is not None else []
        ancestor_results = ancestor_results or {}
        open_numbers = open_numbers if open_numbers is not None else []

        def fetch_fn(sprint_id):
            return shas, err

        def ancestor_fn(sha):
            return ancestor_results.get(sha, False)

        def open_pr_fn(sprint_id):
            return open_numbers, open_err

        return fetch_fn, ancestor_fn, open_pr_fn

    # ① タイトルに SP-n が無い（Sprint Planning コメントのみでスプリント判定された Issue）
    #    → 対応する PR を機械的に特定できない → 判定不能（None・fail-closed）
    fetch_fn, ancestor_fn, open_pr_fn = make()
    r = is_merged_into_main("改善: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn, open_pr_fn=open_pr_fn)
    if r is not None:
        failures.append(f"is_merged_into_main: SP-n の無いタイトルは None（判定不能）を期待したが {r}")

    # ②a merged PR 0 件・open PR も 0 件（open 検索自体は成功）→ 判定不能（None・fail-closed）
    #    #723 指摘1 CRITICAL: 旧実装はここで無条件 False（未マージ確定）を返しており、
    #    「PR は merge 済みだがタイトルに SP-n トークンが無く検索でヒットしない」ケースを
    #    見逃す fail-open だった。これがその再発防止テスト。
    fetch_fn, ancestor_fn, open_pr_fn = make(shas=[], open_numbers=[])
    r = is_merged_into_main("SP-7: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn, open_pr_fn=open_pr_fn)
    if r is not None:
        failures.append(
            f"is_merged_into_main: merged/open とも 0 件は None（判定不能・fail-closed）"
            f"を期待したが {r}（#723 指摘1 の再発防止ケース）"
        )

    # ②b merged PR 0 件だが、同じトークンの open PR が実在する → 未マージと確定できる（False）
    fetch_fn, ancestor_fn, open_pr_fn = make(shas=[], open_numbers=[99])
    r = is_merged_into_main("SP-7: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn, open_pr_fn=open_pr_fn)
    if r is not False:
        failures.append(f"is_merged_into_main: merged0件+open PR実在 は False を期待したが {r}")

    # ②c merged PR 0 件・open PR 検索自体が失敗 → 判定不能（None・fail-closed）
    fetch_fn, ancestor_fn, open_pr_fn = make(shas=[], open_err="REST も失敗")
    r = is_merged_into_main("SP-7: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn, open_pr_fn=open_pr_fn)
    if r is not None:
        failures.append(f"is_merged_into_main: open PR 検索失敗は None（判定不能）を期待したが {r}")

    # ③ 複数 PR が紐付き、うち 1 件の merge commit が main の祖先 → True
    fetch_fn, ancestor_fn, open_pr_fn = make(
        shas=["aaa", "bbb"], ancestor_results={"aaa": False, "bbb": True}
    )
    r = is_merged_into_main("SP-8: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn, open_pr_fn=open_pr_fn)
    if r is not True:
        failures.append(f"is_merged_into_main: 複数 PR の 1 件が祖先なら True を期待したが {r}")

    # ④ merged PR はあるが、その merge commit が main の祖先ではない
    #    （squash 後に revert された・SHA が一致しない等）→ 未マージ扱い（False）
    fetch_fn, ancestor_fn, open_pr_fn = make(shas=["ccc"], ancestor_results={"ccc": False})
    r = is_merged_into_main("SP-9: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn, open_pr_fn=open_pr_fn)
    if r is not False:
        failures.append(f"is_merged_into_main: merged だが祖先でない場合は False を期待したが {r}")

    # ⑥ merged PR 検索 API が失敗（err が返る）→ 判定不能（None・fail-closed）。
    #    open_pr_fn は呼ばれるべきではない（err の時点で早期リターンする実装を確認する）
    open_pr_fn_called = {"yes": False}

    def open_pr_fn_should_not_be_called(sprint_id):
        open_pr_fn_called["yes"] = True
        return [], None

    fetch_fn, ancestor_fn = make(shas=[], err="REST 応答のパースに失敗")[:2]
    r = is_merged_into_main(
        "SP-10: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn,
        open_pr_fn=open_pr_fn_should_not_be_called,
    )
    if r is not None:
        failures.append(f"is_merged_into_main: fetch 失敗は None（判定不能）を期待したが {r}")
    if open_pr_fn_called["yes"]:
        failures.append("is_merged_into_main: merged 検索が err の時点で open_pr_fn が呼ばれた（早期リターンできていない）")

    # ⑦ git 祖先判定が失敗（fetch 失敗・無効な SHA 等で ancestor_fn が None を返す）
    #    → 判定不能（None・fail-closed）。他の PR が明確に False でも None を優先する
    fetch_fn, ancestor_fn, open_pr_fn = make(
        shas=["ddd", "eee"], ancestor_results={"ddd": False, "eee": None}
    )
    r = is_merged_into_main("SP-11: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn, open_pr_fn=open_pr_fn)
    if r is not None:
        failures.append(f"is_merged_into_main: git 判定不能を含む場合は None を期待したが {r}")

    return failures


def _self_test_is_ancestor_of_main() -> list[str]:
    """is_ancestor_of_main / ensure_main_fetched を実際に呼び出し、`subprocess.run` を
    モック差し替えして returncode 0/1/その他（128 等）→ True/False/None の写像、
    **fetch のメモ化**（#723 指摘2: 候補 Issue 数 × SHA 数だけ fetch が重複発行される問題の
    修正）、**fetch 呼び出し引数の完全一致**（#723 指摘4 NIT: refspec の `+` と merge-base の
    引数順が壊れても緑のまま通ってしまう欠陥の修正）をエントリポイントから実測する
    （#474「テストの到達範囲」: 上のロジック再実装ではなく実関数を通す）。
    """
    failures = []
    import subprocess as _subprocess_module
    import types

    real_run = _subprocess_module.run

    def fake_run_factory(fetch_returncode: int, merge_base_returncode: int, call_log: list):
        def fake_run(args, **kwargs):
            call_log.append(list(args))
            if args[:2] == ["git", "fetch"]:
                return types.SimpleNamespace(returncode=fetch_returncode, stdout="", stderr="")
            if args[:2] == ["git", "merge-base"]:
                return types.SimpleNamespace(returncode=merge_base_returncode, stdout="", stderr="")
            return types.SimpleNamespace(returncode=127, stdout="", stderr="想定外呼び出し")
        return fake_run

    cases = [
        (0, 0, True),    # fetch 成功・祖先である
        (0, 1, False),   # fetch 成功・祖先でない
        (0, 128, None),  # fetch 成功・merge-base が異常終了（無効な SHA 等）→ 判定不能
        (1, 0, None),    # fetch 自体が失敗 → 判定不能（merge-base を呼ぶ前に打ち切る）
    ]
    try:
        for fetch_rc, merge_base_rc, expected in cases:
            reset_main_fetch_cache()
            call_log: list = []
            _subprocess_module.run = fake_run_factory(fetch_rc, merge_base_rc, call_log)
            got = is_ancestor_of_main("deadbeef")
            if got != expected:
                failures.append(
                    f"is_ancestor_of_main(fetch_rc={fetch_rc}, merge_base_rc={merge_base_rc}): "
                    f"{expected!r} を期待したが {got!r}"
                )

        # #723 指摘4（NIT）: git fetch の refspec（`+` 込み）と merge-base の引数順を
        # 完全一致で検証する（`args[:2]` だけの検査では refspec の `+` が消えても素通りする）
        reset_main_fetch_cache()
        call_log = []
        _subprocess_module.run = fake_run_factory(0, 0, call_log)
        is_ancestor_of_main("deadbeefcafe")
        if call_log[:1] != [["git", "fetch", "origin", "+main:refs/remotes/origin/main"]]:
            failures.append(f"is_ancestor_of_main: git fetch の呼び出し引数が不正: {call_log[:1]}")
        if len(call_log) < 2 or call_log[1] != [
            "git", "merge-base", "--is-ancestor", "deadbeefcafe", "origin/main"
        ]:
            failures.append(f"is_ancestor_of_main: git merge-base の呼び出し引数が不正: {call_log[1:2]}")

        # #723 指摘2: fetch が一度成功したら、同一プロセス内の 2 回目以降は再実行しない
        # （merge-base だけが呼ばれる）ことを実測する
        reset_main_fetch_cache()
        call_log = []
        _subprocess_module.run = fake_run_factory(0, 0, call_log)
        is_ancestor_of_main("sha1")
        is_ancestor_of_main("sha2")
        is_ancestor_of_main("sha3")
        fetch_calls = [c for c in call_log if c[:2] == ["git", "fetch"]]
        merge_base_calls = [c for c in call_log if c[:2] == ["git", "merge-base"]]
        if len(fetch_calls) != 1:
            failures.append(
                f"fetch メモ化: git fetch が 3 回呼び出し中 {len(fetch_calls)} 回実行された（期待 1 回）"
            )
        if len(merge_base_calls) != 3:
            failures.append(
                f"fetch メモ化: merge-base が 3 回呼び出し中 {len(merge_base_calls)} 回実行された（期待 3 回）"
            )

        # fetch 失敗時はメモ化されない（次回呼び出しで再試行できる）ことを確認する
        reset_main_fetch_cache()
        call_log = []
        _subprocess_module.run = fake_run_factory(1, 0, call_log)  # 1回目: fetch 失敗
        r1 = is_ancestor_of_main("sha4")
        _subprocess_module.run = fake_run_factory(0, 0, call_log)  # 2回目: fetch 成功
        r2 = is_ancestor_of_main("sha5")
        if r1 is not None:
            failures.append(f"fetch 失敗時の再試行: 1 回目の戻り値が None でない（{r1!r}）")
        if r2 is not True:
            failures.append(f"fetch 失敗時の再試行: 2 回目（再試行成功）の戻り値が True でない（{r2!r}）")
        fetch_calls = [c for c in call_log if c[:2] == ["git", "fetch"]]
        if len(fetch_calls) != 2:
            failures.append(
                f"fetch 失敗時の再試行: fetch 呼び出しが {len(fetch_calls)} 回（期待 2 回。"
                "失敗時はメモ化されず再試行できるべき）"
            )
    finally:
        _subprocess_module.run = real_run
        reset_main_fetch_cache()

    return failures


def _self_test_fetch_merged_pr_commit_shas() -> list[str]:
    """#723 指摘3: fetch_merged_pr_commit_shas を gh→REST の 3 段フォールバック込みで
    エントリポイントから実測する（`_run_gh` / `_http_get` をモック差し替え）。

    入力バリアント: ① gh 成功 ② gh 失敗 + token 無し ③ gh 失敗 + REST 検索失敗
    ④ gh 失敗 + REST 検索成功だが個別 PR 取得失敗 ⑤ gh 失敗 + REST 全経路成功
    ⑥ gh が想定外形状（配列でなく辞書）を返す（AttributeError 耐性・#723 指摘3 本体）。
    ①⑤ では "SP-1"/"SP-10" のような前方一致ノイズの除外（#723 指摘3 NIT）も確認する。
    """
    failures = []
    orig_run_gh = _run_gh
    orig_http_get = _http_get
    orig_gh_token = os.environ.get("GH_TOKEN")
    orig_github_token = os.environ.get("GITHUB_TOKEN")

    def clear_tokens():
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)

    try:
        # ① gh 成功 → gh の結果をそのまま使う（前方一致ノイズ SP-10 は除外される）
        globals()["_run_gh"] = lambda args: (True, json.dumps([
            {"number": 1, "title": "feat(SP-1): 何か", "mergeCommit": {"oid": "aaa111"}},
            {"number": 2, "title": "feat(SP-10): 別件", "mergeCommit": {"oid": "bbb222"}},
        ]))
        shas, err = fetch_merged_pr_commit_shas("SP-1")
        if err is not None or shas != ["aaa111"]:
            failures.append(f"① gh 成功: {(shas, err)!r}（期待 (['aaa111'], None)。SP-10 混入除外を確認）")

        # ② gh 失敗 + token 無し → エラー
        globals()["_run_gh"] = lambda args: (False, "認証エラー")
        clear_tokens()
        shas, err = fetch_merged_pr_commit_shas("SP-2")
        if err is None:
            failures.append(f"② gh失敗+token無し: エラーを期待したが {(shas, err)!r}")

        os.environ["GH_TOKEN"] = "dummy-token-for-selftest"

        # ③ gh 失敗 + REST 検索失敗 → エラー
        globals()["_http_get"] = lambda url, token: (False, "HTTP 502")
        shas, err = fetch_merged_pr_commit_shas("SP-3")
        if err is None:
            failures.append(f"③ REST検索失敗: エラーを期待したが {(shas, err)!r}")

        # ④ gh 失敗 + REST 検索成功、個別 PR 取得失敗 → エラー
        def http_g4(url, token):
            if "search/issues" in url:
                return True, json.dumps({"items": [
                    {"number": 42, "title": "SP-4: 何か", "pull_request": {}},
                ]})
            return False, "HTTP 404"

        globals()["_http_get"] = http_g4
        shas, err = fetch_merged_pr_commit_shas("SP-4")
        if err is None:
            failures.append(f"④ 個別PR取得失敗: エラーを期待したが {(shas, err)!r}")

        # ⑤ gh 失敗 + REST 検索・個別取得とも成功（前方一致ノイズ SP-50 の除外も確認）
        def http_g5(url, token):
            if "search/issues" in url:
                return True, json.dumps({"items": [
                    {"number": 55, "title": "feat(SP-5): 何か", "pull_request": {}},
                    {"number": 56, "title": "feat(SP-50): 別件", "pull_request": {}},
                ]})
            if url.endswith("/pulls/55"):
                return True, json.dumps({"merge_commit_sha": "ccc333"})
            if url.endswith("/pulls/56"):
                return True, json.dumps({"merge_commit_sha": "ddd444"})
            return False, "unexpected"

        globals()["_http_get"] = http_g5
        shas, err = fetch_merged_pr_commit_shas("SP-5")
        if err is not None or shas != ["ccc333"]:
            failures.append(f"⑤ REST全成功: {(shas, err)!r}（期待 (['ccc333'], None)。SP-50 混入除外を確認）")

        # ⑥ gh が想定外形状（配列でなく辞書）を返す → 未処理の AttributeError でクラッシュせず、
        #    エラーとして返す（#723 指摘3 本体: 元の except 節は AttributeError を捕捉しなかった）。
        #    REST フォールバック側も失敗させ、gh 側の形状異常が正しく検知・フォールバックされた
        #    上でエラーになる（＝クラッシュではなく想定どおりのエラー経路）ことを確認する。
        globals()["_run_gh"] = lambda args: (True, json.dumps({"unexpected": "shape"}))
        globals()["_http_get"] = lambda url, token: (False, "HTTP 502")
        try:
            shas, err = fetch_merged_pr_commit_shas("SP-6")
        except AttributeError as e:
            failures.append(f"⑥ gh想定外形状: 未処理の AttributeError でクラッシュした（{e}）")
        else:
            if err is None:
                failures.append(f"⑥ gh想定外形状: エラーを期待したが {(shas, err)!r}")
    finally:
        globals()["_run_gh"] = orig_run_gh
        globals()["_http_get"] = orig_http_get
        clear_tokens()
        if orig_gh_token is not None:
            os.environ["GH_TOKEN"] = orig_gh_token
        if orig_github_token is not None:
            os.environ["GITHUB_TOKEN"] = orig_github_token

    return failures


def _self_test_fetch_open_pr_numbers() -> list[str]:
    """#723 指摘1 の補助関数 fetch_open_pr_numbers を gh→REST フォールバック込みで実測する。

    入力バリアント: ① gh 成功（前方一致ノイズ除外込み） ② gh 失敗 + token 無し
    ③ gh 失敗 + REST 検索成功。
    """
    failures = []
    orig_run_gh = _run_gh
    orig_http_get = _http_get
    orig_gh_token = os.environ.get("GH_TOKEN")
    orig_github_token = os.environ.get("GITHUB_TOKEN")

    def clear_tokens():
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)

    try:
        # ① gh 成功（前方一致ノイズ SP-70 の除外を確認）
        globals()["_run_gh"] = lambda args: (True, json.dumps([
            {"number": 7, "title": "feat(SP-7): 何か"},
            {"number": 8, "title": "feat(SP-70): 別件"},
        ]))
        numbers, err = fetch_open_pr_numbers("SP-7")
        if err is not None or numbers != [7]:
            failures.append(f"① gh成功: {(numbers, err)!r}（期待 ([7], None)。SP-70 混入除外を確認）")

        # ② gh 失敗 + token 無し → エラー
        globals()["_run_gh"] = lambda args: (False, "認証エラー")
        clear_tokens()
        numbers, err = fetch_open_pr_numbers("SP-8")
        if err is None:
            failures.append(f"② gh失敗+token無し: エラーを期待したが {(numbers, err)!r}")

        # ③ gh 失敗 + REST 検索成功
        os.environ["GH_TOKEN"] = "dummy-token-for-selftest"
        globals()["_http_get"] = lambda url, token: (True, json.dumps({"items": [
            {"number": 99, "title": "SP-9: 何か", "pull_request": {}},
        ]}))
        numbers, err = fetch_open_pr_numbers("SP-9")
        if err is not None or numbers != [99]:
            failures.append(f"③ REST成功: {(numbers, err)!r}（期待 ([99], None)）")
    finally:
        globals()["_run_gh"] = orig_run_gh
        globals()["_http_get"] = orig_http_get
        clear_tokens()
        if orig_gh_token is not None:
            os.environ["GH_TOKEN"] = orig_gh_token
        if orig_github_token is not None:
            os.environ["GITHUB_TOKEN"] = orig_github_token

    return failures


def _self_test_fetch_in_progress_sprint_candidates() -> list[str]:
    """#237: fetch_in_progress_sprint_candidates を gh→REST フォールバック込みで
    エントリポイントから実測する（`_run_gh` / `_http_get` をモック差し替え）。

    入力バリアント: ① gh 成功 ② gh 失敗 + token 無し ③ gh 失敗 + REST 失敗
    ④ gh 失敗 + REST 成功（pull_request キーを持つ行を除外することも確認）
    ⑤〜⑦ gh 失敗 + REST が list 以外（`{}` / `null` / 文字列）を返す
    （レビュー指摘 CONFIRMED 2: 「0 件」への誤読 fail-open の再発防止）。
    ⑧〜⑩ **gh 自体が exit 0 で** `{}` / `""` / `[]` を返す（gh 成功パスの isinstance 検査
    ・レビュー指摘 CRITICAL 2 の再発防止。`[]` は正当な「0 件」であり誤ってエラー扱いに
    ならないことも固定する）。
    ⑪〜⑬ gh 失敗 + REST 側でページング打ち切り境界（299/300/301 件・レビュー指摘 WARNING 4
    の再発防止。従来はこの関数にだけ打ち切り検知が無かった）。
    """
    failures = []
    orig_run_gh = _run_gh
    orig_http_get = _http_get
    orig_gh_token = os.environ.get("GH_TOKEN")
    orig_github_token = os.environ.get("GITHUB_TOKEN")

    def clear_tokens():
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)

    try:
        # ① gh 成功
        globals()["_run_gh"] = lambda args: (True, json.dumps([
            {"number": 1, "title": "SP-1: 何か", "body": "本文"},
        ]))
        issues, err = fetch_in_progress_sprint_candidates()
        if err is not None or issues != [{"number": 1, "title": "SP-1: 何か", "body": "本文"}]:
            failures.append(f"① gh成功: {(issues, err)!r}")

        # ② gh 失敗 + token 無し → エラー（issues は空リスト）
        globals()["_run_gh"] = lambda args: (False, "認証エラー")
        clear_tokens()
        issues, err = fetch_in_progress_sprint_candidates()
        if err is None or issues != []:
            failures.append(f"② gh失敗+token無し: エラーかつ issues=[] を期待したが {(issues, err)!r}")

        os.environ["GH_TOKEN"] = "dummy-token-for-selftest"

        # ③ gh 失敗 + REST 失敗 → エラー
        globals()["_http_get"] = lambda url, token: (False, "HTTP 502")
        issues, err = fetch_in_progress_sprint_candidates()
        if err is None:
            failures.append(f"③ REST失敗: エラーを期待したが {(issues, err)!r}")

        # ④ gh 失敗 + REST 成功（PR 行は pull_request キーで除外される）
        globals()["_http_get"] = lambda url, token: (True, json.dumps([
            {"number": 2, "title": "SP-2: 何か", "body": ""},
            {"number": 3, "title": "PR風", "body": "", "pull_request": {}},
        ]))
        issues, err = fetch_in_progress_sprint_candidates()
        if err is not None or issues != [{"number": 2, "title": "SP-2: 何か", "body": ""}]:
            failures.append(f"④ REST成功: {(issues, err)!r}（PR 行の除外を確認）")

        # ⑤〜⑦ REST 応答が list 以外（CONFIRMED 2 の再発防止ケース）→ 「0 件」に誤読せずエラー
        for label, body in (
            ("⑤ REST応答が{}", "{}"),
            ("⑥ REST応答がnull", "null"),
            ('⑦ REST応答が"文字列"', '"文字列"'),
        ):
            globals()["_http_get"] = lambda url, token, body=body: (True, body)
            issues, err = fetch_in_progress_sprint_candidates()
            if err is None or issues != []:
                failures.append(
                    f"{label}: 「取得失敗」と区別できるエラー・issues=[] を期待したが {(issues, err)!r}"
                )

        # ⑧〜⑩ gh **自体**が exit 0 で想定外スキーマを返すケース（CRITICAL 2 の再発防止）。
        # token を未設定にしておき、gh のスキーマ異常が REST フォールバックへ正しく倒れて
        # from-there エラーになる（`[]` だけは倒れず正常終了する）ことを確認する。
        clear_tokens()
        for label, gh_body, expect_error in (
            ("⑧ gh応答が{}", "{}", True),
            ('⑨ gh応答が""', '""', True),
            ("⑩ gh応答が[]（正当な0件）", "[]", False),
        ):
            globals()["_run_gh"] = lambda args, gh_body=gh_body: (True, gh_body)
            issues, err = fetch_in_progress_sprint_candidates()
            if expect_error:
                if err is None or issues != []:
                    failures.append(
                        f"{label}: gh 成功パスの型検査でエラーになることを期待したが {(issues, err)!r}"
                    )
            else:
                if err is not None or issues != []:
                    failures.append(
                        f"{label}: 正当な 0 件（エラーなし）を期待したが {(issues, err)!r}"
                    )

        # ⑪〜⑬ gh は失敗のまま、REST 側の件数を境界表（MAX_IN_PROGRESS_ISSUE_PAGES=3）
        # どおりに変えて打ち切り検知を確認する（WARNING 4 の再発防止）。
        globals()["_run_gh"] = lambda args: (False, "認証エラー")
        os.environ["GH_TOKEN"] = "dummy-token-for-selftest"

        def make_issue_rest_pager(total: int):
            def http_get(url, token):
                m = re.search(r"[?&]page=(\d+)", url)
                page = int(m.group(1)) if m else 1
                start = (page - 1) * 100
                end = min(start + 100, total)
                if start >= total:
                    return True, json.dumps([])
                batch = [
                    {"number": 1000 + i, "title": f"SP-{i}: 何か", "body": ""}
                    for i in range(start, end)
                ]
                return True, json.dumps(batch)
            return http_get

        for total, expect_truncated in ((299, False), (300, True), (301, True)):
            globals()["_http_get"] = make_issue_rest_pager(total)
            issues, err = fetch_in_progress_sprint_candidates()
            if expect_truncated:
                if err is None:
                    failures.append(
                        f"件数{total}（in-progress候補）: 打ち切り疑いでエラーを期待したが "
                        f"{(len(issues), err)!r}"
                    )
            else:
                if err is not None or len(issues) != total:
                    failures.append(
                        f"件数{total}（in-progress候補）: エラーなし・{total}件取得を期待したが "
                        f"{(len(issues), err)!r}"
                    )
    finally:
        globals()["_run_gh"] = orig_run_gh
        globals()["_http_get"] = orig_http_get
        clear_tokens()
        if orig_gh_token is not None:
            os.environ["GH_TOKEN"] = orig_gh_token
        if orig_github_token is not None:
            os.environ["GITHUB_TOKEN"] = orig_github_token

    return failures


def _self_test_fetch_issue_comments() -> list[str]:
    """#237: fetch_issue_comments を gh→REST フォールバック込みでエントリポイントから実測する。

    入力バリアント: ① gh 成功 ② gh 失敗 + token 無し ③ gh 失敗 + REST 失敗
    ④〜⑩ gh 失敗 + REST 成功で件数を境界表どおりに変える（0/1/99/100/101/999 件は打ち切り
    なし、300 件は中間値として非境界であることも確認、1000/1001 件は打ち切り疑いでエラー）。
    ⑪〜⑬ gh 失敗 + REST が list 以外（`{}` / `null` / 文字列）を返す（レビュー指摘
    CONFIRMED 2 の再発防止）。
    ⑭〜⑯ **gh 自体が exit 0** で想定外スキーマ（トップレベルが list / 空文字列）を返す
    （レビュー指摘 CRITICAL 2 の再発防止）。`{"comments": []}`（正当な 0 件）は誤ってエラー
    扱いにならないことも固定する。境界の根拠は関数内コメントの入力境界表（MAX_COMMENT_PAGES）を参照。
    """
    failures = []
    orig_run_gh = _run_gh
    orig_http_get = _http_get
    orig_gh_token = os.environ.get("GH_TOKEN")
    orig_github_token = os.environ.get("GITHUB_TOKEN")

    def clear_tokens():
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)

    def make_rest_pager(total: int):
        """`total` 件のコメントを 100 件区切りでページング応答するダミー _http_get。"""
        def http_get(url, token):
            # "per_page=100" にも "page=" が部分一致するため `[?&]` 境界で区切って誤マッチを防ぐ
            m = re.search(r"[?&]page=(\d+)", url)
            page = int(m.group(1)) if m else 1
            start = (page - 1) * 100
            end = min(start + 100, total)
            if start >= total:
                return True, json.dumps([])
            batch = [
                {"body": f"comment {i}", "created_at": f"2026-08-{(i % 28) + 1:02d}T00:00:00Z",
                 "author_association": "OWNER"}
                for i in range(start, end)
            ]
            return True, json.dumps(batch)
        return http_get

    try:
        # ① gh 成功
        globals()["_run_gh"] = lambda args: (True, json.dumps({
            "comments": [
                {"body": "c1", "createdAt": "2026-08-20T00:00:00Z", "authorAssociation": "OWNER"},
            ]
        }))
        comments, err = fetch_issue_comments(1)
        if err is not None or len(comments) != 1:
            failures.append(f"① gh成功: {(comments, err)!r}")

        # ② gh 失敗 + token 無し → エラー
        globals()["_run_gh"] = lambda args: (False, "認証エラー")
        clear_tokens()
        comments, err = fetch_issue_comments(2)
        if err is None or comments != []:
            failures.append(f"② gh失敗+token無し: エラーかつ comments=[] を期待したが {(comments, err)!r}")

        os.environ["GH_TOKEN"] = "dummy-token-for-selftest"

        # ③ gh 失敗 + REST 失敗 → エラー
        globals()["_http_get"] = lambda url, token: (False, "HTTP 502")
        comments, err = fetch_issue_comments(3)
        if err is None:
            failures.append(f"③ REST失敗: エラーを期待したが {(comments, err)!r}")

        # ④〜⑩: gh は失敗のまま、REST 側の件数を境界表（MAX_COMMENT_PAGES=10）どおりに変えて確認する
        boundary_cases = [
            (0, False), (1, False), (99, False), (100, False),
            (101, False), (300, False), (999, False),
            (1000, True), (1001, True),
        ]
        for total, expect_truncated in boundary_cases:
            globals()["_http_get"] = make_rest_pager(total)
            comments, err = fetch_issue_comments(100 + total)
            if expect_truncated:
                if err is None:
                    failures.append(
                        f"件数{total}: 打ち切り疑いでエラーを期待したが {(len(comments), err)!r}"
                    )
            else:
                if err is not None or len(comments) != total:
                    failures.append(
                        f"件数{total}: エラーなし・{total}件取得を期待したが {(len(comments), err)!r}"
                    )

        # ⑪〜⑬ REST 応答が list 以外（CONFIRMED 2 の再発防止ケース）→ 「0 件」に誤読せずエラー
        for label, body in (
            ("⑪ REST応答が{}", "{}"),
            ("⑫ REST応答がnull", "null"),
            ('⑬ REST応答が"文字列"', '"文字列"'),
        ):
            globals()["_http_get"] = lambda url, token, body=body: (True, body)
            comments, err = fetch_issue_comments(999)
            if err is None or comments != []:
                failures.append(
                    f"{label}: 「取得失敗」と区別できるエラー・comments=[] を期待したが {(comments, err)!r}"
                )

        # ⑭〜⑯ gh **自体**が exit 0 で想定外スキーマを返すケース（CRITICAL 2 の再発防止）。
        # token 未設定にして REST フォールバックへ正しく倒れることを確認する
        # （`{"comments": []}` は正当な 0 件で、倒れずそのまま終わることも確認する）。
        clear_tokens()
        for label, gh_body, expect_error in (
            ("⑭ gh応答がlist", "[]", True),
            ('⑮ gh応答が""', '""', True),
            ('⑯ gh応答が{"comments": []}（正当な0件）', json.dumps({"comments": []}), False),
        ):
            globals()["_run_gh"] = lambda args, gh_body=gh_body: (True, gh_body)
            comments, err = fetch_issue_comments(1000)
            if expect_error:
                if err is None or comments != []:
                    failures.append(
                        f"{label}: gh 成功パスの型検査でエラーになることを期待したが {(comments, err)!r}"
                    )
            else:
                if err is not None or comments != []:
                    failures.append(
                        f"{label}: 正当な 0 件（エラーなし）を期待したが {(comments, err)!r}"
                    )
    finally:
        globals()["_run_gh"] = orig_run_gh
        globals()["_http_get"] = orig_http_get
        clear_tokens()
        if orig_gh_token is not None:
            os.environ["GH_TOKEN"] = orig_gh_token
        if orig_github_token is not None:
            os.environ["GITHUB_TOKEN"] = orig_github_token

    return failures


def _self_test_main_unhandled_exception() -> list[str]:
    """#313 / レビュー指摘 CONFIRMED 3: main() 内の未捕捉例外が exit 2（判定不能）になり、
    正常な待機（exit 1）やデプロイ可（exit 0）と区別できることを、エントリポイント `main()`
    から実測する。あわせて次の 2 点を確認する:
      - `SystemExit`（正常系の `sys.exit`）は素通りする（`except SystemExit: raise` が
        `except BaseException` より先に評価されることの確認・回帰防止）
      - `Exception` を継承しない `BaseException`（実運用では主に `KeyboardInterrupt`）も
        exit 2 に倒れる（`except Exception` のまま据え置く後退が起きていないかの確認）
    """
    import contextlib
    import io

    failures = []
    orig_argv = sys.argv
    orig_fetch = fetch_in_progress_sprint_candidates
    orig_repo = REPO

    def restore():
        sys.argv = orig_argv
        globals()["fetch_in_progress_sprint_candidates"] = orig_fetch
        global REPO
        REPO = orig_repo

    def run_main() -> tuple[int | None, str, str]:
        buf_out, buf_err = io.StringIO(), io.StringIO()
        code = None
        try:
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                main()
        except SystemExit as e:
            code = e.code
        return code, buf_out.getvalue(), buf_err.getvalue()

    try:
        # ケース1: 未捕捉例外（--json）→ exit 2・can_deploy: null・例外型がメッセージに含まれる
        globals()["fetch_in_progress_sprint_candidates"] = (
            lambda: (_ for _ in ()).throw(ValueError("boom"))
        )
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, out, _err = run_main()
        if code != 2:
            failures.append(f"main(): 未捕捉例外は exit 2 を期待したが {code!r}")
        try:
            payload = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if payload.get("can_deploy") is not None:
            failures.append(
                f"main(): 未捕捉例外時の can_deploy は null を期待したが {payload.get('can_deploy')!r}"
            )
        if "ValueError" not in (payload.get("error") or ""):
            failures.append(f"main(): 未捕捉例外の型が error メッセージに含まれない: {payload.get('error')!r}")

        # ケース2: 同じ例外を非 --json で発生させる → stderr に出て exit 2
        sys.argv = ["check_deploy_gate.py", "--repo", "owner/name"]
        code, _out, err = run_main()
        if code != 2:
            failures.append(f"main(): 非JSON時の未捕捉例外は exit 2 を期待したが {code!r}")
        if "ValueError" not in err:
            failures.append(f"main(): 非JSON時の未捕捉例外が stderr に出ていない: {err!r}")

        # ケース3: 既存の正常なエラー応答（sys.exit(2) 直呼び）は変わらず exit 2
        globals()["fetch_in_progress_sprint_candidates"] = lambda: ([], "取得失敗テスト")
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, _out, _err = run_main()
        if code != 2:
            failures.append(f"main(): fetch のエラー応答は exit 2 を期待したが {code!r}")

        # ケース4: 正常系（issues 0 件）は exit 0 のまま（例外ハンドラが正常終了を握り潰さない）
        globals()["fetch_in_progress_sprint_candidates"] = lambda: ([], None)
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, _out, _err = run_main()
        if code != 0:
            failures.append(f"main(): 正常系（塞ぐIssueなし）は exit 0 を期待したが {code!r}")

        # ケース5: fetch 内で明示的な sys.exit(5)（本実装には無いが「`except SystemExit: raise`
        # より先に `except BaseException` が評価されてしまっていないか」を検知する回帰ケース）
        # → 5 のまま伝播する
        def raise_system_exit_5():
            sys.exit(5)

        globals()["fetch_in_progress_sprint_candidates"] = raise_system_exit_5
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, _out, _err = run_main()
        if code != 5:
            failures.append(
                f"main(): SystemExit(5) は素通りして exit 5 を期待したが {code!r}"
                "（except SystemExit: raise が except BaseException より先に評価されているか確認）"
            )

        # ケース6（レビュー指摘 CONFIRMED 3）: `Exception` を継承しない `BaseException`
        # （`KeyboardInterrupt` で代表）が `except Exception` だけでは素通りして CPython 既定の
        # exit 1（正常な「待機」と区別できない値）に化けていた経路の再発防止。
        # `except BaseException` へ拡張済みなら exit 2（判定不能）に倒れるはず。
        def raise_keyboard_interrupt():
            raise KeyboardInterrupt()

        globals()["fetch_in_progress_sprint_candidates"] = raise_keyboard_interrupt
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, out, _err = run_main()
        if code != 2:
            failures.append(
                f"main(): KeyboardInterrupt（Exception 非継承の BaseException）は exit 2 を"
                f"期待したが {code!r}（except Exception のままだと exit 1 に化ける・CONFIRMED 3）"
            )
        try:
            payload = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if "KeyboardInterrupt" not in (payload.get("error") or ""):
            failures.append(
                f"main(): KeyboardInterrupt の型が error メッセージに含まれない: {payload.get('error')!r}"
            )
    finally:
        restore()

    return failures


def _self_test_main_token_sanitization() -> list[str]:
    """レビュー指摘 CONFIRMED 1: `GH_TOKEN` の実値が未捕捉例外のメッセージに埋まっていても、
    `main()` の出力（stdout の JSON / stderr のテキスト）にトークン実値が 1 文字も現れない
    ことをエントリポイントから実測する（`_http_get` が `Authorization: Bearer <token>` を
    組み立てる際、トークンに不正な文字が混ざっていると `http.client` が
    `ValueError: Invalid header value b'Bearer <トークン全文>...'` を送出し、この例外は
    `_http_get` の `except`（HTTPError/URLError/TimeoutError）を素通りして `main()` の
    未捕捉例外ハンドラまで届く実測済みの経路・CONFIRMED 1 の再現ケース）。
    `--json`（stdout）・非 JSON（stderr）の両方の出力経路を検査する。

    あわせて次の再発防止ケースを含む:
      - トークン自体に実際の CR/LF を埋め込み、`http.client.putheader` が送出する
        bytes repr 形式のメッセージを忠実に再現するケース（CRITICAL 1: 値そのものの
        単純 `str.replace` だけでは、エスケープ済み表現との不一致で空振りしていた）
      - 短い値・空白のみの値では無関係なメッセージ全文を巻き添えにしないケース
        （WARNING 3: `MIN_SECRET_LEN` 未満は対象外にする）
    """
    import contextlib
    import io

    failures = []
    orig_argv = sys.argv
    orig_fetch = fetch_in_progress_sprint_candidates
    orig_repo = REPO
    orig_gh_token = os.environ.get("GH_TOKEN")
    orig_github_token = os.environ.get("GITHUB_TOKEN")

    CANARY = "ghp_CANARY_MUST_NOT_LEAK_1234"

    def restore():
        sys.argv = orig_argv
        globals()["fetch_in_progress_sprint_candidates"] = orig_fetch
        global REPO
        REPO = orig_repo
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        if orig_gh_token is not None:
            os.environ["GH_TOKEN"] = orig_gh_token
        if orig_github_token is not None:
            os.environ["GITHUB_TOKEN"] = orig_github_token

    def run_main() -> tuple[int | None, str, str]:
        buf_out, buf_err = io.StringIO(), io.StringIO()
        code = None
        try:
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                main()
        except SystemExit as e:
            code = e.code
        return code, buf_out.getvalue(), buf_err.getvalue()

    try:
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ["GH_TOKEN"] = CANARY

        # CONFIRMED 1 の実測経路を模す: putheader が送出する ValueError にはトークン実値が
        # `Bearer <値>` の形（bytes repr 込み）で埋まる。
        def raise_header_value_error():
            raise ValueError(
                f"Invalid header value b'Bearer {CANARY}\\r\\n'"
            )

        globals()["fetch_in_progress_sprint_candidates"] = raise_header_value_error

        # --json（stdout）
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, out, err = run_main()
        if code != 2:
            failures.append(f"トークン漏洩再現(--json): exit 2 を期待したが {code!r}")
        if CANARY in out or CANARY in err:
            failures.append(
                f"トークン漏洩再現(--json): カナリアが出力に残っている（stdout={out!r} / stderr={err!r}）"
            )
        if "***" not in out:
            failures.append(f"トークン漏洩再現(--json): 伏字 '***' が stdout に見つからない: {out!r}")

        # 非 JSON（stderr）
        sys.argv = ["check_deploy_gate.py", "--repo", "owner/name"]
        code, out, err = run_main()
        if code != 2:
            failures.append(f"トークン漏洩再現(非JSON): exit 2 を期待したが {code!r}")
        if CANARY in out or CANARY in err:
            failures.append(
                f"トークン漏洩再現(非JSON): カナリアが出力に残っている（stdout={out!r} / stderr={err!r}）"
            )
        if "***" not in err:
            failures.append(f"トークン漏洩再現(非JSON): 伏字 '***' が stderr に見つからない: {err!r}")

        # GITHUB_TOKEN 側でも同様に伏字化されることを確認する
        os.environ.pop("GH_TOKEN", None)
        os.environ["GITHUB_TOKEN"] = CANARY
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, out, err = run_main()
        if CANARY in out or CANARY in err:
            failures.append(
                f"トークン漏洩再現(GITHUB_TOKEN): カナリアが出力に残っている（stdout={out!r}）"
            )

        # 【レビュー指摘 CRITICAL 1 の実測再現】トークン自体に CR/LF を埋め込み、
        # `http.client.putheader` が実際に送出する bytes repr（`%r`）形式のメッセージを
        # 忠実に再現する。生の値（実 CR/LF を含む）のままではエスケープ済みテキストと
        # 部分文字列一致しないため、旧実装（値そのものの `str.replace` のみ）はここで
        # 空振りしていた。既存ケース（メッセージ文字列側に既にエスケープ済みテキストを
        # 手書きで足すだけ）はこの不一致を踏まないため区別して追加する。
        os.environ.pop("GITHUB_TOKEN", None)
        canary_with_crlf = CANARY + "\r\nX-Evil: 1"
        os.environ["GH_TOKEN"] = canary_with_crlf

        def raise_putheader_style_error():
            header_bytes = f"Bearer {canary_with_crlf}".encode()
            raise ValueError("Invalid header value %r" % (header_bytes,))

        globals()["fetch_in_progress_sprint_candidates"] = raise_putheader_style_error

        for argv, stream_label in (
            (["check_deploy_gate.py", "--json", "--repo", "owner/name"], "--json"),
            (["check_deploy_gate.py", "--repo", "owner/name"], "非JSON"),
        ):
            sys.argv = argv
            code, out, err = run_main()
            combined = out + err
            if code != 2:
                failures.append(f"CR/LF実測再現({stream_label}): exit 2 を期待したが {code!r}")
            if CANARY in combined:
                failures.append(
                    f"CR/LF実測再現({stream_label}): カナリアが出力に残っている（{combined!r}）"
                )
            if "***" not in combined:
                failures.append(
                    f"CR/LF実測再現({stream_label}): 伏字 '***' が出力に見つからない（{combined!r}）"
                )

        # 【レビュー指摘 WARNING 3】短い値・空白のみの値では無関係なメッセージ全文を
        # 巻き添えにして破壊しないことを確認する（`MIN_SECRET_LEN` 未満は対象外にする）。
        os.environ.pop("GH_TOKEN", None)
        for label, short_token, message_text in (
            ("空白のみ", " ", "normal message with spaces here"),
            ("1文字", "e", "ValueError: some message here"),
            (f"{MIN_SECRET_LEN - 1}文字（MIN_SECRET_LEN未満）", "short12", "value=short12 embedded in message"),
        ):
            os.environ["GH_TOKEN"] = short_token
            globals()["fetch_in_progress_sprint_candidates"] = (
                lambda message_text=message_text: (_ for _ in ()).throw(ValueError(message_text))
            )
            sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
            code, out, err = run_main()
            try:
                payload = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
            except json.JSONDecodeError:
                payload = {}
            expected = f"未捕捉の例外が発生しました（ValueError: {message_text}）"
            if payload.get("error") != expected:
                failures.append(
                    f"WARNING3({label}): 短い/空白トークンでメッセージが破壊された: "
                    f"{payload.get('error')!r}（期待 {expected!r}）"
                )
            os.environ.pop("GH_TOKEN", None)

        # 境界値ちょうど（MIN_SECRET_LEN 文字）は引き続き伏字化されることも確認する
        # （下限ガードが必要以上に広く効いて正当な長さのトークンまで見逃していないか）
        boundary_token = "x" * MIN_SECRET_LEN
        os.environ["GH_TOKEN"] = boundary_token
        globals()["fetch_in_progress_sprint_candidates"] = (
            lambda: (_ for _ in ()).throw(ValueError(f"token={boundary_token} leaked"))
        )
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, out, err = run_main()
        if boundary_token in out:
            failures.append(
                f"MIN_SECRET_LEN境界: {MIN_SECRET_LEN}文字ちょうどのトークンが伏字化されていない: {out!r}"
            )
        os.environ.pop("GH_TOKEN", None)

        # 空文字・未設定のトークンでは全文置換が事故を起こさないことも確認する
        # （`value.replace("", "***")` のような空文字一致で本文が壊れていないか）
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        globals()["fetch_in_progress_sprint_candidates"] = (
            lambda: (_ for _ in ()).throw(ValueError("通常のメッセージ"))
        )
        sys.argv = ["check_deploy_gate.py", "--json", "--repo", "owner/name"]
        code, out, err = run_main()
        try:
            payload = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if payload.get("error") != "未捕捉の例外が発生しました（ValueError: 通常のメッセージ）":
            failures.append(
                f"トークン未設定時: メッセージが不必要に伏字化されていないか確認: {payload.get('error')!r}"
            )
    finally:
        restore()

    return failures


def _self_test_decide_and_exit_code() -> list[str]:
    failures = []
    always_merged = lambda title: True  # noqa: E731

    # 塞ぐ Issue が無い → デプロイ可（exit 0）
    result = decide([
        (_issue(1, "SP-1: a"), [_verdict_comment("accepted")]),
        (_issue(2, "fix: 無関係なバグ"), []),
    ], merged_check=always_merged)
    if result["can_deploy"] is not True or result["blocking_issues"]:
        failures.append(f"decide: 全 accepted で can_deploy=True を期待したが {result}")
    if exit_code_for(result["can_deploy"]) != 0:
        failures.append("exit_code_for: can_deploy=True は exit 0 を期待")

    # 1 件でも塞ぐ Issue（main 反映済み前提）があれば待機（exit 1）。塞がない Issue が
    # 混在していても変わらない
    result = decide([
        (_issue(1, "SP-1: a"), [_verdict_comment("accepted")]),
        (_issue(2, "SP-2: b"), [_verdict_comment("rejected")]),
        (_issue(3, "SP-3: c"), []),  # 判定未実施
    ], merged_check=always_merged)
    if result["can_deploy"] is not False:
        failures.append(f"decide: rejected/未実施混在で can_deploy=False を期待したが {result}")
    blocking_numbers = sorted(b["number"] for b in result["blocking_issues"])
    if blocking_numbers != [2, 3]:
        failures.append(f"decide: 塞ぐ Issue 番号が不一致: {blocking_numbers}（期待 [2, 3]）")
    if exit_code_for(result["can_deploy"]) != 1:
        failures.append("exit_code_for: can_deploy=False は exit 1 を期待")

    # #471: rejected/未実施でも main に未反映と確定できれば塞がない（デプロイ可・exit 0）
    result = decide([
        (_issue(1, "SP-1: a"), [_verdict_comment("rejected")]),
        (_issue(2, "SP-2: b"), []),  # 判定未実施
    ], merged_check=lambda title: False)
    if result["can_deploy"] is not True or result["blocking_issues"]:
        failures.append(f"decide: 全件 main 未反映なら can_deploy=True を期待したが {result}")

    # 判定不能（API 到達不可等）は can_deploy=None → exit 2（fail-closed）
    if exit_code_for(None) != 2:
        failures.append("exit_code_for: can_deploy=None は exit 2（fail-closed）を期待")

    return failures


def _self_test_mask_occurrences() -> list[str]:
    """CI 指摘（CodeQL "Clear-text logging of sensitive information"・PR #735）対応の
    `_mask_occurrences` / `_sanitize_secrets` の置換順序・全件置換を実測する。

    既存の `_self_test_main_token_sanitization` は「単一の秘匿値がメッセージ中に 1 回だけ
    現れる」ケースしか踏んでおらず、次の 2 つの実害シナリオを検知できなかった:
      - 同一の秘匿値がメッセージ中に **複数回** 現れる（後段の出現が伏字化されない）
      - **短い候補が、より長い候補の部分文字列になっている**（`GH_TOKEN` の値の中に
        `GITHUB_TOKEN` の値がそのまま埋まっている等）ときに短い方を先に置換すると、
        長い方の置換が「もう一致しない」ため素通りし、**秘匿値の断片が平文で残る**
        （`_sanitize_secrets` が候補を長い順に処理する理由そのもの）。
    """
    failures = []

    # ① _mask_occurrences 単体: 同一 needle の複数出現を全て置換する
    masked = _mask_occurrences("token=SECRETVALUE end SECRETVALUE end2", "SECRETVALUE")
    if "SECRETVALUE" in masked or masked.count(SECRET_PLACEHOLDER) != 2:
        failures.append(
            f"_mask_occurrences: 複数出現を全置換できていない: {masked!r}"
        )

    # ② _sanitize_secrets の統合シナリオ: GITHUB_TOKEN の値が GH_TOKEN の値の
    # 部分文字列になっている（実運用でも「片方がもう片方を内包する」誤設定は起こりうる）。
    # 短い候補（GITHUB_TOKEN 由来）を先に処理すると、長い候補（GH_TOKEN 由来）の
    # 置換が素通りし "SECRET" と "5" という秘匿値の断片が平文で残る。
    orig_gh_token = os.environ.get("GH_TOKEN")
    orig_github_token = os.environ.get("GITHUB_TOKEN")
    try:
        os.environ["GH_TOKEN"] = "SECRETVALUE12345"  # 長い候補（17文字）
        os.environ["GITHUB_TOKEN"] = "VALUE1234"      # 短い候補（9文字）。上の値の部分文字列
        message = "leaked: SECRETVALUE12345 end"
        sanitized = _sanitize_secrets(message)
        if "SECRET" in sanitized or "VALUE1234" in sanitized or "12345" in sanitized:
            failures.append(
                f"_sanitize_secrets: 長い候補優先の順序が壊れ秘匿値の断片が残った: {sanitized!r}"
            )
        if sanitized != "leaked: *** end":
            failures.append(
                f"_sanitize_secrets: 長い候補を単一の '***' に丸ごと置換できていない: {sanitized!r}"
            )
    finally:
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        if orig_gh_token is not None:
            os.environ["GH_TOKEN"] = orig_gh_token
        if orig_github_token is not None:
            os.environ["GITHUB_TOKEN"] = orig_github_token

    return failures


def run_self_test() -> int:
    groups = [
        ("スプリント対象判定", _self_test_is_sprint_issue),
        ("判定コメントのパース（accepted_with_conditions 優先）", _self_test_verdict_result_re),
        ("最新判定の優先順位", _self_test_latest_verdict_order),
        ("判定コメントの投稿者権限検証", _self_test_verdict_author_guard),
        ("Issue 単位のゲート判定", _self_test_evaluate_issue),
        ("main 反映判定の統合（#471）", _self_test_merged_check_integration),
        ("main 反映判定の純ロジック（#471/#723）", _self_test_is_merged_into_main),
        ("main 祖先判定・fetch メモ化（git 呼び出しのモック差し替え・#471/#723）", _self_test_is_ancestor_of_main),
        ("merged PR 検索の gh/REST フォールバック（#723 指摘3）", _self_test_fetch_merged_pr_commit_shas),
        ("open PR 検索の gh/REST フォールバック（#723 指摘1）", _self_test_fetch_open_pr_numbers),
        ("in-progress スプリント候補の gh/REST フォールバック（#237）", _self_test_fetch_in_progress_sprint_candidates),
        ("Issue コメント取得の gh/REST フォールバックとページング打ち切り（#237）", _self_test_fetch_issue_comments),
        ("main() の未捕捉例外→exit 2 写像（#313・BaseException 拡張含む）", _self_test_main_unhandled_exception),
        ("main() 未捕捉例外時のトークンサニタイズ（CONFIRMED 1）", _self_test_main_token_sanitization),
        ("_mask_occurrences の全件置換・長い候補優先の順序（PR #735 CodeQL 対応）", _self_test_mask_occurrences),
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

    # 【#313 / レビュー指摘 CONFIRMED 3】判定処理中の未捕捉例外は CPython 既定の exit 1 に
    # 化け、正常な「待機」（exit 1）と区別できなくなる（fail-closed の 3 値契約 0/1/2 が壊れる）。
    # ここで捕捉し exit 2（判定不能）へ写像する。`SystemExit`（正常な `sys.exit(0/1/2)`）だけは
    # 先に `raise` で素通しし、それ以外は `BaseException` で受ける（`Exception` だけだと
    # `KeyboardInterrupt` 等が素通りして exit 1 に化ける経路が残るため）。`KeyboardInterrupt` を
    # 「デプロイ待機」ではなく「判定不能」に倒すのは、中断された時点で判定処理が最後まで
    # 走り切ったかどうか保証できず、fail-closed の原則上デプロイ可には倒せないため。
    try:
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
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 — 未捕捉例外を fail-closed の exit 2 へ写像する
        # （#313・レビュー指摘 CONFIRMED 3）。`SystemExit` は上の節で既に再送出済みのため
        # ここへは落ちてこない（`except` 節は上から順に一致判定されるため、この節が
        # `SystemExit` を横取りすることはない）。
        #
        # 【レビュー指摘 CONFIRMED 1・トークン漏洩の実測再現への対応】
        # `GH_TOKEN` / `GITHUB_TOKEN` に不正な文字（末尾改行等）が混ざっていると、
        # `_http_get` が組み立てる `Authorization` ヘッダを `http.client` に渡す際に
        # `putheader` が `ValueError: Invalid header value b'Bearer <トークン全文>...'` を
        # 送出することがあり、この例外は `_http_get` 内の `except`（HTTPError/URLError/
        # TimeoutError）では拾われずここまで素通りする。`str(e)` にトークン実値が
        # そのまま埋まりうるため、`_emit_error` に渡す前に必ずサニタイズする
        # （「urllib の例外だからトークンは含まれない」という以前の想定は誤りだった）。
        message = _sanitize_secrets(f"未捕捉の例外が発生しました（{type(e).__name__}: {e}）")
        _emit_error(message, args.json)
        sys.exit(2)


# GH_TOKEN/GITHUB_TOKEN の実値としてあまりに短い文字列（誤設定・空白のみ・テスト値等）まで
# 伏字化の対象にすると、その短い文字列がメッセージ中の無関係な単語と偶然部分一致して全文が
# 判読不能になる（レビュー指摘 WARNING 3・実測: `GH_TOKEN=" "` で通常メッセージの単語の
# 隙間が軒並み `***` に置換された）。実運用の GitHub トークンは数十文字あるため、
# この長さ未満の値・セグメントは伏字化の対象外にする。
MIN_SECRET_LEN = 8


def _collect_secret_candidates(value: str, candidates: set[str]) -> None:
    """`value`（環境変数の生値）から、メッセージ中に現れうる表現の候補を `candidates` へ
    集める（レビュー指摘 CRITICAL 1 の再発防止）。

      - 生の値そのもの（値に制御文字を含まない通常のケースでの一致用）
      - `unicode_escape` でエスケープした表現: `http.client.putheader` が送出する
        `ValueError` の `str(e)` は bytes repr（`b'...'`）であり、値に含まれる CR/LF 等の
        制御文字が `\\r` `\\n` という 2 文字テキストへ変換されて現れる。生の値のままでは
        この表示形と部分文字列一致しない（CRITICAL 1 の実測再現ケースそのもの）。
      - 制御文字・空白で分割した各セグメント（生・エスケープ済みの両方）: 値自体にヘッダ
        インジェクション用の制御文字が混ざっている場合、値全体のエスケープ表現がメッセージの
        実際の表示形と完全一致しない可能性がある defense-in-depth。

    `MIN_SECRET_LEN` 未満の候補（前後の空白を除いた長さで判定）は追加しない
    （レビュー指摘 WARNING 3: 短い候補による無関係テキストの巻き添え破壊を防ぐ）。
    """
    def add(candidate: str) -> None:
        if len(candidate.strip()) >= MIN_SECRET_LEN:
            candidates.add(candidate)
            candidates.add(candidate.encode("unicode_escape").decode("ascii"))

    add(value)
    for segment in re.split(r"[\s\x00-\x1f\x7f]+", value):
        if segment:
            add(segment)


SECRET_PLACEHOLDER = "***"


def _mask_occurrences(message: str, needle: str) -> str:
    """`message` 中の `needle`（秘匿値由来の候補文字列）の出現箇所を `SECRET_PLACEHOLDER`
    へ置き換える（CI 指摘: CodeQL "Clear-text logging of sensitive information" 対応・PR #735）。

    🔴 戻り値は `message` のスライスと定数 `SECRET_PLACEHOLDER` だけから組み立てる。
    `str.replace(needle, ...)` のように `needle`（秘匿値そのもの）を戻り値の組み立てに
    使う API へ渡すと、CodeQL の文字列モデルは taint（秘匿値 → 戻り値）を伝播させ、
    その戻り値が `print` に渡る経路を「平文でのログ出力」として検知する（`str.replace`
    はサニタイザとして認識されない）。ここでは `needle` を `str.find`/`len` という
    **int を返す** 演算にしか使わず、出力文字列そのものの組み立てには一切関与させない
    （`tools/check_prod_drift.py` の `count_build_triggers()` と同じ設計判断: 秘匿値を
    扱う関数から秘匿値由来の文字列を返さない）。
    """
    if not needle:
        return message
    parts: list[str] = []
    start = 0
    while True:
        idx = message.find(needle, start)
        if idx == -1:
            parts.append(message[start:])
            return "".join(parts)
        parts.append(message[start:idx])
        parts.append(SECRET_PLACEHOLDER)
        start = idx + len(needle)


def _sanitize_secrets(message: str) -> str:
    """`GH_TOKEN` / `GITHUB_TOKEN` の実値がメッセージ中に含まれていたら伏字（`***`）へ
    置換する（レビュー指摘 CONFIRMED 1）。`Bearer <値>` の形や `b'...'` bytes repr、値の
    途中に制御文字が混ざって別表現へエスケープされている場合も含めて潰す
    （候補の集め方は `_collect_secret_candidates` を参照）。
    値が空文字・未設定の環境変数、および `MIN_SECRET_LEN` 未満の値は対象にしない
    （空文字・短い値の部分一致で無関係なテキストごと壊す事故を防ぐ・WARNING 3）。
    置換そのものは `_mask_occurrences`（`str.replace` に秘匿値を渡さない実装）に委譲する。
    """
    candidates: set[str] = set()
    for env_name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(env_name)
        if value:
            _collect_secret_candidates(value, candidates)
    # 長い候補から順に置換する（短い候補を先に置換すると、それを含む長い候補が部分的に
    # 欠けて一致しなくなり、置換漏れが起きるため）。
    for candidate in sorted(candidates, key=len, reverse=True):
        message = _mask_occurrences(message, candidate)
    return message


def _emit_error(message: str, as_json: bool) -> None:
    # `_emit_error` は main() の複数箇所（fetch エラー・未捕捉例外の両方）から呼ばれる
    # 唯一の出力窓口のため、ここでも一段サニタイズをかけて防御を重ねる（呼び出し漏れ対策）。
    message = _sanitize_secrets(message)
    if as_json:
        print(json.dumps(
            {"can_deploy": None, "error": message, "checked_at": now_jst_str(), "repo": REPO},
            ensure_ascii=False,
        ))
    else:
        print(f"ERROR: 判定不能: {message}", file=sys.stderr)


if __name__ == "__main__":
    main()
