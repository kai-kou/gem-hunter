#!/usr/bin/env python3
"""check_agent_diff_claim.py — サブエージェントの完了報告と実 diff を突合し虚偽報告・報告漏れを検知する（#99）

## なぜ必要か

委譲したサブエージェントが「3 ファイルを修正し検証済み」と詳細な報告を返したが、ディスク上の
ファイルは 1 つも変更されていなかった事例が発生した（SP-2 レトロスペクティブ・PR #96）。親が
`git status` / `git diff` で突合して初めて発覚しており、この突合は完全に人手だった。本ツールは
「サブエージェントの完了報告に書かれた変更ファイル一覧」と「実際の作業ツリーの差分」を機械的に
突合する。

## 検査方法（読み取り専用）

実 diff は以下 3 コマンドを `subprocess` で実行し **読み取りのみ** で取得する（書き込み系 git
コマンドは一切呼ばない）:

- `git status --short`（追跡外ファイルも含む変更全体）
- `git diff --stat`（未ステージの変更）
- `git diff --cached --stat`（ステージ済みの変更）

3 つの出力からファイルパスを抽出した和集合を「実 diff ファイル集合」とする。

## 入力形式

`--stdin` でサブエージェントの完了報告テキストをそのまま標準入力に流し込む
（オーケストレーターが Bash から 1 コマンドで叩けることを最優先にした唯一の形式）。

**優先: 明示リストブロック（`CHANGED_FILES:`・Issue #717）**。報告テキストに
`CHANGED_FILES:` 行（大文字小文字不問・前後の空白は許容）があれば、その直後の行
（空行・コードフェンス終端・次の `CHANGED_FILES:` 行のいずれかまで）だけを claim 集合とする。
それ以外の本文（否定文脈の言及「〜は変更していません」等）は一切見ない — 文字列一致だけで
「報告済み」とみなす旧方式は、否定文脈の言及を誤って claim 扱いし `missing_from_report`
（報告漏れ＝より重い警告）を握りつぶす fail-open だったため（#717）。

```
CHANGED_FILES:
tools/check_agent_diff_claim.py
docs/rules/agent-team-summary.md
```

**フォールバック: 全文ヒューリスティックスキャン**。`CHANGED_FILES:` ブロックが無い報告
（明示ブロック未導入の既存運用・移行期）では、テキスト中からパスらしき文字列
（`git status --short` 形式の行・バッククォート囲みのパス・スラッシュと拡張子を含むトークン）を
正規表現で抽出する（ヒューリスティックのため 100% ではなく、否定文脈の誤検出も残る）。
フォールバックした事実は **必ず** stderr と JSON 出力（`fallback_used`）に明示する（黙って劣化させない）。

    cat agent_report.txt | python3 tools/check_agent_diff_claim.py --stdin

## 判定

- 「報告にあるが実 diff に無い」（`missing_from_diff`）: 虚偽報告・未反映の疑い → 警告
- 「実 diff にあるが報告に無い」（`missing_from_report`）: 報告漏れ。親が見落としやすい方向
  のため **より重い警告** として扱う
- どちらか一方でも非空なら exit 1

## 使い方

    python3 tools/check_agent_diff_claim.py --stdin < agent_report.txt
    python3 tools/check_agent_diff_claim.py --stdin --json < agent_report.txt
    python3 tools/check_agent_diff_claim.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# パスらしきトークン: 英数字/アンダースコア/開き角括弧で始まり、スラッシュ・ドット・ハイフン・
# 角括弧を含み、最後に "." + 拡張子で終わる文字列。
# 角括弧（`[` `]`）は Next.js App Router の動的セグメント（`app/[locale]/page.tsx` 等）で
# 実際にこのリポジトリのパスに使われているため必須（Issue #712）。`git ls-files` で確認した限り
# 本リポジトリのパスに現れる記号は `[` `]` `.` `-` `_` `/` のみで、`(` `)` `@` `+` `~` 等は
# 使われていない（含めると日本語文中の記号を誤って拾うリスクが増すため見送る）。
# 先頭にも `[` を許すのは、報告が先頭ディレクトリを省いて `[locale]/page.tsx` と書いた場合に
# 開き括弧を落とした `locale]/page.tsx` を生まないため（PR #716 Layer 1 レビュー）。
#
# 既知の限界（いずれも `missing_from_diff` = 余分な警告側にしか倒れない）:
#   - `list[0].name` のような配列アクセス表記が 1 トークンとして拾われる
#   - `a[b.c` のように括弧が閉じない断片がそのまま候補に残る
# 一方、`][` で連結された 2 パス（`[a/x.py][b/y.py]`）は 1 トークンに融合すると
# **両方のパスが `missing_from_report` 側へ落ちる**（見落とし方向）ため、
# `extract_claimed_paths` が後処理で明示的に分割する。
_PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_\[][A-Za-z0-9_./\[\]-]*\.[A-Za-z0-9_]+")
_URL_RE = re.compile(r"https?://\S+")  # ドメイン名がパストークンとして誤抽出されるのを防ぐため事前に除去する

# 課題2（#717）: `_PATH_TOKEN_RE` は「.」を含まない・区切りが無い巨大な非マッチ文字列に対して
# 二次関数的にバックトラックする（実測: 200,001 文字の非空白トークン単独で約 78 秒）。
# 空白区切りでトークン化してから 1 トークンずつ照合すれば、悪意/暴走した入力が
# 「空白を含まない 1 個の巨大トークン」であっても各トークンの照合コストを定数で頭打ちできる
# （現実のファイルパスがこの長さを超えることはない）。
_MAX_TOKEN_CHARS = 500

# 課題2（#717）: stdin 全体に対する多重防御の安全弁。トークン単位の頭打ち（上記）だけで
# 二次関数バックトラックは解消するが、暴走したサブエージェントが数百 KB 〜 MB を返すケースに
# 備え、そもそもの処理対象文字数も上限で切り詰める（切り詰めた事実は stderr に明示する）。
MAX_STDIN_CHARS = 200_000

# 課題1（#717）: 明示リストブロックのヘッダー行。大文字小文字は問わない。
_CHANGED_FILES_HEADER_LINE_RE = re.compile(r"^[ \t]*CHANGED_FILES:[ \t]*$", re.IGNORECASE)


def _tokens_from_text(text: str) -> set[str]:
    """任意のテキストからパスらしきトークンを抽出する（ヒューリスティック本体）。

    空白区切りでトークン化し、1 トークンずつ `_MAX_TOKEN_CHARS` で頭打ちしてから
    `_PATH_TOKEN_RE` を適用する（課題2: バックトラック対策）。パス文字クラスに
    空白は含まれないため、この前処理は通常入力の抽出結果を一切変えない
    （元の実装が全文に対して `findall` していたのと同じ結果になる）。
    """
    candidates: set[str] = set()
    for word_match in re.finditer(r"\S+", text):
        word = word_match.group(0)
        if len(word) > _MAX_TOKEN_CHARS:
            word = word[:_MAX_TOKEN_CHARS]
        for raw in _PATH_TOKEN_RE.findall(word):
            # `[a/x.py][b/y.py]` のように区切りなしで並べられた 2 パスを分割する。
            # 融合したままだと実 diff のどちらとも一致せず、両方が missing_from_report
            # （見落とし方向のより重い警告）に落ちるため、ここだけは後処理で必ず割る。
            for tok in raw.split("]["):
                tok = tok.strip("`'\"(),;:")
                tok = _trim_unpaired_brackets(tok)
                tok = tok.lstrip("./")
                if not tok:
                    continue
                ext = tok.rsplit(".", 1)[-1]
                if ext.isdigit():
                    continue
                candidates.add(tok)
    return candidates


def _find_changed_files_block(text: str) -> str | None:
    """`CHANGED_FILES:` ヘッダー以降の行を明示リストブロックとして切り出す（課題1・#717）。

    ヘッダー行が見つからなければ `None`（＝呼び出し側はフォールバックする）。
    ヘッダー行はあるが本文が空（次行が空行 / コードフェンス終端 / EOF）なら
    `""` を返す（「ブロックはあるが claim はゼロ件」を明示的に表す。フォールバックとは区別する）。
    ブロックの終端は「空行」「コードフェンス終端（```）」「次の `CHANGED_FILES:` ヘッダー行」の
    いずれか（先に来たもの）。これによりブロック前後の空行・インデント・コードフェンス内配置を
    素通しできる（大文字小文字はヘッダー正規表現側で吸収）。
    """
    lines = text.split("\n")
    header_idx = None
    for i, line in enumerate(lines):
        if _CHANGED_FILES_HEADER_LINE_RE.match(line):
            header_idx = i
            break
    if header_idx is None:
        return None
    body: list[str] = []
    for line in lines[header_idx + 1 :]:
        if line.strip() == "":
            break
        if line.strip().startswith("```"):
            break
        if _CHANGED_FILES_HEADER_LINE_RE.match(line):
            break
        body.append(line)
    return "\n".join(body)


