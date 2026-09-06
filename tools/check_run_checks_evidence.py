#!/usr/bin/env python3
"""check_run_checks_evidence.py — PR 本文の run_checks 結果表が「本物」かを検査する（Issue #463）。

## なぜ必要か

`.claude/hooks/pre-pr-create-check.sh` 4.5 節は「`## run_checks 結果` 見出しの下に `|` で
始まる行が 1 つでもあるか」だけを見ており、**表の中身を一切検証していない**。次のダミー本文が
実機で通過することが確認されている（Issue #463 本文）:

    ## run_checks 結果
    （実行していません、これはダミーです）
    | これは本物のテスト結果に見えるダミー |

本ツールは「Claude が意図的に偽装するのを防ぐ」ものではなく、**うっかり貼り忘れ・貼り間違い・
古い別物の表を貼るのを取り逃さないこと** を狙う（issue 本文）。`pre-pr-create-check.sh` への配線・
`tools/run_checks.sh` への self-test 配線・ドキュメント更新は本タスクのスコープ外（別 Issue で行う）。

## 採用した方式（親セッションが決定済み）

案 1（既知チェック名との照合・本命）+ 案 3（列構造の検証）の組み合わせ。案 2（実行トークンの
`.git/` 突合）は、`run_checks` 実行と PR 作成が別セッションにまたがる運用（本リポジトリの実態）で
詰まるため不採用。

## 判定の 4 本柱

1. **セクション抽出**: `.claude/hooks/pre-pr-create-check.sh` 4.5 節の awk と同義の見出し判定。
   ⚠️ `tools/check_evidence_freshness.py` に同義の独立実装（`_HEADING_RE` / `_HEADING_GENERIC_RE`・
   `md_fence.fence_flags` によるフェンス除外・全角スペース正規化・見出し複数回出現時の全走査）が
   既にあるため、**本ツールはそれを import して再利用する**（3 箇所目の独自実装を増やさない）。
   `check_evidence_freshness.py` 自身は「表の中身」を見ないため（SHA 行の有無だけを見る）、
   本ツールが新規に持つのはその先の「セクション内のテーブル行を集める」処理だけである。
2. **列構造の検証**（案 3）: `tools/run_checks.sh` の実際の出力形式
   （`| チェック | 結果 | 所要秒数 |` ヘッダ + `|---|---|---|` 区切り + データ行）と整合するかを見る。
   データ行が 3 列であること、結果セルが既知ステータス語彙（`PASS` / `FAIL` / `FAIL(timeout)` /
   `SKIP`）であることを検証する。
3. **既知チェック名との照合**（案 1・本命）: `tools/run_checks.sh` から `run_check` /
   `run_check_timeout` / `skip_check` / `RESULTS+=(...)` の 4 形式でチェック名を抽出し、
   表のチェック名がその集合に含まれるかを「割合」と「絶対数」の両方で判定する（閾値の根拠は
   `_THRESH_*` 定数のコメントを参照）。
4. **完走性の検証（末尾チェック名の在否）**: 上記 2・3 だけでは「`run_checks.sh` の先頭部分だけを
   並べた表」（列構造も既知名も正当）を落とせない。`run_checks.sh` は上から順に実行される
   シェルスクリプトであるため、**既知チェック名を初出位置の定義順で並べたときの末尾
   `_TAIL_CHECK_COUNT` 件のうち 1 件以上が表に含まれること** を「最後まで完走した」ことの
   証拠として要求する（`_TAIL_CHECK_COUNT` のコメントに閾値のトレードオフを明記）。

いずれも fail-closed（`docs/rules/check-tool-design-rules.md` §1 / §2）: 判定不能は `0` に丸めない。
既知名が 1 件も抽出できない・表セクションが無い・列が壊れている・既知名との一致が薄い・完走した
形跡が無い、のいずれも「妥当」とはみなさない。

## 本ツールが検証しないこと（意図的に受け入れる範囲・反例作成レンズによる特定）

1. **表の内容が、その `実行時点コミット:` の SHA で実際に生成されたかは検証しない**。別ブランチで
   完走させた本物の表をコピーし、SHA 行だけを現在の head へ書き換えたケースは通ってしまう。
   `check_evidence_freshness.py` も SHA 文字列の一致しか見ておらず、表の生成元コミットまでは
   追跡できない（本ツールもその限界を引き継ぐ）。
2. **PR 作成後に HEAD が進んだ場合の再検査はしない**。本ツールを呼ぶフックは
   `mcp__github__create_pull_request` の時点でしか発火しないため、作成後の追加コミットに
   よる証跡の陳腐化はマージ前ゲート（`check_evidence_freshness.py` の手動実行）が担当する。

## 失敗経路の列挙（#474 必須項目 1）

1. `run_checks.sh` が読めない（存在しない・権限無し・不正 UTF-8） → `run_checks_unreadable`（判定不能・exit 2）
2. `run_checks.sh` から既知チェック名が 1 件も抽出できない → `no_known_names`（判定不能・exit 2）
3. `--body-file` が読めない（存在しない・権限無し・不正 UTF-8） → `body_unreadable`（判定不能・exit 2）
4. PR 本文に対象見出しセクションが 1 つも無い → `no_section`（不正・exit 1）
5. セクションはあるがテーブル行（`|` で始まる行）が 1 行も無い → `no_table_rows`（不正・exit 1）
6. データ行が 0 件（ヘッダ行のみ、または区切り行だけ） → `no_data_rows`（不正・exit 1）
7. データ行が 3 列でない・結果セルの語彙が既知ステータスでない（列構造の破綻） → `invalid`（不正・exit 1）
8. データ行のチェック名が既知集合と一致する割合・絶対数のいずれかが閾値未満（手打ちの偽装） → `invalid`（不正・exit 1）
9. データ行の重複が異常に多い（同一チェック名の水増しコピペ・#896 型の負ケース） → `invalid`（不正・exit 1）
10. 列構造・既知名・重複はすべて正当だが、定義順で最後のほうの既知チェック名が表に 1 件も
    含まれない（先頭部分だけの打ち切り実行結果） → `incomplete_run`（不正・exit 1）
11. 複数セクションのうち **いずれか 1 つ** が上記すべてを満たす → `valid`（exit 0・ANY セマンティクス。
    `check_evidence_freshness.py` の ANY セマンティクスと同じ考え方 = 追記で貼り直した PR を誤ブロックしない）
12. 上記以外の想定外の内部エラー → `internal_error`（判定不能・exit 2。ブロックしすぎない側の最終防波堤）

## 使い方

    python3 tools/check_run_checks_evidence.py --body-file pr_body.md
    gh pr view N --json body -q .body | python3 tools/check_run_checks_evidence.py
    python3 tools/check_run_checks_evidence.py --body-file pr_body.md --json
    python3 tools/check_run_checks_evidence.py --body-file pr_body.md --run-checks-path tools/run_checks.sh
    python3 tools/check_run_checks_evidence.py --self-test

## 終了コード

| コード | 意味 | 判定の性質 |
|---|---|---|
| `0` | 表が妥当（いずれかのセクションが既知名照合・列構造・完走性のすべてを満たす） | 検査が走り、違反が無かった |
| `1` | 表が不正（セクション不在・テーブル行不在・列不整合・既知名との不一致・異常な重複・完走した形跡が無い） | 検査が走り、違反を検出した |
| `2` | 判定不能（`run_checks.sh` が読めない・既知名が 1 件も抽出できない・`--body-file` が読めない・想定外の内部エラー） | 検査自体が成立しなかった |

`2`（判定不能）を `0` に丸めない。対象 0 件（セクション不在・データ行不在）を `0` に丸めない
（fail-closed・`docs/rules/check-tool-design-rules.md` §1 / §2）。

## 配線（本タスクのスコープ外）

`.claude/hooks/pre-pr-create-check.sh` への配線・`tools/run_checks.sh` への self-test 配線・
`docs/rules/pr-review-flow-summary.md` の更新は、このタスク（Issue #463 の実装のみ）では行わない。
親セッションが後続作業として行う（並行作業中のファイル衝突を避けるため）。したがって本スクリプトは
現時点では `# tool-wiring-ok:` マーカーを持たない（配線タスクが完了した時点で判断する）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ──────────────────────────────────────────────
# 既存実装の再利用（セクション見出し判定・フェンス除外）
# ──────────────────────────────────────────────
# `check_evidence_freshness.py` の `_HEADING_RE` / `_HEADING_GENERIC_RE` は
# `.claude/hooks/pre-pr-create-check.sh` 4.5 節の awk 正規表現と同義の独立実装として既に
# 存在する（相互参照コメント付き）。本ツールはこれを import して再利用し、3 箇所目の
# 独立実装を増やさない（タスク要件・#906 WARNING 5 と同じ思想）。
# `md_fence.fence_flags` はフェンス判定そのものの共有ヘルパー。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_evidence_freshness import _HEADING_GENERIC_RE, _HEADING_RE  # noqa: E402
from md_fence import fence_flags  # noqa: E402

# ──────────────────────────────────────────────
# 正規表現（既知チェック名の抽出・表セルの検証）
# ──────────────────────────────────────────────

# `run_check "名前" ...` / `run_check_timeout "名前" <秒> ...`（`run_check_timeout` は内部で
# `run_check` から呼ばれる以外に、E2E 等が直接 `run_check_timeout "名前" "$TIMEOUT" cmd...` の
# 形で呼ぶため両方を 1 パターンで拾う）。
_RE_RUN_CHECK = re.compile(r'^\s*run_check(?:_timeout)?\s+"([^"]+)"', re.MULTILINE)
# `skip_check "名前" "理由"`
_RE_SKIP_CHECK = re.compile(r'^\s*skip_check\s+"([^"]+)"', re.MULTILINE)
# `RESULTS+=("名前|STATUS|秒数")` のような直接追加
_RE_RESULTS_DIRECT = re.compile(r'RESULTS\+=\("([^"|]+)\|', re.MULTILINE)

_KNOWN_NAME_PATTERNS = (_RE_RUN_CHECK, _RE_SKIP_CHECK, _RE_RESULTS_DIRECT)

# 表の結果セルが取りうる既知ステータス語彙（`tools/run_checks.sh` の `RESULTS+=` 実装が正）
_STATUS_VOCAB_RE = re.compile(r"^(PASS|FAIL|FAIL\(timeout\)|SKIP)$")
# 所要秒数セル（整数・小数どちらも許容。`run_checks.sh` は整数秒だが将来の小数化に備える）
_SECONDS_CELL_RE = re.compile(r"^\d+(?:\.\d+)?秒$")
# Markdown テーブルの区切り行のセル（`---` / `:---` / `---:` / `:---:`）
_SEPARATOR_CELL_RE = re.compile(r"^:?-{1,}:?$")

# ──────────────────────────────────────────────
# 閾値（根拠はコメントに明記・check-tool-design-rules.md §1 逸脱時の必須要件ではないが
# 閾値の恣意性を残さないため明記する）
# ──────────────────────────────────────────────
#
# 実測（2026-09 時点）: tools/run_checks.sh は run_check(_timeout) 109 件 + skip_check 85 件 +
# RESULTS+= 直接追加 9 件 = 延べ 203 件、重複除去後の既知チェック名は 113 件。同名の
# run_check / skip_check は「同じチェック枠が環境条件で実行かスキップに分岐する」対（例:
# package.json の有無で Lint を run_check するか skip_check するか）であり、実際の 1 回の
# 実行で出力される表の行数はこれよりかなり少なくなるが、依存規則・self-test 系だけでも
# 数十行規模になる（`run_check_timeout` の grep 実測 109 件が上限の目安）。
#
# - THRESH_KNOWN_RATIO: データ行のうち既知名に一致する行の割合。0.9 とする根拠は、
#   本物の出力は 100% 一致するはずであり、10% 未満の逸脱（例: 将来 run_checks.sh 側の
#   チェック名を変更したのに PR 側が古い表のコピーを貼った・数行だけ手で書き換えた）は
#   拾いたいが、本ツール自身の抽出漏れ（正規表現が対応しない 5 個目の追加形式が将来
#   増える等）で全 PR が壊れることは避けたいための安全マージン。
# - THRESH_KNOWN_ABS: 既知名に一致する行の絶対数。10 とする根拠は、ダミー表（1 行・
#   既知名 0 件）を確実に落とす一方、`tools/run_checks.sh` の実際の出力は Lint / Format /
#   型チェック / テスト / E2E 系 / 依存規則 / 各 self-test だけで優に 10 行を超えるため、
#   本物の出力を絶対数で誤って弾くリスクが無い。
_THRESH_KNOWN_RATIO = 0.9
_THRESH_KNOWN_ABS = 10

# - THRESH_UNIQUE_RATIO: データ行のうち「重複していない（初出の）」行の割合。0.9 とする
#   根拠は、`run_checks.sh` の 1 回の実行では同じチェック名が複数回 RESULTS に積まれることは
#   無い（各チェックは 1 回しか走らない設計）ため、本物の表は常に 1.0 になる。#896 が要求する
#   「同一チェック名を大量にコピペした表」（例: 1 行を 40 回複製）は、既知名一致の割合・絶対数
#   だけでは通ってしまう（コピペ元が本物の行だから）ため、独立した軸として重複率を見る。
_THRESH_UNIQUE_RATIO = 0.9

# - TAIL_CHECK_COUNT（完走性の検証・親セッションの反例作成レンズ #463 追補）: 割合ベースの
#   既知名照合だけでは「`run_checks.sh` の先頭 N 件だけを並べた表」（= E2E / Lighthouse に
#   到達する前に中断した実行結果。実績: #852 の exit 137 OOM 中断・#851 の重さ）を検知できない。
#   列構造・既知名はどちらも正当なため、案 1・案 3 の判定だけでは原理的に落とせない。
#   `run_checks.sh` は上から順に実行されるため、**定義順で最後の既知チェック名が表に含まれて
#   いること** を「完走した」ことの直接的な証拠として使う。
#
#   末尾 3 件のうち 1 件以上が表に含まれることを必須条件とする。トレードオフ:
#   - 末尾 1 件だけに依存すると、そのチェックが将来別ファイルへ移動しただけ・条件分岐で
#     稀に対象外になっただけで、無関係な全 PR が誤ブロックされる（本ツール自身の変更に
#     弱すぎる）。
#   - 逆に N を広げすぎる（例: 末尾 20 件）と、末尾付近のどれか 1 つでも表に載っていれば
#     通ってしまい、直前の重い E2E / Lighthouse だけが失敗して中断したケースを見逃す
#     （検知したい実害に対して緩すぎる）。
#   3 件という値は、`run_checks.sh` の末尾が同種の self-test 群（#710 系の argv 検証テスト等）
#   で連続しているため、1 件が将来動いても残り 2 件が拾える一方、表全体の大部分（既知名割合
#   90% 以上を要求する既存の閾値）を占めるほどには広くない、という中間点として選んだ。
_TAIL_CHECK_COUNT = 3


# ──────────────────────────────────────────────
# 既知チェック名の抽出
# ──────────────────────────────────────────────


def extract_known_names_ordered(run_checks_text: str) -> list[str]:
    """`tools/run_checks.sh` から既知チェック名を **定義順（初出位置順）を保って** 抽出する。

    `run_checks.sh` はシェルスクリプトとして上から順に実行されるため、初出位置の順序は
    「そのチェックが実行順序のどのあたりに定義されているか」の代理指標として使える。
    同名の `run_check` / `skip_check` は「同じチェック枠が環境条件で実行かスキップに分岐する」
    if/else 対で、実装上ほぼ隣接して書かれるため、初出位置を採用すれば十分に「定義順」を
    近似できる（実測: 2026-09 時点の `tools/run_checks.sh` で最後の既知名は
    `WIP 自動保全の振る舞いテスト (test_wip_commit_deferral.sh)` であり、これは同ファイル末尾の
    self-test 群と一致する）。
    """
    matches: list[tuple[int, str]] = []
    for pattern in _KNOWN_NAME_PATTERNS:
        for m in pattern.finditer(run_checks_text):
            matches.append((m.start(), m.group(1)))
    matches.sort(key=lambda t: t[0])

    seen: set[str] = set()
    ordered: list[str] = []
    for _, name in matches:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def extract_known_names(run_checks_text: str) -> set[str]:
    """`tools/run_checks.sh` のソースから既知のチェック名集合を抽出する（案 1・本命）。"""
    return set(extract_known_names_ordered(run_checks_text))


# ──────────────────────────────────────────────
# セクション抽出（`check_evidence_freshness.py` の見出し判定を再利用）
# ──────────────────────────────────────────────


def extract_table_sections(pr_body: str) -> list[list[str]]:
    """PR 本文から対象見出し（`## run_checks 結果` 系）の各セクション本文（行のリスト）を返す。

    `check_evidence_freshness.find_evidence_shas()` と同じ見出し判定・フェンス除外・全角
    スペース正規化を用いるが、あちらは SHA 行だけを拾って戻り値に生の行を残さないため、
    表の行そのものを集める本関数は独立に持つ（見出し・フェンス判定の再定義はしない）。

    複数セクションが出現する場合は全セクションを個別のリストとして返す（後段で ANY
    セマンティクスの判定に使う）。
    """
    normalized = pr_body.replace("　", " ")
    lines = normalized.split("\n")
    in_fence = fence_flags(lines)

    sections: list[list[str]] = []
    trying = False
    current: list[str] = []

    for i, line in enumerate(lines):
        if in_fence[i]:
            continue
        if _HEADING_RE.match(line):
            if trying:
                sections.append(current)
            trying = True
            current = []
            continue
        if trying:
            if _HEADING_GENERIC_RE.match(line):
                sections.append(current)
                trying = False
                current = []
                continue
            current.append(line)

    if trying:
        sections.append(current)

    return sections


# ──────────────────────────────────────────────
# テーブル行のパース（案 3・列構造）
# ──────────────────────────────────────────────


def parse_table_row(line: str) -> list[str] | None:
    """`| a | b | c |` 形式の 1 行をセルのリストへ分解する。テーブル行でなければ None。"""
    s = line.strip()
    if not s.startswith("|"):
        return None
    parts = s.split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]


def is_separator_row(cells: list[str]) -> bool:
    return len(cells) > 0 and all(_SEPARATOR_CELL_RE.match(c) for c in cells)


def analyze_section_table(lines: list[str]) -> dict:
    """セクション内の行からテーブルを解析し、ヘッダ・区切り行を除いたデータ行を返す。

    戻り値のキー: has_table_rows / has_header_and_separator / data_rows
    """
    table_lines = [line for line in lines if line.strip().startswith("|")]
    rows = [r for r in (parse_table_row(line) for line in table_lines) if r is not None]

    if not rows:
        return {"has_table_rows": False, "has_header_and_separator": False, "data_rows": []}

    if len(rows) == 1:
        # ヘッダ行だけ（区切り・データ行が無い）。ダミー表の 1 行はここに落ちる。
        return {"has_table_rows": True, "has_header_and_separator": False, "data_rows": [rows[0]]}

    header, maybe_sep, *rest = rows
    if is_separator_row(maybe_sep):
        return {"has_table_rows": True, "has_header_and_separator": True, "data_rows": rest}

    # 2 行目が区切り行の形をしていない = ヘッダ + 区切りという正規の形になっていない。
    # 構造が壊れているとみなし、ヘッダ以外の全行をデータ行候補として渡す（後続の列検証で
    # 確実に不正判定させるため、ここで捨てずに data_rows へ積む）。
    return {"has_table_rows": True, "has_header_and_separator": False, "data_rows": [maybe_sep, *rest]}


def _match_known_name(name: str, known_names: set[str]) -> bool:
    # バッククォート囲みの表記ゆれ（`` `Lint (eslint)` `` 等）を許容する。
    stripped = name.strip("`").strip()
    return stripped in known_names


def validate_data_rows(data_rows: list[list[str]], known_names: set[str], tail_names: list[str]) -> dict:
    """データ行群を検証し、列構造・既知名一致・重複・完走性の各指標を返す（純粋関数）。

    `tail_names`: `extract_known_names_ordered()` の末尾 `_TAIL_CHECK_COUNT` 件（定義順で
    最後のほうの既知チェック名）。このうち 1 件以上が表のデータ行に含まれていれば、
    `run_checks.sh` が最後まで完走したとみなす（完走性の検証・`_TAIL_CHECK_COUNT` のコメント
    参照）。
    """
    total = len(data_rows)
    col_ok = 0
    status_ok = 0
    known_ok = 0
    seen_names: set[str] = set()
    unique_rows = 0
    matched_tail_names: set[str] = set()

    for cells in data_rows:
        if len(cells) == 3:
            col_ok += 1
            name_cell, status_cell, seconds_cell = cells
            if _STATUS_VOCAB_RE.match(status_cell.strip()) and _SECONDS_CELL_RE.match(seconds_cell.strip()):
                status_ok += 1
            normalized_name = name_cell.strip("`").strip()
            if _match_known_name(name_cell, known_names):
                known_ok += 1
            if normalized_name in tail_names:
                matched_tail_names.add(normalized_name)
            if normalized_name not in seen_names:
                seen_names.add(normalized_name)
                unique_rows += 1
        else:
            # 列数が壊れている行はユニーク判定に混ぜない（重複計算の分母をぼかさないため）
            unique_rows += 1

    known_ratio = (known_ok / total) if total else 0.0
    unique_ratio = (unique_rows / total) if total else 0.0
    tail_ok = len(matched_tail_names) >= 1 if tail_names else False

    return {
        "total": total,
        "col_ok": col_ok,
        "status_ok": status_ok,
        "known_ok": known_ok,
        "known_ratio": known_ratio,
        "unique_rows": unique_rows,
        "unique_ratio": unique_ratio,
        "tail_names": list(tail_names),
        "matched_tail_names": sorted(matched_tail_names),
        "tail_ok": tail_ok,
    }


def _evaluate_section(metrics: dict) -> str:
    """`validate_data_rows()` の指標から、そのセクションの判定を返す。

    戻り値: `"valid"` / `"invalid"`（列構造・既知名一致・重複のいずれかが不正）/
    `"incomplete_run"`（列構造・既知名一致・重複はすべて正当だが、末尾チェック名が
    表に含まれておらず run_checks が完走した形跡が無い）。

    列構造・既知名の破綻より「未完走」を後段の判定にする（構造的な偽装のほうが優先度が
    高い違反であり、両方に該当する場合は既存の `invalid` 理由で報告する）。
    """
    total = metrics["total"]
    if total == 0:
        return "invalid"

    structurally_ok = (
        metrics["col_ok"] == total
        and metrics["status_ok"] == total
        and metrics["known_ratio"] >= _THRESH_KNOWN_RATIO
        and metrics["known_ok"] >= _THRESH_KNOWN_ABS
        and metrics["unique_ratio"] >= _THRESH_UNIQUE_RATIO
    )
    if not structurally_ok:
        return "invalid"
    if not metrics["tail_ok"]:
        return "incomplete_run"
    return "valid"


# ──────────────────────────────────────────────
# 総合判定（純粋関数・`main()` を介さず単体テスト可能）
# ──────────────────────────────────────────────


def judge_evidence(pr_body: str, run_checks_text: str) -> dict:
    """PR 本文と `run_checks.sh` のソースから run_checks 結果表の妥当性を判定する。

    戻り値のキー: valid / reason / exit_code / sections（各セクションの解析結果。デバッグ用）
    """
    known_names_ordered = extract_known_names_ordered(run_checks_text)
    known_names = set(known_names_ordered)
    if not known_names:
        return {
            "valid": False,
            "reason": "no_known_names",
            "exit_code": 2,
            "known_names_count": 0,
            "sections": [],
        }
    tail_names = known_names_ordered[-_TAIL_CHECK_COUNT:]

    sections = extract_table_sections(pr_body)
    if not sections:
        return {
            "valid": False,
            "reason": "no_section",
            "exit_code": 1,
            "known_names_count": len(known_names),
            "sections": [],
        }

    section_reports: list[dict] = []
    best_valid: dict | None = None

    for lines in sections:
        analysis = analyze_section_table(lines)
        if not analysis["has_table_rows"]:
            report = {"reason": "no_table_rows", "metrics": None}
            section_reports.append(report)
            continue

        data_rows = analysis["data_rows"]
        if not data_rows:
            report = {"reason": "no_data_rows", "metrics": None}
            section_reports.append(report)
            continue

        metrics = validate_data_rows(data_rows, known_names, tail_names)
        section_reason = _evaluate_section(metrics)
        report = {
            "reason": section_reason,
            "metrics": metrics,
            "has_header_and_separator": analysis["has_header_and_separator"],
        }
        section_reports.append(report)
        if section_reason == "valid" and best_valid is None:
            best_valid = report

    if best_valid is not None:
        return {
            "valid": True,
            "reason": "valid",
            "exit_code": 0,
            "known_names_count": len(known_names),
            "sections": section_reports,
        }

    # いずれのセクションも妥当でない。最も情報量が多い（total が最大の）失敗理由を代表として返す。
    worst = max(
        section_reports,
        key=lambda r: (r["metrics"]["total"] if r["metrics"] else -1),
    )
    return {
        "valid": False,
        "reason": worst["reason"],
        "exit_code": 1,
        "known_names_count": len(known_names),
        "sections": section_reports,
    }


# ──────────────────────────────────────────────
# 出力
# ──────────────────────────────────────────────


def print_report(result: dict) -> None:
    reason = result["reason"]
    if reason == "no_known_names":
        print(
            "❌ 判定不能: run_checks.sh から既知のチェック名を 1 件も抽出できませんでした"
            "（--run-checks-path の指定を確認してください）。",
            file=sys.stderr,
        )
    elif reason == "no_section":
        print(
            "❌ PR 本文に `## run_checks 結果` / `## npm run check 結果` セクションが見つかりません。",
            file=sys.stderr,
        )
    elif reason in ("no_table_rows", "no_data_rows"):
        print(
            "❌ run_checks 結果セクションはありますが、有効なデータ行（チェック名・結果・所要秒数の"
            "3 列）が見つかりません。",
            file=sys.stderr,
        )
    elif reason == "invalid":
        worst = max(
            (s for s in result["sections"] if s["metrics"]),
            key=lambda r: r["metrics"]["total"],
            default=None,
        )
        detail = f"（{worst['metrics']}）" if worst else ""
        print(
            "❌ run_checks 結果表が本物の出力形式と一致しません（列構造の破綻・既知チェック名との"
            f"不一致・異常な重複行のいずれか）。 {detail}\n"
            "`bash tools/run_checks.sh` の出力末尾の Markdown サマリー表をそのまま貼り直してください。",
            file=sys.stderr,
        )
    elif reason == "incomplete_run":
        worst = max(
            (s for s in result["sections"] if s["metrics"]),
            key=lambda r: r["metrics"]["total"],
            default=None,
        )
        detail = f"（末尾チェック名候補: {worst['metrics']['tail_names']}）" if worst else ""
        print(
            "❌ run_checks が最後まで完走した形跡がありません（列構造・既知チェック名は妥当ですが、"
            f"定義順で最後のほうのチェック名が表に見当たりません）。{detail}\n"
            "E2E / Lighthouse などの重いチェックの途中で中断していないか確認し、"
            "`bash tools/run_checks.sh` を最後まで完走させてから結果表を貼り直してください。",
            file=sys.stderr,
        )
    else:
        print(f"✅ run_checks 結果表は妥当です（既知チェック名 {result['known_names_count']} 件と照合）。")


# ──────────────────────────────────────────────
# CLI 実行本体
# ──────────────────────────────────────────────


def _read_text_or_none(path_str: str | None) -> tuple[str | None, str | None]:
    """ファイル or 標準入力からテキストを読む。戻り値: (text, error) のどちらか一方が None。"""
    try:
        if path_str is None or path_str == "-":
            return sys.stdin.read(), None
        return Path(path_str).read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as e:
        return None, str(e)


def _judge_and_report(args: argparse.Namespace) -> int:
    run_checks_text, err = _read_text_or_none(args.run_checks_path)
    if err is not None:
        print(f"❌ 判定不能: --run-checks-path を読めません: {err}", file=sys.stderr)
        if args.json:
            print(json.dumps({"valid": False, "reason": "run_checks_unreadable", "error": err}, ensure_ascii=False))
        return 2

    pr_body, err = _read_text_or_none(args.body_file)
    if err is not None:
        print(f"❌ 判定不能: --body-file を読めません: {err}", file=sys.stderr)
        if args.json:
            print(json.dumps({"valid": False, "reason": "body_unreadable", "error": err}, ensure_ascii=False))
        return 2

    result = judge_evidence(pr_body, run_checks_text)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return result["exit_code"]


def judge_and_report_safely(args: argparse.Namespace) -> int:
    """`_judge_and_report()` の想定外の例外を `internal_error`（exit 2）へ倒す（fail-closed の
    最終防波堤。`check_evidence_freshness.judge_and_report_safely()` と同じ設計）。"""
    try:
        return _judge_and_report(args)
    except Exception as e:  # noqa: BLE001 - 判定不能への最終防波堤
        print(f"❌ 判定不能: 予期しない内部エラー（{type(e).__name__}: {e}）", file=sys.stderr)
        if args.json:
            print(json.dumps({"valid": False, "reason": "internal_error", "error": str(e)}, ensure_ascii=False))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--body-file", help="PR 本文ファイルのパス（省略時・'-' 指定時は標準入力から読む）")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument(
        "--run-checks-path",
        default=str(Path(__file__).resolve().parent / "run_checks.sh"),
        help="既知チェック名の抽出元スクリプト（既定: tools/run_checks.sh）",
    )
    parser.add_argument("--self-test", action="store_true", help="ネットワーク非依存のセルフテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    return judge_and_report_safely(args)


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────

# 自己完結のフィクスチャ用サンプル run_checks.sh 断片（実ファイルに依存しない・将来 run_checks.sh
# が変わっても self-test の合否がぶれないようにするため独立に持つ）。
_SAMPLE_RUN_CHECKS_SH = """
run_check "Lint (eslint)" npx eslint
run_check "Format (prettier --check)" npx prettier --check .
run_check "型チェック (tsc --noEmit)" npx tsc --noEmit
run_check "テスト (vitest run)" npx vitest run
run_check "依存規則 (check_architecture_boundaries.py)" python3 tools/check_architecture_boundaries.py
run_check "依存規則 self-test (check_architecture_boundaries.py --self-test)" python3 tools/check_architecture_boundaries.py --self-test
run_check "run_checks 証跡鮮度検査 self-test (check_evidence_freshness.py --self-test)" python3 tools/check_evidence_freshness.py --self-test
run_check_timeout "E2E (playwright test)" "$E2E_TIMEOUT_SEC" npx playwright test
run_check_timeout "Workers E2E (test:e2e:workers)" "$WORKERS_E2E_TIMEOUT_SEC" npm run test:e2e:workers
run_check_timeout "Lighthouse (Accessibility gate)" "$LIGHTHOUSE_TIMEOUT_SEC" node tools/run_lighthouse.mjs
skip_check "Lint (eslint)" "package.json が無い"
skip_check "E2E (playwright test)" "SKIP_E2E=1 が指定されました"
RESULTS+=("依存関係のインストール状態|FAIL|0")
RESULTS+=("OpenNext アセット鮮度チェック (ensure_open_next_assets.mjs)|FAIL|0")
RESULTS+=("Workers E2E (test:e2e:workers)|FAIL|0")
run_check "UI 寸法検査 (check_ui_dimensions.py)" python3 tools/check_ui_dimensions.py
run_check "UI 寸法検査 self-test (check_ui_dimensions.py --self-test)" python3 tools/check_ui_dimensions.py --self-test
run_check "WIP 自動保全の振る舞いテスト (test_wip_commit_deferral.sh)" bash tools/test_wip_commit_deferral.sh
"""


def _sample_known_names() -> list[str]:
    """`_SAMPLE_RUN_CHECKS_SH` から抽出される既知名を、抽出順に近い順で列挙する（本物の表
    フィクスチャを組み立てるための便宜関数。集合の要素順は不定なので明示的に持つ）。"""
    return [
        "Lint (eslint)",
        "Format (prettier --check)",
        "型チェック (tsc --noEmit)",
        "テスト (vitest run)",
        "依存規則 (check_architecture_boundaries.py)",
        "依存規則 self-test (check_architecture_boundaries.py --self-test)",
        "run_checks 証跡鮮度検査 self-test (check_evidence_freshness.py --self-test)",
        "E2E (playwright test)",
        "Workers E2E (test:e2e:workers)",
        "Lighthouse (Accessibility gate)",
        "依存関係のインストール状態",
        "OpenNext アセット鮮度チェック (ensure_open_next_assets.mjs)",
        "UI 寸法検査 (check_ui_dimensions.py)",
        "UI 寸法検査 self-test (check_ui_dimensions.py --self-test)",
        "WIP 自動保全の振る舞いテスト (test_wip_commit_deferral.sh)",
    ]


def _build_good_table_body(names: list[str], heading: str = "## run_checks 結果") -> str:
    lines = [heading, "| チェック | 結果 | 所要秒数 |", "|---|---|---|"]
    for i, name in enumerate(names):
        status = "PASS" if i % 4 != 0 else "SKIP"
        lines.append(f"| {name} | {status} | {i}秒 |")
    return "\n".join(lines) + "\n"


def run_self_test() -> int:
    import subprocess
    import tempfile

    passed, failed = 0, 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {label}" + (f" — {detail}" if detail else ""))

    known_names = extract_known_names(_SAMPLE_RUN_CHECKS_SH)
    sample_names = _sample_known_names()

    # ── 前提: サンプル run_checks.sh から既知名がちょうど抽出できていること ──
    check(
        "前提: サンプル run_checks.sh から既知名が抽出できる",
        known_names == set(sample_names),
        f"known_names={known_names!r} expected={set(sample_names)!r}",
    )

    good_body = _build_good_table_body(sample_names)

    # ── 正常系: 本物の出力形式に一致する表は valid・exit 0 ──
    r_good = judge_evidence(good_body, _SAMPLE_RUN_CHECKS_SH)
    check("正常系: 本物の表は valid・exit 0", r_good["valid"] is True and r_good["exit_code"] == 0, str(r_good))

    # ── Issue #463 本文のダミー表そのもの ──
    issue_dummy_body = (
        "## run_checks 結果\n"
        "（実行していません、これはダミーです）\n"
        "| これは本物のテスト結果に見えるダミー |\n"
    )
    r_issue_dummy = judge_evidence(issue_dummy_body, _SAMPLE_RUN_CHECKS_SH)
    check(
        "Issue #463 本文のダミー表は invalid・exit 1",
        r_issue_dummy["valid"] is False and r_issue_dummy["exit_code"] == 1,
        str(r_issue_dummy),
    )

    # ── 境界の外側1（#750）: 見出しは正しいがデータ行が全て既知名と無関係な手打ち偽装 ──
    body_fake_names = (
        "## run_checks 結果\n"
        "| チェック | 結果 | 所要秒数 |\n"
        "|---|---|---|\n"
        "| でっちあげチェックA | PASS | 1秒 |\n"
        "| でっちあげチェックB | PASS | 2秒 |\n"
        "| でっちあげチェックC | PASS | 1秒 |\n"
        "| でっちあげチェックD | PASS | 1秒 |\n"
        "| でっちあげチェックE | PASS | 1秒 |\n"
        "| でっちあげチェックF | PASS | 1秒 |\n"
        "| でっちあげチェックG | PASS | 1秒 |\n"
        "| でっちあげチェックH | PASS | 1秒 |\n"
        "| でっちあげチェックI | PASS | 1秒 |\n"
        "| でっちあげチェックJ | PASS | 1秒 |\n"
    )
    r_fake_names = judge_evidence(body_fake_names, _SAMPLE_RUN_CHECKS_SH)
    check(
        "境界の外側: 3 列だが既知名と無関係な手打ち偽装は invalid（既知名一致率ゼロ）",
        r_fake_names["valid"] is False,
        str(r_fake_names),
    )

    # ── 境界の外側2（#750）: 3 列だがステータス語彙が不正 ──
    body_bad_status = _build_good_table_body(sample_names).replace("PASS", "OK").replace("SKIP", "済")
    r_bad_status = judge_evidence(body_bad_status, _SAMPLE_RUN_CHECKS_SH)
    check(
        "境界の外側: ステータス語彙が不正（OK/済）な表は invalid",
        r_bad_status["valid"] is False,
        str(r_bad_status),
    )

    # ── 境界の外側3（#750）: コードフェンス内にだけ本物そっくりの表がある ──
    body_fenced = (
        "## run_checks 結果\n"
        "例:\n"
        "```\n" + _build_good_table_body(sample_names, heading="") + "```\n"
    )
    r_fenced = judge_evidence(body_fenced, _SAMPLE_RUN_CHECKS_SH)
    check(
        "境界の外側: コードフェンス内の本物そっくりの表は無視され invalid（セクション内は空）",
        r_fenced["valid"] is False,
        str(r_fenced),
    )

    # ── 要素間の関係が不正な負ケース（#896）: 同一チェック名を大量にコピペした表 ──
    body_duplicated = _build_good_table_body([sample_names[0]] * 40)
    r_duplicated = judge_evidence(body_duplicated, _SAMPLE_RUN_CHECKS_SH)
    check(
        "#896: 同一既知チェック名を 40 行コピペした表は invalid（重複率が閾値未満）",
        r_duplicated["valid"] is False,
        str(r_duplicated),
    )
    if r_duplicated["sections"]:
        dup_metrics = r_duplicated["sections"][0]["metrics"]
        check(
            "#896: 重複表は既知名一致率だけなら 100% になる（割合ベース単独では見逃す設計であることの確認）",
            dup_metrics is not None and dup_metrics["known_ratio"] == 1.0 and dup_metrics["unique_ratio"] < _THRESH_UNIQUE_RATIO,
            str(dup_metrics),
        )

    # ── 追加1（親セッション反例作成レンズ・実害あり）: 途中で打ち切られた run_checks 出力 ──
    # サンプル run_checks.sh の既知名は sample_names と同じ初出順（前提テストで確認済み）。
    # 末尾 _TAIL_CHECK_COUNT 件を含まない「先頭部分だけ」の表は、列構造・既知名照合が
    # どちらも正当であっても incomplete_run・exit 1 で落ちなければならない。
    truncated_names = sample_names[: -_TAIL_CHECK_COUNT]
    body_truncated = _build_good_table_body(truncated_names)
    r_truncated = judge_evidence(body_truncated, _SAMPLE_RUN_CHECKS_SH)
    check(
        "追加1: 末尾チェック名を含まない打ち切り表は incomplete_run・exit 1",
        r_truncated["valid"] is False
        and r_truncated["reason"] == "incomplete_run"
        and r_truncated["exit_code"] == 1,
        str(r_truncated),
    )
    if r_truncated["sections"]:
        trunc_metrics = r_truncated["sections"][0]["metrics"]
        check(
            "追加1: 打ち切り表は列構造・既知名照合は正当（他の理由で偶然落ちたのではない）",
            trunc_metrics is not None
            and trunc_metrics["col_ok"] == trunc_metrics["total"]
            and trunc_metrics["status_ok"] == trunc_metrics["total"]
            and trunc_metrics["known_ratio"] == 1.0
            and trunc_metrics["tail_ok"] is False,
            str(trunc_metrics),
        )

    # ── 追加1: 末尾チェック名を含む完全な表は exit 0（正ケース。既存の good_body が兼ねる） ──
    check(
        "追加1: 末尾チェック名を含む完全な表は tail_ok・valid・exit 0（既存正ケースが兼ねる）",
        r_good["valid"] is True
        and r_good["sections"][0]["metrics"]["tail_ok"] is True,
        str(r_good),
    )

    # ── 干渉検証: 完走チェック（追加1）を満たすが既知名割合が低い表は、引き続き既知名不一致で
    #    落ちること（追加1と既存の割合ベース判定が同じデータ行走査を通るため、片方が他方の
    #    前提を壊していないかを確認する）。
    body_tail_ok_but_fake = _build_good_table_body(
        ["でっちあげA", "でっちあげB", "でっちあげC", "でっちあげD", "でっちあげE",
         "でっちあげF", "でっちあげG", "でっちあげH", "でっちあげI", sample_names[-1]]
    )
    r_tail_ok_but_fake = judge_evidence(body_tail_ok_but_fake, _SAMPLE_RUN_CHECKS_SH)
    check(
        "干渉検証: 末尾チェック名は含むが既知名割合が低い表は、既知名不一致で invalid のまま"
        "（reason は incomplete_run に化けない）",
        r_tail_ok_but_fake["valid"] is False and r_tail_ok_but_fake["reason"] == "invalid",
        str(r_tail_ok_but_fake),
    )
    if r_tail_ok_but_fake["sections"]:
        interference_metrics = r_tail_ok_but_fake["sections"][0]["metrics"]
        check(
            "干渉検証: 末尾チェック名自体は tail_ok=True になっている（完走判定は独立して機能）",
            interference_metrics is not None and interference_metrics["tail_ok"] is True,
            str(interference_metrics),
        )

    # ── fail-closed: セクション不在 ──
    r_no_section = judge_evidence("普通の PR 本文です。特に証跡なし。", _SAMPLE_RUN_CHECKS_SH)
    check(
        "fail-closed: セクション不在は no_section・exit 1",
        r_no_section["reason"] == "no_section" and r_no_section["exit_code"] == 1,
        str(r_no_section),
    )

    # ── fail-closed: セクションはあるがテーブル行が無い ──
    r_no_table = judge_evidence("## run_checks 結果\n実行しました。\n", _SAMPLE_RUN_CHECKS_SH)
    check(
        "fail-closed: テーブル行そのものが無いのは no_table_rows・exit 1",
        r_no_table["reason"] == "no_table_rows" and r_no_table["exit_code"] == 1,
        str(r_no_table),
    )

    # ── fail-closed: 既知名が 1 件も抽出できない run_checks.sh（判定不能・exit 2） ──
    r_no_known = judge_evidence(good_body, "echo 'このスクリプトには run_check 系の呼び出しが無い'\n")
    check(
        "fail-closed: 既知名 0 件の run_checks.sh は no_known_names・exit 2（判定不能）",
        r_no_known["reason"] == "no_known_names" and r_no_known["exit_code"] == 2,
        str(r_no_known),
    )

    # ── ANY セマンティクス: 複数セクションのうち後段の 1 つだけが妥当 ──
    body_multi_section = (
        "## run_checks 結果\n"
        "（古い・ダミー）\n"
        "| ダミー |\n"
        "## 変更点\n"
        "何か\n"
        + _build_good_table_body(sample_names)
    )
    r_multi = judge_evidence(body_multi_section, _SAMPLE_RUN_CHECKS_SH)
    check(
        "ANY セマンティクス: 複数セクションのうち後段の 1 つが妥当なら valid",
        r_multi["valid"] is True and r_multi["exit_code"] == 0,
        str(r_multi),
    )

    # ── バリアント: 見出しのバッククォート有無・npm run check 見出し ──
    r_bt_heading = judge_evidence(
        _build_good_table_body(sample_names, heading="## `run_checks` 結果"), _SAMPLE_RUN_CHECKS_SH
    )
    check("バリアント: 見出しバッククォート付きでも検出", r_bt_heading["valid"] is True, str(r_bt_heading))

    r_npm_heading = judge_evidence(
        _build_good_table_body(sample_names, heading="## npm run check 結果"), _SAMPLE_RUN_CHECKS_SH
    )
    check("バリアント: npm run check 見出しでも検出", r_npm_heading["valid"] is True, str(r_npm_heading))

    # ── バリアント: 表のチェック名がバッククォートで囲まれていても既知名照合できる ──
    body_bt_names = _build_good_table_body([f"`{n}`" for n in sample_names])
    r_bt_names = judge_evidence(body_bt_names, _SAMPLE_RUN_CHECKS_SH)
    check("バリアント: チェック名がバッククォート囲みでも既知名照合できる", r_bt_names["valid"] is True, str(r_bt_names))

    # ── find_evidence 系純粋関数の単体確認 ──
    sections = extract_table_sections(good_body)
    check("extract_table_sections: 1 セクション抽出", len(sections) == 1, str(len(sections)))

    analysis = analyze_section_table(sections[0]) if sections else {}
    check(
        "analyze_section_table: ヘッダ+区切りを検出しデータ行を正しく分離",
        analysis.get("has_header_and_separator") is True and len(analysis.get("data_rows", [])) == len(sample_names),
        str(analysis),
    )

    metrics = (
        validate_data_rows(analysis["data_rows"], known_names, sample_names[-_TAIL_CHECK_COUNT:])
        if sections
        else {}
    )
    check(
        "validate_data_rows: 本物の表は col_ok == status_ok == known_ok == total",
        metrics.get("total") == len(sample_names)
        and metrics.get("col_ok") == len(sample_names)
        and metrics.get("status_ok") == len(sample_names)
        and metrics.get("known_ok") == len(sample_names),
        str(metrics),
    )

    # ── main() の CLI end-to-end 実行（終了コード配線の退行検知） ──
    script_path = str(Path(__file__).resolve())

    def run_cli(extra_args: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, script_path, *extra_args],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=30,
        )

    with tempfile.TemporaryDirectory() as tmp:
        run_checks_path = Path(tmp) / "sample_run_checks.sh"
        run_checks_path.write_text(_SAMPLE_RUN_CHECKS_SH, encoding="utf-8")

        good_path = Path(tmp) / "good_body.md"
        good_path.write_text(good_body, encoding="utf-8")

        cli_good = run_cli(
            ["--body-file", str(good_path), "--run-checks-path", str(run_checks_path)]
        )
        check(
            "CLI: 本物の表は exit 0",
            cli_good.returncode == 0,
            f"stdout={cli_good.stdout!r} stderr={cli_good.stderr!r}",
        )

        dummy_path = Path(tmp) / "dummy_body.md"
        dummy_path.write_text(issue_dummy_body, encoding="utf-8")
        cli_dummy = run_cli(
            ["--body-file", str(dummy_path), "--run-checks-path", str(run_checks_path)]
        )
        check(
            "CLI: Issue #463 本文のダミー表は exit 1",
            cli_dummy.returncode == 1,
            f"stdout={cli_dummy.stdout!r} stderr={cli_dummy.stderr!r}",
        )

        cli_missing_run_checks = run_cli(
            ["--body-file", str(good_path), "--run-checks-path", str(Path(tmp) / "nope.sh")]
        )
        check(
            "CLI: 存在しない --run-checks-path は exit 2（run_checks_unreadable）",
            cli_missing_run_checks.returncode == 2,
            f"stdout={cli_missing_run_checks.stdout!r} stderr={cli_missing_run_checks.stderr!r}",
        )

        cli_missing_body = run_cli(
            ["--body-file", str(Path(tmp) / "nope.md"), "--run-checks-path", str(run_checks_path)]
        )
        check(
            "CLI: 存在しない --body-file は exit 2（body_unreadable）",
            cli_missing_body.returncode == 2,
            f"stdout={cli_missing_body.stdout!r} stderr={cli_missing_body.stderr!r}",
        )

        truncated_path = Path(tmp) / "truncated_body.md"
        truncated_path.write_text(body_truncated, encoding="utf-8")
        cli_truncated = run_cli(
            ["--body-file", str(truncated_path), "--run-checks-path", str(run_checks_path), "--json"]
        )
        try:
            truncated_payload = json.loads(cli_truncated.stdout)
            truncated_reason_ok = truncated_payload.get("reason") == "incomplete_run"
        except json.JSONDecodeError:
            truncated_reason_ok = False
        check(
            "CLI: 追加1・打ち切り表は exit 1・reason=incomplete_run",
            cli_truncated.returncode == 1 and truncated_reason_ok,
            f"stdout={cli_truncated.stdout!r} stderr={cli_truncated.stderr!r}",
        )

        cli_stdin = run_cli(["--run-checks-path", str(run_checks_path)], stdin_text=good_body)
        check(
            "CLI: stdin からの本文入力でも exit 0",
            cli_stdin.returncode == 0,
            f"stdout={cli_stdin.stdout!r} stderr={cli_stdin.stderr!r}",
        )

        cli_json = run_cli(
            ["--body-file", str(good_path), "--run-checks-path", str(run_checks_path), "--json"]
        )
        try:
            payload = json.loads(cli_json.stdout)
            json_ok = payload.get("valid") is True
        except json.JSONDecodeError:
            json_ok = False
        check("CLI: --json が構造化出力を返す", cli_json.returncode == 0 and json_ok, f"stdout={cli_json.stdout!r}")

    # ── 想定外の内部エラーは judge_and_report_safely で internal_error・exit 2 へ倒れる ──
    with tempfile.TemporaryDirectory() as tmp2:
        run_checks_path2 = Path(tmp2) / "sample_run_checks.sh"
        run_checks_path2.write_text(_SAMPLE_RUN_CHECKS_SH, encoding="utf-8")
        body_path2 = Path(tmp2) / "body.md"
        body_path2.write_text(good_body, encoding="utf-8")

        class _FakeArgsInternalError:
            body_file = str(body_path2)
            run_checks_path = str(run_checks_path2)
            json = False

        _module = sys.modules[__name__]
        _orig_judge_evidence = _module.judge_evidence

        def _boom(_pr_body: str, _run_checks_text: str) -> dict:
            raise RuntimeError("induced failure for self-test (internal_error path)")

        _module.judge_evidence = _boom
        try:
            rc_internal = judge_and_report_safely(_FakeArgsInternalError())
        finally:
            _module.judge_evidence = _orig_judge_evidence

        check(
            "想定外の例外は judge_and_report_safely で internal_error・exit 2 へ倒れる",
            rc_internal == 2,
            f"rc={rc_internal!r}",
        )
        check(
            "judge_evidence の差し替えは確実に元へ戻る",
            _module.judge_evidence is _orig_judge_evidence,
            "",
        )

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
