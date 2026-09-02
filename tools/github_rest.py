#!/usr/bin/env python3
"""github_rest.py — GitHub REST API 共通ヘルパー（Issue #602）

`tools/` 配下に独立して何度も再実装されていた「urllib + GH_TOKEN で GitHub REST を GET し、
`per_page=100` でページネーションし、`"pull_request" in item` で PR を除外する」パターンのうち、
**実装が本当に同型と確認できたもの** だけを集約する。

## 集約したもの

- `http_get()`: urllib.request で GET するだけの最小 GET
  （`tools/check_deploy_gate.py` / `tools/check_roadmap_status.py` の `_http_get` と同一実装だった）。
- `paginate_json_array()`: `fetch_page(page) -> (ok, raw_json_str)` を呼び出し JSON 配列を
  結合するページネーションループ。**HTTP 層に依存しない**設計にすることで、各呼び出し元が
  self-test でモック差し替えるために持つ module-level の `_http_get` / `_http_request` を
  そのまま温存できる（DI 経路を壊さない）。打ち切り時の挙動は `on_truncate` で選ぶ:
  - `"error"`（既定・fail-closed）: 最終ページがちょうど `per_page` 件（＝続きがある可能性を
    否定できない）なら `(False, 理由)` を返す。`check_roadmap_status.fetch_all_issues` /
    `sprint_backlog_sync` の既存挙動。
  - `"stop"`（fail-open）: 同じ状況でも取得済み分をそのまま `(True, items)` として返す。
    `check_deploy_gate.py` の 2 関数・`check_claude_code_updates.py` の既存挙動
    （挙動を変えない集約のため、呼び出し元ごとの既存方針をそのまま選べるようにしてある。
    fail-open が安全側とは限らない点は呼び出し元の docstring に既に注記されている）。
- `exclude_pull_requests()`: `/issues` エンドポイント応答から `pull_request` キーを持つ要素
  （PR）を除外する。

## 集約しなかったもの（同型に見えて実は違う・Issue #602 対応方針1）

- **`tools/check_pending_pr_reviews.py` の `_rest_get_all_pages`**: 本モジュールの
  `paginate_json_array` と最終的には同型（`fetch_page` を HTTP 層から切り離せば同じ形）だが、
  同ファイル内 5 箇所で再利用される self-test 済みのローカル実装として、追加済みのコード
  コメントで既に「Issue #602 が扱う共通ページネーションモジュール化のスコープには入らない、
  本ファイル内に閉じた最小実装（YAGNI）」と判断が記録されている。`globals()["_http_get"]`
  差し替えに依存する self-test（`_test_rest_pagination`）が既に整備済みで、移行して得られる
  重複削減（1 ファイル内で完結している）に対して差分・再テストのリスクが見合わないため、
  既存の判断を踏襲し変更しない。
- **`tools/generate_project_context.py` の `fetch_open_issues`**: `urllib` + `GH_TOKEN` では
  なく `gh api` サブプロセス経由で認証する別系統（クラウドでは gh 不在のため通常必ず失敗する
  ことを前提にした設計・#338/#342）。かつ 2 ページ目以降の失敗を「取得済み分で打ち切り」と
  fail-open で許容する点が、他の実装（打ち切りを検知したら fail-closed でエラーにする、または
  `on_truncate="stop"` で明示的に許容する）と設計思想の出発点から違う。認証方式もエラー処理
  方針も異なるため集約しない。
- **`tools/analyze_pr_review_comments.py`**: `gh api ... --paginate` という gh CLI 組み込みの
  ページネーションフラグを使っており、独自ループの実装がそもそも存在しない。
- **`tools/retire_preview_aliases.py`**: GitHub ではなく Cloudflare API のページネーション。
  継続判定が `len(batch) < per_page` ではなく応答直下の `result_info`
  （`page`/`per_page`/`count`/`total_count`）を見る、全く別のレスポンス形状
  （#476 と同系列の Cloudflare API）。「ページネーションという言葉が同じでも判定ロジックが
  違う」実例のため、意図的に分けたままにする。

## self-test
    python3 tools/github_rest.py --self-test
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Callable

DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "gem-hunter-github-rest"


def http_get(
    url: str,
    token: str | None,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = DEFAULT_TIMEOUT,
    accept: str = "application/vnd.github+json",
) -> tuple[bool, str]:
    """GitHub REST を GET する。

    token をサブプロセス引数に載せず Python プロセス内でヘッダを組み立てる
    （`ps` / `/proc/<pid>/cmdline` 経由の露出防止・既存パターン踏襲）。

    `token` は None・空文字を許容する（その場合 Authorization ヘッダを付けず匿名リクエストに
    する。`check_claude_code_updates.py` の `_github_rest_get` が未認証でも動く公開エンドポイント
    に使っている既存挙動を保つ）。
    """
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": user_agent,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return True, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"接続失敗（{type(e).__name__}）"
    except TimeoutError:
        return False, "リクエストがタイムアウトしました"


def paginate_json_array(
    fetch_page: Callable[[int], tuple[bool, str]],
    *,
    per_page: int = 100,
    max_pages: int,
    on_truncate: str = "error",
) -> tuple[bool, list | str]:
    """`fetch_page(page) -> (ok, raw_json_str)` を `page=1` から呼び出し、JSON 配列を結合する。

    - 各ページの `fetch_page` が失敗（`ok=False`）を返したら、その理由をそのまま伝播する。
    - JSON デコード失敗・配列でない応答は `(False, 理由)`。
    - 返却件数が `per_page` 未満になった時点で「これが最終ページ」とみなして正常終了する。
    - `max_pages` に到達してもなお最終ページがちょうど `per_page` 件（＝まだ続きがある可能性を
      否定できない）場合の挙動は `on_truncate` で選ぶ:
        - `"error"`: `(False, "ページネーション上限（N ページ）に達し、全件取得を保証できません")`
        - `"stop"`: 取得済み分をそのまま `(True, items)` として返す
    """
    if on_truncate not in ("error", "stop"):
        raise ValueError(f"on_truncate は 'error' か 'stop' のいずれか: {on_truncate!r}")

    items: list = []
    for page in range(1, max_pages + 1):
        ok, out = fetch_page(page)
        if not ok:
            return False, out
        try:
            batch = json.loads(out)
        except json.JSONDecodeError:
            return False, "REST 応答の JSON 解析に失敗しました"
        if not isinstance(batch, list):
            return False, "REST 応答が配列ではありません"
        items.extend(batch)
        if len(batch) < per_page:
            return True, items
        if page == max_pages:
            if on_truncate == "error":
                return False, (
                    f"ページネーション上限（{max_pages} ページ）に達し、"
                    "全件取得を保証できません（判定不能）"
                )
            return True, items
    return True, items  # pragma: no cover — max_pages>=1 なら上のループ内で必ず return する


def exclude_pull_requests(items: list[dict]) -> list[dict]:
    """`/issues` エンドポイントの応答から PR（`pull_request` キーを持つ要素）を除外する。

    GitHub REST の `GET /repos/{owner}/{repo}/issues` は Issue と PR を区別せず返すため、
    PR を除外したい呼び出し元はこのフィルタを適用する。
    """
    return [i for i in items if "pull_request" not in i]


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_paginate_single_page() -> list[str]:
    failures = []
    calls: list[int] = []

    def fetch_page(page: int) -> tuple[bool, str]:
        calls.append(page)
        return True, json.dumps([{"id": 1}, {"id": 2}])

    ok, items = paginate_json_array(fetch_page, per_page=100, max_pages=5)
    if not ok or items != [{"id": 1}, {"id": 2}]:
        failures.append(f"単一ページ: 期待 (True, 2件) だが {(ok, items)!r}")
    if calls != [1]:
        failures.append(f"単一ページ: 2 ページ目以降を呼んではいけない（呼び出し履歴 {calls!r}）")
    return failures


def _self_test_paginate_multi_page_combine() -> list[str]:
    failures = []

    def fetch_page(page: int) -> tuple[bool, str]:
        if page == 1:
            return True, json.dumps([{"id": i} for i in range(100)])
        if page == 2:
            return True, json.dumps([{"id": 100}, {"id": 101}])
        return True, json.dumps([])  # 呼ばれてはいけない

    ok, items = paginate_json_array(fetch_page, per_page=100, max_pages=5)
    if not ok or len(items) != 102:
        failures.append(f"複数ページ結合: 期待 (True, 102件) だが ok={ok}, len={len(items) if isinstance(items, list) else items!r}")
    return failures


def _self_test_paginate_truncate_error() -> list[str]:
    """最終ページがちょうど per_page 件で max_pages に到達 → on_truncate='error' はエラー
    （#790 と同種の「取りこぼしを 0 件・完了に化けさせない」ガード）。"""
    failures = []

    def fetch_page(page: int) -> tuple[bool, str]:
        return True, json.dumps([{"id": page}] * 100)

    ok, reason = paginate_json_array(fetch_page, per_page=100, max_pages=2, on_truncate="error")
    if ok is not False or "ページネーション上限" not in str(reason):
        failures.append(f"打ち切り(error): 期待 (False, 'ページネーション上限...') だが {(ok, reason)!r}")
    return failures


