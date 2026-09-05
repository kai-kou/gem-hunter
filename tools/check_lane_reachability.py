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
- **既定では保証しない（意味的生存性）**: その記述が実運用の firing でどれくらいの頻度で評価に
  到達するか（上位ブランチの飢餓で実際には滅多に真にならない、という状態）

コンパイラの到達不能コード検出が「一度も通らない行」は見つけられても「滅多に通らない行」は
プロファイラの仕事であるのと同じ分離。飢餓は決定木側のエージング設計で防ぐ（#377 の Step 5.5）。

⚠️ **`--liveness`（#420）を付けたときだけ、第 2 軸として意味的生存性を近似的に見る**：到達可能な
レーンについて「そのレーンが担当する Issue が直近 N 時間（既定 48）に **完了クローズ** されたか」を
確認する。オプトイン（GitHub API に依存するため）。**本節が `--liveness` の規範の正本である。**

- **WARNING のみで終了コードは変えない**（`stale` / `unknown` / 対象 0 件のいずれでも）。飢餓が
  「上位ブランチが本当に忙しい健全な結果」であることもあり、FAIL / PASS の二値では構造的不足と
  一時的な逸脱を区別できないため。判定は stdout の判定列を読むこと。
  🔴 これは `docs/rules/check-tool-design-rules.md` §1（2 = 判定不能を 0 に丸めない）・§2
  （対象 0 件は fail-closed）からの **意図的な逸脱** である。`--liveness` は本判定（構文的到達
  可能性）に付随する report-only の第 2 軸で、本判定の終了コードを汚さないことを優先した。
  代わりに `unknown`（未計測）と対象 0 件は出力側で明示的に WARNING として可視化する。
- **測るのは対象 Issue ラベルの対応があるレーンだけ**（`LIVENESS_LANE_LABELS`）。監査・衛生レーンと
  `retrospective` は Issue のクローズ数で消化実績を測れないため対象外で、その事実は出力の
  「未計測」行に出す。
- 🔴 **ラベルは「レーンが閉じた」の近似**にすぎない（担当レーン以外のクローズも数える fail-open）。
- `tools/run_checks.sh` には配線しない（GitHub API 依存。`--self-test` がネットワーク非依存で
  あるという設計原則を壊さないため）。呼び出し元は `workflow-health-check` スキルの週次監査
  （`reference.md` Step 5-g）。

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
  python3 tools/check_lane_reachability.py --liveness   # 第 2 軸（消化実績）も見る（要 GitHub API）

