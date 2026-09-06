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
- 「`.../` 省略パスを一意に解決できなかった」（`unresolved`）: どの実ファイルを指すか確定できず
  報告漏れとも虚偽報告とも判定できない → `mismatch` には混ぜないが **exit 2（判定不能）** を返す
  （`0` へ丸めると exit code だけを見る呼び出し元に「未検証のファイルが残っている」ことが届かない・
  `docs/rules/check-tool-design-rules.md` §1 / §3 の fail-closed 既定）

## 終了コード

- `0`: 報告と実 diff が一致し、未解決の省略パスも無い
- `1`: 虚偽報告・報告漏れを検出した
- `2`: 判定不能（git 実行失敗・引数不足・解決できない省略パスが残った）

## 使い方

    python3 tools/check_agent_diff_claim.py --stdin < agent_report.txt
    python3 tools/check_agent_diff_claim.py --stdin --json < agent_report.txt
    python3 tools/check_agent_diff_claim.py --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import git_diff_utils

REPO_ROOT = Path(__file__).resolve().parent.parent

# パスらしきトークン: 英数字/アンダースコア/開き角括弧/先頭ドットで始まり、スラッシュ・ドット・
# ハイフン・角括弧を含み、最後に "." + 拡張子で終わる文字列。
# 角括弧（`[` `]`）は Next.js App Router の動的セグメント（`app/[locale]/page.tsx` 等）で
# 実際にこのリポジトリのパスに使われているため必須（Issue #712）。`git ls-files` で確認した限り
# 本リポジトリのパスに現れる記号は `[` `]` `.` `-` `_` `/` のみで、`(` `)` `@` `+` `~` 等は
# 使われていない（含めると日本語文中の記号を誤って拾うリスクが増すため見送る）。
# 先頭にも `[` を許すのは、報告が先頭ディレクトリを省いて `[locale]/page.tsx` と書いた場合に
# 開き括弧を落とした `locale]/page.tsx` を生まないため（PR #716 Layer 1 レビュー）。
# 先頭に `.` も許すのは Issue #948 の対策（重要・見落としやすい）: 先頭文字クラスが `.` を
# 除外していると、`.github/workflows/x.yml` のような **標準の先頭ドットパス** は
# `re.findall` の「最も左で始まるマッチ」規則により、そもそも `.` の次の文字（`g`）から
# マッチが始まってしまい `github/workflows/x.yml` になる。これは旧 `tok.lstrip("./")` の
# 文字集合バグ（`.` `/` を集合として食い荒らす）とは **別の場所で起きる同じ症状の別原因**
# であり、`lstrip` を `removeprefix` に直すだけでは直らない（`tok` に渡る時点で既に `.` が
# 失われているため）。実測: 修正前は `_PATH_TOKEN_RE.findall(".github/workflows/x.yml")`
# が `['github/workflows/x.yml']` を返す（`.` が消える）。
#
# 既知の限界（いずれも `missing_from_diff` = 余分な警告側にしか倒れない）:
#   - `list[0].name` のような配列アクセス表記が 1 トークンとして拾われる
#   - `a[b.c` のように括弧が閉じない断片がそのまま候補に残る
# 一方、`][` で連結された 2 パス（`[a/x.py][b/y.py]`）は 1 トークンに融合すると
# **両方のパスが `missing_from_report` 側へ落ちる**（見落とし方向）ため、
# `extract_claimed_paths` が後処理で明示的に分割する。
#
# Issue #968（CRITICAL・上記と同型で発見が遅れた回帰）: 先頭文字クラスへ `.` を足した副作用で、
# `../bin/tool.sh`（相対パス）や「対応完了...utils.pyを修正」中の `...utils.py`（三点リーダーと
# ファイル名の融合）も 1 トークンとしてそのまま拾われる。これらは実 diff 側では `bin/tool.sh` /
# `utils.py` として現れるため、正規化せず素通しすると `missing_from_report`（報告漏れ・見落とし
# 方向のより重い警告）に落ちる。`git_diff_utils.normalize_leading_dots()`（claim 側・実 diff 側の
# 両方が通る共通正規化関数）が「../」1 回以上・直後が英数字の 2+ 連続ドットを剥がして解決する
# （`.../` = `ABBREV_PREFIX` は先読みで保護され絶対に触らない）。
# Issue #880: 上記の拡張子必須パターンは `.gitignore` のような「拡張子を持たない先頭ドット
# ファイル」（ドットが 1 個しかない）を一切抽出できない（`re.findall(".gitignore")` は空リスト。
# パターンが「本体 + リテラル "." + 拡張子」の 2 ドット構造を要求するため）。CHANGED_FILES:
# ブロックに `.gitignore` とだけ書かれた報告は claim に一切現れず、実 diff 側にだけ存在する
# ことになり `missing_from_report`（報告漏れ・より重い警告）の偽陽性を生む。
# 第 2 選択肢として「先頭ドット + 英数字/アンダースコア/ハイフンのみで、直後に更なる `.` や
# 単語文字が続かない（＝拡張子パターン側に既に食われていない）」bare dotfile を追加する。
# `(?<![.\w])` で直前が `.` や単語文字でないことを要求し、二重ドット（`...utils.py` 等・#968 が
# 別関数で処理する）や「拡張子パターンの内部から始まる部分マッチ」を避ける。`(?![.\w-])` で
# 直後に別の `.` や単語文字・ハイフンが続かないことを要求する。
# 🔴 **本体は小文字・数字・`_`・`-` に限定する**（Layer 1 セルフレビュー指摘）。`[A-Za-z...]` に
# すると `.NET` のような大文字始まりの技術名が自由記述から拾われて claim に混入し、
# `missing_from_diff` 経由で **exit 1（FAIL）** になる（`compare()` の `mismatch` は
# `missing_from_diff or missing_from_report` なので「軽い警告側」ではない・実測済み）。
# 実在の bare dotfile（`.gitignore` / `.eslintrc` / `.npmrc` / `.editorconfig` …）は慣行として
# すべて小文字なので、限定しても取りこぼしは実質的に生じない。仮に大文字の bare dotfile を
# 報告して拾えなかった場合は `missing_from_report` 側（fail-closed）に出るだけで、
# 「報告漏れを見逃す」方向へは倒れない。
_PATH_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_.\[][A-Za-z0-9_./\[\]-]*\.[A-Za-z0-9_]+"
    r"|(?<![.\w])\.[a-z0-9_-]+(?![.\w-])"
)
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
                # Issue #948: `lstrip("./")` は文字集合として解釈されるため、`.github/workflows/x.yml`
                # のような先頭ドット付きの実在パスまで `.` を食い荒らし `github/workflows/x.yml` に
                # 化けていた（偽陽性の直接原因）。共通正規化関数（claim 側・実 diff 側の双方が通る
                # 唯一の入口）に置き換える。Issue #968: 同関数は「../」相対パス・三点リーダー融合
                # （"...utils.py"）の正規化も担う（`_PATH_TOKEN_RE` 先頭文字クラスへ `.` を足した
                # 副作用で生まれた新しい偽陽性・下記 `_PATH_TOKEN_RE` docstring 参照）。
                tok = git_diff_utils.normalize_leading_dots(tok)
                if not tok:
                    continue
                ext = tok.rsplit(".", 1)[-1]
                if ext.isdigit():
                    continue
                candidates.add(tok)
    return candidates


