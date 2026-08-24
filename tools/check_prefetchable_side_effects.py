#!/usr/bin/env python3
"""check_prefetchable_side_effects.py — プリフェッチされる副作用付き API ルートの検出

**実バグの再発防止用ゲート**: `src/ui/login-link.tsx` が `next/link` の `<Link>` で
`href="/api/auth/logout"` を描画していたため、Next.js の自動プリフェッチが
`GET /api/auth/logout` を実際に実行し、**ページを表示しただけでセッション Cookie が
破棄される**バグが起きた（Playwright トレースで実測）。同種のミスは
「`<Link>` で `/api/**` を指す」という形をとる。

検査:
  1. `app/**/*.tsx` と `src/**/*.tsx` を走査し、`next/link` の `<Link>`（import 名は
     エイリアスに追従する）の `href` が `/api/` で始まるものを **違反** として報告する
     （プリフェッチで副作用のある GET が実行されうるため）。素の `<a href="/api/...">` は
     プリフェッチされないため違反にしない。
  2. `app/api/**/route.ts` に `GET` ハンドラがあり、その中で `cookies.set(` または
     `cookies.delete(` を呼んでいるものを **違反** として報告する（GET に副作用を持たせない・
     安全なメソッドの原則）。

     🔴 例外（無言のハードコード除外にしない・パスと理由をセットで明記する）:
     `app/api/auth/login/route.ts` — OAuth 認可の開始点。外部プロバイダ（GitHub）の
     authorize エンドポイントへリダイレクトするという性質上、ブラウザから直接辿られる
     GET でしか呼び出せず、CSRF 対策の `oauth_state` を発行するために GET 内で
     `cookies.set(` が必要になる（OAuth 2.0 の authorization request はリンク遷移 /
     リダイレクトで開始する仕様であり、POST 化できない）。
     `app/api/auth/callback/route.ts` — OAuth 認可のコールバック。GitHub からの
     リダイレクト先であるため GET でしか受けられず、セッション Cookie の発行と
     `oauth_state` の破棄をここで行う必要がある（UI からリンクされないため
     プリフェッチの対象にもならない）。

前提と免責:
  - 検査対象コード（`app/**/*.tsx` / `src/**/*.tsx` / `app/api/**/route.ts`）が
    1 つも無ければ検査対象ゼロとして PASS 扱いにする
  - 文字列リテラルを保護したうえでコメント（`//` と `/* */`）を除去してから検査する
  - `.next` / `node_modules` / `dist` / `build` 等の生成物ディレクトリは対象外

ツールの限界（既知の検出漏れ）:
  - 検査 2（GET ハンドラ内 Cookie 変更）は `cookies.set(` / `cookies.delete(` が
    ハンドラ本体に **直接** 現れる場合のみ検出する。Cookie 削除処理を共有ヘルパー関数へ
    委譲されると（例: `clearSessionCookie(res)`）検出をすり抜ける。この限界がある分、
    検査 1（`<Link href="/api/...">` の検出）が **第一の防衛線**であり、検査 2 は多層防御の
    二段目という位置づけである。

使い方:
  python3 tools/check_prefetchable_side_effects.py              # リポジトリ全体を検査
  python3 tools/check_prefetchable_side_effects.py path/a.tsx …  # 指定ファイルのみ検査
  python3 tools/check_prefetchable_side_effects.py --self-test   # 検査ロジックの自己テスト
  違反があれば exit 1、無ければ PASS（exit 0）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ts_source import find_matching_brace, find_tag_end, strip_comments

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIR_PARTS = {"node_modules", ".next", "dist", "build", ".git", "__tests__", "e2e"}
MAX_FILE_BYTES = 1_000_000  # 生成物・巨大ファイルは読まない（ゲート全体のハングを防ぐ）

# 検査2の例外リスト（パス → 許容理由）。ここに書かれたパス以外は無条件で違反にする。
GET_COOKIE_MUTATION_EXCEPTIONS: dict[str, str] = {
    "app/api/auth/login/route.ts": (
        "OAuth 認可の開始点。GitHub の authorize エンドポイントへのリダイレクトは "
        "ブラウザからのリンク遷移 / GET でしか開始できず、CSRF 対策の oauth_state を "
        "発行するために GET 内で cookies.set( が必要（OAuth 2.0 仕様上 POST 化できない）"
    ),
    "app/api/auth/callback/route.ts": (
        "OAuth 認可のコールバック。GitHub からのリダイレクト先であり GET でしか受けられず、"
        "セッション Cookie の発行と oauth_state の破棄をここで行う必要がある。"
        "UI からリンクされないためプリフェッチの対象にもならない"
    ),
}


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def find_matching_paren(text: str, open_idx: int) -> int:
    """`text[open_idx] == '('` として、対応する `)` のインデックスを返す。"""
    depth = 0
    i = open_idx
    n = len(text)
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
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


# --------------------------------------------------------------------------- 検査1: <Link href="/api/...">

# next/link の import 名（エイリアス）を拾う。`import Link from 'next/link'` /
# `import NextLink from "next/link"` に加え、`import Link, { LinkProps } from 'next/link'`
# のような named import 併記形にも対応する（末尾の `{ ... }` は任意）。
LINK_IMPORT_RE = re.compile(
    r"""import\s+([A-Za-z_$][\w$]*)\s*(?:,\s*\{[^}]*\})?\s*from\s+['"]next/link['"]"""
)