終了コード: 0 = 全レーンが到達可能 / 1 = 到達不能なレーンあり
（`--liveness` の結果は終了コードに影響しない。理由と扱いは上の「⚠️ `--liveness`」節が正本）
"""

import argparse
import contextlib
import io
import json
import math
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_api import resolve_token  # noqa: E402
from github_rest import exclude_pull_requests, http_get  # noqa: E402
from mask_secrets import mask_text  # noqa: E402
from repo_slug import resolve_repo_slug  # noqa: E402

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


# ──────────────────────────────────────────────
# 第 2 軸: 意味的生存性（--liveness・Issue #420）
# ──────────────────────────────────────────────
# 規範の正本は module docstring の「⚠️ `--liveness`」節（WARNING のみ・終了コードを変えない
# 理由・run_checks.sh へ配線しない理由）。ここでは実装上の判断だけを書く（同じ規範を 2 箇所へ
# 逐語コピーすると、片方だけ直したときに静かに食い違う）。

# レーン → そのレーンが「消化した」ことを示す closed Issue のラベル群。
#
# 🔴 これは **近似指標** である。ラベルが示すのは「そのラベルの Issue が閉じられた」ことであって
# 「そのレーンが閉じた」ことではない（メインセッションの直接実装・手動クローズも含む）。
# クローズ主体を特定する痕跡（PR トレーラー等）との AND を取るのが本来だが、現状の運用では
# その痕跡が Issue 側に残らないため、ここでは fail-open を承知で近似する。判定を強める案は
# Issue 化して扱う（本ファイルで黙って厳しくすると、正しく動いているレーンを stale と誤報する）。
#
# 対応が無いレーンは liveness の対象外にする（監査・衛生レーンや `retrospective` は Issue の
# クローズ数で消化実績を測れない。無理に測ると常時 stale になり警告が腐る）。
LIVENESS_LANE_LABELS: dict[str, tuple[str, ...]] = {
    # 振り返りレーンの実装担当。対象は `type:retro-try` のみ（`improvement-lane-map.md` §2 ルール 2）。
    "retro-try-handler": ("type:retro-try",),
    # 改善 Issue レーンは `improvement-lane-map.md` §2 ルール 1 が「**`type` では絞らない**」と
    # 定めている。`type:improvement` 単独にすると、`type:bug` / `type:docs` だけを消化した週に
    # 健全なレーンを stale と誤報する（狭すぎる一致）。ルール 1 が名指しする type を並べる。
    "self-improvement-loop": ("type:improvement", "type:bug", "type:docs"),
}

# 既定 48 時間。
# 🔴 Issue #420 は根拠を「エージング閾値と揃える」と書いたが、実際のエージング閾値は
# `sprint-cycle-router` SKILL.md §5-4 ② の **8 時間** であり 48 とは揃っていない。数値 48 を採り、
# 根拠を「8 時間の 6 倍窓（エージングが効いていれば必ず 1 回は通っているはずの幅）」へ読み替えた
# （`intent-gate-rules.md`: 仕様と実装の不一致は黙って解消せず記録する。Issue #420 へも記録済み）。
# 8 時間そのものを閾値にすると、2 時間 cron で 1 巡しただけで stale が立ち警告が腐る。
DEFAULT_LIVENESS_THRESHOLD_HOURS = 48

# 表示・記録は JST（`docs/rules/datetime-rules.md`）。比較そのものは UTC のまま行う。
JST = timezone(timedelta(hours=9))

# GitHub の `/issues` は closed_at でソートできない（`sort` は created / updated / comments のみ）。
# close 時には updated も必ず更新されるため、updated 降順の上位から最大の closed_at を取る。
# 🔴 これは近似で、**closed 後に更新された Issue が per_page 件を超えると最新の close が窓の外へ
# 押し出される**（実測: `type:retro-try` は 30 件では既に飽和していた）。GitHub の上限 100 を使い、
# 1 レーン 1 ラベルあたり 1 クエリに収める。
LIVENESS_PAGE_SIZE = 100

# クローズ理由が「完了」でないもの（棚卸しでの `not_planned` / 重複統合の `duplicate`）は
# 消化実績に数えない。数えると、リファインメントが滞留 Try を一括クローズしただけで
# 飢餓しているレーンが live に見える（fail-open）。`state_reason` が無い旧 Issue（None）は
# 当時の API に無かっただけなので完了扱いで許容する。
LIVENESS_COMPLETED_STATE_REASONS = ("completed", None)


def liveness_targets(report):
    """liveness を評価するレーン名を返す。

    条件は 2 つ: ① 構文的に到達可能である（断絶しているレーンの飢餓を二重に報告しない）
    ② 対象 Issue ラベルの対応が `LIVENESS_LANE_LABELS` にある。
    """
    return sorted(
        r["skill"] for r in report.get("lanes", [])
        if r.get("reachable") and r.get("skill") in LIVENESS_LANE_LABELS
    )


def liveness_map_drift(report):
    """`LIVENESS_LANE_LABELS` にあるがレーン一覧に存在しないキーを返す。

    レーンのリネーム・削除で対応表が古くなると、liveness は例外も警告も出さずに監視対象ゼロで
    緑に見える（`check-tool-design-rules.md` §2 が禁じる「対象 0 件の fail-open」）。本体の
    `stale_references` はレーン表と `.claude/skills/` の整合しか見ないためここは拾えない。
    """
    known = {r.get("skill") for r in report.get("lanes", [])}
    return sorted(name for name in LIVENESS_LANE_LABELS if name not in known)


def _parse_iso8601_utc(value):
    """GitHub の ISO 8601 を **aware**（UTC）datetime にする。解釈できなければ None。

    🔴 名前に `_utc` を含めるのは、`tools/check_prod_drift.py` の同名 `_parse_iso8601` が
    **失敗時に ValueError を送出する別契約** だから（こちらは None を返す）。共通化の対象として
    取り違えられると、`closed_at: null` や不正文字列で例外が `main()` まで抜け、
    「終了コードを変えない」契約が壊れる。

    TZ 指定の無い文字列（`2026-09-05` / `2026-09-05T12:00:00`）は UTC とみなす。naive のまま
    返すと `now - newest` が TypeError になり、`--liveness` を付けただけで主レポートごと落ちる。
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def is_completed_close(issue):
    """その closed Issue を「消化実績」と数えてよいかを判定する。"""
    if not isinstance(issue, dict):
        return False
    return issue.get("state_reason") in LIVENESS_COMPLETED_STATE_REASONS


