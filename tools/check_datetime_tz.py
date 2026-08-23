#!/usr/bin/env python3
"""check_datetime_tz.py — 表示・記録系の TZ 未指定 datetime 残存チェック（Issue #80 / #445）

`docs/rules/datetime-rules.md` の SSOT に従い、表示・記録に使うと
コンテナのローカル TZ に依存して不定になる **TZ 未指定（naive）の datetime** を検出する。

検出対象（naive = 表示・記録に使うと壊れる。実際に実行されるコードのみ）:
  - `datetime.utcnow()` / `datetime.utcnow`（呼び出さず参照渡しする default 等も含む）
  - `datetime.now()`（引数なし）
  - `datetime.today()`（引数なし）

検出しない（正しい使い方・または対象外）:
  - `datetime.now(timezone.utc)` / `datetime.now(JST)` など引数ありの aware 呼び出し
  - `# tz-ok` を同じ行に書いた箇所（明示的に許可・レビュー済みの例外）
  - **docstring・コメント・文字列リテラル内の記述**（Issue #445 で解消）。
    本ツールは Python の `ast` モジュールで実際のコード（`Call` / `Attribute` ノード）だけを
    走査する。「`datetime.utcnow()` を使わない」という禁止事項を説明する docstring 中の
    引用文字列は Python 文法上 `Constant`（文字列）ノードにしかならず `Call`/`Attribute` には
    ならないため、走査対象に含まれない。行単位の正規表現で走査していた旧実装は、この
    区別ができずルール文の引用まで誤検出していた。

使い方:
  python3 tools/check_datetime_tz.py             # リポジトリ全体の *.py を検査
  python3 tools/check_datetime_tz.py --changed   # main との差分 *.py のみ検査
  python3 tools/check_datetime_tz.py --self-test # ネットワーク非依存のユニットテスト
  違反があれば exit 1（CI / セルフレビューでガードレール化できる）。
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOW_MARKER = "# tz-ok"
# 引数なしで呼ばれたときだけ naive（`datetime.now(tz)` 等の aware 呼び出しは対象外）。
NAIVE_NO_ARG_METHODS = {"now", "today"}
# 呼び出しの有無を問わず常に naive（`datetime.utcnow()` も `default=datetime.utcnow` も対象）。
NAIVE_BARE_ATTRS = {"utcnow"}

# 自分自身は検査しない（走査コスト削減。誤検出自体は ast 化により既に解消済み）。
EXCLUDE_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env"}
EXCLUDE_FILES = {"check_datetime_tz.py"}


def _py_files_all() -> list[Path]:
    out = []
    for p in REPO_ROOT.rglob("*.py"):
        if p.name in EXCLUDE_FILES:
            continue
        if EXCLUDE_PARTS & set(p.relative_to(REPO_ROOT).parts):
            continue
        out.append(p)
    return out


def _py_files_changed() -> list[Path]:
    try:
        base = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "merge-base", "HEAD", "origin/main"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip() or "origin/main"
        diff = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "--name-only", base, "HEAD"],
            capture_output=True, text=True, timeout=15,
        )
        if diff.returncode != 0:
            # 失敗を握りつぶすと「検査スキップ」が「検出なし(PASS)」に化ける偽陰性になるため警告する。
            print(f"Warning: git diff 失敗（--changed 検査をスキップ）: {diff.stderr.strip()}", file=sys.stderr)
            return []
        names = diff.stdout.splitlines()
    except Exception as e:
        print(f"Warning: 変更ファイル取得に失敗（--changed 検査をスキップ）: {e}", file=sys.stderr)
        return []
    files = []
    for n in names:
        if not n.endswith(".py") or n in EXCLUDE_FILES:
            continue
        p = REPO_ROOT / n
        if p.exists() and not (EXCLUDE_PARTS & set(Path(n).parts)):
            files.append(p)
    return files


def _dotted_chain(node: ast.AST) -> str | None:
    """Attribute/Name チェーンをドット区切り文字列に変換する（起点が Name でない複雑な式は None）。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _naive_attr_name(node: ast.Attribute) -> str | None:
    """`<...>.datetime.<attr>` 形式の Attribute なら `<attr>` を返す（そうでなければ None）。

    `datetime.now` はもちろん `_dt.datetime.now` のようにモジュールへのエイリアス経由の
    参照でも、直前の要素が `datetime` である限り拾う（旧・正規表現実装と同じ許容範囲）。
    """
    chain = _dotted_chain(node)
    if not chain or "." not in chain:
        return None
    base, _, attr = chain.rpartition(".")
    if base.rsplit(".", 1)[-1] == "datetime":
        return attr
    return None


