#!/usr/bin/env python3
"""cloudflare_api.py — Cloudflare REST API に共通のヘルパー

【背景（Issue #476・PR #460 レトロスペクティブ）】
`tools/retire_preview_aliases.py` の `should_fetch_next_page()` と
`tools/trigger_workers_build.py` の `should_fetch_next_worker_scripts_page()` は、
Cloudflare API の `result_info` を見てページングを継続するかどうかを判定する
**同一ロジックの独立したコピー** だった。各スクリプトの `--self-test` は自分のコピーしか
検証しないため、Cloudflare 側のページネーション仕様が変わって片方だけ直しても
`run_checks.sh` は緑のまま本番でだけ挙動が食い違う（`parse_worker_name` で実際に起きた経路）。

【背景（Issue #940）】
上記の述語共通化のあと、ページングの **ループ本体**（`page=1` から回す →
`success` 判定 → `result` を extend → 継続判定 → `break`）は
`trigger_workers_build.fetch_worker_scripts` / `retire_preview_aliases.fetch_versions` /
`check_cloudflare_cost.fetch_billable_usage` の 3 本に独立コピーのまま残っていた。
`fetch_all_pages()` へループ制御だけを寄せる（エンドポイントごとに違う HTTP 呼び出し・
`success` 判定・応答形式検証は呼び出し側の `page_fetcher` に残す）。

あわせて `trigger_workers_build._http_json` と `trigger_workers_build.ApiError` を
公開名（`http_json` / `CloudflareApiError`）で本モジュールへ移設した。読み取り専用の
`check_cloudflare_cost.py` が、`subprocess` / `wrangler_config` / `workers_build_diagnostics`
を抱えるデプロイ CLI（`trigger_workers_build.py`）へ import 時依存し、しかもアンダースコア
始まりの私的シンボルを跨モジュールで参照していたため。`trigger_workers_build.py` 側は
後方互換のため両名を再エクスポートする（`check_prod_drift.py` 等の既存 import を壊さない）。

【`wrangler_config.py` と分ける理由】
`wrangler_config.py` は「`wrangler.jsonc` を読む」責務で、API のページング判定とは関心が違う。
Cloudflare API に共通のヘルパーは本モジュールへ集約する（Issue #476 対応方針の案 2）。

【例外設計】
`should_fetch_next_page()` / `fetch_all_pages()` は `wrangler_config.py` と同じく特定 CLI の
例外型に依存しない純関数。`http_json()` だけは唯一の例外型として `CloudflareApiError` を
送出する（HTTP 呼び出しという副作用を持つ以上、失敗を表現する型が要るため）。

使い方:
    python3 tools/cloudflare_api.py --self-test    # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_secrets import mask_text  # noqa: E402

# 一覧取得の既定ページサイズ。#476 以前は退役スクリプトが 100・再トリガースクリプトが 50 と
# バラついていた（害は無いが共通化にあたり判断が要る）。Cloudflare の一覧系エンドポイントは
# `per_page` の上限が 100 なので、往復回数が最小になる 100 へ揃える。
# 実測（2026-09-03 JST・PR #856 Layer 1 セルフレビュー）: 50 から引き上げた側の
# `GET /accounts/{id}/workers/scripts?per_page=100&page=1` は `success: true` を返す（13 件）。
CF_PAGE_SIZE = 100


class CloudflareApiError(Exception):
    """Cloudflare API 呼び出しの失敗（呼び出し側は fail-closed の終了コードへ写像する）。

    旧 `trigger_workers_build.ApiError` の公開名移設（Issue #940）。`trigger_workers_build.py`
    は本クラスを `ApiError` として再エクスポートするため、既存の `except ApiError` /
    サブクラス化（`TriggerNotConfiguredApiError`）はそのまま動く。
    """


def http_json(
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Any:
    """HTTP して JSON をパースする共通ヘルパー（旧 `trigger_workers_build._http_json`）。

    `opener` は既定で `urllib.request.urlopen`。self-test では差し替えて、ネットワーク非依存に
    異常系（2xx + 不正 JSON・`HTTPError` + 非 JSON ボディ）を再現する
    （Layer 1 セルフレビュー WARNING-3・PR #460）。失敗はすべて `CloudflareApiError`（秘匿値は
    `mask_secrets.mask_text()` でマスク済み）に写像する。
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            # Cloudflare API は 4xx でも success:false の JSON ボディを返すことが多い
            # （呼び出し側で success を見て CloudflareApiError に変換する）。
            return parsed
        raise CloudflareApiError(mask_text(f"HTTP {error.code}: {body[:300]}")) from error
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise CloudflareApiError(mask_text(f"{type(error).__name__}: {error}")) from error


