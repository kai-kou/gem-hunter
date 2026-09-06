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

索引（`CONTRACT_INDEX`）は「共有モジュール → その内部実装を名指しする語（トリガー語） →
その語を説明文として持つ利用側ファイル」の対応を **明示リスト** として持つ。判定は 3 段:

1. 変更ファイル集合（`--changed` の git 差分、または引数で明示指定したパス）に索引の
   **共有モジュール** が含まれているか（パスは完全一致。前方一致で判定しない）
2. （git モードのみ）その共有モジュールの **差分行**（追加行・削除行）に **トリガー語** が
   現れているか（＝内部実装そのものを触ったか）。無関係な変更で毎回警告しないための絞り込み。
   パス明示モードでは差分が取れないため、この段は「触った」とみなす（fail-closed）
3. その索引に載っている **利用側ファイル** が変更集合に含まれているか。含まれていなければ drift

drift は「説明文が壊れた」ことの証明ではなく、「説明文を読み直すべき差分が来た」ことの通知である。
読み直した結果 **説明が今も正しい** なら、索引からその利用側を外す（理由をコミットメッセージに残す）
か、説明文側を現在の実装に合わせて更新する。

## なぜ全関数名を自動抽出しないか

共有モジュールの公開シンボルを全部拾うと、利用側は必ずどれかを名前で言及しているため、
共有モジュールを触る全 PR が警告になり、警告が無視される（機能しなくなる）。索引は
**内部実装を名指しする語** に限定し、初期セットも実例 1 件から始めて実効性を確認してから広げる。

## 索引を Python 内定数で持つ理由

`tools/check_delegation_preamble.py` の `REQUIRED_GROUPS` と同じ形にそろえた。行ごとに
「なぜこの語がトリガーなのか」をコメントで残せること、JSON 外部ファイルにすると
「パース失敗 → 判定不能」の経路が増えるだけで得るものが無いことが理由。

## 使い方

    python3 tools/check_module_contract_drift.py --changed        # git 差分から判定
    python3 tools/check_module_contract_drift.py a.py b.py        # パスを明示指定して判定
    python3 tools/check_module_contract_drift.py --self-test      # 自己テスト（ネットワーク不要）

終了コード（`docs/rules/check-tool-design-rules.md` §1 の標準どおり）:
  0 = 合格（索引の共有モジュールに該当する差分が無い、または利用側も同じ差分に含まれている）
  1 = drift 検出（Warning。上記「判定契約」に従って説明文を読み直すこと）
  2 = 判定不能（索引が壊れている・索引のファイルが読めない/解析できない・git が到達不能・
      base range の基準 ref を解決できない・索引が陳腐化している）
