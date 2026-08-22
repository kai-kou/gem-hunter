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

hooks からの起動は経路として持たない。現状 `.claude/hooks/` にスキルを起動する配線は 1 件も無く、
地の文（コメント・エラーメッセージ）でスキル名に触れているだけの行を「配線」と読むと、
文言を変えただけで判定が反転する偽陽性になる（実際に発生した）。実配線が生まれたときに足す。

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

# 自然文起動のみで運用することを明示するマーカー。既存の `refcheck:ignore` とは
# 意味論が異なるため流用しない（片方の除外指定をもう片方が誤読するのを避ける）。
NATURAL_TRIGGER_MARKER = "<!-- lanecheck:natural-trigger-only -->"

# バッククォートで囲まれたスキル名候補。実在するスキルディレクトリ名との積集合を取るので、
# `tools/foo.py` や `docs/bar.md` のようなパス片はホワイトリストで自動的に落ちる。
BACKTICK_NAME = re.compile(r"`([a-z][a-z0-9-]+)`")

# 起動を示す動詞。「担当」「対象」のような責務の記述は含めない（言及と起動を区別する）。
# `起動` は `起動する` / `起動し` 等の活用形を包含する（活用形を個別に並べても
# alternation で常に短い方が先に一致するため、到達しない分岐になる）。
LAUNCH_VERBS = re.compile(r"(起動|呼び出す|呼び出し|委譲)")

# 否定文脈。起動動詞と共起していても「呼ばない」ことの説明なので証拠にしない。
# 例: 「type:retro-try は …… の担当なので従来どおり除外する」「…… の起動は未実装」
NEGATION = re.compile(r"(扱わない|扱われない|除外|未実装|ではない|しない|対象外|持たない)")


def discover_skills(skills_dir=None):
    """`.claude/skills/` 配下に実在するスキル名の集合を返す（ホワイトリスト）。"""
    skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()}


def _cells(line):
    """パイプテーブルの 1 行をセルへ分割する（前後の空セルは落とす）。"""
    parts = line.strip().split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return parts


def extract_lane_skills(text, known_skills):
    """レーンマップの表の **「スキル」列** から「レーンの担当スキル」を抽出する。

    行全体から拾うと「主な起動」列に書かれた **呼び出し元** のスキル名まで
    「レーンの担当スキル」として数えてしまう（例: 振り返りレーンの起動元として
    `sprint-cycle-router` が書かれている行）。列を特定して絞る。

    マーカー行（自然文起動のみ）は除外する。`→` 連結・括弧注記・Step サフィックスは
    バッククォート境界で切るので自然に処理される。
    """
    found = set()
    skill_col = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("|"):
            skill_col = None  # 表の外に出たら列位置をリセットする
            continue
        cells = _cells(line)
        if skill_col is None:
            # ヘッダ行から「スキル」列の位置を特定する
            for idx, cell in enumerate(cells):
                if cell.strip() == "スキル":
                    skill_col = idx
                    break
            continue
        if set(stripped) <= set("|-: "):
            continue  # 区切り行
        if NATURAL_TRIGGER_MARKER in line:
            continue
        if skill_col >= len(cells):
            continue
        for name in BACKTICK_NAME.findall(cells[skill_col]):
            if name in known_skills:
                found.add(name)
    return found


def extract_stale_references(text, known_skills):
    """レーン表の「スキル」列にあるが `.claude/skills/` に実在しない名前を返す。

    ホワイトリスト方式で絞ると、スキルをリネーム・削除したときに **その名前が
    レーン一覧から静かに消える**。レーンが評価対象から外れるので `unreachable` にも
    載らず、実運用が壊れているのに検査は緑を返す（最も危険な偽陰性）。

    「スキル」列に書かれた kebab-case 名は定義上すべてスキルなので、実在しないものは
    リネーム漏れ・typo・削除漏れとして FAIL させる。
    """
    stale = set()
    skill_col = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("|"):
            skill_col = None
            continue
        cells = _cells(line)
        if skill_col is None:
            for idx, cell in enumerate(cells):
                if cell.strip() == "スキル":
                    skill_col = idx
                    break
            continue
        if set(stripped) <= set("|-: "):
            continue
        if skill_col >= len(cells):
            continue
        for name in BACKTICK_NAME.findall(cells[skill_col]):
            if name not in known_skills:
                stale.add(name)
    return stale


