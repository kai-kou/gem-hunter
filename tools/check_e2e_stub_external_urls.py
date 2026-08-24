#!/usr/bin/env python3
"""check_e2e_stub_external_urls.py — E2E スタブ HTML の外部サブリソース混入検査

背景（実測・2026-08-24）: `e2e/stub/server.mjs` のフィクスチャに外部 URL の画像
（`<img src="https://img.shields.io/...">`）が残っていたため、到達不可なテスト用 Chromium で
`page.goto()`（既定 `waitUntil: 'load'`）が 1 回あたり約 12.6 秒ブロックし、12 テストで
スイート全体の 46%（約 151 秒）を浪費していた。`page.route` で遮断すれば 12,793ms → 219ms。
`NFR-24`（外部 API はモック化してネットワークを遮断する）に対する違反でもある。本ツールはこの
混入が再発しないよう、E2E スタブが返す HTML 断片から「ブラウザが自動的に取得しに行くサブリソース」
の URL を静的抽出し、外部ホストを指していないか検査する。

検出対象 vs 対象外（この区別が本ツールの肝）:
  検出する   = ページ読み込み時にブラウザが **自動で** 取得しにいくもの
               （`<img src>` / `<script src>` / `<link href>` / `<iframe src>` / `srcset` /
               CSS の `url(...)`）。これらは実 URL が外部を指していると即座にネットワーク往復が
               発生し、到達不可なら上記の実測どおりテストを丸ごとブロックする。
  検出しない = **データとしての URL 文字列**（`<a href>` のリンク先、JSON フィクスチャの
               `html_url` / `repository_url` 等）。これらはブラウザが自動取得せず、テストが
               「長い URL でも横スクロールしない」等の表示検証に使う対象そのものであり、
               外部ホストであっても遅延を生まない。誤って検出すると正当なテストフィクスチャを
               破壊するため、本ツールは HTML タグの構造（`<img ...src=...>` 等）に一致した
               ものだけを検出し、JSON フィールドや `<a href>` は対象外にしている。

対象ファイル: 既定で `e2e/stub/` 配下の `*.mjs`（スタブ HTTP サーバーが HTML 文字列を
組み立てている場所。JS の文字列リテラル/テンプレートリテラルの中身であっても、HTML の
`属性="値"` はソーステキスト上にそのまま現れるため、AST を組まず正規表現でも十分検出できる）。

許容する値: `data:` URI・相対パス（`/images/x.webp` 等）・同一オリジン
（`http://127.0.0.1:...` / `http://localhost:...`）。テンプレートリテラルの `${IDENT}` 展開は、
同一ファイル内の `const IDENT = '...'`（他の const への参照チェーンも可）を辿って解決を試みる
（本ファイルの `README_BADGE_IMAGE` → `PRIVATE_MIXED_AVATAR` → `data:...` のような 2 段の
チェーンを解決できれば十分という YAGNI 判断。解決できない場合は誤検出を避けるため見逃す側に倒す）。

使い方:
  python3 tools/check_e2e_stub_external_urls.py             # e2e/stub/*.mjs を検査
  python3 tools/check_e2e_stub_external_urls.py --self-test # ネットワーク非依存のユニットテスト
  違反があれば exit 1（❌・ファイル:行番号・URL・理由を stderr に出す）。
  対象ファイルが読めない/デコードできない場合は「違反なし」にせず exit 1（⚠️・対象ファイルを明示）。
  走査対象が 1 件も見つからない場合（`e2e/stub/` のリネーム・移動等）も同様に「違反なし」にせず
  exit 1（⚠️・探索先パスを明示。「未実行」と「合格」を終了コードで区別できないままにしない）。
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_DIR = REPO_ROOT / "e2e" / "stub"

LOCAL_HOSTS = {"localhost", "127.0.0.1"}

# ブラウザが自動取得するサブリソースの属性・タグ（対象）。`<a href>` は含めない（対象外・上記参照）。
_ATTR_TAG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("img src", re.compile(r"<img\b[^>]*?\bsrc\s*=\s*(['\"`])(.*?)\1", re.IGNORECASE)),
    ("script src", re.compile(r"<script\b[^>]*?\bsrc\s*=\s*(['\"`])(.*?)\1", re.IGNORECASE)),
    ("link href", re.compile(r"<link\b[^>]*?\bhref\s*=\s*(['\"`])(.*?)\1", re.IGNORECASE)),
    ("iframe src", re.compile(r"<iframe\b[^>]*?\bsrc\s*=\s*(['\"`])(.*?)\1", re.IGNORECASE)),
    ("srcset", re.compile(r"\bsrcset\s*=\s*(['\"`])(.*?)\1", re.IGNORECASE)),
]
_CSS_URL_RE = re.compile(r"\burl\(\s*(['\"])(.*?)\1\s*\)", re.IGNORECASE)

_TEMPLATE_IDENT_RE = re.compile(r"^\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}$")
_CONST_DECL_RE_TMPL = r"\bconst\s+{ident}\s*=\s*"


class ScanError(Exception):
    """対象ファイルが読めない/デコードできない場合の例外（「違反なし」への黙殺を避ける）。"""


def _lineno_at(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def resolve_const(text: str, ident: str, depth: int = 5) -> str | None:
    """`const IDENT = ...` を辿ってリテラル文字列に解決する（他 const への参照チェーンも可）。

    このリポジトリのコードはセミコロンを付けない流儀（`const X = 'literal'` で改行）のため、
    セミコロンではなく「RHS の直後の 1 トークン」で判定する: RHS が引用符で始まれば文字列
    リテラルとしてエスケープを解決し、識別子であれば別の const として再帰的に解決する。
    それ以外（式・関数呼び出し等）は解決できないため None を返す（式評価はしない・YAGNI・
    誤検出よりは見逃しに倒す）。
    """
    if depth <= 0:
        return None
    match = re.search(_CONST_DECL_RE_TMPL.format(ident=re.escape(ident)), text)
    if not match:
        return None
    pos = match.end()
    while pos < len(text) and text[pos] in " \t\r\n":
        pos += 1
    if pos >= len(text):
        return None

    ch = text[pos]
    if ch in "'\"`":
        j = pos + 1
        buf: list[str] = []
        while j < len(text) and text[j] != ch:
            if text[j] == "\\" and j + 1 < len(text):
                buf.append(text[j + 1])
                j += 2
                continue
            buf.append(text[j])
            j += 1
        return "".join(buf)

    ident_match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[pos:])
    if not ident_match:
        return None
    return resolve_const(text, ident_match.group(0), depth - 1)


def resolve_value(text: str, value: str) -> str:
    """値が `${IDENT}` の形（それだけ）なら const チェーンで解決を試みる。解決できなければ元の値を返す。"""
    match = _TEMPLATE_IDENT_RE.match(value.strip())
    if not match:
        return value
    resolved = resolve_const(text, match.group(1))
    return resolved if resolved is not None else value


def is_external(value: str) -> bool:
    """許容できない（外部ホストへ自動的に到達しにいく）URL かどうかを判定する。"""
    value = value.strip()
    if not value or value.startswith("data:"):
        return False
    if value.startswith("//"):
        # プロトコル相対 URL。ホスト部だけを見る。
        host = urlparse("http:" + value).hostname
        return host not in LOCAL_HOSTS
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https"):
        return parsed.hostname not in LOCAL_HOSTS
    # スキームなし（相対パス・`${...}` を解決できなかった残骸を含む）は許容側に倒す。
    return False


def find_violations(path: Path, text: str) -> list[tuple[int, str, str]]:
    """`(行番号, 種別, URL)` のリストを返す（外部ホストのみ）。"""
    violations: list[tuple[int, str, str]] = []

    for kind, pattern in _ATTR_TAG_PATTERNS:
        for m in pattern.finditer(text):
            raw_value = m.group(2)
            lineno = _lineno_at(text, m.start())
            if kind == "srcset":
                # `"url1 1x, url2 2x"` 形式。カンマ区切りの各記述子の先頭トークンが URL。
                for descriptor in raw_value.split(","):
                    token = descriptor.strip().split()[0] if descriptor.strip() else ""
                    if not token:
                        continue
                    resolved = resolve_value(text, token)
                    if is_external(resolved):
                        violations.append((lineno, kind, resolved))
            else:
                resolved = resolve_value(text, raw_value)
                if is_external(resolved):
                    violations.append((lineno, kind, resolved))

    for m in _CSS_URL_RE.finditer(text):
        raw_value = m.group(2)
        lineno = _lineno_at(text, m.start())
        resolved = resolve_value(text, raw_value)
        if is_external(resolved):
            violations.append((lineno, "css url()", resolved))

    return violations


def discover_targets(target_dir: Path = DEFAULT_TARGET_DIR) -> list[Path]:
    if not target_dir.exists():
        return []
    return sorted(target_dir.rglob("*.mjs"))


def run_checks(target_dir: Path = DEFAULT_TARGET_DIR) -> tuple[list[str], list[str], int]:
    """`(errors, scan_error_messages, scanned_count)` を返す。呼び出し側で優先順位を判断する。

    走査対象が 1 件も見つからなかった場合（`e2e/stub/` のリネーム・移動等）は「違反なし」と
    区別できないため、`scan_errors` に積んで非ゼロ終了させる（解析不能ファイルと同じ扱いに
    寄せる・「未実行」と「合格」を終了コードで取り違えないための一貫性）。
    """
    errors: list[str] = []
    scan_errors: list[str] = []

    targets = discover_targets(target_dir)
    if not targets:
        scan_errors.append(
            f"対象ファイルが 1 件も見つからなかった（探索先: {target_dir}）。"
            "ディレクトリの移動・リネームの可能性があるため検査未実行として扱う"
        )
        return errors, scan_errors, 0

    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            scan_errors.append(f"{path}: 読み込みに失敗（{e.__class__.__name__}: {e}）")
            continue

        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        for lineno, kind, url in find_violations(path, text):
            errors.append(
                f"{rel}:{lineno} [{kind}] {url}"
                "（テスト用 Chromium から到達不可なホストへの自動フェッチは page.goto() を"
                "1回あたり約12.6秒ブロックする。NFR-24 違反。data: URI か同一オリジンに差し替える）"
            )

    return errors, scan_errors, len(targets)


def self_test() -> int:
    """ネットワーク不要のユニットテスト。"""
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    # 1. 外部ホストの <img src> を検出する
    text = '<img src="https://img.shields.io/badge/build-passing-green" alt="badge">'
    v = find_violations(Path("x.mjs"), text)
    expect(len(v) == 1 and v[0][1] == "img src", f"外部 img src を検出できていない: {v}")

    # 2. data: URI の <img src> を検出しない
    text = '<img src="data:image/png;base64,iVBORw0KGgo=" alt="badge">'
    expect(find_violations(Path("x.mjs"), text) == [], "data: URI を誤検出している")

    # 3. 相対パス・同一オリジンを検出しない
    text = (
        '<img src="/images/logo.webp" alt="logo">'
        '<img src="http://127.0.0.1:8788/avatar.png" alt="a">'
        '<img src="http://localhost:8788/avatar.png" alt="b">'
    )
    expect(find_violations(Path("x.mjs"), text) == [], "相対パス/同一オリジンを誤検出している")

    # 4. 外部ホストの <a href> を検出しない（偽陽性防止）
    text = '<a href="https://github.com/octostub/octo-readme-rich/blob/main/docs/build.md">docs</a>'
    expect(find_violations(Path("x.mjs"), text) == [], "<a href> を誤って検出している")

    # 5. JSON フィクスチャ相当の html_url 文字列を検出しない
    text = '{"html_url": "https://github.com/octostub/octo-widgets", "id": 1}'
    expect(find_violations(Path("x.mjs"), text) == [], "JSON の html_url を誤検出している")

    # 6. script src / link href / iframe src も検出する
    text = (
        '<script src="https://cdn.example.com/lib.js"></script>'
        '<link href="https://fonts.example.com/font.css" rel="stylesheet">'
        '<iframe src="https://embed.example.com/widget"></iframe>'
    )
    v = find_violations(Path("x.mjs"), text)
    kinds = {kind for _, kind, _ in v}
    expect(kinds == {"script src", "link href", "iframe src"}, f"script/link/iframe を検出できていない: {v}")

    # 7. srcset のうち外部ホストの記述子だけを検出する
    text = '<img srcset="/local.webp 1x, https://cdn.example.com/remote.webp 2x">'
    v = find_violations(Path("x.mjs"), text)
    expect(
        len(v) == 1 and v[0][2] == "https://cdn.example.com/remote.webp",
        f"srcset の外部記述子を検出できていない: {v}",
    )

    # 8. CSS url(...) の外部ホストを検出する
    text = 'div{background-image:url("https://cdn.example.com/bg.png")}'
    v = find_violations(Path("x.mjs"), text)
    expect(len(v) == 1 and v[0][1] == "css url()", f"CSS url() を検出できていない: {v}")

    # 9. ${IDENT} の const チェーン解決（本ファイルの README_BADGE_IMAGE パターン）
    text = (
        "const PRIVATE_MIXED_AVATAR = 'data:image/png;base64,AAAA'\n"
        "const README_BADGE_IMAGE = PRIVATE_MIXED_AVATAR\n"
        '<img src="${README_BADGE_IMAGE}" alt="badge">'
    )
    expect(find_violations(Path("x.mjs"), text) == [], "const チェーン解決後の data: URI を誤検出している")

    text2 = (
        "const REMOTE_BADGE = 'https://img.shields.io/badge.svg'\n"
        '<img src="${REMOTE_BADGE}" alt="badge">'
    )
    v = find_violations(Path("x.mjs"), text2)
    expect(len(v) == 1, f"const チェーン解決後の外部 URL を検出できていない: {v}")

    # 10. 解決できない ${IDENT} は誤検出しない（見逃し側に倒す）
    text = '<img src="${UNKNOWN_IDENT}" alt="badge">'
    expect(find_violations(Path("x.mjs"), text) == [], "未解決の ${IDENT} を誤検出している")

    # 11. 走査対象が 0 件（ディレクトリの移動・リネーム等）は「合格」と区別できない未実行として扱う
    with tempfile.TemporaryDirectory() as tmp:
        missing_dir = Path(tmp) / "does-not-exist"
        errors, scan_errors, scanned_count = run_checks(missing_dir)
        expect(errors == [], f"対象ゼロ件で errors が非空になっている: {errors}")
        expect(scanned_count == 0, f"対象ゼロ件で scanned_count が 0 でない: {scanned_count}")
        expect(
            len(scan_errors) == 1 and str(missing_dir) in scan_errors[0],
            f"対象ゼロ件が scan_errors として報告されていない: {scan_errors}",
        )

    if failures:
        for label in failures:
            print(f"[e2e-stub-external-urls] SELF-TEST FAIL: {label}", file=sys.stderr)
        return 1
    print("[e2e-stub-external-urls] self-test OK（11 項目）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行する")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    errors, scan_errors, scanned_count = run_checks()

    if scan_errors:
        for msg in scan_errors:
            print(f"⚠️ [e2e-stub-external-urls] {msg}", file=sys.stderr)
        return 1

    if errors:
        for msg in errors:
            print(f"❌ [e2e-stub-external-urls] {msg}", file=sys.stderr)
        return 1

    print(f"[e2e-stub-external-urls] OK（外部サブリソース URL の混入なし・{scanned_count} ファイル走査）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
