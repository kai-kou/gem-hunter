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
  8. <img srcset> の記述子・実ファイル・sizes の整合（Issue #998）。REQUIRE_SRCSET_BASENAMES に
     載る画像は srcset が必須で、各候補は実ファイルの実寸・重複の無さ・sizes との整合を検査する

使い方:
  python3 tools/check_site.py            # 検査（違反があれば exit 1）
  python3 tools/check_site.py --self-test  # 検査ロジック自体の自己テスト
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import io
import re
import struct
import sys
import tempfile
import textwrap
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

# srcset が必須の画像（basename ベース）。Issue #998: PC 解像度で撮った画像をモバイル幅にも
# そのまま配信していた 3 画像（shot-search / shot-digest / shot-gems）を対象にする。
# shot-mobile.webp は対象外（理由は main() 呼び出し元のコメントではなく、Issue #998 の
# 完了条件チェックで実測して判断: 表示先 .phone の実効幅は最大 228px(padding込み) で、
# 現行ファイルは 640px 幅 = 約 2.8x 相当をすでにカバーしており、追加の派生を作っても
# 転送削減効果が薄い一方、それ以上縮小すると 3x 相当の画質を割り込むリスクがある）。
# 将来ここへ追加された画像は同じ規約に従う（新規の <img> でも自動的に検査対象へ入る）。
REQUIRE_SRCSET_BASENAMES = {"shot-search.webp", "shot-digest.webp", "shot-gems.webp"}
# srcset の各候補は `URL 幅w` の形式のみ許可する（density descriptor `x` は本サイトでは未使用）。
SRCSET_CANDIDATE_RE = re.compile(r"^(\S+)\s+(\d+)w$")

# sizes の値をパースする際に横断する代表ビューポート幅（CSS px）。フルカバレッジではなく、
# 「メディア条件の閾値」と「割り当てサイズ値」を混同しないための実測点として使う
# （Issue #998 CRITICAL 2）。モバイル最小級 / モバイル標準 / デスクトップ小 / デスクトップ大。
SIZES_REPRESENTATIVE_VIEWPORTS = (320, 390, 1280, 1920)
# sizes の 1 候補（カンマ区切りの 1 要素）は `(メディア条件)? サイズ値` の形。
SIZES_ENTRY_RE = re.compile(r"^\(([^)]*)\)\s*(.+)$")
# メディア条件内の `min-width: Npx` / `max-width: Npx` を抽出する（本 LP は単純な単一条件のみ使用）。
SIZES_MEDIA_COND_RE = re.compile(r"(min-width|max-width)\s*:\s*(\d+)px")
_SIZES_PX_VALUE_RE = re.compile(r"^(\d+)px$")
_SIZES_VW_VALUE_RE = re.compile(r"^(\d+)vw$")
_SIZES_CALC_VW_PX_RE = re.compile(r"^calc\(\s*(\d+)vw\s*([+-])\s*(\d+)px\s*\)$")


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


def fake_png_bytes(width: int, height: int) -> bytes:
    """self-test 用の最小 PNG バイト列を作る（IHDR チャンクの中身だけが正しければ足りる）。

    png_size() はシグネチャ + IHDR の width/height しか読まないため、圧縮データ・CRC・IEND を
    含む完全な PNG である必要が無い。self_test() 内の PNG デコード検証と srcset の候補ファイル
    フィクスチャの両方から呼ばれる（同じ最小 PNG を 2 箇所で手書きして desync するのを防ぐ）。
    """
    return (
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    )


def _resolve_local_asset(ref: str) -> Path:
    """`src` / `href` / srcset 候補の URL をリポジトリ内パスへ解決する。

    404.html はサブパス付き絶対パス（`gem-hunter/...`）で参照するため接頭辞を剥がす。
    check_page() の src / href 解決と全く同じ規則にする（別々に実装すると片方だけ直す desync
    が起きるため、両方から本関数を呼ぶ形にしてある）。
    """
    local = ref.lstrip("/")
    if local.startswith("gem-hunter/"):
        local = local[len("gem-hunter/") :]
    return SITE_DIR / local


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
        candidate = _resolve_local_asset(ref).resolve()
        if not candidate.exists():
            errors.append(f"{page}:{line} 参照先 {ref} が存在しない")

    for attr, line in parser.images:
        src = attr.get("src", "")
        if src.startswith(("http://", "https://", "data:")):
            continue
        candidate = _resolve_local_asset(src)
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

    check_img_srcset(page, parser.images, errors)
    return parser