# 決定木テーブルのヘッダ行。この表だけを経路 A の証拠にする（他の表は拾わない）。
ROUTER_TABLE_HEADER = re.compile(r"^\|\s*Step\s*\|.*委譲先")


def _router_table_lines(text):
    """決定木テーブルの行だけを切り出す。

    SKILL.md には失敗モード表など他のパイプテーブルもあり、そこにもスキル名が出てくる。
    ファイル全体を舐めると「決定木から消してもよそのテーブルの言及で到達可能に見える」
    という偽陽性が出る（#377 の再発をこの検査自身が見逃すことになる）。
    """
    lines = text.splitlines()
    out, inside = [], False
    for line in lines:
        stripped = line.lstrip()
        if ROUTER_TABLE_HEADER.match(stripped):
            inside = True
            continue
        if not inside:
            continue
        if not stripped.startswith("|"):
            break  # テーブルの終端
        if set(stripped) <= set("|-: "):
            continue  # 区切り行
        out.append(line)
    return out


def extract_router_delegations(text, known_skills):
    """決定木テーブルの「委譲先スキル」列からスキル名を抽出する（経路 A）。

    決定木テーブルの範囲だけを見る（他のパイプテーブルは対象外）。列位置は固定せず
    行全体から拾いホワイトリストで絞るため、`→` 連結は両方拾え、`tools/*.py` への委譲や
    no-op 行（—）はホワイトリストに無いので落ちる。
    """
    found = set()
    for line in _router_table_lines(text):
        for name in BACKTICK_NAME.findall(line):
            if name in known_skills:
                found.add(name)
    return found


def _router_delegation_col(text):
    """決定木テーブルの「委譲先スキル」列のインデックスを返す（見つからなければ None）。"""
    for line in text.splitlines():
        stripped = line.lstrip()
        if ROUTER_TABLE_HEADER.match(stripped):
            for idx, cell in enumerate(_cells(line)):
                if "委譲先" in cell:
                    return idx
    return None


def extract_stale_delegations(text, known_skills):
    """決定木の **委譲先列** にあるが `.claude/skills/` に実在しない名前を返す。

    行全体を見ると判定条件・実行内容の列に出てくるバッククォート語（通知名 `routine-idle`・
    ラベル名など）まで「実在しないスキル」として誤検出する。委譲先列だけを見る。

    `BACKTICK_NAME` は `[a-z][a-z0-9-]+` なので `tools/sprint_backlog_sync.py` のような
    スクリプト委譲（`/` `_` `.` を含む）には最初からマッチしない。したがってこの列で拾える
    kebab-case 名は定義上すべてスキルであり、実在しないものはリネーム漏れ・typo。
    """
    col = _router_delegation_col(text)
    if col is None:
        return set()
    stale = set()
    for line in _router_table_lines(text):
        cells = _cells(line)
        if col >= len(cells):
            continue
        for name in BACKTICK_NAME.findall(cells[col]):
            if name not in known_skills:
                stale.add(name)
    return stale


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
        # 表の行では、そのスキルのセルを越えた先は別の話題なのでセル境界で切る。
        if line.lstrip().startswith("|") and "|" in after:
            after = after[:after.index("|")]
            window = after  # 表の行では次行を先読みしない（次行は別 Step の行）
        else:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            # 次行が新しい表の行なら別の話題。先読みしない。
            window = after if nxt.lstrip().startswith("|") else after + "\n" + nxt
        m = LAUNCH_VERBS.search(window)
        if not m:
            continue
        # 動詞の手前に別スキルのトークンが割り込んでいたら、その動詞は別スキルの述語。
        before_verb = window[:m.start()]
        if any(f"`{other}`" in before_verb for other in known if other != skill):
            continue
        # 否定判定の窓は動詞判定の窓と揃える。行頭から見ると、トークンより前にある
        # 無関係な否定語（「失敗しない場合に限り …… を起動する」の「しない」）が
        # 正当な起動を打ち消してしまう。
        if NEGATION.search(window):
            continue
        return True
    return False


