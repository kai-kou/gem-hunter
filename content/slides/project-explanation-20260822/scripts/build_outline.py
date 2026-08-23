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
    long_slide = next(
        (s["no"] for s in plan["slides"] if "90〜100 秒" in s.get("message", "")), None
    )
    note = f"。スライド {long_slide} のみ 90〜100 秒" if long_slide else ""
    lines.append(f"想定尺: {count}〜{count + 3} 分（{count} 枚 / 1 枚あたり 60〜70 秒{note}）")
    lines.append("作成日: 2026-08-22（2026-08-23 改訂）")
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
