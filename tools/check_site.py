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
  7. **index.html の** footer から README 本体への直リンクが存在すること（LP → README の導線）

使い方:
  python3 tools/check_site.py            # 検査（違反があれば exit 1）
  python3 tools/check_site.py --self-test  # 検査ロジック自体の自己テスト
"""

from __future__ import annotations

import contextlib
import io
import re
import struct
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
PAGES = ["index.html", "404.html"]
REPO_URL = "https://github.com/kai-kou/gem-hunter"
REPO_LINK_RE = re.compile(re.escape(REPO_URL) + r"/(?:blob|tree)/main/([^\"'\s)#]+)")
README_URL = f"{REPO_URL}/blob/main/README.md"
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


class FooterLinkParser(HTMLParser):
    """<footer> 配下の <a href> だけを集める。

    正規表現の部分一致では、コメントアウトされたリンク・地の文に書いた URL・
    別要素の属性値（title 等）を「リンクがある」と誤判定して fail-open になる。
    HTMLParser はコメントを handle_comment、地の文を handle_data へ回すため、
    ここで集まるのは実際にクリックできる href だけになる。
    footer が複数あるときは全ての footer を対象にする（最初の 1 個だけ見ると、
    カード等の入れ子 footer が増えた瞬間に誤検知でゲートが赤くなる）。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.seen_footer = False
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "footer":
            self.depth += 1
            self.seen_footer = True
            return
        if self.depth > 0 and tag == "a":
            for key, value in attrs:
                if key == "href" and value:
                    self.hrefs.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "footer" and self.depth > 0:
            self.depth -= 1


def check_footer_readme_link(
    errors: list[str], html: str | None = None, page: str = "index.html"
) -> None:
    """LP footer から README 本体へ 1 クリックで到達できることを検査する（Issue #403）。

    README → LP のリンクは成立しているのに LP → README が無い非対称を止める。
    footer 自体が見つからない場合も fail-closed で違反として報告する
    （footer の書き換えで検査が黙って素通りするのを防ぐ）。
    href は完全一致で判定する（前方一致だと README.md.bak / README.mdx のような
    別ファイルへのリンクを「README 本体への導線」と誤認する）。
    """
    text = html if html is not None else (SITE_DIR / page).read_text(encoding="utf-8")
    parser = FooterLinkParser()
    parser.feed(text)
    if not parser.seen_footer:
        errors.append(f"{page}: <footer> が見つからず README 直リンクを検査できない")
        return
    for href in parser.hrefs:
        if href == README_URL or href.startswith(f"{README_URL}#"):
            return
    errors.append(f"{page}: footer に README 本体（{README_URL}）への直リンクが無い")


