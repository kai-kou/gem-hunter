#!/usr/bin/env python3
"""レビュー待ちPRを検出し、セッション復帰時に対応を再開するためのスクリプト。

クラウド環境（Claude.ai Scheduled Tasks）ではセッションタイムアウトが頻発する。
PR作成後のAIレビュー待ち（sleep ポーリング）中にセッションが切れると、
レビュー対応が宙に浮く。本スクリプトはセッション開始時やスケジューラーから
呼び出され、対応が必要なPRを検出する。

レビュー構成（飼い主決定）:
  外部 AI レビュアー（Copilot / Gemini）への依頼は廃止。レビューは Claude 自身が
  Layer 1 セルフレビュー（自前 code-review スキル・Skill(code-review)）で完結する。組み込み
  /code-review は disable-model-invocation で自律起動不可のため、同名 project スキル
  .claude/skills/code-review/ が bundled を置換している（#275 → #280）。
  本スクリプトは Layer 1 を機械検出できないため、未解決スレッドの
  有無と経過時間でセッション復帰時の対応を決める。SSOT: docs/rules/ai-reviewer-strategy.md

検出条件:
  1. Open状態のPR（kai-kou/gem-hunter）
  2. Claude 作業ブランチ（claude/ feat/ fix/ docs/ 等）**かつ著者が OWNER/MEMBER/COLLABORATOR**
     （authorAssociation・#379）の PR、または未解決スレッドのある PR
  3. 指摘対応 or Layer 1 セルフレビューが未完了

著者検証（#379・公開リスク監査 r03 critical）:
  _is_claude_branch() はブランチ名の前方一致だけでなく、gh --json authorAssociation を
  AND 条件に加える。fork PR は通常 CONTRIBUTOR 以下になるため、規約どおりの命名
  （feat/ fix/ docs/ 等）で fork から PR を出しても needs_prompt（自動マージ対象）にならない。
  authorAssociation が取得できない場合は安全側（対象外）に倒す。
  gh 経路（実 gh・クラウドの gh_shim.py 双方）は REST の author_association から取得できるが、
  gh が全面失敗して呼び出し元が mcp__github__list_pull_requests に直接切り替える場合、
  同ツールには authorAssociation 相当のフィールドが存在しない（2026-08 実機確認）。
  その場合は mcp__github__list_repository_collaborators で信頼済みログイン集合を作り
  PR 著者（user.login）と突合するフォールバックを使う（docs/rules/github-mcp-fallback-patterns.md）。

出力:
  - PENDING:<pr_number>:<status>:<summary>
  - status: needs_response（未解決スレッドあり = CI 失敗・人手コメント・履歴上のボット指摘 → 指摘対応）
            needs_prompt（Layer 1 セルフレビュー要実施 → 観点別フレッシュ文脈レビュー実行 → 即マージ）
            awaiting_review（PR 作成直後 = 作成セッションがセルフレビュー実行中 → 待機）
            blocked_waiting_user（status:waiting-user ラベル付き → 自動マージ対象外）
            blocked_circuit_breaker（status:blocked ラベル付き → A-4 発動済み・Step 2/3 の対象外・#746）
            no_action（Claude 以外の PR または手動 PR）
  ※ 外部レビュアーの 25 分応答待ち・催促・問題なし判定タイムアウトは廃止。

gh 取得失敗時（クラウドの 403 等・Issue #130・#789）:
  クラウド実行環境には `gh` がプリインストールされていないため、多くの firing で
  `gh pr list` 等が即座に失敗する（L-114）。本スクリプトは 2 層フォールバックを持つ:
    第 1 層: `gh` CLI（ローカル実行時はここで完結）
    第 2 層: `urllib` + `GH_TOKEN` / `GITHUB_TOKEN` による GitHub REST 直叩き
             （`_run_gh_raw` → 失敗 → 各 `get_*` 内の REST フォールバックへ自動移行）
  両層とも失敗した場合のみ「0 件」と沈黙せず、stderr に `ERROR: gh_unavailable: ...`、
  stdout に `GH_UNAVAILABLE: ...` を出力して **exit code 3** で終了する（PR 一覧取得の場合）。
  呼び出し元は exit code を確認し、3 の場合は `mcp__github__list_pull_requests` で直接代替すること
  （PR ごとの補助情報取得の失敗は従来どおり部分的な情報欠落として許容し、全体を失敗にはしない）。
  なお `get_unresolved_threads`（GraphQL 専用）は REST に等価エンドポイントが無いため
  第 2 層フォールバックの対象外。gh 到達不可時は件数を 0 件へ黙って化けさせず、戻り値の
  2 つ目の要素（取得成功可否）で「未検証」を呼び出し元へ機械可読に伝える。`analyze_pr` は
  これを `unresolved_threads_unknown` として JSON 出力へ載せ、summary の先頭に
  「⚠️ 未解決スレッド数は未検証」の警告を差し込む（status 判定自体は変えない・#790 指摘1）。

アクティブセッション除外（CP-4・Issue #3007）:
  各 PR について「人間側（Claude セッション）の最終アクティビティ」
  （PR 作成・head ブランチへのコミット・非ボットコメント）からの経過分を
  last_activity_min として算出する。直近 ACTIVE_WINDOW_MIN 分以内に活動が
  ある PR は active_session=true となり、--actionable-only から除外される
  （作成セッションが現役で対応中の PR に他セッションが介入しない）。
  活動が途絶えた PR は従来どおり救済対象（CP-3 維持）。
  作成セッション自身のハートビート（--json + PR 番号フィルタ）は status を
  そのまま参照するため影響を受けない。

アイデンティティベース所有判定（CP-4・#47）:
  各 PR 本文の `Session-Id: {UUID}` トレーラー（session-sprint-rules.md §2 で必須化）を
  owner_session_id として解析し、現セッション（$CLAUDE_CODE_SESSION_ID）と一致するかを
  is_mine で返す。--mine を付けると「自セッションが作成した PR のみ」を決定論的に出力する
  （他セッションの PR は触れない）。自 PR は所有者本人なので active_session（時間ベース）の
  除外を適用しない＝10 分超アイドルやセッション再起動・圧縮後でも自 PR を見失わず責任継続できる。
  これが「自セッション作成 PR のみマージまで進める」積極的所有判定（時間ベースのレイヤー 5 を補完）。

Usage:
    python3 tools/check_pending_pr_reviews.py
    python3 tools/check_pending_pr_reviews.py --json
    python3 tools/check_pending_pr_reviews.py --actionable-only --include-active
    python3 tools/check_pending_pr_reviews.py --mine --json            # 自セッション所有 PR のみ
    python3 tools/check_pending_pr_reviews.py --mine --actionable-only # 自 PR で要対応のもの
    python3 tools/check_pending_pr_reviews.py --self-test              # Session-Id 解析テスト
    python3 tools/check_pending_pr_reviews.py --verify-layer1 <PR番号> # Layer 1 投稿済みか機械検証（base#462）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_slug import repo_from_git_remote as _repo_from_git_remote  # noqa: E402


class GhUnavailableError(RuntimeError):
    """gh CLI の repo スコープ操作が失敗した（クラウドの 403 等）ことを示す。

    「取得できたが 0 件」と「取得自体に失敗した」を区別するために使う（Issue #130・L-074/L-086）。
    このエラーを握りつぶして空リスト扱いすると、クラウドで常に「レビュー待ち PR 0 件」という
    誤判定が沈黙して発生する。
    """


# owner/repo 解決ロジックの正本は tools/repo_slug.py（#215）。
# 本リポジトリ自身（bootstrap 未適用）に対して運用ルーティンを回すケース（R-1・#213/#220）では
# プレースホルダが未置換のまま残るため、その場合のみ _repo_from_git_remote() で動的に補う。


_REPO_PLACEHOLDER = "kai-kou/gem-hunter"
# owner / name を REPO から動的導出する（GraphQL クエリ等でハードコードしない）。
# bootstrap.sh が REPO の kai-kou/gem-hunter を置換すれば OWNER/REPO_NAME も追従する。
if "__" in _REPO_PLACEHOLDER:
    # プレースホルダ未置換（本リポジトリの自己ホスト実行等） → git remote から動的補完
    REPO = _repo_from_git_remote() or _REPO_PLACEHOLDER
else:
    # bootstrap.sh 済み（下流リポジトリ） → git 呼び出し不要、既存の決定論的動作を維持
    REPO = _REPO_PLACEHOLDER
OWNER, _, REPO_NAME = REPO.partition("/")
# 形式不正（owner / name のどちらか欠落・bootstrap 未実行のプレースホルダ残存）のまま
# GitHub API を叩くと別リポジトリを参照したり取得失敗を 0 件扱いして誤判定するため、
# API を実際に使う前（main() 冒頭・ただし API 非依存の --self-test は除く）に明示的に失敗させる
# （Copilot review・誤 ready_to_merge 防止）。純粋関数（parse_session_id 等）の self-test は
# プレースホルダのままのテンプレートリポジトリでも実行できるよう、検証は関数化して遅延する。
def _validate_repo() -> None:
    # プレースホルダ検出は "__" の部分一致で行う（tools/repo_slug.py と同方式）。
    # "kai-kou" 等の完全一致リテラルを書くと bootstrap.sh の全域 sed がこの判定文字列
    # 自体を実値に置換してしまい、置換成功後もガードが常時発火する（exit 2）ため。
    if not OWNER or not REPO_NAME or "__" in REPO:
        print(
            f"ERROR: REPO の形式が不正です: '{REPO}'（owner/name 形式が必要。"
            "bootstrap.sh でプレースホルダを置換してください）",
            file=sys.stderr,
        )
        sys.exit(2)


GEMINI_BOT = "gemini-code-assist[bot]"
COPILOT_BOTS = {"copilot[bot]", "copilot-pull-request-reviewer[bot]"}
AI_REVIEWERS = {GEMINI_BOT} | COPILOT_BOTS

# Gemini Code Assist 消費者版は 2026-07-17 に code review activity 完全停止（#2485）。
# 同日以降は Gemini を必須から外し、Copilot 単独完了（+ 恒久構成 Claude /code-review）で
# 即時マージ可能にする。これがないと has_gemini_review が常に False になり全 PR が25分遅延する。
# 恒久構成の正本: docs/rules/ai-reviewer-strategy.md
GEMINI_SUNSET_DATE = datetime(2026, 7, 17, tzinfo=timezone.utc)

# 直近この分数以内に人間側アクティビティがある PR は「作成セッションが現役」と
# みなし、他セッション（--actionable-only 利用者）は介入しない（CP-4・Issue #3007）。
# 活動途絶後はこの分数の遅延だけで従来どおり救済される（CP-3 とのバランス点）。
ACTIVE_WINDOW_MIN = 10

# アイデンティティベース所有判定（CP-4・#47）。
# PR 本文の `Session-Id: {UUID}` トレーラー（session-sprint-rules.md §2 で必須化）を
# 所有権の権威ソースとして解析する。これにより「自セッションが作成した PR のみ」を
# 決定論的に識別でき、時間ベースの active_session（レイヤー 5）の穴
# （①自 PR でも 10 分超アイドルで奪われる ②セッション再起動・圧縮後に自 PR を見失う）を埋める。
# sprint_session_metrics.py の SESSION_ID_RE と同一パターン（UUID 形式・大文字小文字不問）。
SESSION_ID_RE = re.compile(
    # dup-ok: sprint_session_metrics.py の SESSION_ID_RE と同一パターン。統合は Issue #612 のスコープ外
    r"Session-Id:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)


def parse_session_id(body: str | None) -> str:
    """PR 本文から `Session-Id:` トレーラーの UUID を抽出する（小文字正規化）。

    トレーラー不在・形式不正の場合は空文字を返す（時間窓フォールバックに委ねる）。
    純粋関数（API 非依存）のため --self-test で検証する。
    """
    if not body:
        return ""
    m = SESSION_ID_RE.search(body)
    return m.group(1).lower() if m else ""


def current_session_id(explicit: str | None = None) -> str:
    """現セッションの ID を返す。--session-id 明示指定 > $CLAUDE_CODE_SESSION_ID。"""
    if explicit:
        return explicit.strip().lower()
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip().lower()


def _gemini_sunset() -> bool:
    """Gemini Code Assist 停止日（2026-07-17 UTC）以降なら True。"""
    return datetime.now(timezone.utc) >= GEMINI_SUNSET_DATE


def _run_gh_raw(args: list[str]) -> tuple[bool, str]:
    """gh CLI コマンドの最下層実行（第 1 層）。例外を投げず (成功可否, stdout/理由) を返す。

    クラウド実行環境には `gh` がプリインストールされておらず、PATH にシムも無い構成がある
    （CLAUDE.md「gh CLI / GitHub 操作」・L-114）。ここで素の例外を投げると呼び出し元まで
    トレースバックで抜け、終了コード 1 = LAYER1_MISSING と区別できなくなる（＝誤ブロック）ため、
    失敗はすべて (False, 理由) として返し、上位（`run_gh`）に判断させる。
    """
    cmd = ["gh"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as e:
        return False, f"gh コマンドが見つかりません（{e.__class__.__name__}）"
    except subprocess.TimeoutExpired as e:
        return False, f"gh コマンドがタイムアウトしました（{e.__class__.__name__}）"
    if result.returncode != 0:
        stderr_msg = result.stderr.strip()
        return False, stderr_msg or f"gh command failed: {' '.join(cmd)}"
    return True, result.stdout.strip()


def _get_gh_token() -> str:
    """第 2 層（REST）で使う GitHub トークンを環境変数から取得する。ログには絶対に出さない。"""
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def _token_gated(fn, *args) -> tuple[bool, str]:
    """token 取得 → 未設定なら早期失敗、取得できれば fn(*args, token) を呼ぶ（第 2 層の共通ガード）。

    「トークン未取得なら (False, 'GH_TOKEN/GITHUB_TOKEN 未設定') を返す」というガードが
    8 箇所の `_fallback` クロージャへコピペされていたのを畳んだ共通ヘルパー（#790 指摘4）。
    各 `get_*` 関数の `rest_fallback=` は `lambda: _token_gated(_rest_xxx, ...固有引数)` の
    1 行に置き換える。
    """
    token = _get_gh_token()
    if not token:
        return False, "GH_TOKEN/GITHUB_TOKEN 未設定"
    return fn(*args, token)


def _http_get(url: str, token: str) -> tuple[bool, str]:
    """GitHub REST を GET する（第 2 層）。

    token をサブプロセス引数に載せず Python プロセス内でヘッダを組み立てる
    （`ps` / `/proc/<pid>/cmdline` 経由の露出防止。`tools/check_deploy_gate.py` の既存パターンを踏襲）。
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gem-hunter-check-pending-pr-reviews",
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


