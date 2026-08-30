#!/usr/bin/env python3
"""check_github_body_markdown.py

GitHub の Issue / PR 本文として送信される Markdown のうち、**送信経路の中間レイヤーが
本文を書き換えて壊す書式** を静的に検出する（Issue #27）。

## 何を防ぐか（実測・2026-08-30）

Issue #27 で報告された「送信していないバッククォートが本文に挿入される」事象を、
本文をファイルから読み込んで `urllib` で GitHub API へ直接 POST する経路で再現し、
発生条件を特定した。実測の要点:

  - 送信ペイロードのバッククォートは 0 個、保存された本文は 4 個（`IDENTICAL: False`）
  - 同じ応答で **送信していない Claude Code の帰属フッターも付与されていた**
    → 本文を書き換える中間レイヤーが送信経路に実在する（送信側スクリプトの不具合ではない）
  - 挿入は常に 1 組（開き `` ` `` と閉じ `` ` ``）で、行内リンクの `](` 直後に開き、
    後続の日本語文の途中に閉じが入る。結果としてリンクが解決しなくなる

発生した / しなかったケース（実測）:

  | # | 行内リンクの URL          | `)` の直後  | 結果     |
  |---|---------------------------|-------------|----------|
  | 1 | `....md#日本語アンカー`   | CJK の長文  | **壊れた** |
  | 2 | `....md#日本語アンカー`   | CJK の短文  | 無傷     |
  | 3 | `....md#sp-1`             | CJK の長文  | **壊れた** |
  | 4 | `.md` を含まない          | CJK の長文  | 無傷     |
  | 6 | `....md#sp-1`             | ASCII       | 無傷     |
  | 8 | `....md`（リンクテキストは短い） | CJK の長文 | **壊れた** |

リンクテキストの内容（パス様かどうか）・日本語アンカーの有無は **トリガーではない**。
共通条件は「**URL に `.md` パスを含む行内リンクの直後に、非 ASCII の文が続く**」ことだった。

中間レイヤーはこちら側から修正できないため、**壊れる書式を書かない** ことが恒久対応になる。
回避策は Issue #26 で実証済み: 該当リンクを行内に埋めず、**1 行に単独で置く**。

## 検査対象（Issue / PR 本文になる文字列だけを見る）

  - `tools/*.py`                     … 起票系スクリプトが持つ本文テンプレート
  - `.claude/skills/**/SKILL.md`     … フェンスドコードブロック内のテンプレートのみ
  - `.github/**/*TEMPLATE*.md`       … PR / Issue テンプレート（全体）

`docs/rules/*.md` 等の通常ドキュメント本文は Issue 本文として送信されないため対象外
（対象を広げると、壊れようのないリンクを大量に誤検出する）。

使い方:
  python3 tools/check_github_body_markdown.py                 # 既定の対象を検査
  python3 tools/check_github_body_markdown.py <file> ...      # ファイルを指定して検査
  python3 tools/check_github_body_markdown.py --self-test     # セルフテスト

## レビュー済みの例外（`# gh-body-ok`）

意図的に壊れる書式を書く必要がある行（本ツール自身の self-test データ・破損例の提示など）は、
その行に `gh-body-ok` を書くと検査から除外できる。乱用しない（レビュー済みの正当な例外のみ）。

終了コード: 0=違反なし / 1=違反あり / 2=ツール異常
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 行内リンク `[text](url)` のうち URL が .md パス（アンカー付き可）を指すもの。
# URL 部分に空白・閉じ括弧は含めない（Markdown の行内リンクの一般形に合わせる）。
INLINE_MD_LINK_RE = re.compile(r"\[[^\]\n]*\]\([^()\s]*\.md(?:#[^()\s]*)?\)")

# フェンスドコードブロックの開始 / 終了（``` または ~~~）。
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")


# レビュー済みの例外マーカー（check_datetime_tz.py の `# tz-ok` と同型）。
ALLOW_MARKER = "gh-body-ok"


def _is_non_ascii(ch: str) -> bool:
    """CJK の約物（（「。等）も含めて拾いたいので、ASCII 外かどうかで判定する。"""
    return ord(ch) > 0x7F


def find_violations_in_text(text: str, *, fenced_only: bool) -> list[tuple[int, str]]:
    """壊れる書式の (行番号, 行) を返す。

    fenced_only=True のときは、フェンスドコードブロックの内側だけを検査する
    （SKILL.md の本文リンクではなく、そこに書かれた本文テンプレートだけを見るため）。
    """
    violations: list[tuple[int, str]] = []
    in_fence = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if fenced_only and not in_fence:
            continue
        if ALLOW_MARKER in line:
            continue

        for m in INLINE_MD_LINK_RE.finditer(line):
            tail = line[m.end():]
            if tail and _is_non_ascii(tail[0]):
                violations.append((lineno, line.strip()))
                break

    return violations


def default_targets() -> list[Path]:
    targets: list[Path] = []
    targets.extend(sorted((REPO_ROOT / "tools").glob("*.py")))
    targets.extend(sorted((REPO_ROOT / ".claude" / "skills").glob("*/SKILL.md")))
    github_dir = REPO_ROOT / ".github"
    if github_dir.is_dir():
        targets.extend(sorted(p for p in github_dir.rglob("*.md") if "TEMPLATE" in p.name.upper()))
    return targets


def check_files(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        if not path.is_file():
            continue
        # SKILL.md はテンプレート（フェンス内）だけを見る。スクリプト・PR テンプレートは全体を見る。
        fenced_only = path.name == "SKILL.md"
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # 解析不能を黙殺しない
            print(f"⚠️  読み込めません: {path} ({exc})", file=sys.stderr)
            return 2

        for lineno, line in find_violations_in_text(text, fenced_only=fenced_only):
            total += 1
            rel = path.relative_to(REPO_ROOT)
            print(f"❌ {rel}:{lineno}: .md への行内リンクの直後に非 ASCII の文が続いています", file=sys.stderr)
            print(f"    {line}", file=sys.stderr)

    if total:
        print(
            f"\n❌ {total} 件: この書式は送信経路の中間レイヤーがバッククォートを挿入し、"
            "リンクが解決しなくなります（Issue #27 で実測）。\n"
            "   回避策: 該当リンクを行内に埋めず 1 行に単独で置く（Issue #26 で実証済み）。",
            file=sys.stderr,
        )
        return 1

    print("✅ GitHub 本文 Markdown 検査: 違反なし")
    return 0


def self_test() -> int:
    """実測ケース（Issue #27）を回帰ケースとして固定する。"""
    md = "https://github.com/kai-kou/gem-hunter/blob/main/docs/02_requirements/user-story-map.md"

    broken = [
        # L1: URL に .md#日本語アンカー、直後に CJK の長文
        f"L1: [docs/02_requirements/user-story-map.md §5.3 SP-1]({md}#sp-1-検索して一覧が出るs-0)（操作レビュー手順の本文はここにコピーしない。ID 参照が正本）",
        # L3: URL に .md#ascii アンカー、直後に CJK
        f"L3: [docs/02_requirements/user-story-map.md §5.3 SP-1]({md}#sp-1)（操作レビュー手順の本文はここにコピーしない。ID 参照が正本）",
        # L8: リンクテキストが短くても URL 側が .md なら壊れる
        f"L8: [概要]({md})（操作レビュー手順の本文はここにコピーしない。ID 参照が正本）",
        # 相対パスの行内リンクも同じ形
        "L9: [ストーリーマップ](../02_requirements/user-story-map.md)（参照が正本）",  # gh-body-ok
    ]
    safe = [
        # L4: URL が .md を指さない（トリガーはリンクテキストではない）
        "L4: [docs/02_requirements/user-story-map.md §5.3 SP-1](https://example.com/x)（操作レビュー手順の本文はここにコピーしない。ID 参照が正本）",
        # L5: そもそも行内リンクではない
        "L5: docs/02_requirements/user-story-map.md §5.3 SP-1 を参照（操作レビュー手順の本文はここにコピーしない）",
        # L6: 直後が ASCII
        f"L6: [docs/02_requirements/user-story-map.md §5.3 SP-1]({md}#sp-1) trailing ascii text only",
        # L7: URL が .md を指さず直後が CJK
        "L7: [docs/02_requirements/user-story-map.md](https://example.com/x)（あいうえお）",
        # 回避策そのもの: リンクを 1 行に単独で置く
        f"[docs/02_requirements/user-story-map.md §5.3 SP-1]({md}#sp-1)",
    ]

    failures: list[str] = []

    for line in broken:
        if not find_violations_in_text(line, fenced_only=False):
            failures.append(f"検出できるべき行を検出しなかった: {line[:70]}")
    for line in safe:
        if find_violations_in_text(line, fenced_only=False):
            failures.append(f"検出すべきでない行を検出した: {line[:70]}")

    # fenced_only の挙動: フェンス外は無視し、フェンス内だけを見る
    doc = "\n".join([broken[2], "```markdown", broken[0], "```"])
    fenced = find_violations_in_text(doc, fenced_only=True)
    if len(fenced) != 1 or fenced[0][0] != 3:
        failures.append(f"fenced_only がフェンス内 1 件だけを拾えていない: {fenced}")
    if len(find_violations_in_text(doc, fenced_only=False)) != 2:
        failures.append("fenced_only=False が全体を拾えていない")

    # 未閉じフェンスでも例外にならず、フェンス内として扱われること
    if len(find_violations_in_text("```\n" + broken[1], fenced_only=True)) != 1:
        failures.append("未閉じフェンス内の違反を拾えていない")

    # レビュー済み例外マーカーが効くこと（効きすぎないこと＝マーカー無しでは検出されること）
    if find_violations_in_text(broken[3] + f"  # {ALLOW_MARKER}", fenced_only=False):
        failures.append(f"{ALLOW_MARKER} マーカーが効いていない")
    if not find_violations_in_text(broken[3], fenced_only=False):
        failures.append("マーカー無しの同じ行が検出されない（マーカー検証が無意味）")

    if failures:
        for f in failures:
            print(f"❌ self-test: {f}", file=sys.stderr)
        return 1

    print(f"✅ self-test: {len(broken)} 件の破損ケースと {len(safe)} 件の安全ケースを判別")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="検査するファイル（省略時は既定の対象）")
    parser.add_argument("--self-test", action="store_true", help="セルフテストを実行する")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    paths = [Path(p).resolve() for p in args.paths] if args.paths else default_targets()
    return check_files(paths)


if __name__ == "__main__":
    sys.exit(main())
