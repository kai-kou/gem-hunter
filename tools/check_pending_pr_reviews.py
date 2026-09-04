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
  `get_unresolved_threads` は正確な件数を GraphQL（`isResolved`）専用で取得するが、
  REST に等価エンドポイントが無いため、gh 到達不可時は「返信の有無」から近似する
  第 2 層（`_rest_unresolved_threads_approx`）を持つ（#792）。gh・REST 近似の両方が
  失敗した場合のみ件数を 0 件へ黙って化けさせず、戻り値の 2 つ目の要素（正確に取得できたか）
  で「未検証」を呼び出し元へ機械可読に伝える。`analyze_pr` はこれを `unresolved_threads_unknown`
  として JSON 出力へ載せ、summary の先頭に「⚠️ 未解決スレッド数は未検証」（近似も失敗）または
  「⚠️ 未解決スレッド数は近似値」（REST 近似が効いた場合。`unresolved_threads_approx` で判別）の
  警告を差し込む（status 判定自体は変えない・#790 指摘1・#792）。近似の限界（偽陰性・偽陽性）は
  `_approx_unresolved_from_comments` の docstring を参照。

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

bot 自動化 PR の回収（--mine-or-automation・#870）:
  Dependabot / `automation/gem-pool-refresh` の PR は bot 作成のため PR 本文に自セッションの
  `Session-Id:` を持たず、`--mine` では **構造的に決して拾われない**。一方 `D-43`
  （`pr-review-flow-summary.md`）とスクリプト実装（`_is_automation_pr()` / `_is_dependabot_pr()`）は
  これらを回収する前提で揃っており、`sprint-cycle-router` 決定木 Step 2 の判定条件だけが
  `--mine` 限定で閉じていた。`--mine-or-automation` は `select_step2_targets()` を適用し、
  **自 PR があればそれだけ / 無ければ bot 自動化 PR だけ / どちらも無ければ空** を返す
  （他者の人手 PR は決して返さない＝CP-4・L-109 の不介入を実装にも残す）。
  `--mine` と同時指定はできない（意味が衝突するため argparse がエラーにする）。

終了コード:
  0 = 正常終了（対象 0 件を含む。「レビュー待ち PR が無い」は日常的に起こるため
      fail-closed にしない・check-tool-design-rules.md §2 の例外条件に該当）
  1 = --verify-layer1 で Layer 1 未投稿を検出（ブロック）/ --self-test 失敗
  2 = 判定不能（--verify-layer1 の LAYER1_UNKNOWN）・引数エラー（argparse 標準・--mine と
      --mine-or-automation の同時指定、--mine 系でセッション ID 不明）
  3 = gh も REST 直叩きも全滅して PR 一覧を取得できなかった（GH_UNAVAILABLE）

Usage:
    python3 tools/check_pending_pr_reviews.py
    python3 tools/check_pending_pr_reviews.py --json
    python3 tools/check_pending_pr_reviews.py --actionable-only --include-active
    python3 tools/check_pending_pr_reviews.py --mine --json            # 自セッション所有 PR のみ
    python3 tools/check_pending_pr_reviews.py --mine --actionable-only # 自 PR で要対応のもの
    python3 tools/check_pending_pr_reviews.py --mine-or-automation --actionable-only --json
                                                                       # Step 2 の対象（自 PR 優先・空なら bot 自動化 PR）
    python3 tools/check_pending_pr_reviews.py --self-test              # Session-Id 解析テスト
    python3 tools/check_pending_pr_reviews.py --verify-layer1 <PR番号> # Layer 1 投稿済みか機械検証（base#462）
