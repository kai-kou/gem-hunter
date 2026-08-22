#!/usr/bin/env python3
"""slides_plan.json からテキスト版 PPTX を生成する。

レイアウト関数は `pptx_template.py`（参照リポジトリのテンプレートをそのまま取り込んだもの）を
import して使い、配色だけを既存インフォグラフィック 13 枚（ネイビー / ティール / コーラル /
生成りの紙地）に合わせて差し替える。画像版と並べたときにトーンが割れないようにするため。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pptx_template as tpl  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402

PLAN = ROOT / "content" / "slides_plan.json"
OUT = ROOT / "output" / "gem-hunter_text.pptx"

# 選択テーマ: 既存インフォグラフィックと同じ「生成りの紙地 + ネイビー + ティール」。
# 理由: 対象読者が開発者で、同一デッキ内に既存グラレコ画像を混在させるため配色を揃える。
tpl.C_BG = RGBColor(0xFA, 0xF6, 0xEC)
tpl.C_HEADER = RGBColor(0x14, 0x36, 0x4F)
tpl.C_ACCENT = RGBColor(0x14, 0x74, 0x6F)
tpl.C_TEXT = RGBColor(0x1B, 0x2A, 0x3A)
tpl.C_CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)

SUMMARY_CARD_TITLES = ["残差で測る", "層を足す条件", "殺せる記録"]


def split_two_column(elements: list[str]) -> tuple[list[str], list[str]]:
    """「却下: 」で始まる要素を左（却下）、それ以外を右（採用）に振り分ける。"""
    left = [e.removeprefix("却下: ") for e in elements if e.startswith("却下: ")]
    right = [e.removeprefix("採用: ") for e in elements if not e.startswith("却下: ")]
    return left, right


def to_slide_data(slide: dict) -> dict:
    no = slide["no"]
    if no == 1:
        return {
            "type": "title",
            "title": slide["elements"][0],
            "subtitle": " / ".join(slide["elements"][1:]),
        }
    if no in (13, 14, 15):
        left, right = split_two_column(slide["elements"])
        return {
            "type": "two-column",
            "header": slide["title"],
            "left_title": "却下した選択肢",
            "left_points": left,
            "right_title": "採用した判断",
            "right_points": right,
        }
    if no == 16:
        cards = [
            {"title": t, "body": b}
            for t, b in zip(SUMMARY_CARD_TITLES, slide["elements"])
        ]
        return {"type": "summary", "header": slide["title"], "cards": cards}
    return {"type": "bullets", "header": slide["title"], "points": slide["elements"]}


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    slides_data = [to_slide_data(s) for s in plan["slides"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tpl.create_text_pptx(slides_data, str(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
