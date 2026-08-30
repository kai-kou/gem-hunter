#!/usr/bin/env python3
"""check_deferred_try_jsonl.py — 見送り Try ログ（deferred_try.jsonl）の整形性を検査する（Issue #704）

## なぜ必要か

`content/analytics/retro/deferred_try.jsonl` は `retrospective` スキル Step 3-0（Q1 再発判定）の
中核データで、**次回以降のレトロが読み戻して「同じ Try が再発しているか」を判定する** ための
唯一の記録である。1 行でも壊れる（JSON パース不能・必須フィールド欠落・値域外）と、その行は
判定材料から静かに脱落する。さらに `.gitignore` は `content/analytics/*` を除外したうえで
`!content/analytics/retro/` で本ディレクトリだけを復活させる **反転パターン** に依存しており、
除外規則を少し触るだけで追跡対象から外れ、クラウドではコンテナ破棄とともに消える（#417）。
どちらも「壊れても誰も気づかない」失敗モードなので機械検査する。

## ignore 状態ではなく「追跡状態」を検査する理由

守りたい不変条件は「このファイルが **git に追跡されている**（＝コンテナ破棄後も残る）」ことで
あって「`.gitignore` にマッチしないこと」ではない。かつ `git check-ignore` は既定で index を
参照するため、**追跡済みファイルは `.gitignore` にマッチしても常に exit 1（＝除外されていない）**
を返す。つまり check-ignore ベースの検査は「除外されている」分岐に到達できない死に枝で、
再包含行 `!content/analytics/retro/` を削除しても PASS する fail-open だった。そのため本検査は
`git ls-files --error-unmatch` で **追跡状態そのもの** を見る（0 = 追跡済み / 1 = 未追跡 /
それ以外 = 判定不能）。

## 検査する違反（すべて fail-closed。判定できないものを PASS にしない）

  1. git の追跡対象になっていない（`git ls-files --error-unmatch` が未追跡と答える）
  2. 有効行が 0 件（空ファイル・空行のみ）
  3. JSON としてパースできない行（クォート抜け・末尾カンマ等）
  4. トップレベルが JSON オブジェクトでない行（配列・文字列・数値）
  5. 必須フィールド（date / title / q1 / q2 / defer_reason）の欠落
  6. 値域違反: q1 / q2 が "YES" / "NO" 以外、defer_reason が
     medium / over_quota / low_single_file 以外
  7. date が `YYYY-MM-DD JST` 形式でない、または実在しない日付（2026-13-45 JST 等）
  8. title が文字列でない、または空文字
  9. related_issue の型違反（**存在する場合のみ** 検査。下記「採用した仮定」を参照）

**空行の扱い**: 空白のみの行は「行の区切り」として **スキップする**（違反にしない）。JSONL の
末尾改行を違反にしないため。ただし有効行が 1 件も無ければ違反 2 として検出する（空ファイルを
「違反 0 件」として PASS させない）。

**記法は問わない**: `{"date": "..."}`（spaced）と `{"date":"..."}`（compact）はどちらも valid。
実データに両方が混在しているが、統一は本検査の目的ではない（Issue #704 のスコープ外）。

## 採用した仮定（実データ準拠・2026-08-30 JST 時点で 51 行を実測）

  - 必須フィールドは Issue #704 が定める 5 件（date / title / q1 / q2 / defer_reason）とする。
    `related_issue` は実データ 51 行すべてに存在するが **仕様上の必須ではない** ため必須にせず、
    「存在する場合のみ型を検査する」に留める（権威順: 仕様 > 現行コード）。
  - `related_issue` は `null` / 文字列 のほかに **整数** も許容する。実データに
    `"related_issue": 660`（int）が 2 件あり、Issue 番号として意味が通る（`"L-138"` のような
    lessons ID も文字列で入る）。「実データと矛盾する仕様を先に決めない」方針に従い、
    int を弾く仕様にはしない。ただし `bool`（`true` / `false`）は Issue 参照として無意味なので
    弾く（Python では `bool` が `int` の派生であるため明示的に除外している）。
  - `date` は実データ 51 行すべてが `YYYY-MM-DD JST`（14 文字）だったため、この形式を必須とする
    （`docs/rules/datetime-rules.md`: 記録に残る日時は JST 表記）。

## 終了コード

  0 = 違反なし
  1 = 違反あり
  2 = 判定不能（ファイル不在・デコード不能・JSON のネストが深すぎる・git コマンド不在 / エラー）
      ※ 判定不能を 0 にしない（黙って PASS するのが最も危険な失敗モードであるため）

使い方:
  python3 tools/check_deferred_try_jsonl.py              # 本判定
  python3 tools/check_deferred_try_jsonl.py --self-test  # ネットワーク・git 非依存のユニットテスト
  python3 tools/check_deferred_try_jsonl.py --path FILE  # 別ファイルを検査（デバッグ / self-test 用）
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFERRED_TRY_PATH = REPO_ROOT / "content" / "analytics" / "retro" / "deferred_try.jsonl"

# SSOT: .claude/skills/retrospective/SKILL.md §「見送りログのフィールド」表
SKILL_FIELD_SSOT = ".claude/skills/retrospective/SKILL.md §「見送りログのフィールド」表"
REQUIRED_FIELDS = ("date", "title", "q1", "q2", "defer_reason")
YES_NO = ("YES", "NO")
DEFER_REASONS = ("medium", "over_quota", "low_single_file")
DATE_SUFFIX = " JST"
DATE_FORMAT = "%Y-%m-%d"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_UNDETERMINED = 2


class Undetermined(Exception):
    """判定不能（違反ゼロではない）を表す例外。握り潰さず main まで伝播させて exit 2 にする。"""


def _fmt(value: object) -> str:
    """違反メッセージ用に値を短く表示する（長い title で行が溢れないように切り詰める）。"""
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def is_valid_jst_date(value: object) -> bool:
    """`YYYY-MM-DD JST` 形式で、かつ実在する日付なら True。

    正規表現だけだと `2026-13-45 JST` を通してしまうため `strptime` で実在日まで検証する
    （見逃し経路: 形式一致 = 妥当という思い込み）。
    """
    if not isinstance(value, str) or not value.endswith(DATE_SUFFIX):
        return False
    head = value[: -len(DATE_SUFFIX)]
    if len(head) != 10:  # strptime は "2026-8-3" のような桁不足も通すため長さを固定する
        return False
    try:
        datetime.strptime(head, DATE_FORMAT)
    except ValueError:
        return False
    return True


def is_valid_related_issue(value: object) -> bool:
    """related_issue は null / 文字列 / 整数のみ許容する（bool は除外・docstring「採用した仮定」）。"""
    if value is None or isinstance(value, str):
        return True
    return isinstance(value, int) and not isinstance(value, bool)


def check_record(obj: object, lineno: int) -> list[str]:
    """1 レコード分の違反メッセージ一覧を返す（違反なしなら空リスト）。"""
    if not isinstance(obj, dict):
        return [f"L{lineno}: トップレベルが JSON オブジェクトではありません（{type(obj).__name__}）"]

    violations: list[str] = []
    missing = [f for f in REQUIRED_FIELDS if f not in obj]
    if missing:
        violations.append(
            f"L{lineno}: 必須フィールドがありません: {', '.join(missing)}（SSOT: {SKILL_FIELD_SSOT}）"
        )

    if "title" in obj:
        title = obj["title"]
        if not isinstance(title, str) or not title.strip():
            violations.append(f"L{lineno}: title は空でない文字列である必要があります: {_fmt(title)}")

    if "date" in obj and not is_valid_jst_date(obj["date"]):
        violations.append(
            f"L{lineno}: date は `YYYY-MM-DD JST` 形式の実在日である必要があります: {_fmt(obj['date'])}"
        )

    for field in ("q1", "q2"):
        if field in obj and obj[field] not in YES_NO:
            violations.append(
                f"L{lineno}: {field} は {' / '.join(YES_NO)} のいずれかである必要があります: {_fmt(obj[field])}"
            )

    if "defer_reason" in obj and obj["defer_reason"] not in DEFER_REASONS:
        violations.append(
            f"L{lineno}: defer_reason は {' / '.join(DEFER_REASONS)} のいずれかである必要があります: "
            f"{_fmt(obj['defer_reason'])}（SSOT: {SKILL_FIELD_SSOT}）"
        )

    if "related_issue" in obj and not is_valid_related_issue(obj["related_issue"]):
        violations.append(
            f"L{lineno}: related_issue は null / 文字列 / 整数のいずれかである必要があります: "
            f"{_fmt(obj['related_issue'])}"
        )

    return violations


def check_text(text: str) -> tuple[list[str], int]:
    """JSONL 本文を検査し (違反メッセージ一覧, 有効行数) を返す。

    行分割は `str.splitlines()` ではなく `split("\\n")` を使う（`splitlines()` は U+2028 /
    U+2029 / U+0085 等でも分割するため、それらを値に含む整形式の 1 レコードが 2 行に割れて
    偽陽性になり、以降の行番号もずれる）。CRLF 互換のため各行末の `\\r` だけ取り除く。
    """
    violations: list[str] = []
    valid_lines = 0
    for lineno, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue  # 空行は行区切りとしてスキップ（有効行 0 件は下で違反にする）
        valid_lines += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            violations.append(f"L{lineno}: JSON としてパースできません: {e.msg}（col {e.colno}）")
            continue
        except RecursionError as e:
            # 深くネストした JSON はパース中に再帰上限へ達する。違反（exit 1）ではなく
            # 判定不能（exit 2）へ振り分ける（生 traceback で落として違反に化けさせない）。
            raise Undetermined(f"L{lineno}: JSON のネストが深すぎて解析できません: {e}") from e
        violations.extend(check_record(obj, lineno))

    if valid_lines == 0:
        violations.append("有効なレコードが 1 件もありません（空ファイル / 空行のみ）")
    return violations, valid_lines


def check_tracked(path: Path, runner=subprocess.run, repo_root: Path = REPO_ROOT) -> list[str]:
    """対象ファイルが git の追跡対象（index 登録済み）かを検査する。

    `git ls-files --error-unmatch -- <path>` の終了コード:
      0 = 追跡済み（OK） / 1 = 未追跡（違反） / それ以外 = エラー。
    エラー（git 不在・タイムアウト・リポジトリ外など）は「追跡済み」と決めつけず Undetermined を
    送出する（見逃し経路: git が無い環境で例外を握り潰して PASS にしてしまう fail-open）。
    `--` で pathspec の開始位置を明示し、`-` 始まりのパスがオプションと誤解釈されるのを防ぐ。
    """
    try:
        proc = runner(
            ["git", "ls-files", "--error-unmatch", "--", str(path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as e:
        raise Undetermined(f"git コマンドが見つかりません: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise Undetermined(f"git ls-files がタイムアウトしました: {e}") from e
    if proc.returncode == 0:
        return []
    if proc.returncode == 1:
        return [
            f"{path} が git の追跡対象になっていません"
            "（追跡されないとコンテナ破棄でレトロの再発判定材料が失われます）"
        ]
    raise Undetermined(
        f"git ls-files が想定外の終了コード {proc.returncode} を返しました: {(proc.stderr or '').strip()}"
    )


def check_file(path: Path, runner=subprocess.run, repo_root: Path = REPO_ROOT) -> list[str]:
    """ファイル 1 本を検査して違反メッセージ一覧を返す。判定不能は Undetermined を送出する。"""
    if not path.exists():
        raise Undetermined(f"{path} が見つかりません")
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        raise Undetermined(f"{path} を UTF-8 テキストとして読み込めません: {e}") from e

    if path.is_relative_to(repo_root):
        violations = check_tracked(path, runner=runner, repo_root=repo_root)
    else:
        # リポジトリ外のパス（--path でのデバッグ指定等）は git 追跡を問えないため内容検査だけ行う。
        # 判定できなかったことを黙らせず 1 行出力する（exit 2 にはしない）。
        print(f"ℹ️ {path} はリポジトリ外のため git 追跡検査をスキップします")
        violations = []
    text_violations, _ = check_text(text)
    return violations + text_violations


# --------------------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------------------

VALID_RECORD = {
    "date": "2026-08-24 JST",
    "title": "サンプル Try",
    "q1": "NO",
    "q2": "NO",
    "defer_reason": "medium",
    "related_issue": None,
}
VALID_LINE = (
    '{"date": "2026-08-24 JST", "title": "サンプル Try", "q1": "NO", "q2": "NO", '
    '"defer_reason": "medium", "related_issue": null}'
)


class _FakeProc:
    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr


class _RecordingRunner:
    """git を起動せず固定の終了コードを返す fake runner（呼ばれた事実とコマンドを記録する）。"""

    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        return _FakeProc(self.returncode, self.stderr)


def _line(**overrides) -> str:
    """VALID_RECORD をベースに 1 行分の JSONL を組み立てる（キーを消したいときは dict を直接操作する）。"""
    record = dict(VALID_RECORD)
    record.update(overrides)
    return json.dumps(record, ensure_ascii=False)


def _run_self_test() -> None:
    cases = 0  # ケース数はハードコードせず実測で数える

    # --- check_text: 正常系 ---
    v, n = check_text(VALID_LINE + "\n")
    assert v == [] and n == 1, f"正常系 失敗: {v} / {n}"
    cases += 1

    # compact 記法・int / 文字列 related_issue・末尾空行の混在も PASS（記法統一は求めない）
    mixed = (
        VALID_LINE
        + "\n"
        + '{"date":"2026-08-27 JST","title":"compact","q1":"YES","q2":"NO",'
        '"defer_reason":"low_single_file","related_issue":"L-138"}\n'
        + '{"date":"2026-08-28 JST","title":"int issue","q1":"NO","q2":"YES",'
        '"defer_reason":"over_quota","related_issue":660}\n'
        "\n"
    )
    v, n = check_text(mixed)
    assert v == [] and n == 3, f"記法混在 失敗: {v} / {n}"
    cases += 1

    # related_issue は必須ではない（キーごと無い行も PASS・仕様は 5 フィールド）
    no_related = dict(VALID_RECORD)
    del no_related["related_issue"]
    v, n = check_text(json.dumps(no_related, ensure_ascii=False) + "\n")
    assert v == [] and n == 1, f"related_issue 省略 失敗: {v}"
    cases += 1

    # CRLF 改行でも行が壊れない
    v, n = check_text(VALID_LINE + "\r\n")
    assert v == [] and n == 1, f"CRLF 失敗: {v} / {n}"
    cases += 1

    # U+2028 / U+2029 / U+0085 を値に含む 1 レコードを 2 行に割らない（splitlines 過剰一致の回帰）
    for sep in ("\u2028", "\u2029", "\u0085"):  # 見えない文字はエスケープで明示する
        v, n = check_text(_line(title=f"行内{sep}区切り") + "\n")
        assert v == [] and n == 1, f"行分割 失敗({sep!r}): {v} / {n}"
    cases += 1

    # --- 入力バリアント: 壊れ方を変えて実証する ---
    # (a) クォート抜け（JSON パース不能）
    v, _ = check_text('{"date": "2026-08-24 JST", title: "x"}\n')
    assert len(v) == 1 and "パースできません" in v[0], f"パース不能 失敗: {v}"
    cases += 1

    # (b-1) 仕様（Issue #704）が定める 5 フィールドと定数が一致していることをリテラルで固定する。
    #       下のループは REQUIRED_FIELDS を走査するため「定数から 1 語消す」変異はループだけでは
    #       検出できない（ケースごと消えてしまう）。仕様側の期待値をここに直書きして殺す。
    assert set(REQUIRED_FIELDS) == {"date", "title", "q1", "q2", "defer_reason"}, (
        f"必須フィールド定義が仕様（Issue #704 / {SKILL_FIELD_SSOT}）とずれています: {REQUIRED_FIELDS}"
    )
    cases += 1

    # (b-2) 必須フィールド欠落: REQUIRED_FIELDS を 1 件ずつ落として当該フィールド名が出ることを確認する
    #       （フィールドを増やしてもメッセージ検証は自動追随する）
    for field in REQUIRED_FIELDS:
        broken = dict(VALID_RECORD)
        del broken[field]
        v, _ = check_text(json.dumps(broken, ensure_ascii=False) + "\n")
        assert len(v) == 1 and field in v[0], f"必須欠落 失敗({field}): {v}"
        cases += 1

    # (c) 値域外: q1 / q2 / defer_reason を 1 件ずつ単独で壊す（まとめず分離する）
    for field, bad in (("q1", "no"), ("q2", "yes"), ("defer_reason", "high")):
        v, _ = check_text(_line(**{field: bad}) + "\n")
        assert len(v) == 1 and field in v[0], f"値域違反 失敗({field}): {v}"
        cases += 1

    # (d) 日付形式違反（JST 無し / 実在しない日 / 桁不足 / 別 TZ / 非文字列）
    for bad_date in ("2026-08-24", "2026-13-45 JST", "2026-8-3 JST", "2026-08-24 UTC", 20260824):
        v, _ = check_text(_line(date=bad_date) + "\n")
        assert len(v) == 1 and "date" in v[0], f"日付違反 失敗({bad_date}): {v}"
        cases += 1

    # (e) title 空文字・非文字列（数値 / null）
    for bad_title in ("   ", 123, None):
        try:
            v, _ = check_text(_line(title=bad_title) + "\n")
        except Exception as e:  # 非文字列 title で例外が漏れる実装退行を FAIL として表面化する
            raise AssertionError(f"title 違反 失敗({bad_title!r}): 例外が漏れました: {e!r}") from e
        assert len(v) == 1 and "title" in v[0], f"title 違反 失敗({bad_title!r}): {v}"
        cases += 1

    # (f) related_issue の型違反（bool / 配列）
    for bad in (True, [1]):
        v, _ = check_text(_line(related_issue=bad) + "\n")
        assert len(v) == 1 and "related_issue" in v[0], f"related_issue 違反 失敗({bad!r}): {v}"
        cases += 1

    # (g) トップレベルが配列 / 文字列
    v, _ = check_text('[{"date": "2026-08-24 JST"}]\n')
    assert len(v) == 1 and "オブジェクトではありません" in v[0], f"非オブジェクト 失敗: {v}"
    cases += 1

    # (h) 行番号の採番: 2 行目だけを壊し L2 として報告されることを確認（start=1 の回帰）
    v, _ = check_text(VALID_LINE + "\n" + _line(q1="no") + "\n")
    assert len(v) == 1 and v[0].startswith("L2:"), f"行番号 失敗: {v}"
    cases += 1

    # (i) 空ファイル・空行のみ → fail-closed（違反 0 件で PASS させない）
    for empty in ("", "\n", "   \n\n"):
        v, n = check_text(empty)
        assert n == 0 and len(v) == 1 and "1 件もありません" in v[0], f"空ファイル 失敗({empty!r}): {v}"
        cases += 1

    # (j) 深すぎるネストは違反ではなく判定不能（RecursionError の振り分け）
    deep = "[" * 200_000 + "]" * 200_000
    try:
        check_text(deep + "\n")
    except Undetermined:
        pass
    except RecursionError:  # pragma: no cover - 変異検出時のみ到達
        raise AssertionError("深いネスト 失敗（RecursionError が素通りした）")
    else:  # pragma: no cover - 変異検出時のみ到達
        raise AssertionError("深いネスト 失敗（判定不能にならなかった）")
    cases += 1

    # --- check_tracked: 全分岐（git を起動しない fake runner で検証する） ---
    tracked = _RecordingRunner(0)
    assert check_tracked(Path("x"), runner=tracked) == [], "追跡済み 失敗"
    assert tracked.calls and "--error-unmatch" in tracked.calls[0], f"呼び出し形 失敗: {tracked.calls}"
    cases += 1

    untracked = check_tracked(Path("x"), runner=_RecordingRunner(1))
    assert len(untracked) == 1 and "追跡対象になっていません" in untracked[0], f"未追跡 失敗: {untracked}"
    cases += 1

    for bad_runner, label in (
        (_RecordingRunner(128, "fatal"), "exit 128"),
        (_raise_file_not_found, "git 不在"),
        (_raise_timeout, "タイムアウト"),
    ):
        try:
            check_tracked(Path("x"), runner=bad_runner)
        except Undetermined:
            pass
        else:  # pragma: no cover - 失敗時のみ到達
            raise AssertionError(f"判定不能 失敗（{label} を PASS にしてしまった）")
        cases += 1

    # --- main() から exit code までの貫通確認（システム一時領域 = リポジトリ外で行う） ---
    # main() の出力（PASS / ❌ / ⚠️）は self-test の結果ではないため飲み込む。
    with tempfile.TemporaryDirectory() as tmp, \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        tmp_root = Path(tmp).resolve()
        ok_path = tmp_root / "ok.jsonl"
        ok_path.write_text(VALID_LINE + "\n", encoding="utf-8")
        rc = main(["--path", str(ok_path)])
        assert rc == EXIT_OK, f"main 正常系 失敗（exit {rc}）"

        ng_path = tmp_root / "ng.jsonl"
        ng_path.write_text('{"date": "2026-08-24 JST"}\n', encoding="utf-8")
        rc = main(["--path", str(ng_path)])
        assert rc == EXIT_VIOLATION, f"main 違反系 失敗（exit {rc}）"

        rc = main(["--path", str(tmp_root / "missing.jsonl")])
        assert rc == EXIT_UNDETERMINED, f"main ファイル不在 失敗（exit {rc}）"

        bin_path = tmp_root / "bin.jsonl"
        bin_path.write_bytes(b"\xff\xfe\x00binary")
        rc = main(["--path", str(bin_path)])
        assert rc == EXIT_UNDETERMINED, f"main 非 UTF-8 失敗（exit {rc}）"

        # git 追跡検査が main まで配線されていることの確認（呼び出しごと消す変異を殺す）:
        # 一時ディレクトリを repo_root に見立て、fake runner が「未追跡」を返したら
        # 内容が正常でも違反終了すること・runner が実際に呼ばれたことを確認する。
        untracked_runner = _RecordingRunner(1)
        rc = main(["--path", str(ok_path)], runner=untracked_runner, repo_root=tmp_root)
        assert untracked_runner.calls, "main 追跡検査 失敗（git 検査が呼ばれていない）"
        assert rc == EXIT_VIOLATION, f"main 追跡検査 失敗（未追跡なのに exit {rc}）"

        tracked_runner = _RecordingRunner(0)
        rc = main(["--path", str(ok_path)], runner=tracked_runner, repo_root=tmp_root)
        assert tracked_runner.calls and rc == EXIT_OK, f"main 追跡済み 失敗（exit {rc}）"
    cases += 6

    print(f"[deferred-try-jsonl] self-test OK（{cases} ケース）")


def _raise_file_not_found(*args, **kwargs):
    raise FileNotFoundError("git")


def _raise_timeout(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd="git ls-files", timeout=10)


def main(argv: list[str] | None = None, runner=subprocess.run, repo_root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description="見送り Try ログ（deferred_try.jsonl）の整形性検査")
    parser.add_argument(
        "--self-test", action="store_true", help="ネットワーク・git 非依存のユニットテストを実行する"
    )
    parser.add_argument(
        "--path",
        default=None,
        help=f"検査対象の JSONL（既定: {DEFERRED_TRY_PATH.relative_to(REPO_ROOT)}）",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        try:
            _run_self_test()
            return EXIT_OK
        except AssertionError as e:
            print(f"❌ [deferred-try-jsonl] self-test FAIL: {e}", file=sys.stderr)
            return EXIT_VIOLATION

    # CWD 基準の相対パスと git（cwd=repo_root）へ渡すパスが食い違わないよう絶対パスへ正規化する
    path = Path(args.path).expanduser().resolve() if args.path else DEFERRED_TRY_PATH
    try:
        violations = check_file(path, runner=runner, repo_root=repo_root)
    except Undetermined as e:
        print(f"⚠️ 判定不能: {e}", file=sys.stderr)
        return EXIT_UNDETERMINED

    if violations:
        for v in violations:
            print(f"❌ {v}", file=sys.stderr)
        print(f"❌ [deferred-try-jsonl] FAIL: {len(violations)} 件の違反（{path}）", file=sys.stderr)
        return EXIT_VIOLATION

    print(f"[deferred-try-jsonl] PASS: {path} の整形性に問題なし")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
