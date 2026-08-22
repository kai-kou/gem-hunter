#!/usr/bin/env python3
"""
check_lane_reachability.py - レーン定義のスキルが実装から到達可能かを検査する（Issue #377）

`docs/rules/improvement-lane-map.md` が定義するレーンの担当スキルが、実装側（決定木・他スキルの
実行手順・hooks 配線）のどこからも起動されていない「経路断絶」を機械的に検出する。

#377 の実体がまさにこれだった: `improvement-lane-map.md` は `type:retro-try` を
`retro-try-handler` の担当と定めていたが、`sprint-cycle-router` の決定木のどのブランチからも
このスキルへの委譲が無く、open Issue の 6 割が到達不能なまま滞留していた。

## この検査が保証するもの / しないもの

- **保証する（構文的到達可能性）**: 実装側のどこかに「そのスキルを起動する」記述が実在するか
- **保証しない（意味的生存性）**: その記述が実運用の firing でどれくらいの頻度で評価に到達するか
  （上位ブランチの飢餓で実際には滅多に真にならない、という状態は検出できない）

コンパイラの到達不能コード検出が「一度も通らない行」は見つけられても「滅多に通らない行」は
プロファイラの仕事であるのと同じ分離。飢餓は決定木側のエージング設計で防ぐ（#377 の Step 5.5）。

## 到達可能性の 3 経路

| 経路 | 判定根拠 |
|------|---------|
| A | `sprint-cycle-router/SKILL.md` の決定木テーブルの「委譲先スキル」列にスキル名が出現する |
| B | 他スキルの `SKILL.md` 本文で、スキル名と起動動詞が同一行または直後 1 行に共起する |
| C | `.claude/settings.json` / `.claude/hooks/*.sh` にスキル起動の配線がある |

`improvement-lane-map.md` の「主な起動」欄そのものは **証拠にしない**。あれは仕様の記述であって
実装の証拠ではなく、これを根拠にすると #377 のような「書いてあるが呼ばれない」断絶を見逃す。

意図的に自然文起動だけで運用するスキルは、レーン表の行末に
`<!-- lanecheck:natural-trigger-only -->` を書いて除外を明示する（既存の `refcheck:ignore` とは
意味論が違うので流用しない）。

使い方:
  python3 tools/check_lane_reachability.py              # 人間可読レポート
  python3 tools/check_lane_reachability.py --json       # 機械可読 JSON
  python3 tools/check_lane_reachability.py --self-test  # 純粋関数のセルフテスト

終了コード: 0 = 全レーンが到達可能 / 1 = 到達不能なレーンあり
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

LANE_MAP = REPO_ROOT / "docs" / "rules" / "improvement-lane-map.md"
ROUTER_SKILL = REPO_ROOT / ".claude" / "skills" / "sprint-cycle-router" / "SKILL.md"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
SETTINGS_JSON = REPO_ROOT / ".claude" / "settings.json"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

# 自然文起動のみで運用することを明示するマーカー。既存の `refcheck:ignore` とは
# 意味論が異なるため流用しない（片方の除外指定をもう片方が誤読するのを避ける）。
NATURAL_TRIGGER_MARKER = "<!-- lanecheck:natural-trigger-only -->"

# バッククォートで囲まれたスキル名候補。実在するスキルディレクトリ名との積集合を取るので、
# `tools/foo.py` や `docs/bar.md` のようなパス片はホワイトリストで自動的に落ちる。
BACKTICK_NAME = re.compile(r"`([a-z][a-z0-9-]+)`")

# 起動を示す動詞。「担当」「対象」のような責務の記述は含めない（言及と起動を区別する）。
LAUNCH_VERBS = re.compile(r"(起動する|起動し|起動|呼び出す|呼び出し|委譲する|委譲|合流する|合流)")

# 否定文脈。起動動詞と共起していても「呼ばない」ことの説明なので証拠にしない。
# 例: 「type:retro-try は …… の担当なので従来どおり除外する」「…… の起動は未実装」
NEGATION = re.compile(r"(扱わない|扱われない|除外|未実装|ではない|しない|対象外|持たない)")


def discover_skills(skills_dir=None):
    """`.claude/skills/` 配下に実在するスキル名の集合を返す（ホワイトリスト）。"""
    skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()}


def extract_lane_skills(text, known_skills):
    """レーンマップの表から「レーンの担当スキル」を抽出する。

    マーカー行（自然文起動のみ）は除外する。`→` 連結・括弧注記・Step サフィックスは
    バッククォート境界で切るので自然に処理される。
    """
    found = set()
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        if NATURAL_TRIGGER_MARKER in line:
            continue
        for name in BACKTICK_NAME.findall(line):
            if name in known_skills:
                found.add(name)
    return found


def extract_router_delegations(text, known_skills):
    """決定木テーブルの「委譲先スキル」列からスキル名を抽出する（経路 A）。

    列位置を固定せず行全体から拾い、ホワイトリストで絞る。`→` 連結は両方拾える。
    `tools/*.py` への委譲や no-op 行（—）はホワイトリストに無いので落ちる。
    """
    found = set()
    for line in text.splitlines():
        stripped = line.lstrip()
        # 決定木テーブルの行は `| **5** | ... |` の形。見出し・区切り行は拾わない。
        if not stripped.startswith("|") or set(stripped) <= set("|-: "):
            continue
        for name in BACKTICK_NAME.findall(line):
            if name in known_skills:
                found.add(name)
    return found


def is_launched_in_body(skill, text, self_skill=None, known_skills=None):
    """本文中でそのスキルが「起動されている」と読めるかを判定する（経路 B）。

    条件は 3 つすべてを満たすこと:

    1. 起動動詞が **スキル名トークンより後ろ** にある（同一行の残り、または直後 1 行）。
       動詞が前にあるケースは別の主語の起動文なので証拠にしない。実例:
       「本スキルを呼び出す（…）。実際の実装は `retro-try-handler` スキルが担う」
       — ここの「呼び出す」は retrospective 自身の話であって retro-try-handler ではない。
    2. 動詞との間に **別スキルのトークンが割り込んでいない**（割り込んでいれば動詞はそちらの述語）。
    3. 否定文脈（扱わない / 除外 / 未実装 …）と共起しない。「呼ばない」ことの説明は証拠にしない。

    自分自身への言及（`X/SKILL.md` の中の `X`）も証拠にしない。
    """
    if self_skill is not None and skill == self_skill:
        return False
    known = known_skills if known_skills is not None else set()
    lines = text.splitlines()
    token = f"`{skill}`"
    for i, line in enumerate(lines):
        pos = line.find(token)
        if pos < 0:
            continue
        after = line[pos + len(token):]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        window = after + "\n" + nxt
        m = LAUNCH_VERBS.search(window)
        if not m:
            continue
        # 動詞の手前に別スキルのトークンが割り込んでいたら、その動詞は別スキルの述語。
        before_verb = window[:m.start()]
        if any(f"`{other}`" in before_verb for other in known if other != skill):
            continue
        # 否定文脈は行全体（前後の文脈込み）で見る。
        if NEGATION.search(line + "\n" + nxt):
            continue
        return True
    return False


def check(skills_dir=None, lane_map=None, router_skill=None, settings_json=None, hooks_dir=None):
    """実ファイルを読んでレーンごとの到達可能性を判定する。"""
    known = discover_skills(skills_dir)
    lane_path = Path(lane_map) if lane_map else LANE_MAP
    router_path = Path(router_skill) if router_skill else ROUTER_SKILL
    lanes = extract_lane_skills(lane_path.read_text(encoding="utf-8"), known) if lane_path.is_file() else set()
    delegations = (
        extract_router_delegations(router_path.read_text(encoding="utf-8"), known)
        if router_path.is_file() else set()
    )

    sd = Path(skills_dir) if skills_dir else SKILLS_DIR
    bodies = {}
    for name in known:
        p = sd / name / "SKILL.md"
        if p.is_file():
            bodies[name] = p.read_text(encoding="utf-8")

    hooks_text = ""
    sj = Path(settings_json) if settings_json else SETTINGS_JSON
    if sj.is_file():
        hooks_text += sj.read_text(encoding="utf-8")
    hd = Path(hooks_dir) if hooks_dir else HOOKS_DIR
    if hd.is_dir():
        for p in sorted(hd.glob("*.sh")):
            hooks_text += p.read_text(encoding="utf-8")

    results = []
    for lane_skill in sorted(lanes):
        via_a = lane_skill in delegations
        via_b = []
        for owner, body in bodies.items():
            if owner == lane_skill:
                continue
            if is_launched_in_body(lane_skill, body, self_skill=owner, known_skills=known):
                via_b.append(owner)
        via_c = f"`{lane_skill}`" in hooks_text
        results.append({
            "skill": lane_skill,
            "reachable": bool(via_a or via_b or via_c),
            "via_router": via_a,
            "via_skills": sorted(via_b),
            "via_hooks": via_c,
        })
    return {"lanes": results, "unreachable": [r["skill"] for r in results if not r["reachable"]]}


def render(report):
    lines = ["# レーン到達可能性の検査（check_lane_reachability）", ""]
    lines.append("| レーンのスキル | 到達 | 経路 A（決定木） | 経路 B（他スキル） | 経路 C（hooks） |")
    lines.append("|---|---|---|---|---|")
    for r in report["lanes"]:
        via_b = ", ".join(r["via_skills"]) or "—"
        lines.append(
            f"| `{r['skill']}` | {'✅' if r['reachable'] else '❌'} | "
            f"{'✅' if r['via_router'] else '—'} | {via_b} | {'✅' if r['via_hooks'] else '—'} |"
        )
    lines.append("")
    if report["unreachable"]:
        lines.append("## ❌ 到達不能なレーン")
        for s in report["unreachable"]:
            lines.append(f"- `{s}`: 決定木・他スキル・hooks のいずれからも起動されていない")
        lines.append("")
        lines.append("意図的に自然文起動だけで運用するなら、`improvement-lane-map.md` の該当行末へ")
        lines.append(f"`{NATURAL_TRIGGER_MARKER}` を付けて除外を明示すること。")
        lines.append("")
        lines.append("> 参考: `improvement-lane-map.md` に「未実装」等の自己申告が無いかも目視で確認する")
        lines.append("> （自己申告そのものは判定材料にしない。誠実な注記を消すインセンティブを作らないため）。")
    else:
        lines.append("✅ すべてのレーンが実装から到達可能。")
    return "\n".join(lines)


def _self_test():
    """純粋関数（ファイル非依存）のセルフテスト。"""
    fail = 0

    def check_(cond, msg):
        nonlocal fail
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            fail += 1

    known = {"retro-try-handler", "retrospective", "self-improvement-loop",
             "workflow-health-check", "project-sync", "sprint-cycle-router",
             "claude-code-spec-sync", "pr-review-watcher"}

    # --- 経路 A: 決定木テーブルのパース ---
    # → 連結は両方を委譲先として拾う
    got = extract_router_delegations(
        "| 6 | x | y | `workflow-health-check` 軽量版 → `project-sync` |\n", known)
    check_(got == {"workflow-health-check", "project-sync"}, f"router arrow split ({got})")
    # Step サフィックスはバッククォートの外なので混入しない
    got = extract_router_delegations("| 1 | x | y | `claude-code-spec-sync` Step1 |\n", known)
    check_(got == {"claude-code-spec-sync"}, f"router step suffix ({got})")
    # tools/*.py への委譲はホワイトリストに無いので落ちる
    got = extract_router_delegations("| 3.5 | x | y | `tools/sprint_backlog_sync.py` |\n", known)
    check_(got == set(), f"router script delegation excluded ({got})")
    # no-op 行（—）は委譲先なし
    check_(extract_router_delegations("| 9 | x | y | — |\n", known) == set(), "router no-op row")
    # 表の区切り行を拾わない
    check_(extract_router_delegations("|---|---|---|---|\n", known) == set(), "router separator row")

    # --- 経路 B: 本文中の起動判定 ---
    # 手順内の実行文は証拠になる
    check_(is_launched_in_body(
        "retrospective", "4. 続けて `retrospective` スキルを起動する（KPT 生成）。\n") is True,
        "body launch verb same line")
    # 直後 1 行に動詞があっても拾う
    check_(is_launched_in_body(
        "retrospective", "次に `retrospective` を使う。\nこのスキルを起動する。\n") is True,
        "body launch verb next line")
    # スキル名だけ（起動動詞なし）は証拠にしない
    check_(is_launched_in_body(
        "retro-try-handler", "| 振り返りレーン | `retrospective` → `retro-try-handler` | x |\n") is False,
        "body mention without verb")
    # 否定文脈と共起する場合は証拠にしない（#377 の Step 5 除外規定がこれ）
    check_(is_launched_in_body(
        "retro-try-handler",
        "- `retro-try-handler` の担当なので従来どおり除外する\n") is False,
        "body negation context")
    check_(is_launched_in_body(
        "retrospective", "他パイプラインからの `retrospective` 起動は未実装であり、別 Issue で対応する\n") is False,
        "body negation mihJissou")
    # 自己参照は証拠にしない
    check_(is_launched_in_body(
        "retro-try-handler", "このスキル `retro-try-handler` を起動する。\n",
        self_skill="retro-try-handler") is False, "body self reference")

    # --- レーン表の抽出 ---
    lane_md = (
        "| レーン | スキル | 担当 | 主な起動 |\n"
        "|---|---|---|---|\n"
        "| **振り返りレーン** | `retrospective` → `retro-try-handler` | x | y |\n"
        "| **監査・衛生レーン** | `workflow-health-check` → `project-sync` | x | y |\n"
    )
    got = extract_lane_skills(lane_md, known)
    check_(got == {"retrospective", "retro-try-handler", "workflow-health-check", "project-sync"},
           f"lane extract ({got})")
    # マーカー行は除外される
    marked = lane_md + f"| **単発** | `sprint-cycle-router` | x | y | {NATURAL_TRIGGER_MARKER}\n"
    got = extract_lane_skills(marked, known)
    check_("sprint-cycle-router" not in got, f"lane marker excluded ({got})")

    # --- #377 の回帰ケース（この検査の存在理由） ---
    # F1: 決定木に retro-try-handler が無い状態は「到達不能」と判定されなければならない
    router_before = (
        "| Step | 判定条件 | 実行内容 | 委譲先スキル |\n"
        "|---|---|---|---|\n"
        "| **5** | x | バックログ消化 | `self-improvement-loop` 消化モード |\n"
        "| **6** | x | 監査・衛生 | `workflow-health-check` 軽量版 → `project-sync` |\n"
    )
    check_("retro-try-handler" not in extract_router_delegations(router_before, known),
           "F1: retro-try-handler unreachable before fix")
    # F1': Step 5.5 を足すと到達可能になる
    router_after = router_before.replace(
        "| **6** |",
        "| **5.5** | x | retro-try Issue の消化 | `retro-try-handler` |\n| **6** |", 1)
    check_("retro-try-handler" in extract_router_delegations(router_after, known),
           "F1': retro-try-handler reachable after fix")
    # F2: 決定木に無くても他スキルの手順から起動されていれば到達可能（偽陽性の防止）
    check_(is_launched_in_body(
        "retrospective",
        "7. マージ後、続けて `retrospective` スキルを起動する。\n", self_skill="pr-review-watcher") is True,
        "F2: retrospective reachable via skill body")
    # F3: 起動動詞がスキル名より前にある行は証拠にしない（実際に偽陰性を生んだパターン）
    check_(is_launched_in_body(
        "retro-try-handler",
        "完了報告の後に本スキルを呼び出す。実際の実装は `retro-try-handler` スキルが担う。\n",
        self_skill="retrospective", known_skills=known) is False,
        "F3: verb before token is not evidence")
    # F4: 動詞の手前に別スキルのトークンが割り込む場合は、その動詞は別スキルの述語
    check_(is_launched_in_body(
        "retro-try-handler",
        "`retro-try-handler` の成果は `pr-review-watcher` を起動して回収する。\n",
        self_skill="retrospective", known_skills=known) is False,
        "F4: intervening skill token blocks attribution")
    # F5: 責務の記述（担う / 担当）は起動ではない
    check_(is_launched_in_body(
        "retro-try-handler", "| `retro-try-handler` | Try Issue を実装・PR 化する |\n",
        self_skill="retrospective", known_skills=known) is False,
        "F5: responsibility statement is not a launch")

    if fail == 0:
        print("PASS: check_lane_reachability self-test (20 checks)")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description="レーン定義のスキルが実装から到達可能かを検査する")
    ap.add_argument("--json", action="store_true", help="JSON を出力")
    ap.add_argument("--self-test", action="store_true", help="純粋関数のセルフテストを実行")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    report = check()
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    return 1 if report["unreachable"] else 0


if __name__ == "__main__":
    sys.exit(main())