def latest_closed_at(issues):
    """closed Issue 群から **最新の** `closed_at` を返す（無ければ None）。

    応答は updated 降順なので **先頭が最新の closed とは限らない**（close 後にコメントが
    付いた古い Issue が上に来る）。必ず最大値を取る。`not_planned` / `duplicate` のクローズは
    `is_completed_close` で落とす。
    """
    stamps = [
        dt for dt in (
            _parse_iso8601_utc(i.get("closed_at"))
            for i in issues if isinstance(i, dict) and is_completed_close(i)
        ) if dt is not None
    ]
    return max(stamps) if stamps else None


def evaluate_liveness(skill, label, issues, *, now=None,
                      threshold_hours=DEFAULT_LIVENESS_THRESHOLD_HOURS):
    """1 レーン分の生存性を判定する（純粋関数・ネットワーク非依存）。

    `issues` が None は「取得できなかった」で、`unknown` を返す。**stale と混同しない**
    （API 障害を飢餓として報告すると、警告の意味が薄れて読まれなくなる）。
    `reason` の文言はこの関数が唯一の作者である（呼び出し元で上書きしない）。
    """
    now = now or datetime.now(timezone.utc)
    result = {
        "skill": skill,
        "label": label,
        "latest_closed_at": None,
        "hours_since": None,
        "threshold_hours": threshold_hours,
        "status": "unknown",
        "reason": "",
    }
    if issues is None:
        result["reason"] = "対象 Issue を取得できなかった（API 障害・未認証）"
        return result
    newest = latest_closed_at(issues)
    if newest is None:
        result["status"] = "stale"
        result["reason"] = (
            f"取得範囲に `{label}` の完了クローズが 1 件も無い"
            "（一度も消化されていないか、窓の外へ押し出されている）"
        )
        return result
    result["latest_closed_at"] = newest.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    hours = (now - newest).total_seconds() / 3600.0
    result["hours_since"] = round(hours, 1)
    if hours > threshold_hours:
        result["status"] = "stale"
        result["reason"] = (
            f"直近 {threshold_hours} 時間に `{label}` の完了クローズが無い"
            f"（最後は {result['latest_closed_at']}）"
        )
    else:
        result["status"] = "live"
    return result


def liveness_url(repo, label):
    """対象ラベルの closed Issue を取る URL を組み立てる（純関数・self-test で直接検証する）。"""
    return (
        f"https://api.github.com/repos/{repo}/issues"
        f"?state=closed&labels={urllib.parse.quote(label)}"
        f"&sort=updated&direction=desc&per_page={LIVENESS_PAGE_SIZE}"
    )


def _liveness_fetch(repo, label, token=None):
    """対象ラベルの closed Issue を 1 クエリ取得する。戻り値は `(ok, issues | 理由)`。

    self-test は `globals()["http_get"]` を差し替えてネットワークを断ち、組み立てた URL まで
    検証する（終了コードだけを差し替える fake は判定を固定値に潰す変異を見逃す・#710）。
    例外は外へ出さない（`--liveness` は終了コードを変えない契約なので、ここで畳む）。
    """
    try:
        ok, body = http_get(liveness_url(repo, label), token,
                            user_agent="gem-hunter-lane-liveness")
    except Exception as e:  # noqa: BLE001 — 型名だけを返し、トークン由来の文字列を外へ出さない
        return False, f"取得中に例外（{type(e).__name__}）"
    if not ok:
        return False, mask_text(body, secrets={})
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False, "応答が JSON として解釈できない"
    if not isinstance(data, list):
        return False, "応答が配列ではない"
    # 要素が dict である保証が無いまま `exclude_pull_requests` へ渡すと、`"pull_request" in i`
    # が非 dict 要素で TypeError を送出して終了コード契約を破る。
    if any(not isinstance(i, dict) for i in data):
        return False, "応答に Issue オブジェクトでない要素が含まれる"
    # `/issues` は PR も返す。PR のクローズはレーンの消化実績ではない。
    return True, exclude_pull_requests(data)


def check_liveness(report, *, repo=None, token=None, now=None,
                   threshold_hours=DEFAULT_LIVENESS_THRESHOLD_HOURS):
    """到達可能なレーンについて生存性を確認する（レーンのラベル 1 件につき 1 クエリ）。

    複数ラベルを持つレーンは、ラベルごとに取得して **最新の完了クローズ** を採る
    （GitHub の `labels=` は AND なので 1 クエリにまとめられない）。
    """
    repo = repo or resolve_repo_slug()
    if token is None:
        # トークン解決は `github_api.resolve_token()` が SSOT（#238）。自前で env を読むと
        # 対象変数が増えたときに本ファイルだけ取り残される。
        token = resolve_token()
    # 末尾改行つきのトークン（`GH_TOKEN=$(cat ...)` 等）は `http.client` が
    # `ValueError: Invalid header value b'Bearer <トークン全文>'` を送出し、traceback に平文が載る。
    # ヘッダへ渡す前にここで落とす（`tools/check_deploy_gate.py` が CodeQL 指摘で入れた源流対策と同型）。
    if token is not None:
        token = token.strip() or None
    entries = []
    for skill in liveness_targets(report):
        labels = LIVENESS_LANE_LABELS[skill]
        per_label = []
        for label in labels:
            ok, payload = _liveness_fetch(repo, label, token)
            per_label.append(evaluate_liveness(
                skill, label, payload if ok else None,
                now=now, threshold_hours=threshold_hours))
        entries.append(_merge_label_entries(skill, labels, per_label))
    return entries


