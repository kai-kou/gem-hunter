#!/usr/bin/env python3
"""本番ドリフト検査（`sprint-cycle-router` Step 0.2）の連続失敗を数えて escalate 要否を判定する。

【なぜ必要か（Issue #694）】
  Step 0.2 は `check_prod_drift.py` が exit 2（判定不能）を返したとき `[prod-drift]` Issue へ
  追記コメントするだけで先へ進む。設計どおりだが、その裏で **Cloudflare の build trigger が
  0 件になり本番が一切更新されない状態**（#626）が 8 月中ずっと気づかれずに続いた。
  「判定不能が続いている」ことを誰にも伝える経路が無かったのが根本原因。

【設計の制約】
  - 🔴 **新規 state ファイルを作らない**（`sprint-cycle-router` §0 の ephemeral 前提）。
    判定材料は `[prod-drift]` Issue のコメント履歴だけで、毎 firing 再計算できる。
  - 単発の API エラーで毎回鳴らさないため、**同一マーカーが連続 N 回**続いたときだけ escalate する。
    N=3 の根拠: cron 間隔は 2 時間（`docs/routines/sprint-cycle-routine.md`）なので
    3 回連続 ≒ 6 時間。一過性の Cloudflare API エラーはこの窓を跨いで残らない一方、
    構成断線（trigger 0 件）は何度 firing しても直らないため必ず 3 回に到達する。

【マーカー】
  Step 0.2 が追記するコメントの先頭に置く機械可読プレフィックス。文言の grep ではなく
  この固定文字列で数える（表現ゆれで数えられなくなるのを防ぐ）。

    [prod-drift][判定不能]   … check_prod_drift.py が exit 2（原因未特定）
    [prod-drift][経路未構成] … trigger 0 件を実測した（本番デプロイ経路が繋がっていない）
    [prod-drift][解消]       … ドリフト解消・再トリガー成功（連続カウントをリセットする）

【使い方】
    python3 tools/prod_drift_escalation.py --comments-file comments.json \
        --marker "[prod-drift][経路未構成]" --json
    python3 tools/prod_drift_escalation.py --self-test

  `--comments-file` は `mcp__github__issue_read(method="get_comments")` の応答を
  そのまま保存した JSON（`[{"body": "..."}, ...]`）か、本文だけの文字列配列を受け付ける。
  **古い順に並んでいる前提**（GitHub API の既定）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue_marker_counter import (  # noqa: E402
    count_consecutive as _count_consecutive,
    extract_bodies,
)

INDETERMINATE_MARKER = "[prod-drift][判定不能]"
NOT_CONFIGURED_MARKER = "[prod-drift][経路未構成]"
RESOLVED_MARKER = "[prod-drift][解消]"

ALL_MARKERS = (INDETERMINATE_MARKER, NOT_CONFIGURED_MARKER, RESOLVED_MARKER)

# 連続何回で escalate するか（根拠はモジュール docstring）。
ESCALATION_THRESHOLD = 3


def count_consecutive(bodies: list[str], marker: str) -> int:
    """末尾から数えて `marker` が連続している回数を返す。

    数え方（**行頭一致・引用行の除外**・無関係コメントの読み飛ばし）は
    `issue_marker_counter` が正本。他の `[prod-drift]` マーカー（解消・別種の症状）が
    挟まったらそこで打ち切る（症状が変わった＝連続ではない）。
    """
    return _count_consecutive(bodies, (marker,), ALL_MARKERS)


def decide(bodies: list[str], marker: str, threshold: int = ESCALATION_THRESHOLD) -> dict:
    """escalate 要否と `@mention` 要否を判定する。

    `@mention` は `user-notification-triage.md` §1 に従い **A 区分のときだけ** 立てる。
    trigger 0 件（`[prod-drift][経路未構成]`）は Cloudflare ダッシュボードで Workers Builds を
    接続し直す以外に復旧手段がなく、飼い主のアカウント権限が物理的に必要なので **A-6**。
    原因未特定の「判定不能」は A 区分ではないため、連続しても通知するだけで `@mention` しない。
    """
    consecutive = count_consecutive(bodies, marker)
    escalate = consecutive >= threshold
    return {
        "marker": marker,
        "consecutive": consecutive,
        "threshold": threshold,
        "escalate": escalate,
        "mention": escalate and marker == NOT_CONFIGURED_MARKER,
    }


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_single_firing_does_not_escalate() -> list[str]:
    """🔴 完了条件: 単発の API エラー 1 回では通知が飛ばない（#694）。"""
    failures: list[str] = []
    for n in (0, 1, 2):
        bodies = [f"{INDETERMINATE_MARKER} {i} 回目" for i in range(n)]
        result = decide(bodies, INDETERMINATE_MARKER)
        if result["escalate"]:
            failures.append(f"連続 {n} 回で escalate してはいけない: got={result!r}")
        if result["consecutive"] != n:
            failures.append(f"連続回数の数え間違い: n={n} got={result['consecutive']}")
    return failures


