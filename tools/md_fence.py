#!/usr/bin/env python3
"""md_fence.py - Markdown のコードフェンス／インラインコードを判定する共有ヘルパー

なぜ共有化するか（PR #772 Layer 1 セルフレビュー）:
  コードフェンス追跡を各ツールが独自実装した結果、同じ欠陥（``` と ~~~ を同一カウンタで
  数える偶奇判定）が複数箇所に生まれた。偶奇判定は次の 2 方向に壊れる。
    - fail-open : ``` フェンスの中に ~~~ が 1 行あるとトグルが狂い、以降の文書全体が
                  「フェンス内」扱いで無検査になる（検査していないのに緑になる）
    - fail-closed: ```` で囲んだ中の ``` を「フェンス外」と誤判定して誤検知する
  本モジュールは CommonMark のフェンス規則（開始マーカーと同種・同長以上でのみ閉じる）に
  従い、1 パスで各行のフェンス内フラグを前計算する（行ごとの再走査による O(n^2) も解消）。

使い方:
    from md_fence import fence_flags, mask_inline_code
    flags = fence_flags(text.splitlines())   # flags[i] = i 行目がフェンス内か
    masked = mask_inline_code(line)          # インラインコードの中身を \x00 で退避

終了コード（self-test 実行時）: 0=PASS / 1=FAIL
"""
from __future__ import annotations

import re
import sys

# 行頭（インデント 3 まで許容・CommonMark）の ``` / ~~~ 開始・終了マーカー
_FENCE_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")

# インラインコードの退避に使うプレースホルダ（Markdown に現れない制御文字）
_STASH_CHAR = "\x00"


def fence_flags(lines: list[str], *, unclosed_is_fence: bool = False) -> list[bool]:
    """各行が「コードフェンスの内側か」を 1 パスで判定する。

    フェンスの開始行・終了行そのものは True（＝内側扱い）とする。フェンスの中身だけを
    見たい呼び出し側でも、マーカー行を検査対象にしたい場面は無いため。

    unclosed_is_fence:
        閉じられていないフェンスの扱い。CommonMark は「文書末まで継続」と定めるが、
        検査ツールでは「閉じ忘れ 1 個で以降が丸ごと無検査になる」fail-open を招く。
        既定（False）では未閉フェンスを不成立とみなし、開始行以降を検査対象へ戻す
        （安全側＝ fail-closed）。CommonMark 準拠が要る用途だけ True にする。
    """
    flags = [False] * len(lines)
    open_marker: str | None = None
    open_at = -1

    for i, line in enumerate(lines):
        m = _FENCE_RE.match(line)
        if open_marker is None:
            if m is not None:
                # 開始行。info string に同種マーカーは書けない（CommonMark）ので、
                # ``` のときだけ info の ` を弾く（~~~ は info に ` を許す）。
                marker = m.group("marker")
                if marker[0] == "`" and "`" in m.group("info"):
                    continue
                open_marker = marker
                open_at = i
                flags[i] = True
            continue

        # フェンス内。同種・同長以上のマーカー **のみ** の行で閉じる（info string 不可）
        flags[i] = True
        if m is not None:
            marker = m.group("marker")
            if (
                marker[0] == open_marker[0]
                and len(marker) >= len(open_marker)
                and m.group("info").strip() == ""
            ):
                open_marker = None

    if open_marker is not None and not unclosed_is_fence:
        # 未閉フェンス → 不成立とみなして開始行以降を検査対象へ戻す
        for i in range(open_at, len(lines)):
            flags[i] = False

    return flags


def has_unclosed_fence(lines: list[str]) -> bool:
    """未閉フェンスが残るかを返す（呼び出し側が Warning を出したいとき用）。"""
    open_marker: str | None = None
    for line in lines:
        m = _FENCE_RE.match(line)
        if m is None:
            continue
        marker = m.group("marker")
        if open_marker is None:
            if marker[0] == "`" and "`" in m.group("info"):
                continue
            open_marker = marker
        elif (
            marker[0] == open_marker[0]
            and len(marker) >= len(open_marker)
            and m.group("info").strip() == ""
        ):
            open_marker = None
    return open_marker is not None


