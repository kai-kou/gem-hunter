#!/usr/bin/env python3
"""check_module_contract_drift.py — 共有モジュールの内部実装を変えたとき、利用側に残る説明文の陳腐化を検知する（Issue #762）

## なぜ必要か

PR #761 で `tools/git_diff_utils.py` の `collect_changed_files()` の内部実装を `splitlines()` から
NUL 区切り（`-z` + `core.quotePath=false`）へ変更した。公開 API は不変だったが、利用側の
`tools/scan_dangerous_patterns.py` の docstring が「`collect_changed_files()` は `splitlines()` を
使うため…」と **内部実装を名指しで説明** していたため、その説明が事実と食い違った。
人手レビューが偶然拾っただけで、機械検査は存在しなかった。

利用側に残る「実装の説明」は、公開 API が変わらない限りテストでは絶対に落ちない（説明文だから）。
本ツールはその静かな腐り方を、差分の形から機械的に検知する。

## 判定契約（何をもって drift とみなすか）

索引（`CONTRACT_INDEX`）は「共有モジュール → 利用側ファイル → **その利用側が説明している**
トリガー語」の対応を **明示リスト** として持つ。トリガー語は索引エントリ単位ではなく
**利用側ごと** に割り当てる（エントリ単位の直積にすると、`symbolic-ref` を触っただけで
`splitlines` しか説明していない利用側まで更新を要求され、必ず片方が誤検知になる）。判定は 4 段:

1. 変更ファイル集合（`--changed` の git 差分、または引数で明示指定したパス）に索引の
   **共有モジュール** が含まれているか（パスは完全一致。前方一致で判定しない）
2. （git モードのみ）その共有モジュールの **差分行のうち実装層**（コメント・docstring・
   文字列リテラルだけの行を除いたもの）に **トリガー語** が現れているか（＝内部実装そのものを
   触ったか）。モジュール自身の説明文を直しただけで警告しないための層の切り分け。
   パス明示モードでは差分が取れないため、この段は「触った」とみなす（fail-closed）
3. その語を説明している **利用側ファイル** の説明文（コメント + 文字列リテラル）が
   base 版と比べて **変化しているか**。git モードでは `git show {base}:{consumer}` で旧版を取り、
   `explanatory_text()` を通した文字列を比較する。**「差分に含まれるか」では判定しない**
   （無関係な 1 行を足すだけで検査全体が素通りするため）。パス明示モードでは旧版が取れないため
   「変更集合に含まれていれば更新済み」とみなす
4. 説明文が変化していなければ drift。ただし共有モジュール側・利用側のどちらかに
   **理由付き承認マーカー** `# contract-drift-ok: {読み直した結果と理由}` があれば承認済みとして
   合格にする（理由が空のマーカーは無効）

drift は「説明文が壊れた」ことの証明ではなく、「説明文を読み直すべき差分が来た」ことの通知である。
読み直した結果 **説明が今も正しい** なら、上記の承認マーカーを付ける（理由必須）か、説明文側を
現在の実装に合わせて更新する。説明文そのものが消えたときだけ、索引から利用側を外す。

## 承認マーカー `# contract-drift-ok:`

書式は本リポジトリの既存マーカー（`# dup-ok:` / `# tz-ok` / `# selftest-wiring-ok:` /
`# tool-wiring-ok:`）とそろえる。

    # contract-drift-ok: {読み直した結果と理由}

- **理由が空（`# contract-drift-ok:` だけ）のマーカーは無効**（除外してよいかを人が判断した
  形跡を残させることが目的で、マーカーの存在だけでは通さない）
- 共有モジュール側に書けばその索引エントリの全利用側を、利用側に書けばその 1 本を承認する
- `.py` では **実コメントトークンだけ** を見る（docstring で書式を説明した地の文では発火しない。
  `check_selftest_wiring.py` が踏んだ穴と同型の誤除外を避けるため）

## なぜ全関数名を自動抽出しないか

共有モジュールの公開シンボルを全部拾うと、利用側は必ずどれかを名前で言及しているため、
共有モジュールを触る全 PR が警告になり、警告が無視される（機能しなくなる）。索引は
**内部実装を名指しする語** に限定し、初期セットも小さく始めて実効性を確認してから広げる。

## 索引を Python 内定数で持つ理由

`tools/check_delegation_preamble.py` の `REQUIRED_GROUPS` と同じ形にそろえた。行ごとに
「なぜこの語がトリガーなのか」をコメントで残せること、JSON 外部ファイルにすると
「パース失敗 → 判定不能」の経路が増えるだけで得るものが無いことが理由。

## 使い方

    python3 tools/check_module_contract_drift.py --changed        # git 差分から判定
    python3 tools/check_module_contract_drift.py a.py b.py        # パスを明示指定して判定
    python3 tools/check_module_contract_drift.py --changed --base main   # base range の基準 ref を指定
    python3 tools/check_module_contract_drift.py --changed --json        # 機械可読 JSON で出力
    python3 tools/check_module_contract_drift.py --root /path/to/repo …  # 検査対象のルートを指定
    python3 tools/check_module_contract_drift.py --self-test      # 自己テスト（ネットワーク不要）

`--changed` とパスの明示指定は **併用できない**（併用すると明示分が黙って捨てられ、
「指定したのに何も検査していない」状態が緑で返るため exit 2 にする）。

終了コード（`docs/rules/check-tool-design-rules.md` §1 の標準どおり）:
  0 = 合格（索引の共有モジュールに該当する実装差分が無い、利用側の説明文が更新されている、
      または理由付き承認マーカーで承認済み）
  1 = drift 検出。`tools/run_checks.sh` へ `run_check` で配線しているため **実運用ではブロッキング**
      （緑にならない）。誤検知だと判断したときは承認マーカーで理由付き承認する
  2 = 判定不能（索引が壊れている・索引のファイルが読めない/解析できない・判定対象が未指定・
      `--changed` とパスの併用・明示パスがルート配下に無い・`--base` にオプション様の値・
      git が非ゼロ終了した・base range の基準 ref を解決できない・git 出力が色付きで
      プレフィックス判定が成立しない）
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import git_diff_utils

# subprocess.run 互換 callable（テスト用に差し替える）
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class ConsumerEntry:
    """利用側 1 本。そのファイルが **自分で説明している** トリガー語だけを持つ。"""

    path: str
    triggers: tuple[str, ...]


@dataclass(frozen=True)
class ContractEntry:
    """索引 1 件。共有モジュール 1 本と、その内部実装を説明している利用側ファイル群の対応。"""

    module: str
    consumers: tuple[ConsumerEntry, ...]

    @property
    def triggers(self) -> tuple[str, ...]:
        """全利用側のトリガー語の和集合（順序は登録順・重複除去）。"""
        seen: list[str] = []
        for consumer in self.consumers:
            for trigger in consumer.triggers:
                if trigger not in seen:
                    seen.append(trigger)
        return tuple(seen)


# 索引（明示リスト）。初期セットは共有モジュール 1 本（利用側 3 本・トリガー 4 語）。
# #762 が挙げた残りの利用側は、内部実装を名指しする説明文を持つものだけを実効性確認後に足す
# （公開 API 名 `collect_changed_files()` へ言及しているだけのファイルは対象外。載せると
# `check_index_freshness()` がトリガー語不在で exit 2 を返し、全 PR が赤くなる）。
CONTRACT_INDEX: tuple[ContractEntry, ...] = (
    ContractEntry(
        module="tools/git_diff_utils.py",
        consumers=(
            # collect_changed_files() の分割方式（splitlines → NUL 区切り）を docstring で説明している
            ConsumerEntry(
                path="tools/scan_dangerous_patterns.py",
                triggers=("splitlines", "core.quotePath", "NUL 区切り"),
            ),
            # default_branch() の解決手段（symbolic-ref 解決・main フォールバック）を docstring で説明している
            ConsumerEntry(
                path="tools/check_architecture_boundaries.py",
                triggers=("symbolic-ref",),
            ),
            # 本ツール自身の docstring「なぜ必要か」節が PR #761 の変更内容（splitlines → NUL 区切り・
            # core.quotePath）を、`_run_git()` の docstring が base range 解決（symbolic-ref）を
            # 名指しで説明している。検知しようとしている欠陥を検知ツール自身が抱えないための自己登録
            ConsumerEntry(
                path="tools/check_module_contract_drift.py",
                triggers=("splitlines", "core.quotePath", "NUL 区切り", "symbolic-ref"),
            ),
        ),
    ),
)


# 承認マーカー。理由は同じ行の行末までとする（`\s*` は改行にもマッチするため `[ \t]*` を使う。
# `\s*` のままだと理由が空のとき次行を誤って呑み込む・`check_selftest_wiring.py` と同型）。
_MARKER_RE = re.compile(r"#[ \t]*contract-drift-ok:[ \t]*(.*)$")


class UndecidableError(Exception):
    """判定不能（exit 2）。黙って PASS にしないためのシグナル。"""


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- 索引の健全性


def validate_index(index: Sequence[ContractEntry]) -> str | None:
    """索引そのものの構造を検査する。問題があれば 1 行の説明を返す（無ければ None）。

    「各要素は妥当だが集合として壊れている」入力（同じモジュールの二重登録・同じ利用側の
    重複登録・利用側に自分自身を登録）を弾く（#896 の観点）。索引が空の場合も
    「検査対象の選択が壊れている」として判定不能に倒す（対象 0 件は fail-closed・
    `check-tool-design-rules.md` §2）。
    """
    if not index:
        return "索引が空です（CONTRACT_INDEX に 1 件も登録されていません。索引の選択が意図どおりか確認してください）"

    seen_modules: set[str] = set()
    for entry in index:
        if not entry.module:
            return "module が空の索引エントリがあります"
        if not entry.consumers:
            return f"{entry.module}: consumers が空です（利用側が無い索引エントリは判定不能）"
        if entry.module in seen_modules:
            return f"{entry.module}: 同じ共有モジュールが複数の索引エントリに登録されています"
        seen_modules.add(entry.module)

        seen_consumers: set[str] = set()
        for consumer in entry.consumers:
            if not consumer.path:
                return f"{entry.module}: path が空の利用側エントリがあります"
            if not consumer.triggers:
                return (
                    f"{entry.module}: 利用側 {consumer.path} の triggers が空です"
                    "（トリガー語が無いと何も守らないエントリになります）"
                )
            if consumer.path == entry.module:
                return f"{entry.module}: 利用側に自分自身が登録されています"
            if consumer.path in seen_consumers:
                return f"{entry.module}: 利用側 {consumer.path} が重複登録されています"
            seen_consumers.add(consumer.path)

            seen_triggers: set[str] = set()
            for trigger in consumer.triggers:
                if not trigger.strip():
                    return f"{entry.module}: 利用側 {consumer.path} に空のトリガー語があります"
                if trigger in seen_triggers:
                    return (
                        f"{entry.module}: 利用側 {consumer.path} のトリガー語 {trigger!r} が重複しています"
                    )
                seen_triggers.add(trigger)
    return None


# --------------------------------------------------------------------------- 入出力


def read_text(path: Path) -> str:
    """UTF-8 で読む。読めなければ UndecidableError にして fail-closed にする。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UndecidableError(f"{path}: 非 UTF-8 として読み取れません（{exc}）") from exc
    except OSError as exc:
        raise UndecidableError(f"{path}: 読み取りに失敗しました（{exc}）") from exc


