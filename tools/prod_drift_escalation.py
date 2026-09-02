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
    [prod-drift][実行ブロック] … trigger_workers_build.py の呼び出し自体が auto mode classifier に
                                 ブロックされ、exit code が一切返らなかった（L-130・Issue #785。
                                 1 回リトライしてもなお実行不能だった場合のみこのマーカーを使う）
    [prod-drift][解消]       … ドリフト解消・再トリガー成功（連続カウントをリセットする）
    [prod-drift][通知済み]   … 上記の症状で Slack へ A 区分通知を実行した記録

【閾値到達後の再通知抑制（Issue #796）】
  「連続 N 回に到達したら escalate」だけでは、状態が変わらないまま cron が回るたびに
  同一内容の A-6 通知が飛ぶ（実測: #779 で consecutive が 4・5 と伸び続け、セッションが
  毎回コメント履歴を人力で読んで抑制していた＝判定がスクリプトの外に漏れていた）。
  そこで **通知を実行したら `[prod-drift][通知済み]` を追記する** ことにし、escalate の条件を
  「閾値到達 **かつ** 現在の連続区間内に通知済みマーカーが無い」に変える。
  抑制したときは黙って false にせず `suppressed: true` / `reason: "already_notified"` を返す。
  `[prod-drift][解消]`（または別症状マーカー）が挟まると連続区間そのものが切れるため、
  通知済みマーカーも同時に無効化される（別の state を持たない）。

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
    has_marker,
)

INDETERMINATE_MARKER = "[prod-drift][判定不能]"
NOT_CONFIGURED_MARKER = "[prod-drift][経路未構成]"
# trigger_workers_build.py の呼び出し自体が auto mode classifier にブロックされ、exit code が
# 一切返らなかった状態（L-130・Issue #785）。exit code 軸（判定不能・経路未構成等）とは別軸であり、
# どちらにも丸め込まない（丸め込むと L-130 のリトライ規律が適用されず実行ブロックが握り潰される）。
EXECUTION_BLOCKED_MARKER = "[prod-drift][実行ブロック]"
RESOLVED_MARKER = "[prod-drift][解消]"
# 通知を実行した記録。症状マーカーではないので ALL_MARKERS（＝連続を打ち切る集合）には入れない
# （通知しても症状は続いているため、連続カウントは伸び続けるのが正しい）。
NOTIFIED_MARKER = "[prod-drift][通知済み]"

ALL_MARKERS = (
    INDETERMINATE_MARKER,
    NOT_CONFIGURED_MARKER,
    EXECUTION_BLOCKED_MARKER,
    RESOLVED_MARKER,
)

# `@mention`（A-6）を伴う症状マーカー。緩和にユーザーのアカウント権限（Cloudflare ダッシュボード /
# auto mode 設定）が物理的に必要なもの。`decide()` の `mention` 判定はこの集合の所属だけで決める
# （マーカーを追加するたびに `mention` の分岐式を書き換えなくて済むようにする）。
A6_MARKERS = (NOT_CONFIGURED_MARKER, EXECUTION_BLOCKED_MARKER)

# 連続何回で escalate するか（根拠はモジュール docstring）。
ESCALATION_THRESHOLD = 3


def count_consecutive(bodies: list[str], marker: str) -> int:
    """末尾から数えて `marker` が連続している回数を返す。

    数え方（**行頭一致・引用行の除外**・無関係コメントの読み飛ばし）は
    `issue_marker_counter` が正本。他の `[prod-drift]` マーカー（解消・別種の症状）が
    挟まったらそこで打ち切る（症状が変わった＝連続ではない）。
    """
    return _count_consecutive(bodies, (marker,), ALL_MARKERS)