HREF_RE = re.compile(
    r"""href\s*=\s*\{?\s*["'`](/api/[^"'`]*)["'`]\s*\}?"""
)


def check_link_hrefs(rel: str, raw_text: str) -> list[str]:
    """`<Link href="/api/...">` 形式の違反を `path:line` 付きで返す。"""
    text = strip_comments(raw_text)
    m = LINK_IMPORT_RE.search(text)
    if not m:
        return []  # next/link を import していないファイルは対象外
    link_name = m.group(1)

    violations: list[str] = []
    tag_open_re = re.compile(rf"<{re.escape(link_name)}\b")
    pos = 0
    while True:
        tag_match = tag_open_re.search(text, pos)
        if not tag_match:
            break
        attrs_start = tag_match.end()
        tag_end = find_tag_end(text, attrs_start)
        if tag_end == -1:
            break  # 対応するタグ終端が見つからない（壊れた/切り詰められた入力）
        attrs = text[attrs_start:tag_end]
        href_match = HREF_RE.search(attrs)
        if href_match and href_match.group(1).startswith("/api/"):
            ln = line_of(text, tag_match.start())
            violations.append(
                f"{rel}:{ln}: <{link_name} href=\"{href_match.group(1)}\"> が next/link で "
                f"/api/ をプリフェッチさせています（素の <a href> か <form> を使ってください）"
            )
        pos = tag_end + 1
    return violations


# --------------------------------------------------------------------------- 検査2: GET ハンドラ内の Cookie 変更

# `export async function GET(...)` / `export function GET(...)` の関数宣言形。
GET_FUNC_DECL_RE = re.compile(r"export\s+(?:async\s+)?function\s+GET\s*\(")
# `export const GET = async (...) => { ... }` のアロー関数形にも対応する。
GET_ARROW_DECL_RE = re.compile(r"export\s+const\s+GET\s*=\s*(?:async\s*)?\(")
# `export const GET = async function (...) { ... }` の関数式代入形にも対応する
# （関数名は無名 `function (` / 有名 `function foo(` のどちらも許容）。
GET_FUNC_EXPR_RE = re.compile(
    r"export\s+const\s+GET\s*=\s*(?:async\s+)?function\s*(?:[A-Za-z_$][\w$]*)?\s*\("
)

COOKIE_MUTATION_RE = re.compile(r"\bcookies\.(?:set|delete)\s*\(")


def _extract_get_bodies(text: str) -> list[str]:
    """コメント除去済みテキストから GET ハンドラの本体（`{...}`）を全て抜き出す。"""
    bodies: list[str] = []
    for decl_re in (GET_FUNC_DECL_RE, GET_ARROW_DECL_RE, GET_FUNC_EXPR_RE):
        for decl_match in decl_re.finditer(text):
            paren_open = decl_match.end() - 1
            paren_close = find_matching_paren(text, paren_open)
            brace_open = text.find("{", paren_close + 1)
            if brace_open == -1:
                continue  # 暗黙 return のアロー関数など、本体ブロックを持たない
            brace_close = find_matching_brace(text, brace_open)
            bodies.append(text[brace_open : brace_close + 1])
    return bodies


