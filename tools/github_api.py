#!/usr/bin/env python3
"""github_api.py — GitHub API「gh → urllib + GH_TOKEN/GITHUB_TOKEN」フォールバック共通モジュール（Issue #238）。

【背景】
「`gh` を試して失敗したら `urllib` + `GH_TOKEN`/`GITHUB_TOKEN` に落ちる」という多段フォールバックが、
少なくとも次の 5 ファイルに個別実装されていた（`tools/repo_slug.py` が owner/repo 解決を SSOT 化
したのと同じ問題が API 呼び出し層で未解決のまま残っていた・#238）。

- `tools/sprint_backlog_sync.py`（`_run_gh` / `_http_request`）
- `tools/check_deploy_gate.py`（`_run_gh` / 各 fetch 関数の token 解決 + REST フォールバック）
- `tools/github_push_helper.py`（`_token()`）
- `tools/triage_improvements.py`（`run_gh` / `_fetch_via_api`）
- `tools/check_claude_code_updates.py`（`fetch_issued_versions` / `create_issue` 内の gh 呼び出し・
  `_github_rest_get` / `_github_rest_post_issue` の token 解決）

## 集約したもの

- `resolve_token()`: `GH_TOKEN` → `GITHUB_TOKEN`（既定の優先順）の環境変数からトークンを解決する
  1 行パターン（全ファイルで文字通り同一のコードが繰り返されていた）。
- `run_gh()`: `subprocess.run(["gh"] + args, ...)` の実行・`FileNotFoundError`/`TimeoutExpired`/
  非 0 終了の 3 分岐を統一したラッパー（`sprint_backlog_sync._run_gh` / `check_deploy_gate._run_gh`
  と完全に同一実装だった。タイムアウト値だけ呼び出し元ごとに違う＝`timeout` 引数で吸収する）。
- `no_token_message()`: 「gh 失敗（{理由}）かつ GH_TOKEN/GITHUB_TOKEN 未設定」という、gh・トークン
  双方が使えないときの統一エラーメッセージ文言。
- `http_request()`: `Bearer` トークン + `X-GitHub-Api-Version` ヘッダで GET/POST する urllib 実装
  （`sprint_backlog_sync._http_request` と完全に同一。GET は `payload=None`、POST は JSON 文字列を渡す）。
- `http_get()`: 低レベル GET は `tools/github_rest.py`（Issue #602）の実装を再輸出する
  （二重実装を避ける。トークン任意・`X-GitHub-Api-Version` なしの最小 GET）。
- `rest_get_after_gh_failure()`: 「gh 側の失敗理由 `gh_err` が既にわかっている状態から、token を
  解決し、無ければ `no_token_message()` で打ち切り、あれば REST GET を試して結果 or
  『gh 失敗（...）・REST も失敗（...）』を返す」という、各呼び出し元で文字通り重複していた
  "GET フォールバックの後半部分" を集約したもの（完了条件の中核）。

## 集約しなかったもの（意図的・github_rest.py #602 と同じ判断基準）

- **gh の JSON 応答パース・フィールドマッピング**: `gh issue list --json number,title,state` の
  出力をどう解釈するかは呼び出し元ごとのビジネスロジックであり、API フォールバックの型ではない。
  `run_gh()` は raw stdout を返すところまでが責務。
- **ページネーションのループ制御**: `tools/github_rest.py` の `paginate_json_array()` が既に
  この責務を持つ（本モジュールはそれを再利用するだけで再実装しない）。
- **`tools/github_push_helper.py` の Contents API（PUT）**: 認証ヘッダが `Bearer` ではなく
  `token {token}` スキーム、かつ `gh` を一切試さない（push 403 のフォールバック専用ツールで
  最初から gh 経由の代替が無い設計）ため、`gh → urllib` フォールバックの形そのものに当てはまらない。
  トークン解決（`resolve_token()`）だけを共有し、リクエスト実装は独立のまま残す。
- **`tools/triage_improvements.py` の `_fetch_via_api` の while ループ**: `paginate_json_array()`
  と違い `max_pages` 上限を持たず「空バッチで打ち切り」のみで継続するファイル固有の設計
  （既存挙動を変えないため踏襲。per-page の HTTP 呼び出しだけ `http_get()` に寄せる）。

## self-test
    python3 tools/github_api.py --self-test
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import os  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from github_rest import http_get as _github_rest_http_get  # noqa: E402

DEFAULT_TOKEN_ENV_VARS: tuple[str, ...] = ("GH_TOKEN", "GITHUB_TOKEN")
DEFAULT_GH_TIMEOUT = 30
DEFAULT_REST_TIMEOUT = 30
DEFAULT_USER_AGENT = "gem-hunter-github-api"

# `run_gh()` が gh 自体の起動不能（＝実行すら出来ていない）を示すときに返す理由文字列。
# 非 0 終了時の stderr/stdout 文言とは区別する必要がある呼び出し元（例: 「gh はあるが
# 権限エラー」では警告ログを出し、「gh コマンドが無い」では出さない、という非対称挙動を
# 持つ呼び出し元・`tools/triage_improvements.py` / `tools/check_claude_code_updates.py`）が
# `is_gh_unavailable()` 経由で判定する。この定数がタプル文言の唯一の SSOT
# （2 箇所で逐語コピーされていた重複の解消・PR #849 Layer1 指摘3/5）。
GH_UNAVAILABLE_REASONS: tuple[str, ...] = (
    "gh コマンドが見つかりません",
    "gh コマンドがタイムアウトしました",
)


def is_gh_unavailable(reason: str) -> bool:
    """`run_gh()` の失敗理由が「gh 自体が起動できない」（`GH_UNAVAILABLE_REASONS` のいずれか）か。

    非 0 終了時の stderr/stdout 文言（gh は起動できたが失敗した）とは区別する。
    """
    return reason in GH_UNAVAILABLE_REASONS


def resolve_token(env_vars: tuple[str, ...] = DEFAULT_TOKEN_ENV_VARS) -> str | None:
    """`env_vars` を優先順に見て、最初に非空の値を持つ環境変数の値を返す。無ければ None。

    既存 5 ファイルで繰り返されていた `os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")`
    の一般化（呼び出し順は完全一致・値そのものはログ・エラー出力に一切出さない）。
    """
    for name in env_vars:
        v = os.environ.get(name)
        if v:
            return v
    return None


def no_token_message(gh_err: str, env_vars: tuple[str, ...] = DEFAULT_TOKEN_ENV_VARS) -> str:
    """gh・環境変数トークンの両方が使えないときの統一エラーメッセージ。"""
    return f"gh 失敗（{gh_err}）かつ {'/'.join(env_vars)} 未設定"


def run_gh(args: list[str], *, timeout: int = DEFAULT_GH_TIMEOUT) -> tuple[bool, str]:
    """`gh` サブプロセスを実行する。

    成功時 `(True, stdout.strip())`。失敗時 `(False, 理由)`。
    理由は「gh コマンドが見つかりません」/「gh コマンドがタイムアウトしました」/
    非 0 終了時の stderr（無ければ stdout、それも無ければ定型文）のいずれか
    （`sprint_backlog_sync._run_gh` / `check_deploy_gate._run_gh` と完全に同一の分岐）。
    """
    try:
        result = subprocess.run(
            ["gh"] + list(args), capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, "gh コマンドが見つかりません"
    except subprocess.TimeoutExpired:
        return False, "gh コマンドがタイムアウトしました"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or f"gh 実行失敗: {' '.join(args)}"
    return True, result.stdout.strip()


def http_get(
    url: str,
    token: str | None,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = DEFAULT_REST_TIMEOUT,
) -> tuple[bool, str]:
    """`tools/github_rest.py` の共通 GET への薄い再輸出（二重実装を避ける・#602 との整合）。"""
    return _github_rest_http_get(url, token, user_agent=user_agent, timeout=timeout)