def normalize_path(path: str, *, root: Path, cwd: Path | None = None) -> str:
    """入力パスの表記揺れ（`./foo.py` / cwd 相対 / 絶対パス等）を索引の表記へそろえる。

    先頭ドット系の正規化は共有モジュール `git_diff_utils.normalize_leading_dots()` に委ねる
    （ここで再実装しない）。本関数が足すのは 3 点:

    1. 末尾の余白落とし
    2. **リポジトリルート配下の絶対パスをルート相対へ畳む**（シェル補完で絶対パスを渡すと
       索引と一致せず黙って合格していた）
    3. **cwd 相対のパスを解決してルート相対へ畳む**（`cd tools && python3
       check_module_contract_drift.py git_diff_utils.py` が黙って合格していた・#762 の反例レビュー）。
       cwd 起点で **実在する** ときだけ採用し、実在しなければルート相対の表記として扱う
       （`--root` に別ツリーを渡す self-test で、cwd 起点の解決に引きずられないため）

    ルート外の絶対パスは索引と一致しようがないためそのまま返す（呼び出し側が exit 2 に倒す）。
    """
    text = git_diff_utils.normalize_leading_dots(path.strip())
    if not text:
        return text
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            return str(candidate.resolve().relative_to(root.resolve()))
        except (ValueError, OSError):
            return text
    if cwd is not None:
        try:
            resolved = (Path(cwd) / text).resolve()
            if resolved.exists():
                return str(resolved.relative_to(root.resolve()))
        except (ValueError, OSError):
            pass
    return text


def _py_tokens(path: Path, text: str) -> list[tokenize.TokenInfo]:
    """`.py` をトークナイズする。失敗したら合格へ丸めず `UndecidableError`（exit 2）へ倒す。"""
    try:
        return list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError) as exc:
        raise UndecidableError(
            f"{path}: Python として解析できないため説明文を取り出せません（{exc}）"
        ) from exc


def explanatory_text(path: Path, text: str) -> str:
    """「利用側に残る説明文」だけを取り出す（コメント + 文字列リテラル）。

    索引の鮮度検査（`check_index_freshness()`）でファイル全文を対象にすると、**説明文が消えた
    あとも無関係な実装コード中の同語がエントリを生かし続ける**（実測: `check_architecture_boundaries.py`
    は `symbolic-ref` の説明を消しても、本文の `text.splitlines()` によって索引が生き残る）。
    死んだエントリを検知するという鮮度検査の目的が達成できないため、ここではコメントと
    文字列リテラルだけを見る。

    `.py` 以外（Markdown 等）は全文が説明文なのでそのまま返す。`.py` がトークナイズできない
    ときは合格へ丸めず `UndecidableError`（exit 2）へ倒す。
    """
    if path.suffix != ".py":
        return text
    return "\n".join(
        tok.string
        for tok in _py_tokens(path, text)
        if tok.type in (tokenize.COMMENT, tokenize.STRING)
    )


def explanatory_only_lines(path: Path, text: str) -> frozenset[str]:
    """「その行がコメント / 文字列リテラルだけで出来ている」物理行の集合を返す（strip 済み）。

    共有モジュール側の差分行を **実装層と説明層に切り分ける** ために使う。利用側は
    `explanatory_text()` で説明層に限定しているのに、モジュール側だけ層の区別なく照合すると、
    モジュール自身の docstring を直しただけで「内部実装を変更しています」と事実に反する警告が出る。

    `x = 1  # note` のように 1 行にコード片と説明が同居する行は **実装層** とみなす
    （説明層として扱うと、実装変更を説明層に化けさせて見逃す fail-open になる）。
    `.py` 以外・トークナイズ失敗時は空集合を返す（＝全行を実装層とみなす fail-closed）。
    """
    if path.suffix != ".py":
        return frozenset()
    try:
        tokens = _py_tokens(path, text)
    except UndecidableError:
        return frozenset()

    lines = text.splitlines()
    covered = [bytearray(len(line)) for line in lines]
    for tok in tokens:
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (start_row, start_col), (end_row, end_col) = tok.start, tok.end
        for row in range(start_row, end_row + 1):
            idx = row - 1
            if not (0 <= idx < len(lines)):
                continue
            begin = start_col if row == start_row else 0
            finish = end_col if row == end_row else len(lines[idx])
            for col in range(begin, min(finish, len(covered[idx]))):
                covered[idx][col] = 1

    result: set[str] = set()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if all(covered[idx][col] or line[col].isspace() for col in range(len(line))):
            result.add(stripped)
    return frozenset(result)


def marker_reason(path: Path, text: str) -> tuple[str | None, bool]:
    """承認マーカー `# contract-drift-ok: {理由}` を探し `(理由, 理由が空のマーカーがあるか)` を返す。

    `.py` は **実コメントトークンだけ** を見る（docstring で書式を説明した地の文で誤発火しないため。
    本ファイル自身の docstring がまさにその形を取っている）。トークナイズに失敗したら
    「マーカーなし」として扱う（承認は人が明示的に書いたときだけ成立させる＝ fail-closed）。
    `.py` 以外は行単位で走査する。
    """
    if path.suffix == ".py":
        try:
            texts = [
                tok.string for tok in _py_tokens(path, text) if tok.type == tokenize.COMMENT
            ]
        except UndecidableError:
            return None, False
    else:
        texts = text.splitlines()

    has_empty = False
    for chunk in texts:
        matched = _MARKER_RE.search(chunk)
        if not matched:
            continue
        reason = matched.group(1).strip()
        if reason:
            return reason, has_empty
        has_empty = True
    return None, has_empty


