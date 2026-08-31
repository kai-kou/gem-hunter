#!/usr/bin/env python3
"""Issue コメント履歴から「機械可読マーカーの連続回数」を数える共通ロジック。

【なぜ必要か】
  `prod_drift_escalation.py`（#694）と `consume_hold_guard.py`（#690）は、どちらも
  「新規 state ファイルを作らず、対象 Issue のコメント履歴だけから連続回数を再計算する」
  という同じ設計を採る。数え方をそれぞれに実装すると、片方だけにバグ修正が入って
  2 つのサーキットブレーカーの挙動が食い違う。**数え方はこのモジュールにだけ置く**。

【マッチの厳格さ（Layer 1 セルフレビュー CRITICAL・fail-open の実測）】
  マーカーは「コメントの先頭行に置く」規約なのに、本文全体への部分一致（`marker in body`）で
  数えていたため、**マーカー文字列を引用・言及しただけのコメント** が本物の状態報告と誤認された。
  実測: `> [prod-drift][解消] ...` を引用しただけの調査メモが連続カウントを打ち切り、
  真の連続失敗 4 回が 2 回と数えられて escalate しなかった（＝本番断線の通知が飛ばない）。
  したがって判定は次の 2 点を満たす行だけを見る:

    1. **行頭一致**（`line.strip().startswith(marker)`）。行中の言及・バッククォート囲みは数えない
    2. **引用行（`>` 始まり）を除外**。過去のコメントを引用しただけで状態が変わったとみなさない

【投稿者の検証】
  本リポジトリは公開リポジトリであり、Issue コメントは第三者も投稿できる。マーカー行を
  1 件投稿するだけで連続カウントをリセット（通知の握り潰し）・水増し（誤通知）できるため、
  `author_association` を持つコメントは信頼集合（OWNER / MEMBER / COLLABORATOR）に限る。
  フィールドを持たない入力（本文だけの文字列配列・テスト用）は従来どおり受け付ける。

self-test: `python3 tools/issue_marker_counter.py --self-test`
"""

from __future__ import annotations

import json
import sys
from typing import Iterable, Sequence

# コメント投稿者として信頼する `author_association`（GitHub API の値）。
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def extract_bodies(
    data: object,
    *,
    trusted_associations: Iterable[str] | None = TRUSTED_ASSOCIATIONS,
) -> list[str]:
    """コメント JSON から本文の配列を取り出す（古い順のまま）。

    `author_association` を持つ要素は信頼集合に含まれるものだけを残す（第三者による
    マーカー偽装を判定材料にしない）。フィールドが無い要素はそのまま通す。
    """
    if not isinstance(data, list):
        raise ValueError("コメント JSON は配列である必要があります")
    trusted = None if trusted_associations is None else frozenset(trusted_associations)
    bodies: list[str] = []
    for item in data:
        if isinstance(item, str):
            bodies.append(item)
        elif isinstance(item, dict):
            association = item.get("author_association")
            if trusted is not None and association is not None and association not in trusted:
                continue
            bodies.append(str(item.get("body") or ""))
        else:
            raise ValueError(f"想定外のコメント要素です: {item!r}")
    return bodies


def has_marker(body: str, markers: Sequence[str]) -> bool:
    """`markers` のいずれかで **始まる行** が本文にあるか。

    行頭一致だけを見ることで、GitHub の引用（`> [marker] ...`）・バッククォート囲みの言及・
    文中での参照はいずれも自動的に対象外になる（引用専用の除外処理は置かない。
    行頭一致に包含されており、単独では効果を検証できないため）。
    """
    return any(
        line.strip().startswith(marker)
        for line in body.split("\n")
        for marker in markers
    )


def count_consecutive(
    bodies: Sequence[str],
    match_markers: Sequence[str],
    reset_markers: Sequence[str],
) -> int:
    """末尾から数えて `match_markers` が連続している回数を返す。

    - `reset_markers` のいずれかを先頭に持つコメントが現れたらそこで打ち切る（状態が変わった）。
    - どちらのマーカーも持たないコメント（人手のメモ等）は **カウントを壊さない**（読み飛ばす）。
      人がコメントしただけで通知や上限判定が先送りされるのを防ぐため。
    """
    count = 0
    for body in reversed(bodies):
        if has_marker(body, match_markers):
            count += 1
            continue
        if has_marker(body, reset_markers):
            break
    return count


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


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