def check_get_cookie_mutations(rel: str, raw_text: str) -> list[str]:
    """GET ハンドラ内の `cookies.set(` / `cookies.delete(` 違反を `path:line` 付きで返す。"""
    if rel in GET_COOKIE_MUTATION_EXCEPTIONS:
        return []

    text = strip_comments(raw_text)
    violations: list[str] = []
    for body in _extract_get_bodies(text):
        for cm in COOKIE_MUTATION_RE.finditer(body):
            # body は text の部分文字列の「コピー」なので、行番号は body 内オフセットで
            # 近似する（元テキストでの絶対オフセットを持たないため、GET 宣言からの相対行では
            # なく本体内の相対行になる点に注意。誤差は数行程度で目視特定には十分）。
            ln = body.count("\n", 0, cm.start()) + 1
            violations.append(
                f"{rel}: GET ハンドラ内（本体 {ln} 行目付近）で `{cm.group(0)}` を呼んでいます"
                "（GET に副作用を持たせないでください。安全なメソッドの原則違反）"
            )
    return violations


# --------------------------------------------------------------------------- ファイル収集

def collect_targets(argv: list[str]) -> tuple[list[str], list[str]]:
    """検査対象の相対パス一覧と、スキップ理由の Warning を返す。"""
    warnings: list[str] = []
    explicit = [a for a in argv if not a.startswith("-")]
    if explicit:
        candidates = explicit
    else:
        candidates = []
        for root_name in ("app", "src"):
            root = REPO_ROOT / root_name
            if not root.is_dir():
                continue
            for p in root.rglob("*"):
                if p.suffix == ".tsx" or p.name == "route.ts":
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


def check_file(rel: str, raw_text: str) -> list[str]:
    """1 ファイルを検査して違反メッセージのリストを返す。I/O を持たない（self-test の注入口）。"""
    violations: list[str] = []
    if rel.endswith(".tsx"):
        violations.extend(check_link_hrefs(rel, raw_text))
    if rel.endswith("route.ts") and "/api/" in rel.replace("\\", "/"):
        violations.extend(check_get_cookie_mutations(rel, raw_text))
    return violations


# --------------------------------------------------------------------------- self-test

CASES: list[tuple[str, str, int]] = [
    # (rel, text, expected_violation_count)
    # 検査1: 合格例
    ("src/ui/login-link.tsx", 'export const x = <a href="/api/auth/login">login</a>\n', 0),
    ("src/ui/locale-switcher.tsx", "import Link from 'next/link'\nexport const x = <Link href=\"/ja\">JA</Link>\n", 0),
    (
        "src/ui/commented.tsx",
        "import Link from 'next/link'\n// <Link href=\"/api/auth/logout\">x</Link>\n"
        "export const x = <Link href=\"/ja\">JA</Link>\n",
        0,
    ),
    # 検査1: 違反例（元バグの再現）
    (
        "src/ui/login-link.tsx",
        "import Link from 'next/link'\nexport const x = <Link href=\"/api/auth/logout\">logout</Link>\n",
        1,
    ),
    # 検査1: 違反例（複数行 + import エイリアス）
    (
        "src/ui/login-link.tsx",
        "import NextLink from 'next/link'\n"
        "export const x = (\n  <NextLink\n    href=\"/api/auth/logout\"\n  >\n    logout\n  </NextLink>\n)\n",
        1,
    ),
    # 検査2: 合格例（副作用のない GET）
    (
        "app/api/search/route.ts",
        "export async function GET(request: Request) {\n"
        "  const v = request.cookies.get('x')\n  return Response.json({ v })\n}\n",
        0,
    ),
    # 検査2: 違反例（cookies.delete）
    (
        "app/api/session/route.ts",
        "export async function GET(request: Request) {\n"
        "  const res = NextResponse.redirect('/')\n  res.cookies.delete('session')\n  return res\n}\n",
        1,
    ),
    # 検査2: 違反例（cookies.set・アロー関数形）
    (
        "app/api/weird/route.ts",
        "export const GET = async (request: Request) => {\n"
        "  const res = NextResponse.json({})\n  res.cookies.set('a', '1')\n  return res\n}\n",
        1,
    ),
    # 検査2: 例外パス（app/api/auth/login/route.ts は許容）
    (
        "app/api/auth/login/route.ts",
        "export async function GET(request: Request) {\n"
        "  const res = NextResponse.redirect('https://github.com/login/oauth/authorize')\n"
        "  res.cookies.set('oauth_state', 'x')\n  return res\n}\n",
        0,
    ),
    # 検査2: 同ファイル内の POST は対象外（GET が無ければ違反にならない）
    (
        "app/api/auth/logout/route.ts",
        "export async function POST(request: Request) {\n"
        "  const res = NextResponse.redirect('/')\n  res.cookies.delete('session')\n  return res\n}\n",
        0,
    ),
    # 検査2: 例外パス（app/api/auth/callback/route.ts は許容）
    (
        "app/api/auth/callback/route.ts",
        "export async function GET(request: Request) {\n"
        "  const res = NextResponse.redirect('/')\n  res.cookies.set('session', 'x')\n"
        "  res.cookies.delete('oauth_state')\n  return res\n}\n",
        0,
    ),
    # 検査2: コメント内の cookies.delete( は無視する
    (
        "app/api/session/route.ts",
        "export async function GET(request: Request) {\n"
        "  // res.cookies.delete('session')\n  return NextResponse.json({})\n}\n",
        0,
    ),
    # 検査1: 属性内のアロー関数に含まれる `>` をタグ終端と誤認しない（実機再現バグ）。
    # `onClick={() => doThing()}` の `=>` を旧実装（非貪欲 `.*?/?>`）は誤ってタグ終端と
    # みなし、後続の href="/api/auth/logout" を取りこぼしていた。
    (
        "src/ui/order.tsx",
        "import Link from 'next/link'\n"
        'export const x = <Link onClick={() => doThing()} href="/api/auth/logout">out</Link>\n',
        1,
    ),
    # 検査1: named import 併記形（`import Link, { LinkProps } from 'next/link'`）でも
    # import 検出漏れでファイル丸ごとスキップにならない。
    (
        "src/ui/x.tsx",
        "import Link, { LinkProps } from 'next/link'\n"
        'export const x = <Link href="/api/auth/logout">logout</Link>\n',
        1,
    ),
    # 検査1: next/link を import していないファイルは <Link href="/api/..."> 風の文字列が
    # あっても誤検出しない（false positive 方向）。
    (
        "src/ui/no-import.tsx",
        'export const x = <Link href="/api/auth/logout">logout</Link>\n',
        0,
    ),
    # 検査2: 関数式代入形（`export const GET = async function (req) { ... }`）でも
    # cookies.delete( を検出する。
    (
        "app/api/weird2/route.ts",
        "export const GET = async function (request: Request) {\n"
        "  const res = NextResponse.redirect('/')\n  res.cookies.delete('session')\n  return res\n}\n",
        1,
    ),
]