def scan(path: Path) -> list[tuple[int, str]]:
    """実際に実行されるコード（ast の Call / Attribute ノード）だけを走査して naive datetime を検出する。

    docstring・コメント・文字列リテラルは Python の文法上 `Call`/`Attribute` にならないため、
    この方式では自動的に走査対象から外れる（#445 の根治）。
    """
    hits: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return hits
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        # Python として構文解析できないファイル（生成物・テンプレート等）は対象外。
        return hits

    lines = text.splitlines()
    seen_linenos: set[int] = set()

    def _record(node: ast.AST) -> None:
        lineno = getattr(node, "lineno", None)
        if lineno is None or lineno in seen_linenos:
            return
        line_text = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        if ALLOW_MARKER in line_text:
            return
        seen_linenos.add(lineno)
        hits.append((lineno, line_text.strip()))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = _naive_attr_name(node.func)
            if attr in NAIVE_NO_ARG_METHODS and not node.args and not node.keywords:
                _record(node)
        elif isinstance(node, ast.Attribute):
            # 呼び出し有無を問わず naive な utcnow は、Call に包まれていてもいなくても
            # ast.walk が Attribute ノード自体を独立して辿るのでここで一括して拾える。
            attr = _naive_attr_name(node)
            if attr in NAIVE_BARE_ATTRS:
                _record(node)

    return hits


def run_self_test() -> int:
    """ネットワーク非依存のユニットテスト（Issue #445）。

    - 実際に実行されるコードでの naive datetime 呼び出しは引き続き検出できること
    - docstring / コメント / 文字列リテラル内の記述は検出しないこと（本 Issue の回帰防止）
    - aware 呼び出し・`# tz-ok` 抑制は引き続き無視されること
    """
    cases: list[tuple[str, str, int]] = [
        # (ケース名, ソースコード, 期待する検出件数)
        ("naive now()", "x = datetime.now()\n", 1),
        ("naive today()", "x = datetime.today()\n", 1),
        ("naive utcnow() call", "x = datetime.utcnow()\n", 1),
        ("naive utcnow bare ref（default 引数渡し等）", "f = datetime.utcnow\n", 1),
        ("モジュールエイリアス経由の naive now()", "x = _dt.datetime.now()\n", 1),
        (
            "docstring がルール文を引用しているだけなら違反ではない（#445 本体）",
            '"""ルール説明: `datetime.utcnow()` や TZ 未指定 `datetime.now()` は使わない。"""\n'
            "x = 1\n",
            0,
        ),
        (
            "コメントがルール文を引用しているだけなら違反ではない",
            "# datetime.utcnow() は禁止\n"
            "x = 1\n",
            0,
        ),
        (
            "文字列リテラルがルール文を引用しているだけなら違反ではない",
            'msg = "datetime.now() を呼ぶと壊れる"\n',
            0,
        ),
        ("aware: datetime.now(timezone.utc)", "x = datetime.now(timezone.utc)\n", 0),
        ("aware: datetime.now(tz=JST)", "x = datetime.now(tz=JST)\n", 0),
        ("# tz-ok は本物の違反も抑制する", "x = datetime.now()  # tz-ok\n", 0),
    ]

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "sample.py"
        for name, src, expected in cases:
            tmp_path.write_text(src, encoding="utf-8")
            hits = scan(tmp_path)
            if len(hits) != expected:
                failures.append(f"- {name}: expected {expected} 件, got {len(hits)} 件 {hits}")

    if failures:
        print("FAIL: check_datetime_tz self-test", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 1

    print(f"OK: check_datetime_tz self-test 全 {len(cases)} ケース通過")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return run_self_test()

    changed = "--changed" in sys.argv
    files = _py_files_changed() if changed else _py_files_all()

    violations = 0
    for f in sorted(files):
        for lineno, snippet in scan(f):
            violations += 1
            rel = f.relative_to(REPO_ROOT)
            print(f"{rel}:{lineno}: TZ 未指定 datetime（表示・記録に使うと不定）: {snippet}")

    scope = "変更 .py" if changed else "全 .py"
    if violations:
        print(
            f"\n❌ {violations} 件の TZ 未指定 datetime を検出（{scope}・{len(files)} ファイル走査）。\n"
            "   表示・記録用途なら datetime.now(JST)、機械処理用 UTC なら datetime.now(timezone.utc) を使う。\n"
            "   レビュー済みの正当な例外は行末に `# tz-ok` を付けて抑制できる（datetime-rules.md §2）。",
            file=sys.stderr,
        )
        return 1
    print(f"✅ TZ 未指定 datetime は検出なし（{scope}・{len(files)} ファイル走査）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
