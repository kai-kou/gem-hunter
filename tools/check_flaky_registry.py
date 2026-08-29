#!/usr/bin/env python3
"""check_flaky_registry.py — flaky-tests.md の登録要件・賞味期限切れを機械検査する（Issue #223）

【背景】docs/04_development/flaky-tests.md は「赤くなったテストが本表に載っていれば既知の flaky
として扱ってよい」という運用ルールを持つが、これは記載内容が正しいことを前提にした設計。
Issue #145 では誤診断された flaky エントリが 2 スプリントにわたり運用対象として素通りした
（真因は next/link のプリフェッチが原因のプロダクトバグだった）。

【検査する違反】（いずれも「恒久対応」列が未解決＝現役エントリにのみ適用する。過去に解決済みの
エントリへ新しい登録要件を遡及適用しない）
  1. 登録要件違反: 各エントリの「再現条件の切り分け」列が空、または
     単体実行 / ファイル単位実行 / フルスイート実行 いずれかの言及が無い場合
  2. 賞味期限切れ: 「登録日」列から FLAKY_REGISTRY_STALE_DAYS（既定 7 日）以上
     経過している場合

【終了コード】
  0 = 違反なし
  1 = 違反あり（登録要件違反または賞味期限切れ）
  2 = 判定不能（ファイル不在・表のパース失敗）

使い方:
  python3 tools/check_flaky_registry.py            # 本判定
  python3 tools/check_flaky_registry.py --self-test # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLAKY_REGISTRY_PATH = REPO_ROOT / "docs" / "04_development" / "flaky-tests.md"

STALE_DAYS_DEFAULT = 7

RESOLVED_KEYWORDS = ("解決済み", "対応不要", "Closed", "closed")
REPRODUCTION_REQUIRED_PHRASES = ("単体実行", "ファイル単位実行", "フルスイート")

TABLE_HEADER_RE = re.compile(r"^\|\s*対象\s*\|")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _split_row(line: str) -> list[str]:
    """Markdown テーブルの 1 行をセル配列に分解する（先頭・末尾の空セルは除去）。"""
    cells = line.strip().split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def parse_registry(text: str) -> tuple[list[str], list[list[str]]] | None:
    """「## 既知の flaky 一覧」節のテーブルを (ヘッダ, 行リスト) として返す。見つからなければ None。"""
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if TABLE_HEADER_RE.match(line):
            header_idx = i
            break
    if header_idx is None:
        return None

    header = _split_row(lines[header_idx])
    # 次の行は区切り線（|---|---|...）のはずなのでスキップ
    rows: list[list[str]] = []
    for line in lines[header_idx + 2 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = _split_row(line)
        if not cells:
            continue
        rows.append(cells)
    return header, rows


def _cell(header: list[str], row: list[str], name: str) -> str:
    try:
        idx = header.index(name)
    except ValueError:
        return ""
    if idx >= len(row):
        return ""
    return row[idx]


def check_registry(
    text: str, today: date, stale_days: int = STALE_DAYS_DEFAULT
) -> tuple[list[str], list[str]]:
    """(登録要件違反リスト, 賞味期限切れリスト) を返す。テーブルが無ければ両方空リスト。"""
    parsed = parse_registry(text)
    if parsed is None:
        return [], []
    header, rows = parsed

    requirement_violations: list[str] = []
    stale_violations: list[str] = []

    for row in rows:
        target = _cell(header, row, "対象") or "(対象列不明)"

        resolution = _cell(header, row, "恒久対応")
        is_resolved = any(kw in resolution for kw in RESOLVED_KEYWORDS)
        if is_resolved:
            # 過去に解決済みのエントリへ新しい登録要件を遡及適用しない。
            continue

        repro = _cell(header, row, "再現条件の切り分け")
        if not repro or not any(p in repro for p in REPRODUCTION_REQUIRED_PHRASES):
            requirement_violations.append(
                f"{target}: 「再現条件の切り分け」列に単体実行/ファイル単位実行/フルスイートの言及がありません"
            )

        registered_raw = _cell(header, row, "登録日")
        if not registered_raw or not DATE_RE.match(registered_raw):
            requirement_violations.append(f"{target}: 「登録日」列が YYYY-MM-DD 形式で記載されていません")
            continue

        registered_date = datetime.strptime(registered_raw, "%Y-%m-%d").date()
        age_days = (today - registered_date).days
        if age_days >= stale_days:
            stale_violations.append(
                f"{target}: 登録日 {registered_raw} から {age_days} 日経過（恒久対応が未解決のまま放置されています）"
            )

    return requirement_violations, stale_violations


def run_self_test() -> bool:
    today = date(2026, 8, 30)

    # ケース1: 要件を満たす解決済みエントリ → 違反なし
    ok_resolved = """
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-a | 症状a | 原因a | 単体実行/ファイル単位実行/フルスイートで確認 | 緩和a | 解決済み | 2026-08-01 | 2026-08-01 |
"""
    req, stale = check_registry(ok_resolved, today)
    assert req == [], f"ケース1 失敗: {req}"
    assert stale == [], f"ケース1 失敗: {stale}"

    # ケース2: 現役エントリだが登録から7日未満 → 違反なし
    fresh_active = """
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-b | 症状b | 原因b | 単体実行/ファイル単位実行/フルスイートで確認 | 緩和b | #999 で対応中 | 2026-08-25 | 2026-08-25 |
"""
    req, stale = check_registry(fresh_active, today)
    assert req == [], f"ケース2 失敗: {req}"
    assert stale == [], f"ケース2 失敗: {stale}"

    # ケース3: 現役エントリで登録から7日以上経過 → 賞味期限切れ検出
    stale_active = """
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-c | 症状c | 原因c | 単体実行/ファイル単位実行/フルスイートで確認 | 緩和c | #999 で対応中 | 2026-08-01 | 2026-08-01 |
"""
    req, stale = check_registry(stale_active, today)
    assert req == [], f"ケース3 失敗: {req}"
    assert len(stale) == 1, f"ケース3 失敗: {stale}"

    # ケース3b: 境界値ちょうど stale_days 日経過 → 賞味期限切れ検出（>= の境界値を固定する）
    boundary_registered = (today - timedelta(days=STALE_DAYS_DEFAULT)).strftime("%Y-%m-%d")
    boundary_active = f"""
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-c2 | 症状c2 | 原因c2 | 単体実行/ファイル単位実行/フルスイートで確認 | 緩和c2 | #999 で対応中 | {boundary_registered} | {boundary_registered} |
"""
    req, stale = check_registry(boundary_active, today)
    assert len(stale) == 1, f"ケース3b 失敗（境界値 {STALE_DAYS_DEFAULT} 日ちょうどを検出できていない）: {stale}"

    # ケース3c: 境界値の1日前（stale_days - 1 日経過）→ まだ賞味期限切れではない
    just_before_registered = (today - timedelta(days=STALE_DAYS_DEFAULT - 1)).strftime("%Y-%m-%d")
    just_before_active = f"""
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-c3 | 症状c3 | 原因c3 | 単体実行/ファイル単位実行/フルスイートで確認 | 緩和c3 | #999 で対応中 | {just_before_registered} | {just_before_registered} |
"""
    req, stale = check_registry(just_before_active, today)
    assert stale == [], f"ケース3c 失敗（境界値の1日前を誤って賞味期限切れ判定した）: {stale}"

    # ケース3d: 各再現条件フレーズが単独でも要件を満たすことを個別に確認する
    # （3フレーズ全部を含むテキストだけでテストすると、1フレーズを削る変異を検知できない。
    #  REPRODUCTION_REQUIRED_PHRASES を動的に参照すると、フレーズ自体が消える変異では
    #  ループ対象からも消えて検知できないため、ハードコードした期待フレーズで固定する）
    expected_phrases = ("単体実行", "ファイル単位実行", "フルスイート")
    assert set(REPRODUCTION_REQUIRED_PHRASES) == set(expected_phrases), (
        "REPRODUCTION_REQUIRED_PHRASES が想定外の値です。self-test 側の expected_phrases も更新してください: "
        f"{REPRODUCTION_REQUIRED_PHRASES}"
    )
    for phrase in expected_phrases:
        single_phrase_active = f"""
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-phrase | 症状 | 原因 | {phrase}のみで確認 | 緩和 | #999 で対応中 | 2026-08-29 | 2026-08-29 |
"""
        req, stale = check_registry(single_phrase_active, today)
        assert req == [], f"ケース3d 失敗（フレーズ「{phrase}」単独が要件を満たさなかった）: {req}"

    # ケース4: 未解決エントリで再現条件の切り分け列が空 → 登録要件違反
    missing_repro = """
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-d | 症状d | 原因d |  | 緩和d | #999 で対応中 | 2026-08-25 | 2026-08-25 |
"""
    req, stale = check_registry(missing_repro, today)
    assert len(req) == 1, f"ケース4 失敗: {req}"

    # ケース5: 未解決エントリで「再現条件の切り分け」列自体が無い旧形式の表 → 列不在も登録要件違反として検出
    old_format_no_column = """
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 現在の緩和策 | 恒久対応 | 登録日 |
|---|---|---|---|---|---|
| test-e | 症状e | 原因e | 緩和e | #999 で対応中 | 2026-08-25 |
"""
    req, stale = check_registry(old_format_no_column, today)
    assert len(req) >= 1, f"ケース5 失敗（列不在を検出できていない）: {req}"

    # ケース8: 解決済みエントリは再現条件の切り分け列が空でも遡及適用しない → 違反なし
    resolved_without_repro = """
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-g | 症状g | 原因g |  | 緩和g | 解決済み | 2026-08-01 | 2026-08-01 |
"""
    req, stale = check_registry(resolved_without_repro, today)
    assert req == [] and stale == [], f"ケース8 失敗（解決済みエントリへ遡及適用してしまった）: {req} {stale}"

    # ケース6: 登録日が無い → 登録要件違反（賞味期限判定はスキップされ二重報告しない）
    missing_date = """
## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| test-f | 症状f | 原因f | 単体実行/ファイル単位実行/フルスイートで確認 | 緩和f | #999 で対応中 |  |  |
"""
    req, stale = check_registry(missing_date, today)
    assert len(req) == 1, f"ケース6 失敗: {req}"
    assert stale == [], f"ケース6 失敗（登録日不明なのに賞味期限判定してしまった）: {stale}"

    # ケース7: テーブル自体が存在しない（エントリ0件の別ファイル） → 違反なし
    no_table = "# 何か別のドキュメント\n\n内容\n"
    req, stale = check_registry(no_table, today)
    assert req == [] and stale == [], "ケース7 失敗"

    print("[flaky-registry] self-test OK（12 項目）")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行する")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=STALE_DAYS_DEFAULT,
        help=f"賞味期限切れとみなす経過日数（既定 {STALE_DAYS_DEFAULT} 日）",
    )
    args = parser.parse_args()

    if args.self_test:
        try:
            run_self_test()
            return 0
        except AssertionError as e:
            print(f"[flaky-registry] self-test FAIL: {e}", file=sys.stderr)
            return 1

    if not FLAKY_REGISTRY_PATH.exists():
        print(f"⚠️ 判定不能: {FLAKY_REGISTRY_PATH} が見つかりません", file=sys.stderr)
        return 2

    text = FLAKY_REGISTRY_PATH.read_text(encoding="utf-8")
    if parse_registry(text) is None:
        print(f"⚠️ 判定不能: {FLAKY_REGISTRY_PATH} に「## 既知の flaky 一覧」テーブルが見つかりません", file=sys.stderr)
        return 2

    today = datetime.now(timezone.utc).date()
    requirement_violations, stale_violations = check_registry(text, today, args.stale_days)

    if not requirement_violations and not stale_violations:
        print("[flaky-registry] PASS: 登録要件違反・賞味期限切れエントリなし")
        return 0

    for v in requirement_violations:
        print(f"❌ 登録要件違反: {v}", file=sys.stderr)
    for v in stale_violations:
        print(f"❌ 賞味期限切れ: {v}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
