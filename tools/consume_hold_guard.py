#!/usr/bin/env python3
"""消化モード（`self-improvement-loop`）の「保留」連続回数を数え、3 回目を禁じる。

【なぜ必要か（Issue #690）】
  消化モード Step 2 には「大規模・曖昧なら設計を Issue コメントに記録し priority 据え置き」という
  退避路があるが **回数の上限が無い**。実測では `priority:high` の #276 が 2 回連続で保留され、
  2 回目のコメントは「前回から状況の変化なし」と書いていた（＝次回も同じ結論になることが自明）。
  構造上は同じ判定を無限に繰り返せてしまい、priority:high の Issue が消化スロットの選択枠を
  毎回消費したまま永久に着手されない状態を作りうる。
  整理モードには同型のサーキットブレーカー（Step G-6:「保留 3 回連続で 4 回目は選べない」）が
  既にあり、**消化モードにだけ無かった**のを埋める。

【設計の制約】
  - 🔴 **新規 state ファイルを作らない**（`sprint-cycle-router` §0 の ephemeral 前提）。
    判定材料は対象 Issue のコメント履歴だけで、毎スロット再計算できる。
  - 上限は **2 回連続**（整理モードの 3 回より厳しい）。消化モードは「着手して減らす」レーンであり、
    保留は本来の出口ではないため。3 回目は着手・分割・エスカレーションのいずれかを強制する。

【マーカー】
  保留コメントの先頭に置く機械可読プレフィックス。文言の grep ではなく固定文字列で数える。

    [consume-hold] 保留(N 回目): {理由} / 着手へ移る条件: {条件}
    [consume-start]  … 着手した（連続カウントをリセットする）

  過去に使われていた表記ゆれ（`[consume-batch] 保留:` / `## 消化モード: 設計判断の記録`）も
  保留 1 回として数える。既存の履歴をリセットして数え直させないため（#690 の実測がこの 2 形式）。

【使い方】
    python3 tools/consume_hold_guard.py --comments-file comments.json --json
    python3 tools/consume_hold_guard.py --validate-comment-file body.txt
    python3 tools/consume_hold_guard.py --self-test

  `--comments-file` は `mcp__github__issue_read(method="get_comments")` の応答をそのまま保存した
  JSON（`[{"body": "..."}, ...]`）か、本文だけの文字列配列を受け付ける。
  **古い順に並んでいる前提**（GitHub API の既定）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys

HOLD_MARKER = "[consume-hold] 保留"
START_MARKER = "[consume-start]"

# 旧表記（#690 の実測で見つかった 2 形式）。保留 1 回としてカウントする。
LEGACY_HOLD_MARKERS = (
    "[consume-batch] 保留",
    "## 消化モード: 設計判断の記録",
)

ALL_HOLD_MARKERS = (HOLD_MARKER,) + LEGACY_HOLD_MARKERS

# 連続で保留してよい上限。これに達したら次回は保留を選べない（根拠はモジュール docstring）。
HOLD_LIMIT = 2

# 上限到達時に強制される 3 択（整理モード Step G-6 の「取り組む / @owner 諮問」出口と対）。
FORCED_CHOICES = (
    "着手する（無人実行の 3 条件を満たさないなら Issue を分割して満たす単位にする）",
    "@owner に priority / sp の再査定を諮る",
    "status:waiting-user へ移し、ユーザー判断が要る点を 1 文で名指しする",
)

# 保留コメントの必須項目（省略禁止・整理モードの「取り組むへ移る条件」と同じ規律）。
_CONDITION_RE = re.compile(r"着手へ移る条件\s*[:：]\s*\S")
# 「状況の変化なし」だけで閉じさせないための禁止語（条件として無内容なもの）。
_EMPTY_CONDITION_RE = re.compile(r"着手へ移る条件\s*[:：]\s*(状況の?変化なし|様子を見る|特になし|なし)\s*$")


def extract_bodies(data: object) -> list[str]:
    """コメント JSON から本文の配列を取り出す（古い順のまま）。"""
    if not isinstance(data, list):
        raise ValueError("コメント JSON は配列である必要があります")
    bodies: list[str] = []
    for item in data:
        if isinstance(item, str):
            bodies.append(item)
        elif isinstance(item, dict):
            bodies.append(str(item.get("body") or ""))
        else:
            raise ValueError(f"想定外のコメント要素です: {item!r}")
    return bodies


def count_consecutive_holds(bodies: list[str]) -> int:
    """末尾から数えて保留コメントが連続している回数を返す。

    - `[consume-start]`（着手）が挟まったらそこで打ち切る（保留の連鎖が切れている）。
    - どちらのマーカーも持たないコメント（人手のメモ・AI レビュー通知等）は **カウントを壊さない**
      （無視して読み飛ばす）。人がコメントしただけで上限判定が先送りされるのを防ぐため。
    """
    count = 0
    for body in reversed(bodies):
        if any(marker in body for marker in ALL_HOLD_MARKERS):
            count += 1
            continue
        if START_MARKER in body:
            break
        # マーカーの無いコメントは判定に関与しない
    return count


def decide(bodies: list[str], limit: int = HOLD_LIMIT) -> dict:
    """次のスロットで保留を選べるかどうかを判定する。"""
    consecutive = count_consecutive_holds(bodies)
    can_hold = consecutive < limit
    return {
        "consecutive_holds": consecutive,
        "limit": limit,
        "can_hold": can_hold,
        "next_hold_count": consecutive + 1,
        "forced_choices": [] if can_hold else list(FORCED_CHOICES),
    }


def validate_hold_comment(body: str) -> list[str]:
    """保留コメントが必須項目を満たしているか検証する（違反理由の配列を返す）。"""
    problems: list[str] = []
    if HOLD_MARKER not in body:
        problems.append(f"保留コメントは '{HOLD_MARKER}(N 回目):' で始める必要があります")
    if not _CONDITION_RE.search(body):
        problems.append("『着手へ移る条件: {条件}』が必須です（省略禁止）")
    elif _EMPTY_CONDITION_RE.search(body):
        problems.append("『着手へ移る条件』が無内容です（何が決まれば着手できるかを具体化する）")
    return problems


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _hold(n: int) -> str:
    return f"{HOLD_MARKER}({n} 回目): 射程が未確定 / 着手へ移る条件: 対象モジュールの一覧が確定すること"


def _self_test_under_limit_can_hold() -> list[str]:
    """0〜1 回の保留では次も保留を選べる。"""
    failures: list[str] = []
    for n in (0, 1):
        result = decide([_hold(i + 1) for i in range(n)])
        if not result["can_hold"]:
            failures.append(f"連続 {n} 回では保留を選べる必要がある: got={result!r}")
        if result["consecutive_holds"] != n:
            failures.append(f"連続回数の数え間違い: n={n} got={result['consecutive_holds']}")
    return failures


def _self_test_third_hold_is_forbidden() -> list[str]:
    """🔴 完了条件（#690）: 保留 2 回の Issue では 3 回目の保留を選べない。"""
    failures: list[str] = []
    result = decide([_hold(1), _hold(2)])
    if result["can_hold"]:
        failures.append(f"2 回連続の保留のあとに 3 回目を選べてはいけない: got={result!r}")
    if len(result["forced_choices"]) != 3:
        failures.append(f"上限到達時は 3 択を提示する必要がある: got={result['forced_choices']!r}")
    if decide([_hold(1), _hold(2), _hold(3)])["can_hold"]:
        failures.append("上限超過後も保留を選べてはいけない")
    return failures