def self_test() -> int:
    failures: list[str] = []
    # 実際に検証したケース数。手書き定数にはしない — 各検証点を必ずこのヘルパー経由で
    # 通すことで、ケースを足し引きすれば件数が構造的に追従する（数え漏れが起きない）。
    case_count = 0

    def assert_check(ok: bool, message: str) -> None:
        nonlocal case_count
        case_count += 1
        if not ok:
            failures.append(message)

    png = (
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", 1200, 630) + b"\x08\x06\x00\x00\x00"
    )
    assert_check(png_size(png) == (1200, 630), f"png_size が誤り: {png_size(png)}")

    vp8x = (
        b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8X" + b"\x00" * 8
        + (1599).to_bytes(3, "little") + (1024).to_bytes(3, "little")
    )
    assert_check(
        webp_size(vp8x) == (1600, 1025), f"webp_size(VP8X) が誤り: {webp_size(vp8x)}"
    )

    parser = PageParser()
    parser.feed('<div id="a"><span id="a"></span>')
    assert_check(bool(parser.stack), "閉じ漏れを検出できていない")
    assert_check(len(parser.ids) == 2, "id を収集できていない")

    balanced = PageParser()
    balanced.feed("<p>ok</p><br>")
    assert_check(
        not (balanced.stack or balanced.unbalanced), "正常な HTML を誤検知した"
    )

    readme_href = README_URL
    footer_cases = [
        # (説明, HTML, 期待する違反件数)
        ("footer 内に README 直リンクがある", f'<footer><a href="{readme_href}">README</a></footer>', 0),
        ("アンカー付きの README リンク", f'<footer><a href="{readme_href}#使い方">README</a></footer>', 0),
        # footer が複数ある構造でも、いずれかに導線があれば到達できる
        ("2 つ目の footer にリンクがある", f'<footer><a href="#top">top</a></footer><footer><a href="{readme_href}">README</a></footer>', 0),
        ("大文字タグの FOOTER", f'<FOOTER><A HREF="{readme_href}">README</A></FOOTER>', 0),
        # 境界の外側: footer の外にだけあっても到達導線にならない（#750 の負ケース規律）
        ("footer の外にだけ README リンクがある", f'<a href="{readme_href}">README</a><footer><a href="#top">top</a></footer>', 1),
        # 近似だが別対象: 同じ blob/main 配下でも README 本体ではない
        ("footer 内が docs ツリーリンクのみ", f'<footer><a href="{REPO_URL}/tree/main/docs">docs</a></footer>', 1),
        ("footer 内が LICENSE リンクのみ", f'<footer><a href="{REPO_URL}/blob/main/LICENSE">LICENSE</a></footer>', 1),
        # 前方一致だと素通りする派生パス（README.md で終わらない）
        ("README.md.bak へのリンクのみ", f'<footer><a href="{readme_href}.bak">古い README</a></footer>', 1),
        ("README.mdx へのリンクのみ", f'<footer><a href="{REPO_URL}/blob/main/README.mdx">x</a></footer>', 1),
        # クリックできない形（部分一致だと fail-open になる経路）
        ("リンクがコメントアウトされている", f'<footer><!-- <a href="{readme_href}">README</a> --></footer>', 1),
        ("地の文に URL があるだけ", f'<footer><p>README は {readme_href} にあります</p></footer>', 1),
        ("別要素の属性値に URL があるだけ", f'<footer><a href="#top" title="{readme_href}">top</a></footer>', 1),
        ("footer 自体が無い", f'<div><a href="{readme_href}">README</a></div>', 1),
    ]
    for label, html, expected in footer_cases:
        found: list[str] = []
        check_footer_readme_link(found, html=html)
        assert_check(
            len(found) == expected,
            f"check_footer_readme_link（{label}）: 違反 {len(found)} 件（期待 {expected} 件）",
        )

    # 本番の入口（main()）を経由した配線検査（#686）。
    # 検査関数を直接呼ぶだけでは main() から呼び出す 1 行が消えても緑のままになる。
    global SITE_DIR, PAGES
    original_site_dir, original_pages = SITE_DIR, PAGES
    footer_only = '<html><body><footer><ul><li>{link}</li></ul></footer></body></html>'
    marker = "footer に README 本体"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            SITE_DIR = Path(tmp)
            PAGES = ["index.html"]
            wiring_cases = [
                # (説明, footer に置くリンク, 期待 exit, 期待するこの検査由来の違反件数)
                ("README 直リンク無し", '<a href="#top">top</a>', 1, 1),
                ("README 直リンク有り", f'<a href="{readme_href}">README</a>', 0, 0),
            ]
            for label, link, expected_exit, expected_hits in wiring_cases:
                (SITE_DIR / "index.html").write_text(
                    footer_only.format(link=link), encoding="utf-8"
                )
                # 意図的な負ケースの FAIL 出力で self-test のログを汚さないよう捕捉する。
                # 捕捉した文字列は「exit 1 の原因が本当に footer 検査か」の突合にも使う
                # （exit code だけを見ると、他の検査が出した違反と区別できない）。
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    actual = main([])  # 本判定の入口を通す（--self-test を渡さない）
                output = buffer.getvalue()
                hits = output.count(marker)
                assert_check(
                    actual == expected_exit,
                    f"main() 経由の配線検査（{label}）: exit {actual}（期待 {expected_exit}）",
                )
                assert_check(
                    hits == expected_hits,
                    f"main() 経由の配線検査（{label}）: footer 検査由来の違反 {hits} 件"
                    f"（期待 {expected_hits} 件）",
                )
    finally:
        SITE_DIR, PAGES = original_site_dir, original_pages

    for image in sorted((SITE_DIR / "assets/img").glob("*")):
        assert_check(
            image_size(image) is not None,
            f"実ファイルのサイズを解析できない: {image.name}",
        )

    if failures:
        for line in failures:
            print(f"[check_site] SELF-TEST FAIL: {line}")
        return 1
    print(f"[check_site] SELF-TEST PASS（{case_count} 件の検証ケース）")
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
    print("[check_site] OK（site/ の参照・寸法・アンカー・ADR 本数・README 導線に違反なし）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
