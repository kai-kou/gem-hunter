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
（`e2e/stub/server.mjs` の `README_BADGE_IMAGE` → `TRANSPARENT_1PX_PNG`（`data:...`）のような
参照 1 段を解決できれば十分という YAGNI 判断。チェーンが複数段でも `resolve_const()` は
再帰的に辿るため対応できる。解決できない場合は誤検出を避けるため見逃す側に倒す）。

既知の制約: 属性名の一致は「直前が英数字・`-`・`_` でない」ことだけを見る（`data-src` を
誤って `src` と認識しない・Layer 1 指摘 #1 の再発防止）。属性値はクォート付き
（`'`/`"`/`` ` ``）・未クォート（`src=https://...`）のどちらも拾う（Layer 1 指摘 #4）。

使い方:
  python3 tools/check_e2e_stub_external_urls.py             # e2e/stub/*.mjs を検査
  python3 tools/check_e2e_stub_external_urls.py --self-test # ネットワーク非依存のユニットテスト
  違反があれば exit 1（❌・ファイル:行番号・URL・理由を stderr に出す）。
  対象ファイルが読めない/デコードできない場合は「違反なし」にせず exit 1（⚠️・対象ファイルを明示）。
  走査対象が 1 件も見つからない場合（`e2e/stub/` のリネーム・移動等）も同様に「違反なし」にせず
  exit 1（⚠️・探索先パスを明示。「未実行」と「合格」を終了コードで区別できないままにしない）。
  ⚠️（解析不能・対象ゼロ件）と ❌（違反）は同時に起こりうるため、どちらか一方だけを表示して
  もう一方を握り潰すことはしない（両方を出力してから非ゼロ終了する・Layer 1 指摘 #2 の再発防止）。
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

# 🔴 バックトラッキング量の上限（Layer 1 指摘 #6・実測で O(n²) を確認）。
#    `<img\b[^>]*?...src=...` のような「ラジー量指定子 `*?` の後ろに離れた必須リテラルが続く」
#    形は、リテラルが見つからない入力（例: `>` の無い壊れた `<img` が大量に並ぶ・外部から
#    取り込んだ HTML 断片の偶発的な混入）で 1 出現あたり O(残り文字数) の再走査を招き、
#    出現回数 × 残り長 で全体 O(n²) になる（`'<img ' * n` で n=1000/2000/4000 が
#    0.086s/0.350s/1.322s と 4 乗ではなく概ね n² で伸びることを実測）。
#    対策は 2 段構成にすること: ① まず「開始タグはここまで」という上限付きで `<tag ...>` を
#    切り出す（`[^>]{0,N}` は N が有限なので 1 出現あたりの最悪コストが定数で頭打ちになる）
#    → ② その小さく切り出した部分文字列の中だけで属性を探す（部分文字列自体が高々 N 文字
#    なので、その中でどれだけ `.*?` が暴れても定数コスト）。
#    上限値 4096: このリポジトリの実際のタグ（README リッチ HTML 含む）は最長でも数百文字
#    程度で、`width`/`height`/`alt`/`class` 等の属性を足しても数千文字に達することは
#    通常ない。到達不可能に大きく余裕を持たせつつ、悪意・事故のどちらでも 1 出現あたりの
#    最悪コストを定数（4096 文字分の走査）に固定するための値。
_MAX_TAG_LEN = 4096
_MAX_VALUE_LEN = 4096

# 属性値はクォート付き（group 1=クォート文字 / group 2=値）と未クォート（group 3=値）の
# どちらも拾う（HTML5 は未クォート属性値を許可する・Layer 1 指摘 #4）。値の長さは
# `_MAX_VALUE_LEN` で有界にする（閉じクォートが無い壊れた入力でも走査コストを定数に抑える・
# 上記 #6 と同じ理由）。
_VALUE_ALT = rf"(?:(['\"`])(.{{0,{_MAX_VALUE_LEN}}}?)\1|([^\s>]{{1,{_MAX_VALUE_LEN}}}))"


def _extract_value(m: re.Match[str]) -> str:
    """クォート付き/未クォートのどちらでマッチしたかを問わず、抽出した属性値を返す。"""
    return m.group(2) if m.group(1) is not None else m.group(3)