def _self_test_legacy_markers_are_counted() -> list[str]:
    """旧表記も保留として数える（#690 実測の 2 形式で既に 2 回に達している）。"""
    failures: list[str] = []
    bodies = [
        "## 消化モード: 設計判断の記録（無人 firing のため着手保留）",
        "[consume-batch] 保留: 前回消化スロットの設計判断から状況の変化なし",
    ]
    result = decide(bodies)
    if result["consecutive_holds"] != 2:
        failures.append(f"旧表記が数えられていない: got={result['consecutive_holds']}")
    if result["can_hold"]:
        failures.append("旧表記 2 回でも 3 回目の保留は選べない")
    return failures


def _self_test_start_resets() -> list[str]:
    """着手コメントを挟んだら連続カウントがリセットされる。"""
    failures: list[str] = []
    bodies = [_hold(1), _hold(2), f"{START_MARKER} 着手（PR #689）", _hold(1)]
    result = decide(bodies)
    if result["consecutive_holds"] != 1:
        failures.append(f"着手コメントでリセットされていない: got={result['consecutive_holds']}")
    if not result["can_hold"]:
        failures.append("リセット後 1 回なら保留を選べる")
    return failures


def _self_test_unrelated_comment_is_ignored() -> list[str]:
    """人手のコメントが挟まってもカウントは壊れない（上限の先送りを防ぐ）。"""
    failures: list[str] = []
    bodies = [_hold(1), "調査メモ: 影響範囲を確認した", _hold(2)]
    result = decide(bodies)
    if result["consecutive_holds"] != 2:
        failures.append(f"無関係コメントでカウントが壊れている: got={result['consecutive_holds']}")
    if result["can_hold"]:
        failures.append("無関係コメントを挟んでも 2 回連続なら 3 回目は選べない")
    return failures


