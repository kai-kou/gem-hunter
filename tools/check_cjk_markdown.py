#!/usr/bin/env python3
"""check_cjk_markdown.py（汎用ベース）

CLAUDE.md「Markdown 出力ルール」の機械チェック＆自動整形ツール。

ルール（SSOT: CLAUDE.md「Markdown 出力ルール」）:
  CJK テキスト内の **強調** や `コード` 等の記法前後に半角スペースを入れる
  （例: `これは **重要** です`）。

このルールは従来 self-review-checklist.md で「目視」チェック扱いだったため、
大規模ドキュメントで人手の見落としが頻発し、AI レビュアー（Gemini 等）に毎回
同種指摘を受けてレビューコストが高かった（根本原因: 規範はあるが実行支援が無い）。
本ツールで検出を機械化し、`--fix` で自動整形できるようにして再発を防ぐ。

使い方:
  python3 tools/check_cjk_markdown.py <file.md> [<file2.md> ...]   # 検出のみ（違反あれば exit 1）
  python3 tools/check_cjk_markdown.py --fix <file.md> ...          # 自動整形して上書き
  python3 tools/check_cjk_markdown.py --changed                    # 変更された .md を対象に検出
  python3 tools/check_cjk_markdown.py --fix --changed              # 変更された .md を自動整形
  python3 tools/check_cjk_markdown.py --changed --under docs/      # 変更された .md のうち docs/ 配下だけ対象
  python3 tools/check_cjk_markdown.py --under docs/rules/          # --under 単独: 配下の .md を再帰的に全件対象
  python3 tools/check_cjk_markdown.py --self-test                  # セルフテスト

Issue #85: 並行サブエージェント実行中に `--changed`（git 変更検知ベース）だけで一括整形すると、
自分が担当していない・他エージェントが並行編集中のファイルまで書き換えてしまう事故があった。
`--under DIR`（複数指定可）でパスを絞り込むことで、担当ディレクトリ配下だけを対象にできる。

Issue #706: `--under` は当初 `--changed` 併用時の絞り込みフィルタとしてしか機能せず、
`--under` 単独指定は「対象ファイルがありません」で exit 0（fail-open・黙って 0 ファイル検査で
PASS に見える）だった。`--under` 単独指定は **そのディレクトリ配下の .md を再帰的に選択する
ファイル選択** として扱う（`resolve_targets()` / `walk_md_under()`）。それでも対象 0 件なら
typo 等の可能性が高いため exit 1 で警告する（`--changed` 側の「変更 .md が無い」という
日常的な 0 件とは区別し、そちらは従来どおり exit 0 を維持する）。

Issue #711（PR #711 Layer 1 セルフレビュー指摘）:
  - CRITICAL: 明示ファイル指定（または `--changed`）と `--under` を併用したとき、指定ファイルが
    `--under` 配下と 1 件も一致しないと `filter_under()` が 0 件を返し、「日常的な 0 件」
    （`--changed` で変更 .md が無い）と区別できずに exit 0（fail-open）していた。
    `resolve_targets()` は「フィルタ前に候補が 1 件以上あったか」を追跡し、フィルタ後に
    0 件へ落ちた場合は `mode="filtered-to-zero"` として exit 1 で警告する
    （フィルタ前から候補が 0 件だった場合のみ従来どおり `mode="other"` で exit 0 を維持）。
  - WARNING: `walk_md_under()` の `base.rglob("*.md")` が `.git/` `node_modules/` `.next/` 等の
    生成物・サードパーティ製ディレクトリを除外せず、`--fix --under .` 的な使い方で
    第三者著作物（例: `node_modules/**/README.md`）まで書き換えうる状態だった（#233 の方針と矛盾）。
    `walk_md_under()` は `os.walk()` + `EXCLUDED_DIRS` によるディレクトリ単位のプルーニングへ変更。

設計（誤検出を避けるための厳格化）:
  - フェンスドコードブロック（``` / ~~~）内は一切触らない
  - YAML フロントマター（先頭 --- ... ---）は触らない
  - 検査対象記法は **強調**（bold）と `インラインコード` の 2 種のみ
    （* 1 個の斜体は誤検出が多いので対象外）
  - 記法スパンの「外側」が CJK の「単語文字」（かな・漢字等）に直接隣接する場合のみ
    半角スペースを要求する。約物（、。「」（）等）が隣接する場合は要求しない
    （日本語の約物の前後にスペースを入れるとかえって不自然なため）

終了コード: 0=違反なし（または --fix で修正完了） / 1=違反あり（検出モード） / 2=ツール異常
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import git_diff_utils

# CJK「単語文字」: ひらがな・カタカナ・漢字・全角英数など。約物は意図的に除外する。
CJK_WORD = (
    r"ぁ-ゖ"   # ひらがな
    r"ァ-ヺ"   # カタカナ
    r"ー"          # 長音符
    r"㐀-䶿"   # CJK 拡張 A
    r"一-鿿"   # CJK 統合漢字
    r"豈-﫿"   # CJK 互換漢字
    r"Ａ-Ｚ"   # 全角英大文字
    r"ａ-ｚ"   # 全角英小文字
    r"０-９"   # 全角数字
    r"가-힣"   # ハングル音節（CJK の K）
    r"ㄱ-ㅣ"   # ハングル互換字母
)
CJK_WORD_RE = re.compile(f"[{CJK_WORD}]")

# --- 整形対象外（第三者著作物の原文・#233）---------------------------------
# 🔴 本プロジェクトの表記ルールを、**他者が書いた文書へ機械的に適用してはならない**。
#    与件（外部提供の要件定義）は「原本（編集しない）」と定められており、公開時は
#    第三者著作物として LICENSE の対象外に置いている。整形で本文が 1 文字でも変わると
#    「原文のまま収録している」という権利表示自体が虚偽になる。
#    パスはリポジトリルートからの相対で書く（前方一致ではなく完全一致で判定する）。
EXCLUDED_PATHS = frozenset({
    "docs/02_requirements/minimum-requirements.md",
})

# --- 整形対象外（生成物・サードパーティ製ディレクトリ・#711）-----------------
# `walk_md_under()` がこれらのディレクトリ配下へ再帰しないようにする（ディレクトリ名の
# 完全一致で判定＝`os.walk` の `dirnames` から除外）。`.gitignore` に実在が確認できる
# 生成物ディレクトリ + 慣習的なサードパーティ格納ディレクトリを列挙する。
EXCLUDED_DIRS = frozenset({
    ".git",
    "node_modules",
    ".next",
    ".open-next",
    "dist",
    "build",
    "out",
    "coverage",
    "playwright-report",
    "test-results",
    ".venv",
    "venv",
})


def is_excluded(path: str) -> bool:
    """整形・検査の対象外パスか判定する（第三者著作物の保護・#233）。"""
    p = str(path).replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p in EXCLUDED_PATHS