def _find_changed_files_blocks(text: str) -> list[str] | None:
    """`CHANGED_FILES:` ヘッダーごとの明示リストブロックを **全件** 切り出す（課題1・#717 / PR #723 指摘2）。

    ヘッダー行が 1 つも見つからなければ `None`（＝呼び出し側はフォールバックする）。
    見つかった場合は、各ヘッダーに対応する本文（複数あれば複数件）を list で返す。
    本文が空（次行が空行 / コードフェンス終端 / 次ヘッダー / EOF）のブロックは `""` として含める
    （「ブロックはあるが claim はゼロ件」を明示的に表す。フォールバックとは区別する）。
    各ブロックの終端は「空行」「コードフェンス終端（```）」「次の `CHANGED_FILES:` ヘッダー行」の
    いずれか（先に来たもの）。これによりブロック前後の空行・インデント・コードフェンス内配置を
    素通しできる（大文字小文字はヘッダー正規表現側で吸収）。

    複数ヘッダーを 1 つしか採用しない旧実装は、① 複数役の完了報告を連結して 1 回の `--stdin` に
    流す運用（`agent-team-summary.md` が「全サブエージェントの完了報告を受け取ったら実行する」と
    定めている）、② 委譲プロンプト中の書式例をサブエージェントが引用してから本題を書く運用の
    どちらでも、最初の 1 ブロック以外を握りつぶし `missing_from_report`（報告漏れ・より重い警告）
    を誤検出させていた（PR #723 レビュー指摘2）。本関数は全ブロックを収集し、呼び出し側で
    和集合を取ることでこれを解消する。
    """
    lines = text.split("\n")
    header_indices = [i for i, line in enumerate(lines) if _CHANGED_FILES_HEADER_LINE_RE.match(line)]
    if not header_indices:
        return None
    blocks: list[str] = []
    for header_idx in header_indices:
        body: list[str] = []
        for line in lines[header_idx + 1 :]:
            if line.strip() == "":
                break
            if line.strip().startswith("```"):
                break
            if _CHANGED_FILES_HEADER_LINE_RE.match(line):
                break
            body.append(line)
        blocks.append("\n".join(body))
    return blocks


def extract_claimed_paths(text: str, max_fallback_chars: int | None = None) -> tuple[set[str], bool]:
    """完了報告テキストから claim されたパス集合を抽出する。

    戻り値は `(パス集合, 明示ブロックを使ったか)`。

    - 明示ブロック（`CHANGED_FILES:` ヘッダー以降の行）が **ある** 場合: 全ブロックの
      内容の **和集合** を走査する（PR #723 指摘2）。ブロック外の本文（否定文脈の言及等）は
      一切見ないため、「テキスト中の言及＝claim」という旧方式の fail-open（課題1・#717）が
      構造的に起きない。ヘッダーが複数見つかった場合は連結報告 or 引用の疑いを stderr に
      警告する（呼び出し側が判断できるよう握りつぶさない）。**ヘッダー検索は `max_fallback_chars`
      を無視して常に全文に対して行う**（指摘1・PR #723）: ヘッダー正規表現は行アンカーの単純な
      照合でカタストロフィックバックトラックしないため、切り詰めより先に全文を検索してもコスト
      問題は生じない。切り詰めるとヘッダーが切り詰め位置より後ろにある報告でブロックごと
      消えてしまう（実測: 240,043 文字・末尾に正当なブロックを持つ入力で claimed が消失していた）。
    - 明示ブロックが **無い** 場合: 従来どおり全文をヒューリスティックスキャンする
      （後方互換フォールバック）。`max_fallback_chars` を指定した場合は **この経路でのみ**
      走査対象を先頭 `max_fallback_chars` 文字に切り詰める（課題2・#717 の安全弁はフォールバック
      経路にのみ適用し、明示ブロック経路には適用しない。ブロック本文は `_tokens_from_text` 内で
      既にトークン単位で頭打ちされるため追加の切り詰めは不要）。呼び出し側は `used_block=False`
      を見て、フォールバックした事実をユーザー / ログに明示すること（黙って劣化させない）。

    バージョン番号（"2.1.198" や "v2.1.198"）は拡張子相当の末尾セグメントが数字のみ
    （`ext.isdigit()`）になるため `_tokens_from_text` 内で除外される。URL は事前に除去する。
    """
    blocks = _find_changed_files_blocks(text)
    if blocks is not None:
        if len(blocks) > 1:
            print(
                f"⚠️  CHANGED_FILES: ヘッダーが{len(blocks)}件検出されました。"
                "全ブロックの和集合を claim として扱います"
                "（複数役の完了報告の連結、または委譲プロンプト中の書式例の引用が疑われます・PR #723 指摘2）",
                file=sys.stderr,
            )
        claimed: set[str] = set()
        for block in blocks:
            claimed |= _tokens_from_text(_URL_RE.sub(" ", block))
        return claimed, True
    fallback_text = text
    if max_fallback_chars is not None and len(text) > max_fallback_chars:
        fallback_text = text[:max_fallback_chars]
    return _tokens_from_text(_URL_RE.sub(" ", fallback_text)), False


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
    """git を実行し stdout を返す。失敗時は RuntimeError を送出する。

    #195: git 実行 + エラーハンドリング部分は `tools/git_diff_utils.py` の
    `run_git_or_raise()` に統合済み（本ツールは作業ツリーの実差分のみ・`RuntimeError` 送出という
    性質が他 3 ツールと違うため、収集ロジック本体は統合せずここに残す）。**検証の分担**
    （#195 指摘5）: 例外型・メッセージ書式そのものは `git_diff_utils.py --self-test`
    （`_self_test_run_git_or_raise`）が検証済みで変えていない。本ツールの `--self-test`
    （`_self_test_get_real_diff_files_wiring`）は `run_git()` → `git_diff_utils.run_git_or_raise()`
    への配線（`args` / `cwd` の引数順）が壊れていないかを検証する。
    """
    return git_diff_utils.run_git_or_raise(args, cwd)