"""

import argparse
import io
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


def _approx_unresolved_from_comments(comments: list[dict]) -> int:
    """`pulls/{n}/comments` の生 REST 応答からスレッドを再構成し、未解決スレッド数を近似する（純粋関数・#792）。

    GitHub REST にはレビュースレッドの `isResolved` に等価なエンドポイントが無いため、
    「返信の有無」で近似する。**返信が 1 件も無いスレッドを未解決とみなす（返信の投稿者は問わない）**。

    🔴 投稿者を比較しない理由（実 PR #735 での実測に基づく契約修正・当初は「ルート投稿者以外
    による返信が無いこと」を条件にしていたが構造的欠陥があった）: 本リポジトリの運用
    （`pr-review-flow-summary.md`「指摘対応ルール」）では、Layer 1 セルフレビューを
    `code-review` スキルが自己実行し、**指摘の投稿も対応返信の投稿も同一アカウント
    （Claude セッションの GitHub アイデンティティ）** になる。そのため「ルート投稿者以外の
    返信」を条件にすると、本リポジトリの主要ユースケースで全スレッドが構造的に条件を
    満たしてしまい（対応済みでも投稿者が同じというだけで未解決と誤判定）、全 PR が
    `needs_response` に倒れる偽陽性の温床になっていた（PR #735 実測: 6 ルート + 同一投稿者
    による対応返信 6 件、全て解決済みなのに `(6, False, True)` を返していた）。

    スレッド再構成: `in_reply_to_id` が無い（None・キー欠落）コメントをルートとし、
    `in_reply_to_id` がそのルートの `id` と一致するコメントを返信として束ねる
    （GitHub REST は返信の `in_reply_to_id` を常にスレッドの起点コメント id にする仕様で、
    返信への返信でも中間の返信 id ではなくルート id を指す）。

    🔴 近似の限界（呼び出し元の docstring・summary にも明記すること）:
      - **偽陰性**: 返信は付いているが Resolve されていないスレッド（対応が不十分で
        再指摘を待っている場合など）は「解決」と数えてしまう。
      - **偽陰性**: 投稿者の異同では対応の有無を判定できない（上記の理由により、あえて
        投稿者比較を採らない設計判断。ルート投稿者自身の返信であっても解決扱いにする）。
      - **偽陽性**: 返信不要な単独コメント（レビュアーの補足・雑談等）が未解決として
        数えられる。GitHub の「一般コメント」的な使い方をしている場合に過大カウントし得る。
      - **偽陽性（設計判断・#805）**: `in_reply_to_id` が指す親コメントが取得結果に
        存在しない「孤児返信」は未解決側へ寄せる。GitHub はレビュースレッドのルート
        コメントだけの削除を許容し、削除済みルートは `pulls/{n}/comments` の応答から
        消える一方、残った返信の `in_reply_to_id` は削除済み id を指し続けるため、
        スレッドの解決状態を判定できない。見逃し（fail-open）より過大カウントを選ぶ。
        自己参照コメント（`id == in_reply_to_id`）もこの経路で孤児として吸収される。
      - ページング打ち切り（`_rest_get_all_pages` が上限到達で失敗を返す場合）は
        呼び出し元で「取得失敗」として扱われ、本関数自体には渡らない。
      - 想定外の要素形状（dict でない要素・`id`/`in_reply_to_id` が list/dict/set 等の
        unhashable 値）は 1 件ずつ読み飛ばす（近似値としての意味を保つため、1 要素の
        破損でスクリプト全体を落とさない・#805）。
    """
    roots: dict[int, dict] = {}
    replies_by_root: dict[int, list[dict]] = {}
    for c in comments:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if cid is None or isinstance(cid, (list, dict, set)):
            continue
        parent_id = c.get("in_reply_to_id")
        if isinstance(parent_id, (list, dict, set)):
            continue
        if parent_id is None:
            roots[cid] = c
        else:
            replies_by_root.setdefault(parent_id, []).append(c)

    unresolved = 0
    for root_id in roots:
        if not replies_by_root.get(root_id):
            unresolved += 1
    # 親（ルート）が取得結果に存在しない孤児返信は、スレッドの状態を判定できない。
    # 見逃し（fail-open）を避けるため未解決側へ寄せる（自己参照コメントもここに吸収される）。
    unresolved += len(set(replies_by_root) - set(roots))
    return unresolved


def _rest_unresolved_threads_approx(pr_number: int, token: str) -> tuple[bool, str]:
    """未解決レビュースレッド数の REST 近似版（第 2 層・#792）。

    `pulls/{n}/comments` を全ページ取得し `_approx_unresolved_from_comments` で近似する。
    戻り値は既存の第 2 層 getter（`_rest_pr_reviews` 等）と同じ規約（成功可否, JSON 文字列）。
    近似の限界は `_approx_unresolved_from_comments` の docstring を参照。
    """
    ok, items = _rest_get_all_pages(f"pulls/{pr_number}/comments", "", token, max_pages=3)
    if not ok:
        return False, items  # items はこの分岐では理由文字列
    count = _approx_unresolved_from_comments(items)
    return True, json.dumps({"count": count})


def get_unresolved_threads(pr_number: int) -> tuple[int, bool, bool]:
    """未解決のレビュースレッド数を取得する。戻り値は (件数, 正確に取得できたか, 近似値か)。

    第 1 層: `gh api graphql`（review thread の `isResolved`・正確な値）。
    第 2 層（#792）: 第 1 層が gh 到達不可で失敗した場合のみ、REST の `pulls/{n}/comments` から
    `_rest_unresolved_threads_approx` で近似値を算出する。クラウド無人 firing では `gh` が
    常に不在のため、第 2 層が無いと本関数は常に `(0, False, False)` を返し、
    `has_unresolved = False` → 未解決スレッドを抱えた PR が `needs_prompt`（即マージ対象）に
    紛れ込む fail-open が発生していた（Issue #792）。

    2 つ目の要素（正確に取得できたか）は近似成功時も **`False` のまま** にする。
    `isResolved` そのものは取れておらず「検証済み」と主張してはいけないため
    （呼び出し元 `analyze_pr` は 3 つ目の要素 `近似値か` を見て summary の文言を出し分ける）。
    第 1 層・第 2 層とも失敗した場合は `(0, False, False)`（現状と同じ fail-closed 表現）。

    不変条件（#805）: 2 つ目・3 つ目の bool は排他。取り得るのは
    `(True, False)`（gh 成功・正確）/ `(False, True)`（gh 失敗・REST 近似成功）/
    `(False, False)`（両層とも失敗）の 3 通りのみで、`(True, True)` は発生しない。

    NOTE（#805）: 他の getter（`get_pr_reviews` 等）と違い `run_gh(rest_fallback=...)` を
    経由せず `_run_gh_raw` を直接呼んでいるのは意図的な逸脱。`run_gh` の戻り値契約は
    `str` 1 個で「どの層で取得したか」を呼び出し元へ伝播できないため、本関数が返す
    3-tuple（正確に取得できたか・近似値か）の情報を `run_gh` 経由では表現できない。
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
    if gh_ok:
        output = gh_out
        if not output:
            return 0, True, False
        try:
            data = json.loads(output)
            threads = data.get("data", {}).get("repository", {}).get("pullRequest", {}).get("reviewThreads", {}).get("nodes", [])
            return sum(1 for t in threads if not t.get("isResolved", True)), True, False
        except (json.JSONDecodeError, KeyError, TypeError):
            # gh 自体は成功したが応答が破損 — 第 2 層は「gh 到達不可」時のみの対象なので、
            # ここでは従来どおり「取得失敗」として扱う（0 件成功に化けさせない）
            return 0, False, False

    print(
        f"WARNING: gh 到達不可のため未解決スレッド数を正確には取得できません（{gh_out}）。"
        "review thread の解決状態は GitHub GraphQL 専用で REST に等価エンドポイントが無いため、"
        "REST の返信有無から近似値を試みます（正確な isResolved ではありません）。",
        file=sys.stderr,
    )
    approx_ok, approx_out = _token_gated(_rest_unresolved_threads_approx, pr_number)
    if approx_ok:
        try:
            approx_count = json.loads(approx_out)["count"]
            print(
                f"WARNING: 未解決スレッド数は REST 近似値です（{approx_count}件・正確な isResolved は未検証）。"
                "必要なら mcp__github__pull_request_read 等で個別に確認してください。",
                file=sys.stderr,
            )
            return approx_count, False, True
        except (json.JSONDecodeError, KeyError, TypeError):
            print("WARNING: REST 近似フォールバックの応答解析に失敗しました", file=sys.stderr)
    else:
        print(f"WARNING: REST 近似フォールバックも失敗しました（{approx_out}）", file=sys.stderr)
    return 0, False, False


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