# ブラウザが自動取得するサブリソースの属性・タグ（対象）。`<a href>` は含めない（対象外・上記参照）。
# `(kind, tag, attr)`: ① まず `<tag ...>` を `_MAX_TAG_LEN` で有界に切り出し（②の土台）、
# ② 切り出した短い部分文字列の中だけで属性名を探す。属性名の直前を `(?<![\w-])` で
# 「英数字・`-`・`_` でない」ことを要求し、`data-src` / `data-href` の内部一致
# （`\b` では `-` の後ろも語境界になるため誤検出していた）を防ぐ（Layer 1 指摘 #1）。
_TAG_ATTR_SPECS: list[tuple[str, str, str]] = [
    ("img src", "img", "src"),
    ("script src", "script", "src"),
    ("link href", "link", "href"),
    ("iframe src", "iframe", "src"),
]
_TAG_OPEN_PATTERNS: dict[str, re.Pattern[str]] = {
    tag: re.compile(rf"<{tag}\b[^>]{{0,{_MAX_TAG_LEN}}}>", re.IGNORECASE)
    for _, tag, _ in _TAG_ATTR_SPECS
}
_ATTR_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    attr: re.compile(rf"(?<![\w-]){attr}\s*=\s*{_VALUE_ALT}", re.IGNORECASE)
    for _, _, attr in _TAG_ATTR_SPECS
}
# srcset はタグを問わず出現しうる汎用属性のため、タグ切り出しは介さず直接値だけを有界に探す
# （`_VALUE_ALT` が既に有界なので、タグ切り出しを挟まなくても #6 の量指定子暴走は起きない）。
_SRCSET_RE = re.compile(rf"(?<![\w-])srcset\s*=\s*{_VALUE_ALT}", re.IGNORECASE)

# CSS url() の未クォート値は `)` の直前で終わる（img/href 用の `_VALUE_ALT` を使い回すと
# 閉じ括弧まで値に取り込んでしまうため、括弧を止め文字に含めた専用の値パターンを使う）。
# こちらも同じ理由で長さを有界にする。
_CSS_URL_VALUE_ALT = rf"(?:(['\"])(.{{0,{_MAX_VALUE_LEN}}}?)\1|([^\s)]{{1,{_MAX_VALUE_LEN}}}))"
_CSS_URL_RE = re.compile(rf"\burl\(\s*{_CSS_URL_VALUE_ALT}\s*\)", re.IGNORECASE)

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
    """`(行番号, 種別, URL)` のリストを返す（外部ホストのみ）。

    img/script/link/iframe は 2 段構成（① `_MAX_TAG_LEN` で有界に開始タグを切り出す →
    ② その短い部分文字列の中だけで属性を探す）で O(n²) バックトラッキングを避ける
    （モジュール冒頭のコメント・Layer 1 指摘 #6 参照）。
    """
    violations: list[tuple[int, str, str]] = []

    for kind, tag, attr in _TAG_ATTR_SPECS:
        tag_pattern = _TAG_OPEN_PATTERNS[tag]
        attr_pattern = _ATTR_VALUE_PATTERNS[attr]
        for tag_match in tag_pattern.finditer(text):
            attr_match = attr_pattern.search(tag_match.group(0))
            if attr_match is None:
                continue
            raw_value = _extract_value(attr_match)
            lineno = _lineno_at(text, tag_match.start())
            resolved = resolve_value(text, raw_value)
            if is_external(resolved):
                violations.append((lineno, kind, resolved))

    for m in _SRCSET_RE.finditer(text):
        raw_value = _extract_value(m)
        lineno = _lineno_at(text, m.start())
        # `"url1 1x, url2 2x"` 形式。カンマ区切りの各記述子の先頭トークンが URL。
        for descriptor in raw_value.split(","):
            token = descriptor.strip().split()[0] if descriptor.strip() else ""
            if not token:
                continue
            resolved = resolve_value(text, token)
            if is_external(resolved):
                violations.append((lineno, "srcset", resolved))

    for m in _CSS_URL_RE.finditer(text):
        raw_value = _extract_value(m)
        lineno = _lineno_at(text, m.start())
        resolved = resolve_value(text, raw_value)
        if is_external(resolved):
            violations.append((lineno, "css url()", resolved))

    return violations