def extract_claimed_paths(text: str) -> tuple[set[str], bool]:
    """完了報告テキストから claim されたパス集合を抽出する。

    戻り値は `(パス集合, 明示ブロックを使ったか)`。

    - 明示ブロック（`CHANGED_FILES:` ヘッダー以降の行）が **ある** 場合: そのブロックの
      内容だけを走査する。ブロック外の本文（否定文脈の言及等）は一切見ないため、
      「テキスト中の言及＝claim」という旧方式の fail-open（課題1・#717）が構造的に起きない。
    - 明示ブロックが **無い** 場合: 従来どおり全文をヒューリスティックスキャンする
      （後方互換フォールバック）。呼び出し側は `used_block=False` を見て、フォールバックした
      事実をユーザー / ログに明示すること（黙って劣化させない）。

    バージョン番号（"2.1.198" や "v2.1.198"）は拡張子相当の末尾セグメントが数字のみ
    （`ext.isdigit()`）になるため `_tokens_from_text` 内で除外される。URL は事前に除去する。
    """
    block = _find_changed_files_block(text)
    if block is not None:
        return _tokens_from_text(_URL_RE.sub(" ", block)), True
    return _tokens_from_text(_URL_RE.sub(" ", text)), False


def _trim_unpaired_brackets(tok: str) -> str:
    """端に付いた対応相手のいない角括弧だけを落とす（対応が取れているものは残す）。

    `split("][")` で割った断片は端に片方の括弧だけが残ることがある。動的セグメント
    （`app/[locale]/page.tsx`）の括弧は対応が取れているので落とさない。
    """
    while tok.startswith("]"):
        tok = tok[1:]
    while tok.endswith("["):
        tok = tok[:-1]
    if tok.startswith("[") and "]" not in tok[1:]:
        tok = tok[1:]
    if tok.endswith("]") and "[" not in tok[:-1]:
        tok = tok[:-1]
    return tok