def parse_status_short(output: str) -> set[str]:
    """`git status --short` 出力からファイルパスを抽出する（リネームは新パスを採用）。

    Issue #948 / #968: claim 側（`_tokens_from_text`）と同じ `git_diff_utils.normalize_leading_dots()`
    を通す。`git status --short` は通常 `./` `../` プレフィックス無しでパスを返すため実害は無いが、
    「claim 側と実 diff 側が同じ正規化関数を通る」構造を自己テストで固定するため実 diff 側にも
    明示的に適用する（片側だけ正規化される非対称性そのものが再発要因だったため・#948）。
    """
    files: set[str] = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) > 3 else line.strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        rest = git_diff_utils.normalize_leading_dots(rest)
        if rest:
            files.add(rest)
    return files


def get_real_diff_files(root: Path, *, runner=subprocess.run) -> dict:  # noqa: ANN001
    """作業ツリーの実差分ファイル一覧を集める。

    Issue #880: 従来は `git diff --stat` / `git diff --cached --stat`（`run_git()` →
    `git_diff_utils.run_git_or_raise()` 経由）を `parse_diff_stat()` でパース（`"|"` の左だけ
    使い、変更行数・記号列は一切使っていなかった）していたが、この経路には 2 つの偽陽性源が
    あった: ① 幅指定（`--stat=<width>,<name-width>`）をしても `.../` 省略が起こりうる（#850）
    ② `run_git_or_raise()` は `-c core.quotePath=false` を注入しないため、日本語ファイル名が
    `"docs/\\346\\227\\245..."` の形にエスケープされたまま返り、報告側の生パスと一致しなくなる。
    `parse_diff_stat()` が使っていたのはパス文字列だけだったため、`git diff --name-only -z`
    （`git_diff_utils.run_git_paths_or_raise()`。内部で `-c core.quotePath=false` を注入し
    `-z` で NUL 区切りに分割する）へ置き換えることで両方の経路を発生源で解消した
    （`parse_diff_stat()` / `_stat_arg()` / `STAT_WIDTH` は本置き換えにより不要になったため削除）。

    `git status --short` は untracked ファイルの検出に必要なため `run_git()`
    （= `git_diff_utils.run_git_or_raise()`。quotePath は注入されない残存差だが、本 Issue の
    対象範囲は `git diff --stat` 由来の 3 経路であり `git status --short` は対象外）経由のまま残す。

    diff / cached 側の各パスにも `git_diff_utils.normalize_leading_dots()` を適用する
    （claim 側の `_tokens_from_text` と実 diff 側の `parse_status_short` が既に通っているのと
    同じ正規化関数。`--name-only` は通常 `./` `../` プレフィックスを付けないため実害は薄いが、
    「実 diff 側の全ソースが同じ正規化関数を通る」構造を崩さないため明示的に適用する・#948）。

    `normalize_abbreviated_paths()`（#850 の二次対策）はそれでも呼び続ける。`--name-only` は
    理論上 `.../` 省略を起こさないが、この指定が効かない git 実装・想定外の入力への保険として
    多層防御を維持する（実際には省略パスが集合に入らないため、通常は無処理で完了する）。

    `runner` は `git_diff_utils.run_git_paths_or_raise()`（diff / cached の取得）と
    `normalize_abbreviated_paths()`（`.../` 解決のために呼ぶ `git ls-files`）の双方へ転送される
    （self-test で実 git に依存せず検証するための差し替え口）。`run_git()`（`git status --short`）
    には効かない。そちらを差し替えるには `git_diff_utils.run_git_or_raise` そのものを置換する。
    """
    status_out = run_git(["status", "--short"], root)
    diff_paths = git_diff_utils.run_git_paths_or_raise(["diff", "--name-only", "-z"], root, runner=runner)
    cached_paths = git_diff_utils.run_git_paths_or_raise(
        ["diff", "--cached", "--name-only", "-z"], root, runner=runner
    )
    files: set[str] = set()
    files |= parse_status_short(status_out)
    files |= {git_diff_utils.normalize_leading_dots(p) for p in diff_paths if p}
    files |= {git_diff_utils.normalize_leading_dots(p) for p in cached_paths if p}
    # Issue #850: `.../` 省略パスと完全パスが同じ集合に混ざると同一ファイルが 2 件に数えられ、
    # 片方が `missing_from_report`（報告漏れ＝より重い警告）へ落ちて偽陽性になる。`--name-only`
    # は原則これを起こさないが、多層防御として集合比較の前段で解決する（上記 docstring 参照）。
    files, unresolved = git_diff_utils.normalize_abbreviated_paths(
        files, repo_root=root, runner=runner
    )
    return {
        "files": files,
        "unresolved": unresolved,
        "raw": {"status": status_out, "diff_name_only": diff_paths, "diff_cached_name_only": cached_paths},
    }


