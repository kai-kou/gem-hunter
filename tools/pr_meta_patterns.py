#!/usr/bin/env python3
"""pr_meta_patterns.py — PR 本文のメタ行（`Sprint Goal:` 等）を検出する共通パターン（Issue #695）。

## なぜ共通化するか

`Sprint Goal:` の有無で「スプリント PR かどうか」を判定する検査が複数ある
（`self_review_check.py` のスプリントメタ Warning・`check_parallel_safety.py` の
並行安全性判定の実行痕跡チェック）。素朴な部分文字列一致だと
「本 PR は `Sprint Goal:` を持たない…」のような **説明文** にも当たり、非スプリント PR で
Warning が誤発火する（実測: PR #732・Issue #695）。

同じ誤りを各所で独立に直すと再発するため、**行アンカー付きの判定を 1 箇所に集約** する
（`check_duplicate_source_patterns.py` が同一正規表現の分散を検出するのと同じ思想）。

## 判定の形

    (?:^|\\n)[ \\t]*{ラベル}:[ \\t]*\\S

- 行頭（文字列先頭または改行直後）にあること — 説明文の途中に現れた言及を拾わない
- 先頭のインデント（半角空白 / タブ）は許容する — 引用やリスト内の記載を落とさない
- コロンの後に **非空白文字が 1 つ以上** あること — 値が空のメタ行は「記載なし」とみなす

本モジュールは定数とファクトリだけを持つ（振る舞いは呼び出し側の `--self-test` が検証する）。

# selftest-wiring-ok: 定数とファクトリのみで判定ロジックを持たず、振る舞いは
# self_review_check.py / check_parallel_safety.py の --self-test が検証している
"""

from __future__ import annotations

import re

__all__ = ["meta_line_re", "SPRINT_GOAL_LINE_RE"]


def meta_line_re(label: str) -> re.Pattern[str]:
    """`{label}:` メタ行が **値付きで** 記載されているかを判定する正規表現を返す。"""
    return re.compile(r"(?:^|\n)[ \t]*" + re.escape(label) + r":[ \t]*\S")


#: `Sprint Goal:` 行の有無（= その PR が `SP-n` スプリント PR かどうか）
SPRINT_GOAL_LINE_RE = meta_line_re("Sprint Goal")