def run_git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
        )
        return proc.stdout
    except FileNotFoundError as e:
        raise RuntimeError("git コマンドが見つかりません") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git {' '.join(args)} が失敗: {e.stderr.strip()}") from e


def parse_status_short(output: str) -> set[str]:
    """`git status --short` 出力からファイルパスを抽出する（リネームは新パスを採用）。"""
    files: set[str] = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) > 3 else line.strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        if rest:
            files.add(rest)
    return files


def parse_diff_stat(output: str) -> set[str]:
    """`git diff --stat` 出力からファイルパスを抽出する（末尾のサマリー行は "|" が無く自動除外）。"""
    files: set[str] = set()
    for line in output.splitlines():
        if "|" not in line:
            continue
        path = line.split("|", 1)[0].strip()
        if path:
            files.add(path)
    return files


def get_real_diff_files(root: Path) -> dict:
    status_out = run_git(["status", "--short"], root)
    diff_out = run_git(["diff", "--stat"], root)
    cached_out = run_git(["diff", "--cached", "--stat"], root)
    files: set[str] = set()
    files |= parse_status_short(status_out)
    files |= parse_diff_stat(diff_out)
    files |= parse_diff_stat(cached_out)
    return {
        "files": files,
        "raw": {"status": status_out, "diff_stat": diff_out, "diff_cached_stat": cached_out},
    }


