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
       - 未マージ（該当 PR が無い、または祖先でない）と **確定できた** → 塞がない
         （本番に影響しないため）
       - マージ済み、または **判定不能**（SP-n がタイトルに無い・PR 検索/取得の失敗・
         git 判定の失敗）→ 塞ぐ（fail-closed。判定不能を「未マージ」の既定値にしない）
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
# main 反映判定（#471）: Issue → PR 対応付け + merge_commit_sha の祖先判定
# ──────────────────────────────────────────────


def fetch_merged_pr_commit_shas(sprint_id: str) -> tuple[list[str], str | None]:
    """`sprint_id`（例 "SP-3"）をタイトルに含む merged PR の merge commit SHA 一覧を返す。

    Returns (shas, error_reason)。取得失敗時は shas=[] で error_reason に理由を入れる
    （「取得失敗」を「該当 PR 0 件（未マージ）」と混同しない・fail-closed の前提）。
    """
    query = f'"{sprint_id}" in:title'
    ok, out = _run_gh([
        "pr", "list", "-R", REPO, "--search", query, "--state", "merged",
        "--json", "number,mergeCommit", "--limit", "50",
    ])
    if ok:
        try:
            data = json.loads(out)
            shas = [
                d["mergeCommit"]["oid"]
                for d in data
                if isinstance(d.get("mergeCommit"), dict) and d["mergeCommit"].get("oid")
            ]
            return shas, None
        except (json.JSONDecodeError, KeyError, TypeError):
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
    except json.JSONDecodeError:
        return [], f"gh 失敗（{gh_err}）・REST 応答のパースに失敗"
    numbers = [item["number"] for item in data2.get("items", []) if "pull_request" in item]

    shas: list[str] = []
    for number in numbers:
        okp, outp = _http_get(f"https://api.github.com/repos/{REPO}/pulls/{number}", token)
        if not okp:
            return [], f"gh 失敗（{gh_err}）・PR #{number} の詳細取得に失敗（{outp}）"
        try:
            pr = json.loads(outp)
        except json.JSONDecodeError:
            return [], f"gh 失敗（{gh_err}）・PR #{number} 応答のパースに失敗"
        sha = pr.get("merge_commit_sha")
        if sha:
            shas.append(sha)
    return shas, None