def should_fetch_next_page(result_info: dict[str, Any], fetched_count: int, page_item_count: int) -> bool:
    """Cloudflare API の `result_info`（page/per_page/count/total_count）を見て
    次ページを取得すべきか判定する（純粋関数）。

    実測（2026-08-20 JST・GET .../versions?per_page=100）: `result_info` はペイロード直下にあり、
    `{"page": 1, "per_page": 100, "count": 35, "total_count": 35}` の形。`total_pages` フィールドは
    無いため `total_count` との比較で継続判定する。

    🔴 **`result_info` の有無はエンドポイントごとに違う**（実測 2026-09-03 JST・PR #856）:
    `GET .../workers/scripts` は `success: true` でも `result_info` を返さない（キー自体が無い）。
    その場合は下の fail-safe（`total_count is None` → 打ち切り）に落ちるため、当該エンドポイントは
    **常に 1 ページ目で打ち切られる = `CF_PAGE_SIZE` が実質の取得上限** になる。ページングが効いて
    いる前提で読まないこと（100 件超のアカウントが現れたら Cloudflare 側の応答形式を再確認する）。
    """
    if page_item_count == 0:
        return False
    total_count = result_info.get("total_count")
    if total_count is None:
        # total_count が取れない応答は継続条件を判定できないため、無限ループを避けて打ち切る
        return False
    return fetched_count < total_count


def fetch_all_pages(
    page_fetcher: Callable[[int], tuple[list[Any], dict[str, Any]]],
) -> list[Any]:
    """ページングループの共通化（Issue #940）。

    `page=1` から始めて `should_fetch_next_page()` が真である間ページを取得し続ける
    **ループ制御だけ** を共通化する。`page_fetcher(page)` は「`page` 番目のページを取得し、
    `(このページのアイテム一覧, result_info)` を返す」関数で、HTTP 呼び出し・`success` 判定・
    応答形式の検証（本モジュールの関心の外にある、エンドポイントごとに違う失敗の意味づけ）は
    呼び出し側の `page_fetcher` にそのまま残す。

    #476 は継続判定の述語（`should_fetch_next_page`）だけを共通化し、ループ本体
    （`page=1` から回す → `result` を extend → 継続判定 → `break`）は
    `trigger_workers_build.fetch_worker_scripts` / `retire_preview_aliases.fetch_versions` /
    `check_cloudflare_cost.fetch_billable_usage` の 3 本に独立コピーのまま残っていた。
    """
    page = 1
    items: list[Any] = []
    while True:
        page_items, result_info = page_fetcher(page)
        items.extend(page_items)
        if not should_fetch_next_page(result_info or {}, len(items), len(page_items)):
            break
        page += 1
    return items


class _FakeHttpResponse:
    """`urllib.request.urlopen` の戻り値（context manager + `.read()`）を模倣する（self-test 専用。
    `http_json()` の異常系テスト用）。"""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _self_test_http_json() -> list[str]:
    """`http_json()`（旧 `trigger_workers_build._http_json`）の異常系がいずれも
    （マスク済みの）`CloudflareApiError` になることをネットワーク非依存に確認する
    （移設元 PR #460 WARNING-3 と同じケース）。"""
    failures: list[str] = []

    def opener_2xx_bad_json(request: Any, timeout: int = 30) -> _FakeHttpResponse:  # noqa: ARG001
        return _FakeHttpResponse(b"not-json")

    try:
        http_json("https://example.test/a", {}, opener=opener_2xx_bad_json)
        failures.append("http_json: 2xx + 不正 JSON なのに CloudflareApiError を送出していない")
    except CloudflareApiError:
        pass
    except Exception as error:  # noqa: BLE001
        failures.append(
            f"http_json: 2xx + 不正 JSON で CloudflareApiError 以外が飛んだ: "
            f"{type(error).__name__}: {error}"
        )

    def opener_http_error(request: Any, timeout: int = 30) -> Any:  # noqa: ARG001
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "Internal Server Error",
            None,
            io.BytesIO(b"Authorization: Bearer sk-abcdefghijklmnop1234567890 invalid"),
        )

    try:
        http_json("https://example.test/b", {}, opener=opener_http_error)
        failures.append("http_json: HTTPError + 非 JSON ボディなのに CloudflareApiError を送出していない")
    except CloudflareApiError as error:
        if "sk-abcdefghijklmnop1234567890" in str(error):
            failures.append("http_json: HTTPError のメッセージにトークンがマスクされず残っている")
    except Exception as error:  # noqa: BLE001
        failures.append(
            "http_json: HTTPError + 非 JSON ボディで CloudflareApiError 以外が飛んだ: "
            f"{type(error).__name__}: {error}"
        )

    # 2xx かつ success:false の JSON ボディ（4xx でも JSON を返す実運用と同じ形）はそのまま
    # dict を返す（呼び出し側が success を見て変換する。ここで例外化しない）。
    def opener_4xx_json_body(request: Any, timeout: int = 30) -> Any:  # noqa: ARG001
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", None,
            io.BytesIO(json.dumps({"success": False, "errors": []}).encode("utf-8")),
        )

    result = http_json("https://example.test/c", {}, opener=opener_4xx_json_body)
    if result != {"success": False, "errors": []}:
        failures.append(f"http_json: 4xx + JSON ボディをそのまま返していない: {result!r}")

    return failures