def _merge_label_entries(skill, labels, per_label):
    """同一レーンの複数ラベル結果を 1 エントリへ畳む。

    採るのは **最も良い状態**（live > stale > unknown）。1 ラベルでも閾値内の完了クローズが
    あればそのレーンは動いている、と読むのが正しい（`improvement-lane-map.md` §2 ルール 1 が
    「type では絞らない」と定めているのはまさにこの意味）。
    """
    label_repr = " / ".join(f"`{x}`" for x in labels)
    live = [e for e in per_label if e["status"] == "live"]
    if live:
        best = min(live, key=lambda e: e["hours_since"])
        return {**best, "label": label_repr}
    stale = [e for e in per_label if e["status"] == "stale"]
    if stale:
        dated = [e for e in stale if e["latest_closed_at"]]
        best = max(dated, key=lambda e: e["hours_since"]) if dated else stale[0]
        threshold = best["threshold_hours"]
        return {
            **best,
            "label": label_repr,
            "reason": f"直近 {threshold} 時間に {label_repr} の完了クローズが無い",
        }
    merged = dict(per_label[0]) if per_label else {
        "skill": skill, "latest_closed_at": None, "hours_since": None,
        "threshold_hours": None, "status": "unknown", "reason": "対象ラベルが無い",
    }
    merged["label"] = label_repr
    return merged