# 検査対象の記法スパン: **bold** と `code`。
# bold は最短一致・改行を含まない。code はバッククォート1個で囲まれた範囲。
SPAN_RE = re.compile(r"(\*\*(?!\s)(?:[^*]|\*(?!\*))+?(?<!\s)\*\*|`[^`\n]+?`)")


def is_cjk_word(ch: str) -> bool:
    return bool(ch) and bool(CJK_WORD_RE.match(ch))


def _process_line(line: str, fix: bool) -> tuple[str, int]:
    """1 行を処理して (整形後の行, 違反件数) を返す。

    fix=False のときは行を変えず違反件数のみ数える。
    """
    violations = 0
    out: list[str] = []
    idx = 0
    for m in SPAN_RE.finditer(line):
        start, end = m.start(), m.end()
        span = m.group(0)
        # スパン前のテキストを確定（原文をそのまま積む）
        out.append(line[idx:start])
        # --- 開きの境界チェック（原文インデックスで直前の 1 文字を見る）---
        prev_ch = line[start - 1] if start > 0 else ""
        if is_cjk_word(prev_ch):
            violations += 1
            if fix:
                out.append(" ")
        out.append(span)
        # --- 閉じの境界チェック ---
        next_ch = line[end] if end < len(line) else ""
        if is_cjk_word(next_ch):
            violations += 1
            if fix:
                out.append(" ")
        idx = end
    out.append(line[idx:])
    return "".join(out), violations