def _self_test_paginate_truncate_stop() -> list[str]:
    """同じ状況で on_truncate='stop' は取得済み分をそのまま返す（check_deploy_gate.py の既存挙動）。"""
    failures = []

    def fetch_page(page: int) -> tuple[bool, str]:
        return True, json.dumps([{"id": page}] * 100)

    ok, items = paginate_json_array(fetch_page, per_page=100, max_pages=2, on_truncate="stop")
    if ok is not True or not isinstance(items, list) or len(items) != 200:
        failures.append(f"打ち切り(stop): 期待 (True, 200件) だが {(ok, items)!r}")
    return failures


def _self_test_paginate_fetch_failure_propagates() -> list[str]:
    failures = []

    def fetch_page(page: int) -> tuple[bool, str]:
        if page == 1:
            return True, json.dumps([{"id": i} for i in range(100)])
        return False, "HTTP 502"

    ok, reason = paginate_json_array(fetch_page, per_page=100, max_pages=5)
    if ok is not False or reason != "HTTP 502":
        failures.append(f"ページ取得失敗の伝播: 期待 (False, 'HTTP 502') だが {(ok, reason)!r}")
    return failures


def _self_test_paginate_invalid_json() -> list[str]:
    failures = []

    def fetch_page(page: int) -> tuple[bool, str]:
        return True, "{not json"

    ok, reason = paginate_json_array(fetch_page, per_page=100, max_pages=1)
    if ok is not False or "JSON 解析" not in str(reason):
        failures.append(f"不正 JSON: 期待 (False, 'JSON 解析に失敗...') だが {(ok, reason)!r}")
    return failures