def select_step2_targets(results: list[dict]) -> list[dict]:
    """`sprint-cycle-router` 決定木 Step 2 の対象 PR を選ぶ純粋関数（#870）。

    背景: Step 2 の判定条件は長らく「`--mine --actionable-only` が非空」と `--mine` 限定で
    書かれていた。しかし Dependabot / `automation/gem-pool-refresh` の PR は bot が作るため
    PR 本文に自セッションの `Session-Id:` を持たず、`--mine` では **構造的に決して拾われない**。
    一方 `D-43`（`pr-review-flow-summary.md`）と本スクリプトの `_is_automation_pr()` /
    `_is_dependabot_pr()` は bot PR を回収する前提で揃っており、条文だけが閉じていた。

    選択の意味論（自スコープ優先 #47 を崩さない）:
      1. `is_mine` が真の要素が 1 件でもあれば、**それだけ** を返す（bot PR は返さない）
      2. `is_mine` が 0 件なら、`is_automation_pr` または `is_dependabot_pr` が真の要素だけを返す
      3. どちらも無ければ空リスト（＝**他者の人手 PR は決して返さない**）

    3 が本関数の眼目である。孤児 PR の全件回収は Step 2 の責務ではなく、他セッションが対応中の
    PR を奪わない不介入（CP-4・L-109）を条文だけでなく実装にも残す。

    `is_mine` は `main()` が全 PR へ無条件に設定し、`is_automation_pr` / `is_dependabot_pr` は
    `analyze_pr()` の **両方の return 経路** が必ず格納する。したがって 3 キーとも `.get()` の
    既定値に頼らず添字参照する（キー欠落は握り潰さず KeyError で表面化させる＝fail-closed）。
    呼び出し経路は `main()` と self-test だけである（他所から部分的な dict を渡さないこと）。
    """
    mine = [r for r in results if r["is_mine"]]
    if mine:
        return mine
    return [r for r in results if r["is_automation_pr"] or r["is_dependabot_pr"]]



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
            "unresolved_threads_approx": False,
            "bot_comments_count": 0,
            "has_gemini_review": False,
            "has_copilot_review": False,
            "gemini_quota_exceeded": False,
            "last_activity_min": 9999,
            "active_session": False,
            "owner_session_id": owner_session_id,
            "author_association": author_association,
            # #870: bot 自動化 PR 判定を戻り値へ載せる（select_step2_targets() の入力）。
            # 早期 return 経路でもキーを必ず持たせ、呼び出し側が .get() の既定値に頼らないようにする。
            "is_automation_pr": is_automation_pr,
            "is_dependabot_pr": is_dependabot_pr,
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

    # 未解決スレッド数（#790 指摘1: 取得成功可否も受け取り fail-open を防ぐ。
    # #792: 取得成功可否に加え「近似値か」も受け取る）
    unresolved, unresolved_ok, unresolved_approx = get_unresolved_threads(pr_number)
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
    # #792: REST 近似が効いた場合は「未検証」ではなく「近似値」であることが分かる文言にする
    # （近似が取れているのに毎回「取得できませんでした」とだけ出るのを避ける）。
    # status 判定は変えない（可視化と機械可読フラグのみで対処する）。
    if unresolved_threads_unknown:
        if unresolved_approx:
            summary = (
                f"⚠️ 未解決スレッド数は近似値（REST フォールバック・{unresolved}件・正確な isResolved は未検証）。"
                'マージ前に mcp__github__pull_request_read(method="get_review_comments") で確認すること。｜'
                + summary
            )
        else:
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
        "unresolved_threads_approx": unresolved_approx,
        "bot_comments_count": len(issue_comments),
        "has_gemini_review": has_gemini_review,
        "has_copilot_review": has_copilot_review,
        "gemini_quota_exceeded": gemini_quota_exceeded,
        "last_activity_min": last_activity_min,
        "active_session": active_session,
        "owner_session_id": owner_session_id,
        "author_association": author_association,
        # #870: bot 自動化 PR 判定を戻り値へ載せる（select_step2_targets() の入力）
        "is_automation_pr": is_automation_pr,
        "is_dependabot_pr": is_dependabot_pr,
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
    """`get_unresolved_threads` が gh 到達不可時に `(0, False, False)` を返すことを固定する
    （#790 指摘1・#792 で 3-tuple へ拡張）。

    修正前は成功可否を返さず常に `int`（0 件）を返しており、呼び出し元が「取得失敗」と
    「本当に 0 件」を区別できず fail-open していた（本来 `needs_response` になるはずの PR が
    `needs_prompt`/`awaiting_review` に落ちて自動マージ対象へ紛れ込む）。

    このテストは GH_TOKEN/GITHUB_TOKEN を明示的に未設定にし、第 2 層（REST 近似）も
    到達不可になる経路（token 未設定）を通す。第 2 層が実際に近似値を返す経路は
    `_test_get_unresolved_threads_rest_approx_layer` が別途検証する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    saved_env = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}

    try:
        # gh 到達不可 + token 未設定（第 2 層も不可） → (0, False, False)
        globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")
        got = get_unresolved_threads(1)
        if got != (0, False, False):
            failures.append(f"  get_unresolved_threads: gh失敗時 = {got!r} (expected (0, False, False))")

        # gh 成功 → (未解決件数, True, False)
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
        got2 = get_unresolved_threads(1)
        if got2 != (2, True, False):
            failures.append(f"  get_unresolved_threads: gh成功時 = {got2!r} (expected (2, True, False))")

        # gh は成功したが JSON 破損 → (0, False, False)（黙って 0 件成功に化けさせない。
        # 第 2 層は「gh 到達不可」時のみの対象なので、gh 成功時の応答破損では呼ばれない）
        globals()["_run_gh_raw"] = lambda args: (True, "not-json{{{")
        got3 = get_unresolved_threads(1)
        if got3 != (0, False, False):
            failures.append(f"  get_unresolved_threads: JSON解析失敗時 = {got3!r} (expected (0, False, False))")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    return failures


def _test_approx_unresolved_from_comments() -> list[str]:
    """`_approx_unresolved_from_comments` のスレッド再構成・近似ロジックを固定する（#792・
    PR #735 実測を受けて投稿者比較を撤廃した契約修正後の版・#805 で孤児返信検出と型防御を追加）。

    検査ロジック必須確認（#474）の反映:
      - 失敗経路（見逃し = 未解決なのに 0 と数える経路 / 過検知 = 解決済みなのに未解決と
        数える経路）: 返信ゼロ・同一投稿者の返信・他者の返信・`user` が None・
        `in_reply_to_id` キー欠落・**孤児返信（親ルートが取得結果に不在）**・
        **自己参照コメント（`id == in_reply_to_id`）** の各パターンを個別に検証する
      - 入力バリアント: 複数返信・bot 返信者・複数ルート混在の複合ケース、
        実 PR #735 のデータ形状（同一投稿者による指摘＋対応返信が並ぶ）、
        **非 dict 要素・unhashable な `id`/`in_reply_to_id`**（例外を投げず読み飛ばすこと）を含める
    """
    failures: list[str] = []

    def _comment(id_, in_reply_to, login):
        return {
            "id": id_,
            "in_reply_to_id": in_reply_to,
            "user": {"login": login} if login is not None else None,
        }

    cases: list[tuple[str, list[dict], int]] = [
        ("返信ゼロのスレッド1件のみ → 未解決1件", [_comment(1, None, "reviewer-a")], 1),
        (
            # 🔴 回帰ケース（当初の契約は「未解決のまま」を期待していたが、PR #735 実測により
            # 期待値を反転。本リポジトリの Layer 1 セルフレビューは指摘者と対応返信者が
            # 同一アカウントになるため、同一投稿者の返信でも「解決」として数えなければならない。
            "同一投稿者（自己）の返信あり → 解決として数える（投稿者の異同では判定しない）",
            [_comment(1, None, "reviewer-a"), _comment(2, 1, "reviewer-a")],
            0,
        ),
        (
            "他者の返信あり → 解決扱いで除外",
            [_comment(1, None, "reviewer-a"), _comment(2, 1, "author-b")],
            0,
        ),
        (
            "複数返信・bot返信者・複数ルート混在（返信があれば投稿者不問で解決扱い）",
            [
                _comment(1, None, "reviewer-a"),  # root1: 自己返信あり → 解決
                _comment(2, 1, "reviewer-a"),
                _comment(3, None, "reviewer-c"),  # root3: 他者(author-b)の返信あり → 解決
                _comment(4, 3, "author-b"),
                _comment(5, None, "gemini-code-assist[bot]"),  # root5: 返信ゼロ → 未解決
            ],
            1,
        ),
        (
            "user が None・in_reply_to_id キー欠落（両方 root 扱い・返信ゼロ）",
            [_comment(1, None, None), {"id": 2, "user": {"login": "author-b"}}],
            2,
        ),
        (
            "返信ゼロのルートが1件混ざる → 未解決1件",
            [
                _comment(10, None, "reviewer-a"),  # rootA: 同一投稿者返信あり → 解決
                _comment(11, 10, "reviewer-a"),
                _comment(12, None, "reviewer-a"),  # rootB: 返信ゼロ → 未解決
            ],
            1,
        ),
        (
            # 実データ回帰: PR #735 の実データ形状（ルート6件・各ルートに同一投稿者 kai-kou の
            # 対応返信が1件ずつ・計12コメント）。修正前の契約では (6, False, True) を返し
            # 全スレッド解決済みにもかかわらず全件未解決扱いになっていた欠陥の再発防止。
            "PR #735 の実データ形状（ルート6件・同一投稿者返信6件）→ 未解決0件",
            [
                c
                for i in range(1, 7)
                for c in (
                    _comment(3892971259 + i, None, "kai-kou"),
                    _comment(3893072380 + i, 3892971259 + i, "kai-kou"),
                )
            ],
            0,
        ),
        (
            # 🔴 CRITICAL 回帰ケース（#805）: 親ルートが取得結果に存在しない孤児返信。
            # GitHub はルートコメントだけの削除を許容するため実運用で起こり得る。
            # 修正前は roots だけを回すループで消えて 0 件（fail-open）になっていた。
            "孤児返信（親ルートが取得結果に不在）→ 未解決1件",
            [_comment(2, 1, "author-b")],
            1,
        ),
        (
            "自己参照コメント（id == in_reply_to_id）→ 孤児として未解決1件",
            [_comment(1, 1, "reviewer-a")],
            1,
        ),
        (
            "id 欠落コメントは読み飛ばし、正常なルートだけ集計 → 未解決1件",
            [
                {"id": None, "in_reply_to_id": None, "user": {"login": "x"}},
                _comment(1, None, "reviewer-a"),
            ],
            1,
        ),
        (
            "非 dict 要素・unhashable id/in_reply_to_id は例外を投げず読み飛ばす（#805）",
            [
                None,
                {"id": 1, "in_reply_to_id": ["x"], "user": {}},
                {"id": ["y"], "in_reply_to_id": None, "user": {}},
                _comment(2, None, "reviewer-a"),  # 正常なルートは引き続き集計される
            ],
            1,
        ),
    ]
    for label, comments, expected in cases:
        got = _approx_unresolved_from_comments(comments)
        if got != expected:
            failures.append(f"  _approx_unresolved_from_comments[{label}] = {got} (expected {expected})")
    return failures


def _test_get_unresolved_threads_rest_approx_layer() -> list[str]:
    """`get_unresolved_threads` の第 2 層（REST 近似）を検証する（#792）。

    gh (GraphQL) が失敗した場合のみ REST 近似層を試すこと、成功時は `(件数, False, True)`、
    失敗時は `(0, False, False)` を返すことを固定する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    orig_http_get = globals()["_http_get"]
    saved_env = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")

    try:
        # token あり + REST 近似成功 → (件数, False, True)
        os.environ["GH_TOKEN"] = "dummy-token-for-test"

        def _fake_http_get_ok(url, token):
            payload = [
                {"id": 1, "in_reply_to_id": None, "user": {"login": "reviewer-a"}},
                {"id": 2, "in_reply_to_id": 1, "user": {"login": "reviewer-a"}},  # 同一投稿者の返信 → 解決
                {"id": 3, "in_reply_to_id": None, "user": {"login": "reviewer-c"}},
                {"id": 4, "in_reply_to_id": 3, "user": {"login": "author-b"}},  # 他者返信 → 解決
                {"id": 5, "in_reply_to_id": None, "user": {"login": "reviewer-d"}},  # 返信ゼロ → 未解決
            ]
            return True, json.dumps(payload)

        globals()["_http_get"] = _fake_http_get_ok
        got_ok = get_unresolved_threads(2)
        if got_ok != (1, False, True):
            failures.append(f"  get_unresolved_threads: REST近似成功時 = {got_ok!r} (expected (1, False, True))")

        # token あり + REST 近似も失敗（HTTP エラー）→ (0, False, False)
        globals()["_http_get"] = lambda url, token: (False, "HTTP 403")
        got_fail = get_unresolved_threads(3)
        if got_fail != (0, False, False):
            failures.append(f"  get_unresolved_threads: REST近似も失敗時 = {got_fail!r} (expected (0, False, False))")

        # token 未設定 → REST 近似不可 → (0, False, False)
        os.environ.pop("GH_TOKEN", None)
        globals()["_http_get"] = _fake_http_get_ok  # token ガードで呼ばれないはず
        got_no_token = get_unresolved_threads(4)
        if got_no_token != (0, False, False):
            failures.append(f"  get_unresolved_threads: token未設定時 = {got_no_token!r} (expected (0, False, False))")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        globals()["_http_get"] = orig_http_get
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    return failures