def process_text(text: str, fix: bool) -> tuple[str, list[tuple[int, str]]]:
    """テキスト全体を処理。(整形後テキスト, [(行番号, 元行), ...] 違反行) を返す。"""
    lines = text.split("\n")
    in_fence = False
    fence_marker = ""
    in_frontmatter = False
    violations: list[tuple[int, str]] = []
    result: list[str] = []

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        # YAML フロントマター（先頭行が ---）
        if i == 0 and stripped == "---":
            in_frontmatter = True
            result.append(line)
            continue
        if in_frontmatter:
            result.append(line)
            if stripped == "---":
                in_frontmatter = False
            continue
        # フェンスドコードブロック開閉
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            # CommonMark: 閉じフェンスは開きと同じ文字種で、同じ長さ以上のときのみ閉じる
            # （4 個以上のバッククォートで囲んだブロック内の ``` で誤閉鎖しない）
            elif marker[0] == fence_marker[0] and len(marker) >= len(fence_marker):
                in_fence = False
                fence_marker = ""
            result.append(line)
            continue
        if in_fence:
            result.append(line)
            continue
        new_line, count = _process_line(line, fix)
        if count > 0:
            violations.append((i + 1, line))
        result.append(new_line)

    return "\n".join(result), violations


def changed_md_files() -> list[str]:
    """git diff から変更された .md ファイル一覧を取得（origin/<default>...HEAD + 作業ツリー）。

    #195: 収集ロジック本体（4 ソースの合算・出現順維持）は `tools/git_diff_utils.py` の
    `collect_changed_files()` に統合済み。ここでは `require_existing=False` で生の一覧を受け取り、
    `.md` フィルタ・`is_excluded()`・実在チェックは従来どおり本関数側で行う（`.md` でないファイルの
    存在確認を無駄にしないため・元実装と最終的な集合は同一）。
    """
    files = git_diff_utils.collect_changed_files(require_existing=False)
    seen, out = set(), []
    for f in files:
        if f.endswith(".md") and f not in seen and not is_excluded(f) and Path(f).is_file():
            seen.add(f)
            out.append(f)
    return out


def walk_md_under(unders: list[str]) -> list[str]:
    """unders の各ディレクトリ配下を再帰的に走査し、.md / .markdown ファイル一覧を返す（Issue #706）。

    `--under` が単独指定されたときのファイル選択に使う（`filter_under` は既存パス集合を
    絞り込むだけで、それ自体はファイル選択にならない＝#706 の fail-open の原因だった）。
    存在しないディレクトリは黙ってスキップする（typo 検出は呼び出し側の 0 件警告に任せる）。

    Issue #711: `EXCLUDED_DIRS`（`.git` / `node_modules` / `.next` 等）配下へは
    再帰しない（`os.walk` の `dirnames` をその場でプルーニングする＝ディレクトリ単位の
    除外。以前の `Path.rglob("*.md")` はディレクトリ除外を一切持たず、`--fix --under .`
    的な使い方で第三者著作物 [`node_modules/**/README.md` 等] まで書き換えうる状態だった）。
    """
    seen: set[str] = set()
    out: list[str] = []
    for d in unders:
        dd = d.strip().rstrip("/")
        if not dd:
            continue
        base = Path(dd)
        if not base.is_dir():
            continue
        matches: list[str] = []
        for dirpath, dirnames, filenames in os.walk(base):
            # dirnames をその場で書き換えると os.walk がその配下へ降りなくなる（公式仕様）
            dirnames[:] = [dn for dn in dirnames if dn not in EXCLUDED_DIRS]
            for fn in filenames:
                if fn.lower().endswith((".md", ".markdown")):
                    matches.append(str(Path(dirpath) / fn))
        for s in sorted(matches):
            if not Path(s).is_file():
                continue
            if s in seen or is_excluded(s):
                continue
            seen.add(s)
            out.append(s)
    return out


