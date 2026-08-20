#!/usr/bin/env python3
"""check_adr_coverage.py — ADR 記録と README 記載の欠落ゲート（`E-18` / `E-19`）

SSOT: `docs/02_requirements/prd.md` §12（記録すべき ADR の一覧）と
      `docs/02_requirements/minimum-requirements.md` §6（README に書くこと）。
対応要件: `NFR-29`（セットアップ手順）/ `NFR-30`（設計上の判断・`AR-5` を含む）/
          `NFR-31`（AI 利用の範囲と方法）/ `NFR-32`（ADR の記録）/ `AC-11`。

検査（Error・`run_checks.sh` を止める）:
  1. `prd.md` §12 の表に「未作成」の行が残っていないこと
  2. §12 の表から張られた ADR リンクの実ファイルが存在すること（リンク切れ検出）
  3. README にセットアップ手順の必須コマンド（`npm ci` / 起動 / テスト）が載っていること
  4. README が `AR-5`（与件が対象外とした認証を上乗せした理由）に触れていること
  5. README に AI 利用の範囲と方法の節があること
  6. `docs/adr/` に存在する ADR が README の ADR 一覧から漏れていないこと

🔴 このスクリプトは「何本の ADR が要るか」を自分では持たない。主題の一覧は `prd.md` §12 が
   唯一の正本であり、本スクリプトはその表を読んで欠落を検出するだけにゃ（表を増やせば検査も増える）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PRD_PATH = REPO_ROOT / "docs" / "02_requirements" / "prd.md"
README_PATH = REPO_ROOT / "README.md"
ADR_DIR = REPO_ROOT / "docs" / "adr"

# README のセットアップ手順に最低限含まれているべきコマンド（`NFR-29`）
REQUIRED_README_COMMANDS = ("npm ci", "npm run dev", "npm test")

SECTION_12_HEADING = "## 12. 記録すべき ADR"
LINK_RE = re.compile(r"\[[^\]]+\]\((\.\.?/[^)#]+?)(?:#[^)]*)?\)")


def extract_section(markdown: str, heading: str) -> str:
    """`heading` から次の同レベル見出しまでの本文を返す（見つからなければ空文字）。"""
    start = markdown.find(heading)
    if start == -1:
        return ""
    rest = markdown[start + len(heading) :]
    next_heading = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def check_prd_section12(section: str, errors: list[str]) -> set[str]:
    """§12 の表を検査し、リンク先 ADR のファイル名集合を返す。"""
    if not section.strip():
        errors.append(f"{PRD_PATH.name} に「{SECTION_12_HEADING}」が見つからない（表の正本が消えている）")
        return set()

    for line in section.splitlines():
        if line.startswith("|") and "未作成" in line:
            subject = line.split("|")[2].strip() if line.count("|") >= 3 else line.strip()
            errors.append(f"{PRD_PATH.name} §12 に未作成の ADR が残っている: {subject}")

    linked: set[str] = set()
    for match in LINK_RE.finditer(section):
        target = (PRD_PATH.parent / match.group(1)).resolve()
        if "/adr/" not in match.group(1):
            continue
        linked.add(target.name)
        if not target.exists():
            errors.append(f"{PRD_PATH.name} §12 の ADR リンクが壊れている: {match.group(1)}")
    return linked


def check_readme(readme: str, errors: list[str]) -> None:
    for command in REQUIRED_README_COMMANDS:
        if command not in readme:
            errors.append(f"README にセットアップ手順のコマンドが無い（NFR-29）: {command}")

    if "AR-5" not in readme:
        errors.append("README が AR-5（与件が対象外とした認証を上乗せした理由）に触れていない（NFR-30）")

    if not re.search(r"^#{2,3} .*AI", readme, flags=re.MULTILINE):
        errors.append("README に AI 利用の範囲と方法の節が無い（NFR-31）")


def check_readme_lists_all_adrs(readme: str, adr_files: list[str], errors: list[str]) -> None:
    for name in adr_files:
        if name not in readme:
            errors.append(f"README の ADR 一覧に載っていない ADR がある（NFR-32）: docs/adr/{name}")


def run_checks() -> list[str]:
    errors: list[str] = []

    prd = PRD_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    adr_files = sorted(p.name for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))

    if not adr_files:
        errors.append("docs/adr/ に ADR が 1 本も無い（NFR-32）")

    linked = check_prd_section12(extract_section(prd, SECTION_12_HEADING), errors)
    check_readme(readme, errors)
    check_readme_lists_all_adrs(readme, adr_files, errors)

    for name in adr_files:
        if name not in linked and name not in readme:
            errors.append(f"どこからも参照されていない ADR がある（死蔵）: docs/adr/{name}")

    return errors


def self_test() -> int:
    """ネットワーク不要のユニットテスト（退行を実際に捕まえる強度で書く・#198）。"""
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    # extract_section: 次の同レベル見出しの手前で切れる
    doc = "## 11. x\n本文A\n\n## 12. 記録すべき ADR\n表\n\n## 13. y\n本文B\n"
    section = extract_section(doc, SECTION_12_HEADING)
    expect("表" in section, "extract_section が対象節を取り出せていない")
    expect("本文B" not in section, "extract_section が次節まで飲み込んでいる")
    expect("本文A" not in section, "extract_section が前節まで飲み込んでいる")
    expect(extract_section(doc, "## 99. なし") == "", "存在しない見出しで空文字を返していない")

    # 「未作成」の残存を検出する
    errors: list[str] = []
    check_prd_section12("| 1 | Next.js | 未作成 |\n", errors)
    expect(len(errors) == 1 and "未作成" in errors[0], "未作成の行を検出できていない")

    # リンク切れを検出する
    errors = []
    linked = check_prd_section12("| 1 | x | ✅ [ADR 9999](../adr/9999-nope.md) |\n", errors)
    expect("9999-nope.md" in linked, "リンク先のファイル名を拾えていない")
    expect(any("壊れている" in e for e in errors), "リンク切れを検出できていない")

    # 実在するリンクはエラーにしない
    errors = []
    check_prd_section12("| 1 | x | ✅ [ADR 0001](../adr/0001-ui-stack.md) |\n", errors)
    expect(errors == [], f"実在する ADR リンクを誤検出している: {errors}")

    # README の必須要素の欠落を検出する
    errors = []
    check_readme("# repo\n何も無い\n", errors)
    expect(
        len(errors) == len(REQUIRED_README_COMMANDS) + 2,
        f"README の欠落検出数が想定と違う: {errors}",
    )

    errors = []
    check_readme(
        "# repo\n`npm ci` `npm run dev` `npm test`\n`AR-5` の理由\n## AI を利用した範囲と方法\n",
        errors,
    )
    expect(errors == [], f"満たしている README を誤検出している: {errors}")

    # README の ADR 一覧漏れを検出する
    errors = []
    check_readme_lists_all_adrs("0001-ui-stack.md だけ載っている", ["0001-ui-stack.md", "0002-x.md"], errors)
    expect(len(errors) == 1 and "0002-x.md" in errors[0], "README の ADR 一覧漏れを検出できていない")

    if failures:
        for label in failures:
            print(f"[adr-coverage] SELF-TEST FAIL: {label}", file=sys.stderr)
        return 1
    print(f"[adr-coverage] self-test OK（{8 + len(REQUIRED_README_COMMANDS)} 項目）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行する")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    errors = run_checks()
    if errors:
        for message in errors:
            print(f"[adr-coverage] ERROR: {message}", file=sys.stderr)
        print(f"[adr-coverage] NG（{len(errors)} 件）", file=sys.stderr)
        return 1

    print("[adr-coverage] OK（prd.md §12 の ADR 記録と README の必須記載を確認）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