"""

from __future__ import annotations

import argparse
import io
import json
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
class ContractEntry:
    """索引 1 件。共有モジュール 1 本と、その内部実装を説明している利用側ファイル群の対応。"""

    module: str
    triggers: tuple[str, ...]
    consumers: tuple[str, ...]


# 索引（明示リスト・初期セットは実例 1 件だけ。実効性を確認してから広げる・#762）
CONTRACT_INDEX: tuple[ContractEntry, ...] = (
    ContractEntry(
        module="tools/git_diff_utils.py",
        triggers=(
            # PR #761 で実際に変わった分割方式。利用側 docstring が名指ししていた語そのもの
            "splitlines",
            # NUL 区切りへの移行で入った実装詳細（`_run_git_paths()` の注入とレコード区切り）
            "core.quotePath",
            "NUL 区切り",
            # `default_branch()` が base range を解決する手段（利用側が名指しで説明している）
            "symbolic-ref",
        ),
        consumers=(
            # collect_changed_files() の分割方式（splitlines → NUL 区切り）を docstring で説明している
            "tools/scan_dangerous_patterns.py",
            # default_branch() の解決手段（symbolic-ref 解決・main フォールバック）を docstring で説明している
            "tools/check_architecture_boundaries.py",
        ),
    ),
)


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
        if not entry.triggers:
            return f"{entry.module}: triggers が空です（トリガー語が無いと全差分が対象になり機能しません）"
        if not entry.consumers:
            return f"{entry.module}: consumers が空です（利用側が無い索引エントリは判定不能）"
        if entry.module in seen_modules:
            return f"{entry.module}: 同じ共有モジュールが複数の索引エントリに登録されています"
        seen_modules.add(entry.module)

        seen_consumers: set[str] = set()
        for consumer in entry.consumers:
            if consumer == entry.module:
                return f"{entry.module}: 利用側に自分自身が登録されています"
            if consumer in seen_consumers:
                return f"{entry.module}: 利用側 {consumer} が重複登録されています"
            seen_consumers.add(consumer)
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


def normalize_path(path: str, *, root: Path | None = None) -> str:
    """入力パスの表記揺れ（`./foo.py` / 絶対パス等）を索引の表記へそろえる。

    先頭ドット系の正規化は共有モジュール `git_diff_utils.normalize_leading_dots()` に委ねる
    （ここで再実装しない）。本関数が足すのは末尾の余白落としと、**リポジトリルート配下の
    絶対パスをルート相対へ畳む** 処理（シェル補完で絶対パスを渡すと索引と一致せず黙って
    合格していた・#762 の反例レビュー）。ルート外の絶対パスは索引と一致しようがないため
    そのまま返す。
    """
    text = path.strip()
    if root is not None:
        candidate = Path(text)
        if candidate.is_absolute():
            try:
                text = str(candidate.resolve().relative_to(root.resolve()))
            except (ValueError, OSError):
                pass
    return git_diff_utils.normalize_leading_dots(text)


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
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError) as exc:
        raise UndecidableError(
            f"{path}: Python として解析できないため説明文を取り出せません（{exc}）"
        ) from exc
    return "\n".join(
        tok.string for tok in tokens if tok.type in (tokenize.COMMENT, tokenize.STRING)
    )


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

    `git_diff_utils._run_git()` は private なので、本ツールは同等の薄いラッパーを持つ
    （公開関数として切り出すほどの実体が無く、`-c core.quotePath=false` の注入位置も本ツール側で
    決めたいため意図的に重複させる）。
    dup-ok: 3 行の subprocess ラッパー。共通化の実体が無いため意図的に重複させる（#762）
    """
    try:
        proc = runner(
            ["git", "-c", "core.quotePath=false", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return "", 1
    return proc.stdout, proc.returncode


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


def module_diff_touches_trigger(
    module: str,
    triggers: Sequence[str],
    *,
    root: Path,
    base: str,
    runner: Runner,
) -> tuple[bool, list[str]]:
    """共有モジュールの差分行にトリガー語が現れるかを判定し `(触れたか, 当たった語)` を返す。

    base range / worktree / cached の 3 ソースを見る。**pathspec 区切りの `--` を必ず付ける**
    （付けないと同名のブランチ・タグがあるときに git がパスではなく ref として解釈する）。

    3 ソースすべてが非ゼロで終わったときは `UndecidableError`（exit 2）へ倒す。git の非ゼロは
    「差分が無い」を意味しないため、`0` にも `1` にも丸めない（`check-tool-design-rules.md` §3）。
    """
    sources = (
        ["diff", "--unified=0", f"{base}...HEAD", "--", module],
        ["diff", "--unified=0", "--", module],
        ["diff", "--cached", "--unified=0", "--", module],
    )
    body: list[str] = []
    ok = 0
    for args in sources:
        stdout, rc = _run_git(args, cwd=root, runner=runner)
        if rc != 0:
            continue
        ok += 1
        body += _diff_body_lines(stdout)
    if ok == 0:
        raise UndecidableError(
            f"{module}: git diff が 3 ソースすべてで失敗しました（差分を確認できないため判定不能）"
        )
    hits = trigger_hits("\n".join(body), triggers)
    return bool(hits), hits


def ensure_base_reachable(base: str, *, root: Path, runner: Runner) -> None:
    """base range の基準 ref が解決できることを確かめる（解決できなければ判定不能へ倒す）。

    `git diff {base}...HEAD` は ref が無いと非ゼロで終わるが、`collect_changed_files()` も
    `module_diff_touches_trigger()` も **失敗したソースを黙って読み飛ばす**。その結果
    `origin/main` が無い環境（浅い clone・fetch 前）では **コミット済みの変更を 1 行も見ないまま
    ✅ を返す**（PASS しながら何も守らない最悪の失敗モード・`check-tool-design-rules.md` §0/§2）。
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
    - 利用側にトリガー語が 1 つも無い → 判定不能（説明文が既に消えているのに索引に残っている＝
      永久に何も守らない死んだエントリ。索引から外すか説明文を戻すかを人に決めさせる）
    """
    for entry in index:
        module_path = root / entry.module
        if not module_path.is_file():
            raise UndecidableError(
                f"索引の共有モジュールが存在しません: {entry.module}（索引を更新してください）"
            )
        for consumer in entry.consumers:
            consumer_path = root / consumer
            if not consumer_path.is_file():
                raise UndecidableError(
                    f"索引の利用側ファイルが存在しません: {consumer}（索引を更新してください）"
                )
            explanation = explanatory_text(consumer_path, read_text(consumer_path))
            if not trigger_hits(explanation, entry.triggers):
                raise UndecidableError(
                    f"{consumer}: 索引のトリガー語（{', '.join(entry.triggers)}）が"
                    "**説明文（コメント・docstring・文字列リテラル）の中に** 1 つも見つかりません。"
                    "説明文が既に消えているなら索引から外し、消えていないなら索引のトリガー語を直してください"
                )


def analyze(
    index: Sequence[ContractEntry],
    changed: Sequence[str],
    *,
    root: Path,
    use_git: bool,
    base: str,
    runner: Runner,
) -> list[dict]:
    """drift を判定して findings を返す（空リストなら合格）。"""
    changed_set = {normalize_path(p, root=root) for p in changed if p.strip()}
    findings: list[dict] = []

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
            # パス明示モードでは差分が取れないため「内部実装を触った」とみなす（fail-closed）
            hits = list(entry.triggers)
        missing = [c for c in entry.consumers if c not in changed_set]
        if missing:
            findings.append(
                {
                    "module": entry.module,
                    "triggers_hit": hits,
                    "stale_consumers": missing,
                }
            )
    return findings


def render_text(findings: Sequence[dict], scanned: int) -> int:
    if not findings:
        print(f"✅ 共有モジュールの内部実装に対する説明文 drift はありません（索引 {scanned} 件）")
        return 0
    for f in findings:
        print(
            f"⚠️ drift の疑い: {f['module']} の内部実装（{', '.join(f['triggers_hit'])}）を変更していますが、"
            "その実装を説明している次の利用側ファイルが同じ差分に含まれていません:",
            file=sys.stderr,
        )
        for c in f["stale_consumers"]:
            print(f"   - {c}", file=sys.stderr)
    print(
        "  → 説明文を現在の実装に合わせて更新するか、説明が今も正しいなら "
        "tools/check_module_contract_drift.py の CONTRACT_INDEX から外してください"
        "（理由をコミットメッセージに 1 行残す）",
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
        triggers=("splitlines", "NUL 区切り"),
        consumers=(_FIXTURE_A, _FIXTURE_B),
    ),
)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_fixture(root: Path) -> None:
    """索引が健全なフィクスチャを作る。

    利用側 2 本は説明の書き方を変えてある（#2 バリアント展開）:
      - A: docstring 内・小文字の `splitlines`
      - B: 行コメント内・大文字の `SPLITLINES`
    """
    _write(root, _FIXTURE_MODULE, '"""共有モジュール。NUL 区切りで分割する。"""\n')
    _write(root, _FIXTURE_A, '"""利用側 A。collect() は splitlines を使うため…"""\n')
    _write(root, _FIXTURE_B, "# 利用側 B: collect() は SPLITLINES を使う\nX = 1\n")
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
    import io

    out, err = io.StringIO(), io.StringIO()
    argv = ["--root", str(root)] + extra
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, runner=runner, index=index)
    return code, out.getvalue(), err.getvalue()