def _self_test_threshold_escalates() -> list[str]:
    failures: list[str] = []
    bodies = [f"{INDETERMINATE_MARKER} {i} 回目" for i in range(3)]
    result = decide(bodies, INDETERMINATE_MARKER)
    if not result["escalate"]:
        failures.append(f"連続 3 回では escalate する必要がある: got={result!r}")
    if result["mention"]:
        failures.append("判定不能（原因未特定）は A 区分ではないので @mention しない")
    return failures


def _self_test_not_configured_mentions() -> list[str]:
    """trigger 0 件が連続したら A-6 として `@mention` する。"""
    failures: list[str] = []
    bodies = [f"{NOT_CONFIGURED_MARKER} {i}" for i in range(3)]
    result = decide(bodies, NOT_CONFIGURED_MARKER)
    if not (result["escalate"] and result["mention"]):
        failures.append(f"経路未構成の 3 連続は @mention 付きで escalate する: got={result!r}")

    below = decide([f"{NOT_CONFIGURED_MARKER} 1"], NOT_CONFIGURED_MARKER)
    if below["mention"]:
        failures.append("閾値未満で @mention してはいけない")
    return failures


def _self_test_resolved_resets() -> list[str]:
    """解消コメントを挟んだら連続カウントがリセットされる。"""
    failures: list[str] = []
    bodies = [
        f"{INDETERMINATE_MARKER} 1",
        f"{INDETERMINATE_MARKER} 2",
        f"{RESOLVED_MARKER} 再トリガー成功",
        f"{INDETERMINATE_MARKER} 3",
    ]
    result = decide(bodies, INDETERMINATE_MARKER)
    if result["consecutive"] != 1:
        failures.append(f"解消コメントでリセットされていない: got={result['consecutive']}")
    if result["escalate"]:
        failures.append("リセット後 1 回で escalate してはいけない")

    mixed = [
        f"{INDETERMINATE_MARKER} 1",
        f"{NOT_CONFIGURED_MARKER} 別症状",
        f"{INDETERMINATE_MARKER} 2",
    ]
    if count_consecutive(mixed, INDETERMINATE_MARKER) != 1:
        failures.append("別マーカーが挟まったら連続は途切れる必要がある")
    return failures


def _self_test_unrelated_comment_is_ignored() -> list[str]:
    """人手のコメントが挟まってもカウントは壊れない（通知の先送りを防ぐ）。"""
    failures: list[str] = []
    bodies = [
        f"{INDETERMINATE_MARKER} 1",
        "調査メモ: Cloudflare のステータスページを確認した",
        f"{INDETERMINATE_MARKER} 2",
        f"{INDETERMINATE_MARKER} 3",
    ]
    result = decide(bodies, INDETERMINATE_MARKER)
    if result["consecutive"] != 3:
        failures.append(f"無関係コメントでカウントが壊れている: got={result['consecutive']}")
    if not result["escalate"]:
        failures.append("無関係コメントを挟んでも 3 連続なら escalate する")
    return failures