def resolve_targets(files: list[str], changed: bool, unders: list[str]) -> tuple[list[str], str]:
    """files / --changed / --under の指定から検査対象パス一覧と選択モードを決定する（Issue #706 / #711）。

    戻り値: (paths, mode)
      - mode == "none":            ファイル指定も --changed も --under も無い（明確な誤用）
      - mode == "under-only":      --under だけが指定された（ディレクトリ配下を再帰的にファイル
                                   選択する。#706 で追加した新挙動。0 件なら typo 等の可能性が
                                   高いので警告対象）
      - mode == "filtered-to-zero": files / --changed 由来の候補が 1 件以上あったのに、--under の
                                   絞り込みで 0 件になった（#711 の CRITICAL 指摘: 明示ファイル指定と
                                   --under の対象ディレクトリが噛み合っていない fail-open のサイン。
                                   `--changed` で真に変更 .md が無いケースとは区別し、警告対象にする）
      - mode == "other":           files / --changed が絡む在来ロジック。フィルタ前から候補が
                                   0 件（例: --changed で変更 .md が無い）なのは日常的に起こる
                                   正常系のため、呼び出し側は静かに exit 0 にしてよい
    """
    if unders and not files and not changed:
        return walk_md_under(unders), "under-only"

    paths = list(files)
    if changed:
        paths += changed_md_files()
    if not files and not changed:
        return [], "none"

    had_candidates = bool(paths)
    if unders:
        paths = filter_under(paths, unders)
        if had_candidates and not paths:
            # files / --changed 由来の候補は存在したが、--under の絞り込みで全滅した。
            # 「フィルタ前から 0 件」（日常的な正常系）と区別し、fail-open させない。
            return [], "filtered-to-zero"
    return paths, "other"


def filter_under(paths: list[str], unders: list[str]) -> list[str]:
    """paths のうち、unders のいずれかのディレクトリ配下にあるものだけを残す（Issue #85）。

    unders が空（未指定）ならフィルタせず paths をそのまま返す。
    プレフィックス一致による誤爆（`docs` 指定で `docsx/foo.md` まで拾う等）を避けるため、
    パスの完全一致またはディレクトリ境界（`/`）を挟んだ一致だけを許容する。
    """
    if not unders:
        return paths
    norm_unders = [u.strip().rstrip("/") for u in unders if u.strip()]
    norm_unders = [u for u in norm_unders if u]
    if not norm_unders:
        return paths
    out = []
    for p in paths:
        pp = p[2:] if p.startswith("./") else p
        for u in norm_unders:
            if pp == u or pp.startswith(u + "/"):
                out.append(p)
                break
    return out


def check_files(paths: list[str], fix: bool) -> int:
    total_violations = 0
    fixed_files = 0
    for path in paths:
        if is_excluded(path):
            print(f"[cjk-md] スキップ（整形対象外・第三者著作物）: {path}", file=sys.stderr)
            continue
        p = Path(path)
        if not p.is_file():
            print(f"[cjk-md] スキップ（不在）: {path}", file=sys.stderr)
            continue
        # Markdown 専用ツール。.py 等を誤って渡しても内容を壊さないよう .md 限定にする
        if p.suffix.lower() not in (".md", ".markdown"):
            print(f"[cjk-md] スキップ（.md 以外）: {path}", file=sys.stderr)
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            print(f"[cjk-md] スキップ（読み込み失敗: {e}）: {path}", file=sys.stderr)
            continue
        new_text, violations = process_text(text, fix)
        if not violations:
            continue
        total_violations += len(violations)
        if fix:
            p.write_text(new_text, encoding="utf-8")
            fixed_files += 1
            print(f"[cjk-md] 整形: {path}（{len(violations)} 行）")
        else:
            for ln, content in violations[:30]:
                print(f"[cjk-md] {path}:{ln}: CJK 記法の前後に半角スペース不足 → {content.strip()[:80]}")

    if fix:
        if fixed_files:
            print(f"[cjk-md] 自動整形完了: {fixed_files} ファイル / {total_violations} 行")
        else:
            print("[cjk-md] 整形対象なし（OK）")
        return 0
    if total_violations:
        print(f"\n[cjk-md] Warning: CJK 半角スペース違反 {total_violations} 行。")
        print("  → 自動整形: python3 tools/check_cjk_markdown.py --fix <file>")
        return 1
    print("[cjk-md] OK（CJK 半角スペース違反なし）")
    return 0


