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
        （`<!-- BEGIN:nextjs-agent-rules -->` / `<!-- END:nextjs-agent-rules -->`）を
        **行全体として厳密に一致する行** が含まれていないこと（PR #732 Layer 1 指摘 2）。
        マーカーを引用しただけの説明文（コードスパンで文中に埋め込む等）は行全体一致しない
        ため誤検知しない。next dev が実際に書き込むマーカーは改行で独立した行を占有する。
検査 2: `next.config.ts` の `nextConfig`（または `export default { ... }`）オブジェクトの
        **直接プロパティ**として `agentRules: false` が入っていること（PR #732 Layer 1 指摘 1）。
        ブレース深度を数える簡易パーサで判定するため、到達不能コード（`if (false) { ... }` の
        中の別変数への代入等）やネストしたオブジェクト内の同名プロパティには反応しない
        （fail-open 対策）。設定が消されると upsert が再発するため検査する。

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

# next.config.ts のオブジェクトリテラル内で `agentRules: false` プロパティを見つけるための
# パターン（値部分の後続は `,` や改行等いろいろありうるため \b で区切るだけにする）。
AGENT_PROP_RE = re.compile(r"agentRules\s*:\s*false\b")

# nextConfig 変数への代入 `... nextConfig ... = {` を検出するアンカー（型注釈の間に任意の
# トークンが挟まってよい）。`exampleDisabledConfig` のような別名の変数には一致しない
# （`\bnextConfig\b` が識別子全体としての "nextConfig" だけを要求するため）。
_NEXT_CONFIG_VAR_RE = re.compile(r"\bnextConfig\b[^=;{}]*=\s*\{")
# 中間変数を経由せず `export default { ... }` と直書きするパターンのフォールバック。
_EXPORT_DEFAULT_RE = re.compile(r"\bexport\s+default\s*\{")


def find_marker_lines(content: str) -> list[tuple[int, str]]:
    """CLAUDE.md 内で、行全体が厳密にマーカー文字列と一致する行を
    [(1-origin 行番号, マーカー文字列), ...] で返す。

    行全体一致を要求することで、マーカーを言及しただけの説明文（コードスパンで文中に
    埋め込む等）を汚染として誤検知しない（PR #732 Layer 1 指摘 2）。
    """
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped == AGENT_RULES_START_MARKER:
            hits.append((i, AGENT_RULES_START_MARKER))
        elif stripped == AGENT_RULES_END_MARKER:
            hits.append((i, AGENT_RULES_END_MARKER))
    return hits


def _find_config_object_start(content: str) -> int | None:
    """`nextConfig` に代入されるオブジェクトリテラル、または `export default { ... }` の
    直書きオブジェクトリテラルの開始位置（開き `{` の位置）を返す。見つからなければ None。

    到達不能コード内の別変数への代入（`if (false) { const exampleDisabledConfig: NextConfig =
    { agentRules: false } }` 等）は `nextConfig` という識別子そのものではないため拾わない。
    """
    m = _NEXT_CONFIG_VAR_RE.search(content)
    if m:
        return m.end() - 1
    m = _EXPORT_DEFAULT_RE.search(content)
    if m:
        return m.end() - 1
    return None


