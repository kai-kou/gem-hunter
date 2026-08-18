#!/usr/bin/env python3
"""check_architecture_boundaries.py — クリーンアーキテクチャの依存規則チェック（Issue #47 / #32）

SSOT: `docs/03_design/architecture/application-architecture.md` §1.2（層と import 可否）・§6（機械チェック）。
実装時の要約は `docs/rules/architecture-rules.md` §2。

検査（Error = 依存規則違反 / Warning = 逸脱の疑い）:
  1. `src/domain/`   が他層・フレームワーク（next / react / zod 等）を import している
  2. `src/usecases/` が `src/infrastructure/` `src/ui/` `app/` `next` を import している
  3. `app/` `src/ui/` が `src/infrastructure/` を直接 import している（`src/composition/` 経由のみ許可）
  4. 事業者固有バインディングの参照が `src/infrastructure/platform/` の外にある（NFR-21 / INF-5）
  5. GitHub API への直接アクセスが `src/infrastructure/github/` の外にある（NFR-16）
  6. `src/ui/` が `src/usecases/` を import している
  7. `src/shared/` が他層を import している（Warning）

前提と免責:
  - アプリコード（`app/` / `src/` 配下の .ts / .tsx）が 1 つも無ければ **全検査をスキップ**（未着手期を誤検知しない）
  - テストコード（`*.test.*` / `*.spec.*` / `__tests__/` / `e2e/`）は検査対象外
  - 行末に `// arch-ok` を書いた行は個別に除外（レビュー済みの例外）

使い方:
  python3 tools/check_architecture_boundaries.py             # リポジトリ全体を検査
  python3 tools/check_architecture_boundaries.py --self-test # 検査ロジックの自己テスト
  違反（Error）があれば exit 1。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CODE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
EXCLUDE_DIR_PARTS = {"node_modules", ".next", "dist", "build", ".git", "__tests__", "e2e"}
ALLOW_MARKER = "// arch-ok"

# import 元の指定子を拾う（static import / export from / dynamic import / require）
IMPORT_RE = re.compile(
    r"""(?:^|\s)(?:import|export)\s[^'"]*from\s*['"]([^'"]+)['"]"""
    r"""|(?:^|\s)import\s*['"]([^'"]+)['"]"""
    r"""|\bimport\(\s*['"]([^'"]+)['"]\s*\)"""
    r"""|\brequire\(\s*['"]([^'"]+)['"]\s*\)""",
)

# 事業者固有バインディング（Cloudflare）— 触ってよいのは src/infrastructure/platform/ だけ
VENDOR_BINDING_RE = re.compile(
    r"\bgetCloudflareContext\b|\bcloudflare:workers\b|\benv\.(?:KV|R2|D1|CACHE|IMAGES|RATE_LIMITER|ASSETS)\b"
)
# GitHub API への直接アクセス — 触ってよいのは src/infrastructure/github/ だけ
GITHUB_ACCESS_RE = re.compile(r"api\.github\.com|@octokit/")

LAYER_PLATFORM = "src/infrastructure/platform/"
LAYER_GITHUB = "src/infrastructure/github/"


def is_test_file(rel: str) -> bool:
    name = Path(rel).name
    if ".test." in name or ".spec." in name:
        return True
    parts = Path(rel).parts
    return "__tests__" in parts or (parts and parts[0] == "e2e")


def normalize_specifier(spec: str, from_path: str) -> str | None:
    """import 指定子を「リポジトリルート相対のパス接頭辞」に正規化する。

    外部パッケージ（`next` / `react` 等）は解決せずそのまま返す（呼び出し側が判定する）。
    解決できない相対パスは None。
    """
    if spec.startswith("@/"):
        # Next.js 既定のエイリアス。src ディレクトリ運用では `@/x` → `src/x`。
        rest = spec[2:]
        return rest if rest.startswith(("src/", "app/")) else f"src/{rest}"
    if spec.startswith("."):
        base = Path(from_path).parent
        try:
            resolved = (base / spec).resolve().relative_to(REPO_ROOT)
        except (ValueError, OSError):
            # REPO_ROOT 外・解決不能。文字列結合で近似する（self-test 用の仮想パス経路）。
            parts: list[str] = list(base.parts)
            for seg in Path(spec).parts:
                if seg == ".":
                    continue
                if seg == "..":
                    if parts:
                        parts.pop()
                else:
                    parts.append(seg)
            return "/".join(parts)
        return resolved.as_posix()
    return None  # 外部パッケージ