def run_self_test() -> int:
    failures: list[str] = []

    # 回帰テスト（Issue #612）: strip_comments / find_matching_brace / find_tag_end が
    # tools/ts_source.py の共通実装そのものであることを確認する。誰かがローカル実装へ
    # 書き戻してしまう（重複再発）と、この import 元との同一性チェックで検出できる。
    import ts_source

    for name in ("strip_comments", "find_matching_brace", "find_tag_end"):
        local_fn = globals()[name]
        shared_fn = getattr(ts_source, name)
        if local_fn is not shared_fn:
            failures.append(
                f"  regression/{name}_is_ts_source_shared: "
                f"check_prefetchable_side_effects.{name} が ts_source.{name} と同一関数では"
                "ない（ローカル実装へ書き戻された疑いがあります・Issue #612 の再発）"
            )

    for rel, text, want_n in CASES:
        got = check_file(rel, text)
        if len(got) != want_n:
            failures.append(f"  {rel}: want {want_n} 件, got {len(got)} 件 :: {got}")

    if failures:
        print("❌ check_prefetchable_side_effects --self-test FAILED")
        print("\n".join(failures))
        return 1
    print(f"✅ check_prefetchable_side_effects --self-test PASSED（{len(CASES)} ケース）")
    return 0


# --------------------------------------------------------------------------- main

def main() -> int:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        return run_self_test()

    targets, warnings = collect_targets(argv)
    if not targets:
        print("ℹ️ 検査対象のコード（app/ · src/ の .tsx / route.ts）がありません")
        return 0

    violations: list[str] = []
    for rel in targets:
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"{rel} を読めませんでした: {exc}")
            continue
        violations.extend(check_file(rel, text))

    for w in warnings:
        print(f"⚠️ {w}")
    for v in violations:
        print(f"❌ {v}")

    if violations:
        print(
            f"\nプリフェッチされる副作用付き API ルートの疑いが {len(violations)} 件 / "
            f"検査 {len(targets)} ファイル。next/link の <Link> で /api/ を指さない、"
            "GET ハンドラで Cookie を変更しないでください。"
        )
        return 1
    print(f"✅ プリフェッチ副作用 OK（{len(targets)} ファイル）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
