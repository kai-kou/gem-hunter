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

## 「実行場所がある」と認める 5 つの形

いずれか 1 つでもあれば配線済み（`wired`）と判定する。

1. `tools/run_checks.sh` から `--self-test` **以外** で呼ばれている
2. `.claude/hooks/*.sh` から呼ばれている
3. `.claude/skills/**/SKILL.md` に実行指示として書かれている
4. 他の `tools/*.py` / `tools/*.sh` から呼ばれている（間接実行）
5. スクリプト自身に `# tool-wiring-ok: {理由}` マーカーがある

## 「呼ばれている」の判定（誤判定の防止）

単なるファイル名の言及（docstring での参照・「〜は別ツールの担当」といった地の文・
`[ -f ... ]` の存在確認・self-test 用のフィクスチャ文字列）を実行と誤認しないため、
**同一の論理行に実行指標**（`python3` / `python` / `sys.executable` / `subprocess` /
`Popen` / `check_output` / `run_check` / `run_subcheck` / `bash` / `sh`）が
現れることを要求する。判定は次の 3 条件の AND:

- 論理行にファイル名が **語境界付きで** 現れる（`check_foo.py` が `check_foo_bar.py` や
  `xcheck_foo.py` に前方一致・部分一致しないこと。Issue #750 の退行防止）
- 同じ論理行に `--self-test` が **無い**（self-test 実行は本判定の実行場所ではない）
- 同じ論理行に実行指標がある

指標が見つからない書き方は「未配線」（fail-closed）へ倒れる。誤って死蔵を見逃す
（fail-open）よりも、人が 1 度見て判断する方が安全なためである。

さらにソース種別ごとに以下の前処理を行う:

- `*.sh`: クォート外の `#` 以降（シェルコメント）を除去し、行末 `\` の継続行を連結する
- `*.py`: `tokenize` で **実コメントと docstring を除去** し、論理行（`NEWLINE` 区切り）
  単位で判定する（複数行にまたがる `subprocess.run([...])` 呼び出しを取りこぼさない）。
  トークナイズに失敗したファイルは「参照なし」として扱い（安全側）、stderr に警告を出す
- `*.md`: 前処理なし（行末 `\` の継続行のみ連結）。SKILL.md のコードブロックはそのまま実行指示

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
    2 = 判定不能（`tools/` や `run_checks.sh` が見つからない・走査対象が 0 件）

🔴 走査対象 0 件は **PASS にしない**（§2 の fail-closed）。`tools/check_*.py` が 1 本も
無い状態は「対象の選択が壊れている」以外にありえないためである。
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

_SELF_FILENAME = "check_tool_wiring.py"

# 除外マーカー（書式は docstring 参照）。理由は同じ行の行末までとする（`\s*` は改行にも
# マッチするため `[ \t]*` を使う。`\s*` のままだと理由が空のとき次行を誤って呑み込む）。
# ⚠️ 本ファイルの実コメントにマーカー書式を literal で書くと自分自身が除外されるので書かない。
_MARKER_RE = re.compile(r"#[ \t]*tool-wiring-ok:[ \t]*(.*)$", re.MULTILINE)

# 「この論理行は実行である」と認める指標。ファイル名の単なる言及と区別するために要求する。
# 見つからない書き方は未配線（fail-closed）へ倒れるので、指標を増やすときは
# 「実行以外の文脈で頻出しないか」を確認すること。
_EXEC_INDICATOR_RE = re.compile(
    r"\b(?:python3?|sys\.executable|subprocess|Popen|check_output|run_check|run_subcheck|bash|sh)\b"
)

_SELFTEST_TOKEN = "--self-test"


# ─────────────────────────────────────────────────────────────
# マーカー走査（実コメントのみを見る）
# ─────────────────────────────────────────────────────────────


@dataclass
class _MarkerScan:
    """1 ファイルぶんのマーカー走査結果。"""

    reasons: list[str]  # 理由が非空の有効マーカー（出現順）
    has_empty: bool  # 理由が空の無効マーカーが 1 つでもあったか
    tokenize_failed: bool  # tokenize 失敗で「マーカーなし」へ安全側フォールバックしたか


def _comment_texts(content: str) -> list[str] | None:
    """Python としてトークナイズし、実コメントトークンの文字列だけを返す。

    docstring / 文字列リテラルの中身（マーカー書式を説明する地の文など）は含まれない。
    構文エラー・NUL バイト混入等でトークナイズ自体が失敗した場合は `None` を返し、
    呼び出し側は「マーカーなし」として安全側に倒す。
    """
    try:
        return [
            tok.string
            for tok in tokenize.generate_tokens(io.StringIO(content).readline)
            if tok.type == tokenize.COMMENT
        ]
    except Exception:
        # tokenize は SyntaxError / TokenError / ValueError 等を送出しうる。本検査は
        # 死蔵検出が責務であり構文検証ではないため、どんな理由であれクラッシュしない。
        return None


def _scan_markers(content: str) -> _MarkerScan:
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
    """有効な `tool-wiring-ok` マーカーの理由を返す（無ければ None＝除外しない）。"""
    reasons = _scan_markers(content).reasons
    return reasons[0] if reasons else None


def has_invalid_empty_marker(content: str) -> bool:
    """理由が空の（無効な）`tool-wiring-ok` マーカーが存在するか。"""
    return _scan_markers(content).has_empty


# ─────────────────────────────────────────────────────────────
# ソース種別ごとの「論理行」抽出
# ─────────────────────────────────────────────────────────────


def _strip_shell_line_comment(line: str) -> str:
    """bash の 1 行から、クォート外の `#` 以降を取り除く（クォート内の `#` は保持）。"""
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


