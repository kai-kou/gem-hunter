#!/usr/bin/env python3
"""ランディングページ（site/）の静的検査。

`site/` はアプリ本体の検査（eslint / tsc / vitest / playwright / check_contrast.py /
Lighthouse ゲート）のどれにも掛からない。公開面が壊れても緑のままマージされてしまうため、
ネットワーク不要・決定論的に検知できる範囲だけをここで機械化する。

検査内容:
  1. タグの閉じ漏れ・重複 id（HTMLParser で走査）
  2. ローカル参照アセット（src / href）の実在
  3. <img> の width / height と実ファイル実寸の一致（撮り直し後の更新漏れ = CLS を止める）
  4. ページ内アンカー（#foo）の参照先が存在すること
  5. 自リポジトリ docs への GitHub リンク（blob/tree/main/<path>）が実在すること
  6. LP に書いた ADR 本数が docs/adr/ の実数と一致すること
  7. footer から README 本体への直リンクが存在すること（LP → README の導線）

使い方:
  python3 tools/check_site.py            # 検査（違反があれば exit 1）
  python3 tools/check_site.py --self-test  # 検査ロジック自体の自己テスト
"""

from __future__ import annotations

import re
import struct
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
PAGES = ["index.html", "404.html"]
REPO_LINK_RE = re.compile(
    r"https://github\.com/kai-kou/gem-hunter/(?:blob|tree)/main/([^\"'\s)#]+)"
)
FOOTER_RE = re.compile(r"<footer\b[^>]*>.*?</footer>", re.S)
README_LINK_RE = re.compile(
    r"https://github\.com/kai-kou/gem-hunter/blob/main/README\.md"
)
# 自己終了・空要素（閉じタグを持たない）
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    fourcc = data[12:16]
    if fourcc == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if fourcc == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if fourcc == b"VP8 ":
        # 3 バイトのフレームタグ + 3 バイトの sync code のあとに 14bit 幅・14bit 高さ
        if data[23:26] != b"\x9d\x01\x2a":
            return None
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    return None


def image_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    return png_size(data) or webp_size(data)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.ids: list[tuple[str, int]] = []
        self.images: list[tuple[dict[str, str], int]] = []
        self.refs: list[tuple[str, int]] = []
        self.unbalanced: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: (value or "") for key, value in attrs}
        line = self.getpos()[0]
        if "id" in attr:
            self.ids.append((attr["id"], line))
        if tag == "img":
            self.images.append((attr, line))
        for key in ("src", "href"):
            if key in attr:
                self.refs.append((attr[key], line))
        if tag not in VOID_TAGS:
            self.stack.append((tag, line))

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.unbalanced.append(f"{self.getpos()[0]} 行: </{tag}> に対応する開始タグがない")
            return
        open_tag, open_line = self.stack.pop()
        if open_tag != tag:
            self.unbalanced.append(
                f"{self.getpos()[0]} 行: </{tag}> が閉じようとした相手は <{open_tag}>（{open_line} 行）"
            )


def check_page(page: str, errors: list[str]) -> PageParser:
    path = SITE_DIR / page
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))

    for message in parser.unbalanced:
        errors.append(f"{page}: {message}")
    for tag, line in parser.stack:
        errors.append(f"{page}: <{tag}>（{line} 行）が閉じられていない")

    seen: dict[str, int] = {}
    for value, line in parser.ids:
        if value in seen:
            errors.append(f"{page}: id=\"{value}\" が重複している（{seen[value]} 行と {line} 行）")
        seen[value] = line

    anchors = set(seen) | {"top"}
    for ref, line in parser.refs:
        if ref.startswith("#"):
            target = ref[1:]
            if target and target not in anchors:
                errors.append(f"{page}:{line} アンカー {ref} の参照先が存在しない")
            continue
        if ref.startswith(("http://", "https://", "mailto:", "data:")):
            continue
        local = ref.lstrip("/")
        if local.startswith("gem-hunter/"):  # 404.html はサブパス付き絶対パス
            local = local[len("gem-hunter/") :]
        candidate = (SITE_DIR / local).resolve()
        if not candidate.exists():
            errors.append(f"{page}:{line} 参照先 {ref} が存在しない")

    for attr, line in parser.images:
        src = attr.get("src", "")
        if src.startswith(("http://", "https://", "data:")):
            continue
        local = src.lstrip("/")
        if local.startswith("gem-hunter/"):
            local = local[len("gem-hunter/") :]
        candidate = SITE_DIR / local
        if not candidate.exists():
            continue  # 参照切れは上で報告済み
        if "width" not in attr or "height" not in attr:
            errors.append(f"{page}:{line} <img src=\"{src}\"> に width / height が無い（CLS の原因）")
            continue
        actual = image_size(candidate)
        if actual is None:
            errors.append(f"{page}:{line} {src} の画像サイズを解析できなかった")
            continue
        declared = (int(attr["width"]), int(attr["height"]))
        # 表示サイズとして縮小指定する場合があるので、縦横比の一致で判定する
        if abs(declared[0] / declared[1] - actual[0] / actual[1]) > 0.01:
            errors.append(
                f"{page}:{line} {src} の width/height={declared[0]}x{declared[1]} が"
                f" 実寸 {actual[0]}x{actual[1]} と縦横比で食い違う"
            )
    return parser


def check_repo_links(errors: list[str]) -> None:
    for page in PAGES:
        text = (SITE_DIR / page).read_text(encoding="utf-8")
        for match in REPO_LINK_RE.finditer(text):
            target = REPO_ROOT / match.group(1)
            if not target.exists():
                errors.append(f"{page}: リンク先 {match.group(1)} がリポジトリに存在しない")