def mask_inline_code(s: str) -> str:
    """インラインコード（コードスパン）の中身を退避する。

    バッククォートの連数が可変（`` `a | b` `` / ``` `` a|b `` ``` ）なので、開始と同数の
    バッククォートで閉じる形を正しく扱う。退避後の文字列は元と同じ長さを保つため、
    列数の数え上げや位置の突き合わせにそのまま使える。
    """

    def _stash(match: re.Match[str]) -> str:
        return _STASH_CHAR * len(match.group(0))

    return re.sub(r"(?P<ticks>`+)(?:(?!(?P=ticks))[\s\S])*(?P=ticks)", _stash, s)


def _self_test() -> int:
    failures: list[str] = []

    def check(name: str, got: object, want: object) -> None:
        if got != want:
            failures.append(f"{name}: got={got!r} want={want!r}")

    # 1. 単純なフェンス
    check(
        "単純な ``` フェンス",
        fence_flags(["a", "```", "in", "```", "b"]),
        [False, True, True, True, False],
    )

    # 2. ``` フェンスの中の ~~~ で状態が狂わない（旧実装の fail-open）
    check(
        "``` の中の ~~~ で閉じない",
        fence_flags(["```text", "~~~", "```", "| 1 | 2 | x"]),
        [True, True, True, False],
    )

    # 3. ~~~ フェンスの中の ``` で閉じない
    check(
        "~~~ の中の ``` で閉じない",
        fence_flags(["~~~markdown", "```", "```", "~~~", "out"]),
        [True, True, True, True, False],
    )

    # 4. 4 連バッククォートの中の ``` で閉じない（旧実装の fail-closed）
    check(
        "```` の中の ``` で閉じない",
        fence_flags(["````", "```", "```", "````", "out"]),
        [True, True, True, True, False],
    )

    # 5. 開始より長いマーカーでも閉じられる
    check(
        "``` を ```` で閉じられる",
        fence_flags(["```", "in", "````", "out"]),
        [True, True, True, False],
    )

    # 6. 未閉フェンスは既定で不成立（安全側＝以降を検査対象へ戻す）
    check(
        "未閉フェンスは既定で不成立",
        fence_flags(["a", "```", "Closes #1"]),
        [False, False, False],
    )
    check(
        "未閉フェンスは unclosed_is_fence=True でフェンス扱い",
        fence_flags(["a", "```", "Closes #1"], unclosed_is_fence=True),
        [False, True, True],
    )
    check("has_unclosed_fence（未閉あり）", has_unclosed_fence(["```", "x"]), True)
    check("has_unclosed_fence（未閉なし）", has_unclosed_fence(["```", "x", "```"]), False)

    # 7. 閉じマーカーに info string が付いていたら閉じない（CommonMark）
    check(
        "閉じ側の info string は閉じない",
        fence_flags(["```", "in", "```js", "still in", "```"]),
        [True, True, True, True, True],
    )

    # 8. インデント 3 までは開始マーカーとして有効
    check(
        "インデント 3 の開始マーカー",
        fence_flags(["   ```", "in", "   ```", "out"]),
        [True, True, True, False],
    )

    # 9. 行頭インラインコード（```foo```）を開始マーカーにしない
    check(
        "```foo``` は開始マーカーにしない",
        fence_flags(["```foo```", "| 1 | 2 | x"]),
        [False, False],
    )

    # 10. インラインコードの退避（1 連・複数連・長さ保存）
    # `| `a|b` | c |` の区切りパイプは 3 本（コードスパン内の | は退避されて消える）
    check("1 連バッククォート", mask_inline_code("| `a|b` | c |").count("|"), 3)
    check("2 連バッククォート", mask_inline_code("| ``a|b`` | c |").count("|"), 3)
    check("退避しない場合は 4 本", "| `a|b` | c |".count("|"), 4)
    check("長さを保存する", len(mask_inline_code("| `a|b` | c |")), len("| `a|b` | c |"))
    check("閉じないバッククォートは退避しない", mask_inline_code("| `a | b |").count("|"), 3)

    if failures:
        print("❌ md_fence.py self-test 失敗:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("✅ md_fence.py self-test: 全ケース PASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(_self_test())
    print("使い方: python3 tools/md_fence.py --self-test", file=sys.stderr)
    sys.exit(2)