def self_test() -> int:
    # 注意: 入力（左）は「スペース未挿入」の原文。本ツールを self_test 行に対して
    # --fix で走らせると入力が壊れるため、check_files は .md 以外をスキップする。
    cases = [
        # (入力, 期待出力)
        ("これは" + "**重要**" + "です", "これは **重要** です"),
        ("これは `コード` です", "これは `コード` です"),  # 既に正しい → 不変
        ("`コード`" + "を使う", "`コード` を使う"),
        ("使う" + "`コード`", "使う `コード`"),
        ("英語 **bold** text", "英語 **bold** text"),  # 英数字隣接 → 不変
        ("**先頭強調**" + "から始まる", "**先頭強調** から始まる"),
        ("句点の前" + "**強調**" + "。", "句点の前 **強調**。"),  # 約物（。）はスペース不要
        ("「**強調**」", "「**強調**」"),  # 括弧（約物）はスペース不要
        ("English**bold**english", "English**bold**english"),  # 非 CJK → 不変
        ("値は" + "`x`" + "、次は" + "`y`" + "です", "値は `x`、次は `y` です"),
        ("한국어" + "**볼드**" + "입니다", "한국어 **볼드** 입니다"),  # ハングル（CJK の K）
    ]
    passed = 0
    failed = 0
    for src, expected in cases:
        got, _ = process_text(src, fix=True)
        if got == expected:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {src!r}\n  expected: {expected!r}\n  got:      {got!r}")

    # フェンス内は触らない
    fence_src = "```\nこれは**重要**です\n```\n本文の **強調** です"
    fence_got, _ = process_text(fence_src, fix=True)
    if "```\nこれは**重要**です\n```" in fence_got and "本文の **強調** です" in fence_got:
        passed += 1
    else:
        failed += 1
        print(f"FAIL(fence): {fence_got!r}")

    # 4 個のバッククォートで囲んだブロック内の ``` で誤閉鎖しない（CommonMark）
    bt = "`" * 4
    bt3 = "`" * 3
    fence4 = f"{bt}\n{bt3}\n中の**強調**は触らない\n{bt3}\n{bt}\n外の**強調**です"
    fence4_got, _ = process_text(fence4, fix=True)
    if "中の**強調**は触らない" in fence4_got and "外の **強調** です" in fence4_got:
        passed += 1
    else:
        failed += 1
        print(f"FAIL(fence4): {fence4_got!r}")

    # 検出モードで違反行が数えられること
    _, v = process_text("これは" + "**重要**" + "です", fix=False)
    if len(v) == 1:
        passed += 1
    else:
        failed += 1
        print(f"FAIL(detect): {v!r}")

    # --under パス絞り込み（Issue #85）
    under_cases = [
        (["docs/a.md", "content/b.md", "docs/sub/c.md"], ["docs/"], ["docs/a.md", "docs/sub/c.md"]),
        (["docs/a.md", "docsx/b.md"], ["docs"], ["docs/a.md"]),  # プレフィックス誤爆しない（docsx を含めない）
        (["docs/a.md"], [], ["docs/a.md"]),  # --under 未指定なら無変更
        (["./docs/a.md"], ["docs"], ["./docs/a.md"]),  # 先頭 ./ を許容
        (["docs/a.md", "content/b.md"], ["docs", "content"], ["docs/a.md", "content/b.md"]),  # 複数指定
    ]
    for paths_in, unders, expected in under_cases:
        got = filter_under(paths_in, unders)
        if got == expected:
            passed += 1
        else:
            failed += 1
            print(f"FAIL(under): paths={paths_in!r} unders={unders!r}\n  expected: {expected!r}\n  got:      {got!r}")

    # 整形対象外パス（第三者著作物の保護・#233）
    excluded_cases = [
        ("docs/02_requirements/minimum-requirements.md", True),
        ("./docs/02_requirements/minimum-requirements.md", True),   # 先頭 ./ を許容
        ("docs/02_requirements/prd.md", False),                      # 同じディレクトリの別ファイルは対象
        ("minimum-requirements.md", False),                          # 末尾一致では除外しない（完全一致のみ）
        ("docs/02_requirements/minimum-requirements.md.bak", False), # 前方一致でも除外しない
    ]
    for path_in, expected in excluded_cases:
        got = is_excluded(path_in)
        if got == expected:
            passed += 1
        else:
            failed += 1
            print(f"FAIL(excluded): path={path_in!r} expected={expected} got={got}")

    # 除外パスが実在すること（リネームで除外が静かに無効化されるのを防ぐ）
    for rel in EXCLUDED_PATHS:
        if (Path(__file__).resolve().parent.parent / rel).is_file():
            passed += 1
        else:
            failed += 1
            print(f"FAIL(excluded-exists): EXCLUDED_PATHS の {rel} が存在しない（リネーム漏れ？）")

    # --under 単独指定はディレクトリ配下を再帰的にファイル選択する（Issue #706）
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.md").write_text("dummy", encoding="utf-8")
        (tmp_path / "sub" / "b.md").write_text("dummy", encoding="utf-8")
        (tmp_path / "sub" / "c.markdown").write_text("dummy", encoding="utf-8")
        (tmp_path / "sub" / "d.txt").write_text("dummy", encoding="utf-8")  # .md 以外は対象外

        got = sorted(walk_md_under([str(tmp_path)]))
        expected = sorted(
            str(p)
            for p in (
                tmp_path / "a.md",
                tmp_path / "sub" / "b.md",
                tmp_path / "sub" / "c.markdown",
            )
        )
        if got == expected:
            passed += 1
        else:
            failed += 1
            print(f"FAIL(walk_md_under): expected={expected!r}\n  got:      {got!r}")

        # 存在しないディレクトリは黙ってスキップ（0 件の判定は呼び出し側の責務）
        got_missing = walk_md_under([str(tmp_path / "does-not-exist")])
        if got_missing == []:
            passed += 1
        else:
            failed += 1
            print(f"FAIL(walk_md_under-missing): got={got_missing!r}")

    # walk_md_under: EXCLUDED_DIRS 配下（.git / node_modules / .next 等）へは再帰しない（Issue #711）
    with tempfile.TemporaryDirectory() as tmp_excl:
        tmp_excl_path = Path(tmp_excl)
        (tmp_excl_path / "keep.md").write_text("dummy", encoding="utf-8")
        for d in ("node_modules/some-pkg", ".git/refs", ".next/cache", "dist", "coverage"):
            sub = tmp_excl_path / d
            sub.mkdir(parents=True)
            (sub / "README.md").write_text("dummy", encoding="utf-8")

        got_excl = sorted(walk_md_under([str(tmp_excl_path)]))
        expected_excl = [str(tmp_excl_path / "keep.md")]
        if got_excl == expected_excl:
            passed += 1
        else:
            failed += 1
            print(
                f"FAIL(walk_md_under-excluded-dirs): expected={expected_excl!r}\n  got:      {got_excl!r}"
            )

    # resolve_targets: モード判定（Issue #706 の核心 — --under 単独が fail-open しないこと）
    # 注意: changed=True の行は実 git を叩く changed_md_files() の結果に依存しうるため、
    # ここでは unders と組み合わせても常に "other" になる（unders=[] でフィルタ自体が
    # 走らない）行だけを置く。changed + --under の組み合わせ（フィルタ結果に依存する分岐）は
    # 下の monkeypatch ブロックで実 git 状態から切り離して決定的に検証する（#711）。
    resolve_cases = [
        # (files, changed, unders, 期待 mode)
        ([], False, [], "none"),                       # 何も指定なし → 誤用
        (["a.md"], False, [], "other"),                # ファイル明示指定・フィルタなし
        ([], True, [], "other"),                       # --changed のみ・フィルタなし
        ([], False, ["/nonexistent-dir-706"], "under-only"),  # --under 単独 → ファイル選択モード
        (["docs/a.md"], False, ["docs"], "other"),      # files + --under が一致 → 従来どおり絞り込み
        # 🔴 #711 CRITICAL の核心: files はあるが --under 配下と 1 件も一致しない
        # → 以前は黙って mode="other"（0 件・exit 0・fail-open）だったが、
        #   候補が存在したのにフィルタで全滅したケースは "filtered-to-zero" で警告する
        (["a.md"], False, ["docs"], "filtered-to-zero"),
        (["docs/a.md", "content/b.md"], False, ["docs"], "other"),  # 一部一致なら絞り込み結果を返す
    ]
    for files_in, changed_in, unders_in, expected_mode in resolve_cases:
        got_paths, got_mode = resolve_targets(files_in, changed_in, unders_in)
        if got_mode == expected_mode:
            passed += 1
        else:
            failed += 1
            print(
                f"FAIL(resolve_targets-mode): files={files_in!r} changed={changed_in!r} "
                f"unders={unders_in!r}\n  expected: {expected_mode!r}\n  got:      {got_mode!r}"
            )
        if expected_mode == "filtered-to-zero" and got_paths != []:
            failed += 1
            print(f"FAIL(resolve_targets-filtered-to-zero-paths): got_paths={got_paths!r}")

    # resolve_targets: changed + --under の組み合わせを実 git 状態から切り離して決定的に検証する。
    # changed_md_files() はこのモジュールの module-level 関数なので、self_test 内で一時的に
    # 差し替えて元に戻す（並行実行中の他エージェントの .md 変更で self-test がフレーキーに
    # ならないようにするための隔離。#711）。
    _orig_changed_md_files = globals()["changed_md_files"]
    try:
        globals()["changed_md_files"] = lambda: ["docs/x.md", "content/y.md"]
        _, mode_hit = resolve_targets([], True, ["docs"])
        if mode_hit == "other":
            passed += 1
        else:
            failed += 1
            print(f"FAIL(resolve_targets-changed-under-hit): expected='other' got={mode_hit!r}")

        globals()["changed_md_files"] = lambda: ["content/y.md"]  # docs/ 配下は 1 件も無い
        _, mode_miss = resolve_targets([], True, ["docs"])
        if mode_miss == "filtered-to-zero":
            passed += 1
        else:
            failed += 1
            print(f"FAIL(resolve_targets-changed-under-miss): expected='filtered-to-zero' got={mode_miss!r}")

        globals()["changed_md_files"] = lambda: []  # 真に変更 .md が 0 件 → 従来どおり 'other'（exit 0 維持）
        _, mode_genuine_zero = resolve_targets([], True, ["docs"])
        if mode_genuine_zero == "other":
            passed += 1
        else:
            failed += 1
            print(f"FAIL(resolve_targets-changed-genuine-zero): expected='other' got={mode_genuine_zero!r}")
    finally:
        globals()["changed_md_files"] = _orig_changed_md_files

    # resolve_targets: --under 単独指定が実際にディレクトリ配下のファイルを返すこと
    with tempfile.TemporaryDirectory() as tmp2:
        tmp2_path = Path(tmp2)
        (tmp2_path / "x.md").write_text("dummy", encoding="utf-8")
        paths_got, mode_got = resolve_targets([], False, [str(tmp2_path)])
        if mode_got == "under-only" and paths_got == [str(tmp2_path / "x.md")]:
            passed += 1
        else:
            failed += 1
            print(f"FAIL(resolve_targets-underonly-files): mode={mode_got!r} paths={paths_got!r}")

    # main() の exit code 分岐を CLI 経由で直接確認する（Issue #706 の核心）。
    # resolve_targets() の mode 判定だけでは main() 側の分岐（return 0/1/2）まで
    # 検証できないため、実際にサブプロセスとして起動し終了コードを突合する。
    import tempfile as _tf

    with _tf.TemporaryDirectory() as tmp3:
        tmp3_path = Path(tmp3)
        # #711 CRITICAL の反例そのもの: 明示ファイル指定と --under の対象ディレクトリが
        # 一致しない（outside.md は rules/ 配下に無い）→ 修正前は 0 件検査で exit 0（fail-open）。
        outside_md = tmp3_path / "outside.md"
        outside_md.write_text("これは" + "**重要**" + "です", encoding="utf-8")
        rules_dir = tmp3_path / "rules"
        rules_dir.mkdir()
        cli_cases = [
            # (args, 期待終了コード, 説明)
            (["--under", str(tmp3_path / "no-such-dir")], 1, "--under 単独・0 件 → 失敗扱い"),
            ([], 2, "引数なし → 誤用エラー"),
            (
                [str(outside_md), "--under", str(rules_dir)],
                1,
                "#711 反例: 明示ファイル + --under 不一致 → fail-open せず失敗扱い",
            ),
        ]
        for extra_args, expected_code, desc in cli_cases:
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), *extra_args],
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(tmp3_path),
            )
            if r.returncode == expected_code:
                passed += 1
            else:
                failed += 1
                print(
                    f"FAIL(cli-exitcode): {desc} args={extra_args!r}"
                    f"\n  expected exit={expected_code} got exit={r.returncode}"
                    f"\n  stderr={r.stderr!r}"
                )

        # --under 単独指定・実際に .md がある場合は exit 0 で検査自体が走ること
        (tmp3_path / "z.md").write_text("これは" + "**重要**" + "です", encoding="utf-8")
        r_detect = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--under", str(tmp3_path)],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp3_path),
        )
        # 半角スペース違反を仕込んだので検出モードは exit 1（かつ 0 件警告文言は出ない）
        if r_detect.returncode == 1 and "1 件もありません" not in r_detect.stderr:
            passed += 1
        else:
            failed += 1
            print(
                "FAIL(cli-underonly-detects-file): "
                f"exit={r_detect.returncode} stderr={r_detect.stderr!r} stdout={r_detect.stdout!r}"
            )

    print(f"\n[cjk-md] self-test: {passed} passed / {failed} failed")
    return 0 if failed == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="CJK Markdown 半角スペース チェッカー＆整形")
    ap.add_argument("files", nargs="*", help="対象 .md ファイル")
    ap.add_argument("--fix", action="store_true", help="自動整形して上書き")
    ap.add_argument("--changed", action="store_true", help="git で変更された .md を対象にする")
    ap.add_argument(
        "--under",
        action="append",
        default=[],
        metavar="DIR",
        help="このディレクトリ配下の .md だけを対象にする（複数指定可・--changed と併用して並行編集の巻き込みを防ぐ・#85）",
    )
    ap.add_argument("--self-test", action="store_true", help="セルフテストを実行")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    paths, mode = resolve_targets(args.files, args.changed, args.under)

    if not paths:
        if mode == "none":
            # 誤用（ファイル指定・--changed・--under のいずれも無い）。呼び出し元は必ず
            # いずれかを渡すため、ここに到達するのは想定外の使い方＝usage error として扱う
            # （Issue #706: 0 件を黙って PASS にしない）。
            print(
                "[cjk-md] エラー: 対象ファイルが指定されていません"
                "（ファイル指定 / --changed / --under のいずれかが必要）",
                file=sys.stderr,
            )
            return 2
        if mode == "under-only":
            # --under 単独指定でディレクトリ配下を再帰選択したが 1 件も .md が無かった。
            # ディレクトリ typo の可能性が高く、他モードと違って「0 件が日常的に起こる
            # 正常系」ではないため、明示的に失敗として扱う（Issue #706 の本丸）。
            print(
                f"[cjk-md] 警告: --under で指定した配下に .md ファイルが 1 件もありません: {args.under}",
                file=sys.stderr,
            )
            print(
                "[cjk-md]   → パス指定の誤りがないか確認してください（黙って PASS 扱いにしない）",
                file=sys.stderr,
            )
            return 1
        if mode == "filtered-to-zero":
            # 明示ファイル指定 / --changed 由来の候補は存在したのに、--under の絞り込みで
            # 全滅した。「対象自体が無い」日常的な 0 件（mode=="other"）とは異なり、
            # 指定ミス（fail-open）の可能性が高いため明示的に失敗として扱う（Issue #711）。
            print(
                "[cjk-md] 警告: 明示ファイル指定 / --changed 由来の対象は存在しましたが、"
                f"--under {args.under} の絞り込みで 0 件になりました",
                file=sys.stderr,
            )
            print(
                "[cjk-md]   → 明示ファイル指定 / --changed の対象と --under のディレクトリが"
                " 一致しているか確認してください（黙って PASS 扱いにしない）",
                file=sys.stderr,
            )
            return 1
        # mode == "other"（files / --changed 経由）: --changed で変更 .md が 0 件なのは
        # 日常的な正常系（多くの PR は .md を変更しない）。run_checks.sh 等の既存呼び出し元を
        # 壊さないため exit 0 を維持しつつ、メッセージで「0 件は正常」と明示する（Issue #706）。
        print(
            "[cjk-md] 対象ファイルなし（変更された .md が無い、または --under の絞り込みで 0 件・OK）",
            file=sys.stderr,
        )
        return 0

    return check_files(paths, args.fix)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"[cjk-md] checker error: {e}", file=sys.stderr)
        sys.exit(2)