def _k(*args: str) -> tuple[str, ...]:
    return ("git", "-c", "core.quotePath=false", *args)


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
    dup_module = (
        ContractEntry(module="m.py", triggers=("t",), consumers=("a.py",)),
        ContractEntry(module="m.py", triggers=("t",), consumers=("b.py",)),
    )
    check("同一モジュールの二重登録は判定不能", validate_index(dup_module) is not None)
    dup_consumer = (
        ContractEntry(module="m.py", triggers=("t",), consumers=("a.py", "a.py")),
    )
    check("同一利用側の重複登録は判定不能", validate_index(dup_consumer) is not None)
    self_ref = (ContractEntry(module="m.py", triggers=("t",), consumers=("m.py",)),)
    check("利用側に自分自身を登録したら判定不能", validate_index(self_ref) is not None)
    empty_trig = (ContractEntry(module="m.py", triggers=(), consumers=("a.py",)),)
    check("triggers 空は判定不能", validate_index(empty_trig) is not None)
    empty_cons = (ContractEntry(module="m.py", triggers=("t",), consumers=()),)
    check("consumers 空は判定不能", validate_index(empty_cons) is not None)
    check("正常な索引は問題なし", validate_index(_FIXTURE_INDEX) is None)
    check("本番索引は問題なし", validate_index(CONTRACT_INDEX) is None)

    # ------------------------------------------------------------------ 2. パス明示モード
    print("2. パス明示モードの判定（main() 経由）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)

        code, out, err = _run_main(root, [_FIXTURE_MODULE, _FIXTURE_A, _FIXTURE_B])
        check("モジュールと全利用側が同じ差分 → exit 0", code == 0, f"code={code} err={err}")

        code, out, err = _run_main(root, [_FIXTURE_MODULE])
        check("利用側が差分に無い → exit 1", code == 1, f"code={code} out={out}")
        check(
            "警告に欠落した利用側 2 本が出る",
            _FIXTURE_A in err and _FIXTURE_B in err,
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

        # 索引の陳腐化（利用側から説明文が消えている）
        _write(root, _FIXTURE_B, "X = 1\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check("利用側にトリガー語が 1 つも無い → 判定不能(2)", code == 2, f"code={code} err={err}")

        # 陳腐化検知が「無関係なコード中の同語」で生き延びないこと（反例レビュー #762）
        # 説明文は消えているのに実装コードに `splitlines()` が残っているだけ、という形。
        # ファイル全文を対象にすると死んだ索引エントリが永久に生き残る（fail-open）。
        _write(root, _FIXTURE_B, "raw_lines = text.splitlines()\nX = 1\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check(
            "説明文が消え実装コードにだけトリガー語が残る利用側 → 判定不能(2)",
            code == 2,
            f"code={code} err={err}",
        )

        # 逆側（誤検知の抑制）: 説明が文字列リテラル・コメントにあるなら生きている
        _write(root, _FIXTURE_B, "# 利用側 B: collect() は SPLITLINES を使う\nX = 1\n")
        code, _, err = _run_main(root, [_FIXTURE_MODULE, _FIXTURE_A, _FIXTURE_B])
        check("説明がコメントにある利用側は健全（exit 0）", code == 0, f"code={code} err={err}")

        # 索引のファイルが消えた
        (root / _FIXTURE_A).unlink()
        code, _, err = _run_main(root, [_FIXTURE_MODULE])
        check("索引の利用側が存在しない → 判定不能(2)", code == 2, f"code={code} err={err}")

    # ------------------------------------------------------------------ 3. git モード
    print("3. git モード（--changed）と argv 検証（#710）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)

        changed_resp = {
            _k("diff", "--name-only", "-z", "origin/main...HEAD"): f"{_FIXTURE_MODULE}\0",
            _k("diff", "--name-only", "-z"): "",
            _k("diff", "--cached", "--name-only", "-z"): "",
            _k("ls-files", "--others", "--exclude-standard", "-z"): "",
        }
        trigger_diff = "@@\n-    parts = out.splitlines()\n+    parts = out.split('\\0')\n"
        diff_resp = {
            _k("diff", "--unified=0", "origin/main...HEAD", "--", _FIXTURE_MODULE): trigger_diff,
            _k("diff", "--unified=0", "--", _FIXTURE_MODULE): "",
            _k("diff", "--cached", "--unified=0", "--", _FIXTURE_MODULE): "",
        }
        calls: list[list[str]] = []
        runner = _make_recording_runner({**changed_resp, **diff_resp}, calls=calls)
        code, _, err = _run_main(root, ["--changed"], runner=runner)
        check("トリガー語を含む差分 + 利用側なし → exit 1", code == 1, f"code={code} err={err}")

        diff_calls = [c for c in calls if "--unified=0" in c]
        check("main() から git diff が実際に呼ばれている", bool(diff_calls), f"calls={calls}")
        check(
            "pathspec 区切りの `--` が省略されていない",
            all("--" in c and c.index("--") < c.index(_FIXTURE_MODULE) for c in diff_calls),
            f"diff_calls={diff_calls}",
        )
        check(
            "`-c core.quotePath=false` が注入されている",
            all(c[:3] == ["git", "-c", "core.quotePath=false"] for c in diff_calls),
            f"diff_calls={diff_calls}",
        )
        check(
            "3 ソース（base range / worktree / cached）すべてを見ている",
            len(diff_calls) == 3,
            f"diff_calls={diff_calls}",
        )

        # 誤検知の抑制: 同じモジュールを触っていてもトリガー語に当たらない差分なら合格
        no_trigger_diff = "@@\n+# コメントを 1 行足しただけ\n"
        runner2 = _make_recording_runner(
            {
                **changed_resp,
                _k("diff", "--unified=0", "origin/main...HEAD", "--", _FIXTURE_MODULE): no_trigger_diff,
                _k("diff", "--unified=0", "--", _FIXTURE_MODULE): "",
                _k("diff", "--cached", "--unified=0", "--", _FIXTURE_MODULE): "",
            }
        )
        code, out, err = _run_main(root, ["--changed"], runner=runner2)
        check("トリガー語に当たらない差分 → exit 0（誤検知の抑制）", code == 0, f"code={code} err={err}")

        # 本文が `--` / `++` で始まる差分行を diff ヘッダとして捨てないこと（反例レビュー #762）
        header_style_body = (
            "diff --git a/x b/x\nindex 111..222 100644\n"
            f"--- a/{_FIXTURE_MODULE}\n+++ b/{_FIXTURE_MODULE}\n"
            "@@ -1 +1 @@\n"
            "--- NUL 区切り --- （本文が `--` で始まる削除行）\n"
            "+++ splitlines へ戻した行（本文が `++` で始まる追加行）\n"
        )
        check(
            "diff のファイルヘッダ（`--- a/` / `+++ b/`）は本文に含めない",
            not any(l.startswith(("--- a/", "+++ b/")) for l in _diff_body_lines(header_style_body)),
            f"body={_diff_body_lines(header_style_body)}",
        )
        runner_hdr = _make_recording_runner(
            {
                **changed_resp,
                _k("diff", "--unified=0", "origin/main...HEAD", "--", _FIXTURE_MODULE): header_style_body,
                _k("diff", "--unified=0", "--", _FIXTURE_MODULE): "",
                _k("diff", "--cached", "--unified=0", "--", _FIXTURE_MODULE): "",
            }
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_hdr)
        check(
            "本文が `--`/`++` で始まる差分行のトリガー語も検出する → exit 1",
            code == 1,
            f"code={code} err={err}",
        )

        # base range の基準 ref が解決できない → 判定不能（コミット済み変更を見ないまま合格にしない）
        runner_nobase = _make_recording_runner(
            {**changed_resp, **diff_resp},
            fail_cmds=frozenset({_k("rev-parse", "--verify", "--quiet", "origin/main^{commit}")}),
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner_nobase)
        check(
            "base range の基準 ref が解決できない → 判定不能(2)",
            code == 2,
            f"code={code} err={err}",
        )

        # git diff が 3 ソースとも失敗 → 判定不能（0 にも 1 にも丸めない）
        runner3 = _make_recording_runner(
            changed_resp,
            fail_cmds=frozenset(diff_resp.keys()),
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner3)
        check("git diff が全ソース失敗 → 判定不能(2)", code == 2, f"code={code} err={err}")

        # 変更 0 件（日常的に起こりうる）→ 合格
        runner4 = _make_recording_runner(
            {
                _k("diff", "--name-only", "-z", "origin/main...HEAD"): "",
                _k("diff", "--name-only", "-z"): "",
                _k("diff", "--cached", "--name-only", "-z"): "",
                _k("ls-files", "--others", "--exclude-standard", "-z"): "",
            }
        )
        code, out, _ = _run_main(root, ["--changed"], runner=runner4)
        check("変更 0 件 → exit 0（変更起点の検査なので日常的）", code == 0, f"code={code}")

        # 利用側も同じ差分に含まれていれば合格
        runner5 = _make_recording_runner(
            {
                **diff_resp,
                _k("diff", "--name-only", "-z", "origin/main...HEAD"): (
                    f"{_FIXTURE_MODULE}\0{_FIXTURE_A}\0{_FIXTURE_B}\0"
                ),
                _k("diff", "--name-only", "-z"): "",
                _k("diff", "--cached", "--name-only", "-z"): "",
                _k("ls-files", "--others", "--exclude-standard", "-z"): "",
            }
        )
        code, _, err = _run_main(root, ["--changed"], runner=runner5)
        check("モジュールと利用側が同じ差分 → exit 0", code == 0, f"code={code} err={err}")

    # ------------------------------------------------------------------ 4. #762 回帰ケース
    print("4. Issue #762 の実例（git_diff_utils → scan_dangerous_patterns.py）")
    root = repo_root()
    code, _, err = _run_main(
        root, ["tools/git_diff_utils.py"], index=CONTRACT_INDEX
    )
    check(
        "git_diff_utils.py だけを変更 → scan_dangerous_patterns.py の説明文 drift を警告",
        code == 1 and "tools/scan_dangerous_patterns.py" in err,
        f"code={code} err={err}",
    )
    code, _, err = _run_main(
        root,
        [
            "tools/git_diff_utils.py",
            "tools/scan_dangerous_patterns.py",
            "tools/check_architecture_boundaries.py",
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
    r_self = subprocess.run(
        [sys.executable, script, "--self-test-inner"], capture_output=True, text=True
    )
    check("内部フラグは受け付けない（未知オプションは exit 2）", r_self.returncode == 2, r_self.stderr)
    r_ok = subprocess.run(
        [
            sys.executable,
            script,
            "tools/git_diff_utils.py",
            "tools/scan_dangerous_patterns.py",
            "tools/check_architecture_boundaries.py",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )
    check("実プロセス: 合格 = 0", r_ok.returncode == 0, r_ok.stderr)
    r_ng = subprocess.run(
        [sys.executable, script, "tools/git_diff_utils.py"],
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )
    check("実プロセス: drift = 1", r_ng.returncode == 1, r_ng.stderr)
    r_un = subprocess.run(
        [sys.executable, script, "--base", "--pwned", "--changed"],
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )
    check("実プロセス: 判定不能 = 2（オプション様の base）", r_un.returncode == 2, r_un.stderr)

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
            changed = collect_changed(root=root, runner=runner, base=base)
        else:
            changed = list(args.paths)
        findings = analyze(
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
                    "index_size": len(index),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if findings else 0
    return render_text(findings, len(index))


if __name__ == "__main__":
    sys.exit(main())