def discover_targets(target_dir: Path = DEFAULT_TARGET_DIR) -> tuple[list[Path], list[str]]:
    """`(対象ファイル一覧, 除外理由メッセージ一覧)` を返す。

    シンボリックリンクは対象から除外する（Layer 1 指摘 #5）: `Path.rglob()` はシンボリック
    リンクをそのまま列挙してしまい、リンク先が `target_dir` の外（例: リポジトリ外の任意
    ファイル）を指していても検証なしに読み込まれる。① `p.is_symlink()` でリンクそのものを弾き、
    ② 念のため解決後のパスが `target_dir` の配下に収まっているか（シンボリックな親ディレクトリ
    経由での脱出も含めて）二重に確認する。除外した場合は黙って飛ばさず理由を返す（本ツールが
    徹底している「未実行を黙殺しない」方針＝ `⚠️` 表示に合わせる）。
    """
    if not target_dir.exists():
        return [], []

    resolved_root = target_dir.resolve()
    targets: list[Path] = []
    skipped: list[str] = []

    for p in sorted(target_dir.rglob("*.mjs")):
        if p.is_symlink():
            skipped.append(f"{p}: シンボリックリンクのため走査対象から除外した")
            continue
        try:
            resolved = p.resolve()
        except OSError as e:
            skipped.append(f"{p}: パス解決に失敗したため走査対象から除外した（{e.__class__.__name__}: {e}）")
            continue
        if not resolved.is_relative_to(resolved_root):
            skipped.append(
                f"{p}: 解決先が探索先ディレクトリの外（{resolved}）のため走査対象から除外した"
            )
            continue
        targets.append(p)

    return targets, skipped