def is_ancestor_of_main(sha: str) -> bool | None:
    """`sha` が `origin/main` の祖先かどうかを git で判定する（判定不能なら None）。

    まず `origin/main` を明示 refspec で fetch してから判定する（`session-safety-rules.md`
    G-1 と同じパターン。ローカルの参照が古いままだと未反映を誤って「祖先」と判定しうる）。
    """
    try:
        fetch = subprocess.run(
            ["git", "fetch", "origin", "+main:refs/remotes/origin/main"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if fetch.returncode != 0:
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
) -> bool | None:
    """Issue タイトルから対応するスプリント PR を探し、main へ反映済みかを判定する。

    Returns:
        True  = 反映済み（merge commit が origin/main の祖先）
        False = 未反映と確定できた（該当 merged PR が無い、またはどれも祖先でない）
        None  = 判定不能（SP-n がタイトルに無い・PR 検索/取得の失敗・git 判定の失敗）。
                fail-closed のため呼び出し側は None を「反映済み」と同様に扱うこと。

    `fetch_fn` / `ancestor_fn` はテスト用の差し替えポイント（既定は実際の gh/git 呼び出し）。
    """
    m = SPRINT_ID_RE.search(issue_title)
    if not m:
        return None
    sprint_id = m.group(0)
    shas, err = fetch_fn(sprint_id)
    if err is not None:
        return None
    if not shas:
        return False
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
    """#471: is_merged_into_main の純ロジック（fetch_fn / ancestor_fn を注入して検証）。

    入力バリアント: ① タイトルに SP-n が無い ② PR が紐付いていない（0 件）
    ③ 複数 PR が紐付き 1 件が main の祖先 ④ merged だが main に無い（squash 後の SHA 差異等）
    ⑤ PR がまだ open のまま（merged 検索でヒットしない = shas 0 件と同じ経路）
    ⑥ PR 検索/取得 API が失敗 ⑦ git 祖先判定が失敗（判定不能）
    """
    failures = []

    def make(shas=None, err=None, ancestor_results=None):
        shas = shas if shas is not None else []
        ancestor_results = ancestor_results or {}

        def fetch_fn(sprint_id):
            return shas, err

        def ancestor_fn(sha):
            return ancestor_results.get(sha, False)

        return fetch_fn, ancestor_fn

    # ① タイトルに SP-n が無い（Sprint Planning コメントのみでスプリント判定された Issue）
    #    → 対応する PR を機械的に特定できない → 判定不能（None・fail-closed）
    fetch_fn, ancestor_fn = make()
    r = is_merged_into_main("改善: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn)
    if r is not None:
        failures.append(f"is_merged_into_main: SP-n の無いタイトルは None（判定不能）を期待したが {r}")

    # ② 紐付く merged PR が 0 件（＝ PR がまだ open のまま、と同じ経路）→ 未マージ確定（False）
    fetch_fn, ancestor_fn = make(shas=[])
    r = is_merged_into_main("SP-7: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn)
    if r is not False:
        failures.append(f"is_merged_into_main: merged PR 0 件（open のまま含む）は False を期待したが {r}")

    # ③ 複数 PR が紐付き、うち 1 件の merge commit が main の祖先 → True
    fetch_fn, ancestor_fn = make(
        shas=["aaa", "bbb"], ancestor_results={"aaa": False, "bbb": True}
    )
    r = is_merged_into_main("SP-8: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn)
    if r is not True:
        failures.append(f"is_merged_into_main: 複数 PR の 1 件が祖先なら True を期待したが {r}")

    # ④ merged PR はあるが、その merge commit が main の祖先ではない
    #    （squash 後に revert された・SHA が一致しない等）→ 未マージ扱い（False）
    fetch_fn, ancestor_fn = make(shas=["ccc"], ancestor_results={"ccc": False})
    r = is_merged_into_main("SP-9: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn)
    if r is not False:
        failures.append(f"is_merged_into_main: merged だが祖先でない場合は False を期待したが {r}")

    # ⑥ PR 検索/取得 API が失敗（err が返る）→ 判定不能（None・fail-closed）
    fetch_fn, ancestor_fn = make(shas=[], err="REST 応答のパースに失敗")
    r = is_merged_into_main("SP-10: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn)
    if r is not None:
        failures.append(f"is_merged_into_main: fetch 失敗は None（判定不能）を期待したが {r}")

    # ⑦ git 祖先判定が失敗（fetch 失敗・無効な SHA 等で ancestor_fn が None を返す）
    #    → 判定不能（None・fail-closed）。他の PR が明確に False でも None を優先する
    fetch_fn, ancestor_fn = make(shas=["ddd", "eee"], ancestor_results={"ddd": False, "eee": None})
    r = is_merged_into_main("SP-11: 何か", fetch_fn=fetch_fn, ancestor_fn=ancestor_fn)
    if r is not None:
        failures.append(f"is_merged_into_main: git 判定不能を含む場合は None を期待したが {r}")

    return failures


def _self_test_is_ancestor_of_main() -> list[str]:
    """is_ancestor_of_main を実際に呼び出し、`subprocess.run` をモック差し替えして
    returncode 0/1/その他（128 等）→ True/False/None の写像をエントリポイントから
    実測する（#474「テストの到達範囲」: 上のロジック再実装ではなく実関数を通す）。
    """
    failures = []
    import subprocess as _subprocess_module
    import types

    real_run = _subprocess_module.run

    def fake_run_factory(fetch_returncode: int, merge_base_returncode: int):
        def fake_run(args, **kwargs):
            if args[:2] == ["git", "fetch"]:
                return types.SimpleNamespace(returncode=fetch_returncode, stdout="", stderr="")
            if args[:2] == ["git", "merge-base"]:
                return types.SimpleNamespace(returncode=merge_base_returncode, stdout="", stderr="")
            raise AssertionError(f"想定外の subprocess.run 呼び出し: {args}")
        return fake_run

    cases = [
        (0, 0, True),    # fetch 成功・祖先である
        (0, 1, False),   # fetch 成功・祖先でない
        (0, 128, None),  # fetch 成功・merge-base が異常終了（無効な SHA 等）→ 判定不能
        (1, 0, None),    # fetch 自体が失敗 → 判定不能（merge-base を呼ぶ前に打ち切る）
    ]
    try:
        for fetch_rc, merge_base_rc, expected in cases:
            _subprocess_module.run = fake_run_factory(fetch_rc, merge_base_rc)
            got = is_ancestor_of_main("deadbeef")
            if got != expected:
                failures.append(
                    f"is_ancestor_of_main(fetch_rc={fetch_rc}, merge_base_rc={merge_base_rc}): "
                    f"{expected!r} を期待したが {got!r}"
                )
    finally:
        _subprocess_module.run = real_run

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


def run_self_test() -> int:
    groups = [
        ("スプリント対象判定", _self_test_is_sprint_issue),
        ("判定コメントのパース（accepted_with_conditions 優先）", _self_test_verdict_result_re),
        ("最新判定の優先順位", _self_test_latest_verdict_order),
        ("判定コメントの投稿者権限検証", _self_test_verdict_author_guard),
        ("Issue 単位のゲート判定", _self_test_evaluate_issue),
        ("main 反映判定の統合（#471）", _self_test_merged_check_integration),
        ("main 反映判定の純ロジック（#471）", _self_test_is_merged_into_main),
        ("main 祖先判定（git 呼び出しのモック差し替え・#471）", _self_test_is_ancestor_of_main),
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
