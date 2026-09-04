#!/usr/bin/env python3
"""check_selftest_wiring.py — tools/*.py の `--self-test` 配線漏れを検査する（Issue #612）。

## なぜ必要か

`tools/` の検査スクリプトの多くは `--self-test`（ネットワーク・実データ非依存のユニットテスト）を
持ち、`tools/run_checks.sh` から実行される。ところが実際に調べたところ、`check_ui_dimensions.py`
`check_prefetchable_side_effects.py` の 2 本が実装されているのに `run_checks.sh` へ配線されておらず、
この間に偽陽性バグが self-test なしで潜伏していた（Issue #612）。

配線漏れは「テストを書いたのに実行されない」状態で、**検査があるのに機能していない**という
最も見つけにくい失敗モードである。本スクリプトはこの再発を止める。

🔁 `check_tool_wiring.py`（本判定の配線漏れ＝死蔵の検査）と対になる検査である。
**片方の判定ロジックを直したら、もう片方も同じ欠陥を持っていないか見ること。**

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

理由が空（`# selftest-wiring-ok:` だけ）のマーカーは無効として扱い、除外しない
（「除外してよいか」を人が判断した形跡を残させることが目的であり、マーカーの存在だけでは
通さない。`check_duplicate_source_patterns.py` の `dup-ok` マーカーと同じ思想）。

## 誤判定の防止（2026-08-24 の敵対的レビューで発見された 2 つの穴）

本検査自身が「配線されていないのに PASS する」誤判定を起こしうる 2 つの穴が見つかったため、
以下のとおり修正している。

1. **`run_checks.sh` 側のコメントアウトされた `run_check` 行を「配線済み」と誤認する**:
   `is_wired()` は生テキストの正規表現検索だったため、`# run_check "..." python3 tools/foo.py
   --self-test` のようにシェルコメントとして無効化された行も一致してしまい、実際には一度も
   実行されないスクリプトを「配線済み」と報告していた。対策として、`is_wired()` は検索前に
   `_strip_shell_comments()`（クォート外の `#` 以降を除去する簡易 bash コメント除去。シングル
   / ダブルクォートの状態を追跡し、クォート内の `#`（例: `echo "## run_checks 結果"`）は保持
   する）を通す。ヒアドキュメント（`<<EOF`）は `run_checks.sh` に存在しないため未対応（将来
   追加されたら本関数も見直しが必要）。

2. **対象スクリプト側の docstring 内でマーカー書式を「説明する地の文」を、本物のマーカーと
   誤認して除外してしまう**: 旧実装は `_MARKER_RE` をファイル内容全体に対して素朴な正規表現
   検索していたため、docstring の中で「`# selftest-wiring-ok: 理由` と書く」と地の文で説明した
   だけの文字列（実コメントではない）にもマッチし、意図せず自己除外されてしまっていた（本検査自身の
   docstring がまさにこの形を取っているため、他スクリプトが利用例として書式に言及するだけで
   誤除外されうるという皮肉な穴だった）。対策として、`marker_reason()` /
   `has_invalid_empty_marker()` は `tokenize` モジュールで実コメントトークン（`tokenize.COMMENT`）
   だけを抽出してからマーカーを探す（`_comment_texts()`）。**構文エラー等でトークナイズ自体が
   失敗した場合はクラッシュせず、安全側＝「マーカーなし」として扱う**（誤って除外されるより、
   誤って違反扱いされる方が安全 — 除外は人が明示的にマーカーを書かない限り成立しないため）。
   この場合は `scan()` が stderr に警告を出す（`Verdict.tokenize_failed`）。

使い方:
    python3 tools/check_selftest_wiring.py              # 配線漏れ検査（人間可読レポート）
    python3 tools/check_selftest_wiring.py --json        # 機械可読 JSON
    python3 tools/check_selftest_wiring.py --self-test   # 検出ロジック自体のユニットテスト

終了コード: 0 = 配線漏れなし / 1 = 配線漏れあり（または --self-test 失敗）
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
RUN_CHECKS_PATH = TOOLS_DIR / "run_checks.sh"

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

# `# selftest-wiring-ok: {理由}` マーカー。理由は同じ行の行末までとする（`\s*` は改行にも
# マッチするため `[ \t]*` を使う。`\s*` のままだと理由が空のとき次行を誤って呑み込む）。
_MARKER_RE = re.compile(r"#[ \t]*selftest-wiring-ok:[ \t]*(.*)$", re.MULTILINE)


def script_has_selftest_flag(content: str) -> bool:
    """スクリプトが `--self-test` オプションを実装しているか（クォート付きリテラルの有無）。

    `--shim-self-test` のような別名フラグ（例: `gh_shim.py`）は「--self-test」という
    文字列そのものと一致しないため誤検出しない。
    """
    return bool(_SELFTEST_FLAG_RE.search(content))


@dataclass
class _MarkerScan:
    """1 ファイルぶんのマーカー走査結果（`_scan_markers` の戻り値）。"""

    reasons: list[str]  # 実コメントとして書かれた、理由が非空のマーカーの理由文字列（出現順）
    has_empty: bool  # 理由が空の（無効な）マーカーが 1 つでもあったか
    tokenize_failed: bool  # `tokenize` が失敗し、安全側で「マーカーなし」にフォールバックしたか


def _comment_texts(content: str) -> list[str] | None:
    """`content` を Python としてトークナイズし、実コメントトークンの文字列だけを返す。

    docstring / 文字列リテラルの中身（マーカー書式を説明する地の文など）はコメントトークン
    ではないため含まれない。構文エラー・NUL バイト混入等でトークナイズ自体が失敗した場合は
    クラッシュせず `None` を返す（呼び出し側は「マーカーなし」として安全側に倒す）。
    """
    try:
        return [
            tok.string
            for tok in tokenize.generate_tokens(io.StringIO(content).readline)
            if tok.type == tokenize.COMMENT
        ]
    except Exception:
        # tokenize は SyntaxError / IndentationError / tokenize.TokenError / ValueError など
        # 様々な例外を送出しうる（壊れた入力の形によって変わる）。本検査は「配線漏れ検出」が
        # 責務であり構文検証ではないため、どんな理由であれクラッシュしてはならない
        # （datetime-rules.md の check_datetime_tz.py と同じ「解析不能はスキップする」方針）。
        return None


def _scan_markers(content: str) -> _MarkerScan:
    """`content` の実コメントから `selftest-wiring-ok` マーカーを走査する。"""
    comments = _comment_texts(content)
    if comments is None:
        return _MarkerScan(reasons=[], has_empty=False, tokenize_failed=True)
    reasons: list[str] = []
    has_empty = False
    for comment in comments:
        m = _MARKER_RE.search(comment)
        if not m:
            continue
        reason = m.group(1).strip()
        if reason:
            reasons.append(reason)
        else:
            has_empty = True
    return _MarkerScan(reasons=reasons, has_empty=has_empty, tokenize_failed=False)


def marker_reason(content: str) -> str | None:
    """有効な `selftest-wiring-ok` マーカー（実コメントとして書かれたもの）の理由文字列を返す。

    マーカーが無い、全てのマーカーの理由が空（無効マーカー）、またはトークナイズ自体が
    失敗した場合は None を返す（= 除外されない・安全側）。複数マーカーがあり、どれか 1 つでも
    理由が非空なら、その理由を返す。
    """
    reasons = _scan_markers(content).reasons
    return reasons[0] if reasons else None


def has_invalid_empty_marker(content: str) -> bool:
    """理由が空の `selftest-wiring-ok` マーカーが（有効な理由付きマーカーとは別に）存在するか。"""
    return _scan_markers(content).has_empty


def _strip_shell_line_comment(line: str) -> str:
    """bash の 1 行から、クォート外の `#` 以降（シェルコメント）を取り除く。

    シングルクォート `'...'` とダブルクォート `"..."` の中身は保持する（例:
    `echo "## run_checks 結果"` の `#` はコメントとして解釈しない）。`#` は「行頭、または
    直前が空白」のときだけコメント開始とみなす（`foo#bar` のような識別子中の `#` は無視する
    簡易ヒューリスティックだが、`run_checks.sh` の実際の書き方には十分）。
    """
    quote: str | None = None
    prev: str | None = None
    out: list[str] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if quote:
            out.append(ch)
            if quote == '"' and ch == "\\" and i + 1 < n:
                out.append(line[i + 1])
                prev = line[i + 1]
                i += 2
                continue
            if ch == quote:
                quote = None
            prev = ch
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            prev = ch
            i += 1
            continue
        if ch == "#" and (prev is None or prev in " \t"):
            break
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out)


def _strip_shell_comments(content: str) -> str:
    """bash スクリプト全体からシェルコメントを取り除く（行単位。ヒアドキュメント非対応）。"""
    out: list[str] = []
    for raw_line in content.splitlines(keepends=True):
        if raw_line.endswith("\n"):
            body, eol = raw_line[:-1], "\n"
        else:
            body, eol = raw_line, ""
        out.append(_strip_shell_line_comment(body) + eol)
    return "".join(out)


def is_wired(filename: str, run_checks_content: str) -> bool:
    """`run_checks.sh` の中に `<filename> ... --self-test` という **有効な**（コメントアウト
    されていない）呼び出しがあるか。"""
    stripped = _strip_shell_comments(run_checks_content)
    pattern = re.compile(re.escape(filename) + r"\s+--self-test\b")
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
    """1 ファイルぶんの内容から配線状態を判定する（テスト容易性のための純関数）。"""
    if not script_has_selftest_flag(content):
        return Verdict(filename, "not_applicable")

    marker_scan = _scan_markers(content)
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
    report = Report()
    for path in sorted(tools_dir.glob("*.py")):
        if path.name == _SELF_FILENAME:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"⚠️  読み込み失敗のためスキップ: {path.name}（{e}）", file=sys.stderr)
            continue
        verdict = evaluate_script(path.name, content, run_checks_content)
        if verdict.tokenize_failed:
            print(
                f"⚠️  tokenize 失敗のためマーカーなし扱い（安全側）: {path.name}"
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

    return 1 if report.violations else 0


if __name__ == "__main__":
    sys.exit(main())