def shell_statements(content: str) -> list[str]:
    """シェルスクリプトの論理行（コメント除去 + 継続行連結）。"""
    return _join_continuations([_strip_shell_line_comment(line) for line in content.splitlines()])


def markdown_statements(content: str) -> list[str]:
    """Markdown の論理行（継続行のみ連結。コメント概念が無いため除去はしない）。"""
    return _join_continuations(content.splitlines())


def python_statements(content: str) -> list[str] | None:
    """Python の論理行（実コメントと docstring を除去）。

    `subprocess.run([...])` のように複数行へ折り返された呼び出しを 1 つの論理行として
    扱えるよう、`tokenize` の `NEWLINE`（論理行末）で区切る。トークナイズ失敗時は
    `None` を返し、呼び出し側は「このファイルからの参照は無い」として安全側に倒す。
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
    except Exception:
        return None

    statements: list[str] = []
    current: list[str] = []
    # 直前の「意味のある」トークン種別。文の先頭に現れる STRING は docstring とみなす。
    at_statement_start = True
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type in (tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
            continue
        if tok.type == tokenize.NEWLINE:
            if current:
                statements.append(" ".join(current))
                current = []
            at_statement_start = True
            continue
        if tok.type == tokenize.ENDMARKER:
            continue
        if tok.type == tokenize.STRING and at_statement_start:
            # docstring（式文としての文字列）は実行ではないので落とす
            at_statement_start = False
            continue
        current.append(tok.string)
        at_statement_start = False
    if current:
        statements.append(" ".join(current))
    return statements


# ─────────────────────────────────────────────────────────────
# 参照判定
# ─────────────────────────────────────────────────────────────


def _filename_re(filename: str) -> re.Pattern[str]:
    """ファイル名を語境界付きで探す正規表現。

    前方一致・部分一致への退行を防ぐ（`check_foo.py` が `check_foo_bar.py` や
    `xcheck_foo.py` に一致してはならない・Issue #750）。`tools/check_foo.py` のように
    パス区切り `/` が直前に来る形は一致させる。
    """
    return re.compile(
        r"(?<![A-Za-z0-9_.\-])" + re.escape(filename) + r"(?![A-Za-z0-9_])"
    )


def statement_invokes(statement: str, filename: str) -> bool:
    """1 つの論理行が `filename` の **本判定** 実行かどうか。"""
    if _SELFTEST_TOKEN in statement:
        return False  # self-test 実行は本判定の実行場所ではない
    if not _filename_re(filename).search(statement):
        return False
    return bool(_EXEC_INDICATOR_RE.search(statement))


@dataclass
class Source:
    """参照元 1 ファイル（既に論理行へ分解済み）。"""

    label: str  # レポートに出す表示名（リポジトリ相対パス）
    filename: str  # ファイル名（自己参照除外に使う）
    statements: list[str]


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
    status: str  # "wired" | "excluded" | "violation"
    locations: list[str] = field(default_factory=list)
    reason: str | None = None  # excluded のときのマーカー理由
    invalid_marker: bool = False
    tokenize_failed: bool = False


def evaluate_script(filename: str, content: str, sources: list[Source]) -> Verdict:
    """1 ファイルぶんの内容から死蔵判定する（テスト容易性のための純関数）。"""
    marker_scan = _scan_markers(content)
    locations = find_invocations(filename, sources)
    if locations:
        return Verdict(
            filename, "wired", locations=locations, tokenize_failed=marker_scan.tokenize_failed
        )
    if marker_scan.reasons:
        return Verdict(
            filename,
            "excluded",
            reason=marker_scan.reasons[0],
            tokenize_failed=marker_scan.tokenize_failed,
        )
    return Verdict(
        filename,
        "violation",
        invalid_marker=marker_scan.has_empty,
        tokenize_failed=marker_scan.tokenize_failed,
    )


@dataclass
class Report:
    wired: list[tuple[str, list[str]]] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    invalid_markers: list[str] = field(default_factory=list)

    def add(self, v: Verdict) -> None:
        if v.status == "wired":
            self.wired.append((v.filename, v.locations))
        elif v.status == "excluded":
            self.excluded.append((v.filename, v.reason or ""))
        else:
            self.violations.append(v.filename)
            if v.invalid_marker:
                self.invalid_markers.append(v.filename)

    @property
    def total(self) -> int:
        return len(self.wired) + len(self.excluded) + len(self.violations)


def collect_sources(repo_root: Path) -> list[Source]:
    """参照元（run_checks.sh / hooks / SKILL.md / 他 tools）を集める。"""
    sources: list[Source] = []
    paths: list[Path] = []
    paths.extend(sorted((repo_root / "tools").glob("*.py")))
    paths.extend(sorted((repo_root / "tools").glob("*.sh")))
    paths.extend(sorted((repo_root / ".claude" / "hooks").glob("*.sh")))
    paths.extend(sorted((repo_root / ".claude" / "skills").glob("*/SKILL.md")))

    for path in paths:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"⚠️  読み込み失敗のためスキップ: {path}（{e}）", file=sys.stderr)
            continue
        if path.suffix == ".py":
            statements = python_statements(content)
            if statements is None:
                print(
                    f"⚠️  tokenize 失敗のため参照なし扱い（安全側）: {path.name}",
                    file=sys.stderr,
                )
                statements = []
        elif path.suffix == ".sh":
            statements = shell_statements(content)
        else:
            statements = markdown_statements(content)
        try:
            label = str(path.relative_to(repo_root))
        except ValueError:  # pragma: no cover - repo_root 配下以外は来ない
            label = str(path)
        sources.append(Source(label=label, filename=path.name, statements=statements))
    return sources


def scan(repo_root: Path, sources: list[Source]) -> Report:
    report = Report()
    for path in sorted((repo_root / "tools").glob("check_*.py")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"⚠️  読み込み失敗のためスキップ: {path.name}（{e}）", file=sys.stderr)
            continue
        verdict = evaluate_script(path.name, content, sources)
        if verdict.tokenize_failed:
            print(
                f"⚠️  tokenize 失敗のためマーカーなし扱い（安全側）: {path.name}",
                file=sys.stderr,
            )
        report.add(verdict)
    return report


def render_human(report: Report) -> str:
    lines: list[str] = []
    lines.append(
        f"[tool-wiring] 走査対象（tools/check_*.py）: 全 {report.total} 本"
        f"（実行場所あり {len(report.wired)} / マーカー除外 {len(report.excluded)} "
        f"/ 死蔵 {len(report.violations)}）"
    )
    for name in report.violations:
        if name in report.invalid_markers:
            lines.append(
                f"  ❌ 死蔵: {name}（tool-wiring-ok マーカーはあるが理由が空のため無効）"
            )
        else:
            lines.append(
                f"  ❌ 死蔵: {name}"
                "（run_checks.sh / hooks / SKILL.md / 他 tools のどこからも本判定が呼ばれていない）"
            )
    if report.excluded:
        lines.append(f"  ℹ️  マーカーで除外済み: {len(report.excluded)} 件")
        for name, reason in report.excluded:
            lines.append(f"      {name}: {reason}")
    if report.violations:
        lines.append(
            f"[tool-wiring] FAIL: 死蔵 {len(report.violations)} 件"
            "（実行場所を作るか、tool-wiring-ok マーカーで実行場所を明記すること）"
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
        },
        ensure_ascii=False,
        indent=2,
    )


# ─────────────────────────────────────────────────────────────
# --self-test（ネットワーク・実データ非依存）
# ─────────────────────────────────────────────────────────────


def _src(*statements: str) -> Source:
    return Source(label="fixture", filename="fixture.sh", statements=list(statements))


def _write_fixture_repo(root: Path, *, run_checks: str, tools: dict[str, str]) -> None:
    """self-test 用の最小リポジトリを作る（main() を実際に貫通させるため）。"""
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    (root / "tools" / "run_checks.sh").write_text(run_checks, encoding="utf-8")
    for name, body in tools.items():
        (root / "tools" / name).write_text(body, encoding="utf-8")


def _self_test() -> int:
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

    # ── B: 実行ではない言及は検出しない（fail-closed 側の誤検出防止） ──
    check(
        "B1: 存在確認だけの行は実行とみなさない",
        not statement_invokes('if [ -f "$REPO_ROOT/tools/check_alpha.py" ]; then', "check_alpha.py"),
    )
    check(
        "B2: 地の文の言及は実行とみなさない",
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

    # ── C: 境界の外側（#750・前方一致 / 部分一致への退行を捕まえる） ──
    check(
        "C1: check_alpha.py は check_alpha_beta.py の呼び出しに一致しない",
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
        "C4: 対になる正ケース（完全一致なら検出する）",
        statement_invokes("python3 tools/check_alpha.py", "check_alpha.py"),
    )
    check(
        "C5: 長い方の名前は自分自身の呼び出しで検出される",
        statement_invokes("python3 tools/check_alpha_beta.py", "check_alpha_beta.py"),
    )

    # ── D: Python ソースからの間接実行（論理行単位・docstring とコメントを落とす） ──
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
        "D4: 構文エラーの .py は None（参照なし扱い・安全側）",
        python_statements("def f(:\n    pass\n") is None,
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

    # ── F: 要素間の関係が不正な負ケース（各要素は妥当だが集合として不正） ──
    # F1: マーカーが 2 つあり、片方の理由が空 → 有効な方があるので excluded、ただし
    #     有効な理由が 1 つも無ければ空マーカーは救済にならない
    src_mixed = "# tool-wiring-ok:\n# 他のコメント\n# tool-wiring-ok: 有効な理由\n"
    check("F1: 複数マーカー中の有効な理由を拾う", marker_reason(src_mixed) == "有効な理由")
    check("F1: 空マーカーの存在も同時に記録する", has_invalid_empty_marker(src_mixed))
    check(
        "F1: 有効な理由が 1 つでもあれば excluded",
        evaluate_script("check_mixed.py", src_mixed, []).status == "excluded",
    )
    # F2: 同じファイル名が「self-test 実行」と「本判定」の 2 か所に現れる。self-test だけなら死蔵。
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
    # F3: 自分自身の docstring / 使い方例は実行場所として数えない
    self_ref = Source(
        label="tools/check_alpha.py",
        filename="check_alpha.py",
        statements=["python3 tools/check_alpha.py"],
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
        check("G1: 死蔵ありで exit 1", main(["--repo-root", str(root)]) == 1)

        # G2: マーカーで除外すると exit 0
        (root / "tools" / "check_ghost.py").write_text(
            "# tool-wiring-ok: 定期スロットからのみ起動する運用ツール\nprint(2)\n",
            encoding="utf-8",
        )
        check("G2: マーカー除外で exit 0", main(["--repo-root", str(root)]) == 0)

        # G3: --json でも同じ終了コードになる
        check("G3: --json でも exit 0", main(["--repo-root", str(root), "--json"]) == 0)

    with tempfile.TemporaryDirectory() as td2:
        root2 = Path(td2)
        # G4: run_checks.sh が無い → 判定不能 exit 2（0 に丸めない）
        (root2 / "tools").mkdir(parents=True)
        (root2 / "tools" / "check_alpha.py").write_text("print(1)\n", encoding="utf-8")
        check("G4: run_checks.sh 不在は exit 2", main(["--repo-root", str(root2)]) == 2)

        # G5: 走査対象 0 件 → fail-closed の exit 2（PASS にしない）
        (root2 / "tools" / "run_checks.sh").write_text("echo hi\n", encoding="utf-8")
        (root2 / "tools" / "check_alpha.py").unlink()
        check("G5: 走査対象 0 件は exit 2（fail-closed）", main(["--repo-root", str(root2)]) == 2)

        # G6: tools/ ごと無い → exit 2
        check(
            "G6: tools/ 不在は exit 2",
            main(["--repo-root", str(root2 / "nonexistent")]) == 2,
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

    sources = collect_sources(repo_root)
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

    return 1 if report.violations else 0


if __name__ == "__main__":
    sys.exit(main())