def layer_of(rel: str) -> str | None:
    for prefix, layer in (
        ("src/domain/", "domain"),
        ("src/usecases/", "usecases"),
        ("src/infrastructure/", "infrastructure"),
        ("src/ui/", "ui"),
        ("src/composition/", "composition"),
        ("src/shared/", "shared"),
        ("app/", "app"),
    ):
        if rel.startswith(prefix):
            return layer
    return None


def check_file(rel: str, text: str) -> tuple[list[str], list[str]]:
    """1 ファイルを検査して (errors, warnings) を返す。I/O を持たない（self-test の注入口）。"""
    errors: list[str] = []
    warnings: list[str] = []
    layer = layer_of(rel)
    if layer is None or is_test_file(rel):
        return errors, warnings

    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        here = f"{rel}:{lineno}"

        # 検査 4: 事業者固有バインディング（NFR-21 / INF-5・#32）
        if VENDOR_BINDING_RE.search(line) and not rel.startswith(LAYER_PLATFORM):
            errors.append(
                f"{here} 事業者固有バインディングの参照は `{LAYER_PLATFORM}` の中だけです"
                "（NFR-21 / INF-5）"
            )
        # 検査 5: GitHub API への直接アクセス（NFR-16）
        if GITHUB_ACCESS_RE.search(line) and not rel.startswith(LAYER_GITHUB):
            errors.append(
                f"{here} GitHub API への直接アクセスは `{LAYER_GITHUB}` の中だけです（NFR-16）"
            )

        m = IMPORT_RE.search(line)
        if not m:
            continue
        spec = next((g for g in m.groups() if g), None)
        if spec is None:
            continue
        target = normalize_specifier(spec, rel)
        target_layer = layer_of(target) if target else None

        if layer == "domain":
            # 検査 1: ドメインは依存ゼロ（自層と shared のみ）
            if target_layer not in ("domain", "shared"):
                what = target if target else spec
                errors.append(
                    f"{here} ドメイン層は `{what}` を import できません"
                    "（src/domain/ と src/shared/ のみ・A-1）"
                )
        elif layer == "usecases":
            # 検査 2: ユースケースは実装・UI・フレームワークを知らない
            if target_layer in ("infrastructure", "ui", "app", "composition") or (
                target is None and (spec == "next" or spec.startswith("next/") or spec == "react")
            ):
                errors.append(
                    f"{here} ユースケース層は `{spec}` を import できません"
                    "（ポートを引数で受け取る・A-2）"
                )
        elif layer in ("app", "ui"):
            # 検査 3: 実装への直接依存を禁止（composition root 経由）
            if target_layer == "infrastructure":
                errors.append(
                    f"{here} `{layer}` から `src/infrastructure/` を直接 import できません"
                    "（src/composition/ 経由・A-3）"
                )
            # 検査 6: UI はユースケースを知らない
            if layer == "ui" and target_layer == "usecases":
                errors.append(
                    f"{here} `src/ui/` は `src/usecases/` を import できません"
                    "（呼び出しは app/ 側で行う）"
                )
        elif layer == "shared":
            # 検査 7: 共有ユーティリティは層に依存しない（Warning）
            if target_layer not in (None, "shared"):
                warnings.append(
                    f"{here} `src/shared/` が `{target}` に依存しています"
                    "（層に属する知識は各層へ移してください）"
                )
    return errors, warnings


def iter_code_files() -> list[Path]:
    out: list[Path] = []
    for root_name in ("app", "src"):
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.suffix not in CODE_SUFFIXES or not p.is_file():
                continue
            if EXCLUDE_DIR_PARTS & set(p.relative_to(REPO_ROOT).parts):
                continue
            out.append(p)
    return sorted(out)