def _self_test_untrusted_author_is_dropped() -> list[str]:
    """🔴 第三者のコメントを判定材料にしない（公開リポジトリでの偽装対策）。"""
    failures: list[str] = []
    data = [
        {"body": "owner", "author_association": "OWNER"},
        {"body": "outsider", "author_association": "NONE"},
        {"body": "contributor", "author_association": "CONTRIBUTOR"},
        {"body": "member", "author_association": "MEMBER"},
        {"body": "association 不明"},
    ]
    got = extract_bodies(data)
    if got != ["owner", "member", "association 不明"]:
        failures.append(f"信頼集合外のコメントを落とせていない: {got!r}")
    if extract_bodies(data, trusted_associations=None) != [
        "owner", "outsider", "contributor", "member", "association 不明",
    ]:
        failures.append("trusted_associations=None でフィルタを外せない")
    return failures


def _self_test_marker_must_start_line() -> list[str]:
    """🔴 行頭一致であること（言及・引用を状態報告と誤認しない）。"""
    failures: list[str] = []
    cases = [
        ("[MARK] 1 回目", True, "行頭のマーカー"),
        ("見出し\n[MARK] 詳細", True, "2 行目の行頭"),
        ("  [MARK] インデント付き", True, "前後の空白は無視する"),
        ("> [MARK] 引用しただけ", False, "GitHub の引用は行頭が > なので数えない"),
        ("この Issue は `[MARK]` されていない", False, "行中の言及は数えない"),
        ("補足: [MARK] を参照", False, "行頭でない言及は数えない"),
        ("", False, "空文字"),
    ]
    for body, expected, label in cases:
        if has_marker(body, ["[MARK]"]) != expected:
            failures.append(f"{label}: has_marker({body!r}) が {not expected} を返した")
    return failures


def _self_test_count_consecutive() -> list[str]:
    failures: list[str] = []
    bodies = ["[A] 1", "[A] 2", "[A] 3"]
    if count_consecutive(bodies, ["[A]"], ["[B]"]) != 3:
        failures.append("連続 3 回を数えられていない")

    reset = ["[A] 1", "[B] 解消", "[A] 2"]
    if count_consecutive(reset, ["[A]"], ["[B]"]) != 1:
        failures.append("reset マーカーで打ち切れていない")

    noise = ["[A] 1", "調査メモ", "[A] 2"]
    if count_consecutive(noise, ["[A]"], ["[B]"]) != 2:
        failures.append("無関係コメントでカウントが壊れている")

    quoted = ["[A] 1", "[A] 2", "メモ:\n> [B] 解消", "[A] 3", "[A] 4"]
    if count_consecutive(quoted, ["[A]"], ["[B]"]) != 4:
        failures.append("引用しただけの reset マーカーで打ち切られている（fail-open）")

    mentioned = ["[A] 1", "[A] 2", "`[B]` は一度も出ていない", "[A] 3"]
    if count_consecutive(mentioned, ["[A]"], ["[B]"]) != 3:
        failures.append("行中で言及しただけの reset マーカーで打ち切られている（fail-open）")
    return failures


def run_self_test() -> int:
    groups = [
        ("コメント JSON の抽出", _self_test_extract_bodies),
        ("信頼できない投稿者の除外", _self_test_untrusted_author_is_dropped),
        ("マーカーは行頭一致・引用は無視", _self_test_marker_must_start_line),
        ("連続回数の算出", _self_test_count_consecutive),
    ]
    failed = 0
    total = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed += 1
            total += len(failures)
            for failure in failures:
                print(f"FAIL[{name}]: {failure}")
    if total:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed} グループ失敗（{total} 件）")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


def _load(path: str) -> list[str]:
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    return extract_bodies(json.loads(raw))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())
    print(__doc__)
