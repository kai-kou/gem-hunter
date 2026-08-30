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

## 検査する違反（すべて fail-closed。判定できないものを PASS にしない）

  1. `.gitignore` による除外: `git check-ignore` が対象ファイルを「除外対象」と答えたら違反
  2. 有効行が 0 件（空ファイル・空行のみ）
  3. JSON としてパースできない行（クォート抜け・末尾カンマ等）
  4. トップレベルが JSON オブジェクトでない行（配列・文字列・数値）
  5. 必須フィールド（date / title / q1 / q2 / defer_reason / related_issue）の欠落
  6. 値域違反: q1 / q2 が "YES" / "NO" 以外、defer_reason が
     medium / over_quota / low_single_file 以外
  7. date が `YYYY-MM-DD JST` 形式でない、または実在しない日付（2026-13-45 JST 等）
  8. title が文字列でない、または空文字
  9. related_issue の型違反（下記「採用した仮定」を参照）

**空行の扱い**: 空白のみの行は「行の区切り」として **スキップする**（違反にしない）。JSONL の
末尾改行を違反にしないため。ただし有効行が 1 件も無ければ違反 4 として検出する（空ファイルを
「違反 0 件」として PASS させない）。

**記法は問わない**: `{"date": "..."}`（spaced）と `{"date":"..."}`（compact）はどちらも valid。
実データに両方が混在しているが、統一は本検査の目的ではない（Issue #704 のスコープ外）。

## 採用した仮定（実データ準拠・2026-08-30 JST 時点で 51 行を実測）

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
  2 = 判定不能（ファイル不在・デコード不能・git コマンド不在 / エラー）
      ※ 判定不能を 0 にしない（黙って PASS するのが最も危険な失敗モードであるため）

使い方:
  python3 tools/check_deferred_try_jsonl.py              # 本判定
  python3 tools/check_deferred_try_jsonl.py --self-test  # ネットワーク不要のユニットテスト
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

REQUIRED_FIELDS = ("date", "title", "q1", "q2", "defer_reason", "related_issue")
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
        violations.append(f"L{lineno}: 必須フィールドがありません: {', '.join(missing)}")

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
            f"{_fmt(obj['defer_reason'])}"
        )

    if "related_issue" in obj and not is_valid_related_issue(obj["related_issue"]):
        violations.append(
            f"L{lineno}: related_issue は null / 文字列 / 整数のいずれかである必要があります: "
            f"{_fmt(obj['related_issue'])}"
        )

    return violations


def check_text(text: str) -> tuple[list[str], int]:
    """JSONL 本文を検査し (違反メッセージ一覧, 有効行数) を返す。"""
    violations: list[str] = []
    valid_lines = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue  # 空行は行区切りとしてスキップ（有効行 0 件は下で違反にする）
        valid_lines += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            violations.append(f"L{lineno}: JSON としてパースできません: {e.msg}（col {e.colno}）")
            continue
        violations.extend(check_record(obj, lineno))

    if valid_lines == 0:
        violations.append("有効なレコードが 1 件もありません（空ファイル / 空行のみ）")
    return violations, valid_lines