def _media_condition_matches(condition: str, viewport: int) -> bool | None:
    """sizes の候補に付くメディア条件（例: "min-width: 1120px"）が指定ビューポートで真かどうか。

    本 LP は `min-width` / `max-width` の単純な数値条件のみを使う（複数条件が `and` で
    連結されていれば全条件が真のときだけ真とする）。条件から px 形式の判定材料を
    1 つも取り出せない場合は「解釈できない」ことを示す None を返す（呼び出し側が
    fail-closed へ倒す・Issue #998 CRITICAL 2）。
    """
    matches = SIZES_MEDIA_COND_RE.findall(condition)
    if not matches:
        return None
    ok = True
    for kind, value_str in matches:
        value = int(value_str)
        if kind == "min-width" and viewport < value:
            ok = False
        if kind == "max-width" and viewport > value:
            ok = False
    return ok


def _eval_sizes_value(value: str, viewport: int) -> int | None:
    """sizes の 1 候補の「サイズ値」部分（メディア条件を除いた側）を指定ビューポートで px 換算する。

    対応する記法は `Npx`（固定）/ `Nvw`（ビューポート比）/ `calc(Nvw ± Mpx)`（本 LP の実使用形）
    の 3 つ。それ以外（%・他の calc 式・env() 等）は未対応として None を返す（判定不能を
    「要求なし」と誤読しない・fail-closed）。
    """
    value = value.strip()
    match = _SIZES_PX_VALUE_RE.match(value)
    if match:
        return int(match.group(1))
    match = _SIZES_VW_VALUE_RE.match(value)
    if match:
        return round(int(match.group(1)) / 100 * viewport)
    match = _SIZES_CALC_VW_PX_RE.match(value)
    if match:
        vw_part = int(match.group(1)) / 100 * viewport
        sign = 1 if match.group(2) == "+" else -1
        px_part = int(match.group(3))
        return round(vw_part + sign * px_part)
    return None


def _sizes_required_px(sizes_value: str) -> tuple[int | None, bool]:
    """sizes 属性値から「実際にどの幅が要求されうるか」の最大値を計算する（Issue #998 CRITICAL 2）。

    旧実装（`SIZES_PX_RE = re.compile(r"(\\d+)px")`）は sizes 文字列全体から px リテラルを
    無差別に拾っており、次の 2 つの見逃し方をしていた:
      - vw / calc() だけの sizes（px リテラルが 1 つも無い）→ required_px が空になり、
        カバレッジ判定そのものが丸ごとスキップされていた（`sizes="100vw"` 等）
      - メディア条件の閾値（`(min-width: 1400px)` の 1400）と実際の割り当てサイズ値
        （その後に続く `1080px` の 1080）を区別できず、大きい方を拾って
        「デスクトップでは実際より大きい幅が要る」と過大／過小に誤判定していた

    本実装はカンマ区切りの各候補を `(メディア条件)? サイズ値` にパースし、代表ビューポート
    （SIZES_REPRESENTATIVE_VIEWPORTS）ごとに CSS の sizes 評価順序（先頭から見て最初に
    真になった条件、条件なしは常に真＝フォールバック）で「そのビューポートで選ばれる候補」を
    決定してから、そのサイズ値だけを _eval_sizes_value() で px 換算する。メディア条件の
    閾値自体は px 換算の対象に渡らないため、閾値をサイズ値と取り違える経路が構造的に無い。

    戻り値: (代表ビューポートを横断した必要 px の最大値 or None, 判定不能フラグ)。
    メディア条件・サイズ値のどちらか一方でも解釈できない箇所があれば判定不能（True）とし、
    呼び出し側は「要求なし」ではなく fail-closed のエラーとして扱う。
    """
    entries: list[tuple[str | None, str]] = []
    for raw in sizes_value.split(","):
        entry = raw.strip()
        if not entry:
            continue
        match = SIZES_ENTRY_RE.match(entry)
        if match:
            entries.append((match.group(1), match.group(2).strip()))
        else:
            entries.append((None, entry))
    if not entries:
        return None, True

    required: int | None = None
    for viewport in SIZES_REPRESENTATIVE_VIEWPORTS:
        chosen_value: str | None = None
        for condition, value in entries:
            if condition is None:
                chosen_value = value
                break
            matched = _media_condition_matches(condition, viewport)
            if matched is None:
                return None, True
            if matched:
                chosen_value = value
                break
        if chosen_value is None:
            # 条件付き候補しか無く、どのビューポートでも一致せずフォールバックも無い
            # （sizes の書き方として異例）。安全側で最後の候補を使う。
            chosen_value = entries[-1][1]
        px = _eval_sizes_value(chosen_value, viewport)
        if px is None:
            return None, True
        if required is None or px > required:
            required = px
    return required, False