def _rest_get_all_pages(path: str, query: str, token: str, max_pages: int = 5) -> tuple[bool, list | str]:
    """REST の GET を `per_page=100` でページネーションし、JSON 配列を全て結合する（第 2 層）。

    Issue #602 が扱う共通ページネーションモジュール化のスコープには入らない、本ファイル内に
    閉じた最小実装（YAGNI）。取りこぼしが「0 件」に化けないよう、返却件数が 100 件ちょうどの間は
    次ページを取り続ける。戻り値は (成功, 結合済みリスト) または (失敗, エラー理由の文字列)。

    🔴 `max_pages` に到達した時点でも最終ページがちょうど 100 件（＝まだ続きがある可能性を
    否定できない）なら、黙って成功扱いにせず `(False, 理由)` を返す（#790 指摘3）。REST は
    作成日時昇順で返すため、この打ち切りを fail-open で見逃すと 301 件超の PR で**最新の**
    レビュー/コメントが切り捨てられ、`verify_layer1_review` が現行コミットへのレビューを
    見つけられず `LAYER1_MISSING` と誤判定する。`critical=True` の呼び出しはそのまま
    `GhUnavailableError` に倒れる（fail-closed 方針と一致）。
    """
    items: list = []
    truncated = False
    for page in range(1, max_pages + 1):
        sep = "&" if query else ""
        url = f"https://api.github.com/repos/{REPO}/{path}?{query}{sep}per_page=100&page={page}"
        ok, out = _http_get(url, token)
        if not ok:
            return False, out
        try:
            batch = json.loads(out)
        except json.JSONDecodeError:
            return False, "REST 応答の JSON 解析に失敗"
        if not isinstance(batch, list):
            return False, "REST 応答が配列ではありません"
        items.extend(batch)
        if len(batch) < 100:
            break
        if page == max_pages:
            truncated = True
    if truncated:
        return False, "ページ数上限に到達（取得しきれていない可能性）"
    return True, items


def run_gh(args: list[str], critical: bool = False, rest_fallback=None) -> str:
    """gh CLI コマンドを実行して stdout を返す（多段フォールバック・#789）。

    第 1 層: `gh` CLI（`_run_gh_raw`）。失敗したら第 2 層 `rest_fallback`（渡された場合）を試す。
    `rest_fallback` は引数を取らない `() -> tuple[bool, str]` で、成功時は gh の `--jq` 出力と
    同じ形の JSON 文字列（または該当 API のプレーン文字列出力）を返すこと。

    両層とも失敗した場合、`critical=True` の呼び出しは空文字列を返さず `GhUnavailableError` を
    送出する（クラウドで gh が使えず REST も失敗する場合、呼び出し元が「0 件」と誤判定しない
    ようにするため）。補助的な取得（PR ごとのレビュー/コメント等）は `critical=False`（既定）の
    まま、部分的な情報欠落として空リストにフォールバックしてよい（ただし stderr には必ず警告を残す）。
    """
    cmd = ["gh"] + args
    gh_ok, gh_out = _run_gh_raw(args)
    if gh_ok:
        return gh_out
    print(f"WARNING: gh command failed: {' '.join(cmd)}", file=sys.stderr)
    print(f"  stderr: {gh_out}", file=sys.stderr)

    if rest_fallback is not None:
        try:
            rest_ok, rest_out = rest_fallback()
        except Exception as e:  # noqa: BLE001 — REST フォールバック内の想定外失敗も gh 失敗と同列に扱う
            rest_ok, rest_out = False, f"{e.__class__.__name__}: {e}"
        if rest_ok:
            return rest_out
        print(f"WARNING: REST フォールバックも失敗しました: {rest_out}", file=sys.stderr)
        combined_reason = f"gh失敗（{gh_out}）・REST失敗（{rest_out}）"
    else:
        combined_reason = gh_out

    if critical:
        raise GhUnavailableError(combined_reason)
    return ""


def _transform_rest_pr(raw: dict) -> dict:
    """REST `/pulls` の 1 件を gh `pr list --json` のスキーマ（camelCase）へ変換する（純粋関数・#789）。

    呼び出し元（`analyze_pr` 等）は gh スキーマ前提で書かれているため、変換層でスキーマを揃える
    のが最小侵襲（gh 側のフィールド名: createdAt / headRefName / authorAssociation /
    isCrossRepository / labels=[{name}] / author={login} / reviewRequests）。
    """
    head = raw.get("head") or {}
    head_repo = head.get("repo")
    if head_repo is not None:
        is_cross: bool | None = head_repo.get("full_name") != REPO
    else:
        # head リポジトリが取得できない（削除済み等） → fork かどうか不明。fail-closed で None にし、
        # 下流の _is_automation_pr / _is_dependabot_pr が None を「取得不能」として弾く。
        is_cross = None
    user = raw.get("user") or {}
    requested_users = raw.get("requested_reviewers") or []
    requested_teams = raw.get("requested_teams") or []
    review_requests = (
        [{"login": u.get("login", "")} for u in requested_users]
        + [{"name": t.get("name", "")} for t in requested_teams]
    )
    labels = [{"name": lbl.get("name", "")} for lbl in (raw.get("labels") or [])]
    return {
        "number": raw.get("number"),
        "title": raw.get("title", ""),
        "createdAt": raw.get("created_at", ""),
        "headRefName": head.get("ref", ""),
        "author": {"login": user.get("login", "")},
        "authorAssociation": raw.get("author_association", ""),
        "reviewRequests": review_requests,
        "labels": labels,
        "body": raw.get("body") or "",
        "isCrossRepository": is_cross,
    }


def _rest_open_prs(token: str) -> tuple[bool, str]:
    """`gh pr list --state open` の REST 版（第 2 層）。gh スキーマへ変換した JSON 文字列を返す。"""
    ok, items = _rest_get_all_pages("pulls", "state=open", token, max_pages=5)
    if not ok:
        return False, items  # items はこの分岐では理由文字列
    prs = [_transform_rest_pr(pr) for pr in items]
    return True, json.dumps(prs)


def get_open_prs() -> list[dict]:
    """Open状態のPR一覧を取得する。

    gh・REST 両層の失敗（クラウドの 403 等）は `GhUnavailableError` として呼び出し元に伝播する
    （「取得失敗」と「取得できたが 0 件」を混同しないため・Issue #130 / #789）。
    """
    output = run_gh([
        "pr", "list",
        "-R", REPO,
        "--state", "open",
        "--limit", "100",
        "--json", "number,title,createdAt,headRefName,author,authorAssociation,reviewRequests,labels,body,isCrossRepository",
    ], critical=True, rest_fallback=lambda: _token_gated(_rest_open_prs))
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        print("WARNING: Failed to parse PR list JSON", file=sys.stderr)
        return []


def get_pr_reviews(pr_number: int, critical: bool = False) -> list[dict]:
    """PRのレビュー一覧を取得する。

    `critical=True` は gh 到達不可（コマンド失敗・JSON 破損とも）を `GhUnavailableError` として
    呼び出し元に伝播する（`verify_layer1_review` が「レビュー0件」と「gh失敗による空リスト」を
    区別するために使う）。`commit_id` はレビュー投稿時点の PR head SHA（force-push 後の
    古いレビューを「最新コミットに対する実施」と誤認しないための判定材料・base#462）。
    """
    output = run_gh([
        "api", f"repos/{REPO}/pulls/{pr_number}/reviews",
        "--jq", '[.[] | {user: .user.login, state, submitted_at, body_len: (.body | length), commit_id}]',
    ], critical=critical, rest_fallback=lambda: _token_gated(_rest_pr_reviews, pr_number))
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        if critical:
            raise GhUnavailableError(f"reviews JSON 解析失敗: {e}") from e
        return []


def _rest_pr_reviews(pr_number: int, token: str) -> tuple[bool, str]:
    """`gh api pulls/{n}/reviews --jq` の REST 版（第 2 層）。"""
    ok, items = _rest_get_all_pages(f"pulls/{pr_number}/reviews", "", token, max_pages=3)
    if not ok:
        return False, items
    out = [
        {
            "user": (r.get("user") or {}).get("login", ""),
            "state": r.get("state", ""),
            "submitted_at": r.get("submitted_at", ""),
            "body_len": len(r.get("body") or ""),
            "commit_id": r.get("commit_id", ""),
        }
        for r in items
    ]
    return True, json.dumps(out)


def get_pr_comments(pr_number: int, critical: bool = False) -> list[dict]:
    """PRのインラインコメント一覧を取得する。

    `critical` / `commit_id` の意味は `get_pr_reviews` と同じ。
    """
    output = run_gh([
        "api", f"repos/{REPO}/pulls/{pr_number}/comments",
        "--jq", '[.[] | {user: .user.login, created_at, body_len: (.body | length), path, commit_id}]',
    ], critical=critical, rest_fallback=lambda: _token_gated(_rest_pr_comments, pr_number))
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        if critical:
            raise GhUnavailableError(f"comments JSON 解析失敗: {e}") from e
        return []


def _rest_pr_comments(pr_number: int, token: str) -> tuple[bool, str]:
    """`gh api pulls/{n}/comments --jq` の REST 版（第 2 層）。"""
    ok, items = _rest_get_all_pages(f"pulls/{pr_number}/comments", "", token, max_pages=3)
    if not ok:
        return False, items
    out = [
        {
            "user": (c.get("user") or {}).get("login", ""),
            "created_at": c.get("created_at", ""),
            "body_len": len(c.get("body") or ""),
            "path": c.get("path", ""),
            "commit_id": c.get("commit_id", ""),
        }
        for c in items
    ]
    return True, json.dumps(out)


_GEMINI_TRIGGER_RE = re.compile(r"/gemini review", re.I)