def is_notification_of(body: str, marker: str) -> bool:
    """このコメントが `marker` の症状に対する通知記録か。

    書式は **`[prod-drift][通知済み]` で始まる行に、対象の症状マーカーを併記する**:

        [prod-drift][通知済み] [prod-drift][経路未構成] を A-6 として Slack 通知した（ts=...）

    症状を併記させるのは、通知済みの記録が **別症状へ漏れない** ようにするため
    （経路未構成で通知した記録が、その後に始まった判定不能の通知まで抑制すると、
    別の障害が黙って握り潰される）。行頭一致で見るので、引用（`> ...`）や
    バッククォート囲みの言及は通知記録として数えない。

    🔴 **症状マーカーは通知済みマーカーの直後（空白を挟んでよい）にある場合だけ数える**
    （Layer 1 CRITICAL・fail-open の実測）。行内のどこかにあれば良いという部分一致だと、
    通知記録の自由文が別症状に言及しただけで（例: `… を通知した。[prod-drift][判定不能] は未発生`）
    その別症状の通知が永久に抑制され、障害が黙って握り潰される。

    症状マーカーと通知記録が **同一コメントに同居** した場合は本判定が優先し、抑制側に倒れる。
    そのため運用手順（`sprint-cycle-router` §1.5 手順 5-3）は通知記録を別コメントで投稿する。
    """
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped.startswith(NOTIFIED_MARKER):
            continue
        if stripped[len(NOTIFIED_MARKER):].lstrip().startswith(marker):
            return True
    return False


def notified_in_current_streak(bodies: list[str], marker: str) -> bool:
    """現在の連続区間内に、その症状の通知記録が既にあるか（Issue #796）。

    末尾から遡り、`marker` の通知記録が先に見つかれば True。区間を切るマーカー
    （解消・別症状）に先に当たれば False。症状マーカー `marker` 自身と、どのマーカーも
    持たないコメント（人手のメモ・別症状の通知記録）は読み飛ばす。
    """
    for body in reversed(bodies):
        if is_notification_of(body, marker):
            return True
        if has_marker(body, (marker,)):
            continue
        if has_marker(body, ALL_MARKERS):
            return False
    return False