def render_liveness(entries, report=None):
    lines = ["", "## 意味的生存性（`--liveness`・WARNING のみ / 終了コードは変えない）", ""]
    drift = liveness_map_drift(report) if report is not None else []
    if not entries:
        lines.append(
            "⚠️ WARNING: liveness の対象レーンが 0 件。"
            "`LIVENESS_LANE_LABELS` の drift（レーンのリネーム・削除）かレーン表の変更を確認する"
            "（0 件は「問題なし」ではない）。"
        )
        if drift:
            lines.append("")
            lines.append(f"対応表にあるがレーン一覧に無いキー: {', '.join(f'`{d}`' for d in drift)}")
        return "\n".join(lines)
    icon = {"live": "✅", "stale": "⚠️", "unknown": "❔"}
    lines.append("| レーンのスキル | 対象ラベル | 直近の完了クローズ | 経過 | 判定 |")
    lines.append("|---|---|---|---|---|")
    for e in entries:
        elapsed = "—" if e["hours_since"] is None else f"{e['hours_since']} 時間"
        lines.append(
            f"| `{e['skill']}` | {e['label']} | {e['latest_closed_at'] or '—'} | "
            f"{elapsed} | {icon.get(e['status'], '❔')} {e['status']} |"
        )
    # 測っていないレーンを明示する。書かないと「表に並んだ 2 行 = 全レーン生存」と読まれる。
    measured = {e["skill"] for e in entries}
    if report is not None:
        unmeasured = sorted(
            r["skill"] for r in report.get("lanes", [])
            if r.get("skill") not in measured
        )
        if unmeasured:
            lines.append("")
            lines.append(
                "**未計測**（Issue のクローズ数で消化実績を測れないため対象外）: "
                + ", ".join(f"`{u}`" for u in unmeasured)
            )
    if drift:
        lines.append("")
        lines.append(
            "⚠️ WARNING: `LIVENESS_LANE_LABELS` にあるがレーン一覧に無いキー: "
            + ", ".join(f"`{d}`" for d in drift)
            + "（リネーム漏れ。被覆が黙って減っている）"
        )
    stale = [e for e in entries if e["status"] == "stale"]
    unknown = [e for e in entries if e["status"] == "unknown"]
    if stale:
        lines.append("")
        lines.append(f"⚠️ WARNING: {len(stale)} レーンに消化実績がなく **飢餓** の疑いがある。")
        for e in stale:
            lines.append(f"- `{e['skill']}`: {e['reason']}")
        lines.append("")
        lines.append("到達可能なのに消化されていないので、原因は決定木の **上位ブランチの占有** か")
        lines.append("**エージング閾値** にある。`sprint-cycle-router` SKILL.md §5 の飢餓防止条件を確認する。")
        lines.append("")
        lines.append("> 飢餓が「上位ブランチが本当に忙しい健全な結果」であることもあるため、")
        lines.append("> この警告は FAIL にしない（判断は読み手に委ねる）。")
    if unknown:
        lines.append("")
        lines.append("❔ 未計測（PASS ではない）。トークンを供給して再実行する:")
        for e in unknown:
            lines.append(f"- `{e['skill']}`: {e['reason']}")
    return "\n".join(lines)


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
    total = 0

    def check_(cond, msg):
        # 実行数を数えて出力する（件数をハードコードすると、将来アサーションが削られても
        # 表示が変わらず「カバレッジは維持されている」と誤読される）。
        nonlocal fail, total
        total += 1
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

    # --- #420: --liveness（意味的生存性）の判定 ---
    # 構文的到達可能性（この検査の本体）が保証しないもの＝「その経路が実運用で
    # どれくらいの頻度で評価に到達しているか」を、対象 Issue の完了クローズ実績で近似する。
    NOW = datetime(2026, 9, 6, 0, 0, 0, tzinfo=timezone.utc)
    DONE = "completed"

    def issue(closed_at, state_reason=DONE, **extra):
        return {"closed_at": closed_at, "state_reason": state_reason, **extra}

    # L1: 直近の完了クローズが閾値内なら live。表示は **JST 固定値** で検証する
    #     （`astimezone(JST)` を消しても文字列リテラルの " JST" は残るため、状態だけ見る
    #      アサーションでは 9 時間ずれた表示を素通りさせる・datetime-rules.md §0）
    r = evaluate_liveness("retro-try-handler", "type:retro-try",
                          [issue("2026-09-05T12:00:00Z")], now=NOW, threshold_hours=48)
    check_(r["status"] == "live", f"L1: recent close is live ({r})")
    check_(r["latest_closed_at"] == "2026-09-05 21:00 JST",
           f"L1': closed_at is rendered in JST, not UTC ({r['latest_closed_at']})")
    # L2: 閾値を超えていたら stale
    r = evaluate_liveness("retro-try-handler", "type:retro-try",
                          [issue("2026-09-01T00:00:00Z")], now=NOW, threshold_hours=48)
    check_(r["status"] == "stale", f"L2: old close is stale ({r})")
    # L3: ちょうど閾値の時刻は live 側（「超えたら」警告する。境界で鳴らさない）
    r = evaluate_liveness("x", "l", [issue("2026-09-04T00:00:00Z")],
                          now=NOW, threshold_hours=48)
    check_(r["status"] == "live", f"L3: exactly at threshold is live ({r})")
    # L4: 完了クローズゼロは stale
    r = evaluate_liveness("x", "l", [], now=NOW, threshold_hours=48)
    check_(r["status"] == "stale" and r["latest_closed_at"] is None,
           f"L4: no closed issue is stale ({r})")
    # L5: 取得失敗（None）は unknown。stale と混同しない（API 障害を飢餓として報告しない）
    r = evaluate_liveness("x", "l", None, now=NOW, threshold_hours=48)
    check_(r["status"] == "unknown", f"L5: fetch failure is unknown ({r})")
    # L6: 応答は updated 降順なので先頭が最新の closed とは限らない。最大値を取ること
    r = evaluate_liveness("x", "l",
                          [issue("2026-09-01T00:00:00Z"), issue("2026-09-05T12:00:00Z")],
                          now=NOW, threshold_hours=48)
    check_(r["status"] == "live", f"L6: picks the newest closed_at, not the first ({r})")
    # L7: closed_at が null の要素（open の混入・API の欠損）は無視する
    r = evaluate_liveness("x", "l", [issue(None), issue("2026-09-05T12:00:00Z")],
                          now=NOW, threshold_hours=48)
    check_(r["status"] == "live", f"L7: null closed_at is ignored ({r})")
    # L7-b: `not_planned` / `duplicate` のクローズは消化実績に数えない（fail-open の防止）。
    #       棚卸しが滞留 Try を一括クローズしただけで飢餓レーンが live に見えてはいけない
    r = evaluate_liveness("x", "l",
                          [issue("2026-09-05T12:00:00Z", state_reason="not_planned"),
                           issue("2026-09-05T12:00:00Z", state_reason="duplicate")],
                          now=NOW, threshold_hours=48)
    check_(r["status"] == "stale",
           f"L7-b: not_planned/duplicate closes are not progress ({r})")
    # L7-c: `state_reason` が無い旧 Issue（None）は完了扱いで許容する（境界の外側の正ケース）
    r = evaluate_liveness("x", "l", [issue("2026-09-05T12:00:00Z", state_reason=None)],
                          now=NOW, threshold_hours=48)
    check_(r["status"] == "live", f"L7-c: legacy issues without state_reason count ({r})")
    # L7-d: TZ 指定の無い closed_at（日付のみ・秒まで）を UTC とみなす。naive のまま返すと
    #       `now - newest` が TypeError になり「終了コードを変えない」契約が壊れる
    for value in ("2026-09-05", "2026-09-05T12:00:00"):
        r = evaluate_liveness("x", "l", [issue(value)], now=NOW, threshold_hours=48)
        check_(r["status"] in ("live", "stale"),
               f"L7-d: naive timestamp {value!r} must not raise ({r})")
    # L7-e: 解釈できない closed_at は「無かった」扱い（例外を外へ出さない）
    check_(_parse_iso8601_utc("not a date") is None, "L7-e: invalid timestamp returns None")
    check_(_parse_iso8601_utc(None) is None, "L7-e': None returns None")
    # L8: 到達不能なレーンは liveness の評価対象に含めない
    rep = {"lanes": [{"skill": "retro-try-handler", "reachable": False},
                     {"skill": "self-improvement-loop", "reachable": True}]}
    check_(liveness_targets(rep) == ["self-improvement-loop"],
           f"L8: unreachable lanes are excluded ({liveness_targets(rep)})")
    # L9: 対象 Issue ラベルの対応が無いレーンは対象外
    rep = {"lanes": [{"skill": "project-sync", "reachable": True}]}
    check_(liveness_targets(rep) == [], "L9: lanes without an issue label are excluded")
    # L9-b: 対応表にあるがレーン一覧に無いキー（リネーム漏れ）を検出する。
    #       検出しないと被覆が黙って減り「対象レーンなし」＋ exit 0 で通過する
    drift = liveness_map_drift({"lanes": [{"skill": "retro-try-handler", "reachable": True}]})
    check_("self-improvement-loop" in drift,
           f"L9-b: renamed/removed liveness key is reported as drift ({drift})")
    check_(liveness_map_drift({"lanes": [{"skill": k} for k in LIVENESS_LANE_LABELS]}) == [],
           "L9-b': known keys are not drift")

    # --- fetch 層（URL 組み立て・PR 除外・異常系）: ここは self-test でしか守れない ---
    # `_liveness_fetch` を丸ごとスタブすると、`state=closed` を消す・`labels=` を落とす・
    # `exclude_pull_requests` を消す、といった fail-open の変異が全て緑で通る（#710 / #474）。
    check_("state=closed" in liveness_url("o/r", "type:retro-try"),
           "L11: url pins state=closed")
    check_("labels=type%3Aretro-try" in liveness_url("o/r", "type:retro-try"),
           f"L11-b: url url-encodes the label ({liveness_url('o/r', 'type:retro-try')})")
    check_("direction=desc" in liveness_url("o/r", "l") and "sort=updated" in liveness_url("o/r", "l"),
           "L11-c: url pins updated-desc ordering")
    check_(f"per_page={LIVENESS_PAGE_SIZE}" in liveness_url("o/r", "l"),
           "L11-d: url pins the page size")
    check_("/repos/o/r/issues" in liveness_url("o/r", "l"), "L11-e: url targets the given repo")

    orig_http_get = globals()["http_get"]
    calls = []

    def fake_http_get(url, token, **kwargs):
        calls.append((url, token))
        return fake_http_get.response

    try:
        globals()["http_get"] = fake_http_get
        # L12: 応答に PR（`pull_request` キー）が混ざっていたら消化実績から除く。
        #      除かないと `type:improvement` ラベルの PR のクローズで飢餓が live に化ける
        fake_http_get.response = (True, json.dumps([
            {"closed_at": "2026-09-05T12:00:00Z", "state_reason": DONE, "pull_request": {}},
            {"closed_at": "2026-09-01T00:00:00Z", "state_reason": DONE},
        ]))
        ok, payload = _liveness_fetch("o/r", "type:improvement", "tok")
        check_(ok and len(payload) == 1 and "pull_request" not in payload[0],
               f"L12: pull requests are excluded from progress ({payload})")
        seen_url = calls[-1][0] if calls else ""
        check_("labels=type%3Aimprovement" in seen_url,
               f"L12-b: fetch actually requested the given label ({seen_url})")
        check_(calls and calls[-1][1] == "tok", "L12-c: fetch passes the token through")
        # L13: HTTP 失敗・非 JSON・非配列・非 dict 要素はいずれも (False, 理由) に畳む
        #      （例外を外へ出すと終了コード契約が壊れる）
        for label, response in (
            ("http error", (False, "HTTP 502")),
            ("non json", (True, "{not json")),
            ("non array", (True, '{"message":"Not Found"}')),
            ("non dict element", (True, "[null]")),
        ):
            fake_http_get.response = response
            ok, payload = _liveness_fetch("o/r", "l", "tok")
            check_(ok is False and isinstance(payload, str),
                   f"L13: {label} degrades to (False, reason) ({(ok, payload)})")
        # L14: check_liveness は取得失敗を unknown として返す（stale にしない）
        fake_http_get.response = (False, "HTTP 502")
        rep = {"lanes": [{"skill": "retro-try-handler", "reachable": True}]}
        entries = check_liveness(rep, repo="o/r", token="tok", now=NOW)
        check_(len(entries) == 1 and entries[0]["status"] == "unknown",
               f"L14: fetch failure reaches unknown through check_liveness ({entries})")
        # L15: トークンの前後空白・改行を落としてから渡す（CR/LF 入りトークンは
        #      http.client が例外メッセージにトークン全文を載せる）
        calls.clear()
        fake_http_get.response = (True, "[]")
        check_liveness(rep, repo="o/r", token="tok\n", now=NOW)
        seen_token = calls[-1][1] if calls else None
        check_(seen_token == "tok",
               f"L15: token is stripped before reaching the header ({seen_token!r})")
        # L16: 複数ラベルのレーンは 1 ラベルでも閾値内の完了クローズがあれば live
        #      （`improvement-lane-map.md` §2 ルール 1 が type で絞らないと定めているため）
        responses = {
            "type%3Aimprovement": (True, json.dumps([issue("2026-09-01T00:00:00Z")])),
            "type%3Abug": (True, json.dumps([issue("2026-09-05T12:00:00Z")])),
            "type%3Adocs": (True, json.dumps([])),
        }

        def by_label(url, token, **kwargs):
            calls.append((url, token))
            for key, resp in responses.items():
                if key in url:
                    return resp
            return (True, "[]")

        globals()["http_get"] = by_label
        calls.clear()
        rep = {"lanes": [{"skill": "self-improvement-loop", "reachable": True}]}
        entries = check_liveness(rep, repo="o/r", token="tok", now=NOW)
        check_(len(entries) == 1 and entries[0]["status"] == "live",
               f"L16: any in-window label keeps the lane live ({entries})")
        check_(len(calls) == 3, f"L16-b: one query per label ({len(calls)} calls)")
        # L16-c: 全ラベルが窓外なら stale
        responses = {k: (True, json.dumps([issue("2026-09-01T00:00:00Z")])) for k in responses}
        entries = check_liveness(rep, repo="o/r", token="tok", now=NOW)
        check_(len(entries) == 1 and entries[0]["status"] == "stale",
               f"L16-c: all labels out of window means stale ({entries})")
    finally:
        globals()["http_get"] = orig_http_get

    # --- render 層: 終了コードを変えない設計なので、描画された警告が唯一の成果物 ---
    stale_entry = {"skill": "retro-try-handler", "label": "`type:retro-try`",
                   "latest_closed_at": "2026-09-01 09:00 JST", "hours_since": 120.0,
                   "threshold_hours": 48, "status": "stale", "reason": "テスト用"}
    rep = {"lanes": [{"skill": "retro-try-handler", "reachable": True},
                     {"skill": "project-sync", "reachable": True}]}
    out = render_liveness([stale_entry], rep)
    check_("⚠️ WARNING" in out, "L17: stale renders the WARNING block")
    check_("飢餓" in out, "L17-b: stale renders the starvation wording")
    check_("`retro-try-handler`" in out, "L17-c: stale renders the lane row")
    check_("上位ブランチの占有" in out, "L17-d: stale renders the actionable hint")
    check_("未計測" in out and "`project-sync`" in out,
           "L17-e: unmeasured lanes are named（表の 2 行を全レーンと誤読させない）")
    unknown_entry = {**stale_entry, "status": "unknown", "reason": "取得できなかった",
                     "latest_closed_at": None, "hours_since": None}
    out = render_liveness([unknown_entry], rep)
    check_("PASS ではない" in out, "L18: unknown is explicitly not a pass")
    # L18-b: 対象 0 件は「問題なし」ではなく WARNING として出す
    out = render_liveness([], {"lanes": []})
    check_("⚠️ WARNING" in out and "0 件" in out,
           "L18-b: zero targets is a warning, not silence")

    # --- 本番の入口（main）経由: 終了コード契約と CLI フラグの配線 ---
    orig_check = globals()["check"]
    orig_fetch = globals()["_liveness_fetch"]
    orig_argv = sys.argv
    CLEAN_REPORT = {
        "lanes": [{"skill": "retro-try-handler", "reachable": True, "via_router": True,
                   "via_skills": []}],
        "unreachable": [],
        "stale_references": [],
    }

    def run_main(argv):
        buf = io.StringIO()
        sys.argv = argv
        with contextlib.redirect_stdout(buf):
            rc = main()
        return rc, buf.getvalue()

    try:
        # 実リポジトリの状態に依存させない（依存させると、レーン構成を変えただけで
        # 「stale が描画されない」という無関係なメッセージで self-test が赤くなる）
        globals()["check"] = lambda: json.loads(json.dumps(CLEAN_REPORT))
        globals()["_liveness_fetch"] = lambda repo, label, token=None: (True, [])
        rc_without, _ = run_main(["check_lane_reachability.py"])
        rc_with, out_with = run_main(["check_lane_reachability.py", "--liveness"])
        check_(rc_without == 0, f"L10: clean report exits 0 without --liveness ({rc_without})")
        check_(rc_with == 0,
               f"L10-b: --liveness does not change the exit code even when stale ({rc_with})")
        check_("⚠️ WARNING" in out_with and "飢餓" in out_with,
               "L10-c: --liveness rendered the stale warning through main()")
        # L19: `--liveness-threshold-hours` が check_liveness まで届いている。
        #      既定 48 では live になる入力を使い、閾値を絞ると stale へ反転することで固定する
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        globals()["_liveness_fetch"] = lambda repo, label, token=None: (
            True, [{"closed_at": one_hour_ago.replace("+00:00", "Z"), "state_reason": DONE}])
        _, out_default = run_main(["check_lane_reachability.py", "--liveness"])
        check_("✅ live" in out_default, "L19: recent close renders live at the default threshold")
        _, out_tight = run_main(
            ["check_lane_reachability.py", "--liveness", "--liveness-threshold-hours", "0.5"])
        check_("⚠️ stale" in out_tight,
               "L19-b: --liveness-threshold-hours actually reaches check_liveness")
    finally:
        sys.argv = orig_argv
        globals()["check"] = orig_check
        globals()["_liveness_fetch"] = orig_fetch

    # L20: 閾値の値域検証（nan は全比較が偽になり全レーンが無条件 live になる）
    for bad in ("nan", "-1", "0", "abc"):
        rejected = False
        try:
            _positive_hours(bad)
        except argparse.ArgumentTypeError:
            rejected = True
        check_(rejected, f"L20: --liveness-threshold-hours rejects {bad!r}")
    check_(_positive_hours("0.5") == 0.5, "L20-b: positive values are accepted")

    if fail == 0:
        print(f"PASS: check_lane_reachability self-test ({total} checks)")
    return 1 if fail else 0