def http_request(
    url: str,
    token: str,
    payload: str | None = None,
    *,
    timeout: int = DEFAULT_REST_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[bool, str]:
    """GitHub REST を GET（`payload=None`）または POST（`payload`=JSON 文字列）で叩く。

    🔴 token を **サブプロセスの引数に載せない**（`ps` / `/proc/<pid>/cmdline` 経由の露出防止）。
    `sprint_backlog_sync._http_request` と完全に同一の実装（`X-GitHub-Api-Version` ヘッダ付き・
    `Bearer` スキーム）。`http_get()` は `github_rest.http_get` への再輸出（`X-GitHub-Api-Version`
    無し・token 任意）なので、POST が要る・バージョンヘッダを付けたい呼び出し元はこちらを使う。
    """
    data = payload.encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": user_agent,
    }
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return True, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"接続失敗（{type(e).__name__}）"
    except TimeoutError:
        return False, "リクエストがタイムアウトしました"


def rest_get_after_gh_failure(
    gh_err: str,
    rest_url: str,
    *,
    rest_timeout: int = DEFAULT_REST_TIMEOUT,
    token_env_vars: tuple[str, ...] = DEFAULT_TOKEN_ENV_VARS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[bool, str]:
    """gh 側の失敗理由 `gh_err` が既にわかっている状態から、token 解決 → REST GET を試す。

    各呼び出し元で文字通り重複していたパターン（完了条件の中核）:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            return [], f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"
        ok2, out2 = _http_get(rest_url, token)
        if not ok2:
            return [], f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
        return True, out2

    `gh_err` を引数にするのは、呼び出し元の「gh 失敗」判定が `run_gh()` 自身の失敗だけでなく
    gh 成功後の JSON パース失敗（例: `gh の JSON 応答が不正`）も含むため（本関数の責務外の
    ビジネスロジック・github_rest.py の paginate_json_array を再利用しない理由と同じ設計判断）。
    """
    token = resolve_token(token_env_vars)
    if not token:
        return False, no_token_message(gh_err, token_env_vars)
    ok2, out2 = http_get(rest_url, token, timeout=rest_timeout, user_agent=user_agent)
    if not ok2:
        return False, f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
    return True, out2


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_resolve_token_priority() -> list[str]:
    failures = []
    saved = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN", "_GAPI_SELFTEST")}
    try:
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        if resolve_token() is not None:
            failures.append("両方未設定なら None を期待")

        os.environ["GITHUB_TOKEN"] = "fallback-token"
        if resolve_token() != "fallback-token":
            failures.append("GITHUB_TOKEN のみ設定時にそれが返らない")

        os.environ["GH_TOKEN"] = "primary-token"
        if resolve_token() != "primary-token":
            failures.append("GH_TOKEN が優先されない（両方設定時）")

        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ["_GAPI_SELFTEST"] = "custom"
        if resolve_token(env_vars=("_GAPI_SELFTEST",)) != "custom":
            failures.append("カスタム env_vars が使われない")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return failures


def _self_test_no_token_message_format() -> list[str]:
    failures = []
    msg = no_token_message("gh コマンドが見つかりません")
    if msg != "gh 失敗（gh コマンドが見つかりません）かつ GH_TOKEN/GITHUB_TOKEN 未設定":
        failures.append(f"既定文言が一致しない: {msg!r}")
    msg2 = no_token_message("x", env_vars=("A_TOKEN", "B_TOKEN"))
    if msg2 != "gh 失敗（x）かつ A_TOKEN/B_TOKEN 未設定":
        failures.append(f"カスタム env_vars 文言が一致しない: {msg2!r}")
    return failures


def _self_test_is_gh_unavailable() -> list[str]:
    """`GH_UNAVAILABLE_REASONS` / `is_gh_unavailable()` の SSOT 化（PR #849 Layer1 指摘3/5）。

    `run_gh()` が実際に返す 2 つの理由文字列（① FileNotFoundError ② TimeoutExpired）が
    そのまま `is_gh_unavailable()` で True になること、非 0 終了の stderr 文言は False の
    ままであることを確認する。呼び出し元（triage_improvements.py /
    check_claude_code_updates.py）が同じ定数を import して使うため、ここでの文言変更は
    両呼び出し元のテストにも波及する（SSOT が機能していることの裏付け）。
    """
    failures = []
    if not is_gh_unavailable("gh コマンドが見つかりません"):
        failures.append("FileNotFoundError 文言が is_gh_unavailable=True にならない")
    if not is_gh_unavailable("gh コマンドがタイムアウトしました"):
        failures.append("TimeoutExpired 文言が is_gh_unavailable=True にならない")
    if is_gh_unavailable("HTTP 403: Forbidden"):
        failures.append("非0終了時の stderr 文言が誤って is_gh_unavailable=True になった")
    if is_gh_unavailable(""):
        failures.append("空文字が誤って is_gh_unavailable=True になった")
    if tuple(GH_UNAVAILABLE_REASONS) != (
        "gh コマンドが見つかりません", "gh コマンドがタイムアウトしました",
    ):
        failures.append(f"GH_UNAVAILABLE_REASONS の中身が変わっている: {GH_UNAVAILABLE_REASONS!r}")
    return failures


def _self_test_run_gh_entrypoint() -> list[str]:
    """`run_gh()` を実際のエントリポイント（`subprocess.run`）から実測する（#710）。

    fake runner に argv 全体を記録させ、① `gh` が先頭に付与されている
    ② 渡した args がそのまま続く ③ `timeout` が呼び出し元の指定値で渡っている
    の 3 点を assert する（終了コードだけを差し替える fake は握り潰す変異の防止）。
    """
    failures = []
    orig_run = subprocess.run
    captured: list[dict] = []

    class _FakeCompleted:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run_ok(cmd, **kwargs):
        captured.append({"cmd": cmd, "kwargs": kwargs})
        return _FakeCompleted(0, stdout="hello\n")

    def fake_run_fail(cmd, **kwargs):
        captured.append({"cmd": cmd, "kwargs": kwargs})
        return _FakeCompleted(1, stderr="boom\n")

    def fake_run_not_found(cmd, **kwargs):
        raise FileNotFoundError()

    def fake_run_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

    try:
        # ① 成功
        captured.clear()
        subprocess.run = fake_run_ok
        ok, out = run_gh(["issue", "list", "-R", "o/r"], timeout=45)
        if not ok or out != "hello":
            failures.append(f"run_gh 成功: 期待 (True, 'hello') だが {(ok, out)!r}")
        if not captured or captured[0]["cmd"] != ["gh", "issue", "list", "-R", "o/r"]:
            failures.append(f"run_gh: argv が意図通りでない: {captured}")
        if captured and captured[0]["kwargs"].get("timeout") != 45:
            failures.append("run_gh: timeout 引数が subprocess.run に伝播していない")

        # ② 非 0 終了
        captured.clear()
        subprocess.run = fake_run_fail
        ok, out = run_gh(["issue", "list"])
        if ok is not False or out != "boom":
            failures.append(f"run_gh 非0終了: 期待 (False, 'boom') だが {(ok, out)!r}")

        # ③ gh 不在
        subprocess.run = fake_run_not_found
        ok, out = run_gh(["issue", "list"])
        if ok is not False or out != "gh コマンドが見つかりません":
            failures.append(f"run_gh 不在: 期待 (False, 'gh コマンドが見つかりません') だが {(ok, out)!r}")

        # ④ タイムアウト
        subprocess.run = fake_run_timeout
        ok, out = run_gh(["issue", "list"], timeout=5)
        if ok is not False or out != "gh コマンドがタイムアウトしました":
            failures.append(f"run_gh タイムアウト: 期待 (False, 'gh コマンドがタイムアウトしました') だが {(ok, out)!r}")
    finally:
        subprocess.run = orig_run
    return failures


def _self_test_http_request_entrypoint() -> list[str]:
    """`http_request()` を実際のエントリポイント（`urllib.request.urlopen`）から実測する。

    確認する分岐: ① GET（payload=None）→ Content-Type ヘッダなし・method GET
    ② POST（payload=JSON 文字列）→ Content-Type あり・method POST・body がそのまま送られる
    ③ Authorization: Bearer ④ X-GitHub-Api-Version ⑤ HTTPError → (False, "HTTP nnn")
    """
    failures = []
    orig_urlopen = urllib.request.urlopen
    captured: list[urllib.request.Request] = []

    class _FakeResponse:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self) -> bytes:
            return self._body

    def fake_urlopen_ok(req, timeout=None):
        captured.append(req)
        return _FakeResponse(b'{"ok": true}')

    def fake_urlopen_http_error(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable", {}, None)

    try:
        # ① GET
        captured.clear()
        urllib.request.urlopen = fake_urlopen_ok
        ok, out = http_request("https://api.github.com/repos/x/y/issues", "tok")
        if not ok or out != '{"ok": true}':
            failures.append(f"http_request GET: 期待 (True, ...) だが {(ok, out)!r}")
        req = captured[0]
        if req.get_method() != "GET":
            failures.append("http_request GET: method が GET でない")
        if req.get_header("Content-type") is not None:
            failures.append("http_request GET: Content-Type ヘッダを付けてはいけない")
        if req.get_header("Authorization") != "Bearer tok":
            failures.append("http_request: Authorization: Bearer ヘッダが付与されていない")
        if req.get_header("X-github-api-version") != "2022-11-28":
            failures.append("http_request: X-GitHub-Api-Version ヘッダが付与されていない")

        # ② POST
        captured.clear()
        ok, out = http_request(
            "https://api.github.com/repos/x/y/issues", "tok", payload='{"title": "t"}',
        )
        if not ok:
            failures.append(f"http_request POST: 成功を期待したが {(ok, out)!r}")
        req2 = captured[0]
        if req2.get_method() != "POST":
            failures.append("http_request POST: method が POST でない")
        if req2.data != b'{"title": "t"}':
            failures.append("http_request POST: body が意図通り送られていない")
        if req2.get_header("Content-type") is None:
            failures.append("http_request POST: Content-Type ヘッダが付与されていない")

        # ③ HTTPError
        urllib.request.urlopen = fake_urlopen_http_error
        ok, out = http_request("https://api.github.com/repos/x/y/issues", "tok")
        if ok is not False or out != "HTTP 422":
            failures.append(f"http_request HTTPError: 期待 (False, 'HTTP 422') だが {(ok, out)!r}")
    finally:
        urllib.request.urlopen = orig_urlopen
    return failures


def _self_test_rest_get_after_gh_failure() -> list[str]:
    """`rest_get_after_gh_failure()` の 3 分岐（token 無し / REST 失敗 / REST 成功）。"""
    failures = []
    saved = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
    orig_urlopen = urllib.request.urlopen

    class _FakeResponse:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self) -> bytes:
            return self._body

    try:
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)

        # ① token 無し
        ok, out = rest_get_after_gh_failure("gh の JSON 応答が不正", "https://api.github.com/x")
        if ok is not False or out != "gh 失敗（gh の JSON 応答が不正）かつ GH_TOKEN/GITHUB_TOKEN 未設定":
            failures.append(f"token 無し: 期待の統一メッセージと不一致: {(ok, out)!r}")

        # ② REST も失敗
        os.environ["GH_TOKEN"] = "t"
        urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(
            urllib.error.HTTPError(req.full_url, 500, "err", {}, None)
        )
        ok, out = rest_get_after_gh_failure("gh 実行失敗", "https://api.github.com/x")
        if ok is not False or out != "gh 失敗（gh 実行失敗）・REST も失敗（HTTP 500）":
            failures.append(f"REST も失敗: 期待の連結メッセージと不一致: {(ok, out)!r}")

        # ③ REST 成功
        urllib.request.urlopen = lambda req, timeout=None: _FakeResponse(b"[1,2,3]")
        ok, out = rest_get_after_gh_failure("gh 実行失敗", "https://api.github.com/x")
        if ok is not True or out != "[1,2,3]":
            failures.append(f"REST 成功: 期待 (True, '[1,2,3]') だが {(ok, out)!r}")
    finally:
        urllib.request.urlopen = orig_urlopen
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return failures


