#!/usr/bin/env python3
"""slides_plan.json の new_images から gpt-image-2 用のスライド画像プロンプトを組み立てる。

デザイン統一のため、グラレコ調の STYLE 文は `tools/infographic/build_prompt.py` から
**そのまま import** する（既存 13 枚と同じ配色・筆致にするため。文言を複製しない）。
そこに参照ワークフロー（kai-kou/qiita-bash-lt-2026 の slides スキル Step 9・取得日 2026-08-22）が
必須とする TEXT INCLUSION RULE（一字一句正確に / VERBATIM）を重ねる。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "tools" / "infographic"))

from build_prompt import STYLE  # noqa: E402  （リポジトリ内の既存プロンプト基盤を再利用する）

PLAN = ROOT / "content" / "slides_plan.json"
OUT_DIR = ROOT / "content" / "prompts"

VERBATIM_RULE = """--- TEXT INCLUSION RULE (VERBATIM) ---
Render EVERY text element listed under "Text elements" EXACTLY (verbatim) — character for character,
with no omission, abbreviation, paraphrase, summarization, translation or substitution.
You MAY reorganize the layout or adjust font size for readability, but you must NOT change the wording
of any listed element.
Do NOT add any text that is not in the list — not even partial words, captions, or decorative labels.
Do NOT render any text element more than once — each element must appear exactly once in the image.
Do NOT add furigana (ruby annotations).
Preserve letter case EXACTLY: a word written in lowercase in the list (for example "star",
"sort=gem-index", "gem-hunter") must stay lowercase — never capitalize the first letter,
even at the start of a title or a line.
The 「 」 around each listed element are delimiters marking where the element starts and ends —
they are NOT part of the text. Do not draw them. Only 「 」 that appear INSIDE an element
(for example 「今日の Gem」 within a longer sentence) are drawn.
--------------------------------------

--- SLIDE RULE ---
This image is ONE presentation slide (16:9), not a document summary.
The first listed text element is the slide title: draw it once, in a top banner, as the largest text.
Keep the whole composition readable when projected: few, large elements with generous margins.
------------------
"""


def build(image: dict, slide: dict) -> str:
    # 焼き込むテキストの正本はスライド本体（タイトル + 本文）。画像側に複製を持たない。
    elements = [slide["title"], *slide["elements"]]
    lines = [STYLE, VERBATIM_RULE, ""]
    lines.append(f'TITLE (top banner, largest text, drawn once):\n「{elements[0]}」')
    lines.append("")
    lines.append(
        "Text elements (exhaustive — render ALL of these VERBATIM, character for character, "
        "add nothing else):"
    )
    lines.extend(f"「{e}」" for e in elements)
    lines.append("")
    lines.append(
        "Visual elements (icons and shapes ONLY — never draw any text inside these):\n"
        + image["motif"]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    slides = {s["no"]: s for s in plan["slides"]}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for image in plan["new_images"]:
        slide = slides[image["slide_no"]]
        path = OUT_DIR / f'{image["id"]}.txt'
        text = build(image, slide)
        path.write_text(text, encoding="utf-8")
        n = 1 + len(slide["elements"])
        print(f'{path.name}: slide {image["slide_no"]} / {n} text elements / {len(text)} chars')
    return 0


if __name__ == "__main__":
    sys.exit(main())
