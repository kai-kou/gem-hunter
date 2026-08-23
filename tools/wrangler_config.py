#!/usr/bin/env python3
"""wrangler_config.py — wrangler.jsonc から共有設定を読み取るユーティリティ

【背景（Issue #451・PR #460 Layer 1 セルフレビュー WARNING-6）】
`tools/trigger_workers_build.py` と `tools/retire_preview_aliases.py` は、wrangler.jsonc から
Worker 名（`name`）を取り出す **一言一句同一のロジック** をそれぞれ独立に持っていた。
「self-test を単独完結させるため」という当時の理由づけは、`retire_preview_aliases.py` 自身が
`mask_secrets` / `repo_slug` を import した状態で self-test を実行できていることと矛盾する
（＝依存モジュールを import しても self-test の独立性は損なわれない）。よって本モジュールへ
一本化し、両ファイルから import する。

【例外設計】
本モジュールは素の `ValueError` を送出する（呼び出し側が自分の例外型 — `ApiError`
（`trigger_workers_build.py`）/ `Precondition`（`retire_preview_aliases.py`）等 — へ wrap する）。
本モジュール自体は特定 CLI の例外設計に依存しない共有部品として設計する。

使い方:
    python3 tools/wrangler_config.py --self-test    # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def parse_worker_name(jsonc_text: str) -> str:
    """wrangler.jsonc の文字列から Worker 名（`name`）を取り出す。

    行コメント（`// ...`）を除去してから JSON として読む（wrangler.jsonc は JSONC 形式で
    コメントを許すが、標準 `json` モジュールはコメント付き JSON を読めないため）。
    """
    without_comments = re.sub(r"^\s*//.*$", "", jsonc_text, flags=re.MULTILINE)
    data = json.loads(without_comments)
    name = data.get("name")
    if not name:
        raise ValueError("wrangler.jsonc に name がありません")
    return str(name)


def read_worker_name(wrangler_path: Path) -> str:
    """wrangler.jsonc ファイルから Worker 名を読み取る（ファイル不在も ValueError にする）。"""
    if not wrangler_path.exists():
        raise ValueError(f"{wrangler_path} が見つかりません")
    return parse_worker_name(wrangler_path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test() -> int:
    failures: list[str] = []

    def check(label: str, actual: object, expected: object) -> None:
        if actual != expected:
            failures.append(f"{label}: 期待 {expected!r} / 実際 {actual!r}")

    check(
        "行コメントを除去して name を取れる",
        parse_worker_name('{\n  // コメント\n  "name": "gem-hunter",\n  "main": "src/index.ts"\n}\n'),
        "gem-hunter",
    )

    try:
        parse_worker_name('{"main": "src/index.ts"}')
        failures.append("parse_worker_name: name が無いのに ValueError を送出していない")
    except ValueError:
        pass

    try:
        read_worker_name(Path("/nonexistent-dir/wrangler.jsonc"))
        failures.append("read_worker_name: ファイル不在なのに ValueError を送出していない")
    except ValueError:
        pass

    if failures:
        print("セルフテスト: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("セルフテスト: 全 3 ケース PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="wrangler.jsonc の共有パーサ（単独 CLI としては --self-test 専用）。"
    )
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテスト")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
