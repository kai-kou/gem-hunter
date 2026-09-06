#!/usr/bin/env python3
"""check_selftest_wiring.py — tools/ 配下スクリプトの `--self-test` 配線漏れを検査する
（Issue #612）。対象は `.py` / `.mjs` / `.mts` / `.sh`（`SCAN_EXTENSIONS`）で、`tools/` 配下を
再帰的に走査する（Issue #992 フォローアップ・下記「走査対象の拡張」参照）。

## 走査対象の拡張（Issue #992）

当初は `.py` のみが対象だったが、`tools/*.mjs`（将来の `.mts` を含む）にも `--self-test` を
実装したスクリプトが増えたため、対象拡張子を `SCAN_EXTENSIONS`（`py` / `mjs` / `mts`）へ広げた。
実例: `tools/run_lighthouse.mjs` は `--self-test` を実装済みなのに `run_checks.sh` へ未配線だった
（本判定だけが配線され、self-test 呼び出しが無い状態）。

`*.test.mjs`（`e2e-chromium-executable.test.mjs` 等の Vitest テストファイル）も同じ `*.mjs` glob に
乗るため走査対象に含めている。除外を追加しなかった理由: これらは `--self-test` フラグそのものを
実装していない（Vitest の `it()`/`describe()` で完結する）ため `script_has_selftest_flag()` が
`False` を返し、自然に `not_applicable` へ落ちる。将来 `.test.mjs` が誤って本検査の対象になる
ケース（`--self-test` という文字列がテストコード中に偶然出現する等）が出たら、そのとき初めて
拡張子ベースの除外を検討する（YAGNI・現時点では発生していない）。

## 走査対象のさらなる拡張（`.sh` / 再帰走査・Issue #992 フォローアップ）

Layer 1 セルフレビュー（PR #1018）で「`tools/` に `.sh` の対象実体が無い」という前提が事実誤認
だったと判明した。実測: `tools/progress_heartbeat.sh` / `tools/sync_broker_drift.sh` は
`--self-test` を実装済みなのに `run_checks.sh` へ未配線だった（今回 `run_checks.sh` へ配線して
決着済み）。よって `SCAN_EXTENSIONS` に `sh` を追加した。`.sh` のコメント抽出は Python と同じ
`#` 系だが tokenize は使えない（bash は Python 構文ではない）ため、`wiring_marker.strip_shell_line_comment`
（`run_checks.sh` 側のコメント除去でも使っている行単位クォート追跡・#933 で共通モジュールへ集約）
を再利用した専用の `wiring_marker.shell_comment_texts()` で抽出する。

また `tools_dir.glob()`（非再帰）だった走査を `tools_dir.rglob()`（再帰）へ変更し、
`tools/gem-pool/*.mjs` 等のサブディレクトリのスクリプトも走査対象に含めた（変更前は
`not_applicable` にすらならず完全に不可視だった）。実測時点でサブディレクトリのスクリプトは
いずれも `--self-test` を実装していないため、この変更による新規違反は 0 件（将来サブディレクトリに
`--self-test` を実装したスクリプトが追加された場合の見落としを防ぐ回帰防止策）。
`node_modules` 等の除外は現時点で `tools/` 配下に存在しないため未実装（YAGNI）。

## なぜ必要か

`tools/` の検査スクリプトの多くは `--self-test`（ネットワーク・実データ非依存のユニットテスト）を
持ち、`tools/run_checks.sh` から実行される。ところが実際に調べたところ、`check_ui_dimensions.py`
`check_prefetchable_side_effects.py` の 2 本が実装されているのに `run_checks.sh` へ配線されておらず、
この間に偽陽性バグが self-test なしで潜伏していた（Issue #612）。

配線漏れは「テストを書いたのに実行されない」状態で、**検査があるのに機能していない**という
最も見つけにくい失敗モードである。本スクリプトはこの再発を止める。

🔁 `check_tool_wiring.py`（本判定の配線漏れ＝死蔵の検査）と対になる検査である。シェルコメント
除去とマーカー走査の共通ロジックは `tools/wiring_marker.py`（Issue #933）へ集約済みで、
両検査はそこから import して使う。

## 検出する 2 つの形

1. `--self-test` を実装しているのに `run_checks.sh` のどこからも `--self-test` 付きで
   呼ばれていないスクリプト（本体すら一切呼ばれていない場合を含む）。
2. `run_checks.sh` に**通常実行だけ**が配線されていて `--self-test` 呼び出しが無いスクリプト
   （本体の呼び出しがあるかどうかは判定に影響しない。`--self-test` 呼び出し文字列の有無だけを見る）。

いずれも同じ判定（「`<ファイル名> ... --self-test` という呼び出しが `run_checks.sh` に無い」）で
検出できるため、内部ロジックは 1 つに統一している。

## 意図的に配線しないものがある場合（マーカー）

`run_checks.sh` は「PR 前に毎回走らせる品質ゲート」であり、「`--self-test` を持つ全スクリプトの
実行場所」ではない。特定の場面（スケジューラ・他スキルからの直接起動・他検査からの import 経由の
間接実行等）でのみ使う運用ツールは、配線しないことが正しい判断でありうる。その場合はスクリプト側の
任意の行に次のマーカーを書くと、本検査から除外できる:

    # selftest-wiring-ok: {なぜ配線しないかの理由}

🔴 **`.mjs` / `.mts` では `#` が JS のコメントとして認識されない**（独立行に `#` で書くと
`node` 実行が SyntaxError で壊れる）ため、代わりに `//` または `/* ... */` を使う:

    // selftest-wiring-ok: {なぜ配線しないかの理由}
    /* selftest-wiring-ok: {なぜ配線しないかの理由} */

`.sh` は Python と同じ `#` を使う（bash のコメント記号も `#` のため）。

理由が空（`# selftest-wiring-ok:` だけ、または `// selftest-wiring-ok:` だけ）のマーカーは
無効として扱い、除外しない（「除外してよいか」を人が判断した形跡を残させることが目的であり、
マーカーの存在だけでは通さない。`check_duplicate_source_patterns.py` の `dup-ok` マーカーと
同じ思想）。

## 誤判定の防止（2026-08-24 の敵対的レビューで発見された 2 つの穴）

本検査自身が「配線されていないのに PASS する」誤判定を起こしうる 2 つの穴が見つかったため、
以下のとおり修正している。

1. **`run_checks.sh` 側のコメントアウトされた `run_check` 行を「配線済み」と誤認する**:
   `is_wired()` は生テキストの正規表現検索だったため、`# run_check "..." python3 tools/foo.py
   --self-test` のようにシェルコメントとして無効化された行も一致してしまい、実際には一度も
   実行されないスクリプトを「配線済み」と報告していた。対策として、`is_wired()` は検索前に
   `wiring_marker.strip_shell_comments()`（クォート外の `#` 以降を除去する簡易 bash コメント
   除去。シングル / ダブルクォートの状態を追跡し、クォート内の `#`（例: `echo "## run_checks
   結果"`）は保持する）を通す。ヒアドキュメント（`<<EOF`）は `run_checks.sh` に存在しないため
   未対応（将来追加されたら本関数も見直しが必要）。

2. **対象スクリプト側の docstring 内でマーカー書式を「説明する地の文」を、本物のマーカーと
   誤認して除外してしまう**: 旧実装はマーカー正規表現をファイル内容全体に対して素朴な正規表現
   検索していたため、docstring の中で「`# selftest-wiring-ok: 理由` と書く」と地の文で説明した
   だけの文字列（実コメントではない）にもマッチし、意図せず自己除外されてしまっていた（本検査自身の
   docstring がまさにこの形を取っているため、他スクリプトが利用例として書式に言及するだけで
   誤除外されうるという皮肉な穴だった）。対策として、`marker_reason()` /
   `has_invalid_empty_marker()` は `tokenize` モジュールで実コメントトークン（`tokenize.COMMENT`）
   だけを抽出してからマーカーを探す（`_comment_texts()`）。**構文エラー等でトークナイズ自体が
   失敗した場合はクラッシュせず、安全側＝「マーカーなし」として扱う**（誤って除外されるより、
   誤って違反扱いされる方が安全 — 除外は人が明示的にマーカーを書かない限り成立しないため）。
   この場合は `scan()` が stderr に警告を出す（`Verdict.tokenize_failed`）。

## 誤判定の防止（PR #1018 の Layer 1 セルフレビューで発見された 2 つの穴）

3. **`.mjs`/`.mts` の自前レキサが正規表現リテラルを認識せず、文字クラス内の `/*` を
   ブロックコメント開始と誤認していた**（fail-closed の誤検出）: 旧 `_js_comment_texts()` は
   `const SEP_RE = /[/*]/;` のような正規表現リテラルに遭遇すると、内部の `/*` を本物の
   ブロックコメント開始と誤解し、それ以降（本物のマーカーを含む）を「まだ閉じていない
   ブロックコメントの続き」として飲み込んでしまっていた。対策として、JS/TS のコメント抽出は
   `tools/ts_source.py` の `extract_comments()`（正規表現リテラルを不透明な単位として読み飛ばす）
   へ委譲した。逆方向の反例（文字列・テンプレートリテラル内の偽マーカーを拾わない・fail-open）
   も同じ関数の設計で防いでいる。

4. **JS 側のマーカー正規表現がコメント本文中のどこでも一致してしまう**（fail-open）:
   `_JS_MARKER_RE` が非アンカーだったため、`// See docs/... for the selftest-wiring-ok: marker
   format.` のような **地の文で書式に言及しただけの通常コメント** まで有効なマーカーと誤認し、
   ファイルを黙って除外してしまっていた（Python 側の `_MARKER_RE` は `#` 直後にしか一致しないため
   この問題を元々持たない）。対策として、`_JS_MARKER_RE` をコメント本文の先頭（ブロックコメントの
   `*` 継続行は許容）にアンカーした。

使い方:
    python3 tools/check_selftest_wiring.py              # 配線漏れ検査（人間可読レポート）
    python3 tools/check_selftest_wiring.py --json        # 機械可読 JSON
    python3 tools/check_selftest_wiring.py --self-test   # 検出ロジック自体のユニットテスト

終了コード: 0 = 配線漏れなし / 1 = 配線漏れあり（または --self-test 失敗）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ts_source  # noqa: E402 — 共通モジュール（#612 / #992）。JS/TS のコメント抽出はここへ委譲する
import wiring_marker  # noqa: E402 — シェルコメント除去・マーカー走査の共通ロジック（#933）

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
RUN_CHECKS_PATH = TOOLS_DIR / "run_checks.sh"

# 走査対象の拡張子（Issue #992）。Python は tokenize ベース、mjs/mts は `ts_source.extract_comments`
# （正規表現リテラルを認識する専用レキサ）、sh は `_shell_comment_texts`（行単位クォート追跡）で
# コメントを抽出する（言語ごとの抽出関数は _comment_texts_for_lang() が振り分ける）。
SCAN_EXTENSIONS = ("py", "mjs", "mts", "sh")

# 本検査自身（新規作成・Issue #612）。`run_checks.sh` への配線要否は親セッション側の判断事項で、
# 本検査が自分自身を対象に含めるとブートストラップ問題（配線される前は必ず自分自身を違反として
# 検出してしまう）が起きるため、コード側の特例ではなく通常のマーカー運用で自己除外する。
_SELF_FILENAME = "check_selftest_wiring.py"
# selftest-wiring-ok: 新規作成スクリプト自身の run_checks.sh 配線要否は親セッション側の判断事項

# `add_argument("--self-test", ...)` / `"--self-test" in sys.argv` のどちらの書き方でも
# 「--self-test」がクォートで囲まれた文字列リテラルとして現れる。docstring の使い方セクションに
# ある `python3 tools/foo.py --self-test`（クォート無しの地の文）は実装ではなく単なる利用例なので
# ここでは拾わない（クォートで囲まれているかどうかで「フラグの実装」と「使用例の言及」を区別する）。
_SELFTEST_FLAG_RE = re.compile(r'["\']--self-test["\']')

# `.sh` 用（Issue #992 フォローアップ）: bash の典型的な実装は `case "$1" in --self-test) ... ;;`
# のような **case アーム**で、`--self-test` はクォートで囲まれない（`)` が直後に続くだけ）。
# 上記 `_SELFTEST_FLAG_RE`（クォート必須）はこの形を検出できない（実例: `progress_heartbeat.sh`）。
# クォートされた比較形（`[ "$1" = "--self-test" ]`。実例: `sync_broker_drift.sh`）はそのまま
# `_SELFTEST_FLAG_RE` で拾えるので、ここでは case アーム形だけを追加で見る。
# 🔴 case アーム形は行頭（インデント許容）にアンカーする（`^[ \t]*` + `re.MULTILINE`）。
# 非アンカーだと `run_checks.sh` 自身が持つ大量のドキュメントラベル文字列
# `"... (foo.py --self-test)" ...` （`--self-test)` を含む）を誤って「case アーム」と
# 誤検出し、`run_checks.sh` が自己参照で違反判定されてしまう（実測で確認済み）。
_SH_CASE_ARM_SELFTEST_RE = re.compile(r'^[ \t]*["\']?--self-test["\']?\)', re.MULTILINE)

# マーカー語（`wiring_marker.scan_markers` へ渡す token）。
_TOKEN = "selftest-wiring-ok"


def script_has_selftest_flag(content: str, lang: str = "py") -> bool:
    """スクリプトが `--self-test` オプションを実装しているか。

    `py` / `js` は「クォート付き文字列リテラルとしての `--self-test`」の有無で判定する
    （`--shim-self-test` のような別名フラグ（例: `gh_shim.py`）は「--self-test」という
    文字列そのものと一致しないため誤検出しない。docstring の地の文（クォート無し）も
    拾わない）。`sh` はそれに加えて bash の case アーム形（`--self-test)`）も見る
    （`_SH_CASE_ARM_SELFTEST_RE` 参照）。
    """
    if _SELFTEST_FLAG_RE.search(content):
        return True
    if lang == "sh":
        return bool(_SH_CASE_ARM_SELFTEST_RE.search(content))
    return False


_LANG_BY_SUFFIX = {".py": "py", ".mjs": "js", ".mts": "js", ".sh": "sh"}


def _lang_for_filename(filename: str) -> str:
    """拡張子から `wiring_marker.comment_texts_for_lang()` に渡す言語キーを決める。未知の
    拡張子は安全側として python 用の tokenize 抽出にフォールバックする（対象拡張子は
    `SCAN_EXTENSIONS` で絞り込み済みのため実運用では到達しない）。"""
    return _LANG_BY_SUFFIX.get(Path(filename).suffix, "py")


def marker_reason(content: str, lang: str = "py") -> str | None:
    """有効な `selftest-wiring-ok` マーカー（実コメントとして書かれたもの）の理由文字列を返す。

    マーカーが無い、全てのマーカーの理由が空（無効マーカー）、またはコメント抽出自体が
    失敗した場合は None を返す（= 除外されない・安全側）。複数マーカーがあり、どれか 1 つでも
    理由が非空なら、その理由を返す。`lang` は `"py"`（既定）/ `"js"` / `"sh"`。
    """
    return wiring_marker.marker_reason(content, _TOKEN, lang)


def has_invalid_empty_marker(content: str, lang: str = "py") -> bool:
    """理由が空の `selftest-wiring-ok` マーカーが（有効な理由付きマーカーとは別に）存在するか。"""
    return wiring_marker.has_invalid_empty_marker(content, _TOKEN, lang)


def is_wired(filename: str, run_checks_content: str) -> bool:
    """`run_checks.sh` の中に `<filename> ... --self-test` という **有効な**（コメントアウト
    されていない）呼び出しがあるか。

    🔴 **ファイル名の直後の閉じクォートを許容する**（F6・Issue #992 フォローアップ）:
    `node "$REPO_ROOT/tools/foo.mjs" --self-test` のようにパス全体が引用符で囲まれている場合、
    `foo.mjs` の直後には空白ではなく閉じクォート（`"` / `'`）が来る。旧実装（ファイル名の
    直後に空白を必須とする）はこの形を配線済みと認識できず、正しく配線されているスクリプトを
    配線漏れと誤検出していた（実測: `False` を返していた）。
    """
    stripped = wiring_marker.strip_shell_comments(run_checks_content)
    pattern = re.compile(re.escape(filename) + r"[\"']?\s+--self-test\b")
    return bool(pattern.search(stripped))


@dataclass
class Verdict:
    """1 スクリプトぶんの判定結果。"""

    filename: str
    status: str  # "not_applicable" | "wired" | "excluded" | "violation"
    reason: str | None = None  # excluded のときのマーカー理由
    invalid_marker: bool = False  # violation だが空理由マーカーが存在した場合 True
    tokenize_failed: bool = False  # tokenize 失敗により「マーカーなし」へ安全側フォールバックしたか


def evaluate_script(filename: str, content: str, run_checks_content: str) -> Verdict:
    """1 ファイルぶんの内容から配線状態を判定する（テスト容易性のための純関数）。

    `filename` の拡張子（`.py` / `.mjs` / `.mts` / `.sh`）からコメント抽出方式を自動判定する。
    """
    lang = _lang_for_filename(filename)
    if not script_has_selftest_flag(content, lang):
        return Verdict(filename, "not_applicable")

    marker_scan = wiring_marker.scan_markers(content, _TOKEN, lang)
    if marker_scan.reasons:
        return Verdict(
            filename,
            "excluded",
            reason=marker_scan.reasons[0],
            tokenize_failed=marker_scan.tokenize_failed,
        )

    if is_wired(filename, run_checks_content):
        return Verdict(filename, "wired", tokenize_failed=marker_scan.tokenize_failed)

    return Verdict(
        filename,
        "violation",
        invalid_marker=marker_scan.has_empty,
        tokenize_failed=marker_scan.tokenize_failed,
    )


@dataclass
class Report:
    """走査結果。violations は要対応、excluded はマーカーで除外済み。"""

    wired: list[str] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    invalid_markers: list[str] = field(default_factory=list)

    def add(self, v: Verdict) -> None:
        if v.status == "wired":
            self.wired.append(v.filename)
        elif v.status == "excluded":
            self.excluded.append((v.filename, v.reason or ""))
        elif v.status == "violation":
            self.violations.append(v.filename)
            if v.invalid_marker:
                self.invalid_markers.append(v.filename)


def scan(tools_dir: Path, run_checks_content: str) -> Report:
    """`tools_dir` 配下を **再帰的に** 走査する（F4・Issue #992 フォローアップ）。

    旧実装は非再帰 `glob()` だったため `tools/gem-pool/*.mjs` 等のサブディレクトリの
    スクリプトが `not_applicable` にすらならず完全に不可視だった。`rglob()` へ変更し、
    サブディレクトリのスクリプトも走査対象に含める（実測時点でサブディレクトリの
    スクリプトはいずれも `--self-test` を実装していないため新規違反は 0 件。将来
    サブディレクトリに実装が追加された場合の見落としを防ぐ回帰防止策）。
    """
    report = Report()
    paths: list[Path] = []
    for ext in SCAN_EXTENSIONS:
        paths.extend(tools_dir.rglob(f"*.{ext}"))
    for path in sorted(paths):
        if path.name == _SELF_FILENAME:
            continue
        # `tools_dir` からの相対パス（POSIX 区切り）を識別子にする（rglob 化に伴う変更）。
        # ルート直下のファイルは相対パス＝ファイル名のまま（表示は変わらない）。サブ
        # ディレクトリのファイルは `gem-pool/collect.mjs` のような相対パスになり、同名
        # ファイルが異なるディレクトリにあっても衝突しない。`is_wired()` の部分文字列検索は
        # `run_checks.sh` の実際の呼び出し（`node tools/gem-pool/collect.mjs --self-test`）が
        # この相対パスをそのまま含むため、`tools/` プレフィックスの有無に関わらず一致する。
        rel_name = path.relative_to(tools_dir).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"⚠️  読み込み失敗のためスキップ: {rel_name}（{e}）", file=sys.stderr)
            continue
        verdict = evaluate_script(rel_name, content, run_checks_content)
        if verdict.tokenize_failed:
            print(
                f"⚠️  tokenize 失敗のためマーカーなし扱い（安全側）: {rel_name}"
                "（構文エラー等でコメント解析ができなかった）",
                file=sys.stderr,
            )
        report.add(verdict)
    return report


def render_human(report: Report) -> str:
    lines: list[str] = []
    total_checked = len(report.wired) + len(report.excluded) + len(report.violations)
    lines.append(
        f"[selftest-wiring] 走査対象（--self-test 実装済み）: 全 {total_checked} 本"
        f"（配線済み {len(report.wired)} / マーカー除外 {len(report.excluded)} "
        f"/ 配線漏れ {len(report.violations)}）"
    )
    if report.violations:
        for name in report.violations:
            if name in report.invalid_markers:
                lines.append(
                    f"  ❌ 配線漏れ: {name}"
                    f"（selftest-wiring-ok マーカーはあるが理由が空のため無効）"
                )
            else:
                lines.append(f"  ❌ 配線漏れ: {name}（run_checks.sh に --self-test 呼び出しが無い）")
    if report.excluded:
        lines.append(f"  ℹ️  マーカーで除外済み: {len(report.excluded)} 件")
        for name, reason in report.excluded:
            lines.append(f"      {name}: {reason}")
    if report.violations:
        lines.append(
            "[selftest-wiring] FAIL: 配線漏れ "
            f"{len(report.violations)} 件（run_checks.sh へ配線するか、"
            "selftest-wiring-ok マーカーで意図的な除外を明示すること）"
        )
    else:
        lines.append("[selftest-wiring] PASS（配線漏れなし）")
    return "\n".join(lines)


def exit_code_for(report: Report) -> int:
    """`main()` が返す終了コード（`check-tool-design-rules.md` §1 の標準）。

    `main()` 本体から切り出して独立した純関数にしているのは、`sys.exit()` まで到達する
    経路を self-test で直接検証するため（同ルール §4:「終了コードを返す経路を変異対象に
    必ず 1 つ含める」・「判定は正しいが終了コードへ反映されていない」退行を見逃さない）。
    """
    return 1 if report.violations else 0


def render_json(report: Report) -> str:
    return json.dumps(
        {
            "wired": report.wired,
            "excluded": [{"file": n, "reason": r} for n, r in report.excluded],
            "violations": report.violations,
            "invalid_markers": report.invalid_markers,
        },
        ensure_ascii=False,
        indent=2,
    )


# ─────────────────────────────────────────────────────────────
# --self-test（ネットワーク・実ファイル不要のユニットテスト）
# ─────────────────────────────────────────────────────────────

def _self_test() -> int:
    failures: list[str] = []
    assertions = 0

    def check(label: str, cond: bool) -> None:
        nonlocal assertions
        assertions += 1
        if not cond:
            failures.append(label)

    # ── ケース A: --self-test を持つのに run_checks.sh に一切出現しない → 検出する ──
    src_a = (
        "#!/usr/bin/env python3\n"
        '"""foo.py --self-test で実行"""\n'
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check("A: has_selftest_flag 検出", script_has_selftest_flag(src_a))
    check("A: marker 無し", marker_reason(src_a) is None)
    check("A: 未配線 run_checks.sh で is_wired=False", not is_wired("foo.py", ""))
    v_a = evaluate_script("foo.py", src_a, "")
    check("A: 判定は violation", v_a.status == "violation")

    # ── ケース B: run_checks.sh に通常実行だけあって --self-test が無い → 検出する ──
    # （今回の実際の漏れ = check_ui_dimensions.py / check_prefetchable_side_effects.py の形）
    rc_b = 'run_check "bar" python3 tools/bar.py\n'
    check("B: 本体のみ配線では is_wired=False", not is_wired("bar.py", rc_b))
    src_b = (
        "#!/usr/bin/env python3\n"
        'if "--self-test" in __import__("sys").argv:\n'
        "    pass\n"
    )
    check("B: sys.argv 判定でも has_selftest_flag 検出", script_has_selftest_flag(src_b))
    v_b = evaluate_script("bar.py", src_b, rc_b)
    check("B: 判定は violation", v_b.status == "violation")

    # ── ケース C: 理由付きマーカーがある → 検出しない ──
    src_c = (
        "#!/usr/bin/env python3\n"
        "# selftest-wiring-ok: 週次スロットでのみ起動する運用ツールで、PR 前の品質ゲートではない\n"
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check(
        "C: marker_reason が非空を返す",
        marker_reason(src_c) == "週次スロットでのみ起動する運用ツールで、PR 前の品質ゲートではない",
    )
    v_c = evaluate_script("baz.py", src_c, "")
    check("C: 判定は excluded", v_c.status == "excluded")

    # ── ケース D: 理由が空のマーカー → 無効として検出する ──
    src_d1 = (
        "#!/usr/bin/env python3\n"
        "# selftest-wiring-ok:\n"
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check("D1: 理由が空なら marker_reason は None", marker_reason(src_d1) is None)
    v_d1 = evaluate_script("qux.py", src_d1, "")
    check("D1: 判定は violation（無効マーカーは除外しない）", v_d1.status == "violation")
    check("D1: invalid_marker フラグが立つ", v_d1.invalid_marker)

    src_d2 = (
        "#!/usr/bin/env python3\n"
        "# selftest-wiring-ok:   \n"  # 空白のみの理由も無効
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check("D2: 空白のみの理由も無効", marker_reason(src_d2) is None)

    # ── 追加: 正しく配線済みのスクリプトは検出しない ──
    src_e = 'p.add_argument("--self-test", action="store_true")\n'
    rc_e = (
        'run_check "quux" python3 tools/quux.py\n'
        'run_check "quux self-test" python3 tools/quux.py --self-test\n'
    )
    check("E: 配線済みは is_wired=True", is_wired("quux.py", rc_e))
    v_e = evaluate_script("quux.py", src_e, rc_e)
    check("E: 判定は wired", v_e.status == "wired")

    # ── 追加: --self-test を持たないスクリプトは対象外（誤検出しない） ──
    src_f = "#!/usr/bin/env python3\nprint('hello')\n"
    check("F: --self-test 未実装は has_selftest_flag=False", not script_has_selftest_flag(src_f))
    v_f = evaluate_script("plain.py", src_f, "")
    check("F: 判定は not_applicable", v_f.status == "not_applicable")

    # ── 追加: docstring の地の文（クォート無し）だけでは実装とみなさない ──
    src_g = (
        "#!/usr/bin/env python3\n"
        '"""使い方:\n'
        "  python3 tools/g.py --self-test  # クォート無しの利用例のみ（実装ではない）\n"
        '"""\n'
        "print('no real flag here')\n"
    )
    check("G: 地の文だけでは has_selftest_flag=False", not script_has_selftest_flag(src_g))

    # ── 追加: 似て非なるフラグ名（--shim-self-test 等）は別物として扱う ──
    src_h = 'if argv[0] == "--shim-self-test":\n    pass\n'
    check("H: --shim-self-test は --self-test と誤認しない", not script_has_selftest_flag(src_h))

    # ── 追加: 複数マーカーのうち有効な理由があれば拾う（空マーカーが先にあっても後段を見る） ──
    src_i = (
        "# selftest-wiring-ok:\n"
        "# 他のコメント\n"
        "# selftest-wiring-ok: 有効な理由\n"
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check("I: 複数マーカー中の有効な理由を拾う", marker_reason(src_i) == "有効な理由")
    v_i = evaluate_script("mixed.py", src_i, "")
    check("I: 有効な理由が 1 つでもあれば excluded", v_i.status == "excluded")

    # ── 反例 J（2026-08-24 敵対的レビュー発見）: run_checks.sh 側でコメントアウトされた
    # `run_check ... --self-test` 呼び出しを「配線済み」と誤認しない ──
    run_checks_commented_out = (
        '# run_check "sneaky" python3 tools/sneaky.py\n'
        '# run_check "sneaky self-test" python3 tools/sneaky.py --self-test\n'
    )
    check(
        "J: コメントアウトされた --self-test 呼び出しは is_wired=False",
        not is_wired("sneaky.py", run_checks_commented_out),
    )
    # 同じ行がコメントでなければ従来どおり検出する（回帰防止）
    run_checks_active = 'run_check "sneaky self-test" python3 tools/sneaky.py --self-test\n'
    check(
        "J: コメントでない同じ行は is_wired=True（回帰防止）",
        is_wired("sneaky.py", run_checks_active),
    )
    # クォート内の `#`（例: echo "## run_checks 結果"）を誤ってコメント開始と扱わない
    run_checks_quoted_hash = (
        'echo "## run_checks 結果"\n'
        'run_check "sneaky self-test" python3 tools/sneaky.py --self-test\n'
    )
    check(
        "J: クォート内の # で後続行の判定が壊れない",
        is_wired("sneaky.py", run_checks_quoted_hash),
    )

    # ── 反例 K（2026-08-24 敵対的レビュー発見）: docstring 内でマーカー書式を「説明する
    # 地の文」（実コメントではない）を、本物のマーカーと誤認して除外しない ──
    src_k = (
        "#!/usr/bin/env python3\n"
        '"""マーカー書式を説明する docstring:\n'
        "    # selftest-wiring-ok: これは例示であって本物のマーカーではない\n"
        '"""\n'
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check("K: docstring 内の言及は marker_reason=None", marker_reason(src_k) is None)
    v_k = evaluate_script("sneaky_doc.py", src_k, "")
    check("K: 判定は violation（誤って excluded されない）", v_k.status == "violation")
    # 同じ文言でも実コメントとして書かれていれば従来どおり有効に効く（回帰防止）
    src_k2 = (
        "#!/usr/bin/env python3\n"
        "# selftest-wiring-ok: これは実コメントであり本物のマーカー\n"
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check(
        "K: 実コメントのマーカーは従来どおり有効（回帰防止）",
        marker_reason(src_k2) == "これは実コメントであり本物のマーカー",
    )
    v_k2 = evaluate_script("real_marker.py", src_k2, "")
    check("K: 実コメントのマーカーは excluded", v_k2.status == "excluded")

    # ── 反例 L: 構文エラーのある Python ファイルでもクラッシュせず、安全側
    # （マーカーなし扱い）で判定できる ──
    src_l = (
        "#!/usr/bin/env python3\n"
        "def f(:\n"  # 構文エラー
        "    pass\n"
        'p.add_argument("--self-test", action="store_true")\n'
    )
    check("L: 構文エラーでも例外を投げず marker_reason=None", marker_reason(src_l) is None)
    v_l = evaluate_script("broken.py", src_l, "")
    check("L: 構文エラー時は violation（マーカーなし扱い・クラッシュしない）", v_l.status == "violation")
    check("L: tokenize_failed フラグが立つ", v_l.tokenize_failed)

    # ══════════════════════════════════════════════════════════════════
    # 以下 .mjs/.mts（Issue #992・射程拡大）
    # ══════════════════════════════════════════════════════════════════

    # ── 拡張子 → 言語判定 ──
    check("mjs は js 判定", _lang_for_filename("foo.mjs") == "js")
    check("mts も js 判定", _lang_for_filename("foo.mts") == "js")
    check("py は py 判定", _lang_for_filename("foo.py") == "py")

    # ── ケース M: .mjs で --self-test を実装しているのに run_checks.sh 未配線
    #    （run_lighthouse.mjs の実際の穴と同型） → 検出する ──
    src_m = (
        "#!/usr/bin/env node\n"
        "// 本体の判定ロジック\n"
        "if (process.argv.includes('--self-test')) {\n"
        "  selfTest()\n"
        "}\n"
    )
    check("M: mjs でも has_selftest_flag 検出", script_has_selftest_flag(src_m))
    rc_m_unwired = 'run_check_timeout "Lighthouse" "$T" node tools/run_lighthouse.mjs\n'
    v_m = evaluate_script("run_lighthouse.mjs", src_m, rc_m_unwired)
    check("M: mjs 本体のみ配線では violation", v_m.status == "violation")

    # ── ケース N: .mjs の `// selftest-wiring-ok: 理由` マーカー → excluded ──
    src_n = (
        "#!/usr/bin/env node\n"
        "// selftest-wiring-ok: 週次スロットでのみ起動するため PR ゲートには配線しない\n"
        "if (process.argv.includes('--self-test')) { selfTest() }\n"
    )
    check(
        "N: mjs マーカーの理由を取得できる",
        marker_reason(src_n, "js") == "週次スロットでのみ起動するため PR ゲートには配線しない",
    )
    v_n = evaluate_script("weekly.mjs", src_n, "")
    check("N: mjs マーカーありは excluded", v_n.status == "excluded")

    # ── ケース O: .mjs の理由が空のマーカー → 無効として violation ──
    src_o = (
        "// selftest-wiring-ok:\n"
        "if (process.argv.includes('--self-test')) { selfTest() }\n"
    )
    check("O: mjs 空理由マーカーは marker_reason=None", marker_reason(src_o, "js") is None)
    v_o = evaluate_script("empty_marker.mjs", src_o, "")
    check("O: mjs 空理由マーカーは violation", v_o.status == "violation")
    check("O: invalid_marker フラグが立つ", v_o.invalid_marker)

    # ── ケース P（境界の外側・#992 完了条件の必須負ケース）: 文字列リテラル /
    #    テンプレートリテラルの中に書かれた偽マーカーを除外扱いしない ──
    src_p1 = (
        "const msg = \"// selftest-wiring-ok: 文字列の中の偽マーカー\"\n"
        "if (process.argv.includes('--self-test')) { selfTest() }\n"
    )
    check(
        "P1: ダブルクォート文字列内の偽マーカーは拾わない",
        marker_reason(src_p1, "js") is None,
    )
    v_p1 = evaluate_script("fake_marker_string.mjs", src_p1, "")
    check("P1: violation のまま（誤って excluded されない）", v_p1.status == "violation")

    src_p2 = (
        "const msg = `// selftest-wiring-ok: テンプレートリテラルの中の偽マーカー`\n"
        "if (process.argv.includes('--self-test')) { selfTest() }\n"
    )
    check(
        "P2: テンプレートリテラル内の偽マーカーは拾わない",
        marker_reason(src_p2, "js") is None,
    )
    v_p2 = evaluate_script("fake_marker_template.mjs", src_p2, "")
    check("P2: violation のまま（誤って excluded されない）", v_p2.status == "violation")

    src_p3 = (
        "const msg = '// selftest-wiring-ok: シングルクォート文字列の中の偽マーカー'\n"
        "if (process.argv.includes('--self-test')) { selfTest() }\n"
    )
    check(
        "P3: シングルクォート文字列内の偽マーカーは拾わない",
        marker_reason(src_p3, "js") is None,
    )

    # ── ケース Q: ブロックコメント（`/* ... */`）内のマーカーも実コメントとして有効に効く ──
    src_q = (
        "/*\n"
        " * selftest-wiring-ok: ブロックコメント内の正当なマーカー\n"
        " */\n"
        "if (process.argv.includes('--self-test')) { selfTest() }\n"
    )
    check(
        "Q: ブロックコメント内のマーカーを拾える",
        marker_reason(src_q, "js") == "ブロックコメント内の正当なマーカー",
    )
    v_q = evaluate_script("block_marker.mjs", src_q, "")
    check("Q: ブロックコメントマーカーは excluded", v_q.status == "excluded")

    # ── ケース R: .mjs が正しく配線済み → wired ──
    src_r = "if (process.argv.includes('--self-test')) { selfTest() }\n"
    rc_r = (
        "run_check \"quux mjs\" node tools/quux.mjs\n"
        "run_check \"quux mjs self-test\" node tools/quux.mjs --self-test\n"
    )
    check("R: mjs 配線済みは is_wired=True", is_wired("quux.mjs", rc_r))
    v_r = evaluate_script("quux.mjs", src_r, rc_r)
    check("R: mjs 判定は wired", v_r.status == "wired")

    # ── ケース S: `//` の前後空白バリアント（入力バリアント展開・#992 要件 7） ──
    src_s1 = "//selftest-wiring-ok:前後空白なし\nfoo('--self-test')\n"
    check("S1: 前後空白なしのマーカーも拾える", marker_reason(src_s1, "js") == "前後空白なし")
    src_s2 = "//   selftest-wiring-ok:    余白多め   \nfoo('--self-test')\n"
    check("S2: 余白が多いマーカーも拾える", marker_reason(src_s2, "js") == "余白多め")

    # ── ケース T: 未終端の文字列・ブロックコメントは解析失敗として安全側（マーカーなし）に
    #    フォールバックする（Python の tokenize 失敗と同じ扱い） ──
    src_t_unterminated_block = (
        "/* 閉じられていないブロックコメント\n"
        "foo('--self-test')\n"
    )
    check(
        "T: 未終端ブロックコメントは解析失敗で None",
        ts_source.extract_comments(src_t_unterminated_block) is None,
    )
    v_t = evaluate_script("broken.mjs", src_t_unterminated_block, "")
    check("T: 未終端ブロックコメントは violation（安全側）", v_t.status == "violation")
    check("T: tokenize_failed フラグが立つ（mjs でも）", v_t.tokenize_failed)

    # ── ケース U（`main()` からの実到達確認・#992 完了条件の必須負ケース #710 流儀）:
    #    `SCAN_EXTENSIONS` に "mjs" が入っており、`scan()` が一時ディレクトリの `.mjs` を
    #    実際に走査対象へ含めることを確認する。`evaluate_script()` を直接呼ぶテスト（M〜T）
    #    だけでは `SCAN_EXTENSIONS` から "mjs" を削る変異を見逃す（実測: 削っても上記の
    #    ケースは全て PASS したまま）ため、`scan()` を経由する end-to-end ケースを別立てする。
    check("U: SCAN_EXTENSIONS に mjs が含まれる", "mjs" in SCAN_EXTENSIONS)
    check("U: SCAN_EXTENSIONS に mts が含まれる", "mts" in SCAN_EXTENSIONS)
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tools = Path(tmpdir)
        (tmp_tools / "unwired_gate.mjs").write_text(
            "if (process.argv.includes('--self-test')) { selfTest() }\n", encoding="utf-8"
        )
        (tmp_tools / "wired_gate.mjs").write_text(
            "if (process.argv.includes('--self-test')) { selfTest() }\n", encoding="utf-8"
        )
        rc_content = 'run_check "wired" node tools/wired_gate.mjs --self-test\n'
        report_e2e = scan(tmp_tools, rc_content)
        check(
            "U: scan() が .mjs の配線漏れを検出する（run_lighthouse.mjs 型の再発防止）",
            "unwired_gate.mjs" in report_e2e.violations,
        )
        check(
            "U: scan() が .mjs の配線済みを wired と判定する",
            "wired_gate.mjs" in report_e2e.wired,
        )

    # ── ケース V（`check-tool-design-rules.md` §4）: `main()` が返す終了コード経路
    #    （`exit_code_for()`）が violations の有無を正しく反映する ──
    report_clean = Report(wired=["a.py"])
    check("V: 配線漏れ 0 件は exit 0", exit_code_for(report_clean) == 0)
    report_violation = Report(wired=["a.py"], violations=["b.mjs"])
    check("V: 配線漏れ 1 件以上は exit 1", exit_code_for(report_violation) == 1)

    # ══════════════════════════════════════════════════════════════════
    # 以下 PR #1018 Layer 1 セルフレビュー（CONFIRMED 9 件）のフォローアップ（F1〜F8）
    # ══════════════════════════════════════════════════════════════════

    # ── ケース W（F2・境界の外側の負ケース #750）: コメント本文中に「書式を説明する地の文」が
    #    あるだけでは有効なマーカーと誤認しない（アンカー導入前は fail-open していた） ──
    src_w = (
        "// See docs/... for background on the selftest-wiring-ok: marker format used elsewhere.\n"
        "foo('--self-test')\n"
    )
    check("W: 地の文の言及はマーカーとして拾わない（アンカー導入・fail-open 再発防止）", marker_reason(src_w, "js") is None)
    v_w = evaluate_script("mention_only.mjs", src_w, "")
    check("W: 誤って excluded されず violation のまま", v_w.status == "violation")
    # 回帰防止: マーカーがコメント本文の先頭にあれば従来どおり有効（「近似だが別カテゴリ」の対）
    src_w2 = "// selftest-wiring-ok: 正しい先頭マーカー\nfoo('--self-test')\n"
    check(
        "W: 先頭マーカーは従来どおり有効（回帰防止・#750 の負ケースとの対）",
        marker_reason(src_w2, "js") == "正しい先頭マーカー",
    )

    # ── ケース X（F1・PR #1018 CRITICAL の核心）: 正規表現リテラル内部の `/*` を
    #    ブロックコメント開始と誤認せず、その直後の正当なマーカーを検出できる ──
    src_x = (
        "const SEP_RE = /[/*]/;\n"
        "// selftest-wiring-ok: 正規表現リテラルの後ろの正当なマーカー\n"
        "foo('--self-test')\n"
    )
    v_x = evaluate_script("regex_then_marker.mjs", src_x, "")
    check("X: 正規表現リテラル直後の正当なマーカーが excluded になる", v_x.status == "excluded")
    check(
        "X: マーカー理由が正しく取得できる",
        marker_reason(src_x, "js") == "正規表現リテラルの後ろの正当なマーカー",
    )
    # 同型の反例: クォート文字クラスを含む正規表現リテラルでも同様
    src_x2 = (
        "const QUOTE_RE = /['\"]/g;\n"
        "// selftest-wiring-ok: 別の正規表現リテラルの後ろの正当なマーカー\n"
        "foo('--self-test')\n"
    )
    v_x2 = evaluate_script("quote_class_then_marker.mjs", src_x2, "")
    check("X: クォート文字クラスの正規表現リテラル後も excluded になる", v_x2.status == "excluded")

    # ── ケース Y（F1・fail-open の反例）: 文字列リテラル内の偽マーカーは拾わない ──
    src_y = (
        'const RE = /^(?:https?):\\/\\//i; const msg = "selftest-wiring-ok: これはコード";\n'
        "foo('--self-test')\n"
    )
    v_y = evaluate_script("string_fake_marker.mjs", src_y, "")
    check("Y: 文字列内の偽マーカーは excluded にならない（fail-open 再発防止）", v_y.status == "violation")
    # ネストしたテンプレートリテラル（URL の `//` を含む）が破綻しないこと
    src_y2 = "const s = `outer ${`http://example.com`} end`\n// selftest-wiring-ok: ネスト後の正当なマーカー\nfoo('--self-test')\n"
    v_y2 = evaluate_script("nested_template.mjs", src_y2, "")
    check("Y: ネストしたテンプレートリテラル後も正しく excluded になる（破綻しない）", v_y2.status == "excluded")

    # ── ケース Z（F3・.sh 拡張子。case アーム形の --self-test 実装を検出する） ──
    check("Z: .sh は sh 判定", _lang_for_filename("foo.sh") == "sh")
    src_sh_case_arm = (
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        "  --self-test) echo self-test; exit 0 ;;\n"
        "esac\n"
    )
    check(
        "Z: case アーム形の --self-test を sh 判定で検出する（クォート無し・progress_heartbeat.sh 型）",
        script_has_selftest_flag(src_sh_case_arm, "sh"),
    )
    check(
        "Z: py/js 判定では case アーム形を検出しない（言語別ディスパッチ）",
        not script_has_selftest_flag(src_sh_case_arm, "py"),
    )
    v_sh_unwired = evaluate_script("case_arm.sh", src_sh_case_arm, "")
    check("Z: 未配線の .sh は violation", v_sh_unwired.status == "violation")
    rc_sh_wired = 'run_check "case arm" bash tools/case_arm.sh --self-test\n'
    v_sh_wired = evaluate_script("case_arm.sh", src_sh_case_arm, rc_sh_wired)
    check("Z: 配線済みの .sh は wired", v_sh_wired.status == "wired")

    # クォート比較形（sync_broker_drift.sh の実際の形）も検出する
    src_sh_quoted = 'if [ "${1:-}" = "--self-test" ]; then\n  echo ok\nfi\n'
    check("Z: クォート比較形も sh 判定で検出する（sync_broker_drift.sh 型）", script_has_selftest_flag(src_sh_quoted, "sh"))

    # .sh の `#` マーカー（Python と同じ書式）
    src_sh_marker = (
        "#!/usr/bin/env bash\n"
        "# selftest-wiring-ok: 週次スロットでのみ起動する運用ツール\n"
        'if [ "${1:-}" = "--self-test" ]; then exit 0; fi\n'
    )
    check(
        "Z: .sh の # マーカーの理由を取得できる",
        marker_reason(src_sh_marker, "sh") == "週次スロットでのみ起動する運用ツール",
    )
    v_sh_marker = evaluate_script("weekly.sh", src_sh_marker, "")
    check("Z: .sh マーカーは excluded", v_sh_marker.status == "excluded")

    # 自己参照の反例（run_checks.sh 自身の誤検出防止・#992 フォローアップの主眼）: 行頭に
    # アンカーされていない `--self-test)`（ドキュメントラベル文字列の一部）は検出しない
    src_sh_label_only = 'run_check "foo self-test (foo.py --self-test)" python3 tools/foo.py --self-test\n'
    check(
        "Z: 行頭でない --self-test) はラベル文字列として誤検出しない（run_checks.sh 自己参照防止）",
        not script_has_selftest_flag(src_sh_label_only, "sh"),
    )
    # 実際の run_checks.sh 自身で実測する（「.sh の対象実体が無い」という事実誤認の反省を
    # 踏まえ、合成ケースだけでなく実ファイルでも自己参照が起きないことを確認する）
    if RUN_CHECKS_PATH.exists():
        real_run_checks_content = RUN_CHECKS_PATH.read_text(encoding="utf-8")
        check(
            "Z: 実際の run_checks.sh 自身は has_selftest_flag=False（自己参照回避を実測）",
            not script_has_selftest_flag(real_run_checks_content, "sh"),
        )

    # ── ケース AA（F4・サブディレクトリの再帰走査。#992 フォローアップ） ──
    with tempfile.TemporaryDirectory() as tmpdir2:
        tmp_tools2 = Path(tmpdir2)
        subdir = tmp_tools2 / "gem-pool"
        subdir.mkdir()
        (subdir / "nested_unwired.mjs").write_text(
            "if (process.argv.includes('--self-test')) { selfTest() }\n", encoding="utf-8"
        )
        (subdir / "nested_wired.mjs").write_text(
            "if (process.argv.includes('--self-test')) { selfTest() }\n", encoding="utf-8"
        )
        rc_nested = 'run_check "nested wired" node tools/gem-pool/nested_wired.mjs --self-test\n'
        report_nested = scan(tmp_tools2, rc_nested)
        check(
            "AA: サブディレクトリの未配線 .mjs を検出する（rglob 化前は不可視だった）",
            "gem-pool/nested_unwired.mjs" in report_nested.violations,
        )
        check(
            "AA: サブディレクトリの配線済み .mjs を wired と判定する",
            "gem-pool/nested_wired.mjs" in report_nested.wired,
        )

    # ── ケース BB（F6・引用符付きパスの配線検出） ──
    rc_quoted_path = 'run_check "quoted" node "$REPO_ROOT/tools/quux.mjs" --self-test\n'
    check("BB: 引用符付きパス（node \"$REPO_ROOT/tools/foo.mjs\"）でも is_wired=True", is_wired("quux.mjs", rc_quoted_path))
    # 回帰防止: 従来のクォート無しの形も引き続き検出する
    rc_unquoted_path = 'run_check "unquoted" node tools/quux.mjs --self-test\n'
    check("BB: クォート無しパスも引き続き is_wired=True（回帰防止）", is_wired("quux.mjs", rc_unquoted_path))

    # ── ケース CC（F5・#686: main() の本番経路（sys.exit(main()) まで）を実プロセスとして
    #    実測する。判定関数だけを直接呼ぶテスト（A〜BB）では `main()` 内部の配線ミス
    #    （例: `return exit_code_for(report)` を `return 0` に変異する）を見逃す） ──
    import shutil
    import subprocess

    _fake_ts_source_src = (
        "# CC 用の最小フェイク（実 ts_source.py の --self-test 実装を巻き込まないための代替）\n"
        "def extract_comments(source):\n"
        "    return []\n"
    )

    def _run_main_subprocess(tools_files: dict[str, str], run_checks_content: str) -> int:
        this_file = Path(__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            tmp_tools = tmp_root / "tools"
            tmp_tools.mkdir()
            shutil.copy(this_file, tmp_tools / this_file.name)
            # 本ファイルは wiring_marker（#933）を import するため、実プロセス実行には
            # 実物を同梱する必要がある（ts_source.py はフェイクで代替するが、
            # wiring_marker.py 自体の判定ロジックは変異検出対象にしたいので実物を使う）。
            shutil.copy(
                Path(__file__).resolve().parent / "wiring_marker.py",
                tmp_tools / "wiring_marker.py",
            )
            (tmp_tools / "ts_source.py").write_text(_fake_ts_source_src, encoding="utf-8")
            (tmp_tools / "run_checks.sh").write_text(run_checks_content, encoding="utf-8")
            for name, content in tools_files.items():
                target = tmp_tools / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(tmp_tools / this_file.name)],
                cwd=str(tmp_tools),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode

    rc_main_violation = _run_main_subprocess(
        {"gate.mjs": "if (process.argv.includes('--self-test')) { selfTest() }\n"},
        "",
    )
    check("CC: main() 実プロセス実行（違反あり）は exit 1（#686 本番経路の実測）", rc_main_violation == 1)

    rc_main_clean = _run_main_subprocess(
        {"gate.mjs": "if (process.argv.includes('--self-test')) { selfTest() }\n"},
        # 実物の wiring_marker.py（`--self-test` 実装済み）も同梱するため、こちらも配線して
        # おかないと「wiring_marker.py 自身の配線漏れ」で汚染され exit 1 になってしまう。
        'run_check "gate" node tools/gate.mjs --self-test\n'
        'run_check "wiring_marker" python3 tools/wiring_marker.py --self-test\n',
    )
    check("CC: main() 実プロセス実行（違反なし）は exit 0（#686 本番経路の実測）", rc_main_clean == 0)

    # ── ケース DD（干渉検証・独立した複数修正が同一走査で互いの前提を壊さないことの確認） ──
    with tempfile.TemporaryDirectory() as tmpdir3:
        tmp_tools3 = Path(tmpdir3)
        (tmp_tools3 / "gate.mjs").write_text(
            "const SEP_RE = /[/*]/;\n"
            "// selftest-wiring-ok: 干渉検証用の js マーカー\n"
            "foo('--self-test')\n",
            encoding="utf-8",
        )
        (tmp_tools3 / "gate.sh").write_text(
            "#!/usr/bin/env bash\n"
            'case "$1" in\n'
            "  --self-test) exit 0 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        sub3 = tmp_tools3 / "nested"
        sub3.mkdir()
        (sub3 / "gate2.mjs").write_text(
            "if (process.argv.includes('--self-test')) { selfTest() }\n", encoding="utf-8"
        )
        rc3 = 'run_check "nested" node tools/nested/gate2.mjs --self-test\n'
        report3 = scan(tmp_tools3, rc3)
        check(
            "DD: 干渉検証 - F1/F2（js の正規表現リテラル + アンカー済みマーカー）は excluded のまま",
            ("gate.mjs", "干渉検証用の js マーカー") in report3.excluded,
        )
        check(
            "DD: 干渉検証 - F3（.sh の case アーム形）は F1/F2 の js 判定を巻き込まず violation として検出される",
            "gate.sh" in report3.violations,
        )
        check(
            "DD: 干渉検証 - F4（サブディレクトリ再帰）が F6 の相対パス識別子と両立して wired と判定される",
            "nested/gate2.mjs" in report3.wired,
        )

    if failures:
        print("❌ check_selftest_wiring --self-test FAILED:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print(f"✅ check_selftest_wiring --self-test PASSED（{assertions} 件のアサーション全て成功）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="機械可読 JSON で出力する")
    # selftest-wiring-ok: 本検査自身のユニットテスト起動フラグであり、run_checks.sh への配線判断は
    # 親セッション側に委ねる（新規作成スクリプトの自己参照ブートストラップ問題・上記 _SELF_FILENAME 参照）
    parser.add_argument("--self-test", action="store_true", help="検出ロジック自体のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    if not RUN_CHECKS_PATH.exists():
        print(f"⚠️  {RUN_CHECKS_PATH} が見つかりません（判定不能）", file=sys.stderr)
        return 2
    run_checks_content = RUN_CHECKS_PATH.read_text(encoding="utf-8")

    report = scan(TOOLS_DIR, run_checks_content)

    if args.json:
        print(render_json(report))
    else:
        print(render_human(report))

    return exit_code_for(report)


if __name__ == "__main__":
    sys.exit(main())