def compare(claimed: set[str], real: set[str]) -> dict:
    missing_from_diff = sorted(claimed - real)
    missing_from_report = sorted(real - claimed)
    return {
        "claimed": sorted(claimed),
        "real": sorted(real),
        "missing_from_diff": missing_from_diff,
        "missing_from_report": missing_from_report,
        "mismatch": bool(missing_from_diff or missing_from_report),
    }


def print_report(result: dict) -> None:
    if result.get("fallback_used"):
        print("⚠️  CHANGED_FILES: 明示ブロックが見つからず、全文ヒューリスティックスキャンにフォールバックしました（否定文脈の言及も claim として拾う可能性があります）")
    print(f"報告ファイル: {len(result['claimed'])} 件 / 実 diff ファイル: {len(result['real'])} 件")
    if result["missing_from_diff"]:
        print("⚠️  報告にあるが実 diff に無い（虚偽報告・未反映の疑い）:")
        for f in result["missing_from_diff"]:
            print(f"    - {f}")
    if result["missing_from_report"]:
        print("❌ 実 diff にあるが報告に無い（報告漏れ・親が見落としやすい方向・より重い）:")
        for f in result["missing_from_report"]:
            print(f"    - {f}")
    if not result["mismatch"]:
        print("✅ 報告と実 diff は一致")


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def run_self_test() -> int:
    passed, failed = 0, 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {label}" + (f" — {detail}" if detail else ""))

    # parse_status_short: 追跡外・変更・リネームを正しく拾う
    status_sample = " M tools/foo.py\n?? tools/new_file.py\nR  tools/old.py -> tools/renamed.py\n"
    got = parse_status_short(status_sample)
    check(
        "parse_status_short 通常/追跡外/リネーム",
        got == {"tools/foo.py", "tools/new_file.py", "tools/renamed.py"},
        str(got),
    )

    # parse_diff_stat: サマリー行（"|" 無し）を含めない
    stat_sample = (
        " tools/foo.py      | 10 +++++-----\n"
        " path/to/bar.py    | 3 +--\n"
        " 2 files changed, 8 insertions(+), 5 deletions(-)\n"
    )
    got2 = parse_diff_stat(stat_sample)
    check("parse_diff_stat サマリー行除外", got2 == {"tools/foo.py", "path/to/bar.py"}, str(got2))

    # extract_claimed_paths: 完了報告の自由文からパスを抽出（明示ブロック無し→フォールバック）
    report_text = (
        "## 変更ファイル一覧\n"
        " M tools/check_agent_scope_overlap.py\n"
        "?? tools/check_agent_diff_claim.py\n"
        "本文中で `docs/rules/agent-team-summary.md` にも触れています。\n"
        "v2.1.198 で検証済み。詳細は https://example.com/path.html を参照。\n"
    )
    got3, used3 = extract_claimed_paths(report_text)
    check(
        "extract_claimed_paths 抽出（バージョン/URL除外・フォールバック）",
        got3
        == {
            "tools/check_agent_scope_overlap.py",
            "tools/check_agent_diff_claim.py",
            "docs/rules/agent-team-summary.md",
        }
        and used3 is False,
        str((got3, used3)),
    )

    # extract_claimed_paths: 角括弧を含む Next.js App Router 動的セグメントパスを
    # 切り詰めずに、かつ 2 件を同じ文字列に潰さず別々に抽出できること（Issue #712）
    bracket_report_text = (
        "役3（#549）新規作成: app/[locale]/page.test.tsx\n"
        "役3（#549）新規作成: app/[locale]/repos/[owner]/[repo]/page.test.tsx\n"
    )
    got_bracket, _ = extract_claimed_paths(bracket_report_text)
    check(
        "extract_claimed_paths 角括弧パスを切り詰めず別々に抽出（#712）",
        got_bracket
        == {
            "app/[locale]/page.test.tsx",
            "app/[locale]/repos/[owner]/[repo]/page.test.tsx",
        },
        str(got_bracket),
    )

    # extract_claimed_paths: 区切りなしで隣接した 2 パス（`][`）を融合させないこと。
    # 融合すると両方が missing_from_report（見落とし方向）へ落ちるため、
    # 上の角括弧ケースより実害が重い（PR #716 Layer 1 レビュー）
    got_adjacent, _ = extract_claimed_paths("参照: [a/x.py][b/y.py]")
    check(
        "extract_claimed_paths 隣接した角括弧パスを融合させない（#716）",
        got_adjacent == {"a/x.py", "b/y.py"},
        str(got_adjacent),
    )

    # extract_claimed_paths: 動的セグメントから書き始めた報告でも開き括弧を落とさないこと
    got_leading, _ = extract_claimed_paths("新規作成: [locale]/page.tsx")
    check(
        "extract_claimed_paths 先頭の動的セグメントの開き括弧を落とさない（#716）",
        got_leading == {"[locale]/page.tsx"},
        str(got_leading),
    )

    # compare: Issue #712 の再現ケースを end-to-end で検証する。
    # 抽出単体ではなく compare まで通し、報告と実 diff が一致（mismatch=False）することを見る
    # （元の症状は「報告 4 件 / 実 diff 5 件」という件数の食い違いだった）
    issue712_report = (
        "役3（#549）新規作成: app/[locale]/page.test.tsx\n"
        "役3（#549）新規作成: app/[locale]/repos/[owner]/[repo]/page.test.tsx\n"
        "役3（#549）新規作成: app/[locale]/repos/[owner]/page.test.tsx\n"
        "役3（#549）修正: src/ui/repo-card.tsx\n"
        "役3（#549）修正: tools/check_agent_diff_claim.py\n"
    )
    issue712_real = {
        "app/[locale]/page.test.tsx",
        "app/[locale]/repos/[owner]/[repo]/page.test.tsx",
        "app/[locale]/repos/[owner]/page.test.tsx",
        "src/ui/repo-card.tsx",
        "tools/check_agent_diff_claim.py",
    }
    r_issue712 = compare(extract_claimed_paths(issue712_report)[0], issue712_real)
    check(
        "compare #712 再現ケース（5 ファイル）で不一致 0 件（#712 完了条件）",
        r_issue712["mismatch"] is False,
        str(r_issue712),
    )

    # ── #717 課題1: 明示リストブロック（CHANGED_FILES:）────────────────
    # 否定文脈で言及されただけのパスが claim に紛れ込まない・missing_from_report が
    # 握りつぶされないことを end-to-end（compare まで）で検証する（完了条件そのもの）
    negation_text = (
        "app/[locale]/page.tsx は今回変更していません。無関係な既存コードです。\n"
        "CHANGED_FILES:\n"
        "tools/foo.py\n"
    )
    got_neg, used_neg = extract_claimed_paths(negation_text)
    check(
        "明示ブロックあり: 否定文脈のパスを claim に含めない・used_block=True（#717 課題1）",
        got_neg == {"tools/foo.py"} and used_neg is True,
        str((got_neg, used_neg)),
    )
    r_neg = compare(got_neg, {"tools/foo.py", "app/[locale]/page.tsx"})
    check(
        "否定文脈のパスが実際に変更されていれば missing_from_report で検出される（#717 完了条件）",
        r_neg["missing_from_report"] == ["app/[locale]/page.tsx"] and r_neg["mismatch"] is True,
        str(r_neg),
    )

    # 入力バリアント: ブロック前後の空行
    v_blank, u_blank = extract_claimed_paths(
        "\n\n報告です。\n\nCHANGED_FILES:\ntools/a.py\ntools/b.py\n\n以上です。\n"
    )
    check(
        "バリアント: ブロック前後の空行があっても正しく抽出（#717）",
        v_blank == {"tools/a.py", "tools/b.py"} and u_blank is True,
        str((v_blank, u_blank)),
    )

    # 入力バリアント: インデント（ヘッダー行・本文行とも字下げ）
    v_indent, u_indent = extract_claimed_paths("  CHANGED_FILES:\n  tools/a.py\n  tools/b.py\n")
    check(
        "バリアント: インデントされたブロックを正しく抽出（#717）",
        v_indent == {"tools/a.py", "tools/b.py"} and u_indent is True,
        str((v_indent, u_indent)),
    )

    # 入力バリアント: コードフェンス内（フェンス終端でブロックが正しく閉じる）
    v_fence, u_fence = extract_claimed_paths("```\nCHANGED_FILES:\ntools/a.py\ntools/b.py\n```\n")
    check(
        "バリアント: コードフェンス内のブロックをフェンス終端で正しく閉じる（#717）",
        v_fence == {"tools/a.py", "tools/b.py"} and u_fence is True,
        str((v_fence, u_fence)),
    )

    # 入力バリアント: 大文字小文字を問わない
    v_case, u_case = extract_claimed_paths("changed_files:\ntools/a.py\n")
    check(
        "バリアント: ヘッダーの大文字小文字を問わない（#717）",
        v_case == {"tools/a.py"} and u_case is True,
        str((v_case, u_case)),
    )

    # 入力バリアント: 明示ブロックが空（ヘッダーはあるが本文が無い）
    # → 「ブロックはあったが claim ゼロ件」であり、フォールバックとは区別する
    v_empty, u_empty = extract_claimed_paths("CHANGED_FILES:\n\n実際には何も変えていません。\n")
    check(
        "バリアント: 明示ブロックが空なら claim=空集合・used_block=True（フォールバックしない）（#717）",
        v_empty == set() and u_empty is True,
        str((v_empty, u_empty)),
    )
    r_empty = compare(v_empty, {"tools/unreported.py"})
    check(
        "空ブロック: 実 diff にあるファイルは全て missing_from_report に出る（#717）",
        r_empty["missing_from_report"] == ["tools/unreported.py"] and r_empty["mismatch"] is True,
        str(r_empty),
    )

    # ── #717 課題2: 病的入力に対する性能（O(n^2) バックトラック対策）──────────
    import time as _time

    pathological = "a" * 200_001  # 空白なし・"." 無しの巨大単一トークン（旧実装で約78秒）
    _t0 = _time.perf_counter()
    _got_perf, _ = extract_claimed_paths(pathological)
    _elapsed = _time.perf_counter() - _t0
    check(
        f"性能: 200,001文字の病的入力が1秒未満で返る（実測 {_elapsed:.3f}s・#717 完了条件）",
        _elapsed < 1.0,
        f"{_elapsed:.3f}s / 抽出結果={_got_perf}",
    )

    # compare: 一致
    r_match = compare({"a.py", "b.py"}, {"a.py", "b.py"})
    check("compare 一致で mismatch=False", r_match["mismatch"] is False, str(r_match))

    # compare: 双方向の不一致を検出
    r_mismatch = compare({"a.py", "b.py"}, {"a.py", "c.py"})
    check(
        "compare 双方向不一致を検出",
        r_mismatch["missing_from_diff"] == ["b.py"]
        and r_mismatch["missing_from_report"] == ["c.py"]
        and r_mismatch["mismatch"] is True,
        str(r_mismatch),
    )

    print(f"\nセルフテスト: {passed} passed, {failed} failed / {passed + failed} cases")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stdin", action="store_true", help="標準入力から完了報告テキストを読みパスらしき文字列を抽出する")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    # selftest-wiring-ok: サブエージェント委譲直後に親が手動で叩く運用ツールで、PR 前の品質ゲートではない
    parser.add_argument("--self-test", action="store_true", help="セルフテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.stdin:
        parser.print_help()
        return 2

    raw_stdin = sys.stdin.read()
    if len(raw_stdin) > MAX_STDIN_CHARS:
        print(
            f"⚠️  stdin が {len(raw_stdin)} 文字と大きいため先頭 {MAX_STDIN_CHARS} 文字に切り詰めました（課題2・#717）",
            file=sys.stderr,
        )
        raw_stdin = raw_stdin[:MAX_STDIN_CHARS]

    claimed, used_block = extract_claimed_paths(raw_stdin)
    if not used_block:
        print(
            "⚠️  CHANGED_FILES: 明示ブロックが見つからないため、全文ヒューリスティックスキャンにフォールバックしました"
            "（否定文脈の言及も claim として拾う可能性があります・#717）",
            file=sys.stderr,
        )

    try:
        real = get_real_diff_files(REPO_ROOT)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    result = compare(claimed, real["files"])
    result["fallback_used"] = not used_block

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return 1 if result["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