def _self_test_paginate_non_array_response() -> list[str]:
    failures = []

    def fetch_page(page: int) -> tuple[bool, str]:
        return True, json.dumps({"message": "not an array"})

    ok, reason = paginate_json_array(fetch_page, per_page=100, max_pages=1)
    if ok is not False or "配列ではありません" not in str(reason):
        failures.append(f"非配列応答: 期待 (False, '...配列ではありません') だが {(ok, reason)!r}")
    return failures


def _self_test_paginate_invalid_on_truncate() -> list[str]:
    failures = []
    try:
        paginate_json_array(lambda page: (True, "[]"), max_pages=1, on_truncate="bogus")
        failures.append("on_truncate 不正値: ValueError を期待したが例外が発生しなかった")
    except ValueError:
        pass
    return failures


def _self_test_exclude_pull_requests() -> list[str]:
    failures = []
    items = [
        {"number": 1, "title": "Issue"},
        {"number": 2, "title": "PR", "pull_request": {"url": "x"}},
        {"number": 3, "title": "Issue2"},
    ]
    got = exclude_pull_requests(items)
    want_numbers = [1, 3]
    if [i["number"] for i in got] != want_numbers:
        failures.append(f"PR除外: 期待 番号{want_numbers} だが {[i['number'] for i in got]!r}")
    return failures


