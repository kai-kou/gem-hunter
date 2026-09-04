#!/usr/bin/env python3
"""check_evidence_freshness.py — PR 本文の run_checks 証跡が head SHA と同じ鮮度かを検査する（#751 / #906）

## なぜ必要か（Issue #751）

PR 本文の `## run_checks 結果` 表は「PR 作成時点の実行結果」の証跡だが、その後の追加コミット
（Layer 1 セルフレビューの指摘対応・Stop / PostCompact フックの WIP 自動コミット）で実態と
乖離しうる。実測では「PR 本文の証跡は緑と読めるのに実態は赤」の状態でマージ判断に入った。
本ツールは、証跡が記録されたコミット（`実行時点コミット:` 行の SHA）と現在の head SHA が
一致するかを機械的に判定し、乖離をマージ前に検知できるようにする。

証跡 SHA 行の記法（`## run_checks 結果` / `## npm run check 結果` セクション内に置く。
`pr-review-flow-summary.md`「PR 作成時の必須事項」項目 0 が運用手順の正本）:

    実行時点コミット: `abc1234`

## 見出し検出の仕様（`.claude/hooks/pre-pr-create-check.sh` 4.5 節と揃える・当該ファイルは非改修）

- 見出しは `##` 固定。`run_checks` / `npm run check` のどちらでもよく、各キーワードは
  バッククォートで囲んでも囲まなくてもよい（`^##[ \t]*` `?(run_checks|npm run check)` `?[ \t]*結果`）。
  ⚠️ `_HEADING_RE` は `.claude/hooks/pre-pr-create-check.sh` 4.5 節の awk 正規表現と同義の
  独立実装（相互参照コメントを双方に付与済み・#906 WARNING 5）。恒久的な一本化（`--check-section-only`
  モードの追加と awk の廃止）は本ツールのスコープ外（やらない）。
- フェンスドコードブロック（``` / ~~~）内の見出し・SHA 行は判定対象から除外する。判定は
  `md_fence.fence_flags`（CommonMark 準拠・``` と ~~~ をマーカー種別ごとに区別してトグルする
  共有ヘルパー）に委譲する。旧実装は独自の `_FENCE_RE` トグルで両マーカーを同一カウンタに
  数えていたため、``` フェンスの中に ~~~ を 1 行挟むと状態が反転し、以降が丸ごと「フェンス外」
  扱いになる fail-open があった（実測: ` ```text ` の中に `~~~` を挟み、その内側に head と
  一致する `実行時点コミット:` 行を置くと match/exit 0 が返っていた・#906 CRITICAL 1）。
- 見出しが複数回出現する場合、**いずれか 1 セクションに head と前方一致する SHA 行があれば**
  「新鮮」とみなす（ANY セマンティクス。詳細は下記「SHA 行の仕様」）。
- 全角スペース（U+3000）は半角スペースに正規化してから判定する（`pre-pr-create-check.sh` と同じ理由）。

## SHA 行の仕様

- 行頭一致（`^[ \t]*実行時点コミット:`）。インデントは許容するが、引用（`>`）やリスト記号（`-`）の
  後ろに続く形は拾わない（`pr_meta_patterns.py` の `meta_line_re()` と同じアンカー設計 = 行頭 +
  空白インデントのみ許容 + ラベル直後 `:`）。⚠️ `meta_line_re()` をそのまま流用しなかった理由
  （#906 WARNING 5）: 同関数は「ラベル直後に非空白 1 文字があるか」だけを見る汎用の *存在検知*
  （`\S`）で、本ツールが必要とする「7〜40 桁 hex のキャプチャ + バッククォート有無の両対応 +
  長い hex 列の部分一致を防ぐ negative lookahead」という抽出要件を持たない。`pr_meta_patterns.py`
  はメタ行判定の定数・ファクトリのみを持つ薄いモジュールとして意図的にスコープを絞ってあり
  （同ファイル docstring）、抽出用途への拡張はそちらの責務を広げてしまうため、本ツールでは
  アンカー設計（行頭 + 空白インデントのみ許容）だけを揃えた独立の正規表現として持つ。
- SHA はバッククォート囲みの有無を問わず受け付け、7〜40 桁の hex（大文字混じりも許容）。
- `実行時点コミット参考:` のような **前方一致では通ってしまう別ラベル** は拾わない（ラベル直後に
  `:` が来ることを要求するため、`参考` が挟まると正規表現がそもそもマッチしない）。
- 比較は前方一致（短い方の長さで比較・大文字小文字を無視）: 7 桁の短縮 SHA と 40 桁の完全 SHA が
  一致とみなせるようにするため。
- 🔴 **ANY セマンティクス（#906 WARNING 3）**: 本文中の全セクションから証跡 SHA 候補を全件収集し、
  **いずれか 1 件でも** head と前方一致すれば新鮮とみなす。旧実装は「本文で最初に見つかった SHA」
  だけを採用しており、証跡を追記で貼り直した PR（先頭セクションは古いまま・末尾セクションに新しい
  証跡）が誤ってブロックされていた。一致が無い場合、JSON の `evidence_sha` には**最後の候補**
  （最も後方＝追記で貼り直された可能性が高い候補）を採用する。フィールド名は後方互換のため
  単数の `evidence_sha` のまま維持する（複数候補の全件が必要な呼び出し側は `find_evidence_shas()`
  を直接使うこと）。

## 失敗経路の列挙（本ツールが塞いでいるすり抜け・#474 の必須項目 1）

1. 見出しはあるが SHA 行が無い → `no_sha_line`（fail-closed・exit 1）
2. `## run_checks 結果` セクション自体が本文に無い → `no_section`（fail-closed・exit 1。
   セクション欠落自体のブロックは `pre-pr-create-check.sh` 4.5 節の責務なので、本ツールは
   判定材料が無い状態として exit 1 に倒すだけで、そちらの文言を代替しない）
3. SHA 行がコードフェンス内にある（``` と ~~~ の入れ子含む） → `md_fence.fence_flags` による
   除外ロジックで無視され `no_sha_line` 扱いになる
4. SHA 行が `## run_checks 結果` 以外のセクション（例 `## 変更点`）にある → セクション境界判定の
   外側なので無視され `no_sha_line` 扱いになる
5. `実行時点コミット参考:` のような前方一致で通ってしまう別ラベル → ラベル直後 `:` 必須の正規表現で
   非マッチになり `no_sha_line` 扱いになる
6. `--head-sha` が hex でない、または 7 桁未満（コマンド呼び出し側の取得ミス） → `invalid_head_sha`
   （判定不能・exit 2）
7. `--body-file` が読めない（存在しない・権限無し・不正な UTF-8） → `body_unreadable`（判定不能・exit 2）
8. 証跡 SHA と head SHA のどの候補も前方一致しない（乖離あり） → `stale`（exit 1）
9. 証跡 SHA のいずれかの候補が head SHA と前方一致する（新鮮） → `match`（exit 0）
10. 上記以外の想定外の内部エラー（判定ロジック自体が例外を送出した） → `internal_error`（判定不能・exit 2。
    `main()` から `sys.exit()` までの経路を fail-closed に倒しすぎない側＝ブロックしすぎないための
    最終防波堤・#906 WARNING 4）

## 使い方

    python3 tools/check_evidence_freshness.py --body-file pr_body.md --head-sha "$(git rev-parse HEAD)"
    gh pr view N --json body -q .body | python3 tools/check_evidence_freshness.py --head-sha abc1234
    python3 tools/check_evidence_freshness.py --json --body-file pr_body.md --head-sha abc1234
    python3 tools/check_evidence_freshness.py --self-test

## 終了コード

| コード | 意味 | 判定の性質 |
|---|---|---|
| `0` | 新鮮（証跡 SHA のいずれかの候補が head SHA と前方一致） | 検査が走り、乖離が無かった |
| `1` | 乖離、または SHA 行そのものが無い（セクション不在含む） | 検査が走り、証跡が信頼できないと判定した（fail-closed） |
| `2` | 判定不能（`--head-sha` が hex 7〜40 桁でない・`--body-file` が読めない（不正 UTF-8 含む）・想定外の内部エラー） | 検査自体が成立しなかった |

`2`（判定不能）を `0` に丸めない。`no_section` / `no_sha_line` を `0` に丸めない（fail-closed・
`docs/rules/check-tool-design-rules.md` §1 / §2 に従う）。

## 配線（Issue #906 CRITICAL 2 で修正）

本ツールは `tools/run_checks.sh` から `--self-test` 付きで実際に呼ばれている（3.47.2 節相当）。
過去は誤って `selftest-wiring-ok` マーカーで自己除外していたが、配線されている以上マーカーは誤りで、
`check_selftest_wiring.py` が「意図的な除外」と誤認して配線消失を検知できなくなる状態だった。
`.claude/hooks/pre-pr-create-check.sh` 4.7 節からは `--self-test` なしの通常実行（PR 作成時の
証跡鮮度判定そのもの）で直接呼ばれる。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from md_fence import fence_flags

# ──────────────────────────────────────────────
# 正規表現（見出し・SHA 行）
# ──────────────────────────────────────────────

# ⚠️ `.claude/hooks/pre-pr-create-check.sh` 4.5 節の awk 正規表現と同義の独立実装（相互参照コメントを
# 双方に付与済み・#906 WARNING 5）。一本化は本ツールのスコープ外。
_HEADING_RE = re.compile(r"^##[ \t]*`?(run_checks|npm run check)`?[ \t]*結果")
_HEADING_GENERIC_RE = re.compile(r"^##[ \t]")
# ラベル直後に ':' を要求する（「実行時点コミット参考:」等の前方一致別ラベルを拾わないため）。
# SHA はバッククォート有無を問わず受け付け、直後が hex 文字でないことを要求する（長い hex 列の
# 部分一致を防ぐ）。アンカー設計（行頭 + 空白インデントのみ許容 + ラベル直後 `:`）は
# `pr_meta_patterns.meta_line_re()` と揃えているが、抽出用途（キャプチャ + バッククォート両対応）
# のため同関数はそのまま使わない（理由は上記 docstring「SHA 行の仕様」）。
_SHA_LINE_RE = re.compile(
    r"^[ \t]*実行時点コミット:[ \t]*`?([0-9a-fA-F]{7,40})`?(?![0-9a-fA-F])"
)
# 7〜40 桁（証跡側の下限と揃える・#906 NIT 6）。旧実装は 4 桁から通しており、比較桁数が
# 縮むほど prefix 衝突による fail-open（別コミットの短縮 SHA を誤って「一致」と判定するリスク）
# が高まっていた。
_HEAD_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


# ──────────────────────────────────────────────
# 判定ロジック（純粋関数）
# ──────────────────────────────────────────────


def find_evidence_shas(pr_body: str) -> dict:
    """PR 本文の対象セクション群から証跡 SHA 候補を **全件** 収集する（ANY セマンティクス・#906 WARNING 3）。

    フェンス判定は `md_fence.fence_flags`（CommonMark 準拠・マーカー種別を区別する 1 パス前計算）に
    委譲する。旧実装は独自の `_FENCE_RE` トグルで ``` と ~~~ を同一カウンタに数えており、入れ子
    フェンスで状態が反転する fail-open があった（#906 CRITICAL 1・詳細はモジュール docstring）。

    戻り値: {"has_section": bool, "evidence_shas": list[str]}
    - has_section: 対象見出しが（フェンス外に）1 つでもあれば True
    - evidence_shas: 全セクションの SHA 行から見つかった候補を出現順に並べたリスト（0 件もありうる）
    """
    normalized = pr_body.replace("　", " ")
    lines = normalized.split("\n")
    in_fence = fence_flags(lines)

    trying = False
    has_section = False
    evidence_shas: list[str] = []

    for i, line in enumerate(lines):
        if in_fence[i]:
            continue
        if _HEADING_RE.match(line):
            trying = True
            has_section = True
            continue
        if trying:
            m = _SHA_LINE_RE.match(line)
            if m:
                evidence_shas.append(m.group(1))
            if _HEADING_GENERIC_RE.match(line):
                trying = False

    return {"has_section": has_section, "evidence_shas": evidence_shas}


def judge_freshness(pr_body: str, head_sha: str) -> dict:
    """PR 本文と head SHA から鮮度を判定する（`main()` を介さず単体テストできる純粋関数）。

    ANY セマンティクス（#906 WARNING 3）: 全セクションの証跡候補のうち **いずれか 1 件でも**
    head と前方一致すれば fresh とする。一致が無い場合 `evidence_sha` には最後の候補
    （出現順で最も後方＝追記で貼り直された可能性が高い候補）を採用する。

    戻り値のキー: fresh / evidence_sha / head_sha / has_section / reason / exit_code
    """
    if not _HEAD_SHA_RE.match(head_sha):
        return {
            "fresh": False,
            "evidence_sha": None,
            "head_sha": head_sha,
            "has_section": False,
            "reason": "invalid_head_sha",
            "exit_code": 2,
        }

    scan = find_evidence_shas(pr_body)

    if not scan["has_section"]:
        return {
            "fresh": False,
            "evidence_sha": None,
            "head_sha": head_sha,
            "has_section": False,
            "reason": "no_section",
            "exit_code": 1,
        }

    candidates = scan["evidence_shas"]
    if not candidates:
        return {
            "fresh": False,
            "evidence_sha": None,
            "head_sha": head_sha,
            "has_section": True,
            "reason": "no_sha_line",
            "exit_code": 1,
        }

    matched: str | None = None
    for sha in candidates:
        n = min(len(sha), len(head_sha))
        if sha[:n].lower() == head_sha[:n].lower():
            matched = sha
            break

    if matched is not None:
        return {
            "fresh": True,
            "evidence_sha": matched,
            "head_sha": head_sha,
            "has_section": True,
            "reason": "match",
            "exit_code": 0,
        }

    return {
        "fresh": False,
        "evidence_sha": candidates[-1],
        "head_sha": head_sha,
        "has_section": True,
        "reason": "stale",
        "exit_code": 1,
    }


# ──────────────────────────────────────────────
# 出力
# ──────────────────────────────────────────────


def print_report(result: dict) -> None:
    reason = result["reason"]
    if reason == "invalid_head_sha":
        print(f"❌ 判定不能: --head-sha が hex 7〜40 桁ではありません（{result['head_sha']!r}）", file=sys.stderr)
    elif reason == "no_section":
        print("❌ PR 本文に `## run_checks 結果` / `## npm run check 結果` セクションが見つかりません。", file=sys.stderr)
    elif reason == "no_sha_line":
        print(
            "❌ run_checks 結果セクションはありますが `実行時点コミット: <SHA>` 行が見つかりません"
            "（コードフェンス内・別セクションへの記載は無効です）。",
            file=sys.stderr,
        )
    elif reason == "stale":
        print(
            f"❌ 証跡が古い: 実行時点コミット `{result['evidence_sha']}` は現在の head "
            f"`{result['head_sha']}` と一致しません。追加コミット後は run_checks を再実行し、"
            "証跡を貼り直してください。",
            file=sys.stderr,
        )
    else:
        print(f"✅ 証跡は新鮮です（実行時点コミット `{result['evidence_sha']}` が head と一致）。")


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


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

    good_body = (
        "## run_checks 結果\n"
        "実行時点コミット: `abc1234`\n"
        "| チェック | 結果 |\n"
        "|---|---|\n"
        "| lint | OK |\n"
    )

    # ── 正常系: 一致（新鮮） ──
    r = judge_freshness(good_body, "abc1234def5678")
    check("正常系: 前方一致で fresh", r["fresh"] is True and r["exit_code"] == 0, str(r))

    # ── 正常系: 完全一致の逆方向（証跡側が長い） ──
    r_rev = judge_freshness(
        "## run_checks 結果\n実行時点コミット: `abc1234def5678`\n", "abc1234"
    )
    check("正常系: 証跡側が長くても前方一致で fresh", r_rev["fresh"] is True and r_rev["exit_code"] == 0, str(r_rev))

    # ── 乖離（stale） ──
    r_stale = judge_freshness(good_body, "1111999")
    check("乖離あり: stale・exit 1", r_stale["fresh"] is False and r_stale["reason"] == "stale" and r_stale["exit_code"] == 1, str(r_stale))

    # ── バリアント1: 見出しのバッククォート有無違い ──
    body_bt_heading = good_body.replace("## run_checks 結果", "## `run_checks` 結果")
    r_bt = judge_freshness(body_bt_heading, "abc1234")
    check("バリアント: 見出しバッククォート付きでも検出", r_bt["fresh"] is True, str(r_bt))

    body_npm_heading = good_body.replace("## run_checks 結果", "## npm run check 結果")
    r_npm = judge_freshness(body_npm_heading, "abc1234")
    check("バリアント: npm run check 見出しでも検出", r_npm["fresh"] is True, str(r_npm))

    # ── バリアント2: SHA のバッククォート無し ──
    body_no_bt_sha = "## run_checks 結果\n実行時点コミット: abc1234\n"
    r_no_bt = judge_freshness(body_no_bt_sha, "abc1234")
    check("バリアント: SHA バッククォート無しでも検出", r_no_bt["fresh"] is True, str(r_no_bt))

    # ── バリアント3: 大文字混じり SHA ──
    body_upper = "## run_checks 結果\n実行時点コミット: `ABC1234`\n"
    r_upper = judge_freshness(body_upper, "abc1234")
    check("バリアント: 大文字混じり SHA も大小無視で一致", r_upper["fresh"] is True, str(r_upper))

    # ── バリアント4: SHA 行が表の後ろ ──
    body_sha_after_table = (
        "## run_checks 結果\n"
        "| チェック | 結果 |\n"
        "|---|---|\n"
        "| lint | OK |\n"
        "実行時点コミット: `abc1234`\n"
    )
    r_after = judge_freshness(body_sha_after_table, "abc1234")
    check("バリアント: SHA 行が表の後ろでも検出", r_after["fresh"] is True, str(r_after))

    # ── バリアント5: 複数セクション（1 個目に無く 2 個目にある） ──
    body_multi_section = (
        "## run_checks 結果\n"
        "（古いセクション。SHA 行なし）\n"
        "## 変更点\n"
        "何か\n"
        "## run_checks 結果\n"
        "実行時点コミット: `abc1234`\n"
    )
    r_multi = judge_freshness(body_multi_section, "abc1234")
    check("バリアント: 複数セクションのうち後ろの 1 つに SHA 行があれば検出", r_multi["fresh"] is True, str(r_multi))

    # ── バリアント6: 全角スペース混じりの見出し ──
    body_zenkaku = "##　run_checks　結果\n実行時点コミット: `abc1234`\n"
    r_zenkaku = judge_freshness(body_zenkaku, "abc1234")
    check("バリアント: 全角スペース混じりの見出しでも検出", r_zenkaku["fresh"] is True, str(r_zenkaku))

    # ── WARNING 3: ANY セマンティクス（複数セクションのうちいずれか一致で fresh） ──
    body_old_then_new = (
        "## run_checks 結果\n"
        "実行時点コミット: `1111999`\n"  # 先頭セクション = 古い SHA
        "## run_checks 結果\n"
        "実行時点コミット: `abc1234`\n"  # 後続セクション = head 一致
    )
    r_old_then_new = judge_freshness(body_old_then_new, "abc1234")
    check(
        "WARNING3: 先頭セクションが古い SHA・後続セクションが head 一致 → fresh",
        r_old_then_new["fresh"] is True and r_old_then_new["evidence_sha"] == "abc1234",
        str(r_old_then_new),
    )

    body_new_then_old = (
        "## run_checks 結果\n"
        "実行時点コミット: `abc1234`\n"  # 先頭セクション = head 一致
        "## run_checks 結果\n"
        "実行時点コミット: `1111999`\n"  # 後続セクション = 古い SHA
    )
    r_new_then_old = judge_freshness(body_new_then_old, "abc1234")
    check(
        "WARNING3: 先頭セクションが head 一致・後続セクションが古い SHA → fresh（逆順でも）",
        r_new_then_old["fresh"] is True and r_new_then_old["evidence_sha"] == "abc1234",
        str(r_new_then_old),
    )

    # ── 境界の外側1: 別セクション（## 変更点）にだけ SHA 行がある ──
    body_wrong_section = (
        "## run_checks 結果\n"
        "| チェック | 結果 |\n"
        "|---|---|\n"
        "| lint | OK |\n"
        "## 変更点\n"
        "実行時点コミット: `abc1234`\n"
    )
    r_wrong_section = judge_freshness(body_wrong_section, "abc1234")
    check(
        "境界の外側: 別セクションの SHA 行を拾わない（no_sha_line）",
        r_wrong_section["reason"] == "no_sha_line" and r_wrong_section["exit_code"] == 1,
        str(r_wrong_section),
    )

    # ── 境界の外側2: コードフェンス内の SHA 行を拾わない ──
    body_fenced = (
        "## run_checks 結果\n"
        "例:\n"
        "```\n"
        "実行時点コミット: `abc1234`\n"
        "```\n"
    )
    r_fenced = judge_freshness(body_fenced, "abc1234")
    check(
        "境界の外側: コードフェンス内の SHA 行を拾わない（no_sha_line）",
        r_fenced["reason"] == "no_sha_line" and r_fenced["exit_code"] == 1,
        str(r_fenced),
    )

    # ── CRITICAL 1 回帰テスト: ``` フェンスの中に ~~~ を挟んでも中身がフェンス外にならない ──
    # 旧実装（``` と ~~~ を同一カウンタでトグル）は、この本文で fresh/exit 0 を誤って返していた。
    body_nested_fence = (
        "## run_checks 結果\n"
        "```text\n"
        "~~~\n"
        "実行時点コミット: `abc1234`\n"
        "~~~\n"
        "```\n"
    )
    r_nested_fence = judge_freshness(body_nested_fence, "abc1234")
    check(
        "CRITICAL1: ``` の中に ~~~ を挟んだ入れ子フェンス内の SHA 行は拾わない（no_sha_line・fresh にならない）",
        r_nested_fence["fresh"] is False
        and r_nested_fence["reason"] == "no_sha_line"
        and r_nested_fence["exit_code"] == 1,
        str(r_nested_fence),
    )

    # ── 境界の外側3: 前方一致では通ってしまう別ラベル（実行時点コミット参考:）を拾わない ──
    body_similar_label = "## run_checks 結果\n実行時点コミット参考: `abc1234`\n"
    r_similar_label = judge_freshness(body_similar_label, "abc1234")
    check(
        "境界の外側: 「実行時点コミット参考:」のような前方一致別ラベルを拾わない（no_sha_line）",
        r_similar_label["reason"] == "no_sha_line" and r_similar_label["exit_code"] == 1,
        str(r_similar_label),
    )

    # ── セクション不在（no_section・fail-closed） ──
    r_no_section = judge_freshness("普通の PR 本文です。特に証跡なし。", "abc1234")
    check(
        "セクション不在は no_section・exit 1（fail-closed）",
        r_no_section["reason"] == "no_section" and r_no_section["has_section"] is False and r_no_section["exit_code"] == 1,
        str(r_no_section),
    )

    # ── 見出しはあるが SHA 行が無い（no_sha_line） ──
    body_no_sha = "## run_checks 結果\n| チェック | 結果 |\n|---|---|\n| lint | OK |\n"
    r_no_sha = judge_freshness(body_no_sha, "abc1234")
    check(
        "見出しのみで SHA 行が無いのは no_sha_line・exit 1",
        r_no_sha["reason"] == "no_sha_line" and r_no_sha["has_section"] is True and r_no_sha["exit_code"] == 1,
        str(r_no_sha),
    )

    # ── head_sha が hex でない（invalid_head_sha・判定不能） ──
    r_invalid = judge_freshness(good_body, "not-a-sha!!")
    check(
        "head_sha が hex でなければ invalid_head_sha・exit 2",
        r_invalid["reason"] == "invalid_head_sha" and r_invalid["exit_code"] == 2,
        str(r_invalid),
    )
    r_invalid_empty = judge_freshness(good_body, "")
    check("head_sha が空文字でも invalid_head_sha・exit 2", r_invalid_empty["exit_code"] == 2, str(r_invalid_empty))

    # ── NIT 6: head_sha が 7 桁未満なら invalid_head_sha（証跡側の下限 7 と揃える） ──
    r_short = judge_freshness(good_body, "abc12")
    check(
        "NIT6: head_sha が 5 桁（7 桁未満）は invalid_head_sha・exit 2",
        r_short["reason"] == "invalid_head_sha" and r_short["exit_code"] == 2,
        str(r_short),
    )
    r_min7 = judge_freshness(good_body, "abc1234")
    check("NIT6: head_sha が 7 桁ちょうどなら受理される", r_min7["reason"] != "invalid_head_sha", str(r_min7))

    # ── find_evidence_shas 単体（純粋関数） ──
    scan = find_evidence_shas(good_body)
    check(
        "find_evidence_shas: has_section=True, evidence_shas 抽出",
        scan == {"has_section": True, "evidence_shas": ["abc1234"]},
        str(scan),
    )
    scan_multi = find_evidence_shas(body_old_then_new)
    check(
        "find_evidence_shas: 複数セクションの候補を全件・出現順で収集",
        scan_multi == {"has_section": True, "evidence_shas": ["1111999", "abc1234"]},
        str(scan_multi),
    )

    # ── main() の CLI end-to-end 実行（終了コード配線の退行検知・#749 系の完了条件） ──
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
        body_path = Path(tmp) / "pr_body.md"
        body_path.write_text(good_body, encoding="utf-8")

        cli_fresh = run_cli(["--body-file", str(body_path), "--head-sha", "abc1234"])
        check("CLI: 新鮮な証跡は exit 0", cli_fresh.returncode == 0, f"stdout={cli_fresh.stdout!r} stderr={cli_fresh.stderr!r}")

        cli_stale = run_cli(["--body-file", str(body_path), "--head-sha", "1111999"])
        check("CLI: 乖離は exit 1", cli_stale.returncode == 1, f"stdout={cli_stale.stdout!r} stderr={cli_stale.stderr!r}")

        cli_invalid = run_cli(["--body-file", str(body_path), "--head-sha", "not-hex!"])
        check("CLI: 不正な --head-sha は exit 2", cli_invalid.returncode == 2, f"stdout={cli_invalid.stdout!r} stderr={cli_invalid.stderr!r}")

        cli_missing_file = run_cli(["--body-file", str(Path(tmp) / "nope.md"), "--head-sha", "abc1234"])
        check("CLI: 存在しない --body-file は exit 2（body_unreadable）", cli_missing_file.returncode == 2, f"stdout={cli_missing_file.stdout!r} stderr={cli_missing_file.stderr!r}")

        cli_stdin = run_cli(["--head-sha", "abc1234"], stdin_text=good_body)
        check("CLI: stdin からの本文入力でも exit 0", cli_stdin.returncode == 0, f"stdout={cli_stdin.stdout!r} stderr={cli_stdin.stderr!r}")

        cli_json = run_cli(["--body-file", str(body_path), "--head-sha", "abc1234", "--json"])
        try:
            payload = json.loads(cli_json.stdout)
            json_ok = payload.get("fresh") is True and payload.get("evidence_sha") == "abc1234"
        except json.JSONDecodeError:
            json_ok = False
        check("CLI: --json が構造化出力を返す", cli_json.returncode == 0 and json_ok, f"stdout={cli_json.stdout!r}")

        # ── WARNING 4: 不正な UTF-8 を含む --body-file は body_unreadable・exit 2
        #    （internal_error に化けていないことまで --json の reason で確認する。ここを
        #    returncode だけで見ると「UnicodeDecodeError を except から外す」変異を検知できない
        #    ＝どちらの経路でも外側の judge_and_report_safely が exit 2 に倒すため） ──
        bad_utf8_path = Path(tmp) / "bad_utf8.md"
        bad_utf8_path.write_bytes(
            "## run_checks 結果\n実行時点コミット: `abc1234`\n".encode("utf-8") + b"\xff\xfe invalid \x80"
        )
        cli_bad_utf8 = run_cli(["--body-file", str(bad_utf8_path), "--head-sha", "abc1234", "--json"])
        try:
            bad_utf8_payload = json.loads(cli_bad_utf8.stdout)
            bad_utf8_reason_ok = bad_utf8_payload.get("reason") == "body_unreadable"
        except json.JSONDecodeError:
            bad_utf8_reason_ok = False
        check(
            "WARNING4: 不正な UTF-8 の --body-file は exit 2・reason=body_unreadable（internal_error に化けない）",
            cli_bad_utf8.returncode == 2 and bad_utf8_reason_ok,
            f"stdout={cli_bad_utf8.stdout!r} stderr={cli_bad_utf8.stderr!r}",
        )

    # ── WARNING 4: 想定外の内部エラーは judge_and_report_safely が internal_error・exit 2 へ倒す
    #    （main() 全体の try/except を、判定ロジックを差し替える形で in-process 検証する） ──
    with tempfile.TemporaryDirectory() as tmp2:
        body_path2 = Path(tmp2) / "body.md"
        body_path2.write_text(good_body, encoding="utf-8")

        class _FakeArgsInternalError:
            body_file = str(body_path2)
            head_sha = "abc1234"
            json = False

        _module = sys.modules[__name__]
        _orig_judge_freshness = _module.judge_freshness

        def _boom(_pr_body: str, _head_sha: str) -> dict:
            raise RuntimeError("induced failure for self-test (WARNING4 internal_error path)")

        _module.judge_freshness = _boom
        try:
            rc_internal = judge_and_report_safely(_FakeArgsInternalError())
        finally:
            _module.judge_freshness = _orig_judge_freshness

        check(
            "WARNING4: 想定外の例外は judge_and_report_safely で internal_error・exit 2 へ倒れる",
            rc_internal == 2,
            f"rc={rc_internal!r}",
        )
        # 差し替えを確実に戻せていること（後続テストへの影響防止の自己確認）
        check(
            "WARNING4: judge_freshness の差し替えは確実に元へ戻る",
            _module.judge_freshness is _orig_judge_freshness,
            "",
        )

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────


