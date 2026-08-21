#!/usr/bin/env python3
"""ユーザーストーリーマップ用の格子プロンプトを組み立てる。

`build_prompt.py` の「見出し + 箇条書き」形式では表現できない
「横軸 × 縦軸の格子に個々のカードを配置する」図のための専用ビルダー。
入力は `specs/usm_grid.json`（`columns` / `columns_short` / `rows` / `cells`）。
"""
import argparse
import json
import sys

from build_prompt import STYLE

def render(grid: dict, layout: str) -> str:
    cols = grid.get("columns_short") or grid["columns"]
    out = [STYLE, "",
           f'TITLE (top banner, largest text):\n「{grid["title"]}」', "",
           f'SUBTITLE (under the title, one line):\n「{grid["subtitle"]}」', "",
           "LAYOUT INSTRUCTION:", layout, "",
           "COLUMN HEADERS (left to right):"]
    out += [f"{i}. 「{c}」" for i, c in enumerate(cols, 1)]
    out += ["", "ROW LABELS (top to bottom):"]
    out += [f"{i}. 「{r}」" for i, r in enumerate(grid["rows"], 1)]
    out += ["", "CELL CONTENTS (row × column). Every card label must be rendered exactly as written:"]
    for row in grid["rows"]:
        row_key = row.split()[0]
        for idx, col in enumerate(grid["columns"]):
            col_key = col.split()[0]
            items = grid["cells"].get(row_key, {}).get(col_key, [])
            if items:
                cards = " / ".join(f'「{i["label"]}」[{i["state"].upper()}]' for i in items)
                out.append(f"Row {row_key} × Column {cols[idx]}: {cards}")
            else:
                out.append(f"Row {row_key} × Column {cols[idx]}: EMPTY")
    out += ["", "HIGHLIGHT CHIPS (small hand-drawn tags along the very bottom, in accent colors):"]
    out += [f"「{c}」" for c in grid["chips"]]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grid", default="tools/infographic/specs/usm_grid.json")
    ap.add_argument("--layout", default="tools/infographic/layouts/user-story-map.txt")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.grid, encoding="utf-8") as fh:
        grid = json.load(fh)
    with open(args.layout, encoding="utf-8") as fh:
        layout = fh.read().strip()
    prompt = render(grid, layout)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(prompt)
    print(f"{args.out}: {len(prompt)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