def _test_get_unresolved_threads_layer1_success_skips_layer2() -> list[str]:
    """`get_unresolved_threads` は第 1 層（gh GraphQL）が成功したら第 2 層（REST 近似）を
    呼ばないことを固定する（#805）。

    第 2 層をスタブに差し替えて呼び出しフラグを立て、gh 成功パスで `(2, True, False)` を
    返しつつフラグが `False` のままであることを assert する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    orig_rest_approx = globals()["_rest_unresolved_threads_approx"]
    called = {"rest": False}

    def _stub_rest(pr_number, token):
        called["rest"] = True
        return True, json.dumps({"count": 99})

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
    globals()["_rest_unresolved_threads_approx"] = _stub_rest
    try:
        got = get_unresolved_threads(1)
        if got != (2, True, False):
            failures.append(f"  get_unresolved_threads: gh成功時 = {got!r} (expected (2, True, False))")
        if called["rest"] is not False:
            failures.append("  get_unresolved_threads: gh成功時に第2層（REST近似）が呼ばれてしまった")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        globals()["_rest_unresolved_threads_approx"] = orig_rest_approx
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


def _test_analyze_pr_unresolved_threads_approx() -> list[str]:
    """`analyze_pr` が REST 近似成功時、`unresolved_threads_approx` を可視化し summary に
    近似値であることを明示すること、および fail-open が塞がって `needs_response` に倒れる
    ことを固定する（#792 の狙いそのもの）。

    gh 到達不可 + token あり + REST 近似成功（未解決1件）を再現する。
    """
    failures: list[str] = []
    orig_run_gh_raw = globals()["_run_gh_raw"]
    orig_http_get = globals()["_http_get"]
    saved_env = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
    os.environ["GH_TOKEN"] = "dummy-token-for-test"
    globals()["_run_gh_raw"] = lambda args: (False, "gh 到達不可（テスト用スタブ）")

    def _fake_http_get(url, token):
        if "/pulls/" in url and "/comments" in url:
            payload = [{"id": 1, "in_reply_to_id": None, "user": {"login": "reviewer-a"}}]
            return True, json.dumps(payload)
        return True, json.dumps([])

    globals()["_http_get"] = _fake_http_get
    try:
        pr = {
            "number": 9002,
            "title": "テスト PR（REST近似）",
            "headRefName": "feat/y",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "author": {"login": "someone"},
            "authorAssociation": "OWNER",
            "reviewRequests": [],
            "labels": [],
            "body": "",
            "isCrossRepository": False,
        }
        result = analyze_pr(pr)
        if result.get("unresolved_threads_approx") is not True:
            failures.append(
                "  analyze_pr: unresolved_threads_approx が True にならない "
                f"(got {result.get('unresolved_threads_approx')!r})"
            )
        if result.get("unresolved_threads") != 1:
            failures.append(f"  analyze_pr: unresolved_threads = {result.get('unresolved_threads')!r} (expected 1)")
        summary = result.get("summary", "")
        if "近似値" not in summary:
            failures.append(f"  analyze_pr: summary に近似値である旨が書かれていない (summary={summary!r})")
        if result.get("status") != "needs_response":
            failures.append(
                f"  analyze_pr: status = {result.get('status')!r} (expected needs_response・"
                "fail-open修正の眼目=近似値でも needs_response に倒れること)"
            )
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        globals()["_http_get"] = orig_http_get
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


SELF_SESSION_ID_FOR_TEST = "11111111-2222-4333-8444-555555555555"
OTHER_SESSION_ID_FOR_TEST = "99999999-8888-4777-8666-555555555555"


def _fake_pr_for_step2(
    number: int,
    branch: str,
    author_login: str,
    author_association: str,
    session_id: str | None,
    is_cross_repository: bool | None = False,
) -> dict:
    """Step 2 対象選択テスト用の PR スキーマ（gh --json 相当）を組み立てる（#870）。"""
    body = f"Sprint Goal: x\nSession-Id: {session_id}\nsp:3" if session_id else "bot が作成した PR"
    return {
        "number": number,
        "title": f"テスト PR #{number}",
        "headRefName": branch,
        # 十分に古い作成日時にして elapsed_min >= ACTIVE_WINDOW_MIN（needs_prompt）へ倒す
        "createdAt": "2020-01-01T00:00:00Z",
        "labels": [],
        "body": body,
        "authorAssociation": author_association,
        "author": {"login": author_login},
        "isCrossRepository": is_cross_repository,
        "reviewRequests": [],
    }