def check_adr_count(errors: list[str]) -> None:
    actual = len(list((REPO_ROOT / "docs/adr").glob("[0-9]*.md")))
    text = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    match = re.search(r"ADR\s*(\d+)\s*本", text)
    if match is None:
        return
    if int(match.group(1)) != actual:
        errors.append(
            f"index.html: 「ADR {match.group(1)} 本」と書いてあるが docs/adr/ の実数は {actual} 本"
        )


def check_footer_readme_link(errors: list[str], html: str | None = None) -> None:
    """LP footer から README 本体へ 1 クリックで到達できることを検査する（Issue #403）。

    README → LP のリンクは成立しているのに LP → README が無い非対称を止める。
    footer 自体が見つからない場合も fail-closed で違反として報告する
    （footer の書き換えで検査が黙って素通りするのを防ぐ）。
    """
    text = html if html is not None else (SITE_DIR / "index.html").read_text(encoding="utf-8")
    match = FOOTER_RE.search(text)
    if match is None:
        errors.append("index.html: <footer> が見つからず README 直リンクを検査できない")
        return
    if not README_LINK_RE.search(match.group(0)):
        errors.append(
            "index.html: footer に README 本体（blob/main/README.md）への直リンクが無い"
        )


def self_test() -> int:
    failures: list[str] = []

    png = (
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", 1200, 630) + b"\x08\x06\x00\x00\x00"
    )
    if png_size(png) != (1200, 630):
        failures.append(f"png_size が誤り: {png_size(png)}")

    vp8x = (
        b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8X" + b"\x00" * 8
        + (1599).to_bytes(3, "little") + (1024).to_bytes(3, "little")
    )
    if webp_size(vp8x) != (1600, 1025):
        failures.append(f"webp_size(VP8X) が誤り: {webp_size(vp8x)}")

    parser = PageParser()
    parser.feed('<div id="a"><span id="a"></span>')
    if not parser.stack:
        failures.append("閉じ漏れを検出できていない")
    if len(parser.ids) != 2:
        failures.append("id を収集できていない")

    errors: list[str] = []
    balanced = PageParser()
    balanced.feed("<p>ok</p><br>")
    if balanced.stack or balanced.unbalanced:
        failures.append("正常な HTML を誤検知した")

    readme_href = "https://github.com/kai-kou/gem-hunter/blob/main/README.md"
    footer_cases = [
        # (説明, HTML, 期待する違反件数)
        ("footer 内に README 直リンクがある", f'<footer><a href="{readme_href}">README</a></footer>', 0),
        # 境界の外側: footer の外にだけあっても到達導線にならない（#750 の負ケース規律）
        ("footer の外にだけ README リンクがある", f'<a href="{readme_href}">README</a><footer><a href="#top">top</a></footer>', 1),
        # 近似だが別対象: docs ツリーへのリンクは README 本体ではない
        ("footer 内が docs リンクのみ", '<footer><a href="https://github.com/kai-kou/gem-hunter/tree/main/docs">docs</a></footer>', 1),
        ("footer 自体が無い", f'<div><a href="{readme_href}">README</a></div>', 1),
    ]
    for label, html, expected in footer_cases:
        found: list[str] = []
        check_footer_readme_link(found, html=html)
        if len(found) != expected:
            failures.append(
                f"check_footer_readme_link（{label}）: 違反 {len(found)} 件（期待 {expected} 件）"
            )

    # 本番の入口（main()）を経由した配線検査（#686）。
    # 検査関数を直接呼ぶだけでは main() から呼び出す 1 行が消えても緑のままになる。
    global SITE_DIR, PAGES
    original_site_dir, original_pages = SITE_DIR, PAGES
    footer_only = '<html><body><footer><ul><li>{link}</li></ul></footer></body></html>'
    try:
        with tempfile.TemporaryDirectory() as tmp:
            SITE_DIR = Path(tmp)
            PAGES = ["index.html"]
            wiring_cases = [
                ("README 直リンク無し", '<a href="#top">top</a>', 1),
                ("README 直リンク有り", f'<a href="{readme_href}">README</a>', 0),
            ]
            for label, link, expected_exit in wiring_cases:
                (SITE_DIR / "index.html").write_text(
                    footer_only.format(link=link), encoding="utf-8"
                )
                actual = main([])  # 本判定の入口を通す（--self-test を渡さない）
                if actual != expected_exit:
                    failures.append(
                        f"main() 経由の配線検査（{label}）: exit {actual}（期待 {expected_exit}）"
                    )
    finally:
        SITE_DIR, PAGES = original_site_dir, original_pages

    for image in sorted((SITE_DIR / "assets/img").glob("*")):
        if image_size(image) is None:
            failures.append(f"実ファイルのサイズを解析できない: {image.name}")

    if failures:
        for line in failures:
            print(f"[check_site] SELF-TEST FAIL: {line}")
        return 1
    print(f"[check_site] SELF-TEST PASS（{len(errors)} 件の想定エラー）")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--self-test" in args:
        return self_test()

    if not SITE_DIR.is_dir():
        print("[check_site] SKIP: site/ が存在しません")
        return 0

    errors: list[str] = []
    for page in PAGES:
        check_page(page, errors)
    check_repo_links(errors)
    check_adr_count(errors)
    check_footer_readme_link(errors)

    if errors:
        print("[check_site] FAIL:")
        for line in errors:
            print(f"  - {line}")
        return 1
    print("[check_site] OK（site/ の参照・寸法・アンカー・ADR 本数に違反なし）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