def _rest_issue_comments_raw(pr_number: int, token: str) -> tuple[bool, list | str]:
    """`issues/{n}/comments` の生 REST 応答（変換前）を取得する共通下請け（第 2 層）。"""
    return _rest_get_all_pages(f"issues/{pr_number}/comments", "", token, max_pages=3)


def _rest_comment_is_bot(user: dict) -> bool:
    """REST の issue コメント `user` オブジェクトからボット判定する（純粋関数）。

    gh api の jq 式 `.user.type == "Bot" or (.user.login | test("copilot|gemini"; "i"))` と
    同じ判定基準を Python 側で再現する。
    """
    login = (user.get("login") or "").lower()
    user_type = user.get("type") or ""
    return user_type == "Bot" or "copilot" in login or "gemini" in login


def _rest_gemini_trigger_comments(pr_number: int, token: str) -> tuple[bool, str]:
    """`/gemini review` コマンドを含む issue コメントの REST 版（第 2 層）。"""
    ok, items = _rest_issue_comments_raw(pr_number, token)
    if not ok:
        return False, items
    out = [
        {
            "user": (c.get("user") or {}).get("login", ""),
            "created_at": c.get("created_at", ""),
            "body": (c.get("body") or "")[:200],
        }
        for c in items
        if _GEMINI_TRIGGER_RE.search(c.get("body") or "")
    ]
    return True, json.dumps(out)


def get_pr_gemini_trigger_comments(pr_number: int) -> list[dict]:
    """/gemini review コマンドを含むコメントを取得する（投稿者種別不問）。"""
    output = run_gh([
        "api", f"repos/{REPO}/issues/{pr_number}/comments",
        "--jq", '[.[] | select(.body | test("/gemini review"; "i")) | {user: .user.login, created_at, body: (.body | .[0:200])}]',
    ], rest_fallback=lambda: _token_gated(_rest_gemini_trigger_comments, pr_number))
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def _rest_bot_issue_comments(pr_number: int, token: str) -> tuple[bool, str]:
    """ボットの issue コメント（一般コメント）の REST 版（第 2 層）。"""
    ok, items = _rest_issue_comments_raw(pr_number, token)
    if not ok:
        return False, items
    out = [
        {
            "user": (c.get("user") or {}).get("login", ""),
            "created_at": c.get("created_at", ""),
            "body_len": len(c.get("body") or ""),
            "body": (c.get("body") or "")[:500],
        }
        for c in items
        if _rest_comment_is_bot(c.get("user") or {})
    ]
    return True, json.dumps(out)


def get_pr_issue_comments(pr_number: int) -> list[dict]:
    """PRの一般コメント（ボットのみ）を取得する。"""
    output = run_gh([
        "api", f"repos/{REPO}/issues/{pr_number}/comments",
        "--jq", '[.[] | select(.user.type == "Bot" or (.user.login | test("copilot|gemini"; "i"))) | {user: .user.login, created_at, body_len: (.body | length), body: (.body // "" | .[0:500])}]',
    ], rest_fallback=lambda: _token_gated(_rest_bot_issue_comments, pr_number))
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def get_branch_last_commit_time(branch: str) -> str:
    """head ブランチの最新コミット時刻（committer date・ISO8601）を返す。取得失敗時は空文字。

    注意: gh api は `-f` フィールド指定があるとデフォルトメソッドが POST に切り替わるため、
    `--method GET` の明示が必須（省略すると POST /commits → 404 で常に空文字となり、
    ブランチコミットによるアクティビティ検知が無効化される）。
    """
    if not branch:
        return ""

    output = run_gh([
        "api", "--method", "GET", f"repos/{REPO}/commits",
        "-f", f"sha={branch}",
        "-f", "per_page=1",
        "--jq", '.[0]?.commit.committer.date // ""',
    ], rest_fallback=lambda: _token_gated(_rest_branch_last_commit_time, branch))
    return output.strip()


def _rest_branch_last_commit_time(branch: str, token: str) -> tuple[bool, str]:
    """head ブランチの最新コミット時刻の REST 版（第 2 層）。"""
    url = (
        f"https://api.github.com/repos/{REPO}/commits"
        f"?sha={urllib.parse.quote(branch, safe='')}&per_page=1"
    )
    ok, out = _http_get(url, token)
    if not ok:
        return False, out
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return False, "REST 応答の JSON 解析に失敗"
    if not data:
        return True, ""
    date = ((data[0].get("commit") or {}).get("committer") or {}).get("date", "")
    return True, date


def _filter_human_comment_times(comments: list[dict]) -> list[str]:
    """`{login, type, created_at}` 辞書列から非ボットの `created_at` のみを抽出する（純粋関数）。

    gh api 経路・REST フォールバック経路のどちらのソースも同じ形状の辞書列を生成するため、
    ボット判定フィルタはこの 1 箇所に統一する（③-b の self-test 対象）。
    """
    times: list[str] = []
    for c in comments:
        login = (c.get("login") or "").lower()
        user_type = c.get("type") or ""
        is_bot = (
            user_type == "Bot"
            or "copilot" in login
            or "gemini" in login
            or login.endswith("[bot]")
        )
        if not is_bot:
            times.append(c.get("created_at", ""))
    return times


def _rest_human_comment_times_raw(pr_number: int, token: str) -> tuple[bool, str]:
    """PR の issue コメント（ボット判定用の login/type 付き）の REST 版（第 2 層）。"""
    ok, items = _rest_issue_comments_raw(pr_number, token)
    if not ok:
        return False, items
    out = [
        {
            "login": (c.get("user") or {}).get("login", ""),
            "type": (c.get("user") or {}).get("type", ""),
            "created_at": c.get("created_at", ""),
        }
        for c in items
    ]
    return True, json.dumps(out)


def get_pr_human_comment_times(pr_number: int) -> list[str]:
    """PR の非ボット（人間 / Claude セッション）issue コメント時刻一覧を返す。"""
    output = run_gh([
        "api", f"repos/{REPO}/issues/{pr_number}/comments",
        "--jq", '[.[] | {login: .user.login, type: (.user.type // ""), created_at}]',
    ], rest_fallback=lambda: _token_gated(_rest_human_comment_times_raw, pr_number))
    if not output:
        return []
    try:
        comments = json.loads(output)
    except json.JSONDecodeError:
        return []
    return _filter_human_comment_times(comments)


def _parse_iso(ts: str) -> datetime | None:
    """ISO8601 文字列を datetime に変換する。失敗時は None。"""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_last_activity_min(
    pr: dict,
    inline_comments: list[dict],
    human_comment_times: list[str] | None = None,
) -> int:
    """人間側（Claude セッション）の最終アクティビティからの経過分を算出する（Issue #3007）。

    アクティビティ源:
      - PR 作成時刻
      - head ブランチの最新コミット時刻（指摘対応中のコミットを検知）
      - 非ボットの issue コメント時刻
      - 非ボットのインラインレビューコメント時刻（スレッド返信を検知）

    human_comment_times: 事前取得済みの非ボットコメント時刻リスト。
      None の場合は内部で API を呼ぶ（後方互換）。
      analyze_pr() からは重複呼び出し削減のため事前取得値を渡すこと。
    """
    candidates: list[datetime] = []
    created = _parse_iso(pr.get("createdAt", ""))
    if created:
        candidates.append(created)
    branch_commit = _parse_iso(get_branch_last_commit_time(pr.get("headRefName", "")))
    if branch_commit:
        candidates.append(branch_commit)
    times = human_comment_times if human_comment_times is not None else get_pr_human_comment_times(pr["number"])
    for ts in times:
        parsed = _parse_iso(ts)
        if parsed:
            candidates.append(parsed)
    for c in inline_comments:
        login = (c.get("user", "") or "").lower()
        is_bot = login.endswith("[bot]") or "copilot" in login or "gemini" in login
        if not is_bot:
            parsed = _parse_iso(c.get("created_at", ""))
            if parsed:
                candidates.append(parsed)
    if not candidates:
        return 9999
    elapsed = datetime.now(timezone.utc) - max(candidates)
    return max(0, int(elapsed.total_seconds() / 60))


def get_unresolved_threads(pr_number: int) -> tuple[int, bool]:
    """未解決のレビュースレッド数を取得する。戻り値は (件数, 取得成功可否)。

    🔴 GraphQL 専用（review thread の `isResolved` は REST に等価エンドポイントが無い・#789）。
    gh が使えない環境では REST フォールバックできない。以前は失敗時に黙って `0` を返しており、
    呼び出し元 `analyze_pr` はそれを「未解決スレッドなし」と区別できず fail-open していた
    （gh 到達不可時に本来 `needs_response` になるはずの PR が `needs_prompt` / `awaiting_review`
    に落ちて自動マージ対象へ紛れ込む・#790 指摘1）。戻り値の 2 つ目の要素で取得成功可否を
    機械可読に伝え、`analyze_pr` 側で `unresolved_threads_unknown` として可視化する
    （status 判定そのものは変えない — unknown を一律 needs_response に倒すと、gh 不在の
    クラウドでは全 PR が needs_response になり「Layer 1 未実施」の検知が効かなくなるため）。
    """
    query = """
    query {
      repository(owner: "%s", name: "%s") {
        pullRequest(number: %d) {
          reviewThreads(first: 100) {
            nodes { isResolved }
          }
        }
      }
    }
    """ % (OWNER, REPO_NAME, pr_number)
    gh_ok, gh_out = _run_gh_raw(["api", "graphql", "-f", f"query={query}"])
    if not gh_ok:
        print(
            f"WARNING: gh 到達不可のため未解決スレッド数を取得できません（{gh_out}）。"
            "review thread の解決状態は GitHub GraphQL 専用で REST に等価エンドポイントが無く、"
            "本スクリプトでは REST フォールバックできません（未検証として呼び出し元に伝えます。"
            "必要なら mcp__github__pull_request_read 等で個別に確認してください）。",
            file=sys.stderr,
        )
        return 0, False
    output = gh_out
    if not output:
        return 0, True
    try:
        data = json.loads(output)
        threads = data.get("data", {}).get("repository", {}).get("pullRequest", {}).get("reviewThreads", {}).get("nodes", [])
        return sum(1 for t in threads if not t.get("isResolved", True)), True
    except (json.JSONDecodeError, KeyError, TypeError):
        # JSON 破損・スキーマ想定外も「取得失敗」として扱う（0 件成功に化けさせない）
        return 0, False


def _label_based_early_exit_status(pr_labels: set[str]) -> dict | None:
    """ラベルだけで判定できる「actionable 対象外」の早期終了ステータスを返す（純粋関数・#746）。

    gh API を叩く前にラベル集合だけで判定できるため、I/O を伴わずテストできる。
    両方のラベルが同時に付いている場合は status:blocked を優先する
    （A-4 サーキットブレーカーは「これ以上の自動修正サイクルを止める」宣言であり、
    waiting-user 解除だけを理由に Step 2/3 が拾い直すのを防ぐため）。

    Issue #746: sprint-cycle-router §8 の A-4 行は「Step 3 / Step 4 / Step 5 の対象クエリから
    除外」とだけ書いており、本スクリプト（Step 2 の実装）には status:blocked の判定が
    一切実装されていなかった（waiting-user のみ）。この欠落が Step 2 の無人再取得を招いた。
    """
    if "status:blocked" in pr_labels:
        return {
            "status": "blocked_circuit_breaker",
            "summary": "status:blocked ラベル付き（A-4 サーキットブレーカー等発動済み・Step 2/3 の対象外・#746）",
        }
    if "status:waiting-user" in pr_labels:
        return {
            "status": "blocked_waiting_user",
            "summary": "status:waiting-user ラベル付き（ユーザー判断必須・自動マージ対象外）",
        }
    return None


# --actionable-only が除外するステータス集合（#746: main() と self-test で同じ定数を参照し、
# 新設した blocked_circuit_breaker が除外漏れにならないことを固定する）。
ACTIONABLE_EXCLUDED_STATUSES = {"no_action", "blocked_waiting_user", "blocked_circuit_breaker"}