def _self_test_fetch_all_pages() -> list[str]:
    """`fetch_all_pages()` のループ制御（複数ページの結合・継続判定への委譲・停止条件）。"""
    failures: list[str] = []

    # 1) 2 ページで打ち切り、全アイテムを結合順に返す
    calls: list[int] = []

    def pager_two_pages(page: int) -> tuple[list[int], dict[str, Any]]:
        calls.append(page)
        if page == 1:
            return [1, 2], {"page": 1, "per_page": 2, "count": 2, "total_count": 3}
        return [3], {"page": 2, "per_page": 2, "count": 1, "total_count": 3}

    got = fetch_all_pages(pager_two_pages)
    if got != [1, 2, 3]:
        failures.append(f"fetch_all_pages: 複数ページの結合結果が想定外: {got}")
    if calls != [1, 2]:
        failures.append(f"fetch_all_pages: page 引数の連番が想定外（呼び出し順序の変異検出）: {calls}")

    # 2) 1 ページ目で完結するときは 1 回しか呼ばない（無駄な page=2 呼び出しをしない）
    single_calls: list[int] = []

    def pager_single_page(page: int) -> tuple[list[str], dict[str, Any]]:
        single_calls.append(page)
        return ["a", "b"], {"page": 1, "per_page": 100, "count": 2, "total_count": 2}

    got_single = fetch_all_pages(pager_single_page)
    if got_single != ["a", "b"]:
        failures.append(f"fetch_all_pages: 単一ページの結果が想定外: {got_single}")
    if single_calls != [1]:
        failures.append(f"fetch_all_pages: 単一ページで余計な呼び出しをしている: {single_calls}")

    # 3) 空ページで即座に打ち切る（無限ループ防止・should_fetch_next_page への委譲を固定）
    empty_calls: list[int] = []

    def pager_empty(page: int) -> tuple[list[Any], dict[str, Any]]:
        empty_calls.append(page)
        return [], {"page": 1, "per_page": 100, "total_count": 250}

    got_empty = fetch_all_pages(pager_empty)
    if got_empty != []:
        failures.append(f"fetch_all_pages: 空ページで結果が空でない: {got_empty}")
    if empty_calls != [1]:
        failures.append(f"fetch_all_pages: 空ページなのに 2 ページ目を取りに行っている: {empty_calls}")

    # 4) result_info が None（キー欠落等）でも例外にせず打ち切る（`or {}` のフォールバック）
    def pager_none_info(page: int) -> tuple[list[int], dict[str, Any]]:
        return [1], None  # type: ignore[return-value]

    got_none_info = fetch_all_pages(pager_none_info)
    if got_none_info != [1]:
        failures.append(f"fetch_all_pages: result_info=None で打ち切れていない: {got_none_info}")

    return failures