def check(skills_dir=None, lane_map=None, router_skill=None):
    """実ファイルを読んでレーンごとの到達可能性を判定する。"""
    known = discover_skills(skills_dir)
    lane_path = Path(lane_map) if lane_map else LANE_MAP
    router_path = Path(router_skill) if router_skill else ROUTER_SKILL
    lane_text = lane_path.read_text(encoding="utf-8") if lane_path.is_file() else ""
    lanes = extract_lane_skills(lane_text, known)
    stale = extract_stale_references(lane_text, known)
    router_text = router_path.read_text(encoding="utf-8") if router_path.is_file() else ""
    delegations = extract_router_delegations(router_text, known)
    # 決定木の委譲先も stale 検査の対象にする。レーン表に載らないスキル
    # （`pr-review-watcher` / `claude-code-spec-sync` 等）のリネーム漏れは、
    # レーン側の検査だけでは一切現れない。
    stale |= extract_stale_delegations(router_text, known)

    sd = Path(skills_dir) if skills_dir else SKILLS_DIR
    bodies = {}
    for name in known:
        p = sd / name / "SKILL.md"
        if p.is_file():
            bodies[name] = p.read_text(encoding="utf-8")

    results = []
    for lane_skill in sorted(lanes):
        via_a = lane_skill in delegations
        via_b = []
        for owner, body in bodies.items():
            if owner == lane_skill:
                continue
            if is_launched_in_body(lane_skill, body, self_skill=owner, known_skills=known):
                via_b.append(owner)
        results.append({
            "skill": lane_skill,
            "reachable": bool(via_a or via_b),
            "via_router": via_a,
            "via_skills": sorted(via_b),
        })
    return {
        "lanes": results,
        "unreachable": [r["skill"] for r in results if not r["reachable"]],
        "stale_references": sorted(stale),
    }


