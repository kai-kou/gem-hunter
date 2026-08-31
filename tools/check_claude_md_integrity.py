#!/usr/bin/env python3
"""check_claude_md_integrity.py

`CLAUDE.md` が Next.js 16.3 以降の `next dev` 自動生成（upsert）で汚染されていないかを
機械検査する（Issue #50 T-3）。

背景: `next dev` は AI コーディングエージェントを検知すると、管理ブロック
（`<!-- BEGIN:nextjs-agent-rules -->` 〜 `<!-- END:nextjs-agent-rules -->`）が無い場合に
`AGENTS.md` / `CLAUDE.md` へ自動 upsert する（実装は
`node_modules/next/dist/server/lib/generate-agent-files.js`）。本リポジトリの `CLAUDE.md` は
精緻に設計済みのプロジェクト正本であり、上書きされると規律全体が壊れる。

抑止設定は `next.config.ts` の `agentRules: false`（`node_modules/next/dist/server/lib/
generate-agent-files.js` はこの設定を見て自身の呼び出し元でスキップする。設定の存在確認は
`node_modules/next/dist/docs/01-app/02-guides/ai-agents.md` "Opting out" 節が一次情報）。
ただし設定だけでは「消されたら再発する」ため、本ツールが CLAUDE.md 側の汚染検知と
next.config.ts 側の抑止設定の両方を機械チェックする。

検査 1: `CLAUDE.md` に自動生成ブロックのマーカー
        （`<!-- BEGIN:nextjs-agent-rules -->` / `<!-- END:nextjs-agent-rules -->`）が
        含まれていないこと
検査 2: `next.config.ts` に `agentRules: false`（抑止設定）が入っていること
        （設定が消されると upsert が再発するため）

使い方:
  python3 tools/check_claude_md_integrity.py             # 本判定（PASS/NG を stdout・NG は stderr にも詳細）
  python3 tools/check_claude_md_integrity.py --self-test  # ネットワーク不要のユニットテスト

終了コード: 0=PASS / 1=違反あり（❌）/ 2=判定不能・ツール異常（⚠️・fail-closed）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
NEXT_CONFIG = REPO_ROOT / "next.config.ts"

# next dev が書き込む管理ブロックのマーカー（generate-agent-files.js が定義する定数と一致させる）。
AGENT_RULES_START_MARKER = "<!-- BEGIN:nextjs-agent-rules -->"
AGENT_RULES_END_MARKER = "<!-- END:nextjs-agent-rules -->"

# next.config.ts 側の抑止設定。空白の揺れ（`agentRules:false` / `agentRules : false` 等）を
# 許容しつつ、コメントアウトされた行（例のコピペ残骸）は誤検知しないよう行単位で判定する。
AGENT_RULES_CONFIG_RE = re.compile(r"^\s*agentRules\s*:\s*false\s*,?\s*(//.*)?$")


def find_marker_lines(content: str) -> list[tuple[int, str]]:
    """CLAUDE.md 内でマーカー文字列を含む行を [(1-origin 行番号, マーカー文字列), ...] で返す。"""
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(content.splitlines(), start=1):
        if AGENT_RULES_START_MARKER in line:
            hits.append((i, AGENT_RULES_START_MARKER))
        if AGENT_RULES_END_MARKER in line:
            hits.append((i, AGENT_RULES_END_MARKER))
    return hits


def has_agent_rules_suppressed(content: str) -> bool:
    """next.config.ts に `agentRules: false`（コメント行を除く）があれば True。"""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue  # 行コメント・ブロックコメント継続行は設定として数えない
        if AGENT_RULES_CONFIG_RE.match(line):
            return True
    return False


def self_test() -> int:
    """検査ロジックのセルフテスト（マーカー検出・設定検出の両方を回帰させる）。"""
    # --- find_marker_lines ---
    clean = "# CLAUDE.md\n\n本文のみ。\n"
    assert find_marker_lines(clean) == [], "汚染なしの本文でマーカーを誤検出した"

    polluted = (
        "# CLAUDE.md\n\n"
        "本文。\n\n"
        "<!-- BEGIN:nextjs-agent-rules -->\n\n"
        "# This is NOT the Next.js you know\n\n"
        "<!-- END:nextjs-agent-rules -->\n"
    )
    hits = find_marker_lines(polluted)
    assert hits == [
        (5, AGENT_RULES_START_MARKER),
        (9, AGENT_RULES_END_MARKER),
    ], f"汚染ブロックの行番号検出に失敗: {hits}"

    # 開始マーカーのみ混入した不完全ケースも検知できること（upsert 途中の破損等）
    start_only = "本文\n<!-- BEGIN:nextjs-agent-rules -->\n"
    assert find_marker_lines(start_only) == [
        (2, AGENT_RULES_START_MARKER)
    ], "開始マーカーのみのケースを検出できなかった"

    # --- has_agent_rules_suppressed ---
    suppressed = "const nextConfig: NextConfig = {\n  agentRules: false,\n}\n"
    assert has_agent_rules_suppressed(suppressed) is True, "抑止設定ありなのに検出できなかった"

    suppressed_no_trailing_comma = "const nextConfig: NextConfig = {\n  agentRules: false\n}\n"
    assert (
        has_agent_rules_suppressed(suppressed_no_trailing_comma) is True
    ), "末尾カンマなしの抑止設定を検出できなかった"

    suppressed_spaced = "  agentRules : false ,  \n"
    assert has_agent_rules_suppressed(suppressed_spaced) is True, "空白揺れのある抑止設定を検出できなかった"

    not_suppressed = "const nextConfig: NextConfig = {\n  reactStrictMode: true,\n}\n"
    assert has_agent_rules_suppressed(not_suppressed) is False, "抑止設定なしなのに検出してしまった"

    truthy_value = "  agentRules: true,\n"
    assert has_agent_rules_suppressed(truthy_value) is False, "true 設定を false 相当として誤検出した"

    commented_out = "  // agentRules: false,\n"
    assert (
        has_agent_rules_suppressed(commented_out) is False
    ), "コメントアウトされた設定を有効設定として誤検出した"

    print("[claude-md-integrity] self-test OK")
    return 0


def run_check(claude_md_path: Path, next_config_path: Path) -> int:
    """本判定の本体（main() と self_test() の両方から同じ経路を通す）。

    終了コード: 0=PASS / 1=違反あり（❌） / 2=判定不能・ツール異常（⚠️・fail-closed）
    """
    if not claude_md_path.is_file():
        print(f"[claude-md-integrity] ⚠️ {claude_md_path} が読めません（判定不能）", file=sys.stderr)
        return 2
    if not next_config_path.is_file():
        print(f"[claude-md-integrity] ⚠️ {next_config_path} が読めません（判定不能）", file=sys.stderr)
        return 2

    try:
        claude_md_text = claude_md_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[claude-md-integrity] ⚠️ {claude_md_path} の読み込みに失敗: {e}", file=sys.stderr)
        return 2
    try:
        next_config_text = next_config_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[claude-md-integrity] ⚠️ {next_config_path} の読み込みに失敗: {e}", file=sys.stderr)
        return 2

    violations: list[str] = []

    marker_hits = find_marker_lines(claude_md_text)
    if marker_hits:
        for line_no, marker in marker_hits:
            violations.append(
                f"❌ {claude_md_path}:{line_no}: "
                f"next dev 自動生成マーカー `{marker}` が混入しています"
            )

    if not has_agent_rules_suppressed(next_config_text):
        violations.append(
            f"❌ {next_config_path}: `agentRules: false` が設定されていません"
            "（next dev の CLAUDE.md 自動 upsert を抑止できません）"
        )

    if violations:
        print("[claude-md-integrity] NG:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("[claude-md-integrity] OK（CLAUDE.md 未汚染 / agentRules: false 設定済み）")
    return 0


def self_test_run_check(tmp_path: Path) -> None:
    """run_check() をエントリポイントから終了コードまで貫通させるセルフテスト（0/1/2 全パス）。"""
    ok_claude_md = tmp_path / "CLAUDE_ok.md"
    ok_claude_md.write_text("# CLAUDE.md\n\n本文のみ。\n", encoding="utf-8")
    ok_next_config = tmp_path / "next_ok.config.ts"
    ok_next_config.write_text(
        "const nextConfig: NextConfig = {\n  agentRules: false,\n}\n", encoding="utf-8"
    )
    assert run_check(ok_claude_md, ok_next_config) == 0, "PASS ケースで exit 0 にならなかった"

    polluted_claude_md = tmp_path / "CLAUDE_polluted.md"
    polluted_claude_md.write_text(
        "# CLAUDE.md\n\n本文。\n\n<!-- BEGIN:nextjs-agent-rules -->\n\n"
        "# This is NOT the Next.js you know\n\n<!-- END:nextjs-agent-rules -->\n",
        encoding="utf-8",
    )
    assert (
        run_check(polluted_claude_md, ok_next_config) == 1
    ), "CLAUDE.md 汚染ケースで exit 1 にならなかった"

    not_suppressed_config = tmp_path / "next_not_suppressed.config.ts"
    not_suppressed_config.write_text(
        "const nextConfig: NextConfig = {\n  reactStrictMode: true,\n}\n", encoding="utf-8"
    )
    assert (
        run_check(ok_claude_md, not_suppressed_config) == 1
    ), "agentRules 未設定ケースで exit 1 にならなかった"

    missing_path = tmp_path / "does_not_exist.md"
    assert (
        run_check(missing_path, ok_next_config) == 2
    ), "ファイル不在ケースで exit 2（判定不能・fail-closed）にならなかった"


def self_test() -> int:
    """検査ロジックのセルフテスト（マーカー検出・設定検出・run_check() 貫通の 3 系統を回帰させる）。"""
    # --- find_marker_lines ---
    clean = "# CLAUDE.md\n\n本文のみ。\n"
    assert find_marker_lines(clean) == [], "汚染なしの本文でマーカーを誤検出した"

    polluted = (
        "# CLAUDE.md\n\n"
        "本文。\n\n"
        "<!-- BEGIN:nextjs-agent-rules -->\n\n"
        "# This is NOT the Next.js you know\n\n"
        "<!-- END:nextjs-agent-rules -->\n"
    )
    hits = find_marker_lines(polluted)
    assert hits == [
        (5, AGENT_RULES_START_MARKER),
        (9, AGENT_RULES_END_MARKER),
    ], f"汚染ブロックの行番号検出に失敗: {hits}"

    # 開始マーカーのみ混入した不完全ケースも検知できること（upsert 途中の破損等）
    start_only = "本文\n<!-- BEGIN:nextjs-agent-rules -->\n"
    assert find_marker_lines(start_only) == [
        (2, AGENT_RULES_START_MARKER)
    ], "開始マーカーのみのケースを検出できなかった"

    # --- has_agent_rules_suppressed ---
    suppressed = "const nextConfig: NextConfig = {\n  agentRules: false,\n}\n"
    assert has_agent_rules_suppressed(suppressed) is True, "抑止設定ありなのに検出できなかった"

    suppressed_no_trailing_comma = "const nextConfig: NextConfig = {\n  agentRules: false\n}\n"
    assert (
        has_agent_rules_suppressed(suppressed_no_trailing_comma) is True
    ), "末尾カンマなしの抑止設定を検出できなかった"

    suppressed_spaced = "  agentRules : false ,  \n"
    assert has_agent_rules_suppressed(suppressed_spaced) is True, "空白揺れのある抑止設定を検出できなかった"

    not_suppressed = "const nextConfig: NextConfig = {\n  reactStrictMode: true,\n}\n"
    assert has_agent_rules_suppressed(not_suppressed) is False, "抑止設定なしなのに検出してしまった"

    truthy_value = "  agentRules: true,\n"
    assert has_agent_rules_suppressed(truthy_value) is False, "true 設定を false 相当として誤検出した"

    commented_out = "  // agentRules: false,\n"
    assert (
        has_agent_rules_suppressed(commented_out) is False
    ), "コメントアウトされた設定を有効設定として誤検出した"

    # --- run_check()（エントリポイント〜終了コードの貫通） ---
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        self_test_run_check(Path(td))

    print("[claude-md-integrity] self-test OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--self-test", action="store_true", help="検査ロジックのセルフテストのみ実行"
    )
    args = ap.parse_args()

    if args.self_test:
        try:
            return self_test()
        except AssertionError as e:
            print(f"[claude-md-integrity] self-test NG: {e}", file=sys.stderr)
            return 1

    return run_check(CLAUDE_MD, NEXT_CONFIG)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"[claude-md-integrity] ⚠️ checker error: {e}", file=sys.stderr)
        sys.exit(2)