def _self_test_quoted_marker_does_not_reset() -> list[str]:
    """🔴 引用・言及しただけのコメントで連続カウントが壊れない（Layer 1 CRITICAL・fail-open）。"""
    failures: list[str] = []
    bodies = [
        f"{INDETERMINATE_MARKER} 1",
        f"{INDETERMINATE_MARKER} 2",
        f"調査メモ:\n> {RESOLVED_MARKER} 再トリガー成功\nを引用しただけで、まだ解消していない",
        f"{INDETERMINATE_MARKER} 3",
        f"{INDETERMINATE_MARKER} 4",
    ]
    result = decide(bodies, INDETERMINATE_MARKER)
    if result["consecutive"] != 4:
        failures.append(f"引用行で連続が打ち切られている: got={result['consecutive']}")
    if not result["escalate"]:
        failures.append("引用行を挟んでも 4 連続なら escalate する")

    mentioned = [
        f"{INDETERMINATE_MARKER} 1",
        f"{INDETERMINATE_MARKER} 2",
        f"`{RESOLVED_MARKER}` はまだ一度も出ていない",
        f"{INDETERMINATE_MARKER} 3",
    ]
    if count_consecutive(mentioned, INDETERMINATE_MARKER) != 3:
        failures.append("行中の言及で連続が打ち切られている")

    # 逆向き: マーカーを行頭に持たないコメントは「症状の発生」としても数えない
    inline_claim = [f"本文中に {INDETERMINATE_MARKER} と書いただけのコメント"]
    if count_consecutive(inline_claim, INDETERMINATE_MARKER) != 0:
        failures.append("行頭にないマーカーを症状として数えている")
    return failures


def run_self_test() -> int:
    groups = [
        ("単発・閾値未満では通知しない", _self_test_single_firing_does_not_escalate),
        ("閾値到達で escalate", _self_test_threshold_escalates),
        ("経路未構成は A-6 として @mention", _self_test_not_configured_mentions),
        ("解消・別症状でリセット", _self_test_resolved_resets),
        ("無関係コメントは無視", _self_test_unrelated_comment_is_ignored),
        ("引用・言及ではリセットしない", _self_test_quoted_marker_does_not_reset),
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
        description="[prod-drift] Issue のコメント履歴から連続失敗回数を数え escalate 要否を判定する",
    )
    parser.add_argument(
        "--comments-file",
        help="コメント JSON のパス（'-' で標準入力）。古い順に並んでいること",
    )
    parser.add_argument(
        "--marker",
        default=INDETERMINATE_MARKER,
        choices=list(ALL_MARKERS),
        help=f"数える症状マーカー（既定: {INDETERMINATE_MARKER}）",
    )
    parser.add_argument(
        "--threshold", type=int, default=ESCALATION_THRESHOLD,
        help=f"escalate する連続回数（既定: {ESCALATION_THRESHOLD}）",
    )
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    if not args.comments_file:
        parser.error("--comments-file か --self-test のどちらかが必要です")
    if args.threshold < 1:
        parser.error("--threshold は 1 以上で指定してください")

    raw = sys.stdin.read() if args.comments_file == "-" else open(
        args.comments_file, encoding="utf-8").read()
    try:
        bodies = extract_bodies(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: コメント JSON を読めません: {error}", file=sys.stderr)
        sys.exit(2)

    result = decide(bodies, args.marker, args.threshold)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"連続 {result['consecutive']} 回 / 閾値 {result['threshold']} "
              f"→ escalate={result['escalate']} mention={result['mention']}")
    # 0 = 通知不要 / 1 = escalate 必要（呼び出し側が終了コードだけでも分岐できるようにする）
    sys.exit(1 if result["escalate"] else 0)


if __name__ == "__main__":
    main()