def analyze_pr(pr: dict) -> dict:
    """PRのレビュー状態を分析する。"""
    pr_number = pr["number"]
    title = pr["title"]
    branch = pr.get("headRefName", "")
    created_at = pr.get("createdAt", "")
    pr_labels = {lbl.get("name", "") for lbl in pr.get("labels", [])}
    # アイデンティティベース所有判定（#47）: PR 本文の Session-Id トレーラーを抽出
    owner_session_id = parse_session_id(pr.get("body", ""))
    # 著者検証（#379・公開リスク監査 r03 critical）: ブランチ名だけでなく著者関係も見る
    author_association = pr.get("authorAssociation", "")
    # Issue #458: Gem Pool 週次リフレッシュ workflow が作る自動化 PR を認識するための追加情報。
    # `isCrossRepository` は gh pr list --json が返す真偽値（fork なら True）。フィールド自体が
    # 欠落する場合は None のままにし、_is_automation_pr() 側で fail-closed に倒す。
    author_login = (pr.get("author") or {}).get("login", "")
    is_cross_repository = pr.get("isCrossRepository")
    # PR #594: 信頼境界の bot 例外は 2 系統ある（gem-pool-refresh workflow と Dependabot）。
    # どちらも「fork 不可 + ブランチ条件 + 著者ログイン固定」の 3 条件 AND で、
    # `_is_trusted_author_association()` の許可集合自体は広げない（#379 の境界を保つ）。
    is_automation_pr = _is_automation_pr(branch, author_login, is_cross_repository)
    is_dependabot_pr = _is_dependabot_pr(branch, author_login, is_cross_repository)
    is_trusted_bot_pr = is_automation_pr or is_dependabot_pr

    # status:waiting-user / status:blocked ラベル付き PR は自動マージ対象から除外
    # （#2173・#746）。gh API 呼び出し前にラベルだけで判定できるため早期 return する。
    early_exit = _label_based_early_exit_status(pr_labels)
    if early_exit is not None:
        return {
            "pr_number": pr_number,
            "title": title,
            "branch": branch,
            "status": early_exit["status"],
            "summary": early_exit["summary"],
            "elapsed_min": 0,
            "ai_reviews_count": 0,
            "ai_inline_count": 0,
            "unresolved_threads": 0,
            "unresolved_threads_unknown": False,
            "bot_comments_count": 0,
            "has_gemini_review": False,
            "has_copilot_review": False,
            "gemini_quota_exceeded": False,
            "last_activity_min": 9999,
            "active_session": False,
            "owner_session_id": owner_session_id,
            "author_association": author_association,
        }

    # レビューリクエスト（requested_reviewers）を確認
    review_requests = pr.get("reviewRequests", [])
    has_ai_reviewer_requested = False
    for rr in review_requests:
        login = rr.get("login", "") or rr.get("name", "")
        if any(bot_name.replace("[bot]", "") in login.lower() for bot_name in ["copilot", "gemini-code-assist"]):
            has_ai_reviewer_requested = True
            break

    # レビュー取得
    reviews = get_pr_reviews(pr_number)
    ai_reviews = [r for r in reviews if r.get("user", "") in AI_REVIEWERS]

    # インラインコメント取得
    inline_comments = get_pr_comments(pr_number)
    ai_inline = [c for c in inline_comments if c.get("user", "") in AI_REVIEWERS]

    # ボットのIssueコメント取得
    issue_comments = get_pr_issue_comments(pr_number)

    # /gemini review コマンドコメント取得（投稿者種別不問・L-051 対策）
    gemini_trigger_comments = get_pr_gemini_trigger_comments(pr_number)

    # 未解決スレッド数（#790 指摘1: 取得成功可否も受け取り fail-open を防ぐ）
    unresolved, unresolved_ok = get_unresolved_threads(pr_number)
    unresolved_threads_unknown = not unresolved_ok

    # PR作成からの経過時間（ステータス判定より前に計算する）
    elapsed_min = 0
    if created_at:
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            elapsed = datetime.now(timezone.utc) - created
            elapsed_min = int(elapsed.total_seconds() / 60)
        except (ValueError, TypeError):
            pass

    # ステータス判定
    has_ai_review = len(ai_reviews) > 0 or len(ai_inline) > 0
    has_unresolved = unresolved > 0

    # Gemini / Copilot を個別に判定（L-038 対策: Copilot 無応答 → 片方完了でマージ可）
    ai_reviewer_logins = {r.get("user", "") for r in ai_reviews} | {c.get("user", "") for c in ai_inline}
    # Gemini はフォーマルレビュー・インラインコメントに加え、issue comment でも応答する場合がある
    gemini_issue_comments = [c for c in issue_comments if c.get("user", "") == GEMINI_BOT]
    has_gemini_review = (GEMINI_BOT in ai_reviewer_logins) or bool(gemini_issue_comments)
    has_copilot_review = bool(ai_reviewer_logins & COPILOT_BOTS)

    # Gemini クォータ超過検出（#1079 対策）
    # Gemini が「quota」「rate limit」を含むコメントを投稿している場合、当日クォータ超過と判定する
    gemini_quota_exceeded = any(
        ("quota" in c.get("body", "").lower() or "rate limit" in c.get("body", "").lower()
         or "クォータ" in c.get("body", ""))
        for c in issue_comments
        if c.get("user", "").startswith("gemini")
    )

    # Gemini レビュー依頼済み判定（L-051 対策）
    # Gemini は /gemini review コメントで依頼されるため reviewRequests に現れない。
    # gemini_issue_comments（Gemini Bot 応答）または gemini_trigger_comments（/gemini review コマンド・投稿者不問）があれば依頼済みと判定する。
    has_gemini_review_requested = bool(gemini_issue_comments) or bool(gemini_trigger_comments)

    # Copilot レビュー依頼済み判定
    has_copilot_review_requested = any(
        rr.get("login", "").replace("[bot]", "").lower() in {"copilot", "copilot-pull-request-reviewer"}
        for rr in review_requests
    )

    # AIレビュー依頼済みの最終判定（Gemini か Copilot のどちらかに依頼済みなら True）
    has_ai_reviewer_requested_combined = (
        has_ai_reviewer_requested
        or has_gemini_review_requested
        or has_copilot_review_requested
    )

    # 外部 AI レビュアー（Copilot/Gemini）への依頼は廃止（飼い主決定）。レビューは Claude 自身の
    # Layer 1 セルフレビュー（自前 code-review スキル・組み込みを同名 project スキルで置換済み・
    # #275 → #280）で完結する。本スクリプトは Layer 1 の実施を機械検出できないため、未解決スレッドの有無と
    # 経過時間でセッション復帰時の対応を決める。外部レビュアーの 25 分応答待ち・催促は廃止した。
    # has_gemini_review / has_copilot_review / gemini_quota_exceeded は履歴 PR の互換情報として
    # 返り値に残すが、マージ判定には用いない。
    #
    # 🔴 著者検証は「分岐に入る前」に一度だけ行う（#379）。
    #
    # 経緯: 当初は _is_claude_branch() の内部にだけ authorAssociation を AND した。しかしその後の
    # レビューで、判定に至る経路が 3 本あり、うち 2 本が検証を迂回できることが実測で判明した:
    #   ① _is_claude_branch() 経由 …… ブランチ名の前方一致。命名規則は CLAUDE.md で公開済み
    #   ② has_ai_reviewer_requested_combined / has_ai_review 経由 …… OR で並んでいたため、
    #      fork PR の作成者が自分の PR に `/gemini review` と書く・bot レビューを呼ぶだけで到達できた
    #   ③ has_unresolved 経由 …… ブランチ名すら不要。fork PR の作成者が自分の PR に
    #      レビューコメントを 1 件投稿すれば未解決スレッドが立ち、needs_response に到達できた
    #      （GitHub は自分の PR への approve は拒否するが comment は拒否しない）
    # ①だけを塞ぐと穴が②③へ移動するだけなので、**すべての分岐の手前で信頼境界を 1 回引く**。
    # 取得できないときは fail-closed（対象外）。外部 AI レビュアーは廃止済み（ai-reviewer-strategy.md）で
    # ②の 2 経路は履歴 PR 互換のための残骸だが、残す以上は同じ信頼境界の内側に置く。
    # 🔴 Issue #458 / PR #594: 信頼境界の例外を bot 自動化 PR の 2 系統だけに増やす（既存の
    # 「信頼境界外なら全分岐の手前で no_action」という構造は壊さない）。`is_trusted_bot_pr` は
    # `_is_automation_pr()`（gem-pool-refresh）と `_is_dependabot_pr()`（Dependabot）の OR で、
    # いずれも fork 不可・ブランチ条件・著者ログイン固定の 3 条件 AND（各 docstring 参照）なので、
    # authorAssociation が信頼集合に無い bot 著者でもここだけは通す。
    if not _is_trusted_author_association(author_association) and not is_trusted_bot_pr:
        # 信頼できない著者（fork PR・外部コントリビューター・authorAssociation 取得失敗）は
        # どのステータスにも乗せない。pr-review-watcher は status だけを見てマージまで進めるため、
        # ここを通した時点で無人マージの対象になる（下流へも同じ設定が配布される）。
        status = "no_action"
        summary = "信頼境界外の著者による PR（自律レビュー・自動マージの対象外）"
    elif has_unresolved:
        # 未解決スレッド（CI 失敗・人手コメント・履歴上のボット指摘等）→ 指摘対応が必要
        status = "needs_response"
        summary = f"未解決スレッド{unresolved}件（指摘対応が必要）"
    elif (
        _is_claude_branch(branch, author_association)
        or has_ai_reviewer_requested_combined
        or has_ai_review
        or is_trusted_bot_pr
    ):
        # Claude 作業ブランチの PR。Layer 0（機械ゲート）+ Layer 1（観点別フレッシュ文脈セルフレビュー）で
        # 完結する。復帰セッションはセルフレビューを実行し指摘を解消してから即マージする
        # （外部レビュアーの応答待ちは存在しない）。active_session（直近10分の活動）除外により
        # --actionable-only では作成セッションが現役対応中の PR は出力されないため、ここに残るのは
        # アイドル化した自 PR or 孤児 PR で、復帰セッションが Layer 1 を実行してマージすべきもの。
        if elapsed_min >= ACTIVE_WINDOW_MIN:
            status = "needs_prompt"  # = Layer 1 セルフレビュー要実施 → 観点別フレッシュ文脈レビュー実行 → マージ
            summary = (
                f"Layer 1 セルフレビュー要実施・{elapsed_min}分経過"
                "（観点別フレッシュ文脈レビュー実行 → 指摘解消 → 即マージ。外部レビュアー依頼なし）"
            )
        else:
            status = "awaiting_review"
            summary = f"PR 作成直後・{elapsed_min}分（作成セッションがセルフレビュー実行中）"
    else:
        status = "no_action"
        summary = "Claude 以外の PR または手動 PR（自律レビュー対象外）"

    # 未解決スレッド数が未検証（gh 到達不可）なら summary の先頭に必ず警告を差し込む（#790 指摘1）。
    # status 判定は変えない（可視化と機械可読フラグのみで対処する）。
    if unresolved_threads_unknown:
        summary = (
            "⚠️ 未解決スレッド数は未検証（gh 到達不可）。マージ前に "
            'mcp__github__pull_request_read(method="get_review_comments") で確認すること。｜'
            + summary
        )

    # アクティブセッション判定（Issue #3007・CP-4）
    # 介入対象ステータスの PR のみ追加 API 呼び出しでアクティビティを算出する
    last_activity_min = 9999
    active_session = False
    if status in ("awaiting_review", "needs_prompt", "needs_response", "ready_to_merge"):
        human_comment_times = get_pr_human_comment_times(pr_number)
        last_activity_min = compute_last_activity_min(pr, inline_comments, human_comment_times)
        active_session = last_activity_min < ACTIVE_WINDOW_MIN
        if active_session:
            summary += f"｜⚠️ 作成セッション活動中（最終活動{last_activity_min}分前）→ 他セッションは介入禁止"

    return {
        "pr_number": pr_number,
        "title": title,
        "branch": branch,
        "status": status,
        "summary": summary,
        "elapsed_min": elapsed_min,
        "ai_reviews_count": len(ai_reviews),
        "ai_inline_count": len(ai_inline),
        "unresolved_threads": unresolved,
        "unresolved_threads_unknown": unresolved_threads_unknown,
        "bot_comments_count": len(issue_comments),
        "has_gemini_review": has_gemini_review,
        "has_copilot_review": has_copilot_review,
        "gemini_quota_exceeded": gemini_quota_exceeded,
        "last_activity_min": last_activity_min,
        "active_session": active_session,
        "owner_session_id": owner_session_id,
        "author_association": author_association,
    }


