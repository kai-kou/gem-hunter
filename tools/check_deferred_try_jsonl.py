#!/usr/bin/env python3
"""check_deferred_try_jsonl.py — 見送り Try ログ（deferred_try.jsonl）の整形性を検査する（Issue #704）

## なぜ必要か

`content/analytics/retro/deferred_try.jsonl` は `retrospective` スキル Step 3-0（Q1 再発判定）の
中核データで、**次回以降のレトロが読み戻して「同じ Try が再発しているか」を判定する** ための
唯一の記録である。1 行でも壊れる（JSON パース不能・必須フィールド欠落・値域外）と、その行は
判定材料から静かに脱落する。さらに `.gitignore` は `content/analytics/*` を除外したうえで
`!content/analytics/retro/` で本ディレクトリだけを復活させる **反転パターン** に依存しており、
除外規則を少し触るだけで追跡対象から外れ、クラウドではコンテナ破棄とともに消える（#417）。
どちらも「壊れても誰も気づかない」失敗モードなので機械検査する。

## ignore 状態ではなく「追跡状態」を検査する理由

守りたい不変条件は「このファイルが **git に追跡されている**（＝コンテナ破棄後も残る）」ことで
あって「`.gitignore` にマッチしないこと」ではない。かつ `git check-ignore` は既定で index を
参照するため、**追跡済みファイルは `.gitignore` にマッチしても常に exit 1（＝除外されていない）**
を返す。つまり check-ignore ベースの検査は「除外されている」分岐に到達できない死に枝で、
再包含行 `!content/analytics/retro/` を削除しても PASS する fail-open だった。そのため本検査は
`git ls-files --error-unmatch` で **追跡状態そのもの** を見る（0 = 追跡済み / 1 = 未追跡 /
それ以外 = 判定不能）。

## 検査する違反（すべて fail-closed。判定できないものを PASS にしない）

  1. git の追跡対象になっていない（`git ls-files --error-unmatch` が未追跡と答える）
  2. 有効行が 0 件（空ファイル・空行のみ）
  3. JSON としてパースできない行（クォート抜け・末尾カンマ等）
  4. トップレベルが JSON オブジェクトでない行（配列・文字列・数値）
  5. 必須フィールド（date / title / q1 / q2 / defer_reason）の欠落
  6. 値域違反: q1 / q2 が "YES" / "NO" 以外、defer_reason が
     medium / medium_commented / over_quota / low_single_file / high_commented 以外
  7. date が `YYYY-MM-DD JST` 形式でない、または実在しない日付（2026-13-45 JST 等）
  8. title が文字列でない、または空文字
  9. related_issue の型違反（**存在する場合のみ** 検査。下記「採用した仮定」を参照）
  10. reevaluated_at の型違反（**存在する場合のみ** 検査。null または `YYYY-MM-DD HH:MM JST`
      形式の実在日時以外は違反。Issue #707: 空文字・JST 抜けだと `jq 'select(.reevaluated_at
      == null)'` が false になり over_quota Try が「消費済み」と誤判定され永久に合流しなくなる）
  11. defer_reason と q1/q2 の組み合わせ矛盾（Issue #727）: `medium` / `low_single_file` /
      `medium_commented` は priority:high 相当ではなかった見送り（`q1 == "NO"` かつ
      `q2 == "NO"`）を表すため、どちらかが `"YES"` なのにこれらの defer_reason が付いていたら
      矛盾（「high 相当だったのに優先度不足として見送った」という誤った履歴になる）。逆に
      `over_quota` / `high_commented` は priority:high 相当だった見送り（`q1` または `q2` が
      `"YES"`）を表すため、両方 `"NO"` なのにこれらが付いていたら矛盾。**q1 / q2 / defer_reason
      のいずれかが既に値域違反（違反 6）の行は、この整合性検査の対象外とする**（値が不正な状態で
      high 相当か否かを判定すると二重に誤った違反メッセージを出すため。値域違反として既に検出済み
      なので見逃しにはならない）
  12. `defer_reason` が `high_commented` / `medium_commented`（いずれも既存 Issue へ追記して
      完了）なのに `related_issue` が空（Issue #727 のフォローアップ・#815 で `medium_commented`
      へ拡張）: `related_issue` フィールドの欠落・`null`・空文字（空白のみを含む）のいずれも
      「空」として検出する。これら 2 値は「既存 Issue へ追記した」ことを表す値であり、追記先
      Issue 番号（`related_issue`）を伴わないと値の意味そのものと矛盾する（SKILL.md Step 3-0
      見送りログのフィールド表）。**defer_reason が値域違反（違反 6）の行は、この検査の対象外と
      する**（違反 11 と同じ理由）

さらに **違反ではなく WARNING**（exit code には影響しない）として、既知フィールド集合の外に
あるキー（`reevaluted_at` のような typo）を報告する（Issue #707・値域は締めるがキー集合は
締めない現行方針は維持）。

**空行の扱い**: 空白のみの行は「行の区切り」として **スキップする**（違反にしない）。JSONL の
末尾改行を違反にしないため。ただし有効行が 1 件も無ければ違反 2 として検出する（空ファイルを
「違反 0 件」として PASS させない）。

**記法は問わない**: `{"date": "..."}`（spaced）と `{"date":"..."}`（compact）はどちらも valid。
実データに両方が混在しているが、統一は本検査の目的ではない（Issue #704 のスコープ外）。

## 採用した仮定（実データ準拠・2026-08-30 JST 時点で 51 行を実測）

  - 必須フィールドは Issue #704 が定める 5 件（date / title / q1 / q2 / defer_reason）とする。
    `related_issue` は実データ 51 行すべてに存在するが **仕様上の必須ではない** ため必須にせず、
    「存在する場合のみ型を検査する」に留める（権威順: 仕様 > 現行コード）。
  - `related_issue` は `null` / 文字列 のほかに **整数** も許容する。実データに
    `"related_issue": 660`（int）が 2 件あり、Issue 番号として意味が通る（`"L-138"` のような
    lessons ID も文字列で入る）。「実データと矛盾する仕様を先に決めない」方針に従い、
    int を弾く仕様にはしない。ただし `bool`（`true` / `false`）は Issue 参照として無意味なので
    弾く（Python では `bool` が `int` の派生であるため明示的に除外している）。
  - `date` は実データ 51 行すべてが `YYYY-MM-DD JST`（14 文字）だったため、この形式を必須とする
    （`docs/rules/datetime-rules.md`: 記録に残る日時は JST 表記）。
  - `reevaluated_at`（Issue #707）は SKILL.md §3 フィールド表どおり **任意** とする（省略 = 未再評価）。
    存在するときだけ null / `YYYY-MM-DD HH:MM JST`（日付のみの `date` と違い時刻まで必須）を検査する。
  - 既知フィールド集合の外側のキー（typo）は **違反にはせず WARNING に留める**。値域は締めるが
    キー集合までは締めない、という `related_issue` に対する既存方針を typo 検知にも一貫させるため
    （fail-closed にすると将来の正当な拡張フィールドまで巻き込んで壊す）。
  - `defer_reason: "high_commented"`（Issue #727・SKILL.md Step 3-0 判定フロー「YES → Step 3-A →
    類似 Issue あり → Step 3-B」の出口）は、priority:high 相当（Q1 または Q2 が YES）だが
    既存 Issue への追記で完了したケースを表す。`medium`（優先度不足）と混同すると「高優先だったのに
    見送られた」という誤った履歴が残り Q1 の再発カウントが壊れるため、defer_reason と q1/q2 の
    組み合わせを整合性検査する（実データ 75 行は全て q1/q2 が NO のため、既存行は本検査を
    無改修で通過する・2026-08-31 JST 時点で実測）。
  - `defer_reason: "medium_commented"`（Issue #815・SKILL.md Step 3-0 判定フロー「NO → Step 3-A →
    類似 Issue あり」の出口）は、priority:high 相当ではない（Q1 も Q2 も NO）が既存 Issue への
    追記で完了したケースを表す。#815 以前はこの出口専用の値が無く、`medium`（「優先度不足・
    重複なし」の意味）へ記録すると値の意味と実態（重複あり）が食い違っていた。`medium_commented`
    は non-high 側（q1/q2 が両方 NO）に属するため `NOT_HIGH_REASONS` に加えるが、`high_commented`
    と同じ理由で `related_issue` を必須とする（違反 12 の対象を 2 値へ拡張）。実データの既存
    `medium` 行（`related_issue` が非 null のものを含む・2026-09-02 JST 時点で 23 行実測）は
    「重複チェックで類似 Issue が見つからず、たまたま関連 Issue 番号だけ書き添えた」ケースであり
    `medium_commented` への遡及的な書き換えは対象外（本 PR は担当ファイル外の既存ログを変更しない
    ・Issue #815 完了条件）。`medium` は `related_issue` の有無を型検査の対象にするだけで値の
    有無自体は問わないため、これらの既存行は無改修で本検査を通過する。
  - `defer_reason: "high_commented"` / `"medium_commented"` はいずれも `related_issue` を必須と
    する（違反 12・Issue #727 フォローアップ・#815 で 2 値へ拡張）。「既存 Issue へ追記して完了
    した」という値の意味が追記先 Issue 番号を要求するため、`related_issue` が欠落 / `null` /
    空文字（空白のみ含む）のいずれかだと矛盾する行として検出する。実データ 75 行の
    `high_commented` 該当行はいずれも `related_issue` が非 null のため、既存行は本検査を無改修で
    通過する（2026-08-31 JST 時点で実測。`medium_commented` は #815 時点で実データに 0 件）。

## 終了コード

  0 = 違反なし
  1 = 違反あり
  2 = 判定不能（ファイル不在・デコード不能・JSON のネストが深すぎる・git コマンド不在 / エラー）
      ※ 判定不能を 0 にしない（黙って PASS するのが最も危険な失敗モードであるため）

使い方:
  python3 tools/check_deferred_try_jsonl.py              # 本判定
  python3 tools/check_deferred_try_jsonl.py --self-test  # ネットワーク・git 非依存のユニットテスト
  python3 tools/check_deferred_try_jsonl.py --path FILE  # 別ファイルを検査（デバッグ / self-test 用）
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFERRED_TRY_PATH = REPO_ROOT / "content" / "analytics" / "retro" / "deferred_try.jsonl"

# SSOT: .claude/skills/retrospective/SKILL.md §「見送りログのフィールド」表
SKILL_FIELD_SSOT = ".claude/skills/retrospective/SKILL.md §「見送りログのフィールド」表"
REQUIRED_FIELDS = ("date", "title", "q1", "q2", "defer_reason")
YES_NO = ("YES", "NO")
DEFER_REASONS = ("medium", "medium_commented", "over_quota", "low_single_file", "high_commented")
# Issue #727: defer_reason は「Q1/Q2 が priority:high 相当（YES）だったか」を裏切ってはならない。
# NOT_HIGH_REASONS は「high 相当ではなかった」見送り、HIGH_REASONS は「high 相当だった」見送り。
# Issue #815: medium_commented（Step 3-0 判定フロー NO 分岐・類似 Issue あり）は non-high 側。
NOT_HIGH_REASONS = ("medium", "low_single_file", "medium_commented")
HIGH_REASONS = ("over_quota", "high_commented")
assert set(NOT_HIGH_REASONS) | set(HIGH_REASONS) == set(DEFER_REASONS), (
    "NOT_HIGH_REASONS / HIGH_REASONS が DEFER_REASONS と分割一致していません"
)
# Issue #815: 「既存 Issue へ追記して完了した」ことを表す defer_reason はいずれも related_issue
# （追記先 Issue 番号）を必須とする（違反 12）。high 相当 / non-high 相当の両側にまたがる。
RELATED_ISSUE_REQUIRED_REASONS = ("high_commented", "medium_commented")
DATE_SUFFIX = " JST"
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
# SSOT: .claude/skills/retrospective/SKILL.md §「見送りログのフィールド」表 の reevaluated_at 行
# （"持ち越しを合流・再評価した日時（未再評価なら省略。ある行は「消費済み」の印）"）。
# 任意フィールドは REQUIRED_FIELDS に含めない（存在するときだけ形式検査する）。
OPTIONAL_DATETIME_FIELDS = ("reevaluated_at",)
# キー集合の外側を検出する対象（typo 検知）。値域は締めるがキー集合まで締めない現行方針は
# 維持しつつ、未知キーは「壊れ」ではなく「気づき」として WARNING（exit 0 のまま）で報告する
# （採用した判断: fail-closed にすると実データの将来の正当な拡張フィールドまで巻き込んで
# 壊すため、typo 検知は違反ではなく警告に留める・#707）。
KNOWN_FIELDS = frozenset(REQUIRED_FIELDS) | {"related_issue", *OPTIONAL_DATETIME_FIELDS}

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_UNDETERMINED = 2


class Undetermined(Exception):
    """判定不能（違反ゼロではない）を表す例外。握り潰さず main まで伝播させて exit 2 にする。"""


def _fmt(value: object) -> str:
    """違反メッセージ用に値を短く表示する（長い title で行が溢れないように切り詰める）。"""
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


# `strptime` はフォーマット文字列中のリテラル空白を内部で `\s+`（Unicode 空白クラス）として
# コンパイルするため、全角スペース（U+3000）・タブ・NBSP（\xa0）・改行等の非 ASCII 空白でも
# 区切りとして通してしまう（`DATETIME_FORMAT` の "%Y-%m-%d %H:%M" が該当。`DATE_FORMAT` は
# リテラル空白を含まないため対象外）。`strptime` へ渡す前に `re.fullmatch` で
# 「ASCII 数字 + ASCII ハイフン/コロン + リテラル半角スペース」の構造そのものを固定して
# この見逃しを塞ぐ（PR #711 レビュー指摘・実測: 全角スペース/タブ/NBSP/改行のいずれも旧実装では
# `is_valid_jst_datetime` を通過していた）。`[0-9]` を使い `\d`（Unicode 数字も一致しうる）を
# 避けているのは念のための二重の締め（全角数字は strptime 自体の内部パターンでも弾かれるが、
# 判定を fullmatch 単体で完結させるため）。
_DATE_HEAD_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DATETIME_HEAD_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$")


def _is_valid_jst_string(value: object, head_pattern: re.Pattern[str], fmt: str) -> bool:
    """`{head_pattern にマッチする head} JST` 形式で、かつ head が fmt で実在する日時/日付なら True。

    `is_valid_jst_date` / `is_valid_jst_datetime` の共通実装（PR #711 レビュー指摘: 両者は
    サフィックス確認 → 構造チェック → `strptime` という同一構造で、違うのは正規表現と
    フォーマット文字列だけだったため、将来 JST サフィックスの扱いを片方だけ変えて `date` と
    `reevaluated_at` の判定が食い違う事故を防ぐために一本化する）。
    """
    if not isinstance(value, str) or not value.endswith(DATE_SUFFIX):
        return False
    head = value[: -len(DATE_SUFFIX)]
    if not head_pattern.fullmatch(head):
        return False
    try:
        datetime.strptime(head, fmt)
    except ValueError:
        return False
    return True


def is_valid_jst_date(value: object) -> bool:
    """`YYYY-MM-DD JST` 形式で、かつ実在する日付なら True。"""
    return _is_valid_jst_string(value, _DATE_HEAD_RE, DATE_FORMAT)


def is_valid_jst_datetime(value: object) -> bool:
    """`YYYY-MM-DD HH:MM JST` 形式で、かつ実在する日時なら True（`reevaluated_at` 用）。"""
    return _is_valid_jst_string(value, _DATETIME_HEAD_RE, DATETIME_FORMAT)


def is_valid_related_issue(value: object) -> bool:
    """related_issue は null / 文字列 / 整数のみ許容する（bool は除外・docstring「採用した仮定」）。"""
    if value is None or isinstance(value, str):
        return True
    return isinstance(value, int) and not isinstance(value, bool)


def is_empty_related_issue(obj: dict) -> bool:
    """`high_commented` の related_issue 必須検査で使う「空」判定（違反 12）。

    欠落・`None`・空文字（空白のみ含む）・`bool`・0 以下の整数のいずれも「空」として扱う。
    「空文字も空とみなす」判定を `None` のみに緩めると、`"related_issue": ""` の行を見逃す
    （Issue #727 フォローアップ）。整数の非正値を空に含めるのは、`related_issue: 0` が
    「追記先 Issue が実在する」という値の意味を満たさないのに必須検査を素通りしていたため
    （#824 Layer 1 指摘・fail-open の是正）。
    """
    if "related_issue" not in obj:
        return True
    value = obj["related_issue"]
    if value is None:
        return True
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        # Issue 番号は 1 以上。0 / 負数は「追記先が実在する」という値の意味を満たさないため
        # 空として扱う（#824 Layer 1 指摘: 数値だと非空扱いになり必須検査が fail-open していた）。
        return value <= 0
    return isinstance(value, str) and not value.strip()


def check_record(obj: object, lineno: int) -> list[str]:
    """1 レコード分の違反メッセージ一覧を返す（違反なしなら空リスト）。"""
    if not isinstance(obj, dict):
        return [f"L{lineno}: トップレベルが JSON オブジェクトではありません（{type(obj).__name__}）"]

    violations: list[str] = []
    missing = [f for f in REQUIRED_FIELDS if f not in obj]
    if missing:
        violations.append(
            f"L{lineno}: 必須フィールドがありません: {', '.join(missing)}（SSOT: {SKILL_FIELD_SSOT}）"
        )

    if "title" in obj:
        title = obj["title"]
        if not isinstance(title, str) or not title.strip():
            violations.append(f"L{lineno}: title は空でない文字列である必要があります: {_fmt(title)}")

    if "date" in obj and not is_valid_jst_date(obj["date"]):
        violations.append(
            f"L{lineno}: date は `YYYY-MM-DD JST` 形式の実在日である必要があります: {_fmt(obj['date'])}"
        )

    for field in ("q1", "q2"):
        if field in obj and obj[field] not in YES_NO:
            violations.append(
                f"L{lineno}: {field} は {' / '.join(YES_NO)} のいずれかである必要があります: {_fmt(obj[field])}"
            )

    q1 = obj.get("q1")
    q2 = obj.get("q2")
    defer_reason = obj.get("defer_reason")
    q1_valid = q1 in YES_NO
    q2_valid = q2 in YES_NO
    defer_valid = defer_reason in DEFER_REASONS

    if "defer_reason" in obj and not defer_valid:
        violations.append(
            f"L{lineno}: defer_reason は {' / '.join(DEFER_REASONS)} のいずれかである必要があります: "
            f"{_fmt(obj['defer_reason'])}（SSOT: {SKILL_FIELD_SSOT}）"
        )

    # Issue #727: q1 / q2 / defer_reason がいずれも値域内のときだけ組み合わせ整合性を検査する
    # （値域違反はすでに上（q1/q2）・直前（defer_reason）で個別に検出済みなので、値が不正な
    # 状態のまま high 相当判定に踏み込んで二重の誤ったメッセージを出さない）。
    if q1_valid and q2_valid and defer_valid:
        is_high = q1 == "YES" or q2 == "YES"
        if is_high and defer_reason in NOT_HIGH_REASONS:
            violations.append(
                f"L{lineno}: defer_reason が {_fmt(defer_reason)} ですが q1={q1} / q2={q2} は "
                f"priority:high 相当（YES）です。high 相当の見送りは {' / '.join(HIGH_REASONS)} を"
                f"使ってください（SSOT: {SKILL_FIELD_SSOT}）"
            )
        elif not is_high and defer_reason in HIGH_REASONS:
            violations.append(
                f"L{lineno}: defer_reason が {_fmt(defer_reason)} ですが q1={q1} / q2={q2} は "
                f"priority:high 相当ではありません（両方 NO）。{' / '.join(HIGH_REASONS)} は "
                f"q1 または q2 が YES のときだけ使ってください（SSOT: {SKILL_FIELD_SSOT}）"
            )

    if "related_issue" in obj and not is_valid_related_issue(obj["related_issue"]):
        violations.append(
            f"L{lineno}: related_issue は null / 文字列 / 整数のいずれかである必要があります: "
            f"{_fmt(obj['related_issue'])}"
        )

    # Issue #727 フォローアップ（違反 12・#815 で high_commented / medium_commented の 2 値へ拡張）:
    # defer_reason が値域内で related_issue 必須の値のときだけ必須性を検査する（defer_reason 自体が
    # 値域違反の行は違反 6 で既に検出済みのため対象外・違反 11 と同じ理由）。
    if defer_valid and defer_reason in RELATED_ISSUE_REQUIRED_REASONS and is_empty_related_issue(obj):
        violations.append(
            f"L{lineno}: defer_reason が {_fmt(defer_reason)} のとき related_issue は必須です"
            f"（欠落 / null / 空文字は不可）: {_fmt(obj.get('related_issue'))}（SSOT: {SKILL_FIELD_SSOT}）"
        )

    # reevaluated_at は任意フィールド（Issue #707）。存在する場合のみ、null または
    # `YYYY-MM-DD HH:MM JST` 実在日時を要求する。空文字・JST 抜け・非文字列は
    # retrospective スキル Step 3-0 の `jq 'select(.reevaluated_at == null)'` を false のまま
    # 通してしまい、over_quota の Try が「消費済み」と誤判定されて永久に合流しなくなるため。
    if "reevaluated_at" in obj:
        reevaluated_at = obj["reevaluated_at"]
        if reevaluated_at is not None and not is_valid_jst_datetime(reevaluated_at):
            violations.append(
                f"L{lineno}: reevaluated_at は null または `YYYY-MM-DD HH:MM JST` 形式の実在日時"
                f"である必要があります: {_fmt(reevaluated_at)}（SSOT: {SKILL_FIELD_SSOT}）"
            )

    return violations


def unknown_field_warnings(obj: object, lineno: int) -> list[str]:
    """既知フィールド集合の外にあるキーを WARNING として返す（typo 検知・違反にはしない）。

    値域は締めるがキー集合は締めない、という現行の設計判断は変えない（`related_issue` の
    docstring と同じ「実データと矛盾する仕様を先に決めない」方針）。ただし typo（例:
    `reevaluted_at`）は無音のまま無限に合流し続ける実害があるため、気づけるように WARNING
    だけは出す（exit code には影響させない・#707）。
    """
    if not isinstance(obj, dict):
        return []
    extra = sorted(set(obj) - KNOWN_FIELDS)
    if not extra:
        return []
    return [f"L{lineno}: 未知フィールド（typo の可能性）: {', '.join(extra)}"]


def check_text(text: str) -> tuple[list[str], int, list[str]]:
    """JSONL 本文を検査し (違反メッセージ一覧, 有効行数, 警告メッセージ一覧) を返す。

    行分割は `str.splitlines()` ではなく `split("\\n")` を使う（`splitlines()` は U+2028 /
    U+2029 / U+0085 等でも分割するため、それらを値に含む整形式の 1 レコードが 2 行に割れて
    偽陽性になり、以降の行番号もずれる）。CRLF 互換のため各行末の `\\r` だけ取り除く。
    """
    violations: list[str] = []
    warnings: list[str] = []
    valid_lines = 0
    for lineno, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue  # 空行は行区切りとしてスキップ（有効行 0 件は下で違反にする）
        valid_lines += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            violations.append(f"L{lineno}: JSON としてパースできません: {e.msg}（col {e.colno}）")
            continue
        except RecursionError as e:
            # 深くネストした JSON はパース中に再帰上限へ達する。違反（exit 1）ではなく
            # 判定不能（exit 2）へ振り分ける（生 traceback で落として違反に化けさせない）。
            raise Undetermined(f"L{lineno}: JSON のネストが深すぎて解析できません: {e}") from e
        violations.extend(check_record(obj, lineno))
        warnings.extend(unknown_field_warnings(obj, lineno))

    if valid_lines == 0:
        violations.append("有効なレコードが 1 件もありません（空ファイル / 空行のみ）")
    return violations, valid_lines, warnings


def check_tracked(path: Path, runner=subprocess.run, repo_root: Path = REPO_ROOT) -> list[str]:
    """対象ファイルが git の追跡対象（index 登録済み）かを検査する。

    `git ls-files --error-unmatch -- <path>` の終了コード:
      0 = 追跡済み（OK） / 1 = 未追跡（違反） / それ以外 = エラー。
    エラー（git 不在・タイムアウト・リポジトリ外など）は「追跡済み」と決めつけず Undetermined を
    送出する（見逃し経路: git が無い環境で例外を握り潰して PASS にしてしまう fail-open）。
    `--` で pathspec の開始位置を明示し、`-` 始まりのパスがオプションと誤解釈されるのを防ぐ。
    """
    try:
        proc = runner(
            ["git", "ls-files", "--error-unmatch", "--", str(path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as e:
        raise Undetermined(f"git コマンドが見つかりません: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise Undetermined(f"git ls-files がタイムアウトしました: {e}") from e
    if proc.returncode == 0:
        return []
    if proc.returncode == 1:
        return [
            f"{path} が git の追跡対象になっていません"
            "（追跡されないとコンテナ破棄でレトロの再発判定材料が失われます）"
        ]
    raise Undetermined(
        f"git ls-files が想定外の終了コード {proc.returncode} を返しました: {(proc.stderr or '').strip()}"
    )


def check_file(path: Path, runner=subprocess.run, repo_root: Path = REPO_ROOT) -> list[str]:
    """ファイル 1 本を検査して違反メッセージ一覧を返す。判定不能は Undetermined を送出する。"""
    if not path.exists():
        raise Undetermined(f"{path} が見つかりません")
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        raise Undetermined(f"{path} を UTF-8 テキストとして読み込めません: {e}") from e

    if path.is_relative_to(repo_root):
        violations = check_tracked(path, runner=runner, repo_root=repo_root)
    else:
        # リポジトリ外のパス（--path でのデバッグ指定等）は git 追跡を問えないため内容検査だけ行う。
        # 判定できなかったことを黙らせず 1 行出力する（exit 2 にはしない）。
        print(f"ℹ️ {path} はリポジトリ外のため git 追跡検査をスキップします")
        violations = []
    text_violations, _, warnings = check_text(text)
    for w in warnings:
        print(f"⚠️ {w}")
    return violations + text_violations


# --------------------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------------------

VALID_RECORD = {
    "date": "2026-08-24 JST",
    "title": "サンプル Try",
    "q1": "NO",
    "q2": "NO",
    "defer_reason": "medium",
    "related_issue": None,
}
VALID_LINE = (
    '{"date": "2026-08-24 JST", "title": "サンプル Try", "q1": "NO", "q2": "NO", '
    '"defer_reason": "medium", "related_issue": null}'
)


class _FakeProc:
    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr


class _RecordingRunner:
    """git を起動せず固定の終了コードを返す fake runner（呼ばれた事実とコマンドを記録する）。"""

    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        return _FakeProc(self.returncode, self.stderr)


def _line(**overrides) -> str:
    """VALID_RECORD をベースに 1 行分の JSONL を組み立てる（キーを消したいときは dict を直接操作する）。"""
    record = dict(VALID_RECORD)
    record.update(overrides)
    return json.dumps(record, ensure_ascii=False)


def _run_self_test() -> None:
    cases = 0  # ケース数はハードコードせず実測で数える

    # --- check_text: 正常系 ---
    v, n, _ = check_text(VALID_LINE + "\n")
    assert v == [] and n == 1, f"正常系 失敗: {v} / {n}"
    cases += 1

    # compact 記法・int / 文字列 related_issue・末尾空行の混在も PASS（記法統一は求めない）
    mixed = (
        VALID_LINE
        + "\n"
        + '{"date":"2026-08-27 JST","title":"compact","q1":"YES","q2":"NO",'
        '"defer_reason":"high_commented","related_issue":"L-138"}\n'
        + '{"date":"2026-08-28 JST","title":"int issue","q1":"NO","q2":"YES",'
        '"defer_reason":"over_quota","related_issue":660}\n'
        "\n"
    )
    v, n, _ = check_text(mixed)
    assert v == [] and n == 3, f"記法混在 失敗: {v} / {n}"
    cases += 1

    # related_issue は必須ではない（キーごと無い行も PASS・仕様は 5 フィールド）
    no_related = dict(VALID_RECORD)
    del no_related["related_issue"]
    v, n, _ = check_text(json.dumps(no_related, ensure_ascii=False) + "\n")
    assert v == [] and n == 1, f"related_issue 省略 失敗: {v}"
    cases += 1

    # CRLF 改行でも行が壊れない
    v, n, _ = check_text(VALID_LINE + "\r\n")
    assert v == [] and n == 1, f"CRLF 失敗: {v} / {n}"
    cases += 1

    # U+2028 / U+2029 / U+0085 を値に含む 1 レコードを 2 行に割らない（splitlines 過剰一致の回帰）
    for sep in ("\u2028", "\u2029", "\u0085"):  # 見えない文字はエスケープで明示する
        v, n, _ = check_text(_line(title=f"行内{sep}区切り") + "\n")
        assert v == [] and n == 1, f"行分割 失敗({sep!r}): {v} / {n}"
    cases += 1

    # --- 入力バリアント: 壊れ方を変えて実証する ---
    # (a) クォート抜け（JSON パース不能）
    v, _, _w = check_text('{"date": "2026-08-24 JST", title: "x"}\n')
    assert len(v) == 1 and "パースできません" in v[0], f"パース不能 失敗: {v}"
    cases += 1

    # (b-1) 仕様（Issue #704）が定める 5 フィールドと定数が一致していることをリテラルで固定する。
    #       下のループは REQUIRED_FIELDS を走査するため「定数から 1 語消す」変異はループだけでは
    #       検出できない（ケースごと消えてしまう）。仕様側の期待値をここに直書きして殺す。
    assert set(REQUIRED_FIELDS) == {"date", "title", "q1", "q2", "defer_reason"}, (
        f"必須フィールド定義が仕様（Issue #704 / {SKILL_FIELD_SSOT}）とずれています: {REQUIRED_FIELDS}"
    )
    cases += 1

    # (b-2) 必須フィールド欠落: REQUIRED_FIELDS を 1 件ずつ落として当該フィールド名が出ることを確認する
    #       （フィールドを増やしてもメッセージ検証は自動追随する）
    for field in REQUIRED_FIELDS:
        broken = dict(VALID_RECORD)
        del broken[field]
        v, _, _w = check_text(json.dumps(broken, ensure_ascii=False) + "\n")
        assert len(v) == 1 and field in v[0], f"必須欠落 失敗({field}): {v}"
        cases += 1

    # (c) 値域外: q1 / q2 / defer_reason を 1 件ずつ単独で壊す（まとめず分離する）
    for field, bad in (("q1", "no"), ("q2", "yes"), ("defer_reason", "high")):
        v, _, _w = check_text(_line(**{field: bad}) + "\n")
        assert len(v) == 1 and field in v[0], f"値域違反 失敗({field}): {v}"
        cases += 1

    # (d) 日付形式違反（JST 無し / 実在しない日 / 桁不足 / 別 TZ / 非文字列）
    for bad_date in ("2026-08-24", "2026-13-45 JST", "2026-8-3 JST", "2026-08-24 UTC", 20260824):
        v, _, _w = check_text(_line(date=bad_date) + "\n")
        assert len(v) == 1 and "date" in v[0], f"日付違反 失敗({bad_date}): {v}"
        cases += 1

    # (e) title 空文字・非文字列（数値 / null）
    for bad_title in ("   ", 123, None):
        try:
            v, _, _w = check_text(_line(title=bad_title) + "\n")
        except Exception as e:  # 非文字列 title で例外が漏れる実装退行を FAIL として表面化する
            raise AssertionError(f"title 違反 失敗({bad_title!r}): 例外が漏れました: {e!r}") from e
        assert len(v) == 1 and "title" in v[0], f"title 違反 失敗({bad_title!r}): {v}"
        cases += 1

    # (f) related_issue の型違反（bool / 配列）
    for bad in (True, [1]):
        v, _, _w = check_text(_line(related_issue=bad) + "\n")
        assert len(v) == 1 and "related_issue" in v[0], f"related_issue 違反 失敗({bad!r}): {v}"
        cases += 1

    # (g) トップレベルが配列 / 文字列
    v, _, _w = check_text('[{"date": "2026-08-24 JST"}]\n')
    assert len(v) == 1 and "オブジェクトではありません" in v[0], f"非オブジェクト 失敗: {v}"
    cases += 1

    # (f-2) reevaluated_at: 無い行・null は従来どおり PASS（未再評価 = 消費前）
    v, _, _w = check_text(VALID_LINE + "\n")  # VALID_LINE に reevaluated_at キー自体が無い
    assert v == [], f"reevaluated_at 省略 失敗: {v}"
    cases += 1
    v, _, _w = check_text(_line(reevaluated_at=None) + "\n")
    assert v == [], f"reevaluated_at null 失敗: {v}"
    cases += 1

    # (f-3) reevaluated_at: 正しい `YYYY-MM-DD HH:MM JST` は PASS
    v, _, _w = check_text(_line(reevaluated_at="2026-08-30 14:23 JST") + "\n")
    assert v == [], f"reevaluated_at 正常系 失敗: {v}"
    cases += 1

    # (f-4) reevaluated_at: Issue #707 が挙げた実害パターンを個別に FAIL させる
    #       ①空文字 ②JST 抜け ③非文字列(数値) ④日付のみ(時刻無し・桁不足) ⑤存在しない日時
    #       ⑥別 TZ ⑦キー名 typo は「別フィールド」として無視される（このテストでは検査不要、
    #       typo 検知は下の (f-5) 未知フィールド WARNING で別途担保する）
    for bad in (
        "", "2026-08-30 14:23", 20260830, "2026-08-30 JST", "2026-08-30 25:99 JST",
        "2026-08-30 14:23 UTC", "2026-8-3 4:5 JST",  # 桁不足（strptime は許容するため長さ検査必須）
        # ⑧⑨⑩⑪: strptime のリテラル空白が `\s+` 扱いになる穴（PR #711 レビュー指摘・実測で
        # 旧実装は全て通過していた）。日付と時刻の区切りを非 ASCII 空白に差し替えた反例。
        "2026-08-30　14:23 JST",  # 全角スペース（U+3000）
        "2026-08-30\t14:23 JST",  # タブ
        "2026-08-30\xa014:23 JST",  # NBSP（U+00A0）
        "2026-08-30\n14:23 JST",  # 改行
    ):
        v, _, _w = check_text(_line(reevaluated_at=bad) + "\n")
        assert len(v) == 1 and "reevaluated_at" in v[0], f"reevaluated_at 違反 失敗({bad!r}): {v}"
        cases += 1

    # (f-5) 未知フィールド（typo `reevaluted_at` 等）は違反にはせず WARNING として報告する
    typo_line = dict(VALID_RECORD)
    typo_line["reevaluted_at"] = "2026-08-30 14:23 JST"  # わざと typo
    v, _, w = check_text(json.dumps(typo_line, ensure_ascii=False) + "\n")
    assert v == [], f"未知フィールド 違反として検出してしまった: {v}"
    assert len(w) == 1 and "reevaluted_at" in w[0], f"未知フィールド WARNING 失敗: {w}"
    cases += 1

    # 既知フィールドのみなら WARNING はゼロ件
    v, _, w = check_text(_line(reevaluated_at="2026-08-30 14:23 JST") + "\n")
    assert w == [], f"既知フィールドのみで WARNING が出た: {w}"
    cases += 1

    # (g-2) Issue #727: defer_reason と q1/q2 の組み合わせ整合性
    # 正常系: high 相当（YES）× over_quota / high_commented、非 high 相当（NO/NO）× medium /
    # low_single_file はいずれも PASS。high_commented は違反 12（related_issue 必須）も
    # 同時に満たす必要があるため related_issue を明示する。
    for q1, q2, reason, related_issue in (
        ("YES", "NO", "over_quota", None),
        ("NO", "YES", "over_quota", None),
        ("YES", "YES", "high_commented", "727"),
        ("NO", "NO", "medium", None),
        ("NO", "NO", "low_single_file", None),
        ("NO", "NO", "medium_commented", "815"),  # Issue #815: non-high の既存 Issue 追記完了
    ):
        v, _, _w = check_text(
            _line(q1=q1, q2=q2, defer_reason=reason, related_issue=related_issue) + "\n"
        )
        assert v == [], f"defer_reason 整合性 正常系 失敗({q1},{q2},{reason}): {v}"
        cases += 1

    # 異常系: high 相当なのに non-high 用の defer_reason（誤って「優先度不足」と記録される事故）
    # medium_commented は related_issue 必須（違反 12）でもあるため related_issue を明示し、
    # 違反 11（このテストの検証対象）だけを分離して検証する（違反 12 と混ざると len(v)==1 が崩れる）。
    for q1, q2, reason, related_issue in (
        ("YES", "NO", "medium", None),
        ("NO", "YES", "low_single_file", None),
        ("YES", "YES", "medium", None),
        ("YES", "NO", "medium_commented", "815"),  # Issue #815: 非 high 専用値を high に誤用
    ):
        v, _, _w = check_text(
            _line(q1=q1, q2=q2, defer_reason=reason, related_issue=related_issue) + "\n"
        )
        assert len(v) == 1 and "priority:high 相当（YES）です" in v[0], (
            f"defer_reason 整合性 異常系(high 相当) 失敗({q1},{q2},{reason}): {v}"
        )
        cases += 1

    # 異常系: non-high なのに high 専用の defer_reason（over_quota / high_commented を誤用）
    # related_issue は非空にしておき、違反 12（related_issue 必須）と混ざらず違反 11 だけを
    # 検証する（両者は独立した違反のため、混ぜるとどちらの検出漏れも見えなくなる）。
    for reason in ("over_quota", "high_commented"):
        v, _, _w = check_text(
            _line(q1="NO", q2="NO", defer_reason=reason, related_issue="1") + "\n"
        )
        assert len(v) == 1 and "priority:high 相当ではありません" in v[0], (
            f"defer_reason 整合性 異常系(非 high) 失敗({reason}): {v}"
        )
        cases += 1

    # 境界: q1/q2 自体が値域外のときは整合性検査をスキップし、値域違反 1 件だけを報告する
    # （二重の誤ったメッセージを出さない・docstring 違反 11 の注記）
    v, _, _w = check_text(_line(q1="maybe", defer_reason="medium") + "\n")
    assert len(v) == 1 and "q1" in v[0], f"defer_reason 整合性 境界(q1 値域外) 失敗: {v}"
    cases += 1

    # (g-3) Issue #727 フォローアップ（違反 12・#815 で medium_commented へ拡張）:
    # high_commented / medium_commented は related_issue が必須
    # 正常系: 文字列 / 整数のいずれでも related_issue が非空なら PASS（q1/q2 は各 reason の
    # NOT_HIGH_REASONS / HIGH_REASONS の分類と矛盾しない組み合わせを使う）
    for reason, q1, q2 in (("high_commented", "YES", "NO"), ("medium_commented", "NO", "NO")):
        for related_issue in ("660", 660, "L-138"):
            v, _, _w = check_text(
                _line(q1=q1, q2=q2, defer_reason=reason, related_issue=related_issue) + "\n"
            )
            assert v == [], f"{reason} related_issue 正常系 失敗({related_issue!r}): {v}"
            cases += 1

    # 異常系: 欠落 / null / 空文字 / 空白のみ のいずれも FAIL（「空文字も空とみなす」を実証）
    for reason, q1, q2 in (("high_commented", "YES", "NO"), ("medium_commented", "NO", "NO")):
        missing_related = dict(VALID_RECORD)
        missing_related.update(q1=q1, q2=q2, defer_reason=reason)
        del missing_related["related_issue"]
        v, _, _w = check_text(json.dumps(missing_related, ensure_ascii=False) + "\n")
        assert len(v) == 1 and "related_issue" in v[0] and "必須" in v[0], (
            f"{reason} related_issue 欠落 失敗: {v}"
        )
        cases += 1

        # 0 / 負数は Issue 番号として無効なので「空」に含める（#824 Layer 1 指摘の fail-open 是正）。
        # bool は違反 9（型違反）で先に落ちるためここでは扱わない。
        for bad_related in (None, "", "   ", 0, -1):
            v, _, _w = check_text(
                _line(q1=q1, q2=q2, defer_reason=reason, related_issue=bad_related) + "\n"
            )
            assert len(v) == 1 and "related_issue" in v[0] and "必須" in v[0], (
                f"{reason} related_issue 異常系 失敗({bad_related!r}): {v}"
            )
            cases += 1

    # 境界: defer_reason が値域違反のとき（例: "high"）は違反 12 の検査対象外
    # （related_issue が null でも二重の違反にならず、値域違反 1 件だけが出る）
    v, _, _w = check_text(_line(defer_reason="high", related_issue=None) + "\n")
    assert len(v) == 1 and "defer_reason" in v[0], (
        f"high_commented related_issue 境界(defer_reason 値域外) 失敗: {v}"
    )
    cases += 1

    # (h) 行番号の採番: 2 行目だけを壊し L2 として報告されることを確認（start=1 の回帰）
    v, _, _w = check_text(VALID_LINE + "\n" + _line(q1="no") + "\n")
    assert len(v) == 1 and v[0].startswith("L2:"), f"行番号 失敗: {v}"
    cases += 1

    # (i) 空ファイル・空行のみ → fail-closed（違反 0 件で PASS させない）
    for empty in ("", "\n", "   \n\n"):
        v, n, _ = check_text(empty)
        assert n == 0 and len(v) == 1 and "1 件もありません" in v[0], f"空ファイル 失敗({empty!r}): {v}"
        cases += 1

    # (j) 深すぎるネストは違反ではなく判定不能（RecursionError の振り分け）
    deep = "[" * 200_000 + "]" * 200_000
    try:
        check_text(deep + "\n")
    except Undetermined:
        pass
    except RecursionError:  # pragma: no cover - 変異検出時のみ到達
        raise AssertionError("深いネスト 失敗（RecursionError が素通りした）")
    else:  # pragma: no cover - 変異検出時のみ到達
        raise AssertionError("深いネスト 失敗（判定不能にならなかった）")
    cases += 1

    # --- check_tracked: 全分岐（git を起動しない fake runner で検証する） ---
    tracked = _RecordingRunner(0)
    assert check_tracked(Path("x"), runner=tracked) == [], "追跡済み 失敗"
    assert tracked.calls and "--error-unmatch" in tracked.calls[0], f"呼び出し形 失敗: {tracked.calls}"
    cases += 1

    untracked = check_tracked(Path("x"), runner=_RecordingRunner(1))
    assert len(untracked) == 1 and "追跡対象になっていません" in untracked[0], f"未追跡 失敗: {untracked}"
    cases += 1

    for bad_runner, label in (
        (_RecordingRunner(128, "fatal"), "exit 128"),
        (_raise_file_not_found, "git 不在"),
        (_raise_timeout, "タイムアウト"),
    ):
        try:
            check_tracked(Path("x"), runner=bad_runner)
        except Undetermined:
            pass
        else:  # pragma: no cover - 失敗時のみ到達
            raise AssertionError(f"判定不能 失敗（{label} を PASS にしてしまった）")
        cases += 1

    # --- main() から exit code までの貫通確認（システム一時領域 = リポジトリ外で行う） ---
    # main() の出力（PASS / ❌ / ⚠️）は self-test の結果ではないため飲み込む。
    with tempfile.TemporaryDirectory() as tmp, \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        tmp_root = Path(tmp).resolve()
        ok_path = tmp_root / "ok.jsonl"
        ok_path.write_text(VALID_LINE + "\n", encoding="utf-8")
        rc = main(["--path", str(ok_path)])
        assert rc == EXIT_OK, f"main 正常系 失敗（exit {rc}）"

        ng_path = tmp_root / "ng.jsonl"
        ng_path.write_text('{"date": "2026-08-24 JST"}\n', encoding="utf-8")
        rc = main(["--path", str(ng_path)])
        assert rc == EXIT_VIOLATION, f"main 違反系 失敗（exit {rc}）"

        rc = main(["--path", str(tmp_root / "missing.jsonl")])
        assert rc == EXIT_UNDETERMINED, f"main ファイル不在 失敗（exit {rc}）"

        bin_path = tmp_root / "bin.jsonl"
        bin_path.write_bytes(b"\xff\xfe\x00binary")
        rc = main(["--path", str(bin_path)])
        assert rc == EXIT_UNDETERMINED, f"main 非 UTF-8 失敗（exit {rc}）"

        # WARNING（未知フィールド typo）が main() → check_file() → stdout の print まで実際に
        # 配線されていることの確認（PR #711 レビュー指摘: check_file() の `for w in warnings:
        # print(...)` を丸ごと削除しても --self-test は緑のままだった＝未貫通だった箇所）。
        # 外側の redirect_stdout に混ぜると内容を検証できないため、このケースだけ別の
        # StringIO へ内側で捕り直す。
        warn_path = tmp_root / "warn.jsonl"
        typo_record = dict(VALID_RECORD)
        typo_record["reevaluted_at"] = "2026-08-30 14:23 JST"  # わざと typo
        warn_path.write_text(json.dumps(typo_record, ensure_ascii=False) + "\n", encoding="utf-8")
        warn_buf = io.StringIO()
        with contextlib.redirect_stdout(warn_buf):
            rc = main(["--path", str(warn_path)])
        warn_output = warn_buf.getvalue()
        assert rc == EXIT_OK, f"main WARNING系 失敗（違反ではないはずが exit {rc}）"
        assert "⚠️" in warn_output and "reevaluted_at" in warn_output, (
            f"WARNING が main() 経由で stdout まで届いていません: {warn_output!r}"
        )
    cases += 5  # ok / ng / missing / bin / warn の 5 グループ

    with tempfile.TemporaryDirectory() as tmp, \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        tmp_root = Path(tmp).resolve()
        ok_path = tmp_root / "ok.jsonl"
        ok_path.write_text(VALID_LINE + "\n", encoding="utf-8")

        # git 追跡検査が main まで配線されていることの確認（呼び出しごと消す変異を殺す）:
        # 一時ディレクトリを repo_root に見立て、fake runner が「未追跡」を返したら
        # 内容が正常でも違反終了すること・runner が実際に呼ばれたことを確認する。
        untracked_runner = _RecordingRunner(1)
        rc = main(["--path", str(ok_path)], runner=untracked_runner, repo_root=tmp_root)
        assert untracked_runner.calls, "main 追跡検査 失敗（git 検査が呼ばれていない）"
        assert rc == EXIT_VIOLATION, f"main 追跡検査 失敗（未追跡なのに exit {rc}）"

        tracked_runner = _RecordingRunner(0)
        rc = main(["--path", str(ok_path)], runner=tracked_runner, repo_root=tmp_root)
        assert tracked_runner.calls and rc == EXIT_OK, f"main 追跡済み 失敗（exit {rc}）"
    cases += 2  # untracked / tracked の 2 グループ

    print(f"[deferred-try-jsonl] self-test OK（{cases} ケース）")


def _raise_file_not_found(*args, **kwargs):
    raise FileNotFoundError("git")


def _raise_timeout(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd="git ls-files", timeout=10)


def main(argv: list[str] | None = None, runner=subprocess.run, repo_root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description="見送り Try ログ（deferred_try.jsonl）の整形性検査")
    parser.add_argument(
        "--self-test", action="store_true", help="ネットワーク・git 非依存のユニットテストを実行する"
    )
    parser.add_argument(
        "--path",
        default=None,
        help=f"検査対象の JSONL（既定: {DEFERRED_TRY_PATH.relative_to(REPO_ROOT)}）",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        try:
            _run_self_test()
            return EXIT_OK
        except AssertionError as e:
            print(f"❌ [deferred-try-jsonl] self-test FAIL: {e}", file=sys.stderr)
            return EXIT_VIOLATION

    # CWD 基準の相対パスと git（cwd=repo_root）へ渡すパスが食い違わないよう絶対パスへ正規化する
    path = Path(args.path).expanduser().resolve() if args.path else DEFERRED_TRY_PATH
    try:
        violations = check_file(path, runner=runner, repo_root=repo_root)
    except Undetermined as e:
        print(f"⚠️ 判定不能: {e}", file=sys.stderr)
        return EXIT_UNDETERMINED

    if violations:
        for v in violations:
            print(f"❌ {v}", file=sys.stderr)
        print(f"❌ [deferred-try-jsonl] FAIL: {len(violations)} 件の違反（{path}）", file=sys.stderr)
        return EXIT_VIOLATION

    print(f"[deferred-try-jsonl] PASS: {path} の整形性に問題なし")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