def _positive_hours(value):
    """`--liveness-threshold-hours` の値域検証。

    `nan` を通すと全比較が偽になり **全レーンが無条件で live** と報告される（警告の恒久的な
    握りつぶし）。負値・0 は逆に全件 stale となり警告が常時鳴って読まれなくなる。
    """
    try:
        hours = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"数値ではありません: {value!r}") from None
    if not math.isfinite(hours) or hours <= 0:
        raise argparse.ArgumentTypeError(f"正の有限値が必要です: {value!r}")
    return hours


def main():
    ap = argparse.ArgumentParser(description="レーン定義のスキルが実装から到達可能かを検査する")
    ap.add_argument("--json", action="store_true", help="JSON を出力")
    ap.add_argument("--self-test", action="store_true", help="純粋関数のセルフテストを実行")
    ap.add_argument(
        "--liveness", action="store_true",
        help="到達可能なレーンの意味的生存性（直近の消化実績）も確認する"
             "（GitHub API を叩く。WARNING のみで終了コードは変えない）")
    ap.add_argument(
        "--liveness-threshold-hours", type=_positive_hours,
        default=DEFAULT_LIVENESS_THRESHOLD_HOURS,
        help=f"生存性の閾値（既定 {DEFAULT_LIVENESS_THRESHOLD_HOURS} 時間・正の有限値）")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    report = check()
    if args.liveness:
        report["liveness"] = check_liveness(
            report, threshold_hours=args.liveness_threshold_hours)
    if args.json:
        report["liveness_map_drift"] = liveness_map_drift(report) if args.liveness else []
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        out = render(report)
        if args.liveness:
            out += "\n" + render_liveness(report["liveness"], report)
        print(out)
    # 🔴 liveness は終了コードに影響させない（#420 の完了条件）。
    return 1 if (report["unreachable"] or report.get("stale_references")) else 0


if __name__ == "__main__":
    sys.exit(main())
