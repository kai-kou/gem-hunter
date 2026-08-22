#!/usr/bin/env python3
"""実 UI のスクリーンショットを、スライド 1 枚（1536x864・16:9）に合成する。

飼い主の指示（2026-08-22）により **スマホ表示を主役、PC 表示を添え** として並べる。
素材は `capture.spec.ts` が `images/raw/` に撮った端末別の PNG。

レイアウトは「奥に PC の画面、手前に大きくスマホの画面」。スマホを前面かつ縦いっぱいに
置くことで視線が先にスマホへ行き、PC は文脈（同じ画面が広い幅でも成立すること）を示す添えになる。
背景・枠線の色は既存インフォグラフィックのパレット（生成りの紙地 + ネイビー）に合わせる。
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "images" / "raw"
OUT = ROOT / "images"

CANVAS = (1536, 864)
BG = (250, 246, 236)        # 生成りの紙地
FRAME = (20, 54, 79)        # ネイビー
SHADOW = (214, 208, 194)

MOBILE_H = 792              # スマホの表示高さ（上下に 36px の余白）
DESKTOP_W = 900             # PC の表示幅


def rounded(im: Image.Image, radius: int) -> Image.Image:
    """角丸マスクを当てた RGBA 画像を返す。"""
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.size[0] - 1, im.size[1] - 1], radius, fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def framed(im: Image.Image, radius: int, width: int) -> Image.Image:
    """角丸 + 枠線 + 影を付けた RGBA 画像を返す。"""
    card = rounded(im, radius)
    drw = ImageDraw.Draw(card)
    drw.rounded_rectangle(
        [0, 0, card.size[0] - 1, card.size[1] - 1], radius, outline=FRAME + (255,), width=width
    )
    canvas = Image.new("RGBA", (card.size[0] + 10, card.size[1] + 10), (0, 0, 0, 0))
    shadow = Image.new("RGBA", card.size, SHADOW + (255,))
    canvas.paste(rounded(shadow, radius), (10, 10), rounded(shadow, radius))
    canvas.paste(card, (0, 0), card)
    return canvas


def scale_to_height(im: Image.Image, height: int) -> Image.Image:
    return im.resize((round(im.size[0] * height / im.size[1]), height), Image.LANCZOS)


def scale_to_width(im: Image.Image, width: int) -> Image.Image:
    return im.resize((width, round(im.size[1] * width / im.size[0])), Image.LANCZOS)


def compose(shot_id: str, dest_name: str) -> Path:
    mobile = Image.open(RAW / f"{shot_id}-mobile.png").convert("RGB")
    desktop = Image.open(RAW / f"{shot_id}-desktop.png").convert("RGB")

    canvas = Image.new("RGB", CANVAS, BG)

    # 添え: PC 表示（奥・右寄せ）
    pc = framed(scale_to_width(desktop, DESKTOP_W), 14, 3)
    pc_pos = (CANVAS[0] - pc.size[0] - 48, (CANVAS[1] - pc.size[1]) // 2)
    canvas.paste(pc, pc_pos, pc)

    # 主役: スマホ表示（手前・左寄せ・縦いっぱい）
    sp = framed(scale_to_height(mobile, MOBILE_H), 26, 4)
    sp_pos = (96, (CANVAS[1] - sp.size[1]) // 2)
    canvas.paste(sp, sp_pos, sp)

    dest = OUT / dest_name
    canvas.save(dest, "PNG")
    print(f"composed: {dest} (mobile {sp.size} + desktop {pc.size})")
    return dest


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    compose("shot-01", "shot-01-search-results.png")
    compose("shot-02", "shot-02-daily-digest.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