# --------------------------------------------------------------------------- self-test

CASES: list[tuple[str, str, int, int]] = [
    # (rel, text, expected_errors, expected_warnings)
    ("src/domain/model/repo.ts", "import { z } from 'zod'\n", 1, 0),
    ("src/domain/model/repo.ts", "import type { Owner } from './owner'\n", 0, 0),
    ("src/domain/model/repo.ts", "import { clamp } from '../../shared/num'\n", 0, 0),
    ("src/domain/model/repo.ts", "import { z } from 'zod' // arch-ok\n", 0, 0),
    ("src/domain/model/repo.ts", "// import { z } from 'zod'\n", 0, 0),
    ("src/usecases/search.ts", "import { GithubQuery } from '@/infrastructure/github/query'\n", 1, 0),
    ("src/usecases/search.ts", "import type { RepositoryQueryPort } from '@/domain/ports/query'\n", 0, 0),
    ("src/usecases/search.ts", "import { cookies } from 'next/headers'\n", 1, 0),
    ("app/page.tsx", "import { GithubQuery } from '@/infrastructure/github/query'\n", 1, 0),
    ("app/page.tsx", "import { searchUseCase } from '@/composition/container'\n", 0, 0),
    ("src/ui/list.tsx", "import { searchRepositories } from '@/usecases/search'\n", 1, 0),
    ("src/ui/list.tsx", "import { useState } from 'react'\n", 0, 0),
    ("src/shared/num.ts", "import type { Repository } from '@/domain/model/repo'\n", 0, 1),
    ("src/infrastructure/github/query.ts", "const url = 'https://api.github.com/search'\n", 0, 0),
    ("src/usecases/search.ts", "const url = 'https://api.github.com/search'\n", 1, 0),
    ("src/infrastructure/platform/kv.ts", "import { getCloudflareContext } from '@opennextjs/cloudflare'\n", 0, 0),
    ("src/infrastructure/cache/kv.ts", "const c = getCloudflareContext()\n", 1, 0),
    ("app/api/x/route.ts", "const v = env.KV\n", 1, 0),
    # テストコードは検査対象外（vitest の import で誤検知しない）
    ("src/domain/model/repo.test.ts", "import { describe } from 'vitest'\n", 0, 0),
    ("e2e/search.spec.ts", "import { test } from '@playwright/test'\n", 0, 0),
    # 層に属さないファイルは無視する
    ("tools/foo.ts", "import { z } from 'zod'\n", 0, 0),
]


def run_self_test() -> int:
    failures: list[str] = []
    for rel, text, want_e, want_w in CASES:
        errs, warns = check_file(rel, text)
        if len(errs) != want_e or len(warns) != want_w:
            failures.append(
                f"  {rel}: want errors={want_e} warnings={want_w}, "
                f"got errors={len(errs)} warnings={len(warns)} :: {errs + warns}"
            )
    if failures:
        print("❌ check_architecture_boundaries --self-test FAILED")
        print("\n".join(failures))
        return 1
    print(f"✅ check_architecture_boundaries --self-test PASSED（{len(CASES)} ケース）")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return run_self_test()

    files = iter_code_files()
    if not files:
        print("ℹ️ アプリコード（app/ · src/ の .ts/.tsx）が無いため検査をスキップしました")
        return 0

    errors: list[str] = []
    warnings: list[str] = []
    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"{rel} を読めませんでした: {exc}")
            continue
        e, w = check_file(rel, text)
        errors.extend(e)
        warnings.extend(w)

    for w in warnings:
        print(f"⚠️ {w}")
    for e in errors:
        print(f"❌ {e}")
    if errors:
        print(
            f"\n依存規則違反 {len(errors)} 件 / 検査 {len(files)} ファイル。"
            "SSOT: docs/03_design/architecture/application-architecture.md §1.2"
        )
        return 1
    print(f"✅ 依存規則 OK（{len(files)} ファイル・Warning {len(warnings)} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