def _rest_pr_head_sha(pr_number: int, token: str) -> tuple[bool, str]:
    """PR の head コミット SHA の REST 版（第 2 層）。"""
    url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
    ok, out = _http_get(url, token)
    if not ok:
        return False, out
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return False, "REST 応答の JSON 解析に失敗"
    return True, (data.get("head") or {}).get("sha", "")


def get_pr_head_sha(pr_number: int, critical: bool = False) -> str:
    """PRの現在のheadコミットSHAを取得する（`verify_layer1_review` の最新コミット判定用）。"""
    output = run_gh([
        "api", f"repos/{REPO}/pulls/{pr_number}",
        "--jq", ".head.sha",
    ], critical=critical, rest_fallback=lambda: _token_gated(_rest_pr_head_sha, pr_number))
    return output.strip()


def _layer1_verdict(review_count: int, inline_count: int) -> int:
    """レビュー件数・インラインコメント件数から Layer 1 実施の終了コードを決める純粋関数。

    I/O から分離することで `_run_self_test()` が gh 非依存で判定ロジックを検証できる（base#462）。
    返り値は 0（LAYER1_VERIFIED）/ 1（LAYER1_MISSING）のいずれか。
    """
    return 0 if (review_count > 0 or inline_count > 0) else 1


def verify_layer1_review(pr_number: int) -> int:
    """マージ直前に Layer 1 セルフレビューが投稿済みかを機械検証する（base#462）。

    Layer 0（`self_review_check.py`）は PR 作成前の静的チェックで、Layer 1（観点別フレッシュ文脈
    セルフレビュー・`Skill(code-review)`）の実施有無までは検出しない。#461 により指摘ゼロでも
    `event="COMMENT"` のレビューを 1 件投稿する運用のため、対象 PR にフォーマルレビュー
    （`get_pr_reviews`）または行単位インラインコメント（`get_pr_comments`）が 1 件でもあれば
    Layer 1 実施済みとみなす（投稿者の識別はしない — 本プロジェクトは自律運用のため、
    レビューの存在自体が Layer 1 実施の代理指標として十分機能する）。

    ただし件数を数える対象は **現在の PR head コミットに対するレビュー/コメントのみ**
    （`commit_id == head_sha`）に絞る。force-push や追加コミット後も古いレビューが
    残り続けるため、絞り込まないと「最新差分は未レビューなのに件数だけで PASS する」
    誤判定が起こる（レビューレビュー指摘・base#462）。

    返り値は終了コード:
      0 = LAYER1_VERIFIED（現行コミットへのレビューまたはインラインコメントが1件以上・マージ続行可）
      1 = LAYER1_MISSING（0 件・Layer 1 未実施とみなしマージをブロックする）
      2 = LAYER1_UNKNOWN（gh 到達不可 or JSON 破損で判定不能・誤ブロックを避け mcp フォールバックへ委ねる）
    """
    try:
        head_sha = get_pr_head_sha(pr_number, critical=True)
        reviews = get_pr_reviews(pr_number, critical=True)
        inline_comments = get_pr_comments(pr_number, critical=True)
    except GhUnavailableError as e:
        print(f"ERROR: gh_unavailable: {e}", file=sys.stderr)
        print(
            "LAYER1_UNKNOWN: gh 経由の取得に失敗しました（クラウドの 403 等）。"
            "mcp__github__pull_request_read(method=\"get_reviews\") で件数を直接確認してから"
            "マージ判断してください（誤ブロックを避けるためこの終了コードだけではマージを止めない）。",
        )
        return 2

    if not head_sha:
        # gh は成功したが head SHA が空（API 応答の欠落・jq のフィールド不在）。空文字と
        # commit_id を比較すると全件が「古いレビュー」に落ち、実施済みでも MISSING になる。
        # 誤ブロックを避けて UNKNOWN に倒す（判定不能は 2 で表す・base#462）。
        print(
            "LAYER1_UNKNOWN: PR head SHA を取得できませんでした。"
            'mcp__github__pull_request_read(method="get_reviews") で件数を直接確認してから'
            "マージ判断してください。",
        )
        return 2

    current_reviews = [r for r in reviews if r.get("commit_id") == head_sha]
    current_inline = [c for c in inline_comments if c.get("commit_id") == head_sha]
    review_count = len(current_reviews)
    inline_count = len(current_inline)

    if _layer1_verdict(review_count, inline_count) == 0:
        print(f"LAYER1_VERIFIED:{pr_number}:reviews={review_count}:inline={inline_count}")
        return 0

    stale_reviews = len(reviews) - review_count
    stale_inline = len(inline_comments) - inline_count
    stale_note = (
        f"（うち現行コミット以前の古いレビュー/コメント: reviews={stale_reviews} inline={stale_inline}）"
        if (stale_reviews or stale_inline) else ""
    )
    print(
        f"LAYER1_MISSING:{pr_number}:reviews=0:inline=0 "
        f"(Layer 1 セルフレビュー未投稿の可能性 — Skill(code-review) を実行してから再検証すること){stale_note}",
    )
    return 1


# 自動マージ対象と認めるレビュー著者関係（GitHub の authorAssociation 値）。
# CONTRIBUTOR / FIRST_TIME_CONTRIBUTOR / FIRST_TIMER / NONE は信頼しない
# （fork PR は通常 CONTRIBUTOR 以下になる）。
TRUSTED_AUTHOR_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def _is_trusted_author_association(author_association: str | None) -> bool:
    """authorAssociation が信頼できる（OWNER/MEMBER/COLLABORATOR）かどうかを判定する。

    取得できなかった場合（None・空文字・想定外の値）は **安全側（False）に倒す**
    （公開リスク監査 r03・critical: ブランチ名の前方一致だけで自動マージ対象と
    判定すると、CLAUDE.md が公開しているブランチ命名規則どおりの名前で fork から
    PR を出すだけで対象になってしまう。取得失敗を「信頼できる」と誤判定しない）。
    """
    if not author_association:
        return False
    return author_association.strip().upper() in TRUSTED_AUTHOR_ASSOCIATIONS


def _is_claude_branch(branch: str, author_association: str | None) -> bool:
    """Claude Code が作成したブランチ、かつ著者が信頼できるか（AND 条件・#379）。

    ブランチ名の前方一致だけを見ていた旧実装は、規約どおりの命名（feat/ fix/ docs/ 等）で
    fork から PR を出すだけで自動マージ対象（needs_prompt）になってしまう critical な穴だった。
    authorAssociation（gh --json authorAssociation・REST の author_association）を AND 条件に
    加えることで、ブランチ名が一致していても著者が OWNER/MEMBER/COLLABORATOR でなければ
    対象外にする。
    """
    prefixes = ("claude/", "content/", "feat/", "fix/", "docs/")
    branch_matches = any(branch.startswith(p) for p in prefixes)
    return branch_matches and _is_trusted_author_association(author_association)


# 🔴 SSOT: このブランチ名は .github/workflows/gem-pool-refresh.yml の固定ブランチ（`BRANCH=`）と
#     同一でなければならない。どちらか片方を変更したら必ずもう片方も直すこと（Issue #458）。
AUTOMATION_PR_BRANCH = "automation/gem-pool-refresh"
AUTOMATION_PR_AUTHOR_LOGIN = "github-actions[bot]"

# 🔴 SSOT: このプレフィックスは .github/dependabot.yml で有効化した Dependabot が作るブランチ
#     （`dependabot/<ecosystem>/<package>-<version>`）に対応する。dependabot.yml を撤去したら
#     本述語も一緒に外すこと（PR #594）。
DEPENDABOT_PR_BRANCH_PREFIX = "dependabot/"
DEPENDABOT_PR_AUTHOR_LOGIN = "dependabot[bot]"


def _is_automation_pr(
    branch: str,
    author_login: str | None,
    is_cross_repository: bool | None,
) -> bool:
    """Gem Pool 週次リフレッシュ workflow（Issue #458）が作った PR を自動化 PR として認めるか。

    🔴 `_is_trusted_author_association()` の許可集合に bot を足す形にはしない（#379 の信頼境界が
    全経路で緩む）。代わりにこの独立した狭い述語を新設し、次を **すべて満たすときだけ** True にする
    （1 つでも欠けたら False = 従来どおりの信頼境界判定に落ちる）:
      1. head が同一リポジトリ（fork ではない）。`isCrossRepository` を取得できない（None）場合は
         安全側で False にする（fail-closed。fork かどうか分からない PR を通さない）
      2. ブランチ名が **完全一致**（前方一致にしない。`automation/gem-pool-refresh-evil` 等を弾く）
      3. 著者ログインが `github-actions[bot]`（GITHUB_TOKEN で作成された PR の固定著者）

    3 条件の AND がなぜ安全か: fork からは同名ブランチを作れても `isCrossRepository=True` になり
    ①で弾かれる。著者ログインは GitHub 側が PR 作成 API 呼び出し元から機械的に決めるため、
    このリポジトリの `github-actions[bot]` になりすますことは通常のユーザー操作では出来ない。
    """
    if is_cross_repository is not False:
        return False
    if branch != AUTOMATION_PR_BRANCH:
        return False
    return (author_login or "") == AUTOMATION_PR_AUTHOR_LOGIN


def _is_dependabot_pr(
    branch: str,
    author_login: str | None,
    is_cross_repository: bool | None,
) -> bool:
    """Dependabot（`.github/dependabot.yml`・PR #594）が作った PR を自動化 PR として認めるか。

    🔴 `_is_trusted_author_association()` の許可集合に bot を足す形にはしない（#379 の信頼境界が
    全経路で緩む）。`_is_automation_pr()` と同じ 3 条件 AND で、次を **すべて満たすときだけ** True にする:
      1. head が同一リポジトリ（fork ではない）。取得できない（None）場合は fail-closed で False
      2. ブランチ名が `dependabot/` で始まる。**ここだけ前方一致にする**（`_is_automation_pr()` は
         完全一致だが、Dependabot のブランチ名は `dependabot/npm_and_yarn/<pkg>-<ver>` のように
         更新対象ごとに変わるため完全一致では書けない）
      3. 著者ログインが `dependabot[bot]`

    前方一致を許してなお安全な理由: 信頼境界の実質は ③ の著者ログインである。`dependabot[bot]` は
    GitHub 側が PR 作成元から機械的に決める値で、通常のユーザー操作でなりすませない。人間が
    `dependabot/evil` というブランチを作って PR を出しても、著者ログインが自分のアカウントになる
    ため ③ で弾かれる。fork からの偽装は ① で弾かれる。

    なぜ必要か: この述語が無いと、Dependabot PR は `authorAssociation` が信頼集合
    （OWNER/MEMBER/COLLABORATOR）に入らないため `analyze_pr()` で必ず `no_action` に落ち、
    `pr-review-watcher` / `project-sync` のどちらの回収経路にも乗らない。`open-pull-requests-limit`
    に達した時点で Dependabot は新規 PR を出さなくなり、依存更新の自動化が黙って止まる。
    """
    if is_cross_repository is not False:
        return False
    if not branch.startswith(DEPENDABOT_PR_BRANCH_PREFIX):
        return False
    return author_login == DEPENDABOT_PR_AUTHOR_LOGIN


