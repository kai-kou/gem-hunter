#!/usr/bin/env python3
"""決定 ID（`D-{数字}`）の参照が `open-questions.md` に実在するかを検査する。

背景（Issue #724）: 決定ログ `docs/02_requirements/open-questions.md` で採番した
`D-n` を、他のドキュメントが参照する際に番号を誤記する事故が起きた（議論記録側の
採番のまま参照が書かれた・footnote 自体の計算違い等）。本ツールは **存在性の検査**
（参照されている `D-n` が決定ログに実在するか）だけを機械化する。

🔴 **機械化できないこと（意図的なスコープ外）**: 参照が「意味的に正しい ID を指して
いるか」（例: 本当は `D-32` の話をしているのに `D-26` と書いてある、のような意味の
取り違え）は自然言語理解が要るため本ツールでは検出できない。存在する ID を誤って
指す事故（今回の Issue #724 のような）は、本ツールでは捕捉できないことに注意する。
これは自己修正の効かない既知の限界であり、意味の一致はレビュー（Layer 1 セルフ
レビュー等）に委ねる。

検査対象: `docs/` `.claude/` `CLAUDE.md` 配下のテキストファイル（.md / .py / .sh / .json）。
決定ログ自身の「ID 定義」は `open-questions.md` の表（`| **D-n** |` 形式の行の先頭
太字セル）から抽出する。`D-5 / D-7`（併記）・`D-5 追補`（ID + 接尾辞）のような
セルも 1 セル内の `D-\\d+` を全て拾うことで定義扱いにする。

🔴 **`content/` は意図的にスコープ外**（PR #743 Layer 1 指摘 #6）: `content/` 配下、
特に `content/discussions/`（議論記録）には `D-n` 参照が多数（実測 1776 件）存在する
が、議論記録は **その時点の採番をそのまま保存する性質のスナップショット** であり、
`docs/02_requirements/open-questions.md` 末尾の「`D-27`〜`D-29` の採番についての
注記」が明示するとおり、議論記録側の表記と決定ログの実 ID がずれることは仕様
（記録の改ざん防止）であって誤記ではない。したがって `content/` を `SCAN_ROOTS` に
足すのは誤り（既知のずれを大量に「未定義参照」として誤検出する）。

参照側の抽出は `(?<![A-Za-z])D-\\d+` で行う。`SD-1`（sprint-development-rules.md
の ID 体系）のように英字が直前に付く語を `D-1` として誤検出しないため、直前に
英字がある場合は除外する（先読みでなく後読み・lookbehind）。

🔴 **判定範囲は大文字 ASCII の `D-n` のみ**（PR #743 Layer 1 指摘 #4・意図した狭さ）:
`re.IGNORECASE` を付けると `grid-1` のような英文中の偶然の `d-1` を誤って `D-1`
扱いしてしまうリスクがあるため、正規表現は大文字 ASCII 限定のまま変えていない。
結果として小文字 `d-77` や全角 `Ｄ-77` は **検出対象外**（検出漏れではなく仕様。
`self_test()` にこれを固定するケースがある＝後任が「バグ」と誤解して直さないため）。

🔴 **シンボリックリンクは走査対象から除外する**（PR #743 Layer 1 指摘: セキュリティ・
CRITICAL）: `Path.rglob()` はシンボリックリンクをそのまま列挙してしまい、リンク先が
リポジトリ外（例: 巨大ファイル・機密ファイルへの symlink）を指していても検証なしに
読み込まれる。`tools/check_e2e_stub_external_urls.py` の `discover_targets()` と
同じ形で ① `path.is_symlink()` でリンクそのものを弾き ② 解決後のパスがリポジトリ配下
に収まっているかを二重に確認する。⚠️ **`.claude/rules/*.md` は個々のファイルが
`docs/rules/*.md` への symlink**（`.claude/rules` ディレクトリ自体は symlink ではない）
なので、本フィルタでちょうどそれらが除外される。実体（`docs/rules/` 側）は `docs`
ルートの走査でそのまま拾われ続けるため、検査範囲は狭まらず二重カウントが消えるだけ。

🔴 **ファイルサイズに上限を設ける**（PR #743 Layer 1 指摘: セキュリティ）: 上限
`MAX_FILE_BYTES` を超えるファイルは読み込まず、`read_errors` と同じ扱いで
fail-closed（`run_check()` が exit 1）にする。黙って skip すると fail-open になり、
巨大ファイル（symlink 経由に限らず）を静かに検査対象から外す抜け道になるため。

使い方:
  python3 tools/check_decision_ids.py            # 検査（違反があれば exit 1）
  python3 tools/check_decision_ids.py --self-test  # 検査ロジック自体の自己テスト
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ["docs", ".claude"]
SCAN_EXTS = {".md", ".py", ".sh", ".json"}
EXTRA_FILES = ["CLAUDE.md"]

# シンボリックリンク経由で読み込むファイルの上限（超過は fail-closed で read_errors 扱い）。
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2MB

# 定義セル抽出: `| **D-5 / D-7** | ...` のような表の先頭太字セル
DEFINITION_ROW_RE = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|")
# 参照抽出: 直前が英字でない `D-<数字>`（`SD-1` 等の複合 ID を誤検出しない）
REFERENCE_RE = re.compile(r"(?<![A-Za-z])D-(\d+)")
# ID を含む定義セル内から数字だけを拾う
ID_IN_CELL_RE = re.compile(r"D-(\d+)")


def load_defined_ids(open_questions_path: Path) -> set[int]:
    """open-questions.md の決定表から定義済み ID の集合を作る。"""
    text = open_questions_path.read_text(encoding="utf-8")
    defined: set[int] = set()
    for line in text.splitlines():
        m = DEFINITION_ROW_RE.match(line)
        if not m:
            continue
        cell = m.group(1)
        for num in ID_IN_CELL_RE.findall(cell):
            defined.add(int(num))
    return defined


def iter_target_files(repo_root: Path = REPO_ROOT) -> list[Path]:
    """検査対象ファイルを列挙する。

    シンボリックリンクは除外する（ファイル冒頭コメント参照）: ① `path.is_symlink()`
    でリンクそのものを弾き ② 念のため解決後のパスが `repo_root` 配下に収まっている
    かを二重に確認する（`tools/check_e2e_stub_external_urls.py` の
    `discover_targets()` と同じ形）。
    """
    resolved_repo_root = repo_root.resolve()
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in SCAN_EXTS:
                continue
            if path.is_symlink():
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if not resolved.is_relative_to(resolved_repo_root):
                continue
            files.append(path)
    for name in EXTRA_FILES:
        path = repo_root / name
        if path.is_file() and not path.is_symlink():
            files.append(path)
    return files


def find_broken_references(
    defined: set[int], files: list[Path], repo_root: Path = REPO_ROOT
) -> tuple[list[tuple[str, int, str, str]], list[str]]:
    """定義に存在しない `D-n` 参照を列挙する。

    戻り値: (違反リスト[(相対パス, 行番号, 参照文字列, 行内容)], 読み取りエラーのファイル一覧)
    サイズ上限超過ファイルも読み取りエラーと同じ扱い（fail-closed）で第 2 戻り値に積む。
    """
    broken: list[tuple[str, int, str, str]] = []
    read_errors: list[str] = []
    for path in files:
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)

        try:
            size = path.stat().st_size
        except OSError as exc:
            read_errors.append(f"{rel}: {exc}")
            continue
        if size > MAX_FILE_BYTES:
            read_errors.append(
                f"{rel}: ファイルサイズが上限（{MAX_FILE_BYTES} bytes）を超過"
                f"（{size} bytes）のため fail-closed で扱う"
            )
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            read_errors.append(f"{rel}: {exc}")
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in REFERENCE_RE.finditer(line):
                num = int(m.group(1))
                if num not in defined:
                    broken.append((rel, lineno, m.group(0), line.strip()[:160]))
    return broken, read_errors


def run_check(repo_root: Path = REPO_ROOT) -> int:
    open_questions = repo_root / "docs/02_requirements/open-questions.md"
    if not open_questions.is_file():
        print(f"[check_decision_ids] SKIP: {open_questions} が存在しません")
        return 0

    defined = load_defined_ids(open_questions)
    files = iter_target_files(repo_root)
    broken, read_errors = find_broken_references(defined, files, repo_root)

    if read_errors:
        print("[check_decision_ids] FAIL（読み取りエラー）:")
        for line in read_errors:
            print(f"  - {line}")
        return 1

    if broken:
        print(
            f"[check_decision_ids] FAIL: 決定ログ（open-questions.md）に実在しない "
            f"D-n 参照が {len(broken)} 件あります:"
        )
        for rel, lineno, ref, snippet in broken:
            print(f"  - {rel}:{lineno} {ref} … {snippet}")
        print(
            "  ※ 本ツールは存在性のみ検査する（意味の一致は検査しない・"
            "詳細はファイル冒頭のコメント参照）"
        )
        return 1

    print(
        f"[check_decision_ids] OK（定義 {len(defined)} 件・参照 "
        f"{len(files)} ファイルを走査し、未定義参照なし）"
    )
    return 0


def self_test() -> int:
    failures: list[str] = []
    cases = 0

    import tempfile

    def defined_from(text: str) -> set[int]:
        """load_defined_ids() を実際に通して定義集合を得る（テスト内再実装を避ける）。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "open-questions.md"
            p.write_text(text, encoding="utf-8")
            return load_defined_ids(p)

    # --- 1. 定義抽出: 単独 ID（load_defined_ids 本体を経由） ---
    cases += 1
    ids = defined_from("| **D-5** | 何かの決定 | 2026-01-01 |\n")
    if ids != {5}:
        failures.append(f"単独 ID の定義抽出が誤り: {ids}")

    # --- 2. 定義抽出: 併記セル `D-5 / D-7`（load_defined_ids 本体を経由） ---
    cases += 1
    ids = defined_from("| **D-5 / D-7** | 決定 | 2026-01-01 |\n")
    if ids != {5, 7}:
        failures.append(f"併記セルの定義抽出が誤り: {ids}")

    # --- 3. 定義抽出: 接尾辞付きセル `D-5 追補`（load_defined_ids 本体を経由） ---
    cases += 1
    ids = defined_from("| **D-5 追補** | 決定 | 2026-01-01 |\n")
    if ids != {5}:
        failures.append(f"接尾辞付きセルの定義抽出が誤り: {ids}")

    # --- 4. 参照抽出: 複合 ID `SD-1` を D-1 として誤検出しない ---
    cases += 1
    refs = [m.group(0) for m in REFERENCE_RE.finditer("`SD-1` と `SD-3` の話")]
    if refs:
        failures.append(f"SD-1 を D-1 として誤検出した: {refs}")

    # --- 5. 参照抽出: バッククォート無しでも検出する ---
    cases += 1
    refs = [m.group(0) for m in REFERENCE_RE.finditer("これは D-26 の話")]
    if refs != ["D-26"]:
        failures.append(f"バッククォート無し参照を検出できない: {refs}")

    # --- 6. 参照抽出: 同一行内の複数出現を全て拾う ---
    cases += 1
    refs = [m.group(0) for m in REFERENCE_RE.finditer("`D-26` と `D-32` の関係")]
    if refs != ["D-26", "D-32"]:
        failures.append(f"同一行内の複数参照を検出できない: {refs}")

    # --- 7. 参照抽出: D-1 と D-10 の前方一致を混同しない ---
    cases += 1
    refs = [m.group(0) for m in REFERENCE_RE.finditer("`D-1` は `D-10` と別物")]
    if refs != ["D-1", "D-10"]:
        failures.append(f"D-1/D-10 の前方一致を誤って混同した: {refs}")

    # --- 8. 参照抽出: コードフェンス内の言及も検出する ---
    cases += 1
    fenced = "```\n# D-26 のゲートを通す\n```\n"
    refs = [m.group(0) for m in REFERENCE_RE.finditer(fenced)]
    if "D-26" not in refs:
        failures.append("コードフェンス内の参照を検出できない")

    # --- 9. 参照抽出: 判定範囲は大文字 ASCII の D-n のみ（仕様として固定・指摘 #4） ---
    cases += 1
    refs = [m.group(0) for m in REFERENCE_RE.finditer("これは d-77 の話（小文字）")]
    if refs:
        failures.append(f"小文字 d-77 を誤って検出した（仕様は大文字 ASCII の D-n のみ）: {refs}")
    refs = [m.group(0) for m in REFERENCE_RE.finditer("これは Ｄ-77 の話（全角）")]
    if refs:
        failures.append(f"全角 Ｄ-77 を誤って検出した（仕様は大文字 ASCII の D-n のみ）: {refs}")

    # --- 10. エンドツーエンド: run_check() を貫通させて未定義参照を検出させる（指摘 #2） ---
    cases += 1
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        oq_dir = tmp_root / "docs/02_requirements"
        oq_dir.mkdir(parents=True)
        (oq_dir / "open-questions.md").write_text(
            "| **D-1** | 何かの決定 | 2026-01-01 |\n"
            "| **D-2** | 別の決定 | 2026-01-01 |\n",
            encoding="utf-8",
        )
        other_dir = tmp_root / "docs/other"
        other_dir.mkdir(parents=True)
        (other_dir / "note.md").write_text(
            "`D-1` は存在するが `D-99` は存在しない\n", encoding="utf-8"
        )
        rc = run_check(tmp_root)
        if rc != 1:
            failures.append(f"run_check() が未定義参照 D-99 を検出せず exit {rc} を返した")

    # --- 11. エンドツーエンド: run_check() が未定義参照なしなら exit 0 を返す（指摘 #2） ---
    cases += 1
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        oq_dir = tmp_root / "docs/02_requirements"
        oq_dir.mkdir(parents=True)
        (oq_dir / "open-questions.md").write_text(
            "| **D-1** | 何かの決定 | 2026-01-01 |\n", encoding="utf-8"
        )
        other_dir = tmp_root / "docs/other"
        other_dir.mkdir(parents=True)
        (other_dir / "note.md").write_text("`D-1` は存在する\n", encoding="utf-8")
        rc = run_check(tmp_root)
        if rc != 0:
            failures.append(f"run_check() が未定義参照なしなのに exit {rc} を返した")

    # --- 12. 走査対象の構成: .claude 配下と CLAUDE.md がそれぞれ 1 件以上含まれる（指摘 #3） ---
    cases += 1
    real_files = iter_target_files()
    real_files_str = [str(p) for p in real_files]
    if not any("/.claude/" in s for s in real_files_str):
        failures.append(
            "iter_target_files() の走査結果に .claude 配下のファイルが含まれない"
            "（SCAN_ROOTS 構成の退行）"
        )
    if not any(s == str(REPO_ROOT / "CLAUDE.md") for s in real_files_str):
        failures.append(
            "iter_target_files() の走査結果に CLAUDE.md が含まれない（EXTRA_FILES 構成の退行）"
        )

    # --- 13. シンボリックリンクは走査対象から除外される（指摘 #1・CRITICAL） ---
    cases += 1
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        outside_dir = tmp_root.parent / f"outside-{tmp_root.name}"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "secret.md"
        outside_file.write_text("D-999 への言及を含むリポジトリ外ファイル\n", encoding="utf-8")
        try:
            docs_dir = tmp_root / "docs"
            docs_dir.mkdir()
            oq_dir = tmp_root / "docs/02_requirements"
            oq_dir.mkdir()
            (oq_dir / "open-questions.md").write_text(
                "| **D-1** | 何かの決定 | 2026-01-01 |\n", encoding="utf-8"
            )
            symlink_path = docs_dir / "link.md"
            try:
                symlink_path.symlink_to(outside_file)
            except OSError as e:
                print(
                    "[check_decision_ids] SELF-TEST SKIP: シンボリックリンク作成不可のため"
                    f"項目13をスキップ（{e.__class__.__name__}: {e}）",
                    file=sys.stderr,
                )
            else:
                found = iter_target_files(tmp_root)
                if any(str(outside_file) in str(p) or p == symlink_path for p in found):
                    failures.append(
                        f"シンボリックリンクが走査対象に残っている: {found}"
                    )
        finally:
            import shutil

            shutil.rmtree(outside_dir, ignore_errors=True)

    # --- 14. ファイルサイズ上限超過は read_errors に積まれ fail-closed になる（指摘 #5） ---
    cases += 1
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        big_file = tmp_root / "big.md"
        big_file.write_bytes(b"a" * (MAX_FILE_BYTES + 1))
        broken_big, errors_big = find_broken_references(set(), [big_file], tmp_root)
        if not errors_big:
            failures.append("サイズ上限超過ファイルが read_errors に積まれない（fail-open の恐れ）")
        if broken_big:
            failures.append(f"サイズ上限超過ファイルなのに broken が非空: {broken_big}")

    if failures:
        for line in failures:
            print(f"[check_decision_ids] SELF-TEST FAIL: {line}")
        return 1
    print(f"[check_decision_ids] SELF-TEST PASS（{cases} ケース確認）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test", action="store_true", help="検査ロジック自体の自己テストを実行する"
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