def render(report):
    lines = ["# レーン到達可能性の検査（check_lane_reachability）", ""]
    lines.append("| レーンのスキル | 到達 | 経路 A（決定木） | 経路 B（他スキル） |")
    lines.append("|---|---|---|---|")
    for r in report["lanes"]:
        via_b = ", ".join(r["via_skills"]) or "—"
        lines.append(
            f"| `{r['skill']}` | {'✅' if r['reachable'] else '❌'} | "
            f"{'✅' if r['via_router'] else '—'} | {via_b} |"
        )
    lines.append("")
    if report.get("stale_references"):
        lines.append("## ❌ 実在しないスキルを参照しているレーン")
        for s in report["stale_references"]:
            lines.append(f"- `{s}`: `.claude/skills/{s}/` が存在しない（リネーム漏れ・削除漏れ・typo）")
        lines.append("")
    if report["unreachable"]:
        lines.append("## ❌ 到達不能なレーン")
        for s in report["unreachable"]:
            lines.append(f"- `{s}`: 決定木からも他スキルの手順からも起動されていない")
        lines.append("")
        lines.append("意図的に自然文起動だけで運用するなら、`improvement-lane-map.md` の該当行末へ")
        lines.append(f"`{NATURAL_TRIGGER_MARKER}` を付けて除外を明示すること。")
        lines.append("")
        lines.append("> 参考: `improvement-lane-map.md` に「未実装」等の自己申告が無いかも目視で確認する")
        lines.append("> （自己申告そのものは判定材料にしない。誠実な注記を消すインセンティブを作らないため）。")
    elif not report.get("stale_references"):
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
    ROUTER_HDR = "| Step | 判定条件 | 実行内容 | 委譲先スキル |\n|---|---|---|---|\n"
    got = extract_router_delegations(
        ROUTER_HDR + "| 6 | x | y | `workflow-health-check` 軽量版 → `project-sync` |\n", known)
    check_(got == {"workflow-health-check", "project-sync"}, f"router arrow split ({got})")
    # Step サフィックスはバッククォートの外なので混入しない
    got = extract_router_delegations(ROUTER_HDR + "| 1 | x | y | `claude-code-spec-sync` Step1 |\n", known)
    check_(got == {"claude-code-spec-sync"}, f"router step suffix ({got})")
    # tools/*.py への委譲はホワイトリストに無いので落ちる
    got = extract_router_delegations(ROUTER_HDR + "| 3.5 | x | y | `tools/sprint_backlog_sync.py` |\n", known)
    check_(got == set(), f"router script delegation excluded ({got})")
    # no-op 行（—）は委譲先なし
    check_(extract_router_delegations(ROUTER_HDR + "| 9 | x | y | — |\n", known) == set(), "router no-op row")
    # 表の区切り行を拾わない
    check_(extract_router_delegations(ROUTER_HDR + "|---|---|---|---|\n", known) == set(), "router separator row")

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
    # R5: 「主な起動」列に書かれた呼び出し元を、レーンの担当スキルとして数えない
    caller_md = (
        "| レーン | スキル | 担当 | 主な起動 |\n"
        "|---|---|---|---|\n"
        "| **振り返りレーン** | `retrospective` | x | `sprint-cycle-router` の Step 5.5 |\n"
    )
    got = extract_lane_skills(caller_md, known)
    check_(got == {"retrospective"}, f"R5: caller column is not a lane skill ({got})")
    # R6: スキルのリネーム・削除で、レーンが静かに評価対象から消えないこと。
    #     旧名がレーン表に残っているのに実体が無い状態を FAIL させる。
    renamed_md = (
        "| レーン | スキル | 担当 | 主な起動 |\n"
        "|---|---|---|---|\n"
        "| **振り返りレーン** | `retro-try-handler` | x | y |\n"
    )
    check_(extract_stale_references(renamed_md, known - {"retro-try-handler"})
           == {"retro-try-handler"}, "R6: renamed/removed skill is reported as stale")
    check_(extract_stale_references(renamed_md, known) == set(),
           "R6': existing skill is not stale")
    # R7: 決定木の委譲先のリネーム漏れも検出する（レーン表に載らないスキルが対象）
    check_(extract_stale_delegations(
        ROUTER_HDR + "| 2 | x | y | `pr-review-watcher-old` |\n", known) == {"pr-review-watcher-old"},
        "R7: renamed router delegation is reported as stale")
    check_(extract_stale_delegations(
        ROUTER_HDR + "| 2 | x | y | `pr-review-watcher` |\n", known) == set(),
        "R7': existing delegation is not stale")
    # R7'': tools/*.py へのスクリプト委譲は stale にしない（正規表現に最初からマッチしない）
    check_(extract_stale_delegations(
        ROUTER_HDR + "| 3.5 | x | y | `tools/sprint_backlog_sync.py` |\n", known) == set(),
        "R7'': script delegation is not stale")
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

    # --- セルフレビューで実測した欠陥の回帰ケース（#421） ---
    # R1: 決定木テーブル以外のパイプテーブルを経路 A の証拠にしない。
    #     これを許すと「決定木から消してもよそのテーブルの言及で到達可能に見える」となり、
    #     #377 と同型の回帰をこの検査自身が見逃す。
    other_table = (
        "## §12 失敗モード\n\n"
        "| 症状 | 原因 | 対処 |\n"
        "|---|---|---|\n"
        "| CI 赤 | `pr-review-watcher` Step 2 が検知 | 修正して再 push |\n"
    )
    check_(extract_router_delegations(other_table, known) == set(),
           "R1: non-router table is not evidence")
    # 決定木テーブルの直後に別テーブルが来ても、決定木の分だけを拾う
    check_(extract_router_delegations(
        ROUTER_HDR + "| 2 | x | y | `pr-review-watcher` |\n" + "\n" + other_table, known)
        == {"pr-review-watcher"}, "R1': router table scope ends at blank line")
    # R2: 表の行では、そのスキルのセルを越えた先（別 Step の行）を先読みしない。
    two_rows = ("| **9** | 条件 | 参考として `retrospective` も関係する | — |\n"
                "| **10** | 条件 | 実行内容（委譲先の候補は複数ある） | `project-sync` |\n")
    check_(is_launched_in_body("retrospective", two_rows, known_skills=known) is False,
           "R2: table row does not read the next row")
    # R3: 否定判定の窓は動詞判定の窓と揃える。トークンより前の無関係な否定語で
    #     正当な起動が打ち消されてはいけない。
    check_(is_launched_in_body(
        "retrospective", "テストが失敗しない場合に限り `retrospective` を起動する。\n") is True,
        "R3: negation before token does not block")
    # R4: `除外` の否定判定そのものを直接検証する（動詞が確実に一致する文で）。
    check_(is_launched_in_body(
        "retro-try-handler",
        "`retro-try-handler` を起動する対象からは除外する運用にした。\n",
        self_skill="self-improvement-loop", known_skills=known) is False,
        "R4: negation keyword 除外 is exercised")

    if fail == 0:
        print("PASS: check_lane_reachability self-test (32 checks)")
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
    return 1 if (report["unreachable"] or report.get("stale_references")) else 0


if __name__ == "__main__":
    sys.exit(main())