# check_img_srcset() が「REQUIRE_SRCSET_BASENAMES に載る画像を実際に見た」basename を溜める。
# main() が全ページ処理後に空集合差分を取り、「対象の <img> ごと消えて検査が 0 件のまま
# 素通りする」（check-tool-design-rules.md §2 の fail-open）を検知する。
REQUIRED_SRCSET_SEEN: set[str] = set()


def check_img_srcset(
    page: str, images: list[tuple[dict[str, str], int]], errors: list[str]
) -> None:
    """<img srcset> の記述子・実ファイル・sizes の整合を検査する（Issue #998）。

    見逃しうる経路（1 つずつ塞いである）:
      - srcset の無い <img> をそのまま素通りさせる
        → REQUIRE_SRCSET_BASENAMES に載る画像だけは srcset 必須にして塞ぐ
      - srcset="" のような空文字列を「候補 0 件だから検査対象なし」と黙って合格にする
        → 明示的にエラーへ倒す（continue で握り潰さない）
      - カンマ区切りの各候補が `URL 幅w` の形でないとき、正規表現の非マッチをそのまま
        読み飛ばす → 非マッチも 1 件のエラーとして数える
      - 派生ファイルの不在を検査していない → 各候補の実在をチェック
      - 記述子の幅（800w）のパース失敗・実ファイルとの食い違いを握り潰す
        → int() 変換に失敗する形は正規表現の時点で弾かれ、変換できても実寸と突き合わせる
      - 同じ幅記述子が重複している（各候補は妥当だが集合として無効・#896）→ エラー。
        ただし重複エラーを出した回は「有効な候補が実質 1 件」エラーへ二重計上しない
        （valid_candidate_count は重複判定の前に加算するため・#998 WARNING 4）
      - 候補が実質 1 件しかない（srcset を名乗る意味が無い・#896）→ エラー
      - srcset があるのに sizes が無い（仕様上必須の組み合わせ）→ エラー
      - sizes が要求する px 幅を、どの候補もカバーできていない → エラー。
        sizes の px 抽出はメディア条件と vw / calc() を区別して評価する
        （_sizes_required_px()・#998 CRITICAL 2。旧実装は sizes 文字列全体から
        px リテラルを無差別に拾い、vw / calc() だけの sizes を素通りさせたり
        メディア条件の閾値をサイズ値と取り違えたりしていた）
      - **対象の <img> がページから消えると検査対象 0 件のまま合格する経路**
        → REQUIRED_SRCSET_SEEN に記録し、main() が全ページ走査後に必須集合との差分を確認する
    """
    for attr, line in images:
        src = attr.get("src", "")
        src_basename = src.rsplit("/", 1)[-1]
        srcset = attr.get("srcset")
        requires_srcset = src_basename in REQUIRE_SRCSET_BASENAMES

        if requires_srcset:
            REQUIRED_SRCSET_SEEN.add(src_basename)
            if srcset is None or not srcset.strip():
                errors.append(
                    f'{page}:{line} <img src="{src}"> は srcset が必須（Issue #998）だが無い'
                )
                continue

        if srcset is None:
            continue  # srcset 任意の画像（必須集合の対象外）はここで検査終了
        # srcset="" / 空白のみの場合は明示の早期エラーを置かない（重複ガードになるため）。
        # 分割後の各トークンが空になり、下のループ内 “空の候補” チェックが必ず捕まえる
        # （split(",") は空文字列でも要素 1 件を返すため、この経路は迂回できない）。

        sizes_value = attr.get("sizes", "")
        if not sizes_value.strip():
            errors.append(f'{page}:{line} <img src="{src}"> は srcset があるのに sizes が無い')

        widths_seen: dict[int, str] = {}
        # 重複でも個別には妥当な候補として数える（#998 WARNING 4: 重複エラーを出した回に
        # 「候補が実質 1 件」エラーを二重計上しないため、unique 幅の件数とは別に持つ）。
        valid_candidate_count = 0
        for raw in srcset.split(","):
            token = raw.strip()
            if not token:
                errors.append(f'{page}:{line} <img src="{src}"> の srcset に空の候補がある')
                continue
            match = SRCSET_CANDIDATE_RE.match(token)
            if match is None:
                errors.append(
                    f'{page}:{line} srcset の候補 "{token}" が `URL 幅w` の形式でない'
                )
                continue
            url, width_str = match.group(1), int(match.group(2))
            candidate = _resolve_local_asset(url)
            if not candidate.exists():
                errors.append(f"{page}:{line} srcset の候補 {url} が存在しない")
                continue
            actual = image_size(candidate)
            if actual is None:
                errors.append(f"{page}:{line} srcset の候補 {url} の画像サイズを解析できなかった")
                continue
            if actual[0] != width_str:
                errors.append(
                    f"{page}:{line} srcset の候補 {url} は {width_str}w と書かれているが"
                    f" 実寸幅は {actual[0]}px"
                )
                continue
            valid_candidate_count += 1
            if width_str in widths_seen:
                errors.append(
                    f"{page}:{line} srcset に幅記述子 {width_str}w が重複している"
                    f"（{widths_seen[width_str]} と {url}）"
                )
                continue
            widths_seen[width_str] = url

        candidate_widths = list(widths_seen)
        if valid_candidate_count and valid_candidate_count < 2:
            errors.append(
                f"{page}:{line} srcset の有効な候補が {valid_candidate_count} 件しかない"
                "（複数候補が無いと出し分けの意味が無い）"
            )

        if candidate_widths and sizes_value.strip():
            max_required, unparseable = _sizes_required_px(sizes_value)
            if unparseable:
                errors.append(
                    f'{page}:{line} <img src="{src}"> の sizes "{sizes_value}" を解釈できない'
                    "箇所がある（px / vw / calc(Nvw ± Mpx) 以外の記法は未対応・判定不能）"
                )
            elif max_required is not None:
                max_candidate = max(candidate_widths)
                if max_candidate < max_required:
                    errors.append(
                        f"{page}:{line} sizes が {max_required}px を要求しているが"
                        f" srcset の最大候補は {max_candidate}w しかない"
                    )


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
    global SITE_DIR, PAGES, REQUIRE_SRCSET_BASENAMES
    failures: list[str] = []
    # 実際に検証したケース数。手書き定数にはしない — 各検証点を必ずこのヘルパー経由で
    # 通すことで、ケースを足し引きすれば件数が構造的に追従する（数え漏れが起きない）。
    case_count = 0

    def assert_check(ok: bool, message: str) -> None:
        nonlocal case_count
        case_count += 1
        if not ok:
            failures.append(message)

    # メタ検証 1: assert_check がケース数を実際に加算していることを検証する
    # （将来 `case_count += 1` が消えても、他の assert_check 呼び出しは緑のまま通り続けてしまう）。
    _before = case_count
    assert_check(True, "メタ検証用のダミー（常に真）")
    assert_check(
        case_count == _before + 1,
        f"assert_check がケース数を加算していない: {_before} → {case_count}",
    )

    png = fake_png_bytes(1200, 630)
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

    required_basename = sorted(REQUIRE_SRCSET_BASENAMES)[0]
    required_stem = required_basename.rsplit(".", 1)[0]
    required_derivative = f"{required_stem}-800w.webp"
    # 以降の wiring 検証（main() 経由）は「必須集合との突き合わせ」という機構そのものを
    # 検証する目的で、特定の basename 1 件だけを対象に置く。REQUIRE_SRCSET_BASENAMES の
    # 実際の登録件数（本番は 3 件）に依存させると、対象を増減させるたびに無関係なこの
    # テストが壊れる（実測: #998 CRITICAL 1 で 1→3 件に増やした際、他 2 件が「消えた」と
    # 誤検知して赤くなった）。
    original_require_srcset_basenames = REQUIRE_SRCSET_BASENAMES
    REQUIRE_SRCSET_BASENAMES = {required_basename}

    # check_img_srcset() の自己テスト（Issue #998）。check_page() 経由で呼ぶ
    # （check_img_srcset を直接叩くだけでは check_page() 側の呼び出し 1 行が消えても
    # 緑のままになる・#686 と同じ理由）。#896: 各候補は個別に妥当でも集合として
    # 無効な負ケース（幅記述子の重複・候補が実質 1 件）を最低 1 件ずつ含める。
    original_site_dir_srcset, original_pages_srcset = SITE_DIR, PAGES
    try:
        with tempfile.TemporaryDirectory() as tmp:
            SITE_DIR = Path(tmp)
            PAGES = ["index.html"]
            img_dir = SITE_DIR / "assets/img"
            img_dir.mkdir(parents=True)
            fixtures = {
                "w400.png": (400, 250),
                "w800.png": (800, 500),
                "w1600.png": (1600, 1000),
                "wrong-800.png": (750, 469),
                "dup-a.png": (800, 500),
                "dup-b.png": (800, 500),
                required_basename: (1600, 1025),
                required_derivative: (800, 513),
            }
            for name, (fw, fh) in fixtures.items():
                (img_dir / name).write_bytes(fake_png_bytes(fw, fh))
            # 実在はするが PNG/WebP どちらのマジックバイトとも一致しない壊れたファイル
            # （image_size() が None を返す経路・サイズ解析失敗を握り潰さないことの検証用）。
            (img_dir / "corrupt.png").write_bytes(b"not-an-image-at-all")

            base_sizes = "(min-width: 1120px) 1080px, calc(100vw - 40px)"
            srcset_cases = [
                # (説明, <img> の属性文字列（src/width/height/srcset/sizes）, 期待する違反件数)
                (
                    "妥当な 2 候補（違反なし）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w800.png 800w, ./assets/img/w1600.png 1600w"'
                    f' sizes="{base_sizes}"',
                    0,
                ),
                (
                    "記述子が無い候補（正規表現の非マッチを握り潰さない）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/w800.png,'
                    f' ./assets/img/w1600.png 1600w" sizes="{base_sizes}"',
                    1,
                ),
                (
                    "候補ファイルが存在しない（派生ファイルの不在）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/missing.png 800w,'
                    f' ./assets/img/w1600.png 1600w" sizes="{base_sizes}"',
                    1,
                ),
                (
                    "記述子と実寸幅が食い違う",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/wrong-800.png 800w,'
                    f' ./assets/img/w1600.png 1600w" sizes="{base_sizes}"',
                    1,
                ),
                (
                    "候補ファイルは実在するがサイズを解析できない（壊れた画像）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/corrupt.png 800w,'
                    f' ./assets/img/w1600.png 1600w" sizes="{base_sizes}"',
                    1,
                ),
                (
                    "同じ幅記述子が重複（各候補は個別に妥当・#896）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/dup-a.png 800w,'
                    f' ./assets/img/dup-b.png 800w, ./assets/img/w1600.png 1600w"'
                    f' sizes="{base_sizes}"',
                    1,
                ),
                (
                    "候補が実質 1 件しかない（#896）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    f' srcset="./assets/img/w1600.png 1600w" sizes="{base_sizes}"',
                    1,
                ),
                (
                    "srcset があるのに sizes が無い",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/w1600.png 1600w"',
                    1,
                ),
                (
                    "srcset が空文字列（候補 0 件だから合格、にしない）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="" sizes="100vw"',
                    1,
                ),
                (
                    "sizes が要求する px を誰もカバーしていない",
                    'src="./assets/img/w800.png" width="800" height="500"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/w800.png 800w"'
                    ' sizes="1600px"',
                    1,
                ),
                (
                    f"必須画像（{required_basename}）に srcset が無い",
                    f'src="./assets/img/{required_basename}" width="1600" height="1025"',
                    1,
                ),
                (
                    f"必須画像（{required_basename}）が妥当な srcset を持つ",
                    f'src="./assets/img/{required_basename}" width="1600" height="1025"'
                    f' srcset="./assets/img/{required_derivative} 800w,'
                    f' ./assets/img/{required_basename} 1600w" sizes="{base_sizes}"',
                    0,
                ),
                # #998 CRITICAL 3: srcset を一切持たない通常の <img>（必須集合の対象外）は
                # 素通りしてよい負ケース。check_img_srcset() の `if srcset is None: continue`
                # を通る唯一のケースで、これが無いと変異（`if False: continue`）で
                # AttributeError クラッシュしても self-test 全体は緑のままになる。
                (
                    "srcset を持たない通常の <img>（負ケース・#998 CRITICAL 3）",
                    'src="./assets/img/w1600.png" width="1600" height="1000"',
                    0,
                ),
                # #998 CRITICAL 2 その 1: sizes が vw のみ（px リテラルが無い）でも
                # 旧実装（SIZES_PX_RE）はカバレッジ判定を丸ごとスキップしていた（fail-open）。
                (
                    "sizes が 100vw（px リテラル無し）でも必要幅を計算する",
                    'src="./assets/img/w800.png" width="800" height="500"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/w800.png 800w"'
                    ' sizes="100vw"',
                    1,
                ),
                # #998 CRITICAL 2 その 2: メディア条件の閾値（1400）と割り当てサイズ値（300 / 900）を
                # 混同しない。2 つの分岐にわざと異なるサイズ値を与える（両分岐が同じ値だと
                # 「条件を無視して常に先頭分岐を選ぶ」変異を偶然素通りさせてしまうため）。
                # 正しい実装では 1400px 未満（代表ビューポート 320/390/1280 の 3 点）は
                # フォールバックの 900px が採用され、候補最大 800w では不足＝1 件が正しい。
                (
                    "sizes のメディア条件の閾値をサイズ値と取り違えない",
                    'src="./assets/img/w800.png" width="800" height="500"'
                    ' srcset="./assets/img/w400.png 400w, ./assets/img/w800.png 800w"'
                    ' sizes="(min-width: 1400px) 300px, 900px"',
                    1,
                ),
                # #998 CRITICAL 2 その 3: calc() の減算オフセットのみの sizes。旧実装は
                # "calc(100vw - 40px)" から "40px" だけを拾い required=40 という明らかな
                # 過小評価で合格させていた（実際は大画面で ~1880px 相当を要求する）。
                (
                    "sizes が calc(Nvw - Mpx) のみでも実効幅を計算する",
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/w800.png 800w, ./assets/img/w1600.png 1600w"'
                    ' sizes="calc(100vw - 40px)"',
                    1,
                ),
                # #998 WARNING 4: ちょうど 2 候補で両方が同じ幅記述子のとき、「重複」エラーと
                # 「有効な候補が実質 1 件」エラーが二重に出ないことを確認する回帰ケース。
                (
                    "同一幅記述子ちょうど 2 候補（二重エラーの回帰・#998 WARNING 4）",
                    # sizes は候補の最大幅 800px ちょうどに合わせ、カバレッジ判定側の違反を
                    # 誘発しないようにする（この回帰ケースの主眼は「重複」検出の二重計上）。
                    'src="./assets/img/w1600.png" width="1600" height="1000"'
                    ' srcset="./assets/img/dup-a.png 800w, ./assets/img/dup-b.png 800w"'
                    ' sizes="800px"',
                    1,
                ),
            ]
            # #998 CRITICAL 2 の 2 ケース（① 100vw / ③ calc(Nvw-Mpx)）は「違反件数が期待どおり」
            # だけでは変異を見逃す（実測: vw 評価を潰す変異でも、コード側が正しい
            # 「px を要求しているが〜」ではなく「解釈できない」エラーへフォールバックし、
            # 件数だけは偶然 1 件のまま一致してしまった）。件数に加えてメッセージ文言も
            # 検証し、意図した理由で違反しているかを区別する。
            sizes_message_must_contain = {
                "sizes が 100vw（px リテラル無し）でも必要幅を計算する": "px を要求しているが",
                "sizes のメディア条件の閾値をサイズ値と取り違えない": "900px を要求しているが",
                "sizes が calc(Nvw - Mpx) のみでも実効幅を計算する": "px を要求しているが",
            }
            for label, img_attrs, expected in srcset_cases:
                (SITE_DIR / "index.html").write_text(
                    f"<html><body><img {img_attrs}></body></html>", encoding="utf-8"
                )
                found: list[str] = []
                check_page("index.html", found)
                assert_check(
                    len(found) == expected,
                    f"check_img_srcset（{label}）: 違反 {len(found)} 件（期待 {expected} 件）"
                    f"（内訳: {found}）",
                )
                must_contain = sizes_message_must_contain.get(label)
                if must_contain is not None:
                    assert_check(
                        any(must_contain in message for message in found),
                        f"check_img_srcset（{label}）: 文言 '{must_contain}' を含む違反が無い"
                        f"（『解釈できない』への誤フォールバック等を疑う。内訳: {found}）",
                    )
    finally:
        SITE_DIR, PAGES = original_site_dir_srcset, original_pages_srcset

    # main() の対象 0 件フェイルクローズ（check-tool-design-rules.md §2）の配線検査。
    # 「必須画像の <img> が全ページのどこにも見つからない」は check_img_srcset() を
    # 単体で呼ぶだけでは検知できない（check_page() 1 回のスコープ内に閉じた検査のため）。
    # main() が全ページ走査後に REQUIRED_SRCSET_SEEN と突き合わせる 1 行が消えても
    # 緑のままにならないことを、本番の入口（main()）を経由して確認する。
    original_site_dir_req, original_pages_req = SITE_DIR, PAGES
    try:
        with tempfile.TemporaryDirectory() as tmp:
            SITE_DIR = Path(tmp)
            PAGES = ["index.html"]
            img_dir = SITE_DIR / "assets/img"
            img_dir.mkdir(parents=True)
            (img_dir / required_basename).write_bytes(fake_png_bytes(1600, 1025))
            (img_dir / required_derivative).write_bytes(fake_png_bytes(800, 513))
            footer_with_readme = f'<footer><a href="{readme_href}">README</a></footer>'
            required_missing_marker = "全ページのどこにも見つからない"
            required_present_img = (
                f'<img src="./assets/img/{required_basename}" width="1600" height="1025"'
                f' srcset="./assets/img/{required_derivative} 800w,'
                f' ./assets/img/{required_basename} 1600w"'
                ' sizes="(min-width: 1120px) 1080px, calc(100vw - 40px)">'
            )
            required_wiring_cases = [
                # (説明, <body> の中身, 期待 exit, 期待するこの検査由来の違反件数)
                ("必須画像の <img> が全ページから消えている", footer_with_readme, 1, 1),
                ("必須画像の <img> が存在する", required_present_img + footer_with_readme, 0, 0),
            ]
            for label, body, expected_exit, expected_hits in required_wiring_cases:
                (SITE_DIR / "index.html").write_text(
                    f"<html><body>{body}</body></html>", encoding="utf-8"
                )
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    actual = main([])
                output = buffer.getvalue()
                hits = output.count(required_missing_marker)
                assert_check(
                    actual == expected_exit,
                    f"main() 経由の配線検査（{label}）: exit {actual}（期待 {expected_exit}）",
                )
                assert_check(
                    hits == expected_hits,
                    f"main() 経由の配線検査（{label}）: 必須 srcset 欠落由来の違反 {hits} 件"
                    f"（期待 {expected_hits} 件）",
                )
    finally:
        SITE_DIR, PAGES = original_site_dir_req, original_pages_req

    # 本番の入口（main()）を経由した配線検査（#686）。
    # 検査関数を直接呼ぶだけでは main() から呼び出す 1 行が消えても緑のままになる。
    original_site_dir, original_pages = SITE_DIR, PAGES
    # この wiring 検証は footer 検査が主眼だが、main() は check_img_srcset() の
    # REQUIRED_SRCSET_SEEN 突合も同時に走らせる。srcset を検証しないダミー HTML のままだと
    # footer とは無関係な理由で常に exit 1 になり、下の expected_exit=0 ケースが壊れる。
    # そのため妥当な srcset 付き <img> を固定で埋め込み、srcset 起因の違反を 0 件に保つ
    # （footer 検査だけを分離して見る、という本テストの目的を変えない）。
    required_img = (
        f'<img src="./assets/img/{required_basename}" width="1600" height="1025"'
        f' srcset="./assets/img/{required_derivative} 800w,'
        f' ./assets/img/{required_basename} 1600w"'
        ' sizes="(min-width: 1120px) 1080px, calc(100vw - 40px)">'
    )
    footer_only = (
        "<html><body>" + required_img + "<footer><ul><li>{link}</li></ul></footer></body></html>"
    )
    marker = "footer に README 本体"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            SITE_DIR = Path(tmp)
            PAGES = ["index.html"]
            img_dir = SITE_DIR / "assets/img"
            img_dir.mkdir(parents=True, exist_ok=True)
            (img_dir / required_basename).write_bytes(fake_png_bytes(1600, 1025))
            (img_dir / required_derivative).write_bytes(fake_png_bytes(800, 513))
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
        REQUIRE_SRCSET_BASENAMES = original_require_srcset_basenames

    for image in sorted((SITE_DIR / "assets/img").glob("*")):
        assert_check(
            image_size(image) is not None,
            f"実ファイルのサイズを解析できない: {image.name}",
        )

    # メタ検証 2: self_test() 自身のソースを静的解析し、`assert_check` の定義の外で
    # 生の `failures.append(...)` が呼ばれていないことを検証する（#474: assert_check を
    # 経由しない直接 append は case_count に反映されず、機械検知できないまま緑になる）。
    source = textwrap.dedent(inspect.getsource(self_test))
    tree = ast.parse(source)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)

    def _is_failures_append(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "failures"
        )

    assert_check_append_lines: set[int] = set()
    for node in ast.walk(func_def):
        if isinstance(node, ast.FunctionDef) and node.name == "assert_check":
            assert_check_append_lines = {
                inner.lineno for inner in ast.walk(node) if _is_failures_append(inner)
            }
            break

    stray_append_lines = sorted(
        {
            node.lineno
            for node in ast.walk(func_def)
            if _is_failures_append(node) and node.lineno not in assert_check_append_lines
        }
    )
    assert_check(
        not stray_append_lines,
        "self_test() に assert_check を経由しない failures.append(...) がある"
        f"（行: {stray_append_lines}）",
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
    REQUIRED_SRCSET_SEEN.clear()
    for page in PAGES:
        check_page(page, errors)
    check_repo_links(errors)
    check_adr_count(errors)
    check_footer_readme_link(errors)

    # 対象の <img> ごと消えると check_img_srcset() は検査対象 0 件のまま合格してしまう
    # （check-tool-design-rules.md §2 の fail-open）。全ページ走査後に必須集合との差分を見る。
    missing = sorted(REQUIRE_SRCSET_BASENAMES - REQUIRED_SRCSET_SEEN)
    if missing:
        errors.append(
            f"srcset が必須の画像が全ページのどこにも見つからない（<img> ごと消えた？）: {missing}"
        )

    if errors:
        print("[check_site] FAIL:")
        for line in errors:
            print(f"  - {line}")
        return 1
    print("[check_site] OK（site/ の参照・寸法・アンカー・ADR 本数・README 導線・srcset に違反なし）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