def trigger_hits(text: str, triggers: Iterable[str]) -> list[str]:
    """テキストに現れたトリガー語を返す（大文字小文字は区別しない）。

    説明文が docstring かコメントかは区別しない（どちらも「利用側に残る実装の説明」であり、
    腐り方は同じ）。
    """
    lowered = text.lower()
    return [t for t in triggers if t.lower() in lowered]


# --------------------------------------------------------------------------- git 差分


def _run_git(
    args: list[str],
    *,
    cwd: Path | str | None,
    runner: Runner,
    timeout: int = 20,
) -> tuple[str, int]:
    """git を 1 回実行し `(stdout, returncode)` を返す。例外は投げない（失敗は rc!=0 として扱う）。

    固定で `-c color.ui=false` を注入する。本ツールは diff 出力の行頭
    プレフィックス（`+` / `-` / `@@` / `diff --git `）を **生のアンカーとして** 解析するため、
    `color.ui=always` が設定された環境では全行が ANSI エスケープで始まり、本文行が 1 行も
    抽出されないまま「触っていない」と誤判定する（#762 の反例レビューで実測）。外部 diff も同じ理由で
    無効化するが、こちらは **`-c diff.external=` を使わない**（空文字を設定すると git がその空の
    コマンドを実行しようとして `error: cannot run :` / rc=128 で死ぬ・実測）。`--no-color` /
    `--no-ext-diff` はいずれも git のトップレベルオプションではないため（`git --no-color` は
    `unknown option`・実測）、各 diff 呼び出しの引数で明示する。

    `git_diff_utils._run_git()` は private なので、本ツールは同等の薄いラッパーを持つ
    （公開関数として切り出すほどの実体が無く、上記の固定オプションの注入位置も本ツール側で
    決めたいため意図的に重複させる）。
    dup-ok: 3 行の subprocess ラッパー。共通化の実体が無いため意図的に重複させる（#762）
    """
    try:
        proc = runner(
            ["git", "-c", "color.ui=false", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return "", 1
    return proc.stdout, proc.returncode


def ensure_no_ansi(stdout: str, context: str) -> None:
    """git 出力に ANSI エスケープが残っていたら判定不能へ倒す（色付き出力では行頭判定が成立しない）。

    `-c color.ui=false` の注入で通常は起こらないが、注入が退行したときに「本文 0 行 → 触っていない」
    と静かに誤判定するのを防ぐ最後の保険（fail-closed）。
    """
    if "\x1b[" in stdout:
        raise UndecidableError(
            f"{context}: git の出力に ANSI エスケープが含まれています"
            "（色付き出力では diff の行頭プレフィックス判定が成立しないため判定不能）"
        )


def _diff_body_lines(stdout: str) -> list[str]:
    """unified diff の本文（追加行・削除行）だけを取り出す。`+++` / `---` のファイルヘッダは除く。

    ヘッダ判定は **位置** で行う（先頭 3 文字だけで判定しない）。`---` / `+++` はファイルブロックの
    先頭（最初の `@@` より前）にしか現れないため、そこだけをヘッダとみなす。行頭の 3 文字だけで
    落とすと、**本文が `--` / `++` で始まる行**（削除行 `--- …` / 追加行 `+++ …` に化ける）まで
    捨ててしまい、トリガー語を含む差分を見落とす（#762 の反例レビューで実測）。
    """
    lines: list[str] = []
    in_hunk = False
    for line in stdout.split("\n"):
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk and (line.startswith("---") or line.startswith("+++")):
            continue  # ファイルヘッダ（本文行は必ず hunk の中にある）
        if line.startswith("+") or line.startswith("-"):
            lines.append(line)
    return lines


def git_show(rev_path: str, *, root: Path, runner: Runner) -> tuple[str, int]:
    """`git show {rev}:{path}` の内容を返す（`(stdout, rc)`）。rc!=0 は呼び出し側が解釈する。"""
    return _run_git(["show", rev_path], cwd=root, runner=runner)


def _code_diff_lines(
    module: str,
    body: Sequence[str],
    *,
    root: Path,
    base: str,
    runner: Runner,
) -> list[str]:
    """差分本文から **実装層の行だけ** を残す（コメント・docstring だけの行を落とす）。

    追加行（`+`）は現在のファイル、削除行（`-`）は base 版のファイルの「説明層だけの物理行」
    集合と突き合わせる。base 版が取れないときは base 側の集合を空にする（＝削除行はすべて
    実装層扱い＝警告が増える方向・fail-closed）。
    """
    module_path = root / module
    try:
        current_lines = explanatory_only_lines(Path(module), read_text(module_path))
    except UndecidableError:
        current_lines = frozenset()
    old_text, rc = git_show(f"{base}:{module}", root=root, runner=runner)
    base_lines = explanatory_only_lines(Path(module), old_text) if rc == 0 else frozenset()

    kept: list[str] = []
    for line in body:
        content = line[1:].strip()
        if not content:
            continue
        known = current_lines if line.startswith("+") else base_lines
        if content in known:
            continue  # モジュール自身の説明文（コメント・docstring）だけの行
        kept.append(content)
    return kept


def module_diff_touches_trigger(
    module: str,
    triggers: Sequence[str],
    *,
    root: Path,
    base: str,
    runner: Runner,
) -> tuple[bool, list[str]]:
    """共有モジュールの **実装層の差分行** にトリガー語が現れるかを判定し `(触れたか, 当たった語)` を返す。

    base range / worktree / cached の 3 ソースを見る。**pathspec 区切りの `--` を必ず付ける**
    （付けないと同名のブランチ・タグがあるときに git がパスではなく ref として解釈する）。

    いずれか 1 ソースでも非ゼロで終わったら `UndecidableError`（exit 2）へ倒す。git の非ゼロは
    「差分が無い」を意味しないため、`0` にも `1` にも丸めない（`check-tool-design-rules.md` §3）。
    旧実装は「3 ソース全滅のときだけ」判定不能にしていたため、shallow clone（base range だけが
    `no merge base` で落ちる）では原則が破れ、コミット済みの変更を見ないまま合格していた。
    """
    sources = (
        ["diff", "--no-color", "--no-ext-diff", "--unified=0", f"{base}...HEAD", "--", module],
        ["diff", "--no-color", "--no-ext-diff", "--unified=0", "--", module],
        ["diff", "--cached", "--no-color", "--no-ext-diff", "--unified=0", "--", module],
    )
    body: list[str] = []
    for args in sources:
        stdout, rc = _run_git(args, cwd=root, runner=runner)
        if rc != 0:
            raise UndecidableError(
                f"{module}: `git {' '.join(args)}` が非ゼロ終了しました"
                "（git の非ゼロは「差分が無い」を意味しないため判定不能）"
            )
        ensure_no_ansi(stdout, module)
        body += _diff_body_lines(stdout)
    code_lines = _code_diff_lines(module, body, root=root, base=base, runner=runner)
    hits = trigger_hits("\n".join(code_lines), triggers)
    return bool(hits), hits


def consumer_explanation_changed(
    consumer: str,
    *,
    root: Path,
    base: str,
    runner: Runner,
    changed_set: set[str],
) -> bool:
    """利用側の **説明文が base 版から変化したか** を返す。

    「差分に含まれるか」というファイル単位の判定では、説明文と無関係な 1 行を足すだけで
    検査全体が素通りする（#762 そのものの事例が沈黙する）。ここでは `git show {base}:{consumer}`
    で旧版を取り、`explanatory_text()` を通した文字列同士を比較する。

    base 版が取得できないときは 2 通りに分ける:
      - その利用側が変更集合に含まれている → base に存在しない新規追加とみなし「更新済み」
      - 含まれていない → 判定材料が無いので `UndecidableError`（0 にも 1 にも丸めない）
    """
    current = explanatory_text(Path(consumer), read_text(root / consumer))
    old_text, rc = git_show(f"{base}:{consumer}", root=root, runner=runner)
    if rc != 0:
        if consumer in changed_set:
            return True
        raise UndecidableError(
            f"{consumer}: base 版（{base}）を取得できず、変更集合にも含まれていないため"
            "説明文が更新されたかを判定できません"
        )
    return explanatory_text(Path(consumer), old_text) != current


def ensure_base_reachable(base: str, *, root: Path, runner: Runner) -> None:
    """base range の基準 ref が解決できることを確かめる（解決できなければ判定不能へ倒す）。

    `git diff {base}...HEAD` は ref が無いと非ゼロで終わるが、`collect_changed_files()` は
    **失敗したソースを黙って読み飛ばす**。その結果 `origin/main` が無い環境（浅い clone・
    fetch 前）では **コミット済みの変更を 1 行も見ないまま ✅ を返す**（PASS しながら何も守らない
    最悪の失敗モード・`check-tool-design-rules.md` §0/§2）。
    ここで先に ref の解決可否を確かめ、解決できないときは 0 にも 1 にも丸めず 2 を返す。
    """
    _, rc = _run_git(
        ["rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], cwd=root, runner=runner
    )
    if rc != 0:
        raise UndecidableError(
            f"base range の基準 ref を解決できません: {base}"
            "（コミット済みの変更を見ないまま合格にしないため判定不能にします。"
            "`git fetch origin` 後に再実行するか --base で到達可能な ref を指定してください）"
        )


def ensure_changed_collectable(base: str, *, root: Path, runner: Runner) -> None:
    """変更ファイルの収集そのものが成立することを確かめる（ref 解決とは別の失敗経路）。

    `ensure_base_reachable()` は ref が **解決できるか** しか見ない。shallow clone
    （`actions/checkout` 既定の `fetch-depth: 1`）では `origin/main` の ref は解決できる一方、
    `git diff --name-only -z origin/main...HEAD` は merge base 不在で `fatal: no merge base`
    （rc=128）になる。`collect_changed_files()` は rc!=0 のソースを無言で捨てるため、
    worktree / cached が空で成功すると **変更集合が空のまま exit 0** になる。
    ここで収集と同じコマンドを 1 回だけ先に叩き、非ゼロなら判定不能へ倒す。
    """
    _, rc = _run_git(
        ["diff", "--name-only", "-z", f"{base}...HEAD"], cwd=root, runner=runner
    )
    if rc != 0:
        raise UndecidableError(
            f"base range の差分を収集できません: {base}...HEAD"
            "（ref は解決できても merge base が無い shallow clone 等では変更集合が空になり、"
            "何も見ないまま合格してしまうため判定不能にします。"
            "`git fetch --unshallow` か `--base` で到達可能な ref を指定してください）"
        )


def collect_changed(*, root: Path, runner: Runner, base: str | None) -> list[str]:
    """変更ファイル集合を git から取る（収集ロジックは共有モジュールへ委ねる）。

    `require_existing=False`: 索引に載っているファイルの実在は `check_index_freshness()` が
    別途確認するため、ここで実在フィルタを掛ける必要がない（削除されたファイルも差分として
    見えていた方が判定に忠実）。
    """
    return git_diff_utils.collect_changed_files(
        require_existing=False, cwd=root, base=base, runner=runner
    )


# --------------------------------------------------------------------------- 判定


def check_index_freshness(index: Sequence[ContractEntry], root: Path) -> None:
    """索引が現実と対応していることを確かめる（対応が切れていたら判定不能へ倒す）。

    - 索引のファイルが存在しない → 判定不能（索引の陳腐化）
    - **その利用側に割り当てられた** トリガー語が説明文に 1 つも無い → 判定不能（説明文が既に
      消えているのに索引に残っている＝永久に何も守らない死んだエントリ）

    トリガー語をエントリ単位（全語の和集合）で照合すると、割り当て外の同居語で死んだ対応が
    生き残る（実測: `symbolic-ref` の説明を消しても、別件のコメントに「NUL 区切り」が残っていれば
    鮮度検査が発火しない）。判定は必ず **利用側ごとのトリガー語** で行う。
    """
    for entry in index:
        module_path = root / entry.module
        if not module_path.is_file():
            raise UndecidableError(
                f"索引の共有モジュールが存在しません: {entry.module}（索引を更新してください）"
            )
        for consumer in entry.consumers:
            consumer_path = root / consumer.path
            if not consumer_path.is_file():
                raise UndecidableError(
                    f"索引の利用側ファイルが存在しません: {consumer.path}（索引を更新してください）"
                )
            explanation = explanatory_text(consumer_path, read_text(consumer_path))
            if not trigger_hits(explanation, consumer.triggers):
                raise UndecidableError(
                    f"{consumer.path}: この利用側に割り当てたトリガー語"
                    f"（{', '.join(consumer.triggers)}）が"
                    "**説明文（コメント・docstring・文字列リテラル）の中に** 1 つも見つかりません。"
                    "説明文が既に消えているなら索引から外し、消えていないなら索引のトリガー語を直してください"
                )


def _approval(path: Path, *, label: str) -> tuple[str | None, bool]:
    try:
        text = read_text(path)
    except UndecidableError:
        return None, False
    reason, has_empty = marker_reason(path, text)
    if has_empty and not reason:
        print(
            f"⚠️ {label}: 理由が空の `# contract-drift-ok:` は無効です（何を読み直した結果 "
            "承認したのかを 1 行書いてください）",
            file=sys.stderr,
        )
    return reason, has_empty


def analyze(
    index: Sequence[ContractEntry],
    changed: Sequence[str],
    *,
    root: Path,
    use_git: bool,
    base: str,
    runner: Runner,
) -> tuple[list[dict], list[dict]]:
    """drift を判定して `(findings, approvals)` を返す（findings が空なら合格）。"""
    changed_set = {normalize_path(p, root=root) for p in changed if p.strip()}
    findings: list[dict] = []
    approvals: list[dict] = []

    for entry in index:
        if entry.module not in changed_set:
            continue
        if use_git:
            touched, hits = module_diff_touches_trigger(
                entry.module, entry.triggers, root=root, base=base, runner=runner
            )
            if not touched:
                continue
        else:
            # パス明示モードでは差分が取れないため「内部実装を触った」とみなす（fail-closed）。
            # 当たった語は不明なので `hits` は空にし、表示側で「全トリガーを対象とみなした」と明示する
            # （全語を当たったかのように表示すると、読み手が存在しない変更を探すことになる）
            hits = []

        module_reason, _ = _approval(root / entry.module, label=entry.module)

        stale: list[dict] = []
        for consumer in entry.consumers:
            own = (
                [t for t in consumer.triggers if t in hits]
                if use_git
                else list(consumer.triggers)
            )
            if not own:
                continue  # 当たったトリガー語と無関係な利用側は要求しない（直積にしない）
            if use_git:
                if consumer_explanation_changed(
                    consumer.path, root=root, base=base, runner=runner, changed_set=changed_set
                ):
                    continue
            elif consumer.path in changed_set:
                continue

            reason = module_reason
            if reason is None:
                reason, _ = _approval(root / consumer.path, label=consumer.path)
            if reason:
                approvals.append(
                    {"module": entry.module, "consumer": consumer.path, "reason": reason}
                )
                continue
            stale.append({"consumer": consumer.path, "triggers": own})

        if stale:
            findings.append(
                {
                    "module": entry.module,
                    "triggers_hit": hits,
                    "diff_available": use_git,
                    "stale_consumers": stale,
                }
            )
    return findings, approvals


def render_text(findings: Sequence[dict], approvals: Sequence[dict], scanned: int) -> int:
    for a in approvals:
        print(
            f"ℹ️ 承認済み（contract-drift-ok）: {a['consumer']} — {a['reason']}",
        )
    if not findings:
        print(f"✅ 共有モジュールの内部実装に対する説明文 drift はありません（索引 {scanned} 件）")
        return 0
    for f in findings:
        if f["diff_available"]:
            touched = f"内部実装（{', '.join(f['triggers_hit'])}）を変更しています"
        else:
            touched = "内部実装を変更しています（差分未取得のため全トリガーを対象とみなしました）"
        print(
            f"⚠️ drift の疑い: {f['module']} の{touched}が、"
            "その実装を説明している次の利用側ファイルの説明文が更新されていません:",
            file=sys.stderr,
        )
        for c in f["stale_consumers"]:
            print(f"   - {c['consumer']}（説明している語: {', '.join(c['triggers'])}）", file=sys.stderr)
    print(
        "  → 説明文を現在の実装に合わせて更新するか、読み直して説明が今も正しいなら"
        " `# contract-drift-ok: {読み直した結果と理由}` を該当ファイルに書いてください"
        "（理由が空のマーカーは無効。説明文そのものが消えたときだけ CONTRACT_INDEX から外す）",
        file=sys.stderr,
    )
    return 1


# --------------------------------------------------------------------------- self-test


class _FakeResult:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def _make_recording_runner(
    responses: dict[tuple[str, ...], str],
    *,
    fail_cmds: frozenset[tuple[str, ...]] = frozenset(),
    calls: list[list[str]] | None = None,
) -> Runner:
    """argv を記録する fake runner。終了コードだけでなく **呼び出し引数** を検証するために使う（#710）。"""

    def runner(args, **kwargs):  # noqa: ANN001, ANN003
        if calls is not None:
            calls.append(list(args))
        key = tuple(args)
        if key in fail_cmds:
            return _FakeResult(stdout="", returncode=1)
        return _FakeResult(stdout=responses.get(key, ""), returncode=0)

    return runner


_FIXTURE_MODULE = "tools/fake_shared.py"
_FIXTURE_A = "tools/fake_consumer_a.py"
_FIXTURE_B = "tools/fake_consumer_b.py"
_FIXTURE_INDEX = (
    ContractEntry(
        module=_FIXTURE_MODULE,
        consumers=(
            ConsumerEntry(path=_FIXTURE_A, triggers=("splitlines",)),
            ConsumerEntry(path=_FIXTURE_B, triggers=("NUL 区切り",)),
        ),
    ),
)
# 両方の利用側が同じトリガー語を説明している索引（直積の切り分けを見ない検証用）
_FIXTURE_INDEX_SHARED = (
    ContractEntry(
        module=_FIXTURE_MODULE,
        consumers=(
            ConsumerEntry(path=_FIXTURE_A, triggers=("splitlines",)),
            ConsumerEntry(path=_FIXTURE_B, triggers=("splitlines",)),
        ),
    ),
)

_TEXT_A = '"""利用側 A。collect() は splitlines を使うため…"""\n'
_TEXT_B = "# 利用側 B: レコードは NUL 区切りで返る\nX = 1\n"
# 両方のトリガー語を説明している版（_FIXTURE_INDEX_SHARED 用）
_TEXT_B_SHARED = "# 利用側 B: splitlines と NUL 区切り の両方を説明する\nX = 1\n"


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_fixture(root: Path) -> None:
    """索引が健全なフィクスチャを作る。

    利用側 2 本は説明の書き方を変えてある（#2 バリアント展開）:
      - A: docstring 内・小文字の `splitlines`
      - B: 行コメント内・大文字混じりの `NUL 区切り`
    """
    _write(root, _FIXTURE_MODULE, '"""共有モジュール。NUL 区切りで分割する。"""\n')
    _write(root, _FIXTURE_A, _TEXT_A)
    _write(root, _FIXTURE_B, _TEXT_B)
    # 境界の外側（#750）: 索引モジュールと似た名前だが別ファイル
    _write(root, "tools/fake_shared_old.py", "# 旧実装（索引対象外）\n")


def _run_main(
    root: Path,
    extra: list[str],
    *,
    runner: Runner = subprocess.run,
    index: Sequence[ContractEntry] = _FIXTURE_INDEX,
) -> tuple[int, str, str]:
    """本番の入口 `main()` を argv 経由で呼び、exit code と stdout/stderr を返す（#686）。"""
    import contextlib
    import io as _io

    out, err = _io.StringIO(), _io.StringIO()
    argv = ["--root", str(root)] + extra
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, runner=runner, index=index)
    return code, out.getvalue(), err.getvalue()


def _k(*args: str) -> tuple[str, ...]:
    """本ツール自身が発行する git コマンドのキー（固定オプション込み）。"""
    return ("git", "-c", "color.ui=false", *args)


def _kg(*args: str) -> tuple[str, ...]:
    """`git_diff_utils` が発行する git コマンドのキー（`core.quotePath=false` を注入する）。"""
    return ("git", "-c", "core.quotePath=false", *args)


def _git_mode_responses(
    module_diff: str,
    *,
    changed: Sequence[str] = (_FIXTURE_MODULE,),
    show: dict[str, str] | None = None,
) -> dict[tuple[str, ...], str]:
    """git モード self-test の共通レスポンス表を組む。"""
    payload = "".join(f"{p}\0" for p in changed)
    responses: dict[tuple[str, ...], str] = {
        # 変更ファイル収集（git_diff_utils 側）
        _kg("diff", "--name-only", "-z", "origin/main...HEAD"): payload,
        _kg("diff", "--name-only", "-z"): "",
        _kg("diff", "--cached", "--name-only", "-z"): "",
        _kg("ls-files", "--others", "--exclude-standard", "-z"): "",
        # 収集 preflight（本ツール側）
        _k("diff", "--name-only", "-z", "origin/main...HEAD"): payload,
        # モジュール差分
        _k("diff", "--no-color", "--no-ext-diff", "--unified=0", "origin/main...HEAD", "--", _FIXTURE_MODULE): module_diff,
        _k("diff", "--no-color", "--no-ext-diff", "--unified=0", "--", _FIXTURE_MODULE): "",
        _k("diff", "--cached", "--no-color", "--no-ext-diff", "--unified=0", "--", _FIXTURE_MODULE): "",
        # base 版の中身（既定は「現在と同じ＝説明文は未更新」）
        _k("show", f"origin/main:{_FIXTURE_MODULE}"): "",
        _k("show", f"origin/main:{_FIXTURE_A}"): _TEXT_A,
        _k("show", f"origin/main:{_FIXTURE_B}"): _TEXT_B,
    }
    for key, value in (show or {}).items():
        responses[_k("show", key)] = value
    return responses


def run_self_test() -> int:  # noqa: C901
    import tempfile

    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        if cond:
            print(f"  ✅ {label}")
        else:
            failures += 1
            print(f"  ❌ {label}" + (f"\n     {detail}" if detail else ""))

    # ------------------------------------------------------------------ 1. 索引の構造検証
    print("1. 索引の構造検証（要素は妥当でも集合として壊れている入力・#896）")
    check("空の索引は判定不能", validate_index(()) is not None)
    check(
        "module が空の索引エントリは判定不能",
        validate_index((ContractEntry(module="", consumers=(ConsumerEntry("a.py", ("t",)),)),))
        is not None,
    )
    dup_module = (
        ContractEntry(module="m.py", consumers=(ConsumerEntry("a.py", ("t",)),)),
        ContractEntry(module="m.py", consumers=(ConsumerEntry("b.py", ("t",)),)),
    )
    check("同一モジュールの二重登録は判定不能", validate_index(dup_module) is not None)
    dup_consumer = (
        ContractEntry(
            module="m.py",
            consumers=(ConsumerEntry("a.py", ("t",)), ConsumerEntry("a.py", ("u",))),
        ),
    )
    check("同一利用側の重複登録は判定不能", validate_index(dup_consumer) is not None)
    self_ref = (ContractEntry(module="m.py", consumers=(ConsumerEntry("m.py", ("t",)),)),)
    check("利用側に自分自身を登録したら判定不能", validate_index(self_ref) is not None)
    empty_trig = (ContractEntry(module="m.py", consumers=(ConsumerEntry("a.py", ()),)),)
    check("利用側の triggers 空は判定不能", validate_index(empty_trig) is not None)
    dup_trig = (
        ContractEntry(module="m.py", consumers=(ConsumerEntry("a.py", ("t", "t")),)),
    )
    check("同一トリガー語の重複は判定不能", validate_index(dup_trig) is not None)
    empty_cons = (ContractEntry(module="m.py", consumers=()),)
    check("consumers 空は判定不能", validate_index(empty_cons) is not None)
    check("path が空の利用側は判定不能", validate_index(
        (ContractEntry(module="m.py", consumers=(ConsumerEntry("", ("t",)),)),)
    ) is not None)
    check("正常な索引は問題なし", validate_index(_FIXTURE_INDEX) is None)
    check("本番索引は問題なし", validate_index(CONTRACT_INDEX) is None)

    # ------------------------------------------------------------------ 1.5 説明層の切り分け
    print("1.5 説明層 / 実装層の切り分け（explanatory_only_lines）")
    layered = '"""doc\nsplitlines の説明\n"""\n# コメント splitlines\nx = 1  # 末尾コメント\ny = "splitlines"\n'
    only = explanatory_only_lines(Path("m.py"), layered)
    check("docstring 行は説明層", "splitlines の説明" in only, str(only))
    check("行コメントだけの行は説明層", "# コメント splitlines" in only, str(only))
    check("コードと同居する末尾コメント行は実装層", "x = 1  # 末尾コメント" not in only, str(only))
    check("文字列を代入する行は実装層", 'y = "splitlines"' not in only, str(only))
    check(".py 以外は層を判定しない（空集合）", explanatory_only_lines(Path("a.md"), layered) == frozenset())

    # ------------------------------------------------------------------ 1.7 承認マーカー
    print("1.7 承認マーカー `# contract-drift-ok:` の抽出")
    check(
        "理由付きコメントのマーカーは有効",
        marker_reason(Path("m.py"), "# contract-drift-ok: 読み直して正しいと確認\nX = 1\n")[0]
        == "読み直して正しいと確認",
    )
    check(
        "理由が空のマーカーは無効（reason=None・empty=True）",
        marker_reason(Path("m.py"), "# contract-drift-ok:\nX = 1\n") == (None, True),
    )
    check(
        "docstring 内の書式説明ではマーカーが発火しない",
        marker_reason(Path("m.py"), '"""書式は # contract-drift-ok: 理由 と書く"""\n')[0] is None,
    )

    # ------------------------------------------------------------------ 2. パス明示モード
    print("2. パス明示モードの判定（main() 経由）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)

        code, out, err = _run_main(root, [_FIXTURE_MODULE, _FIXTURE_A, _FIXTURE_B])
        check("モジュールと全利用側が同じ差分 → exit 0", code == 0, f"code={code} err={err}")

        code, out, err = _run_main(root, [_FIXTURE_MODULE])
        check("利用側が差分に無い → exit 1", code == 1, f"code={code} out={out}")
        check("警告に欠落した利用側 2 本が出る", _FIXTURE_A in err and _FIXTURE_B in err, err)
        check(
            "差分未取得である旨を明示し、当たってもいない全トリガー語を並べない（NIT 2）",
            "差分未取得" in err and "splitlines, NUL 区切り" not in err,
            err,
        )

        code, _, err = _run_main(root, [_FIXTURE_MODULE, _FIXTURE_A])
        check("片方だけ含まれていれば残り 1 本を警告", code == 1 and _FIXTURE_B in err, err)

        # 境界の外側（#750）: 前方一致で同一視しないこと
        code, out, err = _run_main(root, ["tools/fake_shared_old.py"])
        check(
            "似た名前の別ファイル（fake_shared_old.py）は索引モジュールと同一視しない",
            code == 0,
            f"code={code} err={err}",
        )

        # パス表記の揺れ（#2 バリアント）
        code, _, err = _run_main(root, ["./" + _FIXTURE_MODULE])
        check("`./` 付きの表記でも索引モジュールとして判定する", code == 1, err)

        # 絶対パス表記（#2 バリアント）: 索引と一致しないまま黙って合格しないこと
        code, _, err = _run_main(root, [str(root / _FIXTURE_MODULE)])
        check("絶対パスで指定しても索引モジュールとして判定する", code == 1, f"code={code} err={err}")

        # ルート外の絶対パス / 打ち間違い → 対象 0 件を合格にしない（fail-closed）
        code, _, err = _run_main(root, ["/nonexistent/elsewhere.py"])
        check("ルート外の絶対パスだけを渡したら判定不能(2)", code == 2, f"code={code} err={err}")
        code, _, err = _run_main(root, ["tools/fake_sharedd.py"])
        check("打ち間違い（実在せず索引にも無い）→ 判定不能(2)", code == 2, f"code={code} err={err}")

        # 承認マーカー（利用側）
        _write(root, _FIXTURE_B, _TEXT_B + "# contract-drift-ok: 読み直したが説明は今も正しい\n")
        code, out, err = _run_main(root, [_FIXTURE_MODULE, _FIXTURE_A])
        check("利用側の理由付き承認マーカーがあれば exit 0", code == 0, f"code={code} err={err}")
        check("承認したことを stdout に残す", "承認済み" in out, out)

        # 理由が空のマーカーは無効
        _write(root, _FIXTURE_B, _TEXT_B + "# contract-drift-ok:\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE, _FIXTURE_A])
        check("理由が空の承認マーカーは無効 → exit 1", code == 1, f"code={code} err={err}")
        check("理由が空である旨を警告する", "理由が空" in err, err)

        # 承認マーカー（共有モジュール側）は全利用側を承認する
        _write(root, _FIXTURE_B, _TEXT_B)
        _write(
            root,
            _FIXTURE_MODULE,
            '"""共有モジュール。NUL 区切りで分割する。"""\n'
            "# contract-drift-ok: 内部実装は変えたが公開契約と説明は不変\n",
        )
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check("モジュール側の承認マーカーは全利用側を承認する → exit 0", code == 0, f"code={code} err={err}")
        _write(root, _FIXTURE_MODULE, '"""共有モジュール。NUL 区切りで分割する。"""\n')

        # --json 経路の終了コード（公開オプションなのに一度も実行されていなかった）
        code, out, err = _run_main(root, ["--json", _FIXTURE_MODULE])
        check("--json でも drift は exit 1", code == 1, f"code={code} err={err}")
        try:
            payload = json.loads(out)
            ok_json = payload["findings"][0]["stale_consumers"][0]["consumer"] == _FIXTURE_A
        except Exception as exc:  # noqa: BLE001
            payload, ok_json = None, False
            err += f" json parse error: {exc}"
        check("--json の中身が機械可読で stale_consumers を含む", ok_json, f"out={out} err={err}")

        # --changed と明示パスの併用（NIT 1）
        code, _, err = _run_main(root, ["--changed", _FIXTURE_MODULE])
        check("--changed と明示パスの併用 → 判定不能(2)", code == 2, f"code={code} err={err}")

        # 索引の陳腐化（利用側から説明文が消えている）
        _write(root, _FIXTURE_B, "X = 1\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check("利用側にトリガー語が 1 つも無い → 判定不能(2)", code == 2, f"code={code} err={err}")

        # 割り当て外のトリガー語だけが残っている（#750 の境界の外側 / 「いずれか 1 語」判定の禁止）
        _write(root, _FIXTURE_B, "# 利用側 B: collect() は splitlines を使う\nX = 1\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check(
            "割り当て外のトリガー語（splitlines）だけが残る利用側 B → 判定不能(2)",
            code == 2,
            f"code={code} err={err}",
        )
        _write(root, _FIXTURE_B, _TEXT_B)

        # 陳腐化検知が「無関係なコード中の同語」で生き延びないこと（反例レビュー #762）
        # 説明文は消えているのに実装コードに `splitlines()` が残っているだけ、という形。
        # ファイル全文を対象にすると死んだ索引エントリが永久に生き残る（fail-open）。
        _write(root, _FIXTURE_A, "raw_lines = text.splitlines()\nX = 1\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check(
            "説明文が消え実装コードにだけトリガー語が残る利用側 → 判定不能(2)",
            code == 2,
            f"code={code} err={err}",
        )

        # 逆側（誤検知の抑制）: 説明が文字列リテラル・コメントにあるなら生きている
        _write(root, _FIXTURE_A, _TEXT_A)
        _write(root, _FIXTURE_B, _TEXT_B)
        code, _, err = _run_main(root, [_FIXTURE_MODULE, _FIXTURE_A, _FIXTURE_B])
        check("説明がコメントにある利用側は健全（exit 0）", code == 0, f"code={code} err={err}")

        # 構文が壊れた利用側 → 判定不能（tokenize 失敗を合格へ丸めない）
        _write(root, _FIXTURE_B, "def broken(:\n    pass\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check("構文が壊れた利用側 → 判定不能(2)", code == 2, f"code={code} err={err}")
        check("stderr が「解析できない」を明示する", "解析できない" in err, err)

        # 非 UTF-8 の利用側 → 判定不能（誤って「索引から外せ」と診断しない）
        (root / _FIXTURE_B).write_bytes(b"\xff\xfe# NUL \x8e\xa4\xe8\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check("非 UTF-8 の利用側 → 判定不能(2)", code == 2, f"code={code} err={err}")
        check(
            "非 UTF-8 は「非 UTF-8」と診断する（索引から外せ、ではない）",
            "非 UTF-8" in err and "索引から外し" not in err,
            err,
        )
        _write(root, _FIXTURE_B, _TEXT_B)

        # 索引のファイルが消えた（利用側 / 共有モジュールを別ケースで固定）
        (root / _FIXTURE_A).unlink()
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check("索引の利用側が存在しない → 判定不能(2)", code == 2, f"code={code} err={err}")
        _write(root, _FIXTURE_A, _TEXT_A)
        (root / _FIXTURE_MODULE).unlink()
        code, _, err = _run_main(root, [_FIXTURE_A])
        check("索引の共有モジュールが存在しない → 判定不能(2)", code == 2, f"code={code} err={err}")

    # ------------------------------------------------------------------ 3. git モード
    print("3. git モード（--changed）と argv 検証（#710）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)

        trigger_diff = "@@\n-    parts = out.splitlines()\n+    parts = out.split('\\0')\n"
        calls: list[list[str]] = []
        runner = _make_recording_runner(_git_mode_responses(trigger_diff), calls=calls)
        code, _, err = _run_main(root, ["--changed"], runner=runner)
        check("トリガー語を含む差分 + 説明文未更新 → exit 1", code == 1, f"code={code} err={err}")
        check(
            "当たったトリガー語（splitlines）を説明する A だけを要求し、B は要求しない（直積にしない）",
            _FIXTURE_A in err and _FIXTURE_B not in err,
            err,
        )

        diff_calls = [c for c in calls if "--unified=0" in c and "--name-only" not in c]
        check("main() から git diff が実際に呼ばれている", bool(diff_calls), f"calls={calls}")
        check(
            "pathspec 区切りの `--` が省略されていない",
            all("--" in c and c.index("--") < c.index(_FIXTURE_MODULE) for c in diff_calls),
            f"diff_calls={diff_calls}",
        )
        check(
            "`--no-color` / `--no-ext-diff` が全 diff 呼び出しに付いている"
            "（色付き出力・外部 diff でパーサが空振りしないため）",
            all("--no-color" in c and "--no-ext-diff" in c for c in diff_calls),
            f"diff_calls={diff_calls}",
        )
        check(
            "`-c color.ui=false` が注入されている",
            all(c[1:3] == ["-c", "color.ui=false"] for c in diff_calls),
            f"diff_calls={diff_calls}",
        )
        check(
            "3 ソース（base range / worktree / cached）すべてを見ている",
            len(diff_calls) == 3,
            f"diff_calls={diff_calls}",
        )
        check(
            "収集 preflight（`diff --name-only -z {base}...HEAD`）が main() から呼ばれている",
            any(c[-1] == "origin/main...HEAD" and "--name-only" in c for c in calls),
            f"calls={calls}",
        )
        check(
            "利用側の base 版を `git show` で取得している",
            any(len(c) > 3 and c[3] == "show" and c[-1].endswith(_FIXTURE_A) for c in calls),
            f"calls={calls}",
        )

        # 🔴 CRITICAL 1 の回帰: 「差分に含まれるが説明文は無変更」→ 素通りしない
        runner_noop = _make_recording_runner(
            _git_mode_responses(trigger_diff, changed=(_FIXTURE_MODULE, _FIXTURE_A))
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_noop)
        check(
            "利用側が差分に含まれていても説明文が無変更なら exit 1（無関係な 1 行で素通りしない）",
            code == 1 and _FIXTURE_A in err,
            f"code={code} err={err}",
        )

        # 説明文が実際に更新されていれば合格
        runner_updated = _make_recording_runner(
            _git_mode_responses(
                trigger_diff,
                changed=(_FIXTURE_MODULE, _FIXTURE_A),
                show={f"origin/main:{_FIXTURE_A}": '"""利用側 A。collect() は splitlines を使う（旧説明）。"""\n'},
            )
        )
        code, out, err = _run_main(root, ["--changed"], runner=runner_updated)
        check("利用側の説明文が base 版から変化していれば exit 0", code == 0, f"code={code} err={err}")

        # 誤検知の抑制: 同じモジュールを触っていてもトリガー語に当たらない差分なら合格
        runner2 = _make_recording_runner(
            _git_mode_responses("@@\n+# コメントを 1 行足しただけ\n")
        )
        code, out, err = _run_main(root, ["--changed"], runner=runner2)
        check("トリガー語に当たらない差分 → exit 0（誤検知の抑制）", code == 0, f"code={code} err={err}")

        # 層の切り分け: モジュール自身の docstring / コメントにトリガー語を足しただけ → exit 0
        module_with_note = (
            '"""共有モジュール。NUL 区切りで分割する。"""\n'
            "# 注: 以前は splitlines を使っていた（履歴メモ・実装は変えていない）\n"
        )
        _write(root, _FIXTURE_MODULE, module_with_note)
        runner_comment = _make_recording_runner(
            _git_mode_responses(
                "@@\n+# 注: 以前は splitlines を使っていた（履歴メモ・実装は変えていない）\n"
            )
        )
        code, out, err = _run_main(root, ["--changed"], runner=runner_comment)
        check(
            "モジュールのコメント行にトリガー語を足しただけ → exit 0（説明層を実装変更とみなさない）",
            code == 0,
            f"code={code} err={err}",
        )
        # 対（実装行にトリガー語が現れる差分は従来どおり exit 1）
        runner_code = _make_recording_runner(
            _git_mode_responses("@@\n+    parts = out.splitlines()\n")
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_code)
        check(
            "モジュールの実装行にトリガー語が現れる差分 → exit 1（層の切り分けが実装変更を隠さない）",
            code == 1,
            f"code={code} err={err}",
        )
        _write(root, _FIXTURE_MODULE, '"""共有モジュール。NUL 区切りで分割する。"""\n')

        # 本文が `--` / `++` で始まる差分行を diff ヘッダとして捨てないこと（反例レビュー #762）
        header_style_body = (
            "diff --git a/x b/x\nindex 111..222 100644\n"
            f"--- a/{_FIXTURE_MODULE}\n+++ b/{_FIXTURE_MODULE}\n"
            "@@ -1 +1 @@\n"
            "--- x = NUL 区切り --- （本文が `--` で始まる削除行）\n"
            "+++ y = splitlines へ戻した行（本文が `++` で始まる追加行）\n"
        )
        check(
            "diff のファイルヘッダ（`--- a/` / `+++ b/`）は本文に含めない",
            not any(l.startswith(("--- a/", "+++ b/")) for l in _diff_body_lines(header_style_body)),
            f"body={_diff_body_lines(header_style_body)}",
        )
        runner_hdr = _make_recording_runner(_git_mode_responses(header_style_body))
        code, _, err = _run_main(root, ["--changed"], runner=runner_hdr)
        check(
            "本文が `--`/`++` で始まる差分行のトリガー語も検出する → exit 1",
            code == 1,
            f"code={code} err={err}",
        )

        # ANSI 着色された diff → 判定不能（0 にも 1 にも丸めない）
        runner_ansi = _make_recording_runner(
            _git_mode_responses(
                "\x1b[1mdiff --git a/x b/x\x1b[m\n\x1b[36m@@ -1 +1 @@\x1b[m\n"
                "\x1b[31m-    parts = out.splitlines()\x1b[m\n"
            )
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_ansi)
        check("色付き diff（ANSI エスケープ）→ 判定不能(2)", code == 2, f"code={code} err={err}")

        # base range の基準 ref が解決できない → 判定不能
        runner_nobase = _make_recording_runner(
            _git_mode_responses(trigger_diff),
            fail_cmds=frozenset({_k("rev-parse", "--verify", "--quiet", "origin/main^{commit}")}),
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_nobase)
        check("base range の基準 ref が解決できない → 判定不能(2)", code == 2, f"code={code} err={err}")

        # 🔴 CRITICAL 3 の回帰: ref は解決できるが base range の収集が失敗（shallow clone）
        runner_shallow = _make_recording_runner(
            _git_mode_responses(trigger_diff),
            fail_cmds=frozenset({_k("diff", "--name-only", "-z", "origin/main...HEAD")}),
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_shallow)
        check(
            "ref は解決できても base range の収集が失敗（shallow clone）→ 判定不能(2)",
            code == 2,
            f"code={code} err={err}",
        )

        # git diff の 1 ソースだけ失敗しても判定不能（3 ソース全滅を待たない）
        runner3 = _make_recording_runner(
            _git_mode_responses(trigger_diff),
            fail_cmds=frozenset(
                {_k("diff", "--no-color", "--no-ext-diff", "--unified=0", "origin/main...HEAD", "--", _FIXTURE_MODULE)}
            ),
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner3)
        check("git diff が 1 ソースでも失敗 → 判定不能(2)", code == 2, f"code={code} err={err}")

        # 変更 0 件（日常的に起こりうる）→ 合格
        runner4 = _make_recording_runner(_git_mode_responses(trigger_diff, changed=()))
        code, out, _ = _run_main(root, ["--changed"], runner=runner4)
        check("変更 0 件 → exit 0（変更起点の検査なので日常的）", code == 0, f"code={code}")

        # 共通トリガー語の索引では両方の利用側を要求する（直積回避が過剰に効いていないこと）
        _write(root, _FIXTURE_B, _TEXT_B_SHARED)
        runner_shared = _make_recording_runner(
            _git_mode_responses(
                trigger_diff, show={f"origin/main:{_FIXTURE_B}": _TEXT_B_SHARED}
            )
        )
        code, _, err = _run_main(
            root, ["--changed"], runner=runner_shared, index=_FIXTURE_INDEX_SHARED
        )
        check(
            "同じトリガー語を説明する利用側は全件要求する（絞り込みが効きすぎていない）",
            code == 1 and _FIXTURE_A in err and _FIXTURE_B in err,
            f"code={code} err={err}",
        )
        _write(root, _FIXTURE_B, _TEXT_B)

        # base 版が取れず変更集合にも無い利用側 → 判定不能
        runner_noshow = _make_recording_runner(
            _git_mode_responses(trigger_diff),
            fail_cmds=frozenset({_k("show", f"origin/main:{_FIXTURE_A}")}),
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_noshow)
        check(
            "利用側の base 版が取れず変更集合にも無い → 判定不能(2)",
            code == 2,
            f"code={code} err={err}",
        )

        # base 版が取れないが変更集合に含まれる（新規追加）→ 更新済みとみなす
        runner_newfile = _make_recording_runner(
            _git_mode_responses(trigger_diff, changed=(_FIXTURE_MODULE, _FIXTURE_A)),
            fail_cmds=frozenset({_k("show", f"origin/main:{_FIXTURE_A}")}),
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_newfile)
        check(
            "base に存在しない新規の利用側が差分に含まれる → exit 0",
            code == 0,
            f"code={code} err={err}",
        )

    # ------------------------------------------------------------------ 4. #762 回帰ケース
    print("4. Issue #762 の実例（git_diff_utils → 利用側 3 本）")
    root = repo_root()
    code, _, err = _run_main(root, ["tools/git_diff_utils.py"], index=CONTRACT_INDEX)
    check(
        "git_diff_utils.py だけを変更 → 利用側 3 本の説明文 drift を警告",
        code == 1
        and "tools/scan_dangerous_patterns.py" in err
        and "tools/check_architecture_boundaries.py" in err
        and "tools/check_module_contract_drift.py" in err,
        f"code={code} err={err}",
    )
    code, _, err = _run_main(
        root,
        [
            "tools/git_diff_utils.py",
            "tools/scan_dangerous_patterns.py",
            "tools/check_architecture_boundaries.py",
            "tools/check_module_contract_drift.py",
        ],
        index=CONTRACT_INDEX,
    )
    check("利用側も同じ差分に含まれていれば合格", code == 0, f"code={code} err={err}")
    check(
        "本番索引が現実と対応している（トリガー語・ファイルの実在）",
        _index_freshness_ok(CONTRACT_INDEX, root),
        "本番索引のトリガー語が利用側に見つかりません",
    )

    # ------------------------------------------------------------------ 5. 実プロセスの exit code
    print("5. 実プロセスの終了コード（main() から sys.exit まで貫通しているか）")
    script = str(Path(__file__).resolve())

    def _run_proc(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, script, *args], capture_output=True, text=True, cwd=str(repo_root())
        )

    r_none = _run_proc([])
    check(
        "引数なし → 本ツール自身のガードで exit 2（argparse ではなく判定対象未指定）",
        r_none.returncode == 2 and "判定対象が指定されていません" in r_none.stderr,
        f"rc={r_none.returncode} stderr={r_none.stderr}",
    )
    r_ok = _run_proc(
        [
            "tools/git_diff_utils.py",
            "tools/scan_dangerous_patterns.py",
            "tools/check_architecture_boundaries.py",
            "tools/check_module_contract_drift.py",
        ]
    )
    check("実プロセス: 合格 = 0", r_ok.returncode == 0, r_ok.stderr)
    r_ng = _run_proc(["tools/git_diff_utils.py"])
    check("実プロセス: drift = 1", r_ng.returncode == 1, r_ng.stderr)
    # `=` 連結形で argparse を通過させ、**本ツールのガード** に到達させる（argparse の 2 と区別する）
    r_un = _run_proc(["--base=--pwned", "--changed"])
    check(
        "実プロセス: 判定不能 = 2（オプション様の base・ガード固有のメッセージまで確認）",
        r_un.returncode == 2 and "- で始まる値は使えません" in r_un.stderr,
        f"rc={r_un.returncode} stderr={r_un.stderr}",
    )
    # cwd 相対のパス解決（`tools/` 内から叩くと黙って合格していた・#762 の反例レビュー）
    r_cwd = subprocess.run(
        [sys.executable, script, "git_diff_utils.py"],
        capture_output=True,
        text=True,
        cwd=str(repo_root() / "tools"),
    )
    check(
        "実プロセス: tools/ 内から cwd 相対で叩いても索引モジュールとして判定する = 1",
        r_cwd.returncode == 1 and "tools/scan_dangerous_patterns.py" in r_cwd.stderr,
        f"rc={r_cwd.returncode} stderr={r_cwd.stderr}",
    )
    r_typo = subprocess.run(
        [sys.executable, script, "git_diff_utill.py"],
        capture_output=True,
        text=True,
        cwd=str(repo_root() / "tools"),
    )
    check(
        "実プロセス: tools/ 内からの打ち間違いは黙って合格しない = 2",
        r_typo.returncode == 2 and "存在せず索引にもありません" in r_typo.stderr,
        f"rc={r_typo.returncode} stderr={r_typo.stderr}",
    )
    r_both = _run_proc(["--changed", "tools/git_diff_utils.py"])
    check(
        "実プロセス: --changed と明示パスの併用 = 2",
        r_both.returncode == 2 and "併用できません" in r_both.stderr,
        f"rc={r_both.returncode} stderr={r_both.stderr}",
    )

    print(f"\n{'✅ self-test PASS' if not failures else f'❌ self-test FAIL: {failures} 件'}")
    return 1 if failures else 0


def _index_freshness_ok(index: Sequence[ContractEntry], root: Path) -> bool:
    try:
        check_index_freshness(index, root)
    except UndecidableError:
        return False
    return True


# --------------------------------------------------------------------------- entry point


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner = subprocess.run,
    index: Sequence[ContractEntry] = CONTRACT_INDEX,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="判定対象の変更ファイル（明示指定）")
    parser.add_argument("--changed", action="store_true", help="git 差分から変更ファイルを集める")
    parser.add_argument("--base", default=None, help="base range の基準 ref（既定: origin/<default branch>）")
    parser.add_argument("--root", default=None, help="検査対象のルート（既定: リポジトリルート）")
    parser.add_argument("--json", action="store_true", help="機械可読 JSON で出力")
    parser.add_argument("--self-test", action="store_true", help="自己テストを実行する")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    problem = validate_index(index)
    if problem:
        print(f"⚠️ 判定不能: {problem}", file=sys.stderr)
        return 2

    if args.changed and args.paths:
        print(
            "⚠️ 判定不能: --changed と明示パスは併用できません"
            "（併用すると明示分が黙って捨てられ、指定したのに何も検査していない状態が緑で返ります）",
            file=sys.stderr,
        )
        return 2

    if not args.changed and not args.paths:
        print(
            "⚠️ 判定不能: 判定対象が指定されていません（--changed かパスを指定してください）",
            file=sys.stderr,
        )
        return 2

    root = Path(args.root).resolve() if args.root else repo_root()
    if args.base is not None and args.base.startswith("-"):
        print(
            f"⚠️ 判定不能: --base に - で始まる値は使えません（git のオプションとして解釈される）: {args.base!r}",
            file=sys.stderr,
        )
        return 2

    try:
        check_index_freshness(index, root)
        base = args.base or f"origin/{git_diff_utils.default_branch(cwd=root, runner=runner)}"
        if args.changed:
            # 収集と判定で同じ base を使う（別々に解決すると片方だけ空振りしても気づけない）
            ensure_base_reachable(base, root=root, runner=runner)
            ensure_changed_collectable(base, root=root, runner=runner)
            changed = collect_changed(root=root, runner=runner, base=base)
        else:
            changed = [
                normalize_path(p, root=root, cwd=Path.cwd()) for p in args.paths if p.strip()
            ]
            index_paths = {e.module for e in index} | {
                c.path for e in index for c in e.consumers
            }
            unknown = [
                p for p in changed if not (root / p).exists() and p not in index_paths
            ]
            if unknown:
                print(
                    "⚠️ 判定不能: 指定されたパスがルート配下に存在せず索引にもありません"
                    f"（打ち間違い？ ルート={root}）: {', '.join(unknown)}",
                    file=sys.stderr,
                )
                return 2
        findings, approvals = analyze(
            index, changed, root=root, use_git=args.changed, base=base, runner=runner
        )
    except UndecidableError as exc:
        print(f"⚠️ 判定不能: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:  # git_diff_utils のオプション様 base ガード
        print(f"⚠️ 判定不能: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "changed": changed,
                    "findings": findings,
                    "approvals": approvals,
                    "index_size": len(index),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if findings else 0
    return render_text(findings, approvals, len(index))


if __name__ == "__main__":
    sys.exit(main())
