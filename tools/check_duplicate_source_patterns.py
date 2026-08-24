#!/usr/bin/env python3
"""check_duplicate_source_patterns.py — 同一の正規表現リテラルが複数ファイルにコピーされて
いないかを検査する（Issue #612）。

【なぜ必要か】
同じ意味の正規表現が複数ファイルに独立にコピーされ、そのたびに人手レビューで指摘されている。
実例（Issue #612）: `owner/repo` 形式の判定に使う正規表現
`/^[^/\\s]+\\/[^/\\s]+$/` が `src/infrastructure/platform/static-gem-index.ts:84` /
`static-gem-digest.ts:64` / `src/ui/gem-list.tsx:303` の 3 ファイルに独立にコピーされていた。
このうち `static-gem-digest.ts` 側だけ「なぜこの形で複製したか」の理由がコードに残っておらず、
レビューでの指摘対象になった。

【重要な前提: 重複のすべてが悪いわけではない】
正規表現の重複には、**前提・信頼境界が異なるために意図的に分けているもの**が含まれる。
例えば `src/usecases/search-gems.ts` の `INCLUDE_FULL_NAME_PATTERN` は、上記 `owner/repo`
判定とよく似た見た目だが「URL 由来の利用者入力に対する防御」という別の脅威モデルを持つため、
本検査は **これを別パターンとして扱い、意図的な分離を壊さない**（正規表現の内容そのものが
1 文字でも違えば別パターンとして扱う。読み替え・意味の近さまでは判定しない）。

問題は「意図的な分離」と「ただのコピー」が **コード上で区別できない**ことにある。本検査は
その区別を **`dup-ok` マーカーの記載** という形でコードに残すことを強制する。

【dup-ok マーカーの書式と運用方針】
同一の正規表現が 2 ファイル以上に出現した場合、**出現箇所すべて**（同一ファイル内の複数箇所を
含む）に、その正規表現リテラルと **同じ行、または直前の行**に理由付きマーカーを書く:

    TypeScript / TSX: `// dup-ok: {理由}`
    Python           : `# dup-ok: {理由}`

理由が空（`// dup-ok:` だけ）のマーカーは無効として扱う（「なぜ複製したか」を書かせることが
目的であり、マーカーの存在だけでは通さない）。

**一部の出現箇所にしかマーカーが無い場合は違反として検出する**（`static-gem-digest.ts` に
理由が書かれていなかった実例に対応する。「片方は事情を書いたが、もう片方は書き忘れた」状態を
そのまま放置しない）。

【最小長の閾値・誤検知を避けるための根拠】
`/\\s+/` `/\\d+/` `/\\n/` のような極めて汎用的な正規表現は、たまたま同じ文字列になるだけで
「意味のあるコピー」ではない。実際に本リポジトリの `src/**/*.ts(x)` `app/**/*.ts(x)` /
`tools/**/*.py` を走査して実測したところ、**実在する重複はすべてパターン本体 10 文字以上**
（最短は Python 側の `^SP-(\\d+):` で 10 文字）だった一方、単一ファイル内にしか出現しない
汎用パターン（`\\s+` `\\d+` `.*?` `-` `_` 等）はいずれも 8 文字未満だった。この実測結果から、
**パターン本体（TS は正規表現リテラルの `/.../ ` を除いた中身、Python は文字列リテラルの値）
が 8 文字未満のものは検査対象から除外する**（`_MIN_PATTERN_LENGTH`）。閾値未満のものは
「同じ形になったのは偶然」とみなし、`dup-ok` マーカーの記載も要求しない。

【対象ファイルと言語ごとの抽出方式】
  - `src/**/*.ts` `src/**/*.tsx` `app/**/*.ts` `app/**/*.tsx`（`.test.` `.spec.` を含む
    ファイル名は除外）: JS/TS の正規表現リテラル `/pattern/flags` を対象とする。除算演算子
    `/` との曖昧さは、直前の意味のあるトークンが「値」（識別子・数値・文字列・`)` `]`）で
    あれば除算、そうでなければ正規表現リテラルの開始とみなす簡易ヒューリスティックで判定する
    （完全な字句解析ではないが、本リポジトリの実ファイル全件で正しく動作することを確認済み）。
    コメント・文字列リテラル内の `/.../ ` らしき文字列を誤検出しないよう、走査前に
    `tools/ts_source.py` の `strip_comments`（共通実装・Issue #612）でコメントを除去し、
    文字列・テンプレートリテラルの中身はスキャナ自身がスキップする。
  - `tools/**/*.py`: Python には正規表現リテラル構文が無く、`re.compile(...)` 等の呼び出しに
    文字列を渡す形でしか書けない。そのため `ast` モジュールでソースを構文解析し、
    `re.compile` / `re.match` / `re.fullmatch` / `re.search` / `re.sub` / `re.subn` /
    `re.split` / `re.findall` / `re.finditer` の呼び出しで、第 1 引数が文字列リテラルである
    ものを正規表現として抽出する（`ast` を使うため、コメント除去を自前実装する必要がない。
    文字列の値そのもの＝ `ast.Constant.value` を同一性の判定に使うため、`r"\\d+"` と `"\\d+"`
    のような prefix の違いは正しく同一パターンとして扱われる）。

【既定は Warning・`--strict` のみ exit 1】
現状のコードベースには未対応の重複（`dup-ok` マーカー未挿入）が実在する（下記の実測結果を
`--self-test` 以外の実行で確認できる）。マーカーの挿入は本スクリプトの責務ではなく、検出結果を
見た人（またはレビュー対応する別セッション）が個別に判断して挿入する。そのため既定では検出結果を
Warning として報告するだけで exit 0 とし、マーカー挿入が完了して「新規の無許可重複を二度と
作らせない」フェーズに入ったら `--strict` を `tools/run_checks.sh` に配線して exit 1 化する
（配線自体は本スクリプトの担当外）。

使い方:
    python3 tools/check_duplicate_source_patterns.py            # 検出のみ（Warning・常に exit 0）
    python3 tools/check_duplicate_source_patterns.py --strict    # 未許可の重複があれば exit 1
    python3 tools/check_duplicate_source_patterns.py --self-test # ネットワーク・実ファイル不要のユニットテスト
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ts_source import JS_IDENTIFIER_RE, strip_comments  # 共通モジュール（#612）。フォールバックは持たない


EXIT_OK = 0
EXIT_VIOLATION = 1

# 実測結果に基づく閾値（根拠はモジュール docstring 参照）。
_MIN_PATTERN_LENGTH = 8

_TS_ROOTS = ("src", "app")
_TS_SUFFIXES = (".ts", ".tsx")
_PY_ROOT = "tools"
_PY_SUFFIX = ".py"

_DUP_OK_TS_RE = re.compile(r"//\s*dup-ok:\s*(.*)$")
_DUP_OK_PY_RE = re.compile(r"#\s*dup-ok:\s*(.*)$")


@dataclass(frozen=True)
class Occurrence:
    """1 つの正規表現リテラル出現箇所。"""

    file: str
    line: int
    pattern: str  # 同一性判定に使うキー（TS: `/body/flags` の全体。Python: 文字列の値）
    body_length: int  # 閾値判定に使う「パターン本体」の長さ
    marked: bool
    reason: str | None


# ---------------------------------------------------------------------------
# TypeScript / TSX 側: 正規表現リテラルの抽出
# ---------------------------------------------------------------------------

_IDENT_RE = JS_IDENTIFIER_RE  # 共通定数（ts_source）。同じパターンの再定義を避ける（#612）

# これらの識別子の直後に来る `/` は「式の開始」＝正規表現リテラルの可能性が高い
# （除算ではありえない）。それ以外の識別子（変数名・`true`/`this` 等）は「値」として
# 扱い、直後の `/` を除算演算子とみなす。
_KEYWORDS_EXPR_START = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw",
    "case", "do", "else", "yield", "await", "if", "while", "for", "switch", "extends",
    "default", "export", "const", "let", "var", "function", "class", "import", "from",
    "async", "static", "get", "set", "catch", "finally", "try", "break", "continue",
}


def iter_ts_regex_literals(stripped_source: str) -> list[tuple[str, int]]:
    """コメント除去済みの TS/TSX ソースから正規表現リテラルを抽出する。

    `(リテラル全文, 開始オフセット)` のリストを返す。除算演算子との曖昧さは、直前の
    意味のあるトークンが「値」（識別子・数値・文字列・`)` `]`）かどうかで判定する簡易
    ヒューリスティック（`_KEYWORDS_EXPR_START` にない識別子の直後は除算とみなす）。
    文字列・テンプレートリテラルの中身はスキップし、その中の `/.../ ` を誤検出しない。
    """
    results: list[tuple[str, int]] = []
    i, n = 0, len(stripped_source)
    last_value = False  # 直前の意味のあるトークンが「値」（除算文脈）かどうか
    while i < n:
        ch = stripped_source[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            j = i + 1
            while j < n:
                if stripped_source[j] == "\\":
                    j += 2
                    continue
                if stripped_source[j] == quote:
                    j += 1
                    break
                j += 1
            else:
                j = n
            i = j
            last_value = True
            continue
        if ch.isdigit():
            j = i
            while j < n and (stripped_source[j].isalnum() or stripped_source[j] in "._"):
                j += 1
            i = j
            last_value = True
            continue
        m = _IDENT_RE.match(stripped_source, i)
        if m:
            word = m.group(0)
            i = m.end()
            last_value = word not in _KEYWORDS_EXPR_START
            continue
        if ch == "/":
            if last_value:
                # 除算演算子（例: `a / b`）
                i += 1
                last_value = False
                continue
            # 正規表現リテラルとしてパースを試みる
            j = i + 1
            in_class = False
            ok = False
            while j < n:
                c = stripped_source[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "\n":
                    break  # 改行を跨ぐ正規表現リテラルは存在しない → 不正な入力として諦める
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    ok = True
                    j += 1
                    break
                j += 1
            if ok:
                k = j
                while k < n and stripped_source[k].isalpha():
                    k += 1
                literal = stripped_source[i:k]
                results.append((literal, i))
                i = k
                last_value = True
                continue
            # 対応する終端 `/` が見つからない → 正規表現ではなく除算とみなして 1 文字進める
            i += 1
            last_value = False
            continue
        if ch in ")]":
            i += 1
            last_value = True
            continue
        i += 1
        last_value = False
    return results


def _ts_pattern_body_length(literal: str) -> int:
    """`/body/flags` からフラグと区切りの `/` を除いた本体の長さを返す。"""
    last_slash = literal.rfind("/")
    body = literal[1:last_slash] if last_slash > 0 else literal
    return len(body)


def _marker_lines_ts(original_lines: list[str], line_no: int) -> str | None:
    """`line_no`（1-indexed）の行、または直前の行に `dup-ok` マーカーがあれば理由を返す。"""
    for idx in (line_no - 1, line_no - 2):  # 同じ行 → 直前の行の順に見る
        if 0 <= idx < len(original_lines):
            m = _DUP_OK_TS_RE.search(original_lines[idx])
            if m:
                reason = m.group(1).strip()
                if reason:
                    return reason
    return None


def extract_ts_occurrences(path: str, source: str) -> list[Occurrence]:
    """1 つの TS/TSX ファイルから `Occurrence` のリストを抽出する。"""
    stripped = strip_comments(source)
    original_lines = source.splitlines()
    occurrences: list[Occurrence] = []
    for literal, offset in iter_ts_regex_literals(stripped):
        line_no = stripped.count("\n", 0, offset) + 1
        reason = _marker_lines_ts(original_lines, line_no)
        occurrences.append(
            Occurrence(
                file=path,
                line=line_no,
                pattern=literal,
                body_length=_ts_pattern_body_length(literal),
                marked=reason is not None,
                reason=reason,
            )
        )
    return occurrences


# ---------------------------------------------------------------------------
# Python 側: `re.*` 呼び出しの文字列リテラル引数を抽出
# ---------------------------------------------------------------------------

_RE_CALL_METHODS = {
    "compile", "match", "fullmatch", "search", "sub", "subn", "split", "findall", "finditer",
}
_RE_MODULE_NAMES = {"re", "regex"}


def _marker_line_py(original_lines: list[str], line_no: int) -> str | None:
    """`line_no`（1-indexed）の行、または直前の行に `dup-ok` マーカーがあれば理由を返す。"""
    for idx in (line_no - 1, line_no - 2):
        if 0 <= idx < len(original_lines):
            m = _DUP_OK_PY_RE.search(original_lines[idx])
            if m:
                reason = m.group(1).strip()
                if reason:
                    return reason
    return None


def extract_py_occurrences(path: str, source: str) -> list[Occurrence]:
    """1 つの Python ファイルから `re.*` 呼び出しの正規表現文字列を `Occurrence` として抽出する。

    構文解析できないファイル（構文エラー等）は空リストを返す（本検査はベストエフォートの
    重複検出であり、構文エラー検出は別の検査の責務）。
    """
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError):
        return []
    original_lines = source.splitlines()
    occurrences: list[Occurrence] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _RE_CALL_METHODS:
            continue
        if not isinstance(func.value, ast.Name) or func.value.id not in _RE_MODULE_NAMES:
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)):
            continue
        pattern = first_arg.value
        line_no = first_arg.lineno
        reason = _marker_line_py(original_lines, line_no)
        occurrences.append(
            Occurrence(
                file=path,
                line=line_no,
                pattern=pattern,
                body_length=len(pattern),
                marked=reason is not None,
                reason=reason,
            )
        )
    return occurrences


# ---------------------------------------------------------------------------
# 重複判定（言語共通）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DuplicateGroup:
    """2 ファイル以上に出現した、同一の正規表現パターン。"""

    pattern: str
    occurrences: tuple[Occurrence, ...]

    @property
    def fully_marked(self) -> bool:
        """出現箇所すべてに理由付きマーカーがあるか（= 許可された重複か）。"""
        return all(occ.marked for occ in self.occurrences)

    @property
    def file_count(self) -> int:
        return len({occ.file for occ in self.occurrences})


def find_duplicate_groups(
    occurrences: list[Occurrence], min_pattern_length: int = _MIN_PATTERN_LENGTH
) -> list[DuplicateGroup]:
    """出現箇所のリストから、2 ファイル以上にまたがる重複グループを抽出する。

    - パターン本体が `min_pattern_length` 未満のものは対象外（誤検知になりやすい汎用パターン）。
    - 同一ファイル内にしか出現しないパターンは対象外（ファイル間の重複が対象）。
    - `fully_marked` が False のグループ（＝ 1 箇所でも無許可の出現がある）が違反。
    """
    by_pattern: dict[str, list[Occurrence]] = {}
    for occ in occurrences:
        if occ.body_length < min_pattern_length:
            continue
        by_pattern.setdefault(occ.pattern, []).append(occ)

    groups: list[DuplicateGroup] = []
    for pattern, occs in by_pattern.items():
        file_count = len({occ.file for occ in occs})
        if file_count < 2:
            continue
        groups.append(DuplicateGroup(pattern=pattern, occurrences=tuple(occs)))
    return groups


# ---------------------------------------------------------------------------
# ファイル走査（本番実行のみ。self-test では使わない）
# ---------------------------------------------------------------------------


def _is_test_file(path: Path) -> bool:
    name = path.name
    return ".test." in name or ".spec." in name


def _iter_ts_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in _TS_ROOTS:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for suffix in _TS_SUFFIXES:
            for p in root.rglob(f"*{suffix}"):
                if not _is_test_file(p):
                    files.append(p)
    return sorted(set(files))


def _iter_py_files(repo_root: Path) -> list[Path]:
    root = repo_root / _PY_ROOT
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.rglob(f"*{_PY_SUFFIX}") if "__pycache__" not in p.parts
    )


def collect_occurrences(repo_root: Path) -> list[Occurrence]:
    occurrences: list[Occurrence] = []
    for p in _iter_ts_files(repo_root):
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(p.relative_to(repo_root))
        occurrences.extend(extract_ts_occurrences(rel, source))
    for p in _iter_py_files(repo_root):
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(p.relative_to(repo_root))
        occurrences.extend(extract_py_occurrences(rel, source))
    return occurrences


# ---------------------------------------------------------------------------
# 報告
# ---------------------------------------------------------------------------


def format_report(groups: list[DuplicateGroup]) -> str:
    unresolved = [g for g in groups if not g.fully_marked]
    resolved = [g for g in groups if g.fully_marked]
    lines: list[str] = []
    lines.append(
        f"[duplicate-source-patterns] 重複検出: 全 {len(groups)} 件"
        f"（未許可 {len(unresolved)} 件 / dup-ok 記載済み {len(resolved)} 件）"
    )
    for group in sorted(unresolved, key=lambda g: (-g.file_count, g.pattern)):
        lines.append(f"  ❌ 未許可の重複: {group.pattern!r}（{group.file_count} ファイル）")
        for occ in sorted(group.occurrences, key=lambda o: (o.file, o.line)):
            mark = f"dup-ok あり: {occ.reason!r}" if occ.marked else "dup-ok なし ← ここにマーカーが必要"
            lines.append(f"      {occ.file}:{occ.line}  {mark}")
    if resolved:
        lines.append(f"  ✅ dup-ok 記載済み（許可された意図的重複）: {len(resolved)} 件")
        for group in sorted(resolved, key=lambda g: g.pattern):
            lines.append(f"      {group.pattern!r}（{group.file_count} ファイル）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:
    failures: list[str] = []
    check_count = 0

    def check(label: str, got, want) -> None:
        nonlocal check_count
        check_count += 1
        if got != want:
            failures.append(f"  {label}: want {want!r}, got {got!r}")

    # ---------------- TS: 正規表現リテラルの抽出 ----------------

    # 基本ケース: 正規表現リテラルを 1 つ抽出できる
    lits = iter_ts_regex_literals(strip_comments("const RE = /^[A-Za-z0-9._-]{9,}$/g;\n"))
    check("iter_ts_regex_literals/basic_count", len(lits), 1)
    if lits:
        check("iter_ts_regex_literals/basic_literal", lits[0][0], "/^[A-Za-z0-9._-]{9,}$/g")

    # 偽陽性の反例: 文字列リテラル内の `/.../ ` らしき文字列を拾わない
    lits_str = iter_ts_regex_literals(
        strip_comments('const s = "not/a/regex/literal/at/all";\n')
    )
    check("iter_ts_regex_literals/string_literal_not_matched", len(lits_str), 0)

    # 偽陽性の反例: コメント内の `/.../ ` らしき文字列を拾わない（strip_comments 前提）
    lits_comment = iter_ts_regex_literals(
        strip_comments("// see /^[A-Za-z0-9._-]{9,}$/g for details\nconst x = 1;\n")
    )
    check("iter_ts_regex_literals/comment_not_matched", len(lits_comment), 0)

    # 除算演算子と正規表現リテラルの曖昧さ: `a / b / c` は除算 2 回であり正規表現ではない
    lits_div = iter_ts_regex_literals(strip_comments("const total = width / height / 2;\n"))
    check("iter_ts_regex_literals/division_not_matched", len(lits_div), 0)

    # 除算のあとに正規表現が続くケース（値の直後は除算、`return` の直後は正規表現）
    lits_mixed = iter_ts_regex_literals(
        strip_comments("const ratio = a / b;\nfunction f() { return /^[A-Za-z0-9._-]{9,}$/.test(s); }\n")
    )
    check("iter_ts_regex_literals/mixed_division_then_regex_count", len(lits_mixed), 1)
    if lits_mixed:
        check(
            "iter_ts_regex_literals/mixed_division_then_regex_literal",
            lits_mixed[0][0],
            "/^[A-Za-z0-9._-]{9,}$/",
        )

    # ---------------- 反例（今回の設計要件）: 検出すべきなのに見落とさないこと ----------------

    # 必須ケース 1: 2 ファイルに同じ正規表現があり、片方にしか dup-ok が無い → 検出する
    file_a = (
        "export const OWNER_REPO_RE = /^[^/\\s]+\\/[^/\\s]+$/;\n"  # マーカー無し
    )
    file_b = (
        "// dup-ok: 別モジュールで同じ形式検証を独立に持つ（Issue #612）\n"
        "export const isFullName = (s: string) => /^[^/\\s]+\\/[^/\\s]+$/.test(s);\n"
    )
    occs_partial = extract_ts_occurrences("a.ts", file_a) + extract_ts_occurrences("b.ts", file_b)
    groups_partial = find_duplicate_groups(occs_partial)
    check("partial_marker/group_count", len(groups_partial), 1)
    if groups_partial:
        check("partial_marker/fully_marked_is_false", groups_partial[0].fully_marked, False)
        marked_flags = sorted(occ.marked for occ in groups_partial[0].occurrences)
        check("partial_marker/one_marked_one_not", marked_flags, [False, True])

    # 必須ケース 2: 2 ファイルに同じ正規表現があり、両方に理由付き dup-ok がある → 検出しない
    # （＝ グループとしては見つかるが fully_marked=True になる。ここでは「未許可の重複」に
    #   数えられないことを確認する）
    file_c = (
        "// dup-ok: URL 由来入力の防御用（Issue #612）\n"
        "export const A_RE = /^[^/\\s]+\\/[^/\\s]+$/;\n"
    )
    file_d = (
        "export const B_RE = /^[^/\\s]+\\/[^/\\s]+$/; // dup-ok: 静的インデックス側の検証用\n"
    )
    occs_full = extract_ts_occurrences("c.ts", file_c) + extract_ts_occurrences("d.ts", file_d)
    groups_full = find_duplicate_groups(occs_full)
    check("full_marker/group_count", len(groups_full), 1)
    if groups_full:
        check("full_marker/fully_marked_is_true", groups_full[0].fully_marked, True)
    unresolved_full = [g for g in groups_full if not g.fully_marked]
    check("full_marker/no_unresolved_groups", len(unresolved_full), 0)

    # 必須ケース 3: 同一ファイル内の 2 回出現は検出しない（ファイル間の重複が対象）
    file_same = (
        "export const RE1 = /^[A-Za-z0-9._-]{9,}$/;\n"
        "export const RE2 = /^[A-Za-z0-9._-]{9,}$/;\n"
    )
    occs_same = extract_ts_occurrences("same.ts", file_same)
    check("same_file/occurrence_count", len(occs_same), 2)
    groups_same = find_duplicate_groups(occs_same)
    check("same_file/no_cross_file_group", len(groups_same), 0)

    # 必須ケース 4: 理由が空の dup-ok（`// dup-ok:` だけ）は無効
    file_empty_reason = "export const RE = /^[^/\\s]+\\/[^/\\s]+$/; // dup-ok:\n"
    occs_empty = extract_ts_occurrences("empty.ts", file_empty_reason)
    check("empty_reason/not_marked", occs_empty[0].marked if occs_empty else None, False)

    # 閾値未満のパターンは、2 ファイルにまたがっていても検出対象外
    file_short_a = "const s1 = x.replace(/-/g, '_');\n"
    file_short_b = "const s2 = y.replace(/-/g, '_');\n"
    occs_short = extract_ts_occurrences("s1.ts", file_short_a) + extract_ts_occurrences(
        "s2.ts", file_short_b
    )
    groups_short = find_duplicate_groups(occs_short)
    check("below_threshold/excluded", len(groups_short), 0)

    # ---------------- Python 側 ----------------

    py_a = 'import re\nSP_RE = re.compile(r"^SP-(\\d+):")\n'  # マーカー無し
    py_b = (
        "import re\n"
        "# dup-ok: ロードマップ側でも同じ ID 抽出を独立に持つ（Issue #612）\n"
        'ID_RE = re.compile(r"^SP-(\\d+):")\n'
    )
    py_occs = extract_py_occurrences("a.py", py_a) + extract_py_occurrences("b.py", py_b)
    py_groups = find_duplicate_groups(py_occs)
    check("python/partial_marker_group_count", len(py_groups), 1)
    if py_groups:
        check("python/partial_marker_fully_marked_false", py_groups[0].fully_marked, False)

    # Python: 文字列内・コメント内の re.compile( らしき記述を誤検出しない（ast ベースなので当然
    # 拾わないはずだが、要求仕様の反例として明示的に確認する）
    py_string_like = 'note = "call re.compile(r\'^SP-(\\\\d+):\') somewhere"\n'
    py_occs_str = extract_py_occurrences("note.py", py_string_like)
    check("python/string_literal_not_matched", len(py_occs_str), 0)
    py_comment_like = "# example: re.compile(r'^SP-(\\d+):')\nx = 1\n"
    py_occs_comment = extract_py_occurrences("note2.py", py_comment_like)
    check("python/comment_not_matched", len(py_occs_comment), 0)

    # Python: 構文エラーのファイルはクラッシュせず空リストを返す
    py_broken = "def f(:\n    pass\n"
    check("python/syntax_error_returns_empty", extract_py_occurrences("broken.py", py_broken), [])

    # Python: raw 文字列と通常文字列で同じ値なら同一パターンとして扱う
    py_raw = 'import re\nre.match(r"Session-Id:\\s*[0-9a-f]{8}", s)\n'
    py_escaped = 'import re\nre.match("Session-Id:\\\\s*[0-9a-f]{8}", s)\n'
    py_occs_norm = extract_py_occurrences("raw.py", py_raw) + extract_py_occurrences(
        "escaped.py", py_escaped
    )
    check(
        "python/raw_vs_escaped_same_pattern",
        py_occs_norm[0].pattern == py_occs_norm[1].pattern if len(py_occs_norm) == 2 else False,
        True,
    )

    if failures:
        print("❌ check_duplicate_source_patterns --self-test FAILED")
        print("\n".join(failures))
        return EXIT_VIOLATION
    print(f"✅ check_duplicate_source_patterns --self-test PASSED（{check_count} ケース）")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="ネットワーク・実ファイル不要のユニットテストを実行する")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="未許可の重複（dup-ok マーカー未記載の箇所を含むグループ）があれば exit 1 にする",
    )
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    repo_root = Path(__file__).resolve().parent.parent
    occurrences = collect_occurrences(repo_root)
    groups = find_duplicate_groups(occurrences)

    if not groups:
        print("[duplicate-source-patterns] OK（複数ファイルにまたがる正規表現の重複なし）")
        return EXIT_OK

    print(format_report(groups))

    unresolved = [g for g in groups if not g.fully_marked]
    if unresolved:
        if args.strict:
            print(
                f"[duplicate-source-patterns] NG（--strict・未許可の重複 {len(unresolved)} 件）",
                file=sys.stderr,
            )
            return EXIT_VIOLATION
        print(
            f"[duplicate-source-patterns] WARNING（未許可の重複 {len(unresolved)} 件。"
            "--strict 未指定のため PASS 扱い）",
            file=sys.stderr,
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