def _test_select_step2_targets_pure() -> list[str]:
    """`select_step2_targets()` を純粋関数として直接検証する（#870）。

    境界の外側の負ケース（他者の人手 PR を拾わない・#750）を必ず含める。
    """
    failures: list[str] = []

    def rec(number: int, mine: bool, automation: bool, dependabot: bool) -> dict:
        return {
            "pr_number": number,
            "is_mine": mine,
            "is_automation_pr": automation,
            "is_dependabot_pr": dependabot,
        }

    mine_pr = rec(1, True, False, False)
    dependabot_pr = rec(2, False, False, True)
    automation_pr = rec(3, False, True, False)
    other_human_pr = rec(4, False, False, False)

    cases: list[tuple[str, list[dict], list[int]]] = [
        # (a) 自 PR あり + Dependabot PR あり → 自 PR のみ（--mine 優先が効いている）
        ("(a) mine + dependabot", [mine_pr, dependabot_pr], [1]),
        # (b) 自 PR なし + Dependabot PR あり → Dependabot が返る
        ("(b) dependabot only", [dependabot_pr], [2]),
        # (c) 自 PR なし + automation/gem-pool-refresh PR あり → その PR が返る
        ("(c) automation only", [automation_pr], [3]),
        # (d) 境界の外側の負ケース（#750）: 他者の人手 PR のみ → 空
        ("(d) other human only", [other_human_pr], []),
        # (e) 他者の人手 PR + Dependabot → Dependabot のみ（人手 PR は混ざらない）
        ("(e) other human + dependabot", [other_human_pr, dependabot_pr], [2]),
        # (f) 入力そのものが空 → 空
        ("(f) empty input", [], []),
        # 自 PR が複数あれば全件返す / bot は混ざらない
        (
            "(g) multiple mine + bots",
            [mine_pr, rec(5, True, False, False), dependabot_pr, automation_pr],
            [1, 5],
        ),
    ]
    for label, results, expected in cases:
        got = [r["pr_number"] for r in select_step2_targets(results)]
        if got != expected:
            failures.append(
                f"  select_step2_targets {label}: {got!r} (expected {expected!r})"
            )
    return failures