def check_gitignored(path: Path, runner=subprocess.run) -> list[str]:
    """対象ファイルが `.gitignore` で除外されていないかを検査する。

    `git check-ignore -q` の終了コード: 0 = 除外されている / 1 = されていない / それ以外 = エラー。
    エラー（git 不在・リポジトリ外など）は「除外されていない」と決めつけず Undetermined を送出する
    （見逃し経路: git が無い環境で例外を握り潰して PASS にしてしまう fail-open）。
    """
    try:
        proc = runner(
            ["git", "check-ignore", "-q", str(path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise Undetermined(f"git コマンドが見つかりません: {e}") from e
    if proc.returncode == 0:
        return [f"{path} が .gitignore で除外されています（追跡されないとレトロの再発判定材料が失われます）"]
    if proc.returncode == 1:
        return []
    raise Undetermined(
        f"git check-ignore が想定外の終了コード {proc.returncode} を返しました: {(proc.stderr or '').strip()}"
    )


def check_file(path: Path) -> list[str]:
    """ファイル 1 本を検査して違反メッセージ一覧を返す。判定不能は Undetermined を送出する。"""
    if not path.exists():
        raise Undetermined(f"{path} が見つかりません")
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        raise Undetermined(f"{path} を UTF-8 テキストとして読み込めません: {e}") from e

    violations = check_gitignored(path)
    text_violations, _ = check_text(text)
    return violations + text_violations


# --------------------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------------------

VALID_LINE = (
    '{"date": "2026-08-24 JST", "title": "サンプル Try", "q1": "NO", "q2": "NO", '
    '"defer_reason": "medium", "related_issue": null}'
)


class _FakeProc:
    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr


def _run_self_test() -> None:
    # --- check_text: 正常系 ---
    v, n = check_text(VALID_LINE + "\n")
    assert v == [] and n == 1, f"ケース1 失敗: {v} / {n}"

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
    assert v == [] and n == 3, f"ケース2 失敗: {v} / {n}"

    # --- 入力バリアント: 壊れ方を変えて実証する ---
    # (a) クォート抜け（JSON パース不能）
    v, _ = check_text('{"date": "2026-08-24 JST", title: "x"}\n')
    assert len(v) == 1 and "パースできません" in v[0], f"ケース3 失敗: {v}"

    # (b) 必須フィールド欠落（related_issue と q2 が無い）
    v, _ = check_text('{"date": "2026-08-24 JST", "title": "x", "q1": "NO", "defer_reason": "medium"}\n')
    assert len(v) == 1 and "q2" in v[0] and "related_issue" in v[0], f"ケース4 失敗: {v}"

    # (c) 値域外（q1 / defer_reason）
    v, _ = check_text(VALID_LINE.replace('"q1": "NO"', '"q1": "no"').replace('"medium"', '"high"'))
    assert len(v) == 2, f"ケース5 失敗: {v}"

    # (d) 日付形式違反（JST 無し / 実在しない日 / 桁不足）
    for bad_date in ("2026-08-24", "2026-13-45 JST", "2026-8-3 JST", "2026-08-24 UTC", 20260824):
        line = json.dumps(
            {
                "date": bad_date,
                "title": "x",
                "q1": "NO",
                "q2": "NO",
                "defer_reason": "medium",
                "related_issue": None,
            },
            ensure_ascii=False,
        )
        v, _ = check_text(line + "\n")
        assert len(v) == 1 and "date" in v[0], f"ケース6 失敗({bad_date}): {v}"

    # (e) title 空文字・非文字列
    v, _ = check_text(VALID_LINE.replace('"サンプル Try"', '"   "'))
    assert len(v) == 1 and "title" in v[0], f"ケース7 失敗: {v}"

    # (f) related_issue の型違反（bool / 配列）
    for bad in ("true", "[1]"):
        v, _ = check_text(VALID_LINE.replace("null", bad))
        assert len(v) == 1 and "related_issue" in v[0], f"ケース8 失敗({bad}): {v}"

    # (g) トップレベルが配列 / 文字列
    v, _ = check_text('[{"date": "2026-08-24 JST"}]\n')
    assert len(v) == 1 and "オブジェクトではありません" in v[0], f"ケース9 失敗: {v}"

    # (h) 空ファイル・空行のみ → fail-closed（違反 0 件で PASS させない）
    for empty in ("", "\n", "   \n\n"):
        v, n = check_text(empty)
        assert n == 0 and len(v) == 1 and "1 件もありません" in v[0], f"ケース10 失敗({empty!r}): {v}"

    # --- check_gitignored: 3 分岐すべて ---
    assert check_gitignored(Path("x"), runner=lambda *a, **k: _FakeProc(1)) == [], "ケース11 失敗"
    ignored = check_gitignored(Path("x"), runner=lambda *a, **k: _FakeProc(0))
    assert len(ignored) == 1 and ".gitignore" in ignored[0], f"ケース12 失敗: {ignored}"
    for bad_runner, label in (
        (lambda *a, **k: _FakeProc(128, "fatal"), "exit 128"),
        (_raise_file_not_found, "git 不在"),
    ):
        try:
            check_gitignored(Path("x"), runner=bad_runner)
        except Undetermined:
            pass
        else:  # pragma: no cover - 失敗時のみ到達
            raise AssertionError(f"ケース13 失敗（{label} を PASS にしてしまった）")

    # --- main() から exit code までの貫通確認 ---
    # main() の出力（PASS / ❌ / ⚠️）は self-test の結果ではないため飲み込む。
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix=".tmp_deferred_try_selftest_") as tmp, \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ok_path = Path(tmp) / "ok.jsonl"
        ok_path.write_text(VALID_LINE + "\n", encoding="utf-8")
        rc = main(["--path", str(ok_path)])
        assert rc == EXIT_OK, f"ケース14 失敗（正常データで exit {rc}）"

        ng_path = Path(tmp) / "ng.jsonl"
        ng_path.write_text('{"date": "2026-08-24 JST"}\n', encoding="utf-8")
        rc = main(["--path", str(ng_path)])
        assert rc == EXIT_VIOLATION, f"ケース15 失敗（違反データで exit {rc}）"

        rc = main(["--path", str(Path(tmp) / "missing.jsonl")])
        assert rc == EXIT_UNDETERMINED, f"ケース16 失敗（ファイル不在で exit {rc}）"

        bin_path = Path(tmp) / "bin.jsonl"
        bin_path.write_bytes(b"\xff\xfe\x00binary")
        rc = main(["--path", str(bin_path)])
        assert rc == EXIT_UNDETERMINED, f"ケース17 失敗（非 UTF-8 で exit {rc}）"

    print("[deferred-try-jsonl] self-test OK（17 ケース）")


def _raise_file_not_found(*args, **kwargs):
    raise FileNotFoundError("git")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="見送り Try ログ（deferred_try.jsonl）の整形性検査")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行する")
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

    path = Path(args.path) if args.path else DEFERRED_TRY_PATH
    try:
        violations = check_file(path)
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