def _test_run_gh_fallback_layers() -> list[str]:
    """`run_gh` の多段フォールバック（gh 失敗 → REST → 両方失敗）を monkeypatch で検証する（#789 ④）。

    ネットワーク非依存: `_run_gh_raw` を常に失敗するスタブへ差し替え、`rest_fallback` の
    戻り値だけを変えて分岐を確認する。試験後は必ず元の関数へ復元する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")
    try:
        # ④-a: REST 側が HTTP エラーを返す → critical=True は空文字列ではなく GhUnavailableError
        def _fallback_http_error():
            return False, "HTTP 500"

        try:
            run_gh(["api", "dummy"], critical=True, rest_fallback=_fallback_http_error)
            failures.append(
                "  run_gh: gh失敗+REST HTTPエラー時に critical=True が GhUnavailableError を送出しなかった"
            )
        except GhUnavailableError:
            pass

        # 負ケース: critical=False なら例外にせず空文字列にフォールバックすること（既存挙動維持）
        got = run_gh(["api", "dummy"], critical=False, rest_fallback=_fallback_http_error)
        if got != "":
            failures.append(f"  run_gh: critical=False で空文字列以外を返した: {got!r}")

        # ④-b: GH_TOKEN/GITHUB_TOKEN 未設定を模した rest_fallback（「未設定」を理由に失敗）でも
        # critical=True は同様に GhUnavailableError（空リストに化けない）
        def _fallback_no_token():
            return False, "GH_TOKEN/GITHUB_TOKEN 未設定"

        try:
            run_gh(["api", "dummy"], critical=True, rest_fallback=_fallback_no_token)
            failures.append(
                "  run_gh: gh失敗+token未設定時に critical=True が GhUnavailableError を送出しなかった"
            )
        except GhUnavailableError:
            pass

        # REST フォールバックが成功したら gh 失敗を隠して結果を返すこと（フォールバックの本来目的）
        def _fallback_success():
            return True, '[{"ok": true}]'

        got2 = run_gh(["api", "dummy"], critical=True, rest_fallback=_fallback_success)
        if got2 != '[{"ok": true}]':
            failures.append(f"  run_gh: REST フォールバック成功時の出力が想定と異なる: {got2!r}")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
    return failures


def _test_get_pr_reviews_gh_unavailable() -> list[str]:
    """実 getter（`get_pr_reviews`）レベルの ④-a/④-b 回帰（#789）。

    `_run_gh_raw` を失敗スタブに差し替えたうえで、① トークン未設定 ② トークンありだが
    REST が HTTP エラー、の 2 パターンで critical=True が空リストに化けず
    `GhUnavailableError` を送出することを確認する。試験後は monkeypatch と環境変数を復元する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    saved_env = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")
    try:
        # ④-b: token 未設定 → critical=True で GhUnavailableError
        try:
            get_pr_reviews(1, critical=True)
            failures.append(
                "  get_pr_reviews: token未設定・gh失敗時に critical=True が例外を送出しなかった"
            )
        except GhUnavailableError:
            pass

        # 負ケース: critical=False は従来どおり空リストへフォールバックすること
        got = get_pr_reviews(1, critical=False)
        if got != []:
            failures.append(f"  get_pr_reviews: critical=False で空リスト以外を返した: {got!r}")

        # ④-a: token はあるが REST が HTTP エラー → critical=True は依然 GhUnavailableError
        os.environ["GH_TOKEN"] = "dummy-token-for-test"
        orig_http_get = globals()["_http_get"]
        globals()["_http_get"] = lambda url, token: (False, "HTTP 500")
        try:
            try:
                get_pr_reviews(1, critical=True)
                failures.append(
                    "  get_pr_reviews: token あり・REST HTTPエラー時に critical=True が例外を送出しなかった"
                )
            except GhUnavailableError:
                pass
        finally:
            globals()["_http_get"] = orig_http_get
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    return failures


def _test_rest_pagination() -> list[str]:
    """`_rest_get_all_pages` が 100 件ちょうどで次ページへ進み、取りこぼさないことを検証する
    （#789 実装要件 4）。単一ページ（100件未満）では余計な追加リクエストをしないことも確認する。
    """
    failures: list[str] = []
    orig_http_get = globals()["_http_get"]
    page1 = [{"id": i} for i in range(100)]
    page2 = [{"id": 100}]

    def _fake_http_get_two_pages(url, token):
        # 末尾の `&page=N` で判定する（`per_page=100` に "page=1" が部分文字列として
        # 含まれてしまうため、単純な `in` 判定では全ページが page=1 に誤マッチする）。
        if url.endswith("&page=1"):
            return True, json.dumps(page1)
        if url.endswith("&page=2"):
            return True, json.dumps(page2)
        return True, json.dumps([])

    globals()["_http_get"] = _fake_http_get_two_pages
    try:
        ok, items = _rest_get_all_pages("pulls", "state=open", "dummy-token")
        if not ok or len(items) != 101:
            failures.append(
                f"  _rest_get_all_pages: ページネーション取りこぼし "
                f"(ok={ok!r} len={len(items) if ok else 'N/A'} expected 101)"
            )
    finally:
        globals()["_http_get"] = orig_http_get

    call_count = {"n": 0}

    def _fake_http_get_single_page(url, token):
        call_count["n"] += 1
        return True, json.dumps([{"id": 1}])

    globals()["_http_get"] = _fake_http_get_single_page
    try:
        ok2, items2 = _rest_get_all_pages("pulls", "state=open", "dummy-token")
        if not ok2 or len(items2) != 1 or call_count["n"] != 1:
            failures.append(
                f"  _rest_get_all_pages: 単一ページで想定外の追加リクエスト "
                f"(call_count={call_count['n']} items={items2!r})"
            )
    finally:
        globals()["_http_get"] = orig_http_get

    # 上限到達時の打ち切り検知（#790 指摘3）: max_pages に達した時点でも最終ページが
    # ちょうど100件（＝まだ続きがある可能性）なら fail-open で成功扱いにせず ok=False を返す。
    def _fake_http_get_always_full(url, token):
        return True, json.dumps([{"id": i} for i in range(100)])

    globals()["_http_get"] = _fake_http_get_always_full
    try:
        ok3, reason3 = _rest_get_all_pages("pulls", "state=open", "dummy-token", max_pages=2)
        if ok3:
            failures.append(
                f"  _rest_get_all_pages: max_pages到達時に fail-open で成功扱いになった "
                f"(ok={ok3!r} result={reason3!r})"
            )
        elif "上限" not in str(reason3):
            failures.append(
                f"  _rest_get_all_pages: max_pages到達時の理由文字列に『上限』が含まれない: {reason3!r}"
            )
    finally:
        globals()["_http_get"] = orig_http_get

    # 負ケース: ちょうど max_pages で完了するが最終ページが100件未満（＝続きが無い）なら
    # 打ち切り扱いにしない（誤って fail-closed に倒さないことの回帰固定）。
    def _fake_http_get_exact_boundary(url, token):
        if url.endswith("&page=1"):
            return True, json.dumps([{"id": i} for i in range(100)])
        if url.endswith("&page=2"):
            return True, json.dumps([{"id": 100}])
        return True, json.dumps([])

    globals()["_http_get"] = _fake_http_get_exact_boundary
    try:
        ok4, items4 = _rest_get_all_pages("pulls", "state=open", "dummy-token", max_pages=2)
        if not ok4 or len(items4) != 101:
            failures.append(
                f"  _rest_get_all_pages: ちょうど max_pages で完了するケースを誤って打ち切り扱いした "
                f"(ok={ok4!r} len={len(items4) if ok4 else 'N/A'})"
            )
    finally:
        globals()["_http_get"] = orig_http_get
    return failures


def _test_get_unresolved_threads_fail_open_fix() -> list[str]:
    """`get_unresolved_threads` が gh 到達不可時に `(0, False)` を返すことを固定する（#790 指摘1）。

    修正前は成功可否を返さず常に `int`（0 件）を返しており、呼び出し元が「取得失敗」と
    「本当に 0 件」を区別できず fail-open していた（本来 `needs_response` になるはずの PR が
    `needs_prompt`/`awaiting_review` に落ちて自動マージ対象へ紛れ込む）。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]

    # gh 到達不可 → (0, False)
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")
    try:
        got = get_unresolved_threads(1)
        if got != (0, False):
            failures.append(f"  get_unresolved_threads: gh失敗時 = {got!r} (expected (0, False))")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw

    # gh 成功 → (未解決件数, True)
    def _fake_graphql_success(args):
        query_result = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"isResolved": False},
                                {"isResolved": True},
                                {"isResolved": False},
                            ]
                        }
                    }
                }
            }
        }
        return True, json.dumps(query_result)

    globals()["_run_gh_raw"] = _fake_graphql_success
    try:
        got2 = get_unresolved_threads(1)
        if got2 != (2, True):
            failures.append(f"  get_unresolved_threads: gh成功時 = {got2!r} (expected (2, True))")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw

    # gh は成功したが JSON 破損 → (0, False)（黙って 0 件成功に化けさせない）
    globals()["_run_gh_raw"] = lambda args: (True, "not-json{{{")
    try:
        got3 = get_unresolved_threads(1)
        if got3 != (0, False):
            failures.append(f"  get_unresolved_threads: JSON解析失敗時 = {got3!r} (expected (0, False))")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
    return failures


def _test_analyze_pr_unresolved_threads_unknown() -> list[str]:
    """`analyze_pr` が未解決スレッド数の未検証を `unresolved_threads_unknown` として可視化し、
    summary の先頭に警告を差し込むことを固定する（#790 指摘1）。

    gh 到達不可・token 未設定（REST フォールバックも不可）を再現し、`analyze_pr` を実際に
    呼んで劣化経路を通す。他の `get_*` 呼び出しも同じ環境下で自然に空リスト/空文字へ
    劣化するため、追加の monkeypatch なしで安全に実行できる（実ネットワークへは出ない）。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    saved_env = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")
    try:
        pr = {
            "number": 9001,
            "title": "テスト PR",
            "headRefName": "feat/x",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "author": {"login": "someone"},
            "authorAssociation": "OWNER",
            "reviewRequests": [],
            "labels": [],
            "body": "",
            "isCrossRepository": False,
        }
        result = analyze_pr(pr)
        if result.get("unresolved_threads_unknown") is not True:
            failures.append(
                "  analyze_pr: unresolved_threads_unknown が True にならない "
                f"(got {result.get('unresolved_threads_unknown')!r})"
            )
        summary = result.get("summary", "")
        if not summary.startswith("⚠️ 未解決スレッド数は未検証"):
            failures.append(
                f"  analyze_pr: summary の先頭に未検証警告が差し込まれていない (summary={summary!r})"
            )
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    return failures


def _test_get_open_prs_rest_fallback() -> list[str]:
    """`get_open_prs()` の REST フォールバック（getter レベル）を検証する（#790 指摘2）。

    既存の self-test は `run_gh` の汎用フォールバック分岐・`get_pr_reviews` という別 getter・
    `_transform_rest_pr` / `_rest_get_all_pages` の単体テストしかカバーしておらず、
    `get_open_prs()` 内部の `_fallback`（現 `_rest_open_prs` 経由）自体は一度も実行されて
    いなかった。ここでは `_run_gh_raw` を失敗スタブへ差し替え、`_http_get` を PR 配列 JSON を
    返すスタブへ差し替えたうえで実際に `get_open_prs()` を呼び、結果が `_transform_rest_pr`
    を通した gh スキーマ（createdAt / headRefName / authorAssociation / labels=[{name}]）に
    なっていることを確認する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    orig_http_get = globals()["_http_get"]
    saved_env = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")
    os.environ["GH_TOKEN"] = "dummy-token-for-test"
    raw_prs = [
        {
            "number": 123,
            "title": "テスト PR",
            "created_at": "2026-09-01T00:00:00Z",
            "head": {"ref": "feat/x", "repo": {"full_name": REPO}},
            "user": {"login": "someone"},
            "author_association": "OWNER",
            "requested_reviewers": [],
            "requested_teams": [],
            "labels": [{"name": "sp:3"}],
            "body": "Session-Id: test",
        }
    ]
    globals()["_http_get"] = lambda url, token: (True, json.dumps(raw_prs))
    try:
        got = get_open_prs()
        if len(got) != 1:
            failures.append(
                f"  get_open_prs REST フォールバック: 件数不一致 (got {len(got)} 件, expected 1)"
            )
        else:
            pr = got[0]
            expected_fields = {
                "number": 123,
                "title": "テスト PR",
                "createdAt": "2026-09-01T00:00:00Z",
                "headRefName": "feat/x",
                "authorAssociation": "OWNER",
            }
            for key, expected_value in expected_fields.items():
                if pr.get(key) != expected_value:
                    failures.append(
                        f"  get_open_prs REST フォールバック: {key}={pr.get(key)!r} "
                        f"(expected {expected_value!r})"
                    )
            if pr.get("labels") != [{"name": "sp:3"}]:
                failures.append(
                    f"  get_open_prs REST フォールバック: labels={pr.get('labels')!r} "
                    "(expected [{'name': 'sp:3'}])"
                )
    except GhUnavailableError as e:
        failures.append(f"  get_open_prs REST フォールバック: 予期せず GhUnavailableError ({e})")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        globals()["_http_get"] = orig_http_get
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    return failures


def _test_get_pr_head_sha_rest_fallback() -> list[str]:
    """`get_pr_head_sha()` の REST フォールバック（getter レベル）を検証する（#790 指摘2）。

    `critical=True` で呼ばれ `verify_layer1_review` の判定に直結するため、REST フォールバック
    経由でも正しい head SHA を返すことを確認する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    orig_http_get = globals()["_http_get"]
    saved_env = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")
    os.environ["GH_TOKEN"] = "dummy-token-for-test"
    expected_sha = "deadbeef1234"
    globals()["_http_get"] = lambda url, token: (True, json.dumps({"head": {"sha": expected_sha}}))
    try:
        got = get_pr_head_sha(1, critical=True)
        if got != expected_sha:
            failures.append(f"  get_pr_head_sha REST フォールバック: {got!r} (expected {expected_sha!r})")
    except GhUnavailableError as e:
        failures.append(f"  get_pr_head_sha REST フォールバック: 予期せず GhUnavailableError ({e})")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        globals()["_http_get"] = orig_http_get
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    return failures


