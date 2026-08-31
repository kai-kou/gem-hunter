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

参照側の抽出は `(?<![A-Za-z])D-\\d+` で行う。`SD-1`（sprint-development-rules.md
の ID 体系）のように英字が直前に付く語を `D-1` として誤検出しないため、直前に
英字がある場合は除外する（先読みでなく後読み・lookbehind）。

使い方:
  python3 tools/check_decision_ids.py            # 検査（違反があれば exit 1）
  python3 tools/check_decision_ids.py --self-test  # 検査ロジック自体の自己テスト
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPEN_QUESTIONS = REPO_ROOT / "docs/02_requirements/open-questions.md"
SCAN_ROOTS = ["docs", ".claude"]
SCAN_EXTS = {".md", ".py", ".sh", ".json"}
EXTRA_FILES = ["CLAUDE.md"]

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


def iter_target_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in SCAN_EXTS:
                files.append(path)
    for name in EXTRA_FILES:
        path = REPO_ROOT / name
        if path.is_file():
            files.append(path)
    return files


def find_broken_references(
    defined: set[int], files: list[Path]
) -> tuple[list[tuple[str, int, str, str]], list[str]]:
    """定義に存在しない `D-n` 参照を列挙する。

    戻り値: (違反リスト[(相対パス, 行番号, 参照文字列, 行内容)], 読み取りエラーのファイル一覧)
    """
    broken: list[tuple[str, int, str, str]] = []
    read_errors: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            try:
                err_rel = path.relative_to(REPO_ROOT)
            except ValueError:
                err_rel = path
            read_errors.append(f"{err_rel}: {exc}")
            continue
        try:
            rel = str(path.relative_to(REPO_ROOT))
        except ValueError:
            rel = str(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in REFERENCE_RE.finditer(line):
                num = int(m.group(1))
                if num not in defined:
                    broken.append((rel, lineno, m.group(0), line.strip()[:160]))
    return broken, read_errors


def run_check() -> int:
    if not OPEN_QUESTIONS.is_file():
        print(f"[check_decision_ids] SKIP: {OPEN_QUESTIONS} が存在しません")
        return 0

    defined = load_defined_ids(OPEN_QUESTIONS)
    files = iter_target_files()
    broken, read_errors = find_broken_references(defined, files)

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
        f"{sum(1 for _ in files)} ファイルを走査し、未定義参照なし）"
    )
    return 0


def self_test() -> int:
    failures: list[str] = []

    import tempfile

    def defined_from(text: str) -> set[int]:
        """load_defined_ids() を実際に通して定義集合を得る（テスト内再実装を避ける）。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "open-questions.md"
            p.write_text(text, encoding="utf-8")
            return load_defined_ids(p)

    # --- 1. 定義抽出: 単独 ID（load_defined_ids 本体を経由） ---
    ids = defined_from("| **D-5** | 何かの決定 | 2026-01-01 |\n")
    if ids != {5}:
        failures.append(f"単独 ID の定義抽出が誤り: {ids}")

    # --- 2. 定義抽出: 併記セル `D-5 / D-7`（load_defined_ids 本体を経由） ---
    ids = defined_from("| **D-5 / D-7** | 決定 | 2026-01-01 |\n")
    if ids != {5, 7}:
        failures.append(f"併記セルの定義抽出が誤り: {ids}")

    # --- 3. 定義抽出: 接尾辞付きセル `D-5 追補`（load_defined_ids 本体を経由） ---
    ids = defined_from("| **D-5 追補** | 決定 | 2026-01-01 |\n")
    if ids != {5}:
        failures.append(f"接尾辞付きセルの定義抽出が誤り: {ids}")

    # --- 4. 参照抽出: 複合 ID `SD-1` を D-1 として誤検出しない ---
    refs = [m.group(0) for m in REFERENCE_RE.finditer("`SD-1` と `SD-3` の話")]
    if refs:
        failures.append(f"SD-1 を D-1 として誤検出した: {refs}")

    # --- 5. 参照抽出: バッククォート無しでも検出する ---
    refs = [m.group(0) for m in REFERENCE_RE.finditer("これは D-26 の話")]
    if refs != ["D-26"]:
        failures.append(f"バッククォート無し参照を検出できない: {refs}")

    # --- 6. 参照抽出: 同一行内の複数出現を全て拾う ---
    refs = [m.group(0) for m in REFERENCE_RE.finditer("`D-26` と `D-32` の関係")]
    if refs != ["D-26", "D-32"]:
        failures.append(f"同一行内の複数参照を検出できない: {refs}")

    # --- 7. 参照抽出: D-1 と D-10 の前方一致を混同しない ---
    refs = [m.group(0) for m in REFERENCE_RE.finditer("`D-1` は `D-10` と別物")]
    if refs != ["D-1", "D-10"]:
        failures.append(f"D-1/D-10 の前方一致を誤って混同した: {refs}")

    # --- 8. 参照抽出: コードフェンス内の言及も検出する ---
    fenced = "```\n# D-26 のゲートを通す\n```\n"
    refs = [m.group(0) for m in REFERENCE_RE.finditer(fenced)]
    if "D-26" not in refs:
        failures.append("コードフェンス内の参照を検出できない")

    # --- 9. エンドツーエンド: main() 相当の判定が未定義参照を検出して exit 1 になる ---
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        oq_dir = tmp_root / "docs/02_requirements"
        oq_dir.mkdir(parents=True)
        oq_path = oq_dir / "open-questions.md"
        oq_path.write_text(
            "| **D-1** | 何かの決定 | 2026-01-01 |\n"
            "| **D-2** | 別の決定 | 2026-01-01 |\n",
            encoding="utf-8",
        )
        other_dir = tmp_root / "docs/other"
        other_dir.mkdir(parents=True)
        (other_dir / "note.md").write_text(
            "`D-1` は存在するが `D-99` は存在しない\n", encoding="utf-8"
        )

        defined_e2e = load_defined_ids(oq_path)
        broken_e2e, errors_e2e = find_broken_references(
            defined_e2e, [oq_path, other_dir / "note.md"]
        )
        if errors_e2e:
            failures.append(f"E2E: 想定外の読み取りエラー: {errors_e2e}")
        broken_nums = {ref for _, _, ref, _ in broken_e2e}
        if "D-99" not in broken_nums:
            failures.append("E2E: 未定義参照 D-99 を検出できない（エントリポイント経路）")
        if "D-1" in broken_nums:
            failures.append("E2E: 定義済み D-1 を誤って未定義扱いした")

    if failures:
        for line in failures:
            print(f"[check_decision_ids] SELF-TEST FAIL: {line}")
        return 1
    print(f"[check_decision_ids] SELF-TEST PASS（{9} ケース確認）")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
