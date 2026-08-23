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
  - `# tz-ok` を **呼び出しの開始行〜終了行のいずれかの行** に書いた箇所（明示的に許可・
    レビュー済みの例外）。複数行にまたがる呼び出しなら閉じ括弧の行に書いても抑制される
    （同じ行に書かないと効かない、という旧仕様ではない・#445 問題2 で修正）
  - **docstring・コメント・文字列リテラル内の記述**（Issue #445 で解消）。
    本ツールは Python の `ast` モジュールで実際のコード（`Call` / `Attribute` ノード）だけを
    走査する。「`datetime.utcnow()` を使わない」という禁止事項を説明する docstring 中の
    引用文字列は Python 文法上 `Constant`（文字列）ノードにしかならず `Call`/`Attribute` には
    ならないため、走査対象に含まれない。行単位の正規表現で走査していた旧実装は、この
    区別ができずルール文の引用まで誤検出していた
  - 【既知の制約・スコープ外】`from datetime import datetime as dt` のように `datetime` クラス
    自体をエイリアス束縛して `dt.now()` と呼ぶ形は検出しない（旧・正規表現実装も同じ制約
    だったため #445 の後退ではない。属性チェーンの直前要素が文字列 `"datetime"` であることを
    条件にしているため）

解析不能時の挙動（構文エラー・デコードエラー等）:
  対象 `.py` が構文解析できない場合（構文エラー・非 UTF-8・NUL バイト・病的な深いネスト等）は
  「違反なし」として黙殺せず、**検査全体を非ゼロ終了にする**（stderr に対象ファイルを明示）。
  無関係な `.py` が壊れているだけで TZ 違反があるかのように exit 1 になるので、その `.py` 自体
  を修正するか検査対象から外す（`docs/rules/datetime-rules.md` §3 参照）。

使い方:
  python3 tools/check_datetime_tz.py             # リポジトリ全体の *.py を検査
  python3 tools/check_datetime_tz.py --changed   # main との差分 *.py のみ検査
  python3 tools/check_datetime_tz.py --self-test # ネットワーク非依存のユニットテスト
  違反があれば exit 1（CI / セルフレビューでガードレール化できる）。