def _self_test_http_get_entrypoint() -> list[str]:
    """`http_get()` を実際のエントリポイントから実測する（`urllib.request.urlopen` をモック）。

    確認する分岐: ① token あり → Authorization ヘッダを付与 ② token なし → 付与しない
    （`check_claude_code_updates.py` の匿名リクエスト対応の回帰防止）③ HTTPError → (False, "HTTP nnn")
    ④ URLError → (False, "接続失敗...")。
    """
    failures = []
    orig_urlopen = urllib.request.urlopen
    captured_requests: list[urllib.request.Request] = []

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
        captured_requests.append(req)
        return _FakeResponse(b'[{"id": 1}]')

    def fake_urlopen_http_error(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    def fake_urlopen_url_error(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    try:
        # ① token あり
        captured_requests.clear()
        urllib.request.urlopen = fake_urlopen_ok
        ok, out = http_get("https://api.github.com/repos/x/y/issues", "secret-token")
        if not ok or out != '[{"id": 1}]':
            failures.append(f"http_get token あり: 期待 (True, '[{{...}}]') だが {(ok, out)!r}")
        if not captured_requests or captured_requests[0].get_header("Authorization") != "Bearer secret-token":
            failures.append("http_get token あり: Authorization ヘッダが付与されていない")

        # ② token なし（匿名リクエスト・既存挙動の回帰防止）
        captured_requests.clear()
        ok, out = http_get("https://api.github.com/repos/x/y/issues", None)
        if not ok:
            failures.append(f"http_get token なし: 成功を期待したが {(ok, out)!r}")
        if captured_requests and captured_requests[0].get_header("Authorization") is not None:
            failures.append("http_get token なし: Authorization ヘッダを付けてはいけない")

        # ③ HTTPError
        urllib.request.urlopen = fake_urlopen_http_error
        ok, out = http_get("https://api.github.com/repos/x/y/issues", "t")
        if ok is not False or out != "HTTP 404":
            failures.append(f"http_get HTTPError: 期待 (False, 'HTTP 404') だが {(ok, out)!r}")

        # ④ URLError
        urllib.request.urlopen = fake_urlopen_url_error
        ok, out = http_get("https://api.github.com/repos/x/y/issues", "t")
        if ok is not False or "接続失敗" not in out:
            failures.append(f"http_get URLError: 期待 (False, '接続失敗...') だが {(ok, out)!r}")
    finally:
        urllib.request.urlopen = orig_urlopen

    return failures


def _run_self_tests() -> int:
    tests = [
        ("単一ページで完結", _self_test_paginate_single_page),
        ("複数ページ結合", _self_test_paginate_multi_page_combine),
        ("打ち切り: on_truncate=error", _self_test_paginate_truncate_error),
        ("打ち切り: on_truncate=stop", _self_test_paginate_truncate_stop),
        ("ページ取得失敗の伝播", _self_test_paginate_fetch_failure_propagates),
        ("不正 JSON 応答", _self_test_paginate_invalid_json),
        ("非配列応答", _self_test_paginate_non_array_response),
        ("on_truncate 不正値", _self_test_paginate_invalid_on_truncate),
        ("PR 除外", _self_test_exclude_pull_requests),
        ("http_get エントリポイント", _self_test_http_get_entrypoint),
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
        print("❌ github_rest.py self-test 失敗:", file=sys.stderr)
        for f in all_failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("✅ github_rest.py self-test 全て成功")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _run_self_tests()
    print("usage: python3 tools/github_rest.py --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