def has_agent_rules_suppressed(content: str) -> bool:
    """next.config.ts の `nextConfig`（または `export default {...}`）オブジェクトの
    直接プロパティとして `agentRules: false` があれば True。

    ブレース深度を数える簡易パーサで、①オブジェクトの外（到達不能コード・別変数への代入等）
    ②オブジェクト内でもネストしたサブオブジェクトの中（`experimental: { agentRules: false }`
    等）には反応しないようにする（PR #732 Layer 1 指摘 1・fail-open 対策）。
    文字列リテラル・コメント（`//` 行コメント / `/* */` ブロックコメント）内の記述も除外する。
    """
    start = _find_config_object_start(content)
    if start is None:
        return False

    depth = 0
    i = start
    n = len(content)
    in_line_comment = False
    in_block_comment = False
    string_char: str | None = None

    while i < n:
        c = content[i]
        nxt = content[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if string_char is not None:
            if c == "\\":
                i += 2
                continue
            if c == string_char:
                string_char = None
            i += 1
            continue

        if c == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if c in ("'", '"', "`"):
            string_char = c
            i += 1
            continue

        if c == "{":
            depth += 1
            i += 1
            continue
        if c == "}":
            depth -= 1
            i += 1
            if depth == 0:
                break
            continue

        if depth == 1:
            m = AGENT_PROP_RE.match(content, i)
            if m:
                return True

        i += 1

    return False


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

    # PR #732 Layer 1 指摘 2 の反例をそのまま run_check() 経由でも回帰させる:
    # マーカーを引用するだけの説明文は汚染とみなさない（exit 0）。
    prose_claude_md = tmp_path / "CLAUDE_prose_mention.md"
    prose_claude_md.write_text(
        "## 過去のインシデント記録\n"
        "next dev は自動生成マーカー `<!-- BEGIN:nextjs-agent-rules -->` を書き込んでいたが、\n"
        "`next.config.ts` の `agentRules: false` で抑止した（Issue #50 T-3）。\n",
        encoding="utf-8",
    )
    assert (
        run_check(prose_claude_md, ok_next_config) == 0
    ), "マーカーを言及しただけの説明文を汚染として誤検知した（exit 0 のはず）"

    not_suppressed_config = tmp_path / "next_not_suppressed.config.ts"
    not_suppressed_config.write_text(
        "const nextConfig: NextConfig = {\n  reactStrictMode: true,\n}\n", encoding="utf-8"
    )
    assert (
        run_check(ok_claude_md, not_suppressed_config) == 1
    ), "agentRules 未設定ケースで exit 1 にならなかった"

    # PR #732 Layer 1 指摘 1 の反例をそのまま run_check() 経由でも回帰させる:
    # 到達不能コード内の別変数の agentRules: false を「抑止済み」と誤判定しない（exit 1）。
    dead_code_config = tmp_path / "next_dead_code.config.ts"
    dead_code_config.write_text(
        "// NOTE: an old example kept for reference, never actually used/exported.\n"
        "if (false) {\n"
        "  const exampleDisabledConfig: NextConfig = {\n"
        "    agentRules: false,\n"
        "  };\n"
        "}\n"
        "\n"
        "const nextConfig: NextConfig = {\n"
        "  reactStrictMode: true,\n"
        "};\n"
        "export default nextConfig;\n",
        encoding="utf-8",
    )
    assert (
        run_check(ok_claude_md, dead_code_config) == 1
    ), "到達不能コード内の agentRules: false を抑止済みと誤判定した（fail-open・exit 1 のはず）"

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

    # PR #732 Layer 1 指摘 2 の反例: マーカーを引用しただけの説明文は誤検知しない
    # （行全体がマーカーと厳密一致する行のみを対象にする）。
    prose_mention = (
        "## 過去のインシデント記録\n"
        "next dev は自動生成マーカー `<!-- BEGIN:nextjs-agent-rules -->` を書き込んでいたが、\n"
        "`next.config.ts` の `agentRules: false` で抑止した（Issue #50 T-3）。\n"
    )
    assert (
        find_marker_lines(prose_mention) == []
    ), "マーカーを言及しただけの説明文を汚染として誤検知した"

    # --- has_agent_rules_suppressed ---
    suppressed = "const nextConfig: NextConfig = {\n  agentRules: false,\n}\n"
    assert has_agent_rules_suppressed(suppressed) is True, "抑止設定ありなのに検出できなかった"

    suppressed_no_trailing_comma = "const nextConfig: NextConfig = {\n  agentRules: false\n}\n"
    assert (
        has_agent_rules_suppressed(suppressed_no_trailing_comma) is True
    ), "末尾カンマなしの抑止設定を検出できなかった"

    suppressed_spaced = "const nextConfig: NextConfig = {\n  agentRules : false ,  \n}\n"
    assert has_agent_rules_suppressed(suppressed_spaced) is True, "空白揺れのある抑止設定を検出できなかった"

    suppressed_export_default = "export default {\n  agentRules: false,\n}\n"
    assert (
        has_agent_rules_suppressed(suppressed_export_default) is True
    ), "export default 直書きの抑止設定を検出できなかった"

    not_suppressed = "const nextConfig: NextConfig = {\n  reactStrictMode: true,\n}\n"
    assert has_agent_rules_suppressed(not_suppressed) is False, "抑止設定なしなのに検出してしまった"

    truthy_value = "const nextConfig: NextConfig = {\n  agentRules: true,\n}\n"
    assert has_agent_rules_suppressed(truthy_value) is False, "true 設定を false 相当として誤検出した"

    commented_out = "const nextConfig: NextConfig = {\n  // agentRules: false,\n}\n"
    assert (
        has_agent_rules_suppressed(commented_out) is False
    ), "コメントアウトされた設定を有効設定として誤検出した"

    # ネストしたサブオブジェクト内の同名プロパティは「直接プロパティ」ではないため無効
    nested = (
        "const nextConfig: NextConfig = {\n"
        "  experimental: {\n"
        "    agentRules: false,\n"
        "  },\n"
        "}\n"
    )
    assert (
        has_agent_rules_suppressed(nested) is False
    ), "ネストしたサブオブジェクト内の agentRules: false を直接プロパティとして誤検出した"

    # PR #732 Layer 1 指摘 1 の反例: 到達不能コード内の別変数への代入は「抑止済み」とみなさない
    dead_code = (
        "// NOTE: an old example kept for reference, never actually used/exported.\n"
        "if (false) {\n"
        "  const exampleDisabledConfig: NextConfig = {\n"
        "    agentRules: false,\n"
        "  };\n"
        "}\n"
        "\n"
        "const nextConfig: NextConfig = {\n"
        "  reactStrictMode: true,\n"
        "};\n"
        "export default nextConfig;\n"
    )
    assert (
        has_agent_rules_suppressed(dead_code) is False
    ), "到達不能コード内の agentRules: false を抑止済みと誤判定した（fail-open）"

    # --- run_check()（エントリポイント〜終了コードの貫通・上記反例も含む） ---
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