def _self_test_interference_run_gh_then_rest_fallback() -> list[str]:
    """干渉検証（#725）: `run_gh()` の失敗理由 → `rest_get_after_gh_failure()` の合成経路。

    実際の呼び出し元（`check_deploy_gate.fetch_merged_pr_commit_shas` 等）が使う実データフロー
    を通しで検証する: ① `run_gh()` が実際に失敗して理由文字列を返す ② その文字列が
    そのまま `gh_err` として `rest_get_after_gh_failure()` に渡っても改変されず最終メッセージに
    現れる ③ `resolve_token()` の優先順位（GH_TOKEN 優先）が `rest_get_after_gh_failure()` 経由でも
    保たれる、の 3 点を 1 本のテストで確認する（各関数の単体テストだけでは、片方の出力形式が
    他方の入力契約を壊していないかを検知できないため）。
    """
    failures = []
    orig_run = subprocess.run
    orig_urlopen = urllib.request.urlopen
    saved = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN")}

    class _FakeCompleted:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    class _FakeResponse:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self) -> bytes:
            return self._body

    try:
        # gh 実行そのものは成功するが returncode!=0（実運用でよくある「gh はあるが権限エラー」）
        subprocess.run = lambda cmd, **kw: _FakeCompleted(1, stderr="HTTP 403: Forbidden\n")
        os.environ["GH_TOKEN"] = "primary"
        os.environ["GITHUB_TOKEN"] = "secondary"

        gh_ok, gh_err = run_gh(["issue", "list", "-R", "o/r"])
        if gh_ok is not False or gh_err != "HTTP 403: Forbidden":
            failures.append(f"干渉検証: run_gh の失敗理由が想定外: {(gh_ok, gh_err)!r}")

        captured_auth: list[str | None] = []

        def fake_urlopen(req, timeout=None):
            captured_auth.append(req.get_header("Authorization"))
            return _FakeResponse(b'[{"number": 1}]')

        urllib.request.urlopen = fake_urlopen
        ok, out = rest_get_after_gh_failure(gh_err, "https://api.github.com/repos/o/r/issues")
        if ok is not True or out != '[{"number": 1}]':
            failures.append(f"干渉検証: REST フォールバック成功時の出力が不一致: {(ok, out)!r}")
        if captured_auth != ["Bearer primary"]:
            failures.append(
                f"干渉検証: GH_TOKEN が GITHUB_TOKEN より優先されていない（実送信ヘッダ: {captured_auth!r}）"
            )
    finally:
        subprocess.run = orig_run
        urllib.request.urlopen = orig_urlopen
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return failures


def _run_self_tests() -> int:
    tests = [
        ("resolve_token 優先順位", _self_test_resolve_token_priority),
        ("no_token_message 文言", _self_test_no_token_message_format),
        ("GH_UNAVAILABLE_REASONS / is_gh_unavailable SSOT", _self_test_is_gh_unavailable),
        ("run_gh エントリポイント", _self_test_run_gh_entrypoint),
        ("http_request エントリポイント", _self_test_http_request_entrypoint),
        ("rest_get_after_gh_failure 3分岐", _self_test_rest_get_after_gh_failure),
        ("干渉検証: run_gh → rest_get_after_gh_failure", _self_test_interference_run_gh_then_rest_fallback),
    ]
    all_failures: list[str] = []
    for name, fn in tests:
        failures = fn()
        if failures:
            for f in failures:
                all_failures.append(f"[{name}] {f}")
        else:
            print(f"  ✅ {name}")
    if all_failures:
        print("❌ github_api.py self-test 失敗:", file=sys.stderr)
        for f in all_failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("✅ github_api.py self-test 全て成功")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _run_self_tests()
    print("usage: python3 tools/github_api.py --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