def _self_test_validate_hold_comment() -> list[str]:
    failures: list[str] = []
    if validate_hold_comment(_hold(1)):
        failures.append("正しい保留コメントを弾いてはいけない")
    if not validate_hold_comment("## 消化モード: 設計判断の記録"):
        failures.append("プレフィックスの無いコメントを許してはいけない")
    if not validate_hold_comment(f"{HOLD_MARKER}(1 回目): 射程が未確定"):
        failures.append("『着手へ移る条件』欠落を許してはいけない")
    if not validate_hold_comment(f"{HOLD_MARKER}(2 回目): 変化なし / 着手へ移る条件: 状況の変化なし"):
        failures.append("無内容な条件を許してはいけない")
    return failures


def _self_test_extract_bodies() -> list[str]:
    failures: list[str] = []
    if extract_bodies([{"body": "a"}, {"body": "b"}]) != ["a", "b"]:
        failures.append("dict 形式の抽出に失敗")
    if extract_bodies(["a"]) != ["a"]:
        failures.append("文字列配列の抽出に失敗")
    if extract_bodies([{"id": 1}]) != [""]:
        failures.append("body 欠落は空文字に落とす必要がある")
    for bad in ({"body": "a"}, "abc", 3):
        try:
            extract_bodies(bad)
        except ValueError:
            continue
        failures.append(f"配列でない入力を弾いていない: {bad!r}")
    return failures


def run_self_test() -> int:
    groups = [
        ("上限未満では保留可", _self_test_under_limit_can_hold),
        ("3 回目の保留は禁止", _self_test_third_hold_is_forbidden),
        ("旧表記もカウントする", _self_test_legacy_markers_are_counted),
        ("着手でリセット", _self_test_start_resets),
        ("無関係コメントは無視", _self_test_unrelated_comment_is_ignored),
        ("保留コメントの必須項目検証", _self_test_validate_hold_comment),
        ("コメント JSON の抽出", _self_test_extract_bodies),
    ]
    failed = 0
    total = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed += 1
            total += len(failures)
            for f in failures:
                print(f"FAIL[{name}]: {f}")
    if total:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed} グループ失敗（{total} 件）")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="消化モードの保留連続回数を数え、3 回目の保留を禁じる",
    )
    parser.add_argument(
        "--comments-file",
        help="コメント JSON のパス（'-' で標準入力）。古い順に並んでいること",
    )
    parser.add_argument(
        "--validate-comment-file",
        help="これから投稿する保留コメント本文のパス（'-' で標準入力）。必須項目を検証する",
    )
    parser.add_argument(
        "--limit", type=int, default=HOLD_LIMIT,
        help=f"連続で保留してよい上限（既定: {HOLD_LIMIT}）",
    )
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    if args.validate_comment_file:
        body = (
            sys.stdin.read()
            if args.validate_comment_file == "-"
            else open(args.validate_comment_file, encoding="utf-8").read()
        )
        problems = validate_hold_comment(body)
        if args.json:
            print(json.dumps({"valid": not problems, "problems": problems}, ensure_ascii=False, indent=2))
        else:
            for p in problems:
                print(f"❌ {p}")
            if not problems:
                print("✅ 保留コメントの必須項目を満たしています")
        sys.exit(1 if problems else 0)

    if not args.comments_file:
        parser.error("--comments-file / --validate-comment-file / --self-test のいずれかが必要です")
    if args.limit < 1:
        parser.error("--limit は 1 以上で指定してください")

    raw = sys.stdin.read() if args.comments_file == "-" else open(args.comments_file, encoding="utf-8").read()
    result = decide(extract_bodies(json.loads(raw)), limit=args.limit)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"連続保留回数: {result['consecutive_holds']} / 上限 {result['limit']}")
        if result["can_hold"]:
            print(f"✅ 保留を選べます（次は {result['next_hold_count']} 回目）")
        else:
            print("❌ これ以上保留を選べません。次のいずれかを実行してください:")
            for i, choice in enumerate(result["forced_choices"], 1):
                print(f"  {i}. {choice}")
    # 上限到達（保留を選べない）を exit 1 で機械可読にする
    sys.exit(0 if result["can_hold"] else 1)


if __name__ == "__main__":
    main()
