#!/usr/bin/env python3
"""spec JSON とレイアウト指示から gpt-image-2 用のグラレコ風プロンプトを組み立てる。"""
import argparse
import json
import sys

STYLE = """A 16:9 hand-drawn "graphic recording" (グラレコ / sketchnote) infographic, drawn with markers on warm off-white paper.
Style: hand-lettered Japanese text, rounded hand-drawn boxes and speech bubbles, simple flat doodle icons, hand-drawn arrows, ribbons and banners, light hatching for fills.
Palette: deep navy for body text, teal, coral/salmon, mustard yellow, soft gray. No photorealism, no 3D, no gradients.

--- ABSOLUTE TEXT RULE ---
Every Japanese/English character listed below MUST be rendered EXACTLY as written: no missing characters, no extra characters, no garbled glyphs, no invented words, no translation, no paraphrase.
Do NOT add any text that is not listed below. Do NOT add lorem ipsum or decorative fake characters.
The set of headings drawn on the canvas must be EXACTLY the block headings listed below — no extra boxes, no extra headings, no summary/output box you invented. Every listed item appears exactly ONCE; never repeat the same heading or the same item in two places.
All text must be fully inside the canvas with generous margins — nothing cropped at the edges.
Hand-lettering must stay highly legible at a glance.
--------------------------
"""

REQUIRED_KEYS = ("title", "subtitle", "sections")


def validate(spec: dict, key: str) -> None:
    """描画に必要なキーが揃っているか確認し、欠けていれば場所を示して落とす。"""
    missing = [k for k in REQUIRED_KEYS if k not in spec]
    if missing:
        raise KeyError(f"spec '{key}' に必須キーがない: {', '.join(missing)}")
    for i, sec in enumerate(spec["sections"], 1):
        for field in ("heading", "items"):
            if field not in sec:
                raise KeyError(f"spec '{key}' の section {i} に '{field}' がない")
    for edge in spec.get("edges", []):
        if len(edge) != 2:
            raise ValueError(f"spec '{key}' の edges はペアでなければならない: {edge}")


def render(spec: dict, layout: str) -> str:
    out = [STYLE, "", f'TITLE (top banner, largest text):\n「{spec["title"]}」', "",
           f'SUBTITLE (under the title, one line):\n「{spec["subtitle"]}」', "",
           f"LAYOUT INSTRUCTION:\n{layout}", "",
           "BLOCKS (each block = one hand-drawn rounded box with a small doodle icon next to its heading):"]
    for i, sec in enumerate(spec["sections"], 1):
        out.append(f'\nBlock {i} heading:「{sec["heading"]}」')
        out.append("Block %d items (bulleted list, one line each):" % i)
        out.extend(f"・{item}" for item in sec["items"])
    if spec.get("key_numbers"):
        out.append("\nHIGHLIGHT CHIPS (small hand-drawn tags along the bottom, in accent colors):")
        out.extend(f"「{n}」" for n in spec["key_numbers"])
    if spec.get("edges"):
        out.append("\nARROWS (draw a hand-drawn arrow from the first label to the second; do NOT write the arrow list as text):")
        out.extend(f"{a} → {b}" for a, b in spec["edges"])
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec_file", help="specs/*.json のパス")
    ap.add_argument("key", help="spec JSON 内のトップレベルキー（例: lean-canvas）")
    ap.add_argument("layout_file", help="layouts/*.txt のパス")
    ap.add_argument("out_file", help="組み立てたプロンプトの出力先")
    args = ap.parse_args()

    with open(args.spec_file, encoding="utf-8") as fh:
        data = json.load(fh)
    if args.key not in data:
        print(f"key '{args.key}' が {args.spec_file} にない。利用可能: {', '.join(data)}", file=sys.stderr)
        return 1
    spec = data[args.key]
    try:
        validate(spec, args.key)
    except (KeyError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    with open(args.layout_file, encoding="utf-8") as fh:
        layout_text = fh.read().strip()
    text = render(spec, layout_text)
    with open(args.out_file, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"{args.out_file}: {len(text)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
