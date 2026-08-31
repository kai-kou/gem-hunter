#!/usr/bin/env python3
"""check_architecture_boundaries.py — クリーンアーキテクチャの依存規則チェック（Issue #47 / #32）

SSOT: `docs/03_design/architecture/application-architecture.md` §1.2（層と import 可否）・§6（機械チェック）。
実装時の要約は `docs/rules/architecture-rules.md` §2（`ARCH-1`〜`ARCH-7`）。

検査:
  ARCH-1  `src/domain/`         が他層・フレームワーク（next / react / zod 等）を import している（Error）
  ARCH-2  `src/usecases/`       が `src/infrastructure/` `src/ui/` `app/` `next` を import している（Error）
  ARCH-3  `app/` `src/ui/`      が `src/infrastructure/` を直接 import している（Error・composition 経由のみ許可）
          `src/infrastructure/` が `src/ui/` `src/usecases/` `app/` を import している（Error・依存の逆流）
          `src/ui/`             が `app/` を import している（Error）
  ARCH-4  事業者固有バインディングの参照が `src/infrastructure/platform/` の外にある（Error・NFR-21 / INF-5）
  ARCH-5  GitHub API・GitHub 認証情報の参照が `src/infrastructure/github/` `platform/` の外にある（Error・NFR-16 / D-20）
  ARCH-6  `src/ui/`             が `src/usecases/` を import している（Error）
  ARCH-7  `src/shared/`         が他層に依存している（Warning）
  配置    `app/` `src/` 配下なのに §1.3 のどの層にも属さない（Warning）

前提と免責:
  - アプリコード（`app/` / `src/` 配下の .ts / .tsx / .mts / .cts）が 1 つも無ければ **全検査をスキップ**
  - テストコード（`*.test.*` / `*.spec.*` / `__tests__/` / `e2e/`）は検査対象外
  - 文字列リテラルを保護したうえでコメント（`//` と `/* */`）を除去してから検査する
  - 行末に `// arch-ok` を書いた行は ARCH-1/2/3/6/7 を個別に除外する。
    🔴 **ARCH-4 / ARCH-5（秘密情報とベンダー境界）には効かない**（抜け道にしないため）。
    抑止した件数はサマリーに必ず出力する（黙って消さない）

使い方:
  python3 tools/check_architecture_boundaries.py                  # app/ src/ 全体を検査
  python3 tools/check_architecture_boundaries.py --changed        # main との差分のみ検査
  python3 tools/check_architecture_boundaries.py path/a.ts …      # 指定ファイルのみ検査
  python3 tools/check_architecture_boundaries.py --self-test      # 検査ロジックの自己テスト
  違反（Error）があれば exit 1。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import git_diff_utils

REPO_ROOT = Path(__file__).resolve().parent.parent

# 🔴 `.mjs` / `.cjs` を含める（PR #689）: `src/domain/model/gem-index.rules.mjs` のように
#    `node` から直接 import される純 JS をドメイン層へ置く構成があり、拡張子で落とすと
#    そのファイルの依存規則違反（外部ライブラリの import 等）が検査を丸ごと素通りする。
CODE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".mjs", ".cjs")
EXCLUDE_DIR_PARTS = {"node_modules", ".next", "dist", "build", ".git", "__tests__", "e2e"}
ALLOW_MARKER = "// arch-ok"
MAX_FILE_BYTES = 1_000_000  # 生成物・巨大ファイルは読まない（ゲート全体のハングを防ぐ）

# import 元の指定子を拾う。`import` と `from` の間に改行が入る整形（Prettier 既定）に対応するため
# ファイル全文へ finditer する（行単位 search では複数行 import を取りこぼす）。
IMPORT_RE = re.compile(
    # 🔴 `[^'"();]` は改行も含むので `|\n` を足さない。足すと同じ 1 文字に 2 通りの経路ができ、
    #    import を持たない長いファイル（型定義だけの module 等）で破滅的バックトラックになる（実測 57 秒）。
    r"""(?:^|[\s;])(?:import|export)\s[^'"();]*?from\s*['"]([^'"]+)['"]"""
    r"""|(?:^|[\s;])import\s*['"]([^'"]+)['"]"""
    r"""|\bimport\(\s*['"]([^'"]+)['"]\s*\)"""
    r"""|\brequire\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# 事業者固有バインディング（Cloudflare）— 触ってよいのは src/infrastructure/platform/ だけ
VENDOR_BINDING_RE = re.compile(
    r"\bgetCloudflareContext\b|\bcloudflare:workers\b|\benv\.(?:KV|R2|D1|CACHE|IMAGES|RATE_LIMITER|ASSETS)\b"
)
# GitHub API・GitHub 認証情報 — 触ってよいのは src/infrastructure/github/（認証は platform/ も可）
GITHUB_ACCESS_RE = re.compile(
    r"api\.github\.com|@octokit/|\bGITHUB_TOKEN\b|\bGITHUB_APP_[A-Z0-9_]+\b"
    r"|\bINSTALLATION_TOKEN\b|\bGITHUB_PRIVATE_KEY\b"
)

LAYER_PLATFORM = "src/infrastructure/platform/"
LAYER_GITHUB = "src/infrastructure/github/"

LAYER_PREFIXES = (
    ("src/domain/", "domain"),
    ("src/usecases/", "usecases"),
    ("src/infrastructure/", "infrastructure"),
    ("src/ui/", "ui"),
    ("src/composition/", "composition"),
    ("src/shared/", "shared"),
    ("app/", "app"),
)

# 層に属さないが `app/` `src/` 直下に置かれてよいもの（配置 Warning の除外）
PLACEMENT_ALLOW_RE = re.compile(r"^(?:src|app)/[^/]+\.d\.ts$|^app/(?:global-)?error\.tsx$")


def is_test_file(rel: str) -> bool:
    name = Path(rel).name
    if ".test." in name or ".spec." in name:
        return True
    return bool(EXCLUDE_DIR_PARTS & set(Path(rel).parts))


def strip_comments(text: str) -> str:
    """コメントを空白へ置換する（オフセットと行番号を保つ）。文字列リテラルは保護する。

    行末コメントの URL（`// https://api.github.com/...`）やコメントアウト済み import を
    実コードと誤判定しないために必要（検査 4 / 5 は行全体の正規表現で見るため直撃する）。
    """
    out = list(text)
    i, n = 0, len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                j = text.find("\n", i)
                j = n if j == -1 else j
                for k in range(i, j):
                    out[k] = " "
                i = j
                continue
            if nxt == "*":
                j = text.find("*/", i + 2)
                j = n if j == -1 else j + 2
                for k in range(i, j):
                    if out[k] != "\n":
                        out[k] = " "
                i = j
                continue
        i += 1
    return "".join(out)


def normalize_specifier(spec: str, from_path: str) -> str | None:
    """import 指定子を「リポジトリルート相対のパス接頭辞」に正規化する。

    🔴 **cwd に依存させない**（`Path.resolve()` を使わない）。cwd 次第で解決結果が変わると、
    フックやサブエージェントの起動ディレクトリで検査結果が変わる非決定な挙動になる。
    外部パッケージ（`next` / `react` 等）は None を返す（呼び出し側が指定子で判定する）。
    """
    if spec.startswith("@/"):
        # Next.js 既定のエイリアス。src ディレクトリ運用では `@/x` → `src/x`。
        rest = spec[2:]
        return rest if rest.startswith(("src/", "app/")) else f"src/{rest}"
    if spec.startswith("."):
        base = Path(from_path).parent.as_posix()
        joined = f"{base}/{spec}" if base not in (".", "") else spec
        resolved = os.path.normpath(joined).replace(os.sep, "/")
        return None if resolved.startswith("..") else resolved
    return None  # 外部パッケージ


def layer_of(rel: str) -> str | None:
    for prefix, layer in LAYER_PREFIXES:
        if rel.startswith(prefix):
            return layer
    return None


# 層 → その層が import してはならない層（依存の向きの正本 = SSOT §1.2）
FORBIDDEN_TARGETS: dict[str, tuple[str, ...]] = {
    "domain": ("usecases", "infrastructure", "ui", "composition", "app"),
    "usecases": ("infrastructure", "ui", "composition", "app"),
    "infrastructure": ("usecases", "ui", "app"),
    "ui": ("usecases", "infrastructure", "app"),
    "app": ("infrastructure",),
    "shared": ("domain", "usecases", "infrastructure", "ui", "composition", "app"),
}
RULE_ID = {"domain": "ARCH-1", "usecases": "ARCH-2", "infrastructure": "ARCH-3",
           "ui": "ARCH-3", "app": "ARCH-3", "shared": "ARCH-7"}


def check_file(rel: str, text: str) -> tuple[list[str], list[str], int]:
    """1 ファイルを検査して (errors, warnings, 抑止件数) を返す。I/O を持たない（self-test の注入口）。"""
    errors: list[str] = []
    warnings: list[str] = []
    suppressed = 0
    if is_test_file(rel):
        return errors, warnings, suppressed

    layer = layer_of(rel)
    if layer is None:
        if rel.startswith(("app/", "src/")) and not PLACEMENT_ALLOW_RE.match(rel):
            warnings.append(
                f"{rel} が §1.3 のどの層にも属していません"
                "（app/ · src/{domain,usecases,infrastructure,ui,composition,shared}/ のいずれかへ置いてください）"
            )
        return errors, warnings, suppressed

    raw_lines = text.splitlines()
    allowed_lines = {i for i, line in enumerate(raw_lines, start=1) if ALLOW_MARKER in line}
    code = strip_comments(text)

    def lineno_at(offset: int) -> int:
        return code.count("\n", 0, offset) + 1

    # --- ARCH-4 / ARCH-5: ベンダー境界・GitHub 境界（`// arch-ok` を効かせない）---
    for lineno, line in enumerate(code.splitlines(), start=1):
        here = f"{rel}:{lineno}"
        if VENDOR_BINDING_RE.search(line) and not rel.startswith(LAYER_PLATFORM):
            errors.append(
                f"{here} ARCH-4: 事業者固有バインディングの参照は `{LAYER_PLATFORM}` の中だけです"
                "（NFR-21 / INF-5）"
            )
        if GITHUB_ACCESS_RE.search(line) and not rel.startswith((LAYER_GITHUB, LAYER_PLATFORM)):
            errors.append(
                f"{here} ARCH-5: GitHub API・GitHub 認証情報の参照は `{LAYER_GITHUB}` の中だけです"
                "（NFR-16 / D-20）"
            )

    # --- ARCH-1/2/3/6/7: import の依存規則 ---
    forbidden = FORBIDDEN_TARGETS.get(layer, ())
    rule = RULE_ID.get(layer, "ARCH")
    for m in IMPORT_RE.finditer(code):
        spec = next((g for g in m.groups() if g), None)
        if spec is None:
            continue
        start, end = lineno_at(m.start()), lineno_at(m.end())
        if any(ln in allowed_lines for ln in range(start, end + 1)):
            suppressed += 1
            continue
        here = f"{rel}:{start}"
        target = normalize_specifier(spec, rel)
        target_layer = layer_of(target) if target else None

        if layer == "domain":
            if target_layer not in ("domain", "shared"):
                errors.append(
                    f"{here} ARCH-1: ドメイン層は `{spec}` を import できません"
                    "（src/domain/ と src/shared/ のみ）"
                )
            continue
        if target_layer in forbidden:
            detail = {
                "usecases": "ポートを引数で受け取ってください",
                "infrastructure": "依存の逆流です（内側は外側を知らない）",
                "ui": "呼び出しは app/ 側で行ってください",
                "app": "composition root（src/composition/）を経由してください",
                "shared": "層に属する知識は各層へ移してください",
            }.get(layer, "")
            if layer in ("app", "ui") and target_layer == "infrastructure":
                detail = "src/composition/ を経由してください"
            if layer == "ui" and target_layer == "usecases":
                rule = "ARCH-6"
            severity = warnings if layer == "shared" else errors
            severity.append(f"{here} {rule}: `{layer}` は `{spec}` を import できません（{detail}）")
            rule = RULE_ID.get(layer, "ARCH")
        elif target is None and layer == "usecases" and (
            spec == "next" or spec.startswith("next/") or spec == "react"
        ):
            errors.append(
                f"{here} ARCH-2: ユースケース層は `{spec}` を import できません"
                "（フレームワークに依存させない）"
            )
    return errors, warnings, suppressed


def changed_files() -> list[str]:
    """変更ファイル一覧（base range + worktree・存在チェックなし・ソート済み）。

    #195: 収集ロジック本体は `tools/git_diff_utils.py` の `collect_changed_files()` に統合済み。
    元実装は `origin/main` 固定だったが、`default_branch()`（`symbolic-ref` 解決・失敗時 `main`
    フォールバック）へ寄せる。フォールバック先が `main` のため既存挙動は壊れない（意図的な統一・#195）。
    cached / untracked は元実装どおり見ない（アーキ境界検査は追跡差分のみで十分なため）。
    """
    return git_diff_utils.collect_changed_files(
        include_cached=False,
        include_untracked=False,
        require_existing=False,
        sort=True,
        cwd=REPO_ROOT,
    )


def collect_targets(argv: list[str]) -> tuple[list[str], list[str]]:
    """検査対象の相対パス一覧と、スキップ理由の Warning を返す。"""
    warnings: list[str] = []
    explicit = [a for a in argv if not a.startswith("-")]
    if "--changed" in argv:
        candidates = [f for f in changed_files() if f.endswith(CODE_SUFFIXES)]
    elif explicit:
        candidates = explicit
    else:
        candidates = []
        for root_name in ("app", "src"):
            root = REPO_ROOT / root_name
            if not root.is_dir():
                continue
            for p in root.rglob("*"):
                if p.suffix in CODE_SUFFIXES:
                    candidates.append(p.relative_to(REPO_ROOT).as_posix())
        candidates.sort()

    targets: list[str] = []
    for rel in candidates:
        if EXCLUDE_DIR_PARTS & set(Path(rel).parts):
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        if path.is_symlink():
            warnings.append(f"{rel} はシンボリックリンクのため検査をスキップしました")
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                warnings.append(f"{rel} が {MAX_FILE_BYTES} バイトを超えるため検査をスキップしました")
                continue
        except OSError as exc:
            warnings.append(f"{rel} の情報を取得できませんでした: {exc}")
            continue
        targets.append(rel)
    return targets, warnings


# --------------------------------------------------------------------------- self-test

CASES: list[tuple[str, str, int, int]] = [
    # (rel, text, expected_errors, expected_warnings)
    # ARCH-1: ドメインは依存ゼロ
    ("src/domain/model/repo.ts", "import { z } from 'zod'\n", 1, 0),
    ("src/domain/model/repo.ts", "import type { Owner } from './owner'\n", 0, 0),
    ("src/domain/model/repo.ts", "import { clamp } from '../../shared/num'\n", 0, 0),
    ("src/domain/model/repo.ts", "import { z } from 'zod' // arch-ok\n", 0, 0),
    ("src/domain/model/repo.ts", "// import { z } from 'zod'\n", 0, 0),
    ("src/domain/model/repo.ts", "/**\n@example import { z } from 'zod'\n*/\n", 0, 0),
    # 複数行 import（Prettier 既定整形）と 1 行 2 import
    ("src/usecases/search.ts", "import {\n  GithubQuery,\n} from '@/infrastructure/github/query'\n", 1, 0),
    ("src/domain/model/repo.ts", "import {\n  z,\n} from 'zod'\n", 1, 0),
    ("src/domain/model/repo.ts", "import a from './a'; import { z } from 'zod'\n", 1, 0),
    # ARCH-1: ドメイン層の `.mjs`（PR #689・拡張子で検査を素通りしないこと）
    ("src/domain/model/gem-index.rules.mjs", "export const RANK_MIN = 0\n", 0, 0),
    ("src/domain/model/gem-index.rules.mjs", "import { z } from 'zod'\n", 1, 0),
    # CJS の `require` も同じ IMPORT_RE が拾う（依存としては同じなので検査されるのが正しい）
    ("src/domain/model/gem-index.rules.cjs", "const { z } = require('zod')\n", 1, 0),
    # `.test.mjs` はテストコードなので対象外（既存の除外規則が拡張子追加後も効くこと）
    ("src/domain/model/gem-index.rules.test.mjs", "import { z } from 'zod'\n", 0, 0),
    # ARCH-2: ユースケース
    ("src/usecases/search.ts", "import type { RepositoryQueryPort } from '@/domain/ports/query'\n", 0, 0),
    ("src/usecases/search.ts", "import { cookies } from 'next/headers'\n", 1, 0),
    ("src/usecases/search.ts", "import { q } from '../infrastructure/github/query'\n", 1, 0),
    # ARCH-3: 内向き依存・依存の逆流
    ("app/page.tsx", "import { GithubQuery } from '@/infrastructure/github/query'\n", 1, 0),
    ("app/page.tsx", "import { searchUseCase } from '@/composition/container'\n", 0, 0),
    ("src/infrastructure/github/query.ts", "import { searchRepositories } from '@/usecases/search'\n", 1, 0),
    ("src/infrastructure/github/query.ts", "import { List } from '@/ui/list'\n", 1, 0),
    ("src/ui/list.tsx", "import Page from '../../app/page'\n", 1, 0),
    # ARCH-6: UI → ユースケース
    ("src/ui/list.tsx", "import { searchRepositories } from '@/usecases/search'\n", 1, 0),
    ("src/ui/list.tsx", "import { useState } from 'react'\n", 0, 0),
    # ARCH-7: shared（Warning）
    ("src/shared/num.ts", "import type { Repository } from '@/domain/model/repo'\n", 0, 1),
    # ARCH-5: GitHub 境界（`// arch-ok` を効かせない）
    ("src/infrastructure/github/query.ts", "const url = 'https://api.github.com/search'\n", 0, 0),
    ("src/usecases/search.ts", "const url = 'https://api.github.com/search'\n", 1, 0),
    ("src/ui/list.tsx", "const u = 'https://api.github.com/x' // arch-ok\n", 1, 0),
    ("src/ui/list.tsx", "// see https://api.github.com/search for the shape\n", 0, 0),
    ("src/usecases/search.ts", "const t = process.env.GITHUB_TOKEN\n", 1, 0),
    ("src/infrastructure/platform/auth.ts", "const k = process.env.GITHUB_APP_PRIVATE_KEY\n", 0, 0),
    # ARCH-4: ベンダー境界
    ("src/infrastructure/platform/kv.ts", "import { getCloudflareContext } from '@opennextjs/cloudflare'\n", 0, 0),
    ("src/infrastructure/cache/kv.ts", "const c = getCloudflareContext()\n", 1, 0),
    ("app/api/x/route.ts", "const v = env.KV\n", 1, 0),
    ("src/ui/list.tsx", "const v = env.KV // arch-ok\n", 1, 0),
    # 配置（Warning）
    ("src/services/gem-index.ts", "export const x = 1\n", 0, 1),
    ("src/env.d.ts", "declare const x: number\n", 0, 0),
    # テストコード・層外は対象外
    ("src/domain/model/repo.test.ts", "import { describe } from 'vitest'\n", 0, 0),
    ("src/ui/__tests__/list.tsx", "import { describe } from 'vitest'\n", 0, 0),
    ("e2e/search.spec.ts", "import { test } from '@playwright/test'\n", 0, 0),
    ("tools/foo.ts", "import { z } from 'zod'\n", 0, 0),
    # .mts / .cts もチェッカーは検査する（起動ゲート側の拡張子と揃っていること）
    ("src/domain/model/repo.mts", "import { z } from 'zod'\n", 1, 0),
]


def run_self_test() -> int:
    failures: list[str] = []
    for rel, text, want_e, want_w in CASES:
        errs, warns, _ = check_file(rel, text)
        if len(errs) != want_e or len(warns) != want_w:
            failures.append(
                f"  {rel}: want errors={want_e} warnings={want_w}, "
                f"got errors={len(errs)} warnings={len(warns)} :: {errs + warns}"
            )
    # 🔴 収集フィルタ（`CODE_SUFFIXES`）の検証。`check_file` の単体ケースだけでは
    #    「そもそも収集されない拡張子」を検知できない（PR #689 の変異テストで実測: `.mjs` を
    #    `CODE_SUFFIXES` から外しても上の 42 ケースは全通過した）。実在ファイルを明示指定で
    #    渡し、拡張子が収集の入口で落とされないことを確かめる。
    for required in (".ts", ".tsx", ".mts", ".cts", ".mjs", ".cjs"):
        if required not in CODE_SUFFIXES:
            failures.append(
                f"  収集フィルタ: CODE_SUFFIXES に {required} が含まれていません"
                "（src/ app/ 配下の同拡張子が依存規則の検査を素通りします）"
            )
    probe = "src/domain/model/gem-index.rules.mjs"
    if (REPO_ROOT / probe).is_file():
        collected, _ = collect_targets([probe])
        if probe not in collected:
            failures.append(f"  収集フィルタ: {probe} が検査対象に含まれていません")
        walked, _ = collect_targets([])
        if probe not in walked:
            failures.append(
                f"  収集フィルタ: 全走査（引数なし）で {probe} が拾われていません"
                "（拡張子フィルタが .mjs を落としています）"
            )

    # cwd 非依存の固定（サブディレクトリから起動しても同じ判定になること）
    cwd_case = ("src/usecases/search.ts", "import { q } from '../infrastructure/github/query'\n")
    original = os.getcwd()
    try:
        os.chdir(REPO_ROOT / "tools")
        if len(check_file(*cwd_case)[0]) != 1:
            failures.append("  cwd 非依存: tools/ から実行すると相対 import の違反を検出できない")
    except OSError:
        pass
    finally:
        os.chdir(original)

    if failures:
        print("❌ check_architecture_boundaries --self-test FAILED")
        print("\n".join(failures))
        return 1
    print(f"✅ check_architecture_boundaries --self-test PASSED（{len(CASES) + 2} ケース）")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        return run_self_test()

    targets, warnings = collect_targets(argv)
    if not targets:
        print("ℹ️ 検査対象のアプリコード（app/ · src/ の .ts/.tsx）がありません")
        return 0

    errors: list[str] = []
    suppressed = 0
    for rel in targets:
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"{rel} を読めませんでした: {exc}")
            continue
        e, w, s = check_file(rel, text)
        errors.extend(e)
        warnings.extend(w)
        suppressed += s

    if suppressed:
        warnings.append(f"`{ALLOW_MARKER}` で抑止された import 検査が {suppressed} 件あります（棚卸し対象）")
    for w in warnings:
        print(f"⚠️ {w}")
    for e in errors:
        print(f"❌ {e}")
    if errors:
        print(
            f"\n依存規則違反 {len(errors)} 件 / 検査 {len(targets)} ファイル。"
            "SSOT: docs/03_design/architecture/application-architecture.md §1.2"
        )
        return 1
    print(f"✅ 依存規則 OK（{len(targets)} ファイル・Warning {len(warnings)} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
