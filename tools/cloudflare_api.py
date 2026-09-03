#!/usr/bin/env python3
"""cloudflare_api.py — Cloudflare REST API に共通のヘルパー

【背景（Issue #476・PR #460 レトロスペクティブ）】
`tools/retire_preview_aliases.py` の `should_fetch_next_page()` と
`tools/trigger_workers_build.py` の `should_fetch_next_worker_scripts_page()` は、
Cloudflare API の `result_info` を見てページングを継続するかどうかを判定する
**同一ロジックの独立したコピー** だった。各スクリプトの `--self-test` は自分のコピーしか
検証しないため、Cloudflare 側のページネーション仕様が変わって片方だけ直しても
`run_checks.sh` は緑のまま本番でだけ挙動が食い違う（`parse_worker_name` で実際に起きた経路）。

【`wrangler_config.py` と分ける理由】
`wrangler_config.py` は「`wrangler.jsonc` を読む」責務で、API のページング判定とは関心が違う。
Cloudflare API に共通のヘルパーは本モジュールへ集約する（Issue #476 対応方針の案 2）。

【例外設計】
`wrangler_config.py` と同じく、本モジュールは特定 CLI の例外型に依存しない
（純関数のみで例外を送出しない）。

使い方:
    python3 tools/cloudflare_api.py --self-test    # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

# 一覧取得の既定ページサイズ。#476 以前は退役スクリプトが 100・再トリガースクリプトが 50 と
# バラついていた（害は無いが共通化にあたり判断が要る）。Cloudflare の一覧系エンドポイントは
# `per_page` の上限が 100 なので、往復回数が最小になる 100 へ揃える。
# 実測（2026-09-03 JST・PR #856 Layer 1 セルフレビュー）: 50 から引き上げた側の
# `GET /accounts/{id}/workers/scripts?per_page=100&page=1` は `success: true` を返す（13 件）。
CF_PAGE_SIZE = 100


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

    if failures:
        print("セルフテスト: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"セルフテスト: 全 {len(cases)} ケース PASS")
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