def run_checks(target_dir: Path = DEFAULT_TARGET_DIR) -> tuple[list[str], list[str], int]:
    """`(errors, scan_error_messages, scanned_count)` を返す。呼び出し側で優先順位を判断する。

    走査対象が 1 件も見つからなかった場合（`e2e/stub/` のリネーム・移動等）は「違反なし」と
    区別できないため、`scan_errors` に積んで非ゼロ終了させる（解析不能ファイルと同じ扱いに
    寄せる・「未実行」と「合格」を終了コードで取り違えないための一貫性）。シンボリックリンクの
    除外（上記 `discover_targets()`）も同じ `scan_errors` に合流させ、同じ扱いにする。
    """
    errors: list[str] = []
    scan_errors: list[str] = []

    targets, skipped = discover_targets(target_dir)
    scan_errors.extend(skipped)

    if not targets:
        if not skipped:
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

    # 9. ${IDENT} の const チェーン解決（`resolve_const()` が再帰的にチェーンを辿れることの検証。
    #    フィクスチャは 2 段の参照チェーンにしているが、実際の e2e/stub/server.mjs では
    #    README_BADGE_IMAGE は TRANSPARENT_1PX_PNG を直接参照している・1 段）
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

    # 12.（Layer 1 指摘 #1・最重要）`data-src` を実 src と誤認しない
    # 12a. 偽陰性: data-src の後ろに実際の外部 src がある場合、その実 src を検出できること
    text = '<img data-src="/local.png" src="https://evil-cdn.example.com/badge.png" alt="x">'
    v = find_violations(Path("x.mjs"), text)
    expect(
        len(v) == 1 and v[0][2] == "https://evil-cdn.example.com/badge.png",
        f"data-src と実 src が共存する場合に実 src を検出できていない（偽陰性）: {v}",
    )
    # 12b. 偽陽性: src 属性が無く data-src だけの場合、誤検出しないこと
    text = '<img data-src="https://cdn.example.com/lazy.png" class="lazyload" alt="lazy">'
    expect(find_violations(Path("x.mjs"), text) == [], f"data-src だけの img を誤って src として検出している（偽陽性）")
    # 12c. href / srcset も同様に data- 接頭辞の内部一致をしないこと
    text = '<link data-href="https://cdn.example.com/x.css" rel="preload">'
    expect(find_violations(Path("x.mjs"), text) == [], "data-href を href と誤認している")
    text = '<img data-srcset="https://cdn.example.com/x.webp 1x" alt="x">'
    expect(find_violations(Path("x.mjs"), text) == [], "data-srcset を srcset と誤認している")

    # 13.（Layer 1 指摘 #4）未クォート属性値も検出する
    text = '<img src=https://evil.com/x.png alt="x">'
    v = find_violations(Path("x.mjs"), text)
    expect(
        len(v) == 1 and v[0][2] == "https://evil.com/x.png",
        f"未クォートの src 属性値を検出できていない: {v}",
    )
    text = "<img src=/local.webp alt='x'>"
    expect(find_violations(Path("x.mjs"), text) == [], "未クォートの相対パスを誤検出している")

    # 14.（Layer 1 指摘 #2）scan_errors と errors が同時に発生しても両方とも返る
    #     （main() が片方だけ表示してもう片方を握り潰さないことの前提を保証する）
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / "broken.mjs").write_bytes(b"\xff\xfe\x00broken-non-utf8")
        (tmp_dir / "violation.mjs").write_text(
            '<img src="https://evil-cdn.example.com/badge.png" alt="x">', encoding="utf-8"
        )
        errors, scan_errors, scanned_count = run_checks(tmp_dir)
        expect(scanned_count == 2, f"対象ファイル数の集計が想定と違う: {scanned_count}")
        expect(len(scan_errors) == 1, f"デコード不能ファイルが scan_errors に載っていない: {scan_errors}")
        expect(len(errors) == 1, f"デコード不能ファイルと同時に検出すべき違反が errors に載っていない: {errors}")

    # 15.（Layer 1 指摘 #5）シンボリックリンクは走査対象から除外し、リンク先の内容を漏らさない
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        outside_file = tmp_root / "outside.mjs"
        outside_file.write_text(
            '<img src="https://leak.example.com/token=ABC123" alt="secret">', encoding="utf-8"
        )
        stub_dir = tmp_root / "stub"
        stub_dir.mkdir()
        symlink_path = stub_dir / "evil.mjs"
        try:
            symlink_path.symlink_to(outside_file)
        except OSError as e:
            # シンボリックリンク作成が許可されない実行環境（一部サンドボックス）ではこの項目だけ
            # 検証をスキップする（環境差は自己解決不可・テスト失敗として扱わない）。
            print(
                f"[e2e-stub-external-urls] SELF-TEST SKIP: シンボリックリンク作成不可のため項目15をスキップ"
                f"（{e.__class__.__name__}: {e}）",
                file=sys.stderr,
            )
        else:
            errors, scan_errors, scanned_count = run_checks(stub_dir)
            expect(scanned_count == 0, f"シンボリックリンクが走査対象数に含まれている: {scanned_count}")
            expect(
                "https://leak.example.com" not in "".join(errors),
                f"シンボリックリンク先の内容が errors に漏れている: {errors}",
            )
            expect(
                any("シンボリックリンク" in msg for msg in scan_errors),
                f"シンボリックリンク除外が ⚠️ として報告されていない: {scan_errors}",
            )

    if failures:
        for label in failures:
            print(f"[e2e-stub-external-urls] SELF-TEST FAIL: {label}", file=sys.stderr)
        return 1
    print("[e2e-stub-external-urls] self-test OK（15 項目）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行する")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    errors, scan_errors, scanned_count = run_checks()

    # ⚠️（解析不能・対象ゼロ件）と ❌（違反）は同時に起こりうる。片方だけ表示してもう片方を
    # 握り潰すと、開発者が ⚠️ を直して再実行するまで本当の違反に気づけない（Layer 1 指摘 #2）。
    # そのため両方を出し切ってから非ゼロ終了する。
    for msg in scan_errors:
        print(f"⚠️ [e2e-stub-external-urls] {msg}", file=sys.stderr)
    for msg in errors:
        print(f"❌ [e2e-stub-external-urls] {msg}", file=sys.stderr)

    if scan_errors or errors:
        return 1

    print(f"[e2e-stub-external-urls] OK（外部サブリソース URL の混入なし・{scanned_count} ファイル走査）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