def _self_test_interference() -> list[str]:
    """干渉検証（#725）: `http_json` の公開名化と `fetch_all_pages` の共通化は独立した対策だが、
    実際の呼び出し側（`fetch_worker_scripts` 等）では同じデータフロー
    （`page_fetcher` の中で `http_json` を呼び、`CloudflareApiError` を送出する）を通る。

    片方の変更がもう片方の前提を壊していないかを、`fetch_all_pages` に「`http_json` 経由で
    `CloudflareApiError` を送出する `page_fetcher`」を渡して確認する（実際の呼び出し側と
    同じ形の統合。`fetch_all_pages` が例外を握りつぶして空リストへ丸めていないことを固定する）。
    """
    failures: list[str] = []

    def opener_500(request: Any, timeout: int = 30) -> Any:  # noqa: ARG001
        raise urllib.error.HTTPError(request.full_url, 500, "boom", None, io.BytesIO(b"not-json"))

    def page_fetcher(page: int) -> tuple[list[Any], dict[str, Any]]:
        # 実際の呼び出し側（fetch_worker_scripts 等）と同じ形: ページ取得の中で http_json を呼ぶ。
        payload = http_json(f"https://example.test/page{page}", {}, opener=opener_500)
        return payload.get("result") or [], payload.get("result_info") or {}

    try:
        fetch_all_pages(page_fetcher)
        failures.append(
            "fetch_all_pages: page_fetcher 内の CloudflareApiError を握りつぶしている"
            "（1 ページ目の失敗が空リストへ丸められた疑い）"
        )
    except CloudflareApiError:
        pass
    except Exception as error:  # noqa: BLE001
        failures.append(
            "fetch_all_pages: http_json の CloudflareApiError が別の例外型へ変質した: "
            f"{type(error).__name__}: {error}"
        )

    return failures


def _self_test() -> int:
    """ネットワーク不要のユニットテスト（旧 `retire_preview_aliases.py` セクション C と
    `trigger_workers_build.py` の `_self_test_should_fetch_next_worker_scripts_page()` を統合）。"""
    failures: list[str] = []
    cases = [
        (
            "1 ページで全件取得できたら継続しない（実測 total_count=35, per_page=100 相当）",
            {"page": 1, "per_page": 100, "count": 35, "total_count": 35},
            35,
            35,
            False,
        ),
        (
            "total_count が per_page を超えるなら継続する（100 件超の見落とし防止）",
            {"page": 1, "per_page": 100, "count": 100, "total_count": 250},
            100,
            100,
            True,
        ),
        (
            "累積が total_count に達したら継続しない（最終ページ）",
            {"page": 3, "per_page": 100, "count": 50, "total_count": 250},
            250,
            50,
            False,
        ),
        (
            "このページが 0 件なら継続しない（無限ループ防止）",
            {"page": 5, "per_page": 100, "total_count": 250},
            200,
            0,
            False,
        ),
        (
            "total_count が取れない応答は継続しない（fail-safe・無限ループ防止）",
            {"page": 1, "per_page": 100, "count": 10},
            10,
            10,
            False,
        ),
        # workers/scripts 側（旧 per_page=50）の形も同じ関数で判定できることを固定する。
        (
            "per_page が 50 でも判定は変わらない（21 件以上の Worker の見落とし防止）",
            {"page": 1, "per_page": 50, "count": 50, "total_count": 120},
            50,
            50,
            True,
        ),
        (
            "per_page が 50 の最終ページで継続しない",
            {"page": 3, "per_page": 50, "count": 20, "total_count": 120},
            120,
            20,
            False,
        ),
    ]
    for label, result_info, fetched_count, page_item_count, expected in cases:
        got = should_fetch_next_page(result_info, fetched_count, page_item_count)
        if got != expected:
            failures.append(f"{label}: 期待 {expected} / 実際 {got}")

    # 定数のリグレッションガード。`should_fetch_next_page` のロジックテストではないため、
    # 関数側をどう変異させてもこの行は落ちない（変異テストの被覆評価で数に入れない）。
    if CF_PAGE_SIZE > 100:
        failures.append(f"CF_PAGE_SIZE={CF_PAGE_SIZE} は Cloudflare の per_page 上限 100 を超えている")

    check_count = len(cases)

    groups = [
        ("http_json の異常系（不正 JSON / HTTPError / 4xx+JSON はそのまま返す）", _self_test_http_json),
        ("fetch_all_pages のループ制御（複数ページ・単一ページ・空ページ・result_info=None）",
         _self_test_fetch_all_pages),
        # 干渉検証（#725）: http_json 公開名化と fetch_all_pages 共通化は独立した対策だが、
        # 同じデータフロー（ページ取得 → CloudflareApiError の捕捉）を通る。
        # 片方が他方の前提を壊していないかを固定する。
        ("干渉検証: fetch_all_pages 内で http_json の CloudflareApiError が伝搬する",
         _self_test_interference),
    ]
    for name, fn in groups:
        group_failures = fn()
        if group_failures:
            failures.extend(f"[{name}] {f}" for f in group_failures)
        check_count += 1

    if failures:
        print("セルフテスト: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"セルフテスト: 全 {check_count} ケース PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cloudflare API 共通ヘルパー（単独 CLI としては --self-test 専用）。"
    )
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテスト")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
