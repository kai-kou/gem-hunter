#!/usr/bin/env python3
"""check_tool_wiring.py — `tools/check_*.py` の「本判定がどこからも実行されない」死蔵を検査する（Issue #164）。

## なぜ必要か

`tools/check_selftest_wiring.py`（Issue #612）は **`--self-test` の配線漏れ** を機械保証するが、
「`--self-test` を持たない検査スクリプト」は走査対象にすらならない。その結果、
**本判定（`--self-test` でない実行）がどこからも呼ばれないスクリプト** が静かに死蔵しても
誰も気づかない状態が残っていた（Issue #164 の実測: `check_agent_definitions.py` は
`--self-test` を持たないため既存検査の視界の外にあった）。

死蔵した検査は「検査があるのに機能していない」最悪の状態で、レビュアーにその領域を
見なくてよいという誤った安心感を配布する（`docs/rules/check-tool-design-rules.md` §0）。
本スクリプトはこの再発を止める。

🔁 `check_selftest_wiring.py` と対になる検査である（あちらは `--self-test` の配線、こちらは
本判定の配線）。シェルコメント除去とマーカー走査の共通ロジックは `tools/wiring_marker.py`
（Issue #933）へ集約済みで、両検査はそこから import して使う。

## 走査対象

- `tools/check_*.py`（グロブ）
- `_EXTRA_TARGETS` に明示列挙したスクリプト（`tools/*.py` 全体へは広げない。ライブラリ
  モジュールが「実行されていない」と誤検出されるため）

## 「実行場所がある」と認める形

いずれか 1 つでもあれば配線済み（`wired`）と判定する。参照元は次を走査する。

1. `tools/run_checks.sh` を含む `tools/*.sh` / `tools/*.py`（間接実行）
2. `.claude/hooks/*.sh`
3. `.claude/skills/**/SKILL.md` と `.claude/skills/**/reference.md`（**コードブロック内のみ**）
4. `.claude/commands/*.md`（**コードブロック内のみ**）
5. `scripts/*.sh` / `scripts/*.py`
6. スクリプト自身に `# tool-wiring-ok: {理由}` マーカーがある

## 「呼ばれている」の判定（誤判定の防止）

単なるファイル名の言及（docstring での参照・「〜は別ツールの担当」といった地の文・
`[ -f ... ]` の存在確認・self-test 用のフィクスチャ文字列・データ辞書のキー）を実行と
誤認しないため、**同一の論理行に実行指標** が現れることを要求する。判定は次の AND:

- 論理行にファイル名が **語境界付きで** 現れる（`check_foo.py` が `check_foo_bar.py` や
  `xcheck_foo.py`・`check_foo.py.bak` に前方一致・部分一致しないこと。Issue #750 の退行防止）
- そのファイル名の出現の **近傍**（同一コマンド／同一引数リスト内）に `--self-test` が無い
  （self-test 実行は本判定の実行場所ではない。近傍に限るのは、`[[…], […, "--self-test"]]`
  のように 2 つの呼び出しが 1 論理行へ畳まれたとき本判定まで巻き添えで除外しないため）
- 同じ論理行に実行指標がある（`python3` / `sys.executable` / `subprocess` / `Popen` /
  `check_output` / `run_check*` / `run_subcheck*` / コマンド位置の `bash`・`sh` /
  `$PYTHON` / `uv run`）。シェルでは加えて **コマンド位置に現れるパス自体**
  （`"$REPO_ROOT/tools/check_x.py" --json`）を実行指標とみなす

指標が見つからない書き方は「未配線」（fail-closed）へ倒れる。誤って死蔵を見逃す
（fail-open）よりも、人が 1 度見て判断する方が安全なためである。

さらにソース種別ごとに以下の前処理を行う:

- `*.sh`: クォート外の `#` 以降（シェルコメント）を除去し、行末 `\` の継続行を連結し、
  リテラル代入（`TOOL="$X/tools/check_y.py"`）を `$TOOL` の出現箇所へ展開する
  （変数経由の実行を取りこぼさないため）
- `*.py`: `tokenize` で **実コメントと docstring を除去** し、論理行（`NEWLINE` 区切り）
  単位で判定する。**実行指標の探索からは散文の文字列リテラルを除外** する（空白を含まない
  短い文字列＝argv の 1 要素だけを指標の探索対象に残す）。`USAGE` の使い方説明や
  `help="python3 tools/check_y.py で確認する"`・self-test のフィクスチャ文字列を実行と
  誤認しないため
- `*.md`: **フェンス付きコードブロックの中の行だけ** を対象にする（`md_fence.fence_flags`）。
  地の文・否定文（「python3 が無い環境では実行されない」）を実行と誤認しないため。
  インラインバッククォートは地の文とみなす

## 意図的に配線しないものがある場合（マーカー）

特定の場面（親セッションが手で叩く運用ツール・ネットワーク必須の定期スロット・
既存の赤があり PR ゲートに載せられない等）でのみ使うスクリプトは、配線しないことが
正しい判断でありうる。その場合はスクリプト側の任意の行に次のマーカーを書くと除外できる:

    # tool-wiring-ok: {なぜ配線しないか + 実際にどこで実行されるか}

理由が空（`# tool-wiring-ok:` だけ）のマーカーは無効として扱い、除外しない
（`check_selftest_wiring.py` の `selftest-wiring-ok` マーカーと同じ思想）。
マーカーは **実コメント** としてのみ有効で、docstring 内で書式を説明する地の文は
本物のマーカーと誤認しない。

使い方:
    python3 tools/check_tool_wiring.py              # 死蔵検査（人間可読レポート）
    python3 tools/check_tool_wiring.py --json        # 機械可読 JSON
    python3 tools/check_tool_wiring.py --self-test   # 検出ロジック自体のユニットテスト

終了コード（`docs/rules/check-tool-design-rules.md` §1 の標準に準拠）:
    0 = 死蔵なし（走査対象が 1 件以上あり、全てに実行場所がある）
    1 = 死蔵あり（または --self-test 失敗）
    2 = 判定不能（`tools/` や `run_checks.sh` が見つからない・走査対象が 0 件・
        対象や参照元を読めない / 解析できないファイルがある）

🔴 走査対象 0 件は **PASS にしない**（§2 の fail-closed）。`tools/check_*.py` が 1 本も
無い状態は「対象の選択が壊れている」以外にありえないためである。

🔴 「読めない・解析できない」は 0 にも 1 にも丸めない（#445 の先例）。stderr の先頭記号で
区別する（`❌` = 死蔵あり / `⚠️` = 判定不能）。
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from md_fence import fence_flags  # noqa: E402  （tools/ 直下の共有ヘルパー）
import wiring_marker  # noqa: E402 — シェルコメント除去・マーカー走査の共通ロジック（#933）

# `check_*.py` グロブに載らないが死蔵を機械保証したいスクリプトの明示リスト。
# `tools/*.py` 全体へ広げるとライブラリモジュール（`md_fence.py` 等）が「実行場所なし」と
# 誤検出されるため、個別列挙にしている（Issue #164 の追記コメントで指定された分）。
_EXTRA_TARGETS: tuple[str, ...] = ("lessons_guard.py",)

# 除外マーカー語（`wiring_marker.scan_markers` へ渡す token）。理由が空のマーカーは無効。
# ⚠️ 本ファイルの実コメントにマーカー書式を literal で書くと自分自身が除外されるので書かない。
_TOKEN = "tool-wiring-ok"

# 「この論理行は実行である」と認める指標。ファイル名の単なる言及と区別するために要求する。
# 見つからない書き方は未配線（fail-closed）へ倒れるので、指標を増やすときは
# 「実行以外の文脈で頻出しないか」を確認すること。
#
# 🔴 `sh` / `bash` は **コマンド位置のトークンとしてのみ** 認める。素朴な `\bsh\b` は
#    `tools/run_checks.sh` の末尾 2 文字に一致してしまい、「同一論理行に実行指標」という
#    誤検出防止が事実上無効になる（データ辞書に並べたファイル名リストが実行と判定された）。
# 🔴 同じ理由で `run_check\w*` は直後に `. - / 英数字` が続かないことを要求する
#    （`tools/run_checks.sh` というファイル名の一部を `run_checks` として拾ってしまうため）。
# 🔴 `sys.executable` は Python 層ではトークンを空白連結した `sys . executable` になるため
#    空白を許す形で書く（`sys\.executable` は原理的に一度も一致しない死んだ指標だった）。
_EXEC_INDICATOR_RE = re.compile(
    r"""(?x)
      (?<![A-Za-z0-9_.])python3?(?![A-Za-z0-9_])
    | (?<![A-Za-z0-9_.])subprocess(?![A-Za-z0-9_])
    | (?<![A-Za-z0-9_.])Popen(?![A-Za-z0-9_])
    | (?<![A-Za-z0-9_.])check_output(?![A-Za-z0-9_])
    | (?<![A-Za-z0-9_.])run_check\w*(?![\w.\-/])
    | (?<![A-Za-z0-9_.])run_subcheck\w*(?![\w.\-/])
    | sys\s*\.\s*executable
    | (?:^|[\s|;&(])(?:ba)?sh(?=\s)
    | \$\{?PYTHON\}?(?![A-Za-z0-9_])
    | (?<![A-Za-z0-9_.])uv\s+run(?![A-Za-z0-9_])
    """
)

_SELFTEST_TOKEN = "--self-test"

# `--self-test` を「同一コマンド内」に限定するための打ち切り文字（引数リスト・コマンドの境界）。
_SELFTEST_SCOPE_TERMINATORS = "])};|&\n"
_SELFTEST_SCOPE_CHARS = 80


# ─────────────────────────────────────────────────────────────
# マーカー走査（実コメントのみを見る）
# ─────────────────────────────────────────────────────────────


def marker_reason(content: str) -> str | None:
    """有効な `tool-wiring-ok` マーカーの理由を返す（無ければ None＝除外しない）。"""
    return wiring_marker.marker_reason(content, _TOKEN, "py")


def has_invalid_empty_marker(content: str) -> bool:
    """理由が空の（無効な）`tool-wiring-ok` マーカーが存在するか。"""
    return wiring_marker.has_invalid_empty_marker(content, _TOKEN, "py")


# ─────────────────────────────────────────────────────────────
# ソース種別ごとの「論理行」抽出
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Statement:
    """1 論理行。

    text:      ファイル名の探索に使う全文
    exec_text: 実行指標の探索に使う部分（Python 層は STRING トークンを除外した残り）
    kind:      "sh" | "md" | "py"（シェルだけコマンド位置のパス実行を追加で認める）
    """

    text: str
    exec_text: str
    kind: str = "sh"


def _as_statement(statement: Statement | str) -> Statement:
    return statement if isinstance(statement, Statement) else Statement(statement, statement, "sh")


# bash はメタ文字（`; | & ( )`）の直後の `#` もコメント開始として扱う。`wiring_marker` の
# 既定（空白の直後のみ）に加えてこれらも許容する（`${VAR#pattern}` / `$#` の `#` は
# メタ文字の直後ではないため誤って落とさない）。この拡張は本検査（コマンド位置の実行呼び出し
# 検出）専用で、`check_selftest_wiring.py` 側は既定（空白のみ）のまま使う（#933・意味論維持）。
_SHELL_COMMENT_META_CHARS = ";|&()"


def _join_continuations(lines: list[str]) -> list[str]:
    """行末 `\\` の継続行を 1 論理行へ連結する。"""
    out: list[str] = []
    buf = ""
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        out.append(buf + stripped)
        buf = ""
    if buf:
        out.append(buf)
    return out


# シェルのリテラル代入（`TOOL="$TARGET/tools/check_x.py"`）。値にコマンド置換・バッククォートを
# 含むものは展開しない（静的に決まらないため）。
_SHELL_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _shell_literal_assignments(statements: list[str]) -> dict[str, str]:
    """スクリプト名を含むリテラル代入だけを集める（`$VAR` 経由の実行を追えるようにする）。"""
    assigns: dict[str, str] = {}
    for st in statements:
        m = _SHELL_ASSIGN_RE.match(st)
        if not m:
            continue
        value = m.group(2).strip()
        if "$(" in value or "`" in value:
            continue
        value = value.strip('"').strip("'")
        if ".py" not in value and ".sh" not in value:
            continue  # ファイル名を含まない代入は展開しても意味がない（ノイズを増やさない）
        assigns[m.group(1)] = value
    return assigns


def _expand_shell_vars(statement: str, assigns: dict[str, str]) -> str:
    if not assigns:
        return statement

    def _sub(m: re.Match[str]) -> str:
        name = m.group(1) or m.group(2)
        return assigns.get(name, m.group(0))

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", _sub, statement)


def shell_statements(content: str) -> list[Statement]:
    """シェルスクリプトの論理行（コメント除去 + 継続行連結 + リテラル代入の展開）。"""
    raw = _join_continuations(
        [
            wiring_marker.strip_shell_line_comment(line, _SHELL_COMMENT_META_CHARS)
            for line in content.splitlines()
        ]
    )
    assigns = _shell_literal_assignments(raw)
    return [Statement(_expand_shell_vars(st, assigns), _expand_shell_vars(st, assigns), "sh") for st in raw]


def markdown_statements(content: str) -> list[Statement]:
    """Markdown の論理行。

    🔴 **フェンス付きコードブロックの中の行だけ** を採る。地の文（「`apply-to-repo.sh` は
    `tools/check_x.py` を自動実行し」）や否定文（「python3 が無い環境では実行しない」）を
    実行と誤認しないため。インラインバッククォートは地の文とみなす（フェンスではない）。
    """
    lines = content.splitlines()
    flags = fence_flags(lines)
    fenced = [line for line, inside in zip(lines, flags) if inside]
    return [Statement(st, st, "md") for st in _join_continuations(fenced)]


def _is_argv_like_string(token: str) -> bool:
    """文字列リテラルが「argv の 1 要素」に見えるか（空白を含まない短い語）。

    `subprocess.run(["python3", "tools/check_x.py"])` の `"python3"` は実行指標として
    数えたいが、`USAGE = \"\"\"…python3 tools/check_x.py…\"\"\"` や
    `help="python3 tools/check_y.py で確認する"` のような **散文**（空白を含む）は
    数えたくない。両者を分ける最小の基準が「空白を含まない短い語かどうか」である。
    """
    return len(token) <= 48 and re.search(r"\s", token) is None


# f-string が複数トークンへ分解される処理系（3.12+）でも文字列として扱えるようにする。
_STRING_TOKEN_TYPES = {tokenize.STRING} | {
    getattr(tokenize, name)
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
    if hasattr(tokenize, name)
}


def python_statements(content: str) -> list[Statement] | None:
    """Python の論理行（実コメントと docstring を除去）。

    `subprocess.run([...])` のように複数行へ折り返された呼び出しを 1 つの論理行として
    扱えるよう、`tokenize` の `NEWLINE`（論理行末）で区切る。トークナイズ失敗時は
    `None` を返し、呼び出し側は判定不能として扱う。

    `exec_text` には **STRING トークンを含めない**。`USAGE = \"\"\"python3 tools/check_x.py\"\"\"`
    や `add_argument(help="python3 tools/check_y.py")`、self-test のフィクスチャ文字列が
    実行指標を成立させると、配線を外しても永久に wired になってしまうため。
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
    except Exception:
        return None

    statements: list[Statement] = []
    parts: list[str] = []
    code_parts: list[str] = []
    # 直前の「意味のある」トークン種別。文の先頭に現れる STRING は docstring とみなす。
    at_statement_start = True

    def _flush() -> None:
        if parts:
            statements.append(Statement(" ".join(parts), " ".join(code_parts), "py"))
            parts.clear()
            code_parts.clear()

    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type in (tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
            continue
        if tok.type == tokenize.NEWLINE:
            _flush()
            at_statement_start = True
            continue
        if tok.type == tokenize.ENDMARKER:
            continue
        if tok.type in _STRING_TOKEN_TYPES and at_statement_start:
            # docstring（式文としての文字列）は実行ではないので落とす
            at_statement_start = False
            continue
        parts.append(tok.string)
        if tok.type not in _STRING_TOKEN_TYPES or _is_argv_like_string(tok.string):
            code_parts.append(tok.string)
        at_statement_start = False
    _flush()
    return statements


# ─────────────────────────────────────────────────────────────
# 参照判定
# ─────────────────────────────────────────────────────────────


def _filename_re(filename: str) -> re.Pattern[str]:
    """ファイル名を語境界付きで探す正規表現。

    前方一致・部分一致への退行を防ぐ（`check_foo.py` が `check_foo_bar.py` や
    `xcheck_foo.py`・`check_foo.py.bak` に一致してはならない・Issue #750）。
    `tools/check_foo.py` のようにパス区切り `/` が直前に来る形は一致させる。
    """
    return re.compile(
        r"(?<![A-Za-z0-9_.\-])" + re.escape(filename) + r"(?![A-Za-z0-9_.\-])"
    )


def _bare_path_exec_re(filename: str) -> re.Pattern[str]:
    """シェルの「コマンド位置に置かれたスクリプトパス」（実行ビット付き直接実行）。

    `"$REPO_ROOT/tools/check_x.py" --json` を実行とみなす。誤検出を避けるため
    ① コマンド位置（行頭 or `| ; & (` の直後）② パス区切り `/` を伴うこと
    ③ `=` を含まないこと（`TOOL="…/check_x.py"` という代入を実行と読まない）を要求する。
    """
    return re.compile(
        r"(?:^|[|;&(])\s*[\"']?[^\s;|&()\"'=]*/"
        + re.escape(filename)
        + r"(?![A-Za-z0-9_.\-])"
    )


def _selftest_in_scope(text: str, end: int) -> bool:
    """ファイル名出現位置の直後（同一コマンド／同一引数リスト内）に `--self-test` があるか。

    論理行全体で `--self-test` を探すと、`[["python3","x.py"], ["python3","x.py","--self-test"]]`
    のように 2 つの呼び出しが 1 論理行に畳まれたとき、本判定の呼び出しまで巻き添えで
    除外され死蔵と誤報する（Issue #164 レビュー実測）。
    """
    tail = text[end : end + _SELFTEST_SCOPE_CHARS]
    cut = len(tail)
    for ch in _SELFTEST_SCOPE_TERMINATORS:
        i = tail.find(ch)
        if i != -1:
            cut = min(cut, i)
    return _SELFTEST_TOKEN in tail[:cut]


def statement_invokes(statement: Statement | str, filename: str) -> bool:
    """1 つの論理行が `filename` の **本判定** 実行かどうか。"""
    st = _as_statement(statement)
    matches = list(_filename_re(filename).finditer(st.text))
    if not matches:
        return False
    if all(_selftest_in_scope(st.text, m.end()) for m in matches):
        return False  # self-test 実行しか無い行は本判定の実行場所ではない
    if _EXEC_INDICATOR_RE.search(st.exec_text):
        return True
    if st.kind == "sh" and _bare_path_exec_re(filename).search(st.text):
        return True
    return False


@dataclass
class Source:
    """参照元 1 ファイル（既に論理行へ分解済み）。"""

    label: str  # レポートに出す表示名（リポジトリ相対パス）
    filename: str  # ファイル名（自己参照除外に使う）
    statements: list[Statement]


def find_invocations(filename: str, sources: list[Source]) -> list[str]:
    """`filename` を本判定として実行しているソースのラベル一覧（自分自身は除外）。"""
    found: list[str] = []
    for src in sources:
        if src.filename == filename:
            continue  # 自分自身の docstring / 使い方例は実行場所ではない
        if any(statement_invokes(st, filename) for st in src.statements):
            found.append(src.label)
    return found


# ─────────────────────────────────────────────────────────────
# 判定
# ─────────────────────────────────────────────────────────────


@dataclass
class Verdict:
    """1 スクリプトぶんの判定結果。"""

    filename: str
    status: str  # "wired" | "excluded" | "violation" | "undetermined"
    locations: list[str] = field(default_factory=list)
    reason: str | None = None  # excluded / undetermined の理由
    invalid_marker: bool = False


def evaluate_script(filename: str, content: str, sources: list[Source]) -> Verdict:
    """1 ファイルぶんの内容から死蔵判定する（テスト容易性のための純関数）。"""
    marker_scan = wiring_marker.scan_markers(content, _TOKEN, "py")
    locations = find_invocations(filename, sources)
    if locations:
        return Verdict(filename, "wired", locations=locations)
    if marker_scan.tokenize_failed:
        # マーカーを読めない＝「配線されていない」とも「除外指定がある」とも言えない。
        # 0/1 に丸めず判定不能へ倒す（#445 の先例・マーカーを書いても解除できない
        # 出口なしの ❌ 死蔵表示にしない）。
        return Verdict(
            filename,
            "undetermined",
            reason="Python として解析できずマーカーを読めませんでした（構文エラー等）",
        )
    if marker_scan.reasons:
        return Verdict(filename, "excluded", reason=marker_scan.reasons[0])
    return Verdict(filename, "violation", invalid_marker=marker_scan.has_empty)


@dataclass
class Report:
    wired: list[tuple[str, list[str]]] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    invalid_markers: list[str] = field(default_factory=list)
    undetermined: list[tuple[str, str]] = field(default_factory=list)

    def add(self, v: Verdict) -> None:
        if v.status == "wired":
            self.wired.append((v.filename, v.locations))
        elif v.status == "excluded":
            self.excluded.append((v.filename, v.reason or ""))
        elif v.status == "undetermined":
            self.undetermined.append((v.filename, v.reason or ""))
        else:
            self.violations.append(v.filename)
            if v.invalid_marker:
                self.invalid_markers.append(v.filename)

    @property
    def total(self) -> int:
        return len(self.wired) + len(self.excluded) + len(self.violations) + len(self.undetermined)


def _source_paths(repo_root: Path) -> list[Path]:
    """参照元として走査するファイル一覧（docstring「走査対象」節と一致させること）。"""
    paths: list[Path] = []
    paths.extend(sorted((repo_root / "tools").glob("*.py")))
    paths.extend(sorted((repo_root / "tools").glob("*.sh")))
    paths.extend(sorted((repo_root / "scripts").glob("*.sh")))
    paths.extend(sorted((repo_root / "scripts").glob("*.py")))
    paths.extend(sorted((repo_root / ".claude" / "hooks").glob("*.sh")))
    paths.extend(sorted((repo_root / ".claude" / "skills").rglob("SKILL.md")))
    paths.extend(sorted((repo_root / ".claude" / "skills").rglob("reference.md")))
    paths.extend(sorted((repo_root / ".claude" / "commands").glob("*.md")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def collect_sources(repo_root: Path) -> tuple[list[Source], list[tuple[str, str]]]:
    """参照元を集める。戻り値は (ソース一覧, 読めなかった/解析できなかったもの)。"""
    sources: list[Source] = []
    undetermined: list[tuple[str, str]] = []

    for path in _source_paths(repo_root):
        try:
            label = str(path.relative_to(repo_root))
        except ValueError:  # pragma: no cover - repo_root 配下以外は来ない
            label = str(path)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            # UnicodeDecodeError は ValueError 派生で OSError では捕まらない。握り潰すと
            # 「参照元を読めていないのに死蔵ゼロ」と言い切る fail-open になるため判定不能へ。
            undetermined.append((label, f"読み込み失敗: {e}"))
            continue
        if path.suffix == ".py":
            statements = python_statements(content)
            if statements is None:
                undetermined.append((label, "Python として解析できませんでした（構文エラー等）"))
                continue
        elif path.suffix == ".sh":
            statements = shell_statements(content)
        else:
            statements = markdown_statements(content)
        sources.append(Source(label=label, filename=path.name, statements=statements))
    return sources, undetermined


def target_paths(repo_root: Path) -> list[Path]:
    """死蔵検査の対象（`tools/check_*.py` + 明示リスト）。"""
    paths = list(sorted((repo_root / "tools").glob("check_*.py")))
    known = {p.name for p in paths}
    for name in _EXTRA_TARGETS:
        extra = repo_root / "tools" / name
        if extra.is_file() and name not in known:
            paths.append(extra)
    return paths


def scan(repo_root: Path, sources: list[Source]) -> Report:
    report = Report()
    for path in target_paths(repo_root):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            report.add(Verdict(path.name, "undetermined", reason=f"読み込み失敗: {e}"))
            continue
        report.add(evaluate_script(path.name, content, sources))
    return report


def render_human(report: Report) -> str:
    lines: list[str] = []
    lines.append(
        f"[tool-wiring] 走査対象（tools/check_*.py + 明示リスト）: 全 {report.total} 本"
        f"（実行場所あり {len(report.wired)} / マーカー除外 {len(report.excluded)} "
        f"/ 死蔵 {len(report.violations)} / 判定不能 {len(report.undetermined)}）"
    )
    for name in report.violations:
        if name in report.invalid_markers:
            lines.append(
                f"  ❌ 死蔵: {name}（tool-wiring-ok マーカーはあるが理由が空のため無効）"
            )
        else:
            lines.append(
                f"  ❌ 死蔵: {name}"
                "（run_checks.sh / hooks / SKILL.md / commands / scripts / 他 tools の"
                "どこからも本判定が呼ばれていない）"
            )
    for name, reason in report.undetermined:
        lines.append(f"  ⚠️  判定不能: {name}（{reason}）")
    if report.excluded:
        lines.append(f"  ℹ️  マーカーで除外済み: {len(report.excluded)} 件")
        for name, reason in report.excluded:
            lines.append(f"      {name}: {reason}")
    if report.violations:
        lines.append(
            f"[tool-wiring] FAIL: 死蔵 {len(report.violations)} 件"
            "（実行場所を作るか、tool-wiring-ok マーカーで実行場所を明記すること）"
        )
    elif report.undetermined:
        lines.append(
            f"[tool-wiring] 判定不能 {len(report.undetermined)} 件"
            "（読めない / 解析できないファイルを直すまで死蔵の有無を断定できない）"
        )
    else:
        lines.append("[tool-wiring] PASS（実行場所の無い検査スクリプトなし）")
    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps(
        {
            "wired": [{"file": n, "locations": locs} for n, locs in report.wired],
            "excluded": [{"file": n, "reason": r} for n, r in report.excluded],
            "violations": report.violations,
            "invalid_markers": report.invalid_markers,
            "undetermined": [{"file": n, "reason": r} for n, r in report.undetermined],
        },
        ensure_ascii=False,
        indent=2,
    )


# ─────────────────────────────────────────────────────────────
# --self-test（ネットワーク・実データ非依存）
# ─────────────────────────────────────────────────────────────


def _src(*statements: str) -> Source:
    return Source(
        label="fixture",
        filename="fixture.sh",
        statements=[Statement(s, s, "sh") for s in statements],
    )


def _write_fixture_repo(
    root: Path,
    *,
    run_checks: str = "echo hi\n",
    tools: dict[str, str] | None = None,
    tool_sources: dict[str, str] | None = None,
    hooks: dict[str, str] | None = None,
    skills: dict[str, str] | None = None,
    commands: dict[str, str] | None = None,
    scripts: dict[str, str] | None = None,
) -> None:
    """self-test 用の最小リポジトリを作る（main() を実際に貫通させるため）。

    各参照元ディレクトリ（hooks / skills / commands / scripts）へも書けるようにしてある。
    走査 glob を 1 行削ると、対応する positive ケースが 1 件ずつ落ちる形にするため。
    """
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tools" / "run_checks.sh").write_text(run_checks, encoding="utf-8")
    for name, body in (tools or {}).items():
        (root / "tools" / name).write_text(body, encoding="utf-8")
    for name, body in (tool_sources or {}).items():
        (root / "tools" / name).write_text(body, encoding="utf-8")
    for name, body in (hooks or {}).items():
        (root / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "hooks" / name).write_text(body, encoding="utf-8")
    for rel, body in (skills or {}).items():
        p = root / ".claude" / "skills" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    for name, body in (commands or {}).items():
        (root / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "commands" / name).write_text(body, encoding="utf-8")
    for name, body in (scripts or {}).items():
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / name).write_text(body, encoding="utf-8")


def _fence(*lines: str) -> str:
    """Markdown のフェンス付きコードブロックを組み立てる。"""
    return "```bash\n" + "\n".join(lines) + "\n```\n"


def _silent_main(argv: list[str]) -> int:
    """self-test 用に main() を実行し、レポート出力を飲み込んで終了コードだけ返す。"""
    import contextlib

    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        return main(argv)


def _self_test() -> int:  # noqa: C901 - 網羅性を優先する
    import tempfile

    failures: list[str] = []
    assertions = 0

    def check(label: str, cond: bool) -> None:
        nonlocal assertions
        assertions += 1
        if not cond:
            failures.append(label)

    # ── A: 呼び出し記法のバリアント（同じ実行を 3 通りの書き方で表現しても検出する） ──
    variants = [
        'run_check "alpha" python3 tools/check_alpha.py',
        'run_check "alpha" python3 "$REPO_ROOT/tools/check_alpha.py"',
        "bash -c 'python3 tools/check_alpha.py --json'",
    ]
    for i, stmt in enumerate(variants, start=1):
        check(f"A{i}: 呼び出し記法バリアントを検出", statement_invokes(stmt, "check_alpha.py"))

    # A4〜A10: 指標ごとの単独正ケース（1 指標を消したら 1 件ずつ落ちる形にする）
    check(
        "A4: run_check 単独（python なし）でも実行とみなす",
        statement_invokes('run_check "alpha" "$REPO_ROOT/x" tools/check_alpha.py', "check_alpha.py"),
    )
    check(
        "A5: run_check_timeout（run_check の派生）も実行指標",
        statement_invokes(
            'run_check_timeout "alpha" 60 tools/check_alpha.py', "check_alpha.py"
        ),
    )
    check(
        "A6: run_subcheck も実行指標",
        statement_invokes('run_subcheck ( [ "tools/check_alpha.py" ] )', "check_alpha.py"),
    )
    check(
        "A7: コマンド位置の bash は実行指標",
        statement_invokes("bash tools/check_alpha.py", "check_alpha.py"),
    )
    check(
        "A8: check_output は実行指標",
        statement_invokes('check_output ( [ "tools/check_alpha.py" ] )', "check_alpha.py"),
    )
    check(
        "A9: sys.executable（空白連結された Python 論理行）は実行指標",
        statement_invokes('cmd = [ sys . executable , "tools/check_alpha.py" ]', "check_alpha.py"),
    )
    check(
        "A10: uv run も実行指標",
        statement_invokes("uv run tools/check_alpha.py", "check_alpha.py"),
    )
    check(
        "A11: $PYTHON 経由も実行指標",
        statement_invokes('"$PYTHON" tools/check_alpha.py --json', "check_alpha.py"),
    )
    check(
        "A12: コマンド位置のパス直接実行（実行ビット付き）",
        statement_invokes('"$REPO_ROOT/tools/check_alpha.py" --json', "check_alpha.py"),
    )
    check(
        "A12: 代入は直接実行とみなさない（対の負ケース）",
        not statement_invokes('TOOL="$REPO_ROOT/tools/check_alpha.py"', "check_alpha.py"),
    )
    check(
        "A12: 括弧内の言及は直接実行とみなさない（パス区切りが無い）",
        not statement_invokes('skip_check "検査 (check_alpha.py)" "理由"', "check_alpha.py"),
    )
    check(
        "A13: シェル変数経由の実行を展開して検出する",
        any(
            statement_invokes(st, "check_alpha.py")
            for st in shell_statements(
                'TOOL="$TARGET/tools/check_alpha.py"\nif python3 "$TOOL" check; then :; fi\n'
            )
        ),
    )

    # ── B: 実行ではない言及は検出しない（fail-closed 側の誤検出防止） ──
    check(
        "B1: 存在確認だけの行は実行とみなさない",
        not statement_invokes('if [ -f "$REPO_ROOT/tools/check_alpha.py" ]; then', "check_alpha.py"),
    )
    check(
        "B2: 実行指標語を含む地の文でも（Markdown の地の文でなければ）指標が要る",
        not statement_invokes("詳細は tools/check_alpha.py を参照", "check_alpha.py"),
    )
    check(
        "B3: --self-test 実行は本判定の実行場所ではない",
        not statement_invokes(
            'run_check "alpha self-test" python3 tools/check_alpha.py --self-test',
            "check_alpha.py",
        ),
    )
    # シェルコメント内の呼び出しは除去される（生テキスト検索への退行防止）
    commented = shell_statements('# run_check "alpha" python3 tools/check_alpha.py\n')
    check(
        "B4: コメントアウトされた呼び出しは検出しない",
        not any(statement_invokes(st, "check_alpha.py") for st in commented),
    )
    active = shell_statements('run_check "alpha" python3 tools/check_alpha.py\n')
    check(
        "B4: コメントでない同じ行は検出する（回帰防止）",
        any(statement_invokes(st, "check_alpha.py") for st in active),
    )
    # クォート内の `#` で後続の判定が壊れない
    quoted = shell_statements(
        'echo "## run_checks 結果"\nrun_check "alpha" python3 tools/check_alpha.py\n'
    )
    check(
        "B5: クォート内の # で後続行の判定が壊れない",
        any(statement_invokes(st, "check_alpha.py") for st in quoted),
    )
    # メタ文字直後の `#` もコメント開始（bash 仕様）
    meta_commented = shell_statements("true;#python3 tools/check_alpha.py\n")
    check(
        "B6: `;#` 直後のコメントも除去する",
        not any(statement_invokes(st, "check_alpha.py") for st in meta_commented),
    )
    for prefix in ("|", "&", "("):
        stmts = shell_statements(f"true {prefix}#python3 tools/check_alpha.py\n")
        check(
            f"B6: `{prefix}#` 直後のコメントも除去する",
            not any(statement_invokes(st, "check_alpha.py") for st in stmts),
        )
    # `${VAR#pattern}` / `$#` はコメントではない（壊していないことの回帰）
    param_expand = shell_statements(
        'NAME="${FILE#tools/}"; run_check "alpha" python3 tools/check_alpha.py\n'
    )
    check(
        "B7: ${VAR#pattern} をコメント開始と誤認しない",
        any(statement_invokes(st, "check_alpha.py") for st in param_expand),
    )
    count_expand = shell_statements('[ $# -gt 0 ] && python3 tools/check_alpha.py\n')
    check(
        "B7: $# をコメント開始と誤認しない",
        any(statement_invokes(st, "check_alpha.py") for st in count_expand),
    )
    # データリテラル（ファイル名の一覧）に `.sh` が混ざっても実行と誤認しない（`\bsh\b` 退行）
    data_literal = python_statements(
        'HISTORICAL = {\n'
        '    "a": ["tools/check_alpha.py", "tools/run_checks.sh"],\n'
        '}\n'
    )
    assert data_literal is not None
    check(
        "B8: データリテラル中のファイル名一覧は実行とみなさない（.sh の sh に一致しない）",
        not any(statement_invokes(st, "check_alpha.py") for st in data_literal),
    )
    check(
        "B8: 同じ内容がシェルの実行行なら検出する（対の正ケース）",
        statement_invokes("bash tools/run_checks.sh && python3 tools/check_alpha.py", "check_alpha.py"),
    )

    # ── C: 境界の外側（#750・前方一致 / 部分一致への退行を捕まえる） ──
    check(
        "C1: 語頭の別名（my-check_alpha.py）に一致しない",
        not statement_invokes("python3 tools/my-check_alpha.py", "check_alpha.py"),
    )
    check(
        "C1b: ドット直前（v1.check_alpha.py）に一致しない",
        not statement_invokes("python3 v1.check_alpha.py", "check_alpha.py"),
    )
    check(
        "C1c: 語尾の別名（check_alpha_beta.py）に一致しない",
        not statement_invokes("python3 tools/check_alpha_beta.py", "check_alpha.py"),
    )
    check(
        "C2: check_alpha.py は xcheck_alpha.py の呼び出しに一致しない",
        not statement_invokes("python3 tools/xcheck_alpha.py", "check_alpha.py"),
    )
    check(
        "C3: check_alpha.py は check_alpha.pyc の言及に一致しない",
        not statement_invokes("python3 tools/check_alpha.pyc", "check_alpha.py"),
    )
    check(
        "C3b: check_alpha.py は check_alpha.py.bak に一致しない",
        not statement_invokes("python3 tools/check_alpha.py.bak", "check_alpha.py"),
    )
    check(
        "C4: 対になる正ケース（完全一致なら検出する）",
        statement_invokes("python3 tools/check_alpha.py", "check_alpha.py"),
    )
    check(
        "C5: 長い方の名前は自分自身の呼び出しで検出される",
        statement_invokes("python3 tools/check_alpha_beta.py", "check_alpha_beta.py"),
    )

    # ── D: Python ソースからの間接実行（論理行単位・docstring とコメントと文字列を落とす） ──
    py_src = (
        "#!/usr/bin/env python3\n"
        '"""親ツールの docstring: python3 tools/check_ghost.py と書いただけで実行ではない"""\n'
        "import subprocess\n"
        "# python3 tools/check_commented.py  ← コメント内の言及\n"
        "subprocess.run(\n"
        '    [sys.executable, "tools/check_alpha.py"],\n'
        "    check=True,\n"
        ")\n"
    )
    py_stmts = python_statements(py_src)
    assert py_stmts is not None
    check(
        "D1: 複数行にまたがる subprocess 呼び出しを検出",
        any(statement_invokes(st, "check_alpha.py") for st in py_stmts),
    )
    check(
        "D2: docstring 内の言及は実行とみなさない",
        not any(statement_invokes(st, "check_ghost.py") for st in py_stmts),
    )
    check(
        "D3: コメント内の言及は実行とみなさない",
        not any(statement_invokes(st, "check_commented.py") for st in py_stmts),
    )
    check(
        "D4: 構文エラーの .py は None（解析不能）",
        python_statements("def f(:\n    pass\n") is None,
    )
    # D5: Python の文字列リテラルは実行指標を成立させない（#164 レビュー実測）
    py_strings = python_statements(
        'USAGE = """\n  python3 tools/check_usage.py\n"""\n'
        'parser.add_argument("--x", help="python3 tools/check_help.py で確認する")\n'
        'FIXTURE = "run_check \\"a\\" python3 tools/check_fixture.py"\n'
    )
    assert py_strings is not None
    for name in ("check_usage.py", "check_help.py", "check_fixture.py"):
        check(
            f"D5: 文字列リテラル内の実行指標は無効（{name}）",
            not any(statement_invokes(st, name) for st in py_strings),
        )
    check(
        "D5: 対の正ケース（コード側に指標があれば検出する）",
        any(
            statement_invokes(st, "check_real.py")
            for st in (python_statements('subprocess.run(["tools/check_real.py"])\n') or [])
        ),
    )
    # D6: --self-test の除外が同一コマンド内に限定されている（論理行連結との干渉・#164 レビュー）
    py_pair = python_statements(
        'CHECKS = [["python3", "tools/check_pair.py"], ["python3", "tools/check_pair.py", "--self-test"]]\n'
    )
    assert py_pair is not None
    check(
        "D6: 本判定と self-test が 1 論理行に畳まれても本判定を検出する",
        any(statement_invokes(st, "check_pair.py") for st in py_pair),
    )
    py_only_selftest = python_statements(
        'CHECKS = [["python3", "tools/check_only.py", "--self-test"]]\n'
    )
    assert py_only_selftest is not None
    check(
        "D6: self-test だけなら検出しない（対の負ケース）",
        not any(statement_invokes(st, "check_only.py") for st in py_only_selftest),
    )
    # D7: 行末 `\` の継続行連結（実コーパスに 11 本ある書き方）。
    #     1 行目だけでは「ファイル名なし」、2 行目だけでは「実行指標なし・コマンド位置でもない」
    #     となる形にしてある（連結しなければ検出できない＝連結の有無を実際に問うテスト）。
    cont = shell_statements('run_check "alpha" python3 \\\n  --repo-root . tools/check_alpha.py\n')
    check(
        "D7: 行末 \\ の継続行を 1 論理行として連結する",
        any(statement_invokes(st, "check_alpha.py") for st in cont),
    )
    check(
        "D7: 連結前の各行は単独では検出されない（対の負ケース）",
        not statement_invokes("  --repo-root . tools/check_alpha.py", "check_alpha.py"),
    )

    # ── M: Markdown はコードブロック内だけを実行とみなす（#164 レビュー実測） ──
    md_fenced = markdown_statements("説明の段落\n" + _fence("python3 tools/check_md.py --json"))
    check(
        "M1: フェンス内の実行行を検出する",
        any(statement_invokes(st, "check_md.py") for st in md_fenced),
    )
    md_prose = markdown_statements(
        "`apply-to-repo.sh` は `tools/check_md.py` を python3 で自動実行し、結果を表示する。\n"
    )
    check(
        "M2: 指標語を含む散文は実行とみなさない",
        not any(statement_invokes(st, "check_md.py") for st in md_prose),
    )
    md_negated = markdown_statements(
        "- 検査は python3 が無い環境では `check_md.py` が実行されないためスキップされる。\n"
    )
    check(
        "M3: 否定文（実行しない旨の地の文）は実行とみなさない",
        not any(statement_invokes(st, "check_md.py") for st in md_negated),
    )

    # ── E: マーカー（実コメントのみ有効・理由が空なら無効） ──
    src_marker = (
        "#!/usr/bin/env python3\n"
        "# tool-wiring-ok: 並列委譲の直前に親セッションが手で実行する運用ツール\n"
    )
    check(
        "E1: 理由付きマーカーを拾う",
        marker_reason(src_marker) == "並列委譲の直前に親セッションが手で実行する運用ツール",
    )
    v_e1 = evaluate_script("check_marked.py", src_marker, [])
    check("E1: 判定は excluded", v_e1.status == "excluded")

    src_empty = "#!/usr/bin/env python3\n# tool-wiring-ok:\n"
    check("E2: 理由が空なら marker_reason は None", marker_reason(src_empty) is None)
    v_e2 = evaluate_script("check_empty.py", src_empty, [])
    check("E2: 判定は violation（無効マーカーは除外しない）", v_e2.status == "violation")
    check("E2: invalid_marker フラグが立つ", v_e2.invalid_marker)
    check("E3: 空白のみの理由も無効", marker_reason("# tool-wiring-ok:   \n") is None)

    src_doc_marker = (
        "#!/usr/bin/env python3\n"
        '"""書式の説明:\n'
        "    # tool-wiring-ok: これは例示であって本物のマーカーではない\n"
        '"""\n'
    )
    check("E4: docstring 内の言及はマーカーではない", marker_reason(src_doc_marker) is None)
    check(
        "E4: 判定は violation（誤って excluded されない）",
        evaluate_script("check_doc.py", src_doc_marker, []).status == "violation",
    )
    # E5: 解析できないファイルは「死蔵」ではなく「判定不能」（マーカーも読めないため）
    v_e5 = evaluate_script("check_broken.py", "def f(:\n", [])
    check("E5: 解析不能は undetermined（死蔵に丸めない）", v_e5.status == "undetermined")

    # ── F: 要素間の関係が不正な負ケース（各要素は妥当だが集合として不正） ──
    src_mixed = "# tool-wiring-ok:\n# 他のコメント\n# tool-wiring-ok: 有効な理由\n"
    check("F1: 複数マーカー中の有効な理由を拾う", marker_reason(src_mixed) == "有効な理由")
    check("F1: 空マーカーの存在も同時に記録する", has_invalid_empty_marker(src_mixed))
    check(
        "F1: 有効な理由が 1 つでもあれば excluded",
        evaluate_script("check_mixed.py", src_mixed, []).status == "excluded",
    )
    only_selftest = _src('run_check "a self-test" python3 tools/check_alpha.py --self-test')
    check(
        "F2: self-test 呼び出しだけなら violation",
        evaluate_script("check_alpha.py", "", [only_selftest]).status == "violation",
    )
    both = _src(
        'run_check "a self-test" python3 tools/check_alpha.py --self-test',
        'run_check "a" python3 tools/check_alpha.py',
    )
    check(
        "F2: 本判定が 1 行でもあれば wired（回帰防止）",
        evaluate_script("check_alpha.py", "", [both]).status == "wired",
    )
    self_ref = Source(
        label="tools/check_alpha.py",
        filename="check_alpha.py",
        statements=[Statement("python3 tools/check_alpha.py", "python3 tools/check_alpha.py", "sh")],
    )
    check(
        "F3: 自己参照は実行場所にならない",
        evaluate_script("check_alpha.py", "", [self_ref]).status == "violation",
    )

    # ── G: main() を貫通させ、終了コードまで検証する（本番の入口・#686） ──
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # G1: 死蔵あり → exit 1
        _write_fixture_repo(
            root,
            run_checks='run_check "alpha" python3 tools/check_alpha.py\n',
            tools={
                "check_alpha.py": "print(1)\n",
                "check_ghost.py": "print(2)\n",  # どこからも呼ばれない
            },
        )
        check("G1: 死蔵ありで exit 1", _silent_main(["--repo-root", str(root)]) == 1)

        # G2: マーカーで除外すると exit 0
        (root / "tools" / "check_ghost.py").write_text(
            "# tool-wiring-ok: 定期スロットからのみ起動する運用ツール\nprint(2)\n",
            encoding="utf-8",
        )
        check("G2: マーカー除外で exit 0", _silent_main(["--repo-root", str(root)]) == 0)

        # G3: --json でも同じ終了コードになる
        check("G3: --json でも exit 0", _silent_main(["--repo-root", str(root), "--json"]) == 0)

    with tempfile.TemporaryDirectory() as td2:
        root2 = Path(td2)
        # G4: run_checks.sh が無い → 判定不能 exit 2（0 に丸めない）
        (root2 / "tools").mkdir(parents=True)
        (root2 / "tools" / "check_alpha.py").write_text("print(1)\n", encoding="utf-8")
        check("G4: run_checks.sh 不在は exit 2", _silent_main(["--repo-root", str(root2)]) == 2)

        # G5: 走査対象 0 件 → fail-closed の exit 2（PASS にしない）
        (root2 / "tools" / "run_checks.sh").write_text("echo hi\n", encoding="utf-8")
        (root2 / "tools" / "check_alpha.py").unlink()
        check("G5: 走査対象 0 件は exit 2（fail-closed）", _silent_main(["--repo-root", str(root2)]) == 2)

        # G6: tools/ ごと無い → exit 2
        check(
            "G6: tools/ 不在は exit 2",
            _silent_main(["--repo-root", str(root2 / "nonexistent")]) == 2,
        )

    # G7: 非 UTF-8 の check_*.py はクラッシュせず判定不能（exit 2）
    with tempfile.TemporaryDirectory() as td3:
        root3 = Path(td3)
        _write_fixture_repo(
            root3,
            run_checks='run_check "alpha" python3 tools/check_alpha.py\n',
            tools={"check_alpha.py": "print(1)\n"},
        )
        (root3 / "tools" / "check_broken.py").write_bytes(b"# \xff\xfe not utf-8\nprint(1)\n")
        check("G7: 非 UTF-8 の対象は exit 2（判定不能）", _silent_main(["--repo-root", str(root3)]) == 2)

    # G8: 構文エラーの check_*.py も判定不能（❌ 死蔵と表示して出口なしにしない）
    with tempfile.TemporaryDirectory() as td4:
        root4 = Path(td4)
        _write_fixture_repo(
            root4,
            run_checks='run_check "alpha" python3 tools/check_alpha.py\n',
            tools={"check_alpha.py": "print(1)\n", "check_syntax.py": "def f(:\n"},
        )
        check("G8: 構文エラーの対象は exit 2（判定不能）", _silent_main(["--repo-root", str(root4)]) == 2)

    # ── H: 参照元 glob ごとの positive（1 経路の走査を消したら 1 件ずつ落ちる） ──
    route_cases: list[tuple[str, dict[str, object]]] = [
        ("run_checks.sh", {"run_checks": 'run_check "r" python3 tools/check_route.py\n'}),
        ("hooks", {"hooks": {"h.sh": "python3 tools/check_route.py --json\n"}}),
        ("skills/SKILL.md", {"skills": {"s/SKILL.md": _fence("python3 tools/check_route.py")}}),
        (
            "skills/reference.md",
            {"skills": {"s/reference.md": _fence("python3 tools/check_route.py")}},
        ),
        ("commands", {"commands": {"c.md": _fence("python3 tools/check_route.py")}}),
        ("scripts/*.sh", {"scripts": {"x.sh": "python3 tools/check_route.py\n"}}),
        (
            "scripts/*.py",
            {"scripts": {"x.py": 'subprocess.run(["tools/check_route.py"])\n'}},
        ),
        (
            "tools/*.py",
            {"tool_sources": {"other_tool.py": 'subprocess.run(["tools/check_route.py"])\n'}},
        ),
        ("tools/*.sh", {"tool_sources": {"other.sh": "python3 tools/check_route.py\n"}}),
    ]
    for label, kwargs in route_cases:
        with tempfile.TemporaryDirectory() as tdr:
            rootr = Path(tdr)
            _write_fixture_repo(rootr, tools={"check_route.py": "print(1)\n"}, **kwargs)  # type: ignore[arg-type]
            check(f"H: {label} からの実行のみで wired（exit 0）", _silent_main(["--repo-root", str(rootr)]) == 0)

    # H0: どの経路にも書かなければ死蔵（上記 positive の対になる負ケース）
    with tempfile.TemporaryDirectory() as tdn:
        rootn = Path(tdn)
        _write_fixture_repo(rootn, tools={"check_route.py": "print(1)\n"})
        check("H0: どこからも呼ばれなければ exit 1", _silent_main(["--repo-root", str(rootn)]) == 1)

    # ── I: 明示リスト（check_*.py グロブに載らない対象も走査する） ──
    check("I0: 明示リストが空でない（空にすると死蔵検査の対象が静かに減る）", bool(_EXTRA_TARGETS))
    for _extra in _EXTRA_TARGETS[:1]:
      with tempfile.TemporaryDirectory() as tdx:
          rootx = Path(tdx)
          _write_fixture_repo(
              rootx,
              run_checks='run_check "alpha" python3 tools/check_alpha.py\n',
              tools={"check_alpha.py": "print(1)\n"},
              tool_sources={_extra: "print(1)\n"},
          )
          check(
              f"I1: 明示リスト（{_extra}）も死蔵検査の対象",
              _silent_main(["--repo-root", str(rootx)]) == 1,
          )
          (rootx / "tools" / "run_checks.sh").write_text(
              'run_check "alpha" python3 tools/check_alpha.py\n'
              f'run_check "extra" python3 tools/{_extra} check\n',
              encoding="utf-8",
          )
          check(
              f"I2: 明示リストも配線すれば exit 0（{_extra}）",
              _silent_main(["--repo-root", str(rootx)]) == 0,
          )

    if failures:
        print("❌ check_tool_wiring --self-test FAILED:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print(f"✅ check_tool_wiring --self-test PASSED（{assertions} 件のアサーション全て成功）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="tools/check_*.py の死蔵（実行場所なし）を検査する")
    parser.add_argument("--json", action="store_true", help="機械可読 JSON で出力する")
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="走査するリポジトリルート（既定: 本スクリプトの親ディレクトリ。self-test で使う）",
    )
    # tool-wiring-ok は不要（本スクリプト自身は run_checks.sh に本判定を配線する）
    parser.add_argument(
        "--self-test", action="store_true", help="検出ロジック自体のユニットテストを実行"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    repo_root = Path(args.repo_root).resolve()
    tools_dir = repo_root / "tools"
    if not tools_dir.is_dir():
        print(f"⚠️  {tools_dir} が見つかりません（判定不能）", file=sys.stderr)
        return 2
    if not (tools_dir / "run_checks.sh").is_file():
        print(f"⚠️  {tools_dir / 'run_checks.sh'} が見つかりません（判定不能）", file=sys.stderr)
        return 2

    sources, source_problems = collect_sources(repo_root)
    report = scan(repo_root, sources)

    # 走査対象 0 件は fail-closed（対象の選択が壊れている可能性と区別できないため・
    # check-tool-design-rules.md §2）。tools/check_*.py が 0 本の状態は正常ではない。
    if report.total == 0:
        print(
            "⚠️  走査対象（tools/check_*.py）が 0 件でした（判定不能）。"
            "対象の選択が意図どおりか確認してください",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(render_json(report))
    else:
        print(render_human(report))

    for label, reason in source_problems:
        print(f"⚠️  参照元を読めませんでした（判定不能）: {label}（{reason}）", file=sys.stderr)
    for name, reason in report.undetermined:
        print(f"⚠️  対象を解析できませんでした（判定不能）: {name}（{reason}）", file=sys.stderr)

    if report.violations:
        print(f"❌ 死蔵 {len(report.violations)} 件（実行場所なし）", file=sys.stderr)
        return 1
    if report.undetermined or source_problems:
        # 「読めなかった」は 0（死蔵なし）にも 1（死蔵あり）にも丸めない（#445）。
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