def _test_main_mine_or_automation_e2e() -> list[str]:
    """`main()` を経由して `--mine-or-automation` の選択・終了コード・stdout を貫通検証する（#870）。

    #686: 内部関数の直呼びだけでは CLI 入口の配線（フラグ無視・引数解釈）の退行を見逃すため、
    本番の主コードパス（argparse → get_open_prs → analyze_pr → select_step2_targets → stdout）を
    そのまま通す。#710: `run_gh` の fake に argv を記録させ、意図したサブコマンドが `main()` から
    実際に呼ばれていること（＝ analyze_pr へ到達していること）を assert する。
    """
    import contextlib

    failures: list[str] = []
    recorded_argv: list[list[str]] = []

    def fake_run_gh_raw(args: list[str]) -> tuple[bool, str]:
        recorded_argv.append(list(args))
        return (False, "gh 到達不可（テスト用スタブ）")

    orig_run_gh_raw = globals()["_run_gh_raw"]
    orig_http_get = globals()["_http_get"]
    orig_get_open_prs = globals()["get_open_prs"]
    orig_argv = sys.argv
    saved_env = {
        k: os.environ.pop(k, None)
        for k in ("GH_TOKEN", "GITHUB_TOKEN", "CLAUDE_CODE_SESSION_ID")
    }
    globals()["_run_gh_raw"] = fake_run_gh_raw
    # 第 2 層（REST 直叩き）も到達不可にして、補助情報は欠落したまま status 判定へ進ませる
    globals()["_http_get"] = lambda url, token: (False, "REST 到達不可（テスト用スタブ）")

    mine = _fake_pr_for_step2(101, "feat/mine", "kai-kou", "OWNER", SELF_SESSION_ID_FOR_TEST)
    dependabot = _fake_pr_for_step2(
        102, "dependabot/npm_and_yarn/next-15.5.1", "dependabot[bot]", "NONE", None
    )
    automation = _fake_pr_for_step2(
        103, "automation/gem-pool-refresh", "github-actions[bot]", "NONE", None
    )
    other_human = _fake_pr_for_step2(
        104, "feat/other", "someone-else", "OWNER", OTHER_SESSION_ID_FOR_TEST
    )
    # 入力バリアント（#474）: いずれも bot 判定の 3 条件 AND を満たさないため選ばれてはいけない
    dependabot_upper = _fake_pr_for_step2(
        105, "Dependabot/npm_and_yarn/next-15.5.1", "dependabot[bot]", "NONE", None
    )
    dependabot_fork_unknown = _fake_pr_for_step2(
        106,
        "dependabot/npm_and_yarn/next-15.5.2",
        "dependabot[bot]",
        "NONE",
        None,
        is_cross_repository=None,
    )
    automation_prefix = _fake_pr_for_step2(
        107, "automation/gem-pool-refresh-evil", "github-actions[bot]", "NONE", None
    )
    # 3 条件 AND のうち **③ 著者ログインだけ** が外れる負ケース（#870 敵対的検証の指摘1）。
    # ブランチ名と isCrossRepository は正しいので、著者比較が完全一致から前方一致・部分一致へ
    # 緩んだ瞬間にこれらが Step 2 の対象に混ざり、pr-review-watcher の無人マージ経路へ直行する。
    # `_is_dependabot_pr()` がブランチ名の前方一致を許してなお安全な理由は ③ であり、
    # ③ 自体をテストしていなければその安全性は一度も検証されていない。
    dependabot_author_suffix = _fake_pr_for_step2(
        110, "dependabot/npm_and_yarn/x-1.0", "dependabot[bot]-evil", "NONE", None
    )
    automation_author_trailing_space = _fake_pr_for_step2(
        111, "automation/gem-pool-refresh", "github-actions[bot] ", "NONE", None
    )
    dependabot_author_prefix = _fake_pr_for_step2(
        112, "dependabot/npm_and_yarn/x-1.0", "evil-dependabot[bot]", "NONE", None
    )

    def run_main(argv: list[str], prs: list[dict]) -> tuple[int, str, str]:
        globals()["get_open_prs"] = lambda: list(prs)
        sys.argv = ["check_pending_pr_reviews.py"] + argv
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                main()
        except SystemExit as e:  # noqa: PERF203 - テスト用
            code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    common = ["--mine-or-automation", "--actionable-only", "--session-id", SELF_SESSION_ID_FOR_TEST]
    e2e_cases: list[tuple[str, list[dict], list[int]]] = [
        # (a) 自 PR あり + Dependabot → 自 PR のみ
        ("(a) mine + dependabot", [mine, dependabot], [101]),
        # (b) 自 PR なし + Dependabot → Dependabot
        ("(b) dependabot only", [dependabot, other_human], [102]),
        # (c) 自 PR なし + automation → automation
        ("(c) automation only", [automation, other_human], [103]),
        # (d) 負ケース（#750）: 他者の人手 PR のみ → 空
        ("(d) other human only", [other_human], []),
        # (e) 他者の人手 PR + Dependabot → Dependabot のみ
        ("(e) other human + dependabot", [other_human, dependabot], [102]),
        # 入力バリアント: 大文字ブランチ・isCrossRepository 欠落・前方一致の偽物はいずれも選ばれない
        (
            "(variants) 3条件ANDを満たさない bot 風 PR",
            [dependabot_upper, dependabot_fork_unknown, automation_prefix, other_human],
            [],
        ),
        # 著者ログインだけが外れる負ケース（指摘1）。ブランチ・fork 条件は正しいので、
        # 著者比較が完全一致から緩んだときにだけ緑が壊れる（＝③ を単独で固定する）。
        (
            "(variants) 著者ログインだけ外れる bot 風 PR",
            [
                dependabot_author_suffix,
                automation_author_trailing_space,
                dependabot_author_prefix,
                other_human,
            ],
            [],
        ),
    ]
    try:
        for label, prs, expected in e2e_cases:
            code, out, _err = run_main(common, prs)
            if code != 0:
                failures.append(f"  main --mine-or-automation {label}: exit={code} (expected 0)")
            got = [int(m) for m in re.findall(r"^PENDING:(\d+):", out, flags=re.MULTILINE)]
            if got != expected:
                failures.append(
                    f"  main --mine-or-automation {label}: PENDING={got!r} (expected {expected!r})\n"
                    f"    stdout={out!r}"
                )
            if not expected and "NO_PENDING_PRS" not in out:
                failures.append(
                    f"  main --mine-or-automation {label}: 空選択なのに NO_PENDING_PRS が出ない (stdout={out!r})"
                )

        # (f) PR が 1 件も無い → NO_PENDING_PRS で正常終了（exit 0）。
        # check-tool-design-rules.md §2 の「対象 0 件は原則 fail-closed」の **例外** に該当する:
        # 本ツールは PR 前の品質ゲートではなくセッション復帰時の作業検出であり、
        # 「レビュー待ち PR が無い」は日常的に起こる正常状態だから（0 件で非ゼロにすると
        # 呼び出し元の決定木が毎 firing で異常扱いになる）。
        code, out, _err = run_main(common, [])
        if code != 0 or "NO_PENDING_PRS" not in out:
            failures.append(
                f"  main --mine-or-automation (f) PR 0 件: exit={code} stdout={out!r} "
                "(expected exit=0 / NO_PENDING_PRS)"
            )

        # JSON 出力でも同じ選択になること（--json の書式を壊していないこと）
        code, out, _err = run_main(common + ["--json"], [other_human, dependabot])
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = None
            failures.append(f"  main --mine-or-automation --json: JSON として解析不能 (stdout={out!r})")
        if parsed is not None:
            got_numbers = [r["pr_number"] for r in parsed]
            if got_numbers != [102]:
                failures.append(
                    f"  main --mine-or-automation --json: pr_number={got_numbers!r} (expected [102])"
                )
            elif not parsed[0].get("is_dependabot_pr"):
                failures.append(
                    "  main --mine-or-automation --json: is_dependabot_pr が JSON に載っていない "
                    f"({parsed[0].get('is_dependabot_pr')!r})"
                )

        # --mine（従来経路）は bot PR を拾わない（既存の意味論を壊していないことの回帰固定）
        code, out, _err = run_main(
            ["--mine", "--actionable-only", "--session-id", SELF_SESSION_ID_FOR_TEST],
            [dependabot, automation],
        )
        if "NO_PENDING_PRS" not in out:
            failures.append(f"  main --mine: bot PR を拾ってしまった (stdout={out!r})")

        # --mine と --mine-or-automation の同時指定は引数エラー（argparse 標準の exit 2）
        code, out, err = run_main(
            ["--mine", "--mine-or-automation", "--session-id", SELF_SESSION_ID_FOR_TEST],
            [mine],
        )
        if code != 2:
            failures.append(
                f"  main --mine --mine-or-automation 同時指定: exit={code} (expected 2)"
            )
        if "not allowed with" not in err and "mine-or-automation" not in err:
            failures.append(
                f"  main --mine --mine-or-automation 同時指定: エラーメッセージが不十分 (stderr={err!r})"
            )

        # analyze_pr の **早期 return 経路**（ラベルベース early_exit）でも is_automation_pr /
        # is_dependabot_pr が dict に載っていること（#870）。--actionable-only を付けないと
        # blocked ステータスの PR が select_step2_targets() へ届くため、キー欠落なら KeyError で落ちる。
        blocked_dependabot = _fake_pr_for_step2(
            108, "dependabot/pip/pyyaml-6.0.2", "dependabot[bot]", "NONE", None
        )
        blocked_dependabot["labels"] = [{"name": "status:blocked"}]
        blocked_automation = _fake_pr_for_step2(
            109, "automation/gem-pool-refresh", "github-actions[bot]", "NONE", None
        )
        blocked_automation["labels"] = [{"name": "status:waiting-user"}]
        code, out, err = run_main(
            ["--mine-or-automation", "--json", "--session-id", SELF_SESSION_ID_FOR_TEST],
            [blocked_dependabot, blocked_automation, other_human],
        )
        if code != 0:
            failures.append(
                f"  main --mine-or-automation（早期 return 経路）: exit={code} (expected 0) stderr={err[-200:]!r}"
            )
        else:
            try:
                parsed_blocked = json.loads(out)
            except json.JSONDecodeError:
                parsed_blocked = []
                failures.append(f"  早期 return 経路: JSON 解析不能 (stdout={out!r})")
            if [r["pr_number"] for r in parsed_blocked] != [108, 109]:
                failures.append(
                    f"  早期 return 経路: pr_number={[r.get('pr_number') for r in parsed_blocked]!r} (expected [108, 109])"
                )
            else:
                if not parsed_blocked[0].get("is_dependabot_pr"):
                    failures.append(
                        "  早期 return 経路: is_dependabot_pr が dict に載っていない "
                        f"({parsed_blocked[0].get('is_dependabot_pr')!r})"
                    )
                if not parsed_blocked[1].get("is_automation_pr"):
                    failures.append(
                        "  早期 return 経路: is_automation_pr が dict に載っていない "
                        f"({parsed_blocked[1].get('is_automation_pr')!r})"
                    )

        # セッション ID 不明のまま --mine-or-automation を使わせない（#870）。
        # is_mine が全件 False になり、自 PR があるのに bot PR を先に拾う優先順位の逆転が
        # 黙って起きるため、--mine と同じく exit 2 でエラーにする。
        code, out, err = run_main(["--mine-or-automation", "--actionable-only"], [mine, dependabot])
        if code != 2:
            failures.append(
                f"  main --mine-or-automation (セッション ID 無し): exit={code} (expected 2)"
            )
        if "--mine-or-automation" not in err:
            failures.append(
                f"  main --mine-or-automation (セッション ID 無し): エラー文にフラグ名が無い (stderr={err!r})"
            )

        # fake runner の argv 検証（#710）: main() が analyze_pr まで到達し、PR 番号付きの
        # gh サブコマンドを実際に発行していること（＝終了コードだけ差し替えた fake が
        # 判定結果を固定値へ潰す変異を見逃さないようにする）。
        if not recorded_argv:
            failures.append("  fake run_gh に 1 度も argv が記録されていない（main() が analyze_pr へ到達していない）")
        else:
            joined = [" ".join(a) for a in recorded_argv]
            if not any(a and a[0] == "api" for a in recorded_argv):
                failures.append(f"  fake run_gh argv: `api` サブコマンドが呼ばれていない ({joined[:3]!r})")
            # 選択された PR だけでなく、選択前に analyze_pr へ渡った PR も実際に解析されていること
            # （= main() のループが素通りせず本番経路を通っていること）
            for expected_fragment in ("pulls/101/reviews", "pulls/102/reviews", "pulls/104/reviews"):
                if not any(expected_fragment in j for j in joined):
                    failures.append(
                        f"  fake run_gh argv: {expected_fragment} の呼び出しが無い（analyze_pr 未到達の疑い）"
                    )
            # PR 一覧取得はテストスタブ側（get_open_prs）で差し替えているので gh へは出ないこと
            if any("pr list" in j for j in joined):
                failures.append(f"  fake run_gh argv: 想定外の `pr list` 呼び出し ({joined[:3]!r})")
    finally:
        globals()["_run_gh_raw"] = orig_run_gh_raw
        globals()["_http_get"] = orig_http_get
        globals()["get_open_prs"] = orig_get_open_prs
        sys.argv = orig_argv
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

    # 未解決スレッド REST 近似のスレッド再構成ロジック（#792・#805 で孤児返信検出・型防御を追加）
    approx_comments_failures = _test_approx_unresolved_from_comments()
    failures.extend(approx_comments_failures)
    APPROX_COMMENTS_CASE_COUNT = 11  # 返信ゼロ/同一投稿者返信(回帰・反転)/他者返信あり/複合ケース/user None・キー欠落/混在1件未解決/PR#735実データ形状/孤児返信/自己参照/id欠落読み飛ばし/非dict・unhashable読み飛ばし

    # get_unresolved_threads の第 2 層（REST 近似）フォールバック（#792）
    unresolved_rest_approx_failures = _test_get_unresolved_threads_rest_approx_layer()
    failures.extend(unresolved_rest_approx_failures)
    UNRESOLVED_REST_APPROX_CASE_COUNT = 3  # 近似成功 / 近似も失敗 / token未設定

    # gh (第1層) 成功時は REST 近似(第2層) を呼ばないことの固定（#805）
    layer1_skips_layer2_failures = _test_get_unresolved_threads_layer1_success_skips_layer2()
    failures.extend(layer1_skips_layer2_failures)
    LAYER1_SKIPS_LAYER2_CASE_COUNT = 2  # 件数の一致 / 第2層未呼び出しの確認

    # analyze_pr が unresolved_threads_unknown を可視化し summary 先頭に警告を差すことの固定（#790 指摘1）
    analyze_pr_unknown_failures = _test_analyze_pr_unresolved_threads_unknown()
    failures.extend(analyze_pr_unknown_failures)
    ANALYZE_PR_UNKNOWN_CASE_COUNT = 2  # unresolved_threads_unknown フラグ / summary 先頭の警告

    # analyze_pr が REST 近似成功時に unresolved_threads_approx / summary / needs_response を
    # 正しく反映すること（#792・fail-open 修正の眼目）
    analyze_pr_approx_failures = _test_analyze_pr_unresolved_threads_approx()
    failures.extend(analyze_pr_approx_failures)
    ANALYZE_PR_APPROX_CASE_COUNT = 4  # approxフラグ / 件数 / summary文言 / status=needs_response

    # get_open_prs() の REST フォールバック（getter レベル回帰・#790 指摘2）
    open_prs_fallback_failures = _test_get_open_prs_rest_fallback()
    failures.extend(open_prs_fallback_failures)
    OPEN_PRS_FALLBACK_CASE_COUNT = 7  # 件数1 + フィールド5 + labels1

    # get_pr_head_sha() の REST フォールバック（getter レベル回帰・#790 指摘2）
    head_sha_fallback_failures = _test_get_pr_head_sha_rest_fallback()
    failures.extend(head_sha_fallback_failures)
    HEAD_SHA_FALLBACK_CASE_COUNT = 1

    # Step 2 対象選択（#870）: 純粋関数の直接検証
    step2_pure_failures = _test_select_step2_targets_pure()
    failures.extend(step2_pure_failures)
    STEP2_PURE_CASE_COUNT = 7  # (a)〜(g)

    # Step 2 対象選択（#870）: main() を経由した貫通検証（#686 本番の主コードパス）
    step2_e2e_failures = _test_main_mine_or_automation_e2e()
    failures.extend(step2_e2e_failures)
    STEP2_E2E_CASE_COUNT = 19  # e2e 7 + 0件 + JSON + 早期return経路 3 + --mine 回帰 + 同時指定 + セッションID必須 2 + argv 3

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
        + APPROX_COMMENTS_CASE_COUNT
        + UNRESOLVED_REST_APPROX_CASE_COUNT
        + LAYER1_SKIPS_LAYER2_CASE_COUNT
        + ANALYZE_PR_UNKNOWN_CASE_COUNT
        + ANALYZE_PR_APPROX_CASE_COUNT
        + OPEN_PRS_FALLBACK_CASE_COUNT
        + HEAD_SHA_FALLBACK_CASE_COUNT
        + STEP2_PURE_CASE_COUNT
        + STEP2_E2E_CASE_COUNT
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
    # --mine と --mine-or-automation は選択の意味論が衝突するため同時指定できない
    # （argparse が exit 2 でエラーにする）。
    ownership_group = parser.add_mutually_exclusive_group()
    ownership_group.add_argument(
        "--mine",
        action="store_true",
        help=(
            "自セッションが作成した PR のみ出力する（PR 本文の Session-Id トレーラーが "
            "$CLAUDE_CODE_SESSION_ID と一致するもの・#47）。自 PR は所有者が常に対応可能なため "
            "active_session 除外を適用しない（時間ベースの穴を埋める積極的所有判定）。"
        ),
    )
    ownership_group.add_argument(
        "--mine-or-automation",
        action="store_true",
        help=(
            "sprint-cycle-router 決定木 Step 2 の対象を選ぶ（#870）。自 PR があればそれだけ、"
            "無ければ bot 自動化 PR（Dependabot / automation/gem-pool-refresh）だけを出力する。"
            "他者の人手 PR は決して出力しない（CP-4・L-109）。--mine とは同時指定できない。"
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

    # --mine 利用時はセッション ID が必須（誤って全 PR を自 PR 扱いしないため）。
    # --mine-or-automation も同様に必須にする（#870）。セッション ID が無いと is_mine が全件 False に
    # なり、自 PR があるのに bot PR を先に拾う優先順位の逆転が黙って起きるため。
    session_id = current_session_id(args.session_id)
    if (args.mine or args.mine_or_automation) and not session_id:
        flag = "--mine" if args.mine else "--mine-or-automation"
        print(
            f"ERROR: {flag} には $CLAUDE_CODE_SESSION_ID または --session-id が必要です "
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

    # Step 2 の対象選択（#870）。ループ内の active_session 除外は bot PR にも従来どおり適用済み
    # （is_mine には適用しない）。ここでは「自 PR 優先 / 無ければ bot 自動化 PR / 他者の人手 PR は返さない」
    # の選択だけを純粋関数へ委ねる。
    if args.mine_or_automation:
        results = select_step2_targets(results)

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