def _judge_and_report(args: argparse.Namespace) -> int:
    """`--self-test` 以外の通常実行本体。

    ファイル・標準入力の読み取りに起因する想定内エラー（存在しない・権限無し・不正な UTF-8）は
    ここで `body_unreadable`（exit 2）として明示的に処理する。それ以外の想定外の例外は捕捉せず、
    呼び出し元 `judge_and_report_safely()` の `try/except Exception` に委ねる（#906 WARNING 4）。
    """
    if args.body_file:
        try:
            pr_body = Path(args.body_file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"❌ 判定不能: --body-file を読めません: {e}", file=sys.stderr)
            if args.json:
                print(json.dumps({"fresh": False, "reason": "body_unreadable", "error": str(e)}, ensure_ascii=False))
            return 2
    else:
        try:
            pr_body = sys.stdin.read()
        except UnicodeDecodeError as e:
            print(f"❌ 判定不能: 標準入力を読めません: {e}", file=sys.stderr)
            if args.json:
                print(json.dumps({"fresh": False, "reason": "body_unreadable", "error": str(e)}, ensure_ascii=False))
            return 2

    result = judge_freshness(pr_body, args.head_sha)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return result["exit_code"]


def judge_and_report_safely(args: argparse.Namespace) -> int:
    """`_judge_and_report()` を実行し、想定外の例外を `internal_error`（exit 2）へ倒す
    （#906 WARNING 4）。`--self-test` 自体の失敗（exit 1）や正常な判定結果の exit code は
    このパスを通らない（`main()` は `--self-test` 指定時に `run_self_test()` を直接呼び、
    このラッパーへは来ない）ため握り潰さない。
    """
    try:
        return _judge_and_report(args)
    except Exception as e:  # noqa: BLE001 - 判定不能への最終防波堤（ブロックしすぎない側の fail-closed）
        print(f"❌ 判定不能: 予期しない内部エラー（{type(e).__name__}: {e}）", file=sys.stderr)
        if args.json:
            print(json.dumps({"fresh": False, "reason": "internal_error", "error": str(e)}, ensure_ascii=False))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--body-file", help="PR 本文ファイルのパス（省略時は標準入力から読む）")
    parser.add_argument("--head-sha", help="比較対象の head SHA（hex 7〜40 桁）")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    # 本ツールは tools/run_checks.sh から `--self-test` 付きで実際に配線・起動されている
    # （モジュール docstring「配線」節参照）。マーカーで自己除外はしない。
    parser.add_argument("--self-test", action="store_true", help="セルフテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.head_sha:
        parser.print_help()
        return 2

    return judge_and_report_safely(args)


if __name__ == "__main__":
    sys.exit(main())
