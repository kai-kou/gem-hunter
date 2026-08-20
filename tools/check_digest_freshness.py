#!/usr/bin/env python3
"""check_digest_freshness.py — 配信データ（daily-digest.json）の鮮度チェックと自己修復（E-25）

【設計思想（NFR-8）】
バッチ生成（`tools/generate_gem_digest.mjs`）が止まっても配信自体は止めない。
劣化するのは「鮮度」だけであり、配信済み JSON はそのまま出し続ける。本ツールは
その劣化を検知するための **監視** であって、配信の可否を判定するゲートではない。

【判定ロジック】
  1. `public/data/daily-digest.json`（既定パス）を読み、`meta.generatedAt`（ISO 8601 UTC）を
     パースする。
  2. 現在時刻（UTC）との経過時間を計算し、`--max-age-hours`（既定 48）と比較する。
     - 経過時間が閾値以内 → fresh（終了コード 0）
     - 閾値超過 → stale（終了コード 1）
  3. ファイル不在・JSON 破損・`meta.generatedAt` 欠落 / 非 ISO 形式は「鮮度不明」として扱う
     （終了コード 2）。配信停止の意味ではなく、監視側が要注意として検知するためのシグナル。
     例外で落とさず、理由をメッセージに含めて正常終了（プロセスとしては非ゼロ終了）する。

【自己修復（--heal）】
stale 検知時のみ `node tools/generate_gem_digest.mjs` を subprocess 実行して再生成を試みる。
ネットワーク不通等で失敗しても、配信済み JSON はそのまま残す（上書き・削除しない）。
`--heal` は `tools/run_checks.sh` からは呼び出さない（ネットワーク非依存を保つ・E-25 要件）。

【日時ルール】
表示・記録する日時は JST（`YYYY-MM-DD HH:MM JST`）、経過時間の内部計算は UTC
（`datetime.now(timezone.utc)`）。`datetime.utcnow()` や TZ 未指定 `datetime.now()` は使わない
（`docs/rules/datetime-rules.md`）。

使い方:
    python3 tools/check_digest_freshness.py
    python3 tools/check_digest_freshness.py --json
    python3 tools/check_digest_freshness.py --max-age-hours 24
    python3 tools/check_digest_freshness.py --heal
    python3 tools/check_digest_freshness.py --self-test    # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIGEST_PATH = REPO_ROOT / "public" / "data" / "daily-digest.json"
DEFAULT_GENERATOR = REPO_ROOT / "tools" / "generate_gem_digest.mjs"

JST = timezone(timedelta(hours=9))

# 終了コード
EXIT_FRESH = 0
EXIT_STALE = 1
EXIT_UNKNOWN = 2


def now_jst_str(dt_utc: datetime | None = None) -> str:
    """表示・記録用の現在時刻（JST）。機械処理には使わない（datetime-rules.md）。"""
    dt = dt_utc if dt_utc is not None else datetime.now(timezone.utc)
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")


def parse_generated_at(value: str) -> datetime:
    """ISO 8601（`Z` サフィックス含む）を UTC aware datetime にパースする。不正なら ValueError。"""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        # タイムゾーン情報のない ISO 文字列は UTC とみなす（generatedAt は UTC 生成が前提）
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate(digest_path: Path, max_age_hours: float, now_utc: datetime | None = None) -> dict:
    """鮮度判定結果を dict で返す。例外は投げない（呼び出し側で判定不能として扱う情報を含める）。"""
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    result: dict = {
        "fresh": None,
        "generated_at": None,
        "generated_at_jst": None,
        "age_hours": None,
        "threshold_hours": max_age_hours,
        "path": str(digest_path),
        "checked_at_jst": now_jst_str(now),
        "status": None,  # "fresh" | "stale" | "unknown"
        "reason": None,
    }

    if not digest_path.exists():
        result["status"] = "unknown"
        result["reason"] = f"配信データが見つかりません: {digest_path}"
        return result

    try:
        raw = digest_path.read_text(encoding="utf-8")
    except OSError as e:
        result["status"] = "unknown"
        result["reason"] = f"配信データの読み込みに失敗しました: {e}"
        return result

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        result["status"] = "unknown"
        result["reason"] = f"配信データの JSON が破損しています: {e}"
        return result

    generated_at_raw = None
    if isinstance(data, dict):
        meta = data.get("meta")
        if isinstance(meta, dict):
            generated_at_raw = meta.get("generatedAt")

    if not generated_at_raw or not isinstance(generated_at_raw, str):
        result["status"] = "unknown"
        result["reason"] = "meta.generatedAt が欠落しています"
        return result

    try:
        generated_at = parse_generated_at(generated_at_raw)
    except (ValueError, TypeError) as e:
        result["status"] = "unknown"
        result["reason"] = f"meta.generatedAt が ISO 8601 として解釈できません: {e}"
        return result

    age = now - generated_at
    age_hours = age.total_seconds() / 3600.0

    result["generated_at"] = generated_at.isoformat().replace("+00:00", "Z")
    result["generated_at_jst"] = now_jst_str(generated_at)
    result["age_hours"] = round(age_hours, 2)

    if age_hours <= max_age_hours:
        result["fresh"] = True
        result["status"] = "fresh"
        result["reason"] = f"{age_hours:.1f} 時間経過（閾値 {max_age_hours} 時間以内）"
    else:
        result["fresh"] = False
        result["status"] = "stale"
        result["reason"] = f"{age_hours:.1f} 時間経過（閾値 {max_age_hours} 時間超過）"

    return result


def exit_code_for(status: str) -> int:
    if status == "fresh":
        return EXIT_FRESH
    if status == "stale":
        return EXIT_STALE
    return EXIT_UNKNOWN


def attempt_heal(generator_path: Path) -> dict:
    """自己修復を試みる。配信済み JSON は本関数からは一切書き換えず、生成スクリプトに委ねる。

    失敗（スクリプト不在・非ゼロ終了・タイムアウト・実行時例外）しても例外を投げず、
    結果 dict で理由を返す（配信は止めない・NFR-8）。
    """
    heal_result: dict = {"attempted": True, "succeeded": False, "detail": None}

    if not generator_path.exists():
        heal_result["succeeded"] = False
        heal_result["detail"] = f"再生成スクリプトが見つかりません: {generator_path}"
        return heal_result

    try:
        proc = subprocess.run(
            ["node", str(generator_path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        heal_result["succeeded"] = False
        heal_result["detail"] = f"再生成の実行に失敗しました（配信データは未変更）: {e}"
        return heal_result

    if proc.returncode == 0:
        heal_result["succeeded"] = True
        heal_result["detail"] = "再生成に成功しました"
    else:
        heal_result["succeeded"] = False
        stderr_tail = (proc.stderr or "").strip().splitlines()
        tail = stderr_tail[-1] if stderr_tail else "(stderr なし)"
        heal_result["detail"] = (
            f"再生成が非ゼロ終了しました（code={proc.returncode}）: {tail}"
            "（配信データは未変更のまま。劣化するのは鮮度のみ・NFR-8）"
        )

    return heal_result


def run_self_test() -> int:
    """ネットワーク不要のユニットテスト。実ファイル public/data/daily-digest.json は書き換えない。"""
    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

        # 1. fresh: 生成から 1 時間経過（閾値 48h 以内）
        fresh_path = tmp_dir / "fresh.json"
        fresh_path.write_text(
            json.dumps({"meta": {"generatedAt": "2026-08-20T11:00:00.000Z"}, "candidates": []}),
            encoding="utf-8",
        )
        r = evaluate(fresh_path, max_age_hours=48, now_utc=now)
        check("fresh: status == fresh", r["status"] == "fresh")
        check("fresh: fresh == True", r["fresh"] is True)
        check("fresh: age_hours ≈ 1.0", r["age_hours"] is not None and abs(r["age_hours"] - 1.0) < 0.01)
        check("fresh: exit code 0", exit_code_for(r["status"]) == EXIT_FRESH)

        # 2. stale: 生成から 72 時間経過（閾値 48h 超過）
        stale_path = tmp_dir / "stale.json"
        stale_path.write_text(
            json.dumps({"meta": {"generatedAt": "2026-08-17T12:00:00.000Z"}, "candidates": []}),
            encoding="utf-8",
        )
        r = evaluate(stale_path, max_age_hours=48, now_utc=now)
        check("stale: status == stale", r["status"] == "stale")
        check("stale: fresh == False", r["fresh"] is False)
        check("stale: age_hours ≈ 72.0", r["age_hours"] is not None and abs(r["age_hours"] - 72.0) < 0.01)
        check("stale: exit code 1", exit_code_for(r["status"]) == EXIT_STALE)

        # 3. missing: ファイル不在
        missing_path = tmp_dir / "does-not-exist.json"
        r = evaluate(missing_path, max_age_hours=48, now_utc=now)
        check("missing: status == unknown", r["status"] == "unknown")
        check("missing: exit code 2", exit_code_for(r["status"]) == EXIT_UNKNOWN)

        # 4. corrupt: JSON 破損
        corrupt_path = tmp_dir / "corrupt.json"
        corrupt_path.write_text("{not valid json", encoding="utf-8")
        r = evaluate(corrupt_path, max_age_hours=48, now_utc=now)
        check("corrupt: status == unknown", r["status"] == "unknown")
        check("corrupt: exit code 2", exit_code_for(r["status"]) == EXIT_UNKNOWN)

        # 5. generatedAt 欠落
        no_meta_path = tmp_dir / "no-meta.json"
        no_meta_path.write_text(json.dumps({"meta": {}, "candidates": []}), encoding="utf-8")
        r = evaluate(no_meta_path, max_age_hours=48, now_utc=now)
        check("no-meta: status == unknown", r["status"] == "unknown")
        check("no-meta: exit code 2", exit_code_for(r["status"]) == EXIT_UNKNOWN)

        # 5b. meta 自体が欠落
        no_meta_key_path = tmp_dir / "no-meta-key.json"
        no_meta_key_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
        r = evaluate(no_meta_key_path, max_age_hours=48, now_utc=now)
        check("no-meta-key: status == unknown", r["status"] == "unknown")

        # 5c. generatedAt が非 ISO 文字列
        bad_iso_path = tmp_dir / "bad-iso.json"
        bad_iso_path.write_text(
            json.dumps({"meta": {"generatedAt": "not-a-date"}, "candidates": []}),
            encoding="utf-8",
        )
        r = evaluate(bad_iso_path, max_age_hours=48, now_utc=now)
        check("bad-iso: status == unknown", r["status"] == "unknown")

        # 6. 境界値: ちょうど閾値（48.0h）は fresh のまま
        boundary_path = tmp_dir / "boundary.json"
        boundary_path.write_text(
            json.dumps({"meta": {"generatedAt": "2026-08-18T12:00:00.000Z"}, "candidates": []}),
            encoding="utf-8",
        )
        r = evaluate(boundary_path, max_age_hours=48, now_utc=now)
        check("boundary: status == fresh (<=)", r["status"] == "fresh")

        # 7. attempt_heal: 存在しないジェネレータ → 失敗として扱われ、例外を投げない
        heal = attempt_heal(tmp_dir / "no-such-generator.mjs")
        check("heal: missing generator -> not succeeded", heal["succeeded"] is False)
        check("heal: detail is set", bool(heal["detail"]))

        # 8. heal 成功後の再評価: 再生成で generatedAt が最新化されたら fresh へ戻り exit 0 になる
        #    （Layer 1 セルフレビュー指摘: 再評価しないと「修復済みなのに stale（exit 1）」を返す）
        heal_target = tmp_dir / "heal-target.json"
        heal_target.write_text(
            json.dumps({"meta": {"generatedAt": "2026-08-15T12:00:00.000Z"}, "candidates": []}),
            encoding="utf-8",
        )
        before = evaluate(heal_target, max_age_hours=48, now_utc=now)
        check("heal-reeval: 修復前は stale", before["status"] == "stale")
        check("heal-reeval: 修復前の exit code は 1", exit_code_for(before["status"]) == 1)
        # 生成スクリプトが JSON を最新化したのと同じ状態を作る（subprocess は起動しない）。
        heal_target.write_text(
            json.dumps({"meta": {"generatedAt": "2026-08-20T11:30:00.000Z"}, "candidates": []}),
            encoding="utf-8",
        )
        after = evaluate(heal_target, max_age_hours=48, now_utc=now)
        check("heal-reeval: 再評価すると fresh", after["status"] == "fresh")
        check("heal-reeval: 再評価後の exit code は 0", exit_code_for(after["status"]) == 0)

    if failures:
        print("FAIL: check_digest_freshness self-test", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("OK: check_digest_freshness self-test 全ケース通過")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="配信データ（daily-digest.json）の鮮度チェック。"
                     "0=fresh / 1=stale / 2=鮮度不明（要注意）。配信自体は止めない（NFR-8）。",
    )
    parser.add_argument(
        "--path",
        default=str(DEFAULT_DIGEST_PATH),
        help="daily-digest.json のパス（既定: public/data/daily-digest.json）",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=48.0,
        help="stale とみなす経過時間の閾値（既定: 48時間）",
    )
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument(
        "--heal",
        action="store_true",
        help="stale 検知時に generate_gem_digest.mjs を実行して再生成を試みる（ネットワーク要）。"
             "run_checks.sh からは呼ばない",
    )
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    digest_path = Path(args.path)
    result = evaluate(digest_path, args.max_age_hours)

    heal_result = None
    if args.heal and result["status"] == "stale":
        heal_result = attempt_heal(DEFAULT_GENERATOR)
        # 🔴 修復に成功したら鮮度を再評価してから出力・終了コードを決める。
        #    再評価しないと「修復済みなのに stale（exit 1）」を返し、終了コードだけを見る
        #    監視・cron ラッパーが不要な重複修復やアラートを出す（Layer 1 セルフレビュー指摘）。
        if heal_result["succeeded"]:
            result = evaluate(digest_path, args.max_age_hours)
        result["heal"] = heal_result

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["status"] == "fresh":
            print(f"OK: 配信データは fresh です（{result['reason']}・生成: {result['generated_at_jst']}）")
            if heal_result is not None and heal_result["succeeded"]:
                # stale を検知して --heal で再生成し、その結果 fresh に戻ったケース。
                print(f"  自己修復（--heal）: 成功 — {heal_result['detail']}")
        elif result["status"] == "stale":
            print(f"WARNING: 配信データが stale です（{result['reason']}・生成: {result['generated_at_jst']}）")
            if heal_result is not None:
                status = "成功" if heal_result["succeeded"] else "失敗"
                print(f"  自己修復（--heal）: {status} — {heal_result['detail']}")
        else:
            print(f"UNKNOWN: 配信データの鮮度が判定できません（{result['reason']}）", file=sys.stderr)

    sys.exit(exit_code_for(result["status"]))


if __name__ == "__main__":
    main()