def _run_self_test() -> None:
    """Session-Id 解析（純粋関数）の決定論テスト。CI / セルフレビューで実行する。"""
    uid = "ec373723-01dc-54c9-a204-9ebb221b2295"
    cases: list[tuple[str | None, str]] = [
        (f"Sprint Goal: x\nSession-Id: {uid}\nsp:3", uid),
        (f"session-id: {uid.upper()}", uid),  # 大文字小文字・正規化
        (f"前置き\n\nSession-Id:   {uid}   \n後置き", uid),  # 余白許容
        ("Session-Id: not-a-uuid", ""),  # 形式不正 → 空
        ("Sprint Goal のみ・トレーラーなし", ""),
        ("", ""),
        (None, ""),
    ]
    failures = []
    for body, expected in cases:
        got = parse_session_id(body)
        if got != expected:
            failures.append(f"  parse_session_id({body!r}) = {got!r} (expected {expected!r})")
    # current_session_id: 明示指定が env より優先・小文字正規化
    if current_session_id("ABC-123") != "abc-123":
        failures.append("  current_session_id explicit override failed")

    # 著者検証（#379・公開リスク監査 r03 critical）: ブランチ名一致 AND 信頼できる著者
    branch_cases: list[tuple[str, str | None, bool]] = [
        # (branch, authorAssociation, expected) — オーナー/メンバー/コラボレーターの正規 PR
        ("feat/x", "OWNER", True),
        ("fix/y", "MEMBER", True),
        ("docs/z", "COLLABORATOR", True),
        ("claude/session-123", "owner", True),  # 小文字応答も許容
        ("content/V001-x", "Member", True),
        # fork PR を模した入力（ブランチ名は規約どおりだが著者は信頼できない） → 対象外
        ("feat/evil", "CONTRIBUTOR", False),
        ("fix/evil", "FIRST_TIME_CONTRIBUTOR", False),
        ("docs/evil", "NONE", False),
        # authorAssociation 取得不能（gh 応答欠落等） → 安全側（対象外）
        ("feat/unknown", None, False),
        ("feat/unknown", "", False),
        # ブランチ名がそもそも規約に一致しない → 著者が OWNER でも対象外
        ("random-branch", "OWNER", False),
    ]
    for branch, assoc, expected in branch_cases:
        got = _is_claude_branch(branch, assoc)
        if got != expected:
            failures.append(
                f"  _is_claude_branch({branch!r}, {assoc!r}) = {got!r} (expected {expected!r})"
            )

    # 信頼境界そのもののテスト（#379）。_is_claude_branch() 単体のテストだけでは、
    # 判定に至る 3 経路（ブランチ名一致 / AI レビュー痕跡 / 未解決スレッド）のうち
    # 後ろ 2 つが検証を迂回していたことを検出できなかった。ここで境界関数を直接固定する。
    assoc_cases: list[tuple[str | None, bool]] = [
        ("OWNER", True),
        ("MEMBER", True),
        ("COLLABORATOR", True),
        ("owner", True),          # 小文字応答
        ("  MEMBER  ", True),     # 余白
        ("CONTRIBUTOR", False),   # 過去にマージ実績があるだけの外部貢献者
        ("FIRST_TIME_CONTRIBUTOR", False),
        ("FIRST_TIMER", False),
        ("NONE", False),
        ("MANNEQUIN", False),
        ("", False),              # 取得失敗 → fail-closed
        (None, False),
    ]
    for assoc, expected in assoc_cases:
        got = _is_trusted_author_association(assoc)
        if got != expected:
            failures.append(
                f"  _is_trusted_author_association({assoc!r}) = {got!r} (expected {expected!r})"
            )

    # 自動化 PR 判定（Issue #458）: fork 不可・ブランチ完全一致・著者ログイン固定の 3 条件 AND。
    automation_cases: list[tuple[str, str | None, bool | None, bool]] = [
        # (branch, author_login, is_cross_repository, expected)
        ("automation/gem-pool-refresh", "github-actions[bot]", False, True),  # 3 条件が揃う
        ("automation/gem-pool-refresh-evil", "github-actions[bot]", False, False),  # 前方一致は対象外
        ("automation/gem-pool-refresh", "some-other-user", False, False),  # 著者が別
        ("automation/gem-pool-refresh", "github-actions[bot]", True, False),  # fork（head が別リポジトリ）
        ("automation/gem-pool-refresh", "github-actions[bot]", None, False),  # 取得不能 → fail-closed
        ("automation/other-branch", "github-actions[bot]", False, False),  # ブランチ名が違う
    ]
    for branch, author_login, is_cross_repository, expected in automation_cases:
        got = _is_automation_pr(branch, author_login, is_cross_repository)
        if got != expected:
            failures.append(
                f"  _is_automation_pr({branch!r}, {author_login!r}, {is_cross_repository!r}) = {got!r} (expected {expected!r})"
            )

    # Dependabot PR 判定（PR #594）: fork 不可・ブランチ前方一致・著者ログイン固定の 3 条件 AND。
    dependabot_cases: list[tuple[str, str | None, bool | None, bool]] = [
        # (branch, author_login, is_cross_repository, expected)
        ("dependabot/npm_and_yarn/next-15.5.1", "dependabot[bot]", False, True),  # 3 条件が揃う
        ("dependabot/github_actions/actions/checkout-5", "dependabot[bot]", False, True),
        ("dependabot/pip/pyyaml-6.0.2", "dependabot[bot]", False, True),
        # 人間が Dependabot を騙る名前のブランチを作っても、著者ログインで弾かれる
        ("dependabot/npm_and_yarn/evil", "some-other-user", False, False),
        ("dependabot/npm_and_yarn/next-15.5.1", "github-actions[bot]", False, False),
        # fork（head が別リポジトリ）・取得不能はいずれも fail-closed
        ("dependabot/npm_and_yarn/next-15.5.1", "dependabot[bot]", True, False),
        ("dependabot/npm_and_yarn/next-15.5.1", "dependabot[bot]", None, False),
        # 前方一致しないブランチは対象外（`dependabot` 単体・別プレフィックス）
        ("dependabot", "dependabot[bot]", False, False),
        ("feat/dependabot/npm", "dependabot[bot]", False, False),
    ]
    for branch, author_login, is_cross_repository, expected in dependabot_cases:
        got = _is_dependabot_pr(branch, author_login, is_cross_repository)
        if got != expected:
            failures.append(
                f"  _is_dependabot_pr({branch!r}, {author_login!r}, {is_cross_repository!r}) = {got!r} (expected {expected!r})"
            )

    # 2 系統の述語が互いのケースを取り違えないこと（相互排他の回帰検査）
    cross_cases: list[tuple[str, str, bool]] = [
        # (branch, author_login) → _is_automation_pr が False であること
        ("dependabot/npm_and_yarn/next-15.5.1", "dependabot[bot]", False),
    ]
    for branch, author_login, expected in cross_cases:
        got = _is_automation_pr(branch, author_login, False)
        if got != expected:
            failures.append(
                f"  _is_automation_pr({branch!r}, {author_login!r}, False) = {got!r} (expected {expected!r})"
            )
    if _is_dependabot_pr("automation/gem-pool-refresh", "github-actions[bot]", False):
        failures.append(
            "  _is_dependabot_pr('automation/gem-pool-refresh', 'github-actions[bot]', False) = True (expected False)"
        )

    # status:blocked / status:waiting-user のラベル早期終了判定（#746）。gh 非依存の純粋関数。
    label_exit_cases: list[tuple[set[str], str | None]] = [
        (set(), None),
        ({"status:in-progress"}, None),
        ({"status:waiting-user"}, "blocked_waiting_user"),
        ({"status:blocked"}, "blocked_circuit_breaker"),
        # 両方付いている場合は blocked を優先する（A-4 は waiting-user 解除だけでは解除されない）
        ({"status:blocked", "status:waiting-user"}, "blocked_circuit_breaker"),
        ({"status:blocked", "sp:3", "type:bug"}, "blocked_circuit_breaker"),
        # 表記ゆれ・部分一致は誤検知しない（完全一致のみ判定対象）
        ({"status:blocked-review"}, None),
        ({"Status:Blocked"}, None),
    ]
    for pr_labels_case, expected_status in label_exit_cases:
        got = _label_based_early_exit_status(pr_labels_case)
        got_status = got["status"] if got is not None else None
        if got_status != expected_status:
            failures.append(
                f"  _label_based_early_exit_status({pr_labels_case!r}) = {got_status!r} "
                f"(expected {expected_status!r})"
            )

    # --actionable-only の除外集合に新設ステータスが含まれていること（main() 側の回帰固定）
    if "blocked_circuit_breaker" not in ACTIONABLE_EXCLUDED_STATUSES:
        failures.append(
            "  ACTIONABLE_EXCLUDED_STATUSES に 'blocked_circuit_breaker' が含まれていない"
        )
    if "blocked_waiting_user" not in ACTIONABLE_EXCLUDED_STATUSES:
        failures.append(
            "  ACTIONABLE_EXCLUDED_STATUSES に 'blocked_waiting_user' が含まれていない"
        )

    # Layer 1 検証の判定ロジック（base#462）。I/O から分離した純粋関数なので gh 非依存でテストできる。
    verdict_cases: list[tuple[int, int, int]] = [
        (0, 0, 1),   # 両方0件 → LAYER1_MISSING
        (1, 0, 0),   # レビューのみ1件 → LAYER1_VERIFIED
        (0, 1, 0),   # インラインのみ1件 → LAYER1_VERIFIED
        (3, 5, 0),   # 複数件 → LAYER1_VERIFIED
    ]
    for review_count, inline_count, expected in verdict_cases:
        got = _layer1_verdict(review_count, inline_count)
        if got != expected:
            failures.append(
                f"  _layer1_verdict({review_count!r}, {inline_count!r}) = {got!r} (expected {expected!r})"
            )

    # REST フォールバックの PR スキーマ変換（#789 ③-a）: labels の camelCase 変換後も
    # ラベルベースの早期終了判定（status:blocked 等）が正しく効くこと。境界の外側の負ケース
    # （blocked ラベルが無い PR は除外されないこと）も含める（#750）。
    rest_pr_label_cases: list[tuple[list[dict], str | None]] = [
        ([{"name": "status:blocked"}, {"name": "sp:3"}], "blocked_circuit_breaker"),
        ([{"name": "status:waiting-user"}], "blocked_waiting_user"),
        ([{"name": "sp:3"}, {"name": "type:bug"}], None),  # 負ケース: blocked が無い → 除外されない
        ([], None),
    ]
    for raw_labels, expected_status in rest_pr_label_cases:
        raw_pr = {
            "number": 101,
            "title": "t",
            "created_at": "2026-09-01T00:00:00Z",
            "head": {"ref": "feat/x", "repo": {"full_name": REPO}},
            "user": {"login": "someone"},
            "author_association": "OWNER",
            "requested_reviewers": [],
            "requested_teams": [],
            "labels": raw_labels,
            "body": "",
        }
        transformed = _transform_rest_pr(raw_pr)
        pr_labels = {lbl.get("name", "") for lbl in transformed.get("labels", [])}
        early = _label_based_early_exit_status(pr_labels)
        got_status = early["status"] if early is not None else None
        if got_status != expected_status:
            failures.append(
                f"  REST変換PR: labels={raw_labels!r} → early_exit={got_status!r} (expected {expected_status!r})"
            )

    # REST フォールバックの isCrossRepository 変換（fork 判定・#789）
    rest_pr_cross_repo_cases: list[tuple[dict | None, bool | None]] = [
        ({"full_name": REPO}, False),           # 同一リポジトリ
        ({"full_name": "someone/fork"}, True),  # fork
        (None, None),                            # head リポジトリ取得不能 → fail-closed で None
    ]
    for head_repo, expected in rest_pr_cross_repo_cases:
        raw_pr = {
            "number": 1, "title": "t", "created_at": "", "head": {"ref": "x", "repo": head_repo},
            "user": {}, "author_association": "", "requested_reviewers": [], "requested_teams": [],
            "labels": [], "body": "",
        }
        got = _transform_rest_pr(raw_pr)["isCrossRepository"]
        if got != expected:
            failures.append(
                f"  _transform_rest_pr isCrossRepository: head.repo={head_repo!r} = {got!r} (expected {expected!r})"
            )

    # _rest_comment_is_bot（REST issue コメントのボット判定・#789）の直接テスト。
    # 変異テストで発覚（session 記録参照）: _filter_human_comment_times は独自のボット判定を
    # 持つため、_rest_comment_is_bot 単体の欠陥（"gemini" チェック脱落等）を検知できない。
    rest_comment_bot_cases: list[tuple[dict, bool]] = [
        ({"login": "octocat", "type": "User"}, False),
        ({"login": "some-bot", "type": "Bot"}, True),
        ({"login": "copilot[bot]", "type": "User"}, True),  # type 不問でログイン名一致
        ({"login": "gemini-code-assist[bot]", "type": "User"}, True),
        ({"login": "", "type": ""}, False),
        ({}, False),
    ]
    for user, expected in rest_comment_bot_cases:
        got = _rest_comment_is_bot(user)
        if got != expected:
            failures.append(f"  _rest_comment_is_bot({user!r}) = {got!r} (expected {expected!r})")

    # REST フォールバックの非ボットコメント時刻抽出 → active_session 判定（#789 ③-b）。
    # 境界の外側の負ケース（全員ボットなら active にならないこと）も含める（#750）。
    _now = datetime.now(timezone.utc)
    _recent_iso = _now.isoformat().replace("+00:00", "Z")
    _old_iso = "2020-01-01T00:00:00Z"
    human_time_cases: list[tuple[list[dict], list[str]]] = [
        (
            [
                {"login": "octocat", "type": "User", "created_at": _recent_iso},
                {"login": "gemini-code-assist[bot]", "type": "Bot", "created_at": _old_iso},
            ],
            [_recent_iso],
        ),
        (
            [{"login": "copilot[bot]", "type": "Bot", "created_at": _recent_iso}],
            [],
        ),  # 負ケース: 全員ボット → 空リスト
    ]
    for comments, expected_times in human_time_cases:
        got = _filter_human_comment_times(comments)
        if got != expected_times:
            failures.append(
                f"  _filter_human_comment_times({comments!r}) = {got!r} (expected {expected_times!r})"
            )

    # 上記の非ボット時刻が compute_last_activity_min 経由で active_session 判定に正しく効くこと
    # （headRefName="" にしてブランチコミット取得の実 API 呼び出しを避ける・純粋テスト）
    pr_for_activity = {"number": 1, "createdAt": _old_iso, "headRefName": ""}
    active_times = _filter_human_comment_times(human_time_cases[0][0])
    last_activity_active = compute_last_activity_min(pr_for_activity, [], active_times)
    if not (last_activity_active < ACTIVE_WINDOW_MIN):
        failures.append(
            "  compute_last_activity_min: REST 由来の非ボットコメントがあるのに active 判定にならない "
            f"(last_activity_min={last_activity_active})"
        )
    inactive_times = _filter_human_comment_times(human_time_cases[1][0])
    last_activity_inactive = compute_last_activity_min(pr_for_activity, [], inactive_times)
    if last_activity_inactive < ACTIVE_WINDOW_MIN:
        failures.append(
            "  compute_last_activity_min: ボットのみのコメント（REST 由来）で active 判定になってしまった "
            f"(last_activity_min={last_activity_inactive})"
        )

    # run_gh の多段フォールバック（#789 ④）。gh 失敗 → REST → 両方失敗の分岐を monkeypatch で検証する。
    run_gh_fallback_failures = _test_run_gh_fallback_layers()
    failures.extend(run_gh_fallback_failures)
    RUN_GH_FALLBACK_CASE_COUNT = 4  # ④-a / 負ケース / ④-b / REST成功時の4アサーション

    # 実 getter（get_pr_reviews）レベルでの ④-a/④-b 回帰（#789）。
    getter_fallback_failures = _test_get_pr_reviews_gh_unavailable()
    failures.extend(getter_fallback_failures)
    GETTER_FALLBACK_CASE_COUNT = 3  # ④-b / 負ケース / ④-a の3アサーション

    # REST ページネーションの取りこぼし防止（#789 実装要件4）・上限到達時の打ち切り検知（#790 指摘3）
    pagination_failures = _test_rest_pagination()
    failures.extend(pagination_failures)
    PAGINATION_CASE_COUNT = 4  # 複数ページ結合 / 単一ページ過剰リクエスト無し / 上限打ち切り検知 / ちょうど境界で完了

    # get_unresolved_threads の fail-open 転換の修正固定（#790 指摘1）
    unresolved_threads_failures = _test_get_unresolved_threads_fail_open_fix()
    failures.extend(unresolved_threads_failures)
    UNRESOLVED_THREADS_CASE_COUNT = 3  # gh失敗時 / gh成功時 / JSON解析失敗時

    # analyze_pr が unresolved_threads_unknown を可視化し summary 先頭に警告を差すことの固定（#790 指摘1）
    analyze_pr_unknown_failures = _test_analyze_pr_unresolved_threads_unknown()
    failures.extend(analyze_pr_unknown_failures)
    ANALYZE_PR_UNKNOWN_CASE_COUNT = 2  # unresolved_threads_unknown フラグ / summary 先頭の警告

    # get_open_prs() の REST フォールバック（getter レベル回帰・#790 指摘2）
    open_prs_fallback_failures = _test_get_open_prs_rest_fallback()
    failures.extend(open_prs_fallback_failures)
    OPEN_PRS_FALLBACK_CASE_COUNT = 7  # 件数1 + フィールド5 + labels1

    # get_pr_head_sha() の REST フォールバック（getter レベル回帰・#790 指摘2）
    head_sha_fallback_failures = _test_get_pr_head_sha_rest_fallback()
    failures.extend(head_sha_fallback_failures)
    HEAD_SHA_FALLBACK_CASE_COUNT = 1

    total_cases = (
        len(cases)
        + 1
        + len(branch_cases)
        + len(assoc_cases)
        + len(verdict_cases)
        + len(automation_cases)
        + len(dependabot_cases)
        + len(cross_cases)
        + 1
        + len(label_exit_cases)
        + 2
        + len(rest_pr_label_cases)
        + len(rest_pr_cross_repo_cases)
        + len(rest_comment_bot_cases)
        + len(human_time_cases)
        + 2
        + RUN_GH_FALLBACK_CASE_COUNT
        + GETTER_FALLBACK_CASE_COUNT
        + PAGINATION_CASE_COUNT
        + UNRESOLVED_THREADS_CASE_COUNT
        + ANALYZE_PR_UNKNOWN_CASE_COUNT
        + OPEN_PRS_FALLBACK_CASE_COUNT
        + HEAD_SHA_FALLBACK_CASE_COUNT
    )
    if failures:
        print("FAIL: check_pending_pr_reviews self-test", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        sys.exit(1)
    print(f"PASS: check_pending_pr_reviews self-test ({total_cases} cases)")


def main():
    parser = argparse.ArgumentParser(
        description="レビュー待ちPRを検出する",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力する",
    )
    parser.add_argument(
        "--actionable-only",
        action="store_true",
        help="対応が必要なPRのみ出力する（no_action・blocked_waiting_user・blocked_circuit_breaker と active_session=true を除外）",
    )
    parser.add_argument(
        "--include-active",
        action="store_true",
        help="作成セッション活動中（active_session=true）の PR も actionable に含める（デバッグ・強制救済用）",
    )
    parser.add_argument(
        "--mine",
        action="store_true",
        help=(
            "自セッションが作成した PR のみ出力する（PR 本文の Session-Id トレーラーが "
            "$CLAUDE_CODE_SESSION_ID と一致するもの・#47）。自 PR は所有者が常に対応可能なため "
            "active_session 除外を適用しない（時間ベースの穴を埋める積極的所有判定）。"
        ),
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="--mine の照合に使うセッション ID を明示指定する（既定は $CLAUDE_CODE_SESSION_ID）",
    )
    # selftest-wiring-ok: セッション復帰時のレビュー待ちPR検出でのみ起動する運用ツールで、PR 前の品質ゲートではない
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Session-Id 解析の純粋関数テストを実行して終了する（API 非依存）",
    )
    parser.add_argument(
        "--verify-layer1",
        type=int,
        metavar="PR_NUMBER",
        default=None,
        help=(
            "指定 PR に Layer 1 セルフレビュー（レビュー本体 or 行単位インラインコメント）が "
            "1 件以上投稿されているかをマージ直前に機械検証する（base#462）。"
            "終了コード: 0=LAYER1_VERIFIED / 1=LAYER1_MISSING(ブロック) / 2=LAYER1_UNKNOWN(判定不能)"
        ),
    )
    args = parser.parse_args()

    if args.self_test:
        _run_self_test()
        return

    # API を実際に使うパスに入るためここで REPO 形式を検証する（--self-test は API 非依存で除外済み）
    _validate_repo()

    if args.verify_layer1 is not None:
        sys.exit(verify_layer1_review(args.verify_layer1))

    # --mine 利用時はセッション ID が必須（誤って全 PR を自 PR 扱いしないため）
    session_id = current_session_id(args.session_id)
    if args.mine and not session_id:
        print(
            "ERROR: --mine には $CLAUDE_CODE_SESSION_ID または --session-id が必要です "
            "（クラウドセッション外では --session-id <id> を明示してください）",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        prs = get_open_prs()
    except GhUnavailableError as e:
        # クラウドで repo スコープ gh が 403 になる場合など（L-114・Issue #130）。
        # 「0 件」と誤判定させないため exit 0 以外で終了し、専用の機械可読行を出す。
        print(f"ERROR: gh_unavailable: {e}", file=sys.stderr)
        print(
            "GH_UNAVAILABLE: repo スコープの gh が失敗しました。"
            "mcp__github__list_pull_requests(owner, repo, state=\"open\") で直接オープン PR を確認してください。",
        )
        sys.exit(3)

    if not prs:
        if args.json:
            print(json.dumps([], indent=2))
        else:
            print("NO_PENDING_PRS")
        return

    results = []
    for pr in prs:
        result = analyze_pr(pr)
        # is_mine: PR の Session-Id が現セッションと一致するか（#47）
        is_mine = bool(session_id) and result.get("owner_session_id", "") == session_id
        result["is_mine"] = is_mine
        # --mine: 自セッション所有 PR 以外を除外する（積極的所有判定）
        if args.mine and not is_mine:
            continue
        if args.actionable_only and result["status"] in ACTIONABLE_EXCLUDED_STATUSES:
            continue
        # 作成セッションが現役で対応中の PR には他セッションが介入しない（CP-4・Issue #3007）。
        # ただし自 PR（is_mine）は所有者本人なので active_session 除外を適用しない
        # （自 PR でも 10 分超アイドルで奪われる穴を埋める・#47）。
        if (
            args.actionable_only
            and result["active_session"]
            and not args.include_active
            and not is_mine
        ):
            continue
        results.append(result)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        if not results:
            print("NO_PENDING_PRS")
            return
        for r in results:
            print(f"PENDING:{r['pr_number']}:{r['status']}:{r['summary']} (#{r['pr_number']} {r['title']}, {r['elapsed_min']}分経過)")


if __name__ == "__main__":
    main()
