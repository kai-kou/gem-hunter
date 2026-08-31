#!/usr/bin/env python3
"""count_change_scatter.py — PR バンドル判定用に「変更ファイルの散らばり」を数える（#701）

## なぜ必要か

`retro-try-handler` の Step 4.5（PR バンドル判定）は、複数の retro-try Issue を 1 PR に束ねるかを
「Issue 件数」だけで決めていた。PR #697 は 4 カテゴリ・12 ファイルに散り、Layer 1 セルフレビューが
条件付き観点を複数起動して指摘 7 件・修正 2 サイクルを要した。件数だけでは散らばりを制御できない。

本ツールは判定に使う 2 つの実測値（**カテゴリ数** と **変更ファイル数**）を機械的に数える。
数え方をシェルのワンライナーで各所に書くと、カテゴリ境界の解釈が書き手ごとにぶれる
（実際に `app/` と `src/` を 1 カテゴリと書いた表と 2 カテゴリと数えるスクリプトが同居した）。
**カテゴリ分けの正本は本ファイルの `categorize()` であり、ドキュメントはこれを呼ぶ。**

## カテゴリの決め方

「AI レビューが観点を切り替える単位」を 1 カテゴリとする。

| 入力パス | カテゴリ |
| --- | --- |
| `.claude/hooks/pre-git-push-check.sh` | `.claude/hooks/`（`.claude/` 配下は第 2 階層まで見る） |
| `.claude/settings.json`（`.claude/` 直下のファイル） | `.claude/` |
| `docs/rules/sprint-development-rules.md` | `docs/rules/` |
| `docs/04_development/testing-strategy.md` | `docs/`（`docs/rules/` 以外） |
| `app/page.tsx` / `src/domain/repo.ts` | `app-code`（**`app/` と `src/` は 1 カテゴリに統合する**） |
| `playwright.workers.config.ts`（リポジトリルート直下） | `<root>` |
| 上記以外（`tools/` `e2e/` `.github/` `config/` `site/` 等） | 第 1 階層のディレクトリ名 |

`app/` と `src/` を統合するのは、Next.js の App Router（`app/`）とドメイン層（`src/`）が
同じ「アプリコードのレビュー観点」で読まれるためである（層の依存規則の検査は
`check_architecture_boundaries.py` の担当であって、散らばり指標の担当ではない）。

## 閾値

**カテゴリ数 4 以上 かつ ファイル数 8 以上** で「分割すべき」と判定する（AND 条件）。
根拠は `.claude/skills/retro-try-handler/reference.md` D の実測表を参照。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CATEGORY_THRESHOLD = 4
FILE_THRESHOLD = 8

APP_CODE_ROOTS = ("app", "src")
APP_CODE_CATEGORY = "app-code"
ROOT_CATEGORY = "<root>"


def categorize(path: str) -> str:
    """変更ファイルのパスを 1 カテゴリへ写像する（カテゴリ分けの正本）。"""
    parts = [p for p in path.strip().split("/") if p]
    if not parts:
        return ROOT_CATEGORY
    if len(parts) == 1:
        return ROOT_CATEGORY
    head = parts[0]
    if head == ".claude":
        # `.claude/hooks/x.sh` → `.claude/hooks/` / `.claude/settings.json` → `.claude/`
        return f".claude/{parts[1]}/" if len(parts) >= 3 else ".claude/"
    if head == "docs":
        return "docs/rules/" if parts[1] == "rules" else "docs/"
    if head in APP_CODE_ROOTS:
        return APP_CODE_CATEGORY
    return f"{head}/"


def analyze(paths: list[str]) -> dict:
    files = [p.strip() for p in paths if p.strip()]
    categories = sorted({categorize(p) for p in files})
    should_split = len(categories) >= CATEGORY_THRESHOLD and len(files) >= FILE_THRESHOLD
    return {
        "file_count": len(files),
        "category_count": len(categories),
        "categories": categories,
        "category_threshold": CATEGORY_THRESHOLD,
        "file_threshold": FILE_THRESHOLD,
        "should_split": should_split,
    }


def changed_paths_from_git(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.splitlines()


# --------------------------------------------------------------------------- self-test

# 過去のバンドル PR の実測（回帰フィクスチャ）。値は git show --name-only で取得した実ファイル一覧。
HISTORICAL = {
    "#670": (
        [
            ".claude/skills/retro-try-handler/reference.md",
            "docs/04_development/testing-strategy.md",
            "docs/rules/pr-review-flow-summary.md",
            "playwright.workers.config.ts",
            "tools/run_checks.sh",
        ],
        5,
        5,
        False,
    ),
    "#674": (
        [
            "docs/04_development/flaky-tests.md",
            "docs/rules/agent-team-summary.md",
            "docs/rules/pr-review-flow-summary.md",
            "docs/rules/session-sprint-rules.md",
            "tools/check_flaky_registry.py",
            "tools/run_checks.sh",
        ],
        6,
        3,
        False,
    ),
    "#697": (
        [
            ".claude/hooks/post-merge-publish-check.sh",
            ".claude/hooks/pre-git-push-check.sh",
            ".claude/hooks/session-start.sh",
            ".claude/skills/code-review/SKILL.md",
            ".claude/skills/discussion-review/SKILL.md",
            ".claude/skills/pr-review-watcher/SKILL.md",
            ".claude/skills/sprint-cycle-router/SKILL.md",
            "docs/rules/pr-review-flow-summary.md",
            "docs/rules/sprint-development-rules.md",
            "docs/rules/token-optimization-rules.md",
            "tools/check_prod_drift.py",
            "tools/run_checks.sh",
        ],
        12,
        4,
        True,
    ),
    "#723": (
        [
            "docs/02_requirements/open-questions.md",
            "docs/rules/agent-team-summary.md",
            "docs/rules/token-optimization-rules.md",
            "tools/check_agent_diff_claim.py",
            "tools/check_deploy_gate.py",
        ],
        5,
        3,
        False,
    ),
}


def self_test() -> int:
    failures: list[str] = []

    def expect(label: str, actual, want) -> None:
        if actual != want:
            failures.append(f"{label}: expected {want!r}, got {actual!r}")

    # 1. categorize() の全分岐（1 分岐 = 1 ケース。壊すと必ずどれかが落ちる）
    expect("claude 2nd level", categorize(".claude/hooks/pre-git-push-check.sh"), ".claude/hooks/")
    expect("claude skills nested", categorize(".claude/skills/code-review/SKILL.md"), ".claude/skills/")
    expect("claude direct file", categorize(".claude/settings.json"), ".claude/")
    expect("docs rules", categorize("docs/rules/lessons-core.md"), "docs/rules/")
    expect("docs rules nested", categorize("docs/rules/lessons/pr-review.md"), "docs/rules/")
    expect("docs other", categorize("docs/04_development/testing-strategy.md"), "docs/")
    expect("docs direct file", categorize("docs/project-mission.md"), "docs/")
    expect("app router", categorize("app/[locale]/page.tsx"), APP_CODE_CATEGORY)
    expect("src domain", categorize("src/domain/repository.ts"), APP_CODE_CATEGORY)
    expect("root file", categorize("playwright.workers.config.ts"), ROOT_CATEGORY)
    expect("generic dir", categorize("tools/run_checks.sh"), "tools/")
    expect("github dir", categorize(".github/workflows/quality-checks.yml"), ".github/")
    expect("empty path", categorize(""), ROOT_CATEGORY)

    # 2. app/ と src/ が 1 カテゴリへ統合されること（統合を外すと 2 になって落ちる）
    merged = analyze(["app/page.tsx", "src/domain/repo.ts"])
    expect("app+src merged", merged["category_count"], 1)

    # 3. 閾値の AND 条件（OR に緩めると 3-a / 3-b のどちらかが落ちる）
    four_cat_seven_files = [
        ".claude/hooks/a.sh",
        ".claude/skills/b/SKILL.md",
        "docs/rules/c.md",
        "docs/rules/d.md",
        "docs/rules/e.md",
        "tools/f.py",
        "tools/g.py",
    ]
    a = analyze(four_cat_seven_files)
    expect("3-a categories", a["category_count"], 4)
    expect("3-a files", a["file_count"], 7)
    expect("3-a should_split (files 未達)", a["should_split"], False)

    three_cat_nine_files = [f"docs/rules/r{i}.md" for i in range(7)] + [
        "tools/x.py",
        ".claude/hooks/y.sh",
    ]
    b = analyze(three_cat_nine_files)
    expect("3-b categories", b["category_count"], 3)
    expect("3-b files", b["file_count"], 9)
    expect("3-b should_split (categories 未達)", b["should_split"], False)

    c = analyze(four_cat_seven_files + ["tools/h.py"])
    expect("3-c should_split (両方到達)", c["should_split"], True)

    # 4. 過去 PR の回帰フィクスチャ（reference.md D の実測表と同じ値を返すこと）
    for pr, (paths, want_files, want_cats, want_split) in HISTORICAL.items():
        got = analyze(paths)
        expect(f"{pr} files", got["file_count"], want_files)
        expect(f"{pr} categories", got["category_count"], want_cats)
        expect(f"{pr} should_split", got["should_split"], want_split)

    # 5. 同一カテゴリ内の複数ファイルは 1 カテゴリと数える
    expect(
        "dedup within category",
        analyze(["tools/a.py", "tools/b.py", "tools/c.py"])["category_count"],
        1,
    )

    if failures:
        print("❌ count_change_scatter.py self-test FAILED", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("✅ count_change_scatter.py self-test PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/main", help="比較対象（既定: origin/main）")
    parser.add_argument("--path", action="append", default=[], help="パスを直接指定（繰り返し可・git を使わない）")
    parser.add_argument("--paths-file", help="1 行 1 パスのファイル（`-` で標準入力）")
    parser.add_argument("--json", action="store_true", help="JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="自己テストを実行する")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.path:
        paths = args.path
    elif args.paths_file:
        if args.paths_file == "-":
            paths = sys.stdin.read().splitlines()
        else:
            paths = Path(args.paths_file).read_text(encoding="utf-8").splitlines()
    else:
        try:
            paths = changed_paths_from_git(args.base)
        except subprocess.CalledProcessError as exc:
            print(f"❌ git diff に失敗しました（base={args.base}）: {exc.stderr}", file=sys.stderr)
            return 2

    result = analyze(paths)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"変更ファイル数: {result['file_count']}")
        print(f"カテゴリ数: {result['category_count']}")
        for c in result["categories"]:
            print(f"  - {c}")
        if result["should_split"]:
            print(
                f"🔴 分割推奨（カテゴリ {result['category_count']} >= {CATEGORY_THRESHOLD} "
                f"かつ ファイル {result['file_count']} >= {FILE_THRESHOLD}）"
            )
        else:
            print("🟢 バンドル可（閾値未満）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