def compare(
    claimed: set[str],
    real: set[str],
    unresolved: set[str] | None = None,
) -> dict:
    """報告と実 diff を突き合わせる。

    `unresolved`（Issue #850）は「`.../` 省略パスを一意に解決できなかった」もの。
    どの実ファイルを指すか確定できない以上、報告漏れとも虚偽報告とも判定できないため
    **`mismatch` には混ぜず**、警告として報告だけする（黙って捨てない）。

    ただし「`mismatch` に混ぜない」ことと「`0`（合格）で終わる」ことは別問題である。
    残った `unresolved` は「報告漏れかもしれないが確定できない」状態であり、`main()` は
    これを `2`（判定不能）で返す（`docs/rules/check-tool-design-rules.md` §1 / §3 の
    fail-closed 既定。`0` に丸めると exit code だけを見る呼び出し元へ報告漏れが届かない）。
    """
    missing_from_diff = sorted(claimed - real)
    missing_from_report = sorted(real - claimed)
    return {
        "claimed": sorted(claimed),
        "real": sorted(real),
        "missing_from_diff": missing_from_diff,
        "missing_from_report": missing_from_report,
        "unresolved": sorted(unresolved or set()),
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
    if result.get("unresolved"):
        print("⚠️  判定不能: 省略パス（.../）を一意に解決できず、実 diff の一部を検証できませんでした（exit 2・fail-closed）:")
        for f in result["unresolved"]:
            print(f"    - {f}")
    if not result["mismatch"] and not result.get("unresolved"):
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

    # ── Issue #948: `.github/workflows/x.yml` のような先頭ドット付きパスの偽陽性 ─────────
    # 原因: `tok.lstrip("./")` が文字集合として "." "/" を解釈し、`.github/workflows/x.yml` の
    # 先頭 "." まで食い荒らして `github/workflows/x.yml` に化けていた。claim 側・実 diff 側の
    # 双方で正規化した結果が一致し mismatch=False になることを end-to-end（compare まで）で見る。

    # バリアント1: 明示ブロック（CHANGED_FILES:）経路
    dotpath_block_report = "CHANGED_FILES:\n.github/workflows/x.yml\n.claude/hooks/y.sh\n"
    got_dotpath_block, used_dotpath_block = extract_claimed_paths(dotpath_block_report)
    check(
        "明示ブロック経路: 先頭ドット付きパスの '.' を消さずに抽出する（#948）",
        got_dotpath_block == {".github/workflows/x.yml", ".claude/hooks/y.sh"} and used_dotpath_block is True,
        str((got_dotpath_block, used_dotpath_block)),
    )
    r_dotpath_block = compare(
        got_dotpath_block,
        parse_status_short(" M .github/workflows/x.yml\n M .claude/hooks/y.sh\n"),
    )
    check(
        "明示ブロック経路 end-to-end: 先頭ドット付きパスで mismatch=False（#948 完了条件）",
        r_dotpath_block["mismatch"] is False,
        str(r_dotpath_block),
    )

    # バリアント2: フォールバック（全文ヒューリスティックスキャン）経路。明示ブロックが無いことを
    # 確認したうえで（`used3 is False` 相当）、同じ先頭ドット付きパスが同様に抽出できること。
    dotpath_fallback_report = (
        "変更ファイル: `.github/workflows/x.yml` と `.claude/hooks/y.sh` を更新しました。\n"
    )
    got_dotpath_fallback, used_dotpath_fallback = extract_claimed_paths(dotpath_fallback_report)
    check(
        "フォールバック経路: 先頭ドット付きパスの '.' を消さずに抽出する（#948）",
        got_dotpath_fallback == {".github/workflows/x.yml", ".claude/hooks/y.sh"}
        and used_dotpath_fallback is False,
        str((got_dotpath_fallback, used_dotpath_fallback)),
    )
    r_dotpath_fallback = compare(
        got_dotpath_fallback,
        {".github/workflows/x.yml", ".claude/hooks/y.sh"},
    )
    check(
        "フォールバック経路 end-to-end: 先頭ドット付きパスで mismatch=False（#948 完了条件）",
        r_dotpath_fallback["mismatch"] is False,
        str(r_dotpath_fallback),
    )

    # バリアント3: 症状のバリアント展開（`./x.py`・先頭ドット+`./` 併用・通常 "./" プレフィックス）
    variant_report = "CHANGED_FILES:\n./tools/x.py\n.github/x.yml\n././tools/z.py\n"
    got_variant, _ = extract_claimed_paths(variant_report)
    check(
        "バリアント展開: './x.py'（剥がす）・'.github/x.yml'（無傷）・'././z.py'（1 回だけ剥がす）を同時に正しく扱う（#948）",
        got_variant == {"tools/x.py", ".github/x.yml", "./tools/z.py"},
        str(got_variant),
    )

    # ── Issue #880 4本目の経路: 拡張子を持たない「bare dotfile」（`.gitignore` 等）は
    # 拡張子必須の旧 `_PATH_TOKEN_RE` では一度も抽出されなかった（`re.findall(".gitignore")` が
    # 空リストを返す。パターンが「本体 + リテラル "." + 拡張子」の 2 ドット構造を要求するため、
    # ドットが 1 個しかない `.gitignore` はそもそもマッチしない）。`.github/workflows/y.yml` の
    # ような「先頭ドット + 拡張子あり」パスは #948 で既に対応済みだが、これは別の未対応経路。
    # 正ケース（bare dotfile を含め先頭ドットを保つ）と負ケース（`./` 前置詞は従来どおり剥がす）を
    # 対で置く。bare dotfile 対応の alternation を外す変異で正ケースが FAIL することを実測する
    # （`docs/rules/sprint-development-rules.md` SD-2 の変異テスト）。
    bare_dotfile_report = "CHANGED_FILES:\n.claude/skills/x.md\n.github/workflows/y.yml\n.gitignore\n./tools/x.py\n"
    got_bare_dotfile, used_bare_dotfile = extract_claimed_paths(bare_dotfile_report)
    check(
        "正ケース: 拡張子を持たない bare dotfile（.gitignore）も含め先頭ドットを保ったまま抽出する"
        "（#880）／負ケース: './tools/x.py' は従来どおり './' 前置詞を剥がす（対で検証）",
        got_bare_dotfile == {".claude/skills/x.md", ".github/workflows/y.yml", ".gitignore", "tools/x.py"}
        and used_bare_dotfile is True,
        str((got_bare_dotfile, used_bare_dotfile)),
    )
    r_bare_dotfile = compare(
        got_bare_dotfile,
        {".claude/skills/x.md", ".github/workflows/y.yml", ".gitignore", "tools/x.py"},
    )
    check(
        "上記 end-to-end: 実 diff 側と一致し mismatch=False（#880）",
        r_bare_dotfile["mismatch"] is False,
        str(r_bare_dotfile),
    )

    # 境界の外側の負ケース（#750 / Layer 1 セルフレビュー指摘）: bare dotfile の alternation を
    # 広げすぎると、自由記述に出てくる `.NET` のような **ファイルではない先頭ドット語** まで
    # claim へ混入し、`missing_from_diff` 経由で exit 1（偽陽性 FAIL）になる。正ケース（実在の
    # dotfile を拾う）と対で置き、alternation を `[A-Za-z0-9_-]` へ戻す変異で FAIL させる。
    got_tech_name = _tokens_from_text(".NET Core で実装した。.gitignore も更新した。")
    check(
        "負ケース: '.NET' のような非ファイルの先頭ドット語を claim に含めない"
        "／正ケース: 同じ文の '.gitignore' は拾う（対で検証・#880）",
        ".NET" not in got_tech_name and ".gitignore" in got_tech_name,
        str(got_tech_name),
    )

    # ── Issue #880 経路 1: **報告側（claimed）** に `.../` 省略パスが来るケース。
    # 実 diff の収集を `--name-only -z` へ寄せても、サブエージェントが自分で `git diff --stat` を
    # 叩いて出力をコピーすれば報告テキスト側に省略が入る（収集方法の変更では消えない別経路）。
    # `main()` が claimed 側にも `normalize_abbreviated_paths()` を適用することで解決する。
    # 正ケース（実 diff の完全パスで一意に解決 → mismatch=False）と負ケース（候補が 2 件あり
    # 一意に定まらない → mismatch には混ぜず unresolved へ）を対で置く。
    claimed_abbrev = {".../infrastructure/cloudflare-infrastructure.md"}
    real_for_abbrev = {"docs/03_design/infrastructure/cloudflare-infrastructure.md"}
    resolved_claimed, claimed_unresolved = git_diff_utils.normalize_abbreviated_paths(
        claimed_abbrev, extra_candidates=real_for_abbrev
    )
    r_abbrev = compare(resolved_claimed, real_for_abbrev, claimed_unresolved)
    check(
        "正ケース: 報告側の '.../' 省略パスを実 diff の完全パスで解決し mismatch=False（#880 経路1）",
        r_abbrev["mismatch"] is False and not r_abbrev["unresolved"],
        str(r_abbrev),
    )
    ambiguous_real = {"a/infrastructure/x.md", "b/infrastructure/x.md"}
    resolved_amb, amb_unresolved = git_diff_utils.normalize_abbreviated_paths(
        {".../infrastructure/x.md"}, extra_candidates=ambiguous_real
    )
    r_amb = compare(resolved_amb, ambiguous_real, amb_unresolved)
    check(
        "負ケース: 候補が 2 件で一意に定まらない省略パスは missing_from_diff（虚偽報告の疑い）に"
        "落とさず unresolved に積む（#880 経路1・fail-closed の誤検知を作らない）",
        r_amb["unresolved"] == [".../infrastructure/x.md"]
        and ".../infrastructure/x.md" not in r_amb["missing_from_diff"],
        str(r_amb),
    )

    # 共通正規化関数への配線検証: claim 側（_tokens_from_text 経由）と実 diff 側
    # （parse_status_short・get_real_diff_files() の diff / diff --cached 経由）が同一の
    # `git_diff_utils.normalize_leading_dots` を通ることを、差し替えで呼び出し回数を記録して
    # 確認する（片側だけ直す再発を防ぐ・#948）。Issue #880: 実 diff 側は `parse_diff_stat()`
    # 廃止に伴い `get_real_diff_files()` 経由（`--name-only` の戻り値へ直接適用）へ経路が変わった
    # ため、`get_real_diff_files()` 自体をエンドツーエンドで呼んで検証する
    # （干渉検証: get_real_diff_files() が --name-only 経路へ切り替わった後も、共通正規化関数への
    # 配線が claim 側・status 側・diff/cached 側すべてで維持されていることを見る）。
    _dotslash_calls: list[str] = []
    _orig_normalize_leading_dots = git_diff_utils.normalize_leading_dots

    def _recording_normalize_leading_dots(path: str) -> str:
        _dotslash_calls.append(path)
        return _orig_normalize_leading_dots(path)

    def _fake_status_for_normalize_wiring(args, cwd, *, runner=None):  # noqa: ANN001, ARG001
        if args == ["status", "--short"]:
            return " M .github/workflows/x.yml\n"
        return ""

    def _fake_diff_paths_for_normalize_wiring(args, cwd, *, runner=None):  # noqa: ANN001, ARG001
        if args == ["diff", "--name-only", "-z"]:
            return ["./tools/normalize_wiring_diff.py"]
        if args == ["diff", "--cached", "--name-only", "-z"]:
            return ["./tools/normalize_wiring_cached.py"]
        return []

    _orig_run_git_or_raise_nw = git_diff_utils.run_git_or_raise
    _orig_run_git_paths_or_raise_nw = git_diff_utils.run_git_paths_or_raise
    git_diff_utils.normalize_leading_dots = _recording_normalize_leading_dots
    git_diff_utils.run_git_or_raise = _fake_status_for_normalize_wiring
    git_diff_utils.run_git_paths_or_raise = _fake_diff_paths_for_normalize_wiring
    try:
        _tokens_from_text(".github/workflows/x.yml を変更した")
        normalize_wiring_result = get_real_diff_files(Path("/fake/normalize-wiring/root"))
    finally:
        git_diff_utils.normalize_leading_dots = _orig_normalize_leading_dots
        git_diff_utils.run_git_or_raise = _orig_run_git_or_raise_nw
        git_diff_utils.run_git_paths_or_raise = _orig_run_git_paths_or_raise_nw
    check(
        "claim 側（_tokens_from_text）と実 diff 側（get_real_diff_files() の status/diff/diff --cached "
        "全ソース）が共通正規化関数 git_diff_utils.normalize_leading_dots を通る（#948 / #880）",
        len(_dotslash_calls) == 4
        and normalize_wiring_result["files"]
        == {
            ".github/workflows/x.yml",
            "tools/normalize_wiring_diff.py",
            "tools/normalize_wiring_cached.py",
        },
        f"calls={_dotslash_calls} files={normalize_wiring_result['files']}",
    )

    # ── #968 指摘2（#750 境界の外側の負ケース）: '../'（相対パス）・'...'（三点リーダー融合）を
    # 正規化しつつ '.../'（ABBREV_PREFIX・省略記法）は絶対に無傷で残すこと。end-to-end（compare
    # まで）で mismatch=False になることを見る（CRITICAL 指摘1 の再現ケースそのもの）。
    neg_case_text = "CHANGED_FILES:\n../bin/tool.sh\n...utils.py\n.../tools/x.py\n"
    got_neg_case, used_neg_case = extract_claimed_paths(neg_case_text)
    check(
        "#968 負ケース: '../bin/tool.sh'→'bin/tool.sh'・'...utils.py'→'utils.py' に正規化しつつ、"
        "'.../tools/x.py'（ABBREV_PREFIX）は無傷で残す（#750 境界の外側）",
        got_neg_case == {"bin/tool.sh", "utils.py", ".../tools/x.py"} and used_neg_case is True,
        str((got_neg_case, used_neg_case)),
    )
    r_neg_case = compare(got_neg_case, {"bin/tool.sh", "utils.py", ".../tools/x.py"})
    check(
        "#968 負ケース end-to-end: 正規化後の claim が実 diff 側の表記と一致し mismatch=False",
        r_neg_case["mismatch"] is False,
        str(r_neg_case),
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

    # ── NIT（#968）: `_MAX_TOKEN_CHARS` の頭打ちが実際に効いていることを固定する ──
    # 上の性能テストは「速いこと」しか見ておらず、`_MAX_TOKEN_CHARS` を将来緩める・削除する
    # 変更が入っても（性能が別の要因で保たれていれば）気づかない。ここでは 500 文字を大きく
    # 超える連続ドットトークンが 1 秒未満で処理されることに加え、頭打ちによって末尾の
    # "x.py" が切り捨てられ抽出結果が空集合になること自体もあわせて固定する
    # （結果まで固定することで、`_MAX_TOKEN_CHARS` を大幅に緩める・削除する変異を確実に検知する）。
    _dot_heavy_token = "." * 5000 + "x.py"  # 空白区切りなし・"." が大量に連続する単一トークン
    _t0 = _time.perf_counter()
    _got_dot_perf, _ = extract_claimed_paths(f"CHANGED_FILES:\n{_dot_heavy_token}\n")
    _elapsed_dot_perf = _time.perf_counter() - _t0
    check(
        f"NIT: 500文字超の連続ドットトークンが _MAX_TOKEN_CHARS 頭打ちで1秒未満・"
        f"末尾 'x.py' が切り捨てられ結果が空集合になる（実測 {_elapsed_dot_perf:.3f}s・#968）",
        _elapsed_dot_perf < 1.0 and _got_dot_perf == set(),
        f"{_elapsed_dot_perf:.3f}s / 抽出結果={_got_dot_perf}",
    )

    # ── PR #723 指摘1: ヘッダーが切り詰め位置（MAX_STDIN_CHARS）より後ろにある報告でも
    # ブロックが消えないこと（実測: 240,043 文字・末尾に正当なブロックを持つ入力で
    # claimed が消失していた不具合の再現ケース）
    late_block_text = ("報告本文の水増しです。" * 20000) + "\nCHANGED_FILES:\ntools/late_block_marker.py\n"
    assert len(late_block_text) > MAX_STDIN_CHARS, "テスト前提: 総文字数が MAX_STDIN_CHARS を超えていること"
    _t0 = _time.perf_counter()
    got_late, used_late = extract_claimed_paths(late_block_text, max_fallback_chars=MAX_STDIN_CHARS)
    _elapsed_late = _time.perf_counter() - _t0
    check(
        f"指摘1: 切り詰め位置({MAX_STDIN_CHARS}文字)より後ろのブロックも検出する・1秒未満（実測{_elapsed_late:.3f}s・PR #723）",
        got_late == {"tools/late_block_marker.py"} and used_late is True and _elapsed_late < 1.0,
        f"len={len(late_block_text)} / {(got_late, used_late)} / {_elapsed_late:.3f}s",
    )

    # ── PR #723 指摘2: 複数 CHANGED_FILES ブロックの和集合（複数役の報告を連結する運用）──
    concat_text = (
        "役A の完了報告です。\n"
        "CHANGED_FILES:\n"
        "tools/role_a_file.py\n"
        "\n"
        "役B の完了報告です。\n"
        "CHANGED_FILES:\n"
        "tools/role_b_file.py\n"
    )
    got_concat, used_concat = extract_claimed_paths(concat_text)
    check(
        "指摘2: 連結された複数ブロックの和集合を claim とする（PR #723）",
        got_concat == {"tools/role_a_file.py", "tools/role_b_file.py"} and used_concat is True,
        str((got_concat, used_concat)),
    )
    r_concat = compare(got_concat, {"tools/role_a_file.py", "tools/role_b_file.py"})
    check(
        "指摘2: 連結報告 end-to-end で missing_from_report が誤検出されない（PR #723）",
        r_concat["mismatch"] is False,
        str(r_concat),
    )

    # ── PR #723 指摘2: 委譲プロンプトの書式例を引用してから本題を書くケース ──
    # 引用された例のパスは実 diff に無いので missing_from_diff（軽い警告）側にだけ出る。
    # 本物のパスは union に含まれるため missing_from_report（報告漏れ・重い警告）は誤検出されない。
    quoted_example_text = (
        "書式例として以下を参考にしました:\n"
        "CHANGED_FILES:\n"
        "tools/example_from_prompt.py\n"
        "docs/rules/agent-team-summary.md\n"
        "\n"
        "実際に変更したのは次のとおりです。\n"
        "CHANGED_FILES:\n"
        "tools/real_change.py\n"
    )
    got_quoted, used_quoted = extract_claimed_paths(quoted_example_text)
    r_quoted = compare(got_quoted, {"tools/real_change.py"})
    check(
        "指摘2: 引用例のパスは missing_from_diff 側のみ・本物パスの報告漏れは誤検出されない（PR #723）",
        r_quoted["missing_from_report"] == []
        and set(r_quoted["missing_from_diff"]) == {"tools/example_from_prompt.py", "docs/rules/agent-team-summary.md"}
        and used_quoted is True,
        str((r_quoted, used_quoted)),
    )

    # 入力バリアント: 空ブロック + 実ブロックの併存（和集合は空でない側だけ反映される）
    empty_plus_real_text = "CHANGED_FILES:\n\n何もしていません。\nCHANGED_FILES:\ntools/real_after_empty.py\n"
    got_ep, used_ep = extract_claimed_paths(empty_plus_real_text)
    check(
        "バリアント: 空ブロック + 実ブロックの併存で実ブロックのみ claim に入る（PR #723）",
        got_ep == {"tools/real_after_empty.py"} and used_ep is True,
        str((got_ep, used_ep)),
    )

    # 指摘2: 複数ヘッダー検出時のみ stderr 警告が出ること（単一ヘッダーでは出ない）
    import contextlib as _contextlib
    import io as _io

    _stderr_multi = _io.StringIO()
    with _contextlib.redirect_stderr(_stderr_multi):
        extract_claimed_paths(concat_text)
    check(
        "指摘2: 複数ヘッダー検出時に stderr へ警告する（PR #723）",
        "ヘッダーが2件検出されました" in _stderr_multi.getvalue(),
        _stderr_multi.getvalue(),
    )

    _stderr_single = _io.StringIO()
    with _contextlib.redirect_stderr(_stderr_single):
        extract_claimed_paths("CHANGED_FILES:\ntools/a.py\n")
    check(
        "指摘2: 単一ヘッダーでは複数ヘッダー警告を出さない（PR #723）",
        "ヘッダーが" not in _stderr_single.getvalue(),
        _stderr_single.getvalue(),
    )

    # ── PR #723 指摘4: main() の切り詰め分岐をエントリポイントから実際に貫通させる ──
    def _run_main(stdin_text: str) -> tuple[int, str, str]:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--stdin", "--json"],
            input=stdin_text,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=30,
        )
        return proc.returncode, proc.stdout, proc.stderr

    # A: ヘッダーが MAX_STDIN_CHARS より後ろにある報告 → main() 経由でも claim に残ること
    _late_stdin = ("水増し行です。" * 35000) + "\nCHANGED_FILES:\ntools/main_late_block_marker.py\n"
    assert len(_late_stdin) > MAX_STDIN_CHARS
    _t0 = _time.perf_counter()
    _rc_a, _out_a, _err_a = _run_main(_late_stdin)
    _elapsed_a = _time.perf_counter() - _t0
    try:
        _json_a = json.loads(_out_a)
    except json.JSONDecodeError:
        _json_a = {}
    check(
        f"指摘4: main() 経由でも切り詰め位置より後ろのブロックが claim に残る（実測{_elapsed_a:.3f}s・PR #723）",
        "tools/main_late_block_marker.py" in _json_a.get("claimed", [])
        and _json_a.get("fallback_used") is False
        and _elapsed_a < 5.0,
        f"rc={_rc_a} stdout={_out_a[:300]!r} stderr={_err_a[:300]!r}",
    )

    # B: ヘッダーが一切無い巨大入力 → フォールバック経路の切り詰め警告が stderr に出ること
    _fallback_stdin = "x" * 250_000
    _rc_b, _out_b, _err_b = _run_main(_fallback_stdin)
    try:
        _json_b = json.loads(_out_b)
    except json.JSONDecodeError:
        _json_b = {}
    check(
        "指摘4: 明示ブロックが無い巨大入力は main() 経由でも切り詰め警告が出てフォールバックする（PR #723）",
        _json_b.get("fallback_used") is True and "切り詰めました" in _err_b,
        f"rc={_rc_b} stdout={_out_b[:300]!r} stderr={_err_b[:300]!r}",
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

    # ── #195 指摘3 / #880: get_real_diff_files() → run_git()/run_git_paths_or_raise()
    # への配線が壊れていないことを確認する（引数順の入れ替え・--stat への先祖返り等の回帰を検知）──
    # `run_self_test()` は `run_git()`/`get_real_diff_files()` を一度も呼ばないため、
    # 配線ミス（引数順の入れ替え等）を検知できない、という指摘への対応。
    _wiring_status_calls: list[tuple[list[str], object]] = []
    _wiring_paths_calls: list[tuple[list[str], object]] = []

    def _fake_run_git_or_raise(args, cwd, *, runner=None):  # noqa: ANN001, ARG001
        # git_diff_utils.run_git_or_raise の呼び出しシグネチャ（args, cwd）をそのまま模す。
        _wiring_status_calls.append((args, cwd))
        if args == ["status", "--short"]:
            return " M tools/wiring_marker_status.py\n"
        return ""

    def _fake_run_git_paths_or_raise(args, cwd, *, runner=None):  # noqa: ANN001, ARG001
        # git_diff_utils.run_git_paths_or_raise の呼び出しシグネチャ（args, cwd）をそのまま模す。
        # 呼び出し側で args/cwd が入れ替わっていれば、ここで受け取る args は
        # list[str] ではなく Path になり、下の分岐が一致せず assertion で検出できる。
        _wiring_paths_calls.append((args, cwd))
        if args == ["diff", "--name-only", "-z"]:
            return ["tools/wiring_marker_diff.py"]
        if args == ["diff", "--cached", "--name-only", "-z"]:
            return ["tools/wiring_marker_cached.py"]
        return []

    _orig_run_git_or_raise = git_diff_utils.run_git_or_raise
    _orig_run_git_paths_or_raise = git_diff_utils.run_git_paths_or_raise
    git_diff_utils.run_git_or_raise = _fake_run_git_or_raise
    git_diff_utils.run_git_paths_or_raise = _fake_run_git_paths_or_raise
    try:
        fake_root = Path("/fake/wiring/root")
        wiring_result = get_real_diff_files(fake_root)
    finally:
        git_diff_utils.run_git_or_raise = _orig_run_git_or_raise
        git_diff_utils.run_git_paths_or_raise = _orig_run_git_paths_or_raise

    check(
        "get_real_diff_files() 配線: status は run_git_or_raise・diff/cached は "
        "run_git_paths_or_raise(['diff','--name-only','-z'] 系) を正しい引数・順で呼ぶ（#195 指摘3 / #880）",
        wiring_result["files"]
        == {"tools/wiring_marker_status.py", "tools/wiring_marker_diff.py", "tools/wiring_marker_cached.py"}
        and _wiring_status_calls == [(["status", "--short"], fake_root)]
        and _wiring_paths_calls
        == [
            (["diff", "--name-only", "-z"], fake_root),
            (["diff", "--cached", "--name-only", "-z"], fake_root),
        ],
        f"result={wiring_result} status_calls={_wiring_status_calls} paths_calls={_wiring_paths_calls}",
    )

    # #880: `--stat` へ先祖返りする変異（`--name-only` を落とす・`-z` を落とす等）を検知するため、
    # get_real_diff_files() が実際に呼ぶ引数の書式そのものを固定する（#850 一次対策の後継）。
    check(
        "get_real_diff_files() が --name-only -z で diff/diff --cached を取得している"
        "（.../ 省略・quotePath 未注入の発生源を絶つ・#850 / #880）",
        all("--stat" not in a for a, _ in _wiring_paths_calls)
        and all("--name-only" in a and "-z" in a for a, _ in _wiring_paths_calls),
        f"paths_calls={_wiring_paths_calls}",
    )

    # ── #850 二次対策（多層防御）: `--name-only` は原理的に `.../` 省略を起こさないが、
    # この指定が効かない git 実装・想定外の入力を食わせた場合の受け皿として
    # `normalize_abbreviated_paths()` を経由し続けていることを end-to-end で確認する
    # （get_real_diff_files() の docstring 参照）。実際の git は --name-only で省略しないが、
    # 受け取り側の多層防御が機能し続けていることをテストダブルで模す。──
    _full = "docs/03_design/infrastructure/cloudflare-infrastructure.md"

    def _fake_abbrev_run_git_paths_or_raise(args, cwd, *, runner=None):  # noqa: ANN001, ARG001
        if args == ["diff", "--name-only", "-z"]:
            return [".../infrastructure/cloudflare-infrastructure.md", _full]
        return []

    def _no_ls_files_runner(args, **kwargs):  # noqa: ANN001, ANN003
        # `git ls-files` は空を返す（解決は集合内の完全パスだけで足りることを示す）
        class _R:
            stdout = ""
            returncode = 0

        return _R()

    git_diff_utils.run_git_or_raise = _fake_run_git_or_raise
    git_diff_utils.run_git_paths_or_raise = _fake_abbrev_run_git_paths_or_raise
    try:
        abbrev_real = get_real_diff_files(Path("/fake/abbrev/root"), runner=_no_ls_files_runner)
    finally:
        git_diff_utils.run_git_or_raise = _orig_run_git_or_raise
        git_diff_utils.run_git_paths_or_raise = _orig_run_git_paths_or_raise

    r_abbrev = compare(
        {_full, "tools/wiring_marker_status.py"}, abbrev_real["files"], abbrev_real.get("unresolved")
    )
    check(
        "#850 二次対策: 省略パスと完全パスの混在が 1 件に畳まれ mismatch を立てない（--name-only 経由後も）",
        abbrev_real["files"] == {_full, "tools/wiring_marker_status.py"}
        and r_abbrev["missing_from_report"] == []
        and r_abbrev["mismatch"] is False,
        f"files={sorted(abbrev_real['files'])} result={r_abbrev}",
    )

    # ── #850: 一意に解決できない省略パスは unresolved として報告され mismatch を立てない ──
    def _fake_unresolvable_run_git_paths_or_raise(args, cwd, *, runner=None):  # noqa: ANN001, ARG001
        if args == ["diff", "--name-only", "-z"]:
            return [".../ghost/never-existed.md"]
        return []

    def _fake_empty_status_run_git_or_raise(args, cwd, *, runner=None):  # noqa: ANN001, ARG001
        return ""

    git_diff_utils.run_git_or_raise = _fake_empty_status_run_git_or_raise
    git_diff_utils.run_git_paths_or_raise = _fake_unresolvable_run_git_paths_or_raise
    try:
        unresolvable_real = get_real_diff_files(Path("/fake/abbrev/root"), runner=_no_ls_files_runner)
    finally:
        git_diff_utils.run_git_or_raise = _orig_run_git_or_raise
        git_diff_utils.run_git_paths_or_raise = _orig_run_git_paths_or_raise

    r_unres = compare(set(), unresolvable_real["files"], unresolvable_real.get("unresolved"))
    check(
        "#850: 解決できない省略パスは unresolved に出て mismatch を立てない（黙って捨てない）",
        unresolvable_real["files"] == set()
        and r_unres["unresolved"] == [".../ghost/never-existed.md"]
        and r_unres["mismatch"] is False,
        f"real={unresolvable_real} result={r_unres}",
    )

    # ── PR #873 Layer 1: CLI の入口（main()）を通した終了コードの回帰テスト ──
    # 内部関数の直呼びテストだけでは「`unresolved` が exit code に反映されず、報告漏れが
    # exit 0 で素通りする」fail-open を検知できない（`sprint-development-rules.md` SD-2 の
    # 完了条件 #686「変異対象に本番の主コードパスを含める・self-test は本番の入口を経由させる」）。
    def _run_main_with(stdin_text: str, fake_real: dict) -> tuple[int, str]:
        _orig_stdin, _orig_argv = sys.stdin, sys.argv
        _orig_get_real = globals()["get_real_diff_files"]
        buf = io.StringIO()
        sys.stdin = io.StringIO(stdin_text)
        sys.argv = ["check_agent_diff_claim.py", "--stdin"]
        globals()["get_real_diff_files"] = lambda *a, **k: fake_real  # noqa: ANN003, ARG005
        try:
            with contextlib.redirect_stdout(buf):
                code = main()
        finally:
            sys.stdin, sys.argv = _orig_stdin, _orig_argv
            globals()["get_real_diff_files"] = _orig_get_real
        return code, buf.getvalue()

    _main_report = "CHANGED_FILES:\ntools/a.py\n"

    _code_ok, _out_ok = _run_main_with(_main_report, {"files": {"tools/a.py"}, "unresolved": set()})
    check(
        "main() 経由: 報告と実 diff が一致 → exit 0",
        _code_ok == 0 and "✅" in _out_ok,
        f"code={_code_ok} out={_out_ok!r}",
    )

    _code_miss, _ = _run_main_with(
        _main_report, {"files": {"tools/a.py", "tools/b.py"}, "unresolved": set()}
    )
    check("main() 経由: 報告漏れ → exit 1", _code_miss == 1, f"code={_code_miss}")

    _code_unres, _out_unres = _run_main_with(
        _main_report,
        {"files": {"tools/a.py"}, "unresolved": {".../ghost/never-existed.md"}},
    )
    check(
        "main() 経由: 解決できない省略パスを 0 に丸めず exit 2（判定不能・fail-closed）",
        _code_unres == 2 and "✅" not in _out_unres,
        f"code={_code_unres} out={_out_unres!r}",
    )

    # ── #968 指摘3: 先頭ドット正規化を main()（CLI 入口）から経由させる ──
    # #948 の先頭ドット系テストは全て `extract_claimed_paths()` / `compare()` の直接呼び出しで、
    # `main()` → stdin → exit code の経路を 1 件も通っていなかった（内部関数だけが正しくても、
    # `main()` 側の配線が壊れれば exit code に反映されない退行を見逃す・#686）。
    _dotpath_main_report = "CHANGED_FILES:\n../bin/tool.sh\n...utils.py\n.../tools/x.py\n"
    _code_dotpath_ok, _out_dotpath_ok = _run_main_with(
        _dotpath_main_report,
        {"files": {"bin/tool.sh", "utils.py", ".../tools/x.py"}, "unresolved": set()},
    )
    check(
        "main() 経由: 先頭ドット正規化（'../' '...' 剥がし・'.../' 保護）が一致して exit 0（#968 指摘3）",
        _code_dotpath_ok == 0 and "✅" in _out_dotpath_ok,
        f"code={_code_dotpath_ok} out={_out_dotpath_ok!r}",
    )

    print(f"\nセルフテスト: {passed} passed, {failed} failed / {passed + failed} cases")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stdin", action="store_true", help="標準入力から完了報告を読み、CHANGED_FILES: 明示ブロック（無ければ全文ヒューリスティック）から変更ファイルを抽出する")
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

    # 指摘1（PR #723）: `extract_claimed_paths` は切り詰めより先に `CHANGED_FILES:` ヘッダーを
    # 常に全文に対して検索する。`max_fallback_chars` は「明示ブロックが見つからなかった場合の
    # ヒューリスティックフォールバック経路」にのみ適用される安全弁（課題2・#717）であり、
    # 明示ブロックが切り詰め位置より後ろにある報告でもブロックごと消えることはない。
    if len(raw_stdin) > MAX_STDIN_CHARS and _find_changed_files_blocks(raw_stdin) is None:
        print(
            f"⚠️  stdin が {len(raw_stdin)} 文字と大きいため先頭 {MAX_STDIN_CHARS} 文字に切り詰めました"
            "（CHANGED_FILES: 明示ブロックが見つからずフォールバック経路のため・課題2・#717）",
            file=sys.stderr,
        )

    claimed, used_block = extract_claimed_paths(raw_stdin, max_fallback_chars=MAX_STDIN_CHARS)
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

    # 🔴 Issue #880 経路 1: **報告側（claimed）** に `.../` 省略パスが来るケース。実 diff の収集を
    # `--name-only -z` へ寄せても、サブエージェントが自分で `git diff --stat` を叩いて出力を
    # コピーすれば報告テキスト側に省略が入りうる（収集方法の変更では消えない別経路）。
    # 実 diff の完全パスを候補に与えて解決し、一意に定まらないものは `unresolved` へ積む
    # （黙って `missing_from_diff`＝虚偽報告の疑い に落とさない・fail-closed の誤検知を防ぐ）。
    claimed, claimed_unresolved = git_diff_utils.normalize_abbreviated_paths(
        claimed, extra_candidates=real["files"], repo_root=REPO_ROOT
    )
    unresolved = set(real.get("unresolved") or set()) | claimed_unresolved
    result = compare(claimed, real["files"], unresolved)
    result["fallback_used"] = not used_block

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    if result["mismatch"]:
        return 1
    if result["unresolved"]:
        # 解決できなかった省略パスは「報告漏れかもしれないが確定できない」状態。0（合格）へ
        # 丸めると、exit code だけを見る呼び出し元には報告漏れが一切届かない（fail-open）。
        # `docs/rules/check-tool-design-rules.md` §1 / §3 の既定どおり 2（判定不能）へ倒す。
        print(
            "⚠️  判定不能: 省略パスを解決できず、実 diff の一部を検証できませんでした（exit 2）",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
