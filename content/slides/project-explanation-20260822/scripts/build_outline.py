#!/usr/bin/env python3
"""議論の verdict（slides_plan.json）からスライド構成マークダウンを生成する。

構成の正本は slides_plan.json（議論ホワイトボードの verdict と同一内容）であり、
本スクリプトはそれを人間可読な構成マークダウンへ変換するだけの薄い変換器。
参照ワークフロー: kai-kou/qiita-bash-lt-2026 の slides スキル Step 1（取得日 2026-08-22）。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "content" / "slides_plan.json"
OUT = ROOT / "content" / "slides_content_gem-hunter.md"

# 長尺スライドの目印。`slides_plan.json` の `message` に含める逐語で、ここが唯一の定義。
# 表記を変えるときは JSON 側と本定数を同時に直す（片方だけ変えると尺が静かにズレる）。
LONG_SPAN_MARKER = "90〜100 秒"


def visual_line(slide: dict) -> str:
    return slide.get("visual", "none")


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    lines: list[str] = []
    lines.append("# スライド構成: gem-hunter プロジェクト解説")
    lines.append("")
    lines.append("対象読者: 開発者・エンジニア")
    # 枚数と尺は構成そのものから導出する（ハードコードするとスライドを増減したときに取り残される）。
    count = len(plan["slides"])
    # 長尺スライドは 1 枚とは限らないので全件走査する（next() で先頭だけ拾うと、
    # 2 枚目以降のぶん尺が短く出たうえ注記が「〜のみ」と誤記になる）。
    longs = [s["no"] for s in plan["slides"] if LONG_SPAN_MARKER in s.get("message", "")]
    if len(longs) == 1:
        note = f"。スライド {longs[0]} のみ {LONG_SPAN_MARKER}"
    elif longs:
        note = "。スライド " + " / ".join(str(n) for n in longs) + f" は {LONG_SPAN_MARKER}"
    else:
        note = ""
    # 秒から積み上げて分に直す（枚数 + 3 という当てずっぽうだと長尺スライドのぶんが落ちる）。
    low_sec = count * 60 + (90 - 60) * len(longs)
    high_sec = count * 70 + (100 - 70) * len(longs)
    low_min = -(-low_sec // 60)
    high_min = -(-high_sec // 60)
    lines.append(f"想定尺: {low_min}〜{high_min} 分（{count} 枚 / 1 枚あたり 60〜70 秒{note}）")
    lines.append("作成日: 2026-08-22（2026-08-23・2026-08-24 改訂）")
    lines.append("")
    lines.append("> 本ファイルは `content/slides_plan.json`（議論 `project-slides-20260822` の verdict）から")
    lines.append("> `scripts/build_outline.py` が生成する。**構成を変えるときは JSON 側を直して再生成する。**")
    lines.append("")
    for s in plan["slides"]:
        lines.append(f"## Slide {s['no']}: {s['title']}")
        lines.append("")
        lines.append(f"- 見出し: {s['title']}")
        lines.append("- 本文:")
        for e in s["elements"]:
            lines.append(f"  - {e}")
        lines.append(f"- ビジュアル: {visual_line(s)}")
        lines.append(f"- 伝えたい 1 メッセージ: {s['message']}")
        lines.append(f"- 出典: {s['source']}")
        lines.append("")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"outline written: {OUT} ({len(plan['slides'])} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