def decide(bodies: list[str], marker: str, threshold: int = ESCALATION_THRESHOLD) -> dict:
    """escalate 要否と `@mention` 要否を判定する。

    `@mention` は `user-notification-triage.md` §1 に従い **A 区分のときだけ** 立てる。
    trigger 0 件（`[prod-drift][経路未構成]`）は Cloudflare ダッシュボードで Workers Builds を
    接続し直す以外に復旧手段がなく、飼い主のアカウント権限が物理的に必要なので **A-6**。
    原因未特定の「判定不能」は A 区分ではないため、連続しても通知するだけで `@mention` しない。

    閾値に到達していても、現在の連続区間内に既に通知済みマーカーがあれば **抑制する**
    （`escalate: false` / `suppressed: true` / `reason: "already_notified"`・#796）。
    抑制は黙って false にせず理由を出す（呼び出し側が「閾値未到達」と区別できるようにする）。
    """
    consecutive = count_consecutive(bodies, marker)
    threshold_reached = consecutive >= threshold
    already_notified = notified_in_current_streak(bodies, marker)
    suppressed = threshold_reached and already_notified
    escalate = threshold_reached and not already_notified
    return {
        "marker": marker,
        "consecutive": consecutive,
        "threshold": threshold,
        "threshold_reached": threshold_reached,
        "already_notified": already_notified,
        "escalate": escalate,
        "suppressed": suppressed,
        "reason": "already_notified" if suppressed else None,
        "mention": escalate and marker in A6_MARKERS,
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


def _self_test_notified_suppresses_repeat() -> list[str]:
    """🔴 完了条件（#796）: 閾値到達 → 通知 → 次 firing（状態不変）で再通知しない。"""
    failures: list[str] = []
    notified = [
        f"{NOT_CONFIGURED_MARKER} 1",
        f"{NOT_CONFIGURED_MARKER} 2",
        f"{NOT_CONFIGURED_MARKER} 3",
        f"{NOTIFIED_MARKER} {NOT_CONFIGURED_MARKER} を A-6 として Slack 通知した（ts=...）",
        f"{NOT_CONFIGURED_MARKER} 4",
    ]
    result = decide(notified, NOT_CONFIGURED_MARKER)
    if result["escalate"]:
        failures.append(f"通知済みなのに再通知しようとしている: got={result!r}")
    if not result["suppressed"]:
        failures.append(f"抑制したのに suppressed が立っていない: got={result!r}")
    if result["reason"] != "already_notified":
        failures.append(f"抑制理由が出ていない: got={result.get('reason')!r}")
    if result["mention"]:
        failures.append("抑制中に @mention してはいけない")
    if not result["threshold_reached"]:
        failures.append("閾値到達の事実まで消してはいけない（未到達と区別できなくなる）")
    if result["consecutive"] != 4:
        failures.append(f"通知済みマーカーで連続カウントが壊れている: got={result['consecutive']}")

    # 通知前は従来どおり escalate する（抑制が常時 true になる退行を捕まえる）
    before = decide([f"{NOT_CONFIGURED_MARKER} {i}" for i in range(3)], NOT_CONFIGURED_MARKER)
    if not (before["escalate"] and before["mention"]):
        failures.append(f"未通知の閾値到達は escalate する必要がある: got={before!r}")
    if before["suppressed"] or before["reason"] is not None:
        failures.append(f"未通知なのに抑制扱いになっている: got={before!r}")
    return failures


def _self_test_resolved_reenables_notification() -> list[str]:
    """🔴 完了条件（#796）: 解消を挟んで再び閾値へ到達したら、再度通知する。"""
    failures: list[str] = []
    bodies = [
        f"{NOT_CONFIGURED_MARKER} 1",
        f"{NOT_CONFIGURED_MARKER} 2",
        f"{NOT_CONFIGURED_MARKER} 3",
        f"{NOTIFIED_MARKER} {NOT_CONFIGURED_MARKER} を A-6 として Slack 通知した",
        f"{RESOLVED_MARKER} 再トリガー成功",
        f"{NOT_CONFIGURED_MARKER} 4",
        f"{NOT_CONFIGURED_MARKER} 5",
        f"{NOT_CONFIGURED_MARKER} 6",
    ]
    result = decide(bodies, NOT_CONFIGURED_MARKER)
    if result["consecutive"] != 3:
        failures.append(f"解消後の連続カウントが誤り: got={result['consecutive']}")
    if not result["escalate"]:
        failures.append(f"解消を挟んだ再発は再通知する必要がある: got={result!r}")
    if result["already_notified"] or result["suppressed"]:
        failures.append("解消で通知済みマーカーが無効化されていない")

    # 別症状マーカーも区間を切る（通知済みが他症状へ漏れない）
    other = [
        f"{NOT_CONFIGURED_MARKER} 1",
        f"{NOTIFIED_MARKER} {NOT_CONFIGURED_MARKER} を A-6 として Slack 通知した",
        f"{INDETERMINATE_MARKER} 1",
        f"{INDETERMINATE_MARKER} 2",
        f"{INDETERMINATE_MARKER} 3",
    ]
    other_result = decide(other, INDETERMINATE_MARKER)
    if not other_result["escalate"]:
        failures.append(f"別症状の通知済みで抑制してはいけない: got={other_result!r}")
    return failures


def _self_test_notification_mention_does_not_leak() -> list[str]:
    """🔴 通知記録の自由文中で別症状に言及しても、その症状は抑制されない（Layer 1 CRITICAL）。

    症状マーカーが通知済みマーカーの **直後** にある場合だけ数える、という条件を固定する。
    行内のどこかにあれば良い部分一致に緩めると、この区別テストが落ちる。
    """
    failures: list[str] = []
    bodies = [
        f"{NOTIFIED_MARKER} {NOT_CONFIGURED_MARKER} を通知した。{INDETERMINATE_MARKER} は未発生",
        f"{INDETERMINATE_MARKER} 1",
        f"{INDETERMINATE_MARKER} 2",
        f"{INDETERMINATE_MARKER} 3",
    ]
    result = decide(bodies, INDETERMINATE_MARKER)
    if result["already_notified"]:
        failures.append("通知記録の自由文中の言及で別症状を抑制している（障害が握り潰される）")
    if not result["escalate"]:
        failures.append(f"言及されただけの症状は通常どおり escalate する: got={result!r}")

    # 直後に併記された本来の症状は、従来どおり抑制される
    proper = [
        f"{NOT_CONFIGURED_MARKER} 1",
        f"{NOT_CONFIGURED_MARKER} 2",
        f"{NOT_CONFIGURED_MARKER} 3",
        f"{NOTIFIED_MARKER}  {NOT_CONFIGURED_MARKER} を通知した（空白 2 個でも数える）",
        f"{NOT_CONFIGURED_MARKER} 4",
    ]
    if not decide(proper, NOT_CONFIGURED_MARKER)["suppressed"]:
        failures.append("直後に併記された症状を抑制できていない")
    return failures


def _self_test_below_threshold_is_not_suppressed() -> list[str]:
    """通知記録があっても閾値未満なら抑制ではない（`suppressed` は閾値到達を含意する）。

    `suppressed` の定義から `threshold_reached` を落とす退行を捕まえる。呼び出し側は
    `suppressed: true` を「閾値には到達しているが通知済み」と読むため、閾値未満で立つと
    原因調査が打ち切られる。
    """
    failures: list[str] = []
    bodies = [
        f"{NOTIFIED_MARKER} {NOT_CONFIGURED_MARKER} を通知した",
        f"{NOT_CONFIGURED_MARKER} 1",
    ]
    result = decide(bodies, NOT_CONFIGURED_MARKER)
    if result["consecutive"] != 1 or result["threshold_reached"]:
        failures.append(f"前提が崩れている（連続 1 回・閾値未到達のはず）: got={result!r}")
    if not result["already_notified"]:
        failures.append("通知記録は検出されている必要がある")
    if result["suppressed"] or result["reason"] is not None:
        failures.append(f"閾値未満で抑制扱いにしてはいけない: got={result!r}")
    if result["escalate"]:
        failures.append("閾値未満で escalate してはいけない")
    return failures


def _self_test_notified_marker_must_start_line() -> list[str]:
    """通知済みマーカーの言及・引用では抑制されない（行頭一致・fail-open 防止）。"""
    failures: list[str] = []
    quoted = [
        f"{NOT_CONFIGURED_MARKER} 1",
        f"{NOT_CONFIGURED_MARKER} 2",
        f"メモ:\n> {NOTIFIED_MARKER} 過去の通知を引用しただけ",
        f"{NOT_CONFIGURED_MARKER} 3",
    ]
    result = decide(quoted, NOT_CONFIGURED_MARKER)
    if result["already_notified"]:
        failures.append("引用しただけの通知済みマーカーで抑制している（通知が飛ばなくなる）")
    if not result["escalate"]:
        failures.append(f"引用行を挟んでも 3 連続なら escalate する: got={result!r}")

    mentioned = [
        f"{NOT_CONFIGURED_MARKER} 1",
        f"{NOT_CONFIGURED_MARKER} 2",
        f"`{NOTIFIED_MARKER}` は {NOT_CONFIGURED_MARKER} についてまだ一度も出ていない",
        f"{NOT_CONFIGURED_MARKER} 3",
    ]
    if decide(mentioned, NOT_CONFIGURED_MARKER)["already_notified"]:
        failures.append("行中の言及で抑制している")
    return failures


def _self_test_execution_blocked_mentions() -> list[str]:
    """🔴 完了条件（Issue #785）: 実行ブロックの連続 3 回は A-6 として @mention する。

    exit code 軸の判定不能（`INDETERMINATE_MARKER`）と混同していないかも合わせて固定する
    （実行ブロックは exit code が一切返らない別軸の状態であり、判定不能とは異なるマーカーで
    数える必要がある）。
    """
    failures: list[str] = []
    bodies = [f"{EXECUTION_BLOCKED_MARKER} {i} 回目" for i in range(3)]
    result = decide(bodies, EXECUTION_BLOCKED_MARKER)
    if not (result["escalate"] and result["mention"]):
        failures.append(f"実行ブロックの 3 連続は @mention 付きで escalate する: got={result!r}")

    below = decide([f"{EXECUTION_BLOCKED_MARKER} 1"], EXECUTION_BLOCKED_MARKER)
    if below["mention"] or below["escalate"]:
        failures.append("閾値未満の実行ブロックで escalate / @mention してはいけない")

    # 判定不能マーカーと実行ブロックマーカーは別軸なので混ざらない（互いに連続を打ち切る）
    mixed = [
        f"{EXECUTION_BLOCKED_MARKER} 1",
        f"{EXECUTION_BLOCKED_MARKER} 2",
        f"{INDETERMINATE_MARKER} 別症状（判定不能）",
        f"{EXECUTION_BLOCKED_MARKER} 3",
    ]
    if count_consecutive(mixed, EXECUTION_BLOCKED_MARKER) != 1:
        failures.append("判定不能マーカーが挟まっても実行ブロックの連続が途切れていない")

    # 解消マーカーで実行ブロックの連続もリセットされる
    resolved = [
        f"{EXECUTION_BLOCKED_MARKER} 1",
        f"{EXECUTION_BLOCKED_MARKER} 2",
        f"{RESOLVED_MARKER} 再トリガー成功",
        f"{EXECUTION_BLOCKED_MARKER} 3",
    ]
    if count_consecutive(resolved, EXECUTION_BLOCKED_MARKER) != 1:
        failures.append("解消コメントで実行ブロックの連続がリセットされていない")

    # 🔴 逆方向: 実行ブロックが挟まったら他症状（判定不能）の連続も打ち切られる必要がある
    # （EXECUTION_BLOCKED_MARKER が ALL_MARKERS＝reset 集合から漏れていると、判定不能の
    # 連続カウントが実行ブロックを無視して伸び続け、症状が変わったのに escalate してしまう）。
    reset_other = [
        f"{INDETERMINATE_MARKER} 1",
        f"{INDETERMINATE_MARKER} 2",
        f"{EXECUTION_BLOCKED_MARKER} 別症状（実行ブロック）",
        f"{INDETERMINATE_MARKER} 3",
    ]
    if count_consecutive(reset_other, INDETERMINATE_MARKER) != 1:
        failures.append(
            "実行ブロックマーカーが ALL_MARKERS から漏れており、判定不能の連続を"
            "リセットできていない（症状が変わったのに連続扱いされる）"
        )
    return failures


def _self_test_execution_blocked_quoted_or_inline_is_ignored() -> list[str]:
    """🔴 引用・行中の言及は実行ブロックの発生としても解消としても数えない（fail-open 防止）。"""
    failures: list[str] = []
    quoted = [
        f"{EXECUTION_BLOCKED_MARKER} 1",
        f"{EXECUTION_BLOCKED_MARKER} 2",
        f"調査メモ:\n> {RESOLVED_MARKER} 再トリガー成功\nを引用しただけで、まだ解消していない",
        f"{EXECUTION_BLOCKED_MARKER} 3",
    ]
    if count_consecutive(quoted, EXECUTION_BLOCKED_MARKER) != 3:
        failures.append("引用された解消マーカーで実行ブロックの連続が打ち切られている")

    inline_claim = [f"本文中に {EXECUTION_BLOCKED_MARKER} と書いただけのコメント"]
    if count_consecutive(inline_claim, EXECUTION_BLOCKED_MARKER) != 0:
        failures.append("行頭にない実行ブロックマーカーを症状として数えている")
    return failures


def run_self_test() -> int:
    groups = [
        ("単発・閾値未満では通知しない", _self_test_single_firing_does_not_escalate),
        ("閾値到達で escalate", _self_test_threshold_escalates),
        ("経路未構成は A-6 として @mention", _self_test_not_configured_mentions),
        ("実行ブロックは A-6 として @mention", _self_test_execution_blocked_mentions),
        ("実行ブロックの引用・言及は無視", _self_test_execution_blocked_quoted_or_inline_is_ignored),
        ("解消・別症状でリセット", _self_test_resolved_resets),
        ("無関係コメントは無視", _self_test_unrelated_comment_is_ignored),
        ("引用・言及ではリセットしない", _self_test_quoted_marker_does_not_reset),
        ("通知済みなら再通知を抑制する", _self_test_notified_suppresses_repeat),
        ("解消後は再び通知できる", _self_test_resolved_reenables_notification),
        ("通知済みマーカーも行頭一致", _self_test_notified_marker_must_start_line),
        ("通知記録の言及は別症状へ漏れない", _self_test_notification_mention_does_not_leak),
        ("閾値未満は抑制ではない", _self_test_below_threshold_is_not_suppressed),
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
        suffix = f" suppressed={result['suppressed']}({result['reason']})" if result["suppressed"] else ""
        print(f"連続 {result['consecutive']} 回 / 閾値 {result['threshold']} "
              f"→ escalate={result['escalate']} mention={result['mention']}{suffix}")
    # 0 = 通知不要 / 1 = escalate 必要（呼び出し側が終了コードだけでも分岐できるようにする）
    sys.exit(1 if result["escalate"] else 0)


if __name__ == "__main__":
    main()