"""
from __future__ import annotations

import ast
import contextlib
import io
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class ScanError(Exception):
    """`ast.parse` に失敗したファイルを表す例外。

    解析不能は「違反なし」ではないため黙殺せず呼び出し側（main / self-test）へ伝播させる
    （#445 問題1: 構文エラーのある .py を握りつぶして exit 0 にしてしまう後退の修正）。
    """


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


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """`id(子ノード) -> 親ノード` の対応表を作る（ast 標準には親リンクがないため自前で構築）。

    `datetime.utcnow()` のように `Attribute` が `Call` の `func` として使われている場合、
    親の `Call` を辿れないと呼び出し全体（閉じ括弧まで）の行範囲が分からず、複数行呼び出しの
    閉じ括弧行に書いた `# tz-ok` を正しく認識できない（#445 CRITICAL3）。
    """
    parent_map: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[id(child)] = parent
    return parent_map


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
    except (UnicodeDecodeError, OSError) as e:
        # 読み込み失敗も「違反なし」ではない。#445 問題1 とまったく同じ失敗モードが
        # ここでも起こり得る（非 UTF-8 バイト列の .py を黙殺して PASS 扱いにする）ため、
        # ast.parse の失敗と同様に ScanError へ集約して呼び出し側へ伝播させる（CRITICAL1）。
        raise ScanError(f"{path}: 読み込みに失敗（{e.__class__.__name__}: {e}）") from e
    try:
        tree = ast.parse(text, filename=str(path))
    except (SyntaxError, RecursionError, MemoryError, ValueError) as e:
        # 解析不能は「違反なし」ではない。黙殺すると検査全体が偽陰性化するため、
        # 呼び出し側（main / self-test）に判断を委ねられるよう例外として伝播させる
        # （#445 問題1）。SyntaxError 以外にも、病的に深いネスト式による RecursionError・
        # 極端に巨大なファイルでの MemoryError・NUL バイト混入時の ValueError（Python の
        # バージョンによっては SyntaxError ではなくこちらで送出される）も同様に扱う
        # （CRITICAL4）。
        raise ScanError(f"{path}: 構文解析に失敗（{e.__class__.__name__}: {e}）") from e

    lines = text.splitlines()
    seen_linenos: set[int] = set()
    parent_map = _build_parent_map(tree)

    def _record(node: ast.AST) -> None:
        lineno = getattr(node, "lineno", None)
        if lineno is None or lineno in seen_linenos:
            return
        # 複数行にまたがる呼び出しは、開始行〜終了行のどこに `# tz-ok` を書いても抑制する
        # （閉じ括弧の行に書くのが自然なため・#445 問題2）。
        end_lineno = getattr(node, "end_lineno", None) or lineno
        for ln in range(lineno, end_lineno + 1):
            line_text = lines[ln - 1] if 0 < ln <= len(lines) else ""
            if ALLOW_MARKER in line_text:
                return
        line_text = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
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
                # `datetime.utcnow()` のように Call の func として使われている場合は、
                # 親の Call ノードを渡して範囲（end_lineno）を呼び出し全体に揃える。
                # Attribute 自体の end_lineno は属性名の行までしかなく、複数行呼び出しの
                # 閉じ括弧行の `# tz-ok` を見落とすため（#445 CRITICAL3）。
                parent = parent_map.get(id(node))
                target = parent if isinstance(parent, ast.Call) and parent.func is node else node
                _record(target)

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
        (
            "複数行呼び出しでも naive なら検出する（回帰防止・#445 問題2 併設ケース）",
            "x = datetime.now(\n)\n",
            1,
        ),
        (
            "複数行呼び出しは閉じ括弧の行の # tz-ok でも抑制される（#445 問題2）",
            "x = datetime.now(\n)  # tz-ok\n",
            0,
        ),
        (
            "複数行 utcnow() 呼び出しでも naive なら検出する（回帰防止・CRITICAL3 併設ケース）",
            "x = datetime.utcnow(\n)\n",
            1,
        ),
        (
            "複数行 utcnow() 呼び出しは閉じ括弧の行の # tz-ok でも抑制される"
            "（#445 CRITICAL3: Attribute と Call の非対称性を解消）",
            "x = datetime.utcnow(\n)  # tz-ok\n",
            0,
        ),
    ]

    # 構文エラーのある .py は黙殺せず ScanError を送出しなければならない（#445 問題1・後退防止）。
    parse_error_cases: list[tuple[str, str]] = [
        (
            "構文エラーのある .py（内部に本物の violation あり）は黙殺せず ScanError を送出する",
            "def broken(:\n    x = datetime.now()\n",
        ),
    ]

    # 非 UTF-8 バイト列を含む .py も同様に黙殺してはならない（#445 CRITICAL1: read_text の
    # `except Exception: return hits` が UnicodeDecodeError を握りつぶし、旧問題1 とまったく
    # 同じ「検出不能を PASS と誤認させる」失敗モードを別経路で再現していた）。
    parse_error_byte_cases: list[tuple[str, bytes]] = [
        (
            "非 UTF-8 バイト列（内部に本物の violation あり）は黙殺せず ScanError を送出する",
            b"x = datetime.now()\n# \xff\xfe invalid utf-8\n",
        ),
    ]

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "sample.py"
        for name, src, expected in cases:
            tmp_path.write_text(src, encoding="utf-8")
            hits = scan(tmp_path)
            if len(hits) != expected:
                failures.append(f"- {name}: expected {expected} 件, got {len(hits)} 件 {hits}")

        for name, src in parse_error_cases:
            tmp_path.write_text(src, encoding="utf-8")
            try:
                hits = scan(tmp_path)
            except ScanError:
                pass
            else:
                failures.append(
                    f"- {name}: ScanError が送出されず黙殺された（got {hits}・解析不能を「検出なし」に化かしている）"
                )

        for name, raw in parse_error_byte_cases:
            tmp_path.write_bytes(raw)
            try:
                hits = scan(tmp_path)
            except ScanError:
                pass
            else:
                failures.append(
                    f"- {name}: ScanError が送出されず黙殺された（got {hits}）"
                )

        # RecursionError も黙殺してはならない（#445 CRITICAL4）。実環境の再帰上限に依存させず
        # 決定論的に再現するため、この 1 ケースに限りテスト実行中だけ再帰上限を下げる。
        recursion_case_name = (
            "病的に深いネスト式で RecursionError になっても黙殺せず ScanError を送出する"
        )
        old_limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(60)
            deep_src = "x = " + ("not " * 500) + "True\n"
            tmp_path.write_text(deep_src, encoding="utf-8")
            try:
                hits = scan(tmp_path)
            except ScanError:
                pass
            except RecursionError:
                failures.append(
                    f"- {recursion_case_name}: RecursionError が ScanError に変換されず生で漏れた"
                )
            else:
                failures.append(
                    f"- {recursion_case_name}: 例外が送出されず黙殺された（got {hits}）"
                )
        finally:
            sys.setrecursionlimit(old_limit)

        # main() の判定ロジック（_run）は scan() の 3 ケース（違反あり／解析不能／両方なし）を
        # 通してこそ意味を持つ。--self-test が scan() しか呼ばず main() 相当の集計・終了コード
        # 判定を一切カバーしていなかった（#445 CRITICAL2）ため、一時ディレクトリを走査対象にして
        # `_run()` を直接呼ぶ統合ケースを足す。
        clean_path = Path(tmp_dir) / "clean.py"
        clean_path.write_text("x = datetime.now(timezone.utc)\n", encoding="utf-8")
        violation_path = Path(tmp_dir) / "violation.py"
        violation_path.write_text("x = datetime.now()\n", encoding="utf-8")
        broken_path = Path(tmp_dir) / "broken.py"
        broken_path.write_text("def broken(:\n    pass\n", encoding="utf-8")

        integration_cases: list[tuple[str, list[Path], int, list[str]]] = [
            ("_run(): 違反ありなら exit 1", [violation_path], 1, ["❌"]),
            (
                "_run(): 構文エラーのみでも exit 1 かつ ⚠️ 解析不能を明示",
                [broken_path],
                1,
                ["⚠️", "解析不能のため検査対象外", "構文解析できず検査不能"],
            ),
            ("_run(): 違反ゼロなら exit 0", [clean_path], 0, ["✅"]),
            (
                # 「構文解析できず検査不能」は parse_failures の集計（サマリー）メッセージにしか
                # 出ない文言。violations が真になった時点で早期 return すると、この集計だけが
                # 欠落したまま exit 1 にはなる（＝終了コードだけ見ると気づけない後退）ため、
                # サマリー文言そのものをマーカーにして固定する（#445 NIT5）。
                "_run(): 違反と解析不能が同時発生しても両方の集計メッセージを出してから exit 1（#445 NIT5）",
                [violation_path, broken_path],
                1,
                ["❌", "TZ 未指定 datetime を検出", "構文解析できず検査不能"],
            ),
        ]
        for name, files, expected_code, expected_markers in integration_cases:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = _run(files, Path(tmp_dir), "test")
            combined = out.getvalue() + err.getvalue()
            if code != expected_code:
                failures.append(f"- {name}: expected exit {expected_code}, got {code}")
            missing = [m for m in expected_markers if m not in combined]
            if missing:
                failures.append(f"- {name}: 出力に {missing} が含まれない（出力: {combined!r}）")

    if failures:
        print("FAIL: check_datetime_tz self-test", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 1

    print(f"OK: check_datetime_tz self-test 全 {len(cases)} ケース通過")
    return 0


def _run(files: list[Path], root: Path, scope: str) -> int:
    """`files`（`root` からの相対パス表示用）を走査し、判定メッセージを出して終了コードを返す。

    `main()` から実ファイル走査部分を切り出したもの。`--self-test` から `root` に一時
    ディレクトリを渡して直接呼べるため、`main()` 自体を subprocess 起動せずに統合的な
    判定ロジック（違反検出→非ゼロ終了・解析不能→非ゼロ終了・両方発生時の集計表示）を
    self-test でカバーできる（#445 問題1 修正時のレビュー指摘 CRITICAL2 対応）。
    """
    violations = 0
    parse_failures = 0
    for f in sorted(files):
        rel = f.relative_to(root)
        try:
            file_hits = scan(f)
        except ScanError as e:
            # 黙殺しない（#445 問題1）: 解析不能は「違反なし」ではないので、
            # stderr に明示した上で検査結果を PASS にしない。
            parse_failures += 1
            print(f"⚠️ {rel}: 解析不能のため検査対象外（{e}）", file=sys.stderr)
            continue
        for lineno, snippet in file_hits:
            violations += 1
            print(f"{rel}:{lineno}: TZ 未指定 datetime（表示・記録に使うと不定）: {snippet}")

    # 違反・解析不能どちらも「あれば集計メッセージを出す」だけにして、片方が真でも
    # もう片方の集計が欠落しないようにする（両方は独立した早期 return にしない・#445 NIT5）。
    if violations:
        print(
            f"\n❌ {violations} 件の TZ 未指定 datetime を検出（{scope}・{len(files)} ファイル走査）。\n"
            "   表示・記録用途なら datetime.now(JST)、機械処理用 UTC なら datetime.now(timezone.utc) を使う。\n"
            "   レビュー済みの正当な例外は呼び出しの開始行〜終了行のいずれかに `# tz-ok` を付けて"
            "抑制できる（datetime-rules.md §2）。",
            file=sys.stderr,
        )
    if parse_failures:
        print(
            f"\n⚠️ {parse_failures} 件の .py を構文解析できず検査不能（{scope}・{len(files)} ファイル走査）。"
            "解析不能は「違反なし」ではないため PASS にしない。上記の対象ファイルを修正するか、"
            "検査対象から外す運用上の理由を明記すること。",
            file=sys.stderr,
        )
    if violations or parse_failures:
        return 1
    print(f"✅ TZ 未指定 datetime は検出なし（{scope}・{len(files)} ファイル走査）。")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return run_self_test()

    changed = "--changed" in sys.argv
    files = _py_files_changed() if changed else _py_files_all()
    scope = "変更 .py" if changed else "全 .py"
    return _run(files, REPO_ROOT, scope)


if __name__ == "__main__":
    sys.exit(main())
