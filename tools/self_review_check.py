#!/usr/bin/env python3
"""self_review_check.py（汎用ベース）

PR 作成前のセルフレビュー機械チェック。pre-pr-create-check.sh フックから呼ばれ、
Error 検出時（exit 1）に PR 作成をブロックする「Lv3 ハードコンストレイント」。

汎用ベースでは誤ブロックを避けるため保守的に、明確な事故のみを Error にする:
  - Error: マージコンフリクト痕跡（<<<<<<< / ======= / >>>>>>>）
  - Error: 巨大ファイルの新規追加（既定 5MB 超・SELF_REVIEW_MAX_MB で調整）
  - Warning: デバッグ痕跡（TODO/FIXME/console.log/print デバッグ等）※ブロックしない

プロジェクト固有のチェックは docs/rules/self-review-checklist.md に追記し、
本スクリプトに検査関数を足して拡張する。

終了コード: 0=合格 or Warning のみ / 1=Error あり（ブロック） / 2=チェッカー異常
"""
from __future__ import annotations
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from typing import Callable

import git_diff_utils
from md_fence import fence_flags, mask_inline_code
from pr_meta_patterns import SPRINT_GOAL_LINE_RE, meta_line_re

MAX_MB = float(os.environ.get("SELF_REVIEW_MAX_MB", "5"))
CONFLICT_MARKERS = ("<<<<<<< ", "=======", ">>>>>>> ")

# base-update-notes 追記リマインド（Issue #211）の検出スコープ。
# apply-to-repo.sh の同期（cp -a）はファイル削除・リネームを下流へ伝播しないため、
# 削除/リネーム（D/R）は下流に孤立ファイルを残す最高確度の「下流手動対応」シグナル。
# スコープは apply-to-repo.sh の SYNC_PATHS + docs/rules/ 全体（Warm 層含む）。
UPDATE_NOTES = "docs/base-update-notes.md"
DESTRUCTIVE_SCOPE = (
    "docs/rules/", ".claude/rules/", ".claude/hooks/", ".claude/skills/",
    ".claude/agents/", ".claude/output-styles/", ".claude/commands/",
    ".claude-plugin/", "tools/", "scripts/", "modules.yaml", ".mcp.json",
)
# 配線ファイル: 変更ステータスを問わず下流の手動判断（マージ・モジュール選択・
# フック登録）が要りやすいファイル。CLAUDE.md は PROTECT_PATHS（同期対象外）のため
# base 側の変更が下流へ自動伝播しない唯一級のファイルで、新規 Hot ルールの配線も
# ここに現れる（新規追加 A の代理シグナル）。
WIRING_FILES = ("modules.yaml", ".claude/settings.json", "CLAUDE.md")

# アップデート確認の基準点マーカー（apply-to-repo.sh が下流リポジトリに生成・Issue #205/#206）。
# コミット漏れは次回 apply-base 実行時に「初回適用」への無警告退行を招くため、
# PR 差分に含まれるかを問わず git status で直接検出する。
BASE_SYNC_STATE = ".claude/base-sync-state.json"

# CJK Markdown チェッカー（同ディレクトリの check_cjk_markdown.py）を再利用する。
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from check_cjk_markdown import process_text as _cjk_process_text
    # 整形対象外パス（第三者著作物・#233）の判定も本体と共有する。
    # ここで共有しないと「整形はされないが違反として警告され続ける」状態になり、
    # 直しようのない Warning が毎 PR 出続けて他の指摘が埋もれる。
    from check_cjk_markdown import is_excluded as _cjk_is_excluded
except ImportError:
    # ツール自体が無い場合のみ黙って無効化（任意機能）
    _cjk_process_text = None
    _cjk_is_excluded = None
except Exception as _e:  # noqa: BLE001
    # ツールはあるが壊れている → 黙殺すると再発防止が機能しないので原因を出す
    print(f"[self-review] Warning: check_cjk_markdown の読み込みに失敗（CJK 検査を無効化）: {_e}",
          file=sys.stderr)
    _cjk_process_text = None
    _cjk_is_excluded = None

# Python 危険パターン検出（FAIR Layer 0 強化・#56）。
try:
    from scan_dangerous_patterns import scan_text as _scan_py
except ImportError:
    # ツール自体が無い場合のみ黙って無効化（任意機能）
    _scan_py = None
except Exception as _e:  # noqa: BLE001
    # ツールはあるが壊れている（SyntaxError 等）→ 黙殺するとセキュリティ検査が静かに無効化される
    print(f"[self-review] Warning: scan_dangerous_patterns の読み込みに失敗（危険パターン検査を無効化）: {_e}",
          file=sys.stderr)
    _scan_py = None


# ============================================================================
# TDD コミット順序 / 縦切り(3層) / C-5（レイヤー分割禁止）検査
#
# 根拠: content/discussions/sprint-cycle-design-20260818/whiteboard.md
#   arch_tdd round2 §1（3 層再定義）・§2.2（Tier1 は git diff --name-only の
#   みで判定するゼロコスト静的検査。テスト実行や worktree checkout はしない・
#   Tier2 の実測は CI 側の責務で本ツールの担当外）。
#   round3 決定 4（C-5 新設・違反は blocking）・決定 6（TDD 検証は 2 段構成）。
# いずれも「判定材料が無ければスキップ（黙って通す）」を徹底し、アプリコード
# 未着手のドキュメント変更ブランチ等で誤検知しないようにする。
# ============================================================================

# 直前が英字だと "WASP-1" の "SP-1" / "BONUS-3" の "US-3" のような誤検出を招くため、
# 直前が英字でないことを要求する（Layer 1 セルフレビュー指摘・実測: WASP-1 → SP-1 誤爆）。
SP_PATTERN = re.compile(r"(?<![A-Za-z])SP-(\d+)")
US_PATTERN = re.compile(r"(?<![A-Za-z])US-\d+")

# `layer:frontend` 等の単純な部分文字列一致は、コミットメッセージの説明文中にたまたま
# 同じ文字列が出ただけ（例:「過去の layer:frontend 対応 Issue を統合する」）でも Error に
# なってしまう（Layer 1 セルフレビュー指摘・実測確認済み）。「誤検知で作業を止めないことを
# 優先する」方針（BRIEF.md）に反するため、行全体（先頭の箇条書き記号・`Labels:` 前置きのみ
# 許容）が label トークンのカンマ区切り列である場合に限定する（行頭・箇条書き記号直後のみ
# ヒットする、実質的な「ラベル宣言」だけを検出対象にする）。
_LAYER_LABEL_ITEM = r"layer:(?:frontend|backend|infra(?:structure)?)"
LAYER_LABEL_PATTERN = re.compile(
    rf"^[ \t]*(?:[-*・]\s*)?(?:labels?\s*[:：]\s*)?"
    rf"({_LAYER_LABEL_ITEM}(?:\s*[,、]\s*{_LAYER_LABEL_ITEM})*)"
    r"[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# テストパス判定（whiteboard 確定パターン）
# 🔴 `.mjs` を含める理由（`SP-17` / PR #416 セルフレビュー指摘）: ビルド時ツール（`tools/`）の
#    ユニットテストは `*.test.mjs` で書かれる。これが本タプルに無いと、テストファイルが
#    「プロダクションコード」として数えられ、`SD-2` の TDD コミット順序チェック
#    （`test:` コミット → `feat:` コミット）が当該ディレクトリに対して恒久的に無効化される。
TEST_PATH_GLOBS = (
    "**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx",
    "**/*.test.mjs", "**/*.spec.mjs",
    "e2e/**", "**/__tests__/**", "**/*_test.py", "tests/**",
)

# 3 層の判定対象（BRIEF.md 3 層定義テーブル・whiteboard round2 §1.2 と完全一致）
FRONTEND_GLOBS = ("app/**/page.tsx", "app/**/layout.tsx", "src/ui/**")
BACKEND_GLOBS = (
    "app/**/route.ts", "src/usecases/**", "src/domain/**", "src/infrastructure/**",
    "src/composition/**", "src/shared/**",
)
INFRA_GLOBS = (".github/workflows/**",)

_GLOB_CACHE: dict[str, "re.Pattern[str]"] = {}


def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    """`**`（0 個以上のパス階層）/ `*`（1 階層内の任意文字列）だけを解釈する簡易 glob。

    pathlib.PurePosixPath.match() は `**` を解釈しないため自前で用意する。

    🔴 **`**` はゼロ階層にもマッチする（意図的・固定仕様。`_self_test_glob_match` が固定）**:
    `app/**/page.tsx` は `app/foo/page.tsx` だけでなく `app/page.tsx` にもマッチする。
    これは gitignore・npm glob・doublestar 等が採用する標準的な `**` の解釈（"a/**/b" は
    "a/b" にもマッチする）であり、かつ Next.js App Router では `app/page.tsx`（ルート直下の
    ページ）が最頻出パターンの 1 つ（BRIEF.md の `app/**/page.tsx` はこれを含めて FE 層と
    分類する意図）。ここでゼロ階層を弾くと最も一般的なルートページが FE 層として検出されず、
    縦切り判定（検査B）が「FE を全く触っていない」と誤判定する方が実害が大きい。
    """
    segments = pattern.split("/")
    regex = "^"
    for idx, seg in enumerate(segments):
        is_last = idx == len(segments) - 1
        if seg == "**":
            regex += ".*" if is_last else "(?:.*/)?"
        else:
            regex += re.escape(seg).replace(r"\*", "[^/]*")
            if not is_last:
                regex += "/"
    regex += "$"
    return re.compile(regex)


def _glob_match(pattern: str, path: str) -> bool:
    rx = _GLOB_CACHE.get(pattern)
    if rx is None:
        rx = _glob_to_regex(pattern)
        _GLOB_CACHE[pattern] = rx
    return bool(rx.match(path))


def is_test_path(path: str) -> bool:
    """テストパス判定（`TEST_PATH_GLOBS` のいずれかに一致するか）。"""
    return any(_glob_match(g, path) for g in TEST_PATH_GLOBS)


def _is_infra_path(path: str) -> bool:
    """インフラ層判定。運用基盤の契約（`INF-n`）であり `src/infrastructure/`
    （クリーンアーキテクチャのアダプタ層＝バックエンド層扱い）とは別物（混同禁止・BRIEF.md 注記）。
    """
    if any(_glob_match(g, path) for g in INFRA_GLOBS):
        return True
    name = Path(path).name
    if name == ".env.example" or name.startswith("next.config."):
        return True
    return False


def touched_layers(files: list[str]) -> set[str]:
    """diff ファイル一覧から触れている層（frontend/backend/infra）集合を返す。"""
    layers: set[str] = set()
    for f in files:
        if any(_glob_match(g, f) for g in FRONTEND_GLOBS):
            layers.add("frontend")
        if any(_glob_match(g, f) for g in BACKEND_GLOBS):
            layers.add("backend")
        if _is_infra_path(f):
            layers.add("infra")
    return layers


def branch_commits() -> list[str]:
    """`origin/{default}..HEAD` のコミット SHA 一覧（古い→新しい順）。取得不可なら空。"""
    base = f"origin/{default_branch()}"
    r = sh(["git", "rev-list", "--reverse", f"{base}..HEAD"])
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line.strip()]


def commit_message(sha: str) -> str:
    r = sh(["git", "log", "-1", "--format=%s", sha])
    return r.stdout.strip() if r.returncode == 0 else ""


def commit_files(sha: str) -> list[str]:
    # --root: 親を持たないコミット（ルートコミット）は素の diff-tree だと常に空を返す
    # （Layer 1 セルフレビュー指摘・実測確認済み）。--root は親付きコミットの挙動は変えない
    # （空木との差分になるのはルートコミットのときだけ）ため安全に付与できる。
    r = sh(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha])
    return r.stdout.splitlines() if r.returncode == 0 else []


def current_branch_name() -> str:
    r = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else ""


def branch_sp_number() -> str | None:
    """ブランチ名から `SP-n` を拾う（`git branch -r` 重複検査専用。命名確定値・BRIEF.md）。"""
    m = SP_PATTERN.search(current_branch_name())
    return m.group(1) if m else None


def _sp_signal_text() -> str:
    """SP-n / US-n / レイヤーラベル検出用に、ブランチ名 + 全コミットメッセージを連結して返す。
    PR 本文は PR 作成前（pre-pr-create-check.sh フック）には存在しないため対象外（「相当」の範囲）。
    """
    return current_branch_name() + "\n" + "\n".join(commit_message(sha) for sha in branch_commits())


def tdd_commit_order_warnings(
    commit_info: list[tuple[str, str, list[str]]] | None = None,
) -> list[str]:
    """検査A: TDD コミット順序（Tier1・静的・ゼロコスト。テストは実行しない）。根拠: `SD-2`。

    - `test:` コミットの diff がテストパス以外を含む → Warning
    - `feat:`/`fix:` コミットの diff がテストパスのみ → Warning（コミット種別と中身の不一致）
    - ブランチ内にテストパスの diff が 1 つも無ければ（アプリ未着手）検査自体をスキップ

    `commit_info`（sha, message, files のタプル列）を渡すと git を一切呼ばずに判定できる
    （`--self-test` 用の注入口。省略時は従来どおり git から取得する）。
    """
    if commit_info is None:
        commits = branch_commits()
        if not commits:
            return []
        commit_info = [(sha, commit_message(sha), commit_files(sha)) for sha in commits]

    any_test = any(any(is_test_path(f) for f in files) for _, _, files in commit_info)
    if not any_test:
        return []

    out: list[str] = []
    for sha, msg, files in commit_info:
        if not files:
            continue
        test_files = [f for f in files if is_test_path(f)]
        non_test_files = [f for f in files if not is_test_path(f)]
        short = sha[:7]
        if msg.startswith("test:") and non_test_files:
            out.append(
                f"TDD コミット順序: {short} `{msg}` は test: コミットですがテスト以外の"
                f"ファイルを含みます: {', '.join(non_test_files[:5])}"
            )
        elif (msg.startswith("feat:") or msg.startswith("fix:")) and test_files and not non_test_files:
            kind = msg.split(":", 1)[0]
            out.append(
                f"TDD コミット順序: {short} `{msg}` は {kind}: コミットですがテストパスのみを"
                "変更しています（コミット種別と中身が不一致）"
            )
    return out


def vertical_slice_check(
    files: list[str],
    *,
    app_or_src_exists: bool | None = None,
    sp_signal_text: str | None = None,
) -> tuple[list[str], list[str]]:
    """検査B: 縦切り(3 層タッチ)判定。根拠: `user-story-map.md` §5.2 / whiteboard round2 §1。

    - `app/`・`src/` がどちらも無ければ（アプリ未着手）検査自体をスキップ
    - ブランチ名/コミットメッセージから `SP-n` を拾えなければスキップ
    - `SP-1`: 3 層すべてに diff が無ければ Error（blocking）
    - `SP-4`/`SP-5` のハードコード特別扱いはしない（Layer 1 セルフレビュー指摘・二重管理の解消）。
      `US-n` 参照が無い（イネイブラー単独扱い・判定不能を含む・`SP-4`/`SP-5` は通常ここに該当）は
      すべて汎用ルールで exempt になる。将来 `SP-4`/`SP-5` に `US-n` が追加された場合も
      ドキュメント側の変更だけで自動的に整合する
    - それ以外（`US-n` を含む機能スプリント。`SP-4`/`SP-5` でも `US-n` を含めば対象になる）:
      3 層中 2 層未満なら Warning

    `app_or_src_exists` / `sp_signal_text` を渡すと I/O・git を一切呼ばずに判定できる
    （`--self-test` 用の注入口。省略時は従来どおり実ファイルシステム・git から取得する）。
    """
    errors: list[str] = []
    warnings: list[str] = []
    if app_or_src_exists is None:
        app_or_src_exists = Path("app").is_dir() or Path("src").is_dir()
    if not app_or_src_exists:
        return errors, warnings

    text = sp_signal_text if sp_signal_text is not None else _sp_signal_text()
    sp_match = SP_PATTERN.search(text)
    if not sp_match:
        return errors, warnings
    sp_num = sp_match.group(1)
    layers = touched_layers(files)

    if sp_num == "1":
        missing = {"frontend", "backend", "infra"} - layers
        if missing:
            errors.append(
                "縦切り(SP-1): 歩く骨格の確立スプリントですが未着手の層があります: "
                f"{', '.join(sorted(missing))}（3 層すべての diff が必要）"
            )
        return errors, warnings

    if not US_PATTERN.search(text):
        return errors, warnings

    if len(layers) < 2:
        touched = "、".join(sorted(layers)) if layers else "なし"
        warnings.append(
            f"縦切り(SP-{sp_num}): US-n を含む機能スプリントですが 3 層中 2 層以上に"
            f"触れていません（触れている層: {touched}）"
        )
    return errors, warnings


def layer_split_check(text: str | None = None) -> list[str]:
    """検査C 前段: `C-5`（技術レイヤー別 Issue 分割の禁止）違反痕跡（Error・blocking）。

    `text` を渡すと git を呼ばずに判定できる（`--self-test` 用の注入口。省略時は従来どおり
    `_sp_signal_text()`＝ブランチ名 + コミットメッセージを git から取得する）。
    """
    if text is None:
        text = _sp_signal_text()
    m = LAYER_LABEL_PATTERN.search(text)
    if not m:
        return []
    return [
        f"C-5 違反の疑い: ブランチ名/コミットメッセージにレイヤー分割ラベルの痕跡があります"
        f"（`{m.group(1)}`）。1 SP-n = 1 Issue とし、技術レイヤー別に Issue を分割しないでください"
    ]


_UNSET = object()


def duplicate_sp_branch_warning(
    sp_num: str | None = _UNSET,  # type: ignore[assignment]
    remote_branches: list[str] | None = None,
) -> str | None:
    """検査C 後段: 同一 `SP-n` の作業ブランチが複数存在する形跡（Warning）。

    `sp_num`（未指定センチネル `_UNSET` の場合のみ `branch_sp_number()` で git から取得）と
    `remote_branches`（未指定の場合のみ `git branch -r` で取得）を渡すと git を呼ばずに判定できる
    （`--self-test` 用の注入口。`sp_num=None` は「拾えなかった」を意味する正当な入力として区別する）。
    """
    if sp_num is _UNSET:
        sp_num = branch_sp_number()
    if not sp_num:
        return None
    if remote_branches is None:
        r = sh(["git", "branch", "-r"])
        if r.returncode != 0:
            return None
        remote_branches = r.stdout.splitlines()
    # SP_PATTERN と同じ理由（issue 2）で直前が英字の誤爆を防ぐ（例: "WASP-3" の "SP-3"）
    pattern = re.compile(rf"(?<![A-Za-z])SP-{re.escape(sp_num)}(?!\d)")
    matches = [b.strip() for b in remote_branches if pattern.search(b)]
    if len(matches) >= 2:
        return (
            f"C-5: 同一 SP-{sp_num} に対する作業ブランチが複数存在する形跡があります: "
            f"{', '.join(matches)} → 技術レイヤー別に分割していないか確認してください"
        )
    return None


def tdd_and_sprint_checks(files: list[str]) -> tuple[list[str], list[str]]:
    """検査 A(TDD 順序)/B(縦切り)/C(`C-5`) をまとめて実行する（PR 作成前の Tier1 静的検査）。"""
    errors: list[str] = []
    warnings: list[str] = []
    warnings.extend(tdd_commit_order_warnings())
    b_errors, b_warnings = vertical_slice_check(files)
    errors.extend(b_errors)
    warnings.extend(b_warnings)
    errors.extend(layer_split_check())
    dup_warn = duplicate_sp_branch_warning()
    if dup_warn:
        warnings.append(dup_warn)
    return errors, warnings


# 🔵 パターンを分割リテラルで書く。ベタ書きすると **この検査自身のソース行がパターンに
#    一致し**、本ファイルを変更した PR で必ず自分自身を「デバッグ痕跡」として誤検出する
#    （実際に発生した・#233）。分割して書けば実行時の値は同じまま、ソース上には一致しない。
DEBUG_TRACE_PATTERNS = ("console" ".log(", "debugger" ";", "import" " pdb")


def has_debug_trace(lowered_line: str) -> bool:
    """小文字化済みの 1 行にデバッグ痕跡パターンが含まれるか判定する。"""
    return any(pat in lowered_line for pat in DEBUG_TRACE_PATTERNS)


def cjk_violation_lines(text: str) -> list[int]:
    """CJK 半角スペース違反のある行番号一覧を返す（チェッカー不在時は空）。"""
    if _cjk_process_text is None:
        return []
    try:
        _, violations = _cjk_process_text(text, fix=False)
        return [ln for ln, _ in violations]
    except Exception as e:  # noqa: BLE001
        print(f"[self-review] Warning: CJK 検査でエラー: {e}", file=sys.stderr)
        return []


def sh(args, timeout=20):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def default_branch() -> str:
    return git_diff_utils.default_branch()


def changed_files() -> list[str]:
    """変更ファイル一覧（base range + worktree + cached + untracked・実在チェックあり・出現順維持）。

    #195: 収集ロジック本体は `tools/git_diff_utils.py` の `collect_changed_files()` に統合済み。
    既定引数がここの旧実装（base range → worktree → cached → untracked・`require_existing=True`・
    `sort=False`）とそのまま一致するため、引数なしで呼ぶだけで既存挙動を維持できる。
    """
    return git_diff_utils.collect_changed_files()


def update_notes_reminder(files: list[str]) -> str | None:
    """下流影響の破壊的シグナルがあるのに base-update-notes.md 追記が無ければ文言を返す。

    検出ロジック（開発リポジトリの議論記録・議題 ID: base-fork-review-211 の合意・Warning 一本）:
      - D/R（削除・リネーム）: DESTRUCTIVE_SCOPE 全域で拾う（range diff 1 本のみ）
      - 配線ファイル（WIRING_FILES）: ステータス不問の名前照合
      - .claude/rules/ への追加（新規 Hot 化 symlink）
    単純な内容修正（M）は自動同期で下流に届くため対象外（誤検知抑制の要）。
    base-update-notes.md を持たないリポジトリ（下流フォーク）ではスキップする。
    """
    if not Path(UPDATE_NOTES).is_file():
        return None
    if UPDATE_NOTES in files:
        return None
    impacted: list[str] = []
    r = sh(["git", "diff", "--name-status", f"origin/{default_branch()}...HEAD"])
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            st, old = parts[0][:1], parts[1]  # R100 → R / リネームは旧パスで判定
            if st in ("D", "R") and old.startswith(DESTRUCTIVE_SCOPE):
                impacted.append(f"{st}:{old}")
            elif st == "A" and old.startswith(".claude/rules/"):
                impacted.append(f"A:{old}")
    impacted += [f"変更:{f}" for f in files if f in WIRING_FILES]
    if not impacted:
        return None
    shown = ", ".join(impacted[:10]) + ("…" if len(impacted) > 10 else "")
    return (
        "下流影響シグナル（削除/リネーム・配線ファイル変更）を検出しましたが "
        f"{UPDATE_NOTES} に追記がありません: {shown}"
        " → 下流で手動対応（削除追従・settings/CLAUDE.md 配線・モジュール判断）が必要なら"
        "同一 PR でエントリを追記してください（不要な変更なら無視して構いません。"
        "特にファイル削除は同期が下流へ伝播しないため追記必須）"
    )


def base_sync_state_reminder() -> str | None:
    """base-sync-state.json が存在するのに未コミットならリマインドを返す（Issue #206）。

    PR 差分（changed_files）に載るとは限らない（別セッションで生成されたまま放置される
    ケースがある）ため、対象パス限定の git status で独立に検査する。
    """
    if not Path(BASE_SYNC_STATE).is_file():
        return None
    r = sh(["git", "status", "--porcelain", "--", BASE_SYNC_STATE])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return (
        f"{BASE_SYNC_STATE}（アップデート確認の基準点マーカー）が未コミットです"
        " → コミットに含めないと次回の apply-base 実行が基準点を見失い、"
        "無警告で初回適用扱いに退行します（UPDATE NOTES の手動手順確認もスキップされます）"
    )


def rule_deletion_citation_reminder(files: list[str]) -> str | None:
    """docs/rules/*.md の削除行を検出したら PR 本文への実ケース記載をリマインドする（Issue base#469）。

    削減の品質バー（token-optimization-rules.md「削減の品質バーを先に固定する」）は、ルール文書の
    削除・降格・要約に「実際に適用されたはずの直近の実ケース」1 件以上を PR 本文へ記載することを
    求める。self-review 実行時点では PR 本文がまだ存在しないため、ここでは削除行の有無だけを
    機械検出してリマインドする（記載の検証ではなく Warning 一本のリマインド）。
    """
    rule_docs = [f for f in files if f.startswith("docs/rules/") and f.endswith(".md")]
    if not rule_docs:
        return None
    base = f"origin/{default_branch()}"
    deleted_count: dict[str, int] = {}
    # コミット済み差分・ステージ済み・作業ツリーの 3 経路を合算する（changed_files() と同じ理由:
    # PR 作成前のセルフレビューは未コミットの編集が大半のため、HEAD 比較だけでは見落とす）
    for args in (
        ["git", "diff", "--numstat", f"{base}...HEAD", "--", *rule_docs],
        ["git", "diff", "--cached", "--numstat", "--", *rule_docs],
        ["git", "diff", "--numstat", "--", *rule_docs],
    ):
        r = sh(args)
        if r.returncode != 0:
            continue
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            _added, removed, path = parts
            if removed.isdigit():
                deleted_count[path] = max(deleted_count.get(path, 0), int(removed))
    deleted = [f"{path}(-{n})" for path, n in deleted_count.items() if n > 0]
    if not deleted:
        return None
    shown = ", ".join(deleted[:10]) + ("…" if len(deleted) > 10 else "")
    return (
        f"docs/rules/*.md の削除行を検出しました: {shown}"
        " → PR 本文に実ケース（Issue コメント / PR diff / セッションの行動記録を1件以上）を記載してください"
        "（token-optimization-rules.md「削減の品質バーを先に固定する」）"
    )


def hot_budget_reminder(files: list[str]) -> str | None:
    """Hot 層（`.claude/rules/` 実体・`token-optimization-rules.md`）変更時に予算超過を機械検証する（Issue base#469）。"""
    hot_dir = Path(".claude/rules")
    hot_names = {p.name for p in hot_dir.glob("*.md")} if hot_dir.is_dir() else set()
    touches_hot = any(
        f == "docs/rules/token-optimization-rules.md" or Path(f).name in hot_names
        for f in files
    )
    if not touches_hot:
        return None
    proc = sh([sys.executable, "tools/check_hot_budget.py"], timeout=20)
    if proc.returncode == 0:
        return None
    lines = (proc.stdout or "").strip().splitlines()
    bullet_lines = [l.strip("- ").strip() for l in lines if l.strip().startswith("-")]
    # 通常は "- " 箇条書きの NG 理由行が本体。ツール異常（stdout 無し）等は stderr 全文を落とさず保持する
    detail = "; ".join(bullet_lines) or "; ".join(lines) or (proc.stderr or "").strip() or "unknown"
    return f"Hot 層予算チェック NG: {detail} → docs/rules/token-optimization-rules.md の増減ログを更新してください"


# ============================================================================
# --self-test（ネットワーク・git 不要のユニットテスト）
#
# 対象は検査 A/B/C の追加関数（TDD コミット順序・縦切り・C-5）。commit_info /
# app_or_src_exists / sp_signal_text / remote_branches を注入して git 呼び出しを
# 一切行わずに判定ロジックだけを検証する（合成 git リポジトリは作らない・遅くて壊れやすいため）。
# 呼び出し側（tools/sprint_backlog_sync.py run_self_test()）と同じ流儀:
# `_self_test_<name>() -> list[str]`（失敗メッセージの列挙）をグループごとに定義し、
# `run_self_test()` がグループ名付きで `FAIL[...]` を出す。
# ============================================================================

def _self_test_glob_match() -> list[str]:
    failures = []
    # ** はゼロ階層にもマッチする（意図的固定仕様。_glob_to_regex のコメント参照）
    if not _glob_match("app/**/page.tsx", "app/page.tsx"):
        failures.append("app/**/page.tsx は app/page.tsx（ゼロ階層）にマッチする想定")
    # ** は複数階層にもマッチする
    if not _glob_match("app/**/page.tsx", "app/foo/bar/page.tsx"):
        failures.append("app/**/page.tsx は app/foo/bar/page.tsx（多階層）にマッチする想定")
    # 先頭一致と部分一致の取り違え防止（アンカー漏れがあると誤ってマッチしてしまう）
    if _glob_match("app/**/page.tsx", "xapp/page.tsx"):
        failures.append("xapp/page.tsx は app/**/page.tsx にマッチしない想定（先頭アンカー）")
    if _glob_match("app/**/page.tsx", "app/foo/page.tsxx"):
        failures.append("app/foo/page.tsxx は app/**/page.tsx にマッチしない想定（末尾一致・拡張子違い）")
    # 拡張子一致（page.tsx であって page.ts ではない）
    if _glob_match("app/**/page.tsx", "app/foo/page.ts"):
        failures.append("app/foo/page.ts は app/**/page.tsx にマッチしない想定（拡張子違い）")
    # 単一 * は 1 階層内のみ（ディレクトリを跨がない）
    if _glob_match("src/ui/*", "src/ui/foo/bar.tsx"):
        failures.append("src/ui/* は多階層 src/ui/foo/bar.tsx にマッチしない想定（* は1階層限定）")
    return failures


def _self_test_is_test_path() -> list[str]:
    failures = []
    true_cases = [
        "src/foo.test.ts", "src/foo.test.tsx", "src/foo.spec.ts", "src/foo.spec.tsx",
        "e2e/login.spec.ts", "src/__tests__/foo.ts", "scripts/foo_test.py", "tests/unit/foo.py",
        "tools/gem-pool/collect.test.mjs", "tools/gem-pool/output.spec.mjs",
    ]
    for p in true_cases:
        if not is_test_path(p):
            failures.append(f"is_test_path({p!r}) は True を期待したが False")
    false_cases = [
        "src/domain/foo.ts", "app/foo/page.tsx", "src/usecases/handler.ts",
        "tools/self_review_check.py", "src/infrastructure/db.ts",
        "tools/gem-pool/collect.mjs", "tools/generate_gem_digest.mjs",
    ]
    for p in false_cases:
        if is_test_path(p):
            failures.append(f"is_test_path({p!r}) は False を期待したが True")
    return failures


def _self_test_touched_layers() -> list[str]:
    failures = []
    cases = [
        ("app/foo/page.tsx", "frontend"),
        ("app/page.tsx", "frontend"),
        ("app/foo/layout.tsx", "frontend"),
        ("src/ui/Button.tsx", "frontend"),
        ("app/api/foo/route.ts", "backend"),
        ("src/usecases/create_foo.ts", "backend"),
        ("src/domain/foo.ts", "backend"),
        ("src/infrastructure/db_adapter.ts", "backend"),  # アダプタ層＝バックエンド（INF-n とは別物）
        (".github/workflows/ci.yml", "infra"),
        (".env.example", "infra"),
        ("next.config.mjs", "infra"),
    ]
    for path, expect in cases:
        layers = touched_layers([path])
        if expect not in layers:
            failures.append(f"touched_layers([{path!r}]) に {expect!r} を期待したが {layers}")
        others = {"frontend", "backend", "infra"} - {expect}
        leaked = layers & others
        if leaked:
            failures.append(f"touched_layers([{path!r}]) が余分な層に分類された: {leaked}")
    return failures


def _self_test_vertical_slice_check() -> list[str]:
    failures = []

    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx"], app_or_src_exists=True, sp_signal_text="SP-1-walking-skeleton"
    )
    if not (len(errs) == 1 and warns == []):
        failures.append(f"SP-1 で3層欠落は Error 1件を期待したが errs={errs} warns={warns}")

    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx", "src/domain/entity.ts", ".github/workflows/ci.yml"],
        app_or_src_exists=True, sp_signal_text="SP-1-walking-skeleton",
    )
    if not (errs == [] and warns == []):
        failures.append(f"SP-1 で3層充足は Error/Warning 無しを期待したが errs={errs} warns={warns}")

    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx"], app_or_src_exists=True, sp_signal_text="SP-9-US-12-feature-branch"
    )
    if not (errs == [] and len(warns) == 1):
        failures.append(f"US-n機能スプリントで1層のみは Warning 1件を期待したが errs={errs} warns={warns}")

    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx", "src/domain/entity.ts"],
        app_or_src_exists=True, sp_signal_text="SP-9-US-12-feature-branch",
    )
    if not (errs == [] and warns == []):
        failures.append(f"US-n機能スプリントで2層以上は Warning 無しを期待したが errs={errs} warns={warns}")

    for enabler_sp in ("4", "5"):
        # US-n 参照が無いイネイブラー単独スプリントは汎用ルールで exempt になる（ハードコード無し）
        errs, warns = vertical_slice_check(
            ["app/foo/page.tsx"], app_or_src_exists=True,
            sp_signal_text=f"SP-{enabler_sp}-enabler-only-no-us-reference",
        )
        if not (errs == [] and warns == []):
            failures.append(
                f"SP-{enabler_sp} で US-n 参照が無ければ exempt を期待したが errs={errs} warns={warns}"
            )

    # issue4 回帰: ENABLER_ONLY_EXEMPT_SP のハードコードを撤廃したので、
    # SP-4/SP-5 でも US-n を含めば汎用ルール（2 層未満で Warning）が効く想定
    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx"], app_or_src_exists=True,
        sp_signal_text="SP-4-something referencing US-99",
    )
    if not (errs == [] and len(warns) == 1):
        failures.append(
            f"SP-4 で US-n を含むのに1層のみは Warning 1件を期待したが errs={errs} warns={warns}"
            "（ENABLER_ONLY_EXEMPT_SP ハードコード復活の回帰）"
        )

    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx"], app_or_src_exists=True, sp_signal_text="no-sp-number-here"
    )
    if not (errs == [] and warns == []):
        failures.append(f"SP-n を拾えない場合はスキップを期待したが errs={errs} warns={warns}")

    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx"], app_or_src_exists=False, sp_signal_text="SP-1-walking-skeleton"
    )
    if not (errs == [] and warns == []):
        failures.append(f"app/src 両方無しはスキップを期待したが errs={errs} warns={warns}")

    return failures


def _self_test_layer_split_check() -> list[str]:
    failures = []
    # 行頭の箇条書き記号直後にラベルトークンだけが並ぶ「本物の宣言」は検出する
    errs = layer_split_check("SP-9-branch\nfeat: initial commit\n- layer:frontend")
    if not (len(errs) == 1 and "C-5" in errs[0]):
        failures.append(f"行頭の layer:frontend 宣言は Error 1件を期待したが {errs}")
    errs = layer_split_check("SP-9-branch\nLabels: layer:frontend, layer:backend")
    if not (len(errs) == 1 and "C-5" in errs[0]):
        failures.append(f"Labels: layer:frontend, layer:backend 宣言は Error 1件を期待したが {errs}")

    # issue1 回帰: 説明文中にたまたま同じ文字列が出ただけでは検出しない（実測repro固定）
    errs = layer_split_check("feat: 過去の layer:frontend 対応 Issue を統合する改修")
    if errs != []:
        failures.append(f"説明文中の layer:frontend は検出なしを期待したが {errs}（issue1 の回帰）")

    errs = layer_split_check("SP-9-normal-branch-name")
    if errs != []:
        failures.append(f"痕跡が無ければ検出なしを期待したが {errs}")
    return failures


def _self_test_sp_us_word_boundary() -> list[str]:
    # issue2 回帰: 直前が英字の場合は誤検出しない（実測repro固定）。SP_PATTERN は
    # tools/self_review_check.py の主要な検出入口のため vertical_slice_check 経由でも確認する。
    failures = []
    if SP_PATTERN.search("WASP-1 の調査メモを追記") is not None:
        failures.append("WASP-1 は SP-1 として誤検出しない想定（issue2 の回帰）")
    if US_PATTERN.search("BONUS-3 keys の話") is not None:
        failures.append("BONUS-3 は US-3 として誤検出しない想定（issue2 の回帰）")
    if SP_PATTERN.search("feat: SP-9 do something") is None:
        failures.append("直前が空白/記号の正当な SP-9 は引き続き検出する想定")
    if US_PATTERN.search("参照: US-9 の対応") is None:
        failures.append("直前が空白/記号の正当な US-9 は引き続き検出する想定")

    errs, warns = vertical_slice_check(
        ["app/foo/page.tsx"], app_or_src_exists=True,
        sp_signal_text="chore: WASP-1 の調査メモを追記",
    )
    if not (errs == [] and warns == []):
        failures.append(
            f"WASP-1 を含むブランチは SP-1 と誤判定せずスキップを期待したが errs={errs} warns={warns}"
        )
    return failures


def _self_test_commit_files_root_flag() -> list[str]:
    """issue3 回帰: commit_files が --root 付きで git diff-tree を呼ぶことを固定する。

    実 git リポジトリは使わず、モジュールの `sh()` を一時的に差し替えて呼び出し引数だけを
    検証する（ルートコミット特有の挙動を毎回合成 git リポジトリで再現するのは遅くて壊れやすい）。
    """
    failures = []
    captured: dict = {}

    class _FakeResult:
        returncode = 0
        stdout = "tests/foo_test.py\n"

    def _fake_sh(args, timeout=20):
        captured["args"] = args
        return _FakeResult()

    global sh
    orig_sh = sh
    sh = _fake_sh
    try:
        result = commit_files("deadbeef")
    finally:
        sh = orig_sh

    called_args = captured.get("args", [])
    if "--root" not in called_args:
        failures.append(
            f"commit_files は --root 付き git diff-tree を呼ぶ想定だが呼び出し引数: {called_args}"
            "（issue3 の回帰: ルートコミットで空を返すバグの再発）"
        )
    if result != ["tests/foo_test.py"]:
        failures.append(f"commit_files の戻り値が想定と異なる: {result}")
    return failures


def _self_test_duplicate_sp_branch_warning() -> list[str]:
    failures = []
    if duplicate_sp_branch_warning(sp_num=None, remote_branches=[]) is not None:
        failures.append("sp_num=None は None を期待した")
    dup = duplicate_sp_branch_warning(
        sp_num="3", remote_branches=["origin/SP-3-branch-a", "origin/SP-3-branch-b", "origin/main"]
    )
    if dup is None or "SP-3" not in dup:
        failures.append(f"同一SP-nの複数リモートブランチは Warning 文字列を期待したが {dup!r}")
    if duplicate_sp_branch_warning(sp_num="3", remote_branches=["origin/SP-3-branch-a"]) is not None:
        failures.append("重複ブランチ1本のみは None を期待した")
    return failures


def _self_test_tdd_commit_order_warnings() -> list[str]:
    failures = []
    # ブランチ内にテストパスが1つも無ければスキップ（アプリ未着手の誤検知抑制）
    no_test_commits = [
        ("aaa1111", "feat: add foo", ["src/domain/foo.ts"]),
        ("bbb2222", "fix: bar", ["src/usecases/bar.ts"]),
    ]
    warns = tdd_commit_order_warnings(no_test_commits)
    if warns != []:
        failures.append(f"テストパスが1つも無ければ Warning 0件を期待したが {warns}")

    ok_commits = [
        ("ccc3333", "test: add unit test", ["tests/foo_test.py"]),
        ("ddd4444", "feat: implement foo", ["src/domain/foo.py"]),
    ]
    warns = tdd_commit_order_warnings(ok_commits)
    if warns != []:
        failures.append(f"正しい test:/feat: 分離は Warning 0件を期待したが {warns}")

    mixed_commits = [
        ("eee5555", "test: add unit test", ["tests/bar_test.py", "src/domain/bar.py"]),
    ]
    warns = tdd_commit_order_warnings(mixed_commits)
    if len(warns) != 1:
        failures.append(f"test: コミットへの非テストファイル混入は Warning 1件を期待したが {warns}")

    feat_only_test_commits = [
        ("fff6666", "feat: add baz test only", ["tests/baz_test.py"]),
    ]
    warns = tdd_commit_order_warnings(feat_only_test_commits)
    if len(warns) != 1 or "不一致" not in warns[0]:
        failures.append(f"feat: コミットがテストパスのみは Warning 1件（不一致）を期待したが {warns}")

    return failures


# 🔴 `check_architecture_boundaries.py` の `CODE_SUFFIXES` と同じ集合に保つ（PR #689）。
#    片方だけ狭いと、ドメイン層の `.mjs` が PR 前チェックの候補から落ちて検査が呼ばれない。
ARCH_CODE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".mjs", ".cjs")


def subcheck_outcome(stdout: str, returncode: int) -> tuple[list[str], list[str], str | None]:
    """補助チェッカーの出力を (errors, warnings, 異常終了の理由) に振り分ける。

    🔴 **終了コードだけで正常判定しない**: Python は未捕捉例外でも exit 1 を返すため、
    「違反あり(1)」と「チェッカー自体の死亡(1)」が区別できない。`❌`/`⚠️` の検出、または
    正常終端マーカー（`✅`/`ℹ️`）のどちらも無ければ異常終了として Warning を出す。
    """
    errors: list[str] = []
    warnings: list[str] = []
    matched = False
    ok_marker = False
    for line in (stdout or "").splitlines():
        if line.startswith("❌"):
            errors.append(line[1:].strip())
            matched = True
        elif line.startswith("⚠️"):
            warnings.append(line[2:].strip())
            matched = True
        elif line.startswith(("✅", "ℹ️")):
            ok_marker = True
    if not matched and not ok_marker:
        return errors, warnings, f"exit={returncode}"
    return errors, warnings, None


def run_subcheck(args: list[str], prefix: str, errors: list[str], warnings: list[str],
                 *, timeout: int = 30) -> None:
    """補助チェッカーを実行し、結果を errors / warnings へ prefix 付きで積む。"""
    proc = sh([sys.executable, *args], timeout=timeout)
    e, w, abnormal = subcheck_outcome(proc.stdout or "", proc.returncode)
    errors.extend(f"{prefix}: {x}" for x in e)
    warnings.extend(f"{prefix}: {x}" for x in w)
    if abnormal:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "(出力なし)"
        warnings.append(f"{prefix}チェックが異常終了しました（{abnormal}）: {tail[:200]}")


def _self_test_subcheck_outcome() -> list[str]:
    """補助チェッカー出力の振り分け（#47 の依存規則ゲート回帰）。"""
    failures: list[str] = []
    cases = [
        # (stdout, returncode, want_errors, want_warnings, want_abnormal)
        ("❌ src/x.ts:1 ARCH-1: …\n", 1, 1, 0, False),
        ("⚠️ src/x.ts が層に属していません\n", 0, 0, 1, False),
        ("✅ 依存規則 OK（3 ファイル・Warning 0 件）\n", 0, 0, 0, False),
        ("ℹ️ 検査対象のアプリコードがありません\n", 0, 0, 0, False),
        # 未捕捉例外（stdout 空 + exit 1）は「違反なし」ではなく異常終了として扱う
        ("", 1, 0, 0, True),
        ("", 2, 0, 0, True),
    ]
    for stdout, rc, want_e, want_w, want_abn in cases:
        e, w, abn = subcheck_outcome(stdout, rc)
        if len(e) != want_e or len(w) != want_w or bool(abn) != want_abn:
            failures.append(
                f"stdout={stdout!r} rc={rc}: want ({want_e},{want_w},{want_abn}) "
                f"got ({len(e)},{len(w)},{bool(abn)})"
            )
    # 起動ゲートの拡張子がチェッカー側と揃っていること（.mts/.cts の取りこぼし防止）
    for suffix in (".ts", ".tsx", ".mts", ".cts"):
        if not f"src/domain/x{suffix}".endswith(ARCH_CODE_SUFFIXES):
            failures.append(f"起動ゲートが {suffix} を対象外にしている")
    return failures


def _self_test_debug_trace() -> list[str]:
    failures = []
    # 実際のデバッグ痕跡は検出する
    # ⚠️ フィクスチャも分割リテラルで組み立てる（ベタ書きするとこのテスト自身が
    #    下の「自己誤検出」チェックに引っかかる。実際に起きた）
    positives = (
        "  " + "console" + ".log(x)",
        "\t" + "debugger" + ";",
        "import" + " pdb" + "; pdb.set_trace()",
    )
    for line in positives:
        if not has_debug_trace(line.lower()):
            failures.append(f"デバッグ痕跡として検出される想定: {line!r}")
    # 通常のコードは検出しない
    negatives = ("logger.info(x)", "const debuggerName = 1", "import pdfkit")
    for line in negatives:
        if has_debug_trace(line.lower()):
            failures.append(f"デバッグ痕跡として検出されない想定: {line!r}")
    # 🔴 回帰: 本ファイル自身のソースがパターンに一致してはならない（#233）
    #    ここが壊れると、本ファイルを触る全 PR に直しようのない Warning が出続ける。
    own_src = Path(__file__).read_text(encoding="utf-8")
    for i, line in enumerate(own_src.splitlines(), 1):
        if has_debug_trace(line.lower()):
            failures.append(
                f"self_review_check.py 自身の {i} 行目がデバッグ痕跡パターンに一致している"
                f"（パターンをベタ書きしていないか確認）: {line.strip()[:60]}"
            )
    return failures


# --- スプリントメタ（Session-Id / sp:N / Team:）の記載検査（#45 / #70 / #695） ---
# 🔴 行アンカー必須（#695）: 部分文字列一致だと「本 PR は Sprint Goal: を持たない…」のような
# 説明文にも当たり、非スプリント PR で常時 Warning が出る（オオカミ少年化）。判定の実体は
# pr_meta_patterns.py に集約している（同じ誤りを各所で独立に直さないため）。
_SPRINT_GOAL_LINE_RE = SPRINT_GOAL_LINE_RE
_SESSION_ID_LINE_RE = meta_line_re("Session-Id")
_TEAM_LINE_RE = meta_line_re("Team")
_SP_LABEL_RE = re.compile(r"(?:^|[\s(\[`])sp:\d+\b")


def sprint_meta_warnings(pr_body: str | None) -> list[str]:
    """スプリントメタの記載漏れ Warning を組み立てる（純粋関数・self-test 対象・#695）。

    - `pr_body is None`（PR 本文が渡されない手動実行）: 従来どおり一般リマインドを 1 件返す
    - `pr_body` あり: `Session-Id:` は PR の種類を問わず要求する（`--mine` 所有判定の前提）。
      `sp:N` / `Team:` は **`Sprint Goal:` 行を持つ `SP-n` スプリント PR のときだけ** 要求する
      （`session-sprint-rules.md` §2 のチーム編成規律の射程が `SP-n` に限られるため・#695）
    """
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    sid_hint = f"Session-Id: {sid}" if sid else "Session-Id: $CLAUDE_CODE_SESSION_ID を PR 本文へ"

    if pr_body is None:
        return [
            "スプリントメタを PR 本文に記載してください（session-sprint-rules.md §2/§5）: "
            f"{sid_hint} ＋ sp:N ラベル（project-mission.md 工程別標準値 + Dynamic 補正）"
            "＋ Team: トレーラー（例 `Team: fan-out(3)`・sprint-development-rules.md §1・Issue #70）"
        ]

    out: list[str] = []
    if not _SESSION_ID_LINE_RE.search(pr_body):
        out.append(
            f"PR 本文に Session-Id 行がありません（--mine 所有判定の前提・session-sprint-rules.md §2）: {sid_hint}"
        )
    if _SPRINT_GOAL_LINE_RE.search(pr_body):
        missing = []
        if not _SP_LABEL_RE.search(pr_body):
            missing.append("sp:N（project-mission.md 工程別標準値 + Dynamic 補正）")
        if not _TEAM_LINE_RE.search(pr_body):
            missing.append("Team: トレーラー（例 `Team: fan-out(3)`・sprint-development-rules.md §1・Issue #70）")
        if missing:
            out.append(
                "Sprint Goal: を持つスプリント PR です。次のスプリントメタを PR 本文に記載してください"
                "（session-sprint-rules.md §2/§5）: " + " / ".join(missing)
            )
    return out


# GitHub が認識するクローズキーワード（Issue を自動クローズするトリガーキーワード）。
# 公式ドキュメント: https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue
# GitHub が認識する 9 語: close, closes, closed, fix, fixes, fixed, resolve, resolves, resolved
#
# 🔴 除外するのは **コードブロックとコードスパンだけ**（PR #772 Layer 1 セルフレビュー）。
#   GitHub のクローズキーワード解析は blockquote（`>`）を除外しない。引用行を検査対象から
#   外していた旧実装は `> Closes #281` を素通りさせ、マージ時に Issue が自動クローズされる
#   fail-open だった。引用の中に書いても GitHub は閉じるので、こちらも検出する。
#
# 🔴 参照部（キーワードの後ろ）は GitHub が認識する 4 形式すべてを見る（旧実装は `#N` のみ）:
#   - `#281`                                             ローカル参照
#   - `GH-281`                                           GH- 形式
#   - `owner/repo#281`                                   クロスリポジトリ参照
#   - `https://github.com/owner/repo/issues/281`         URL 形式
#   キーワード直後の `:`（`Closes: #281`）も GitHub は許容するため任意で受ける。
#
# URL 形式の絞り込み（誤検出＝正当な PR のブロックを避けるため）:
#   - ホストは `://github.com/` 直後に `/` が続く形に限定する。`https://notgithub.com/...` や
#     `https://github.com.evil.example/...`・`https://gitlab.com/...` はマッチしない
#   - パスは `/issues/<数字>` のみ。`/pull/281`（PR へのリンク）はクローズ参照ではないので除外
#   - 末尾の `#issuecomment-123` 等のフラグメントは **切り離さずマッチさせたまま** にする
#     （同じ Issue を指すため、見逃す（fail-open）より検出する（fail-closed）側に倒す）
_CLOSES_KEYWORDS = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+"
    r"(?:https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+"
    r"|[\w.-]+/[\w.-]+#\d+"
    r"|GH-\d+"
    r"|#\d+)",
    re.IGNORECASE,
)

# フェンス内の行を検査本文から落とすときの差し込み文字。空行に置き換えると
# 「フェンスの前の行末の `Closes` + フェンスの後の行頭の `#123`」が `\s+` 越しに繋がって
# 誤検出になるため、非空白のプレースホルダで橋渡しを断つ。
_FENCE_PLACEHOLDER = "\x00"


def _mask_fenced_and_inline_code(pr_body: str) -> str:
    """PR 本文からコードフェンス（``` / ~~~）とインラインコードを除いたテキストを返す。

    未閉フェンスは md_fence の既定どおり「不成立」として検査対象へ戻る（fail-closed）。
    `sprint_pr_closes_detection` と `mutation_test_record_warning` が同じ境界で判定するために
    共有する（片方だけ古い境界に取り残されるのを防ぐ）。
    """
    lines = pr_body.splitlines()
    flags = fence_flags(lines)
    return "\n".join(
        _FENCE_PLACEHOLDER if in_fence else mask_inline_code(line)
        for line, in_fence in zip(lines, flags)
    )


def sprint_pr_closes_detection(pr_body: str | None) -> str | None:
    """SP-n スプリント PR にて Closes キーワードの記載を検出する（Issue #281）。

    `Sprint Goal:` 行を持つ PR 本文に GitHub のクローズキーワード（`closes #N` 等）が
    含まれていれば、Step 7（スプリントレビュー + レトロ）完了前に Issue が
    自動クローズされてしまう危険があるため Error を返す。

    除外するのは **コードフェンスとインラインコードだけ**（GitHub のクローズキーワード解析と
    同じ境界）。引用行（`>`）は GitHub が除外しないため、こちらも検出する（PR #772 指摘）。

    戻り値: エラー文言（検出時）/ None（問題なし）
    """
    if pr_body is None:
        return None
    if not _SPRINT_GOAL_LINE_RE.search(pr_body):
        return None

    # コードフェンス（``` / ~~~ を CommonMark 準拠で判定）とインラインコードを除外する。
    text_to_check = _mask_fenced_and_inline_code(pr_body)
    matches = _CLOSES_KEYWORDS.finditer(text_to_check)
    found = [m.group() for m in matches]
    if found:
        shown = ", ".join(found[:3]) + ("…" if len(found) > 3 else "")
        return (
            f"🔴 Error: Sprint Goal: を持つ PR 本文に Closes キーワードが含まれています（{shown}）。"
            f"Issue が PR マージ時に自動クローズされ、Step 7（スプリントレビュー + レトロ）の完了判定が狂います。"
            f"PR 本文から削除してください（Issue #281）。"
        )
    return None


# --- 変異テスト記録リマインド（Issue #698・`sprint-development-rules.md` SD-2） ---
#
# SD-2 は「見た目・スタイルに関わる変更をした場合、変異テストで赤くなることを実測し、PR 本文へ
# 1 行記録する」ことを規律として定めるが、機械検査は見送られていた（本文の #349 参照）。
# ここでは「変異テストを実行したか」自体は検査しない（fail-open を招く広い判定になる）。
# 判定範囲を狭く保つため、① スタイル変更の有無 ② PR 本文の記録行の有無 の 2 点だけを機械判定し、
# ①かつ②なしのときだけ Warning（非ブロッキング）を返す。

# `.tsx`/`.jsx` は「class/className 属性の変更行が diff に含まれる」ときだけスタイル変更とみなす
# （ロジックだけの変更で誤検知しないため・#698 仕様）。plain HTML の `class=` と JSX の
# `className=` の両方を拾う。
_CLASS_ATTR_RE = re.compile(r"(?<![\w-])(?:class|className)\s*=")
_STYLE_EXT_TSX = (".tsx", ".jsx")
_STYLE_EXT_CSS = (".css",)

# `変異テスト:` 記録行（行頭 + 値付き）。書式は既存の meta_line_re 判定（Sprint Goal: 等）と統一する。
_MUTATION_TEST_LINE_RE = meta_line_re("変異テスト")


def _diff_hunk_body_lines(diff_text: str) -> list[str]:
    """unified diff から追加/削除行の中身（先頭の +/- を除いた本文）だけを返す。

    `+++ b/path`/`--- a/path`（ファイルヘッダ）は除外する（除外しないと変更後のファイルパス
    文字列に `class=` を含む場合の誤検知経路になる）。

    🔴 ヘッダ判定は **空白付きの書式**（`+++ ` / `--- `）と裸のヘッダに限定する。単なる
    `startswith("+++")` にすると、追加/削除された **本文行の中身が `++`/`--` で始まる** ケース
    （CSS カスタムプロパティ `--brand: ...` の削除行が diff 上で `---brand: ...` になる等）を
    ヘッダと誤認して落とし、スタイル変更を見逃す（fail-open）。
    """
    out: list[str] = []
    for line in diff_text.splitlines():
        if line in ("+++", "---") or line.startswith(("+++ ", "--- ")):
            continue
        if line.startswith("+") or line.startswith("-"):
            out.append(line[1:])
    return out


def diff_has_class_attr_change(diff_text: str) -> bool:
    """diff の追加/削除行に `class=`/`className=` 属性の変更が含まれるか。"""
    return any(_CLASS_ATTR_RE.search(line) for line in _diff_hunk_body_lines(diff_text))


_DIFF_GIT_HEADER_RE = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+)$")


def split_diff_by_file(diff_text: str) -> dict[str, str]:
    """複数ファイル分の unified diff を `diff --git` ヘッダでファイル単位へ分割する。

    キーは `b/` 側（変更後）のパス。ヘッダより前の行は捨てる。
    """
    chunks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in diff_text.splitlines():
        m = _DIFF_GIT_HEADER_RE.match(line)
        if m:
            current = chunks.setdefault(m.group("b"), [])
        if current is not None:
            current.append(line)
    return {path: "\n".join(lines) for path, lines in chunks.items()}


def _make_default_style_diff_fetcher(files: list[str]) -> Callable[[str], str]:
    """対象ファイル群の diff を **1 回の git 呼び出しでまとめて取得** する fetcher を返す。

    ファイル 1 件ごとに `git diff` を起動すると、`.tsx` を大量に変更した PR（Tailwind クラスの
    一括置換等）で subprocess が O(N) 回直列に走り `npm run check` のレイテンシを悪化させる。

    まず base ブランチとの range diff（`origin/{default}...HEAD`）を試し、範囲が解決できない
    （fork していない・shallow clone 等）場合のみ `git diff HEAD`（作業ツリー差分）へ
    フォールバックする。取得できなければ空文字列（＝スタイル変更なしと同じ扱い＝fail-open だが、
    診断不能を Warning のブロッキング材料にしない方針は他の検査と同じ）。

    `--find-renames` を付けるのは、単一パスの pathspec ではリネーム検出が働かず、内容変更の
    無い `git mv` が「全行追加」として現れて誤検知するため（既存の `className=` を含む行が
    追加行として数えられる）。
    """
    if not files:
        return lambda _f: ""
    base = default_branch()
    per_file: dict[str, str] = {}
    r = sh(["git", "diff", "--find-renames", f"origin/{base}...HEAD", "--", *files], timeout=30)
    if r.returncode == 0 and r.stdout.strip():
        per_file = split_diff_by_file(r.stdout)
    else:
        r2 = sh(["git", "diff", "--find-renames", "HEAD", "--", *files], timeout=30)
        if r2.returncode == 0:
            per_file = split_diff_by_file(r2.stdout)
    return lambda f: per_file.get(f, "")


def detect_style_change_files(
    files: list[str],
    diff_fetcher: Callable[[str], str] | None = None,
) -> list[str]:
    """変更ファイル一覧から「見た目・スタイルに関わる変更」と判定したファイルを返す。

    - `.css` は拡張子だけで判定する（内容を問わず常にスタイル変更）
    - `.tsx`/`.jsx` は diff の追加/削除行に class/className 属性の変更があるときだけ対象
    - それ以外の拡張子は対象外

    `diff_fetcher` を渡すと git を呼ばずに判定できる（`--self-test` 用の注入口）。
    """
    tsx_files = [f for f in files if f.endswith(_STYLE_EXT_TSX)]
    fetcher = diff_fetcher or _make_default_style_diff_fetcher(tsx_files)
    out: list[str] = []
    for f in files:
        if f.endswith(_STYLE_EXT_CSS):
            out.append(f)
        elif f.endswith(_STYLE_EXT_TSX):
            diff_text = fetcher(f)
            if diff_text and diff_has_class_attr_change(diff_text):
                out.append(f)
    return out


def mutation_test_record_warning(
    files: list[str],
    pr_body: str | None,
    diff_fetcher: Callable[[str], str] | None = None,
) -> str | None:
    """スタイル変更 + 変異テスト記録なし の Warning（#698・`sprint-development-rules.md` SD-2）。

    - `pr_body is None`（PR 本文を取得できない経路。Bash 経路 / 手動実行）: 判定不能として
      スキップする（fail-open。判定できないものを毎回 Warning にすると Bash 経路の全 PR で
      誤発火し、本当に必要な Warning が埋もれる）
    - スタイル変更ファイルが 1 つも無ければスキップ
    - `変異テスト:` 記録行（コードフェンス外）があればスキップ
    """
    if pr_body is None:
        return None
    style_files = detect_style_change_files(files, diff_fetcher)
    if not style_files:
        return None

    # コードフェンス（``` / ~~~）とインラインコードを除外して判定する（テンプレート例示の
    # `変異テスト: ...` を実記録と誤認しない・sprint_pr_closes_detection と同じ境界）。
    if _MUTATION_TEST_LINE_RE.search(_mask_fenced_and_inline_code(pr_body)):
        return None

    shown = ", ".join(style_files[:5]) + ("…" if len(style_files) > 5 else "")
    return (
        "見た目・スタイルに関わる変更（class/className 属性の変更・CSS）を含みますが、"
        f"PR 本文に `変異テスト:` の記録がありません（対象: {shown}）。"
        "計算後の値（getComputedStyle）で検証する E2E があり、変異テストで赤くなることを実測した場合は"
        "「変異テスト: 何を壊して何が落ちたか」を PR 本文に 1 行記載してください"
        "（sprint-development-rules.md SD-2・#698）。"
    )


def _self_test_style_change_detection() -> list[str]:
    failures: list[str] = []

    diff_with_class = "diff --git a/x.tsx b/x.tsx\n--- a/x.tsx\n+++ b/x.tsx\n-  <div className=\"old\">\n+  <div className=\"new\">\n"
    diff_logic_only = "diff --git a/x.tsx b/x.tsx\n--- a/x.tsx\n+++ b/x.tsx\n-  const x = 1\n+  const x = 2\n"

    def fetcher(text_map: dict[str, str]) -> Callable[[str], str]:
        return lambda f: text_map.get(f, "")

    # ケース1: .css は内容を問わずスタイル変更
    got = detect_style_change_files(["app/globals.css"], fetcher({}))
    if got != ["app/globals.css"]:
        failures.append(f".css ファイルはスタイル変更として検出されるべきだが {got}")

    # ケース2: .tsx で className 変更行あり → 検出
    got = detect_style_change_files(["app/foo.tsx"], fetcher({"app/foo.tsx": diff_with_class}))
    if got != ["app/foo.tsx"]:
        failures.append(f"className 変更を含む .tsx はスタイル変更として検出されるべきだが {got}")

    # ケース3: .tsx でロジックのみの変更 → 検出しない（誤検知しない）
    got = detect_style_change_files(["app/foo.tsx"], fetcher({"app/foo.tsx": diff_logic_only}))
    if got:
        failures.append(f"ロジックのみの .tsx 変更は検出されないべきだが {got}")

    # ケース4: .ts（ロジックファイル）は対象外拡張子
    got = detect_style_change_files(["src/usecases/foo.ts"], fetcher({"src/usecases/foo.ts": diff_with_class}))
    if got:
        failures.append(f".ts はそもそも判定対象外のはずだが {got}")

    # ケース5: 誤判定しやすい入力 — .md 内に「class=」という文字列があるだけ（.md は対象外拡張子）
    got = detect_style_change_files(["docs/note.md"], fetcher({"docs/note.md": diff_with_class}))
    if got:
        failures.append(f".md は判定対象外のはずだが {got}")

    # ケース6（負ケース・境界の外側）: `data-class=` のようなハイフン区切りの別属性は
    # class/className 属性ではない。`\b` 境界だと `-` の直後で成立して誤検出する。
    diff_data_class = (
        "diff --git a/x.tsx b/x.tsx\n--- a/x.tsx\n+++ b/x.tsx\n"
        '-  <div data-class="a">\n+  <div data-class="b">\n'
    )
    got = detect_style_change_files(["app/foo.tsx"], fetcher({"app/foo.tsx": diff_data_class}))
    if got:
        failures.append(f"data-class= は class/className 属性ではないので検出されないべきだが {got}")

    # ケース7（正ケース・ヘッダ判定の境界）: 本文行の中身が `--`/`++` で始まる場合でも
    # ファイルヘッダと誤認して落とさない（落とすとスタイル変更を見逃す＝fail-open）。
    # 実ヘッダは必ず `--- a/...` / `+++ b/...` と **空白が続く** ので、空白の有無で切り分ける。
    # 下の削除行の中身は CSS カスタムプロパティ（`--custom-prop`）で始まり、diff 上では
    # `---custom-prop...` と描画されるため、素朴な startswith("---") ではヘッダ扱いで落ちる。
    diff_body_starts_with_dashes = (
        "diff --git a/x.tsx b/x.tsx\n--- a/x.tsx\n+++ b/x.tsx\n"
        '---custom-prop:1;<span class="old"></span>\n'
        "+  --custom-prop:2;\n"
    )
    got = detect_style_change_files(
        ["app/foo.tsx"], fetcher({"app/foo.tsx": diff_body_starts_with_dashes})
    )
    if got != ["app/foo.tsx"]:
        failures.append(f"`--` で始まる本文行をヘッダと誤認せず検出されるべきだが {got}")

    # ケース8: 複数ファイル分の diff を `diff --git` ヘッダで分割できる（一括取得の前提）
    merged = diff_with_class.replace("x.tsx", "a.tsx") + diff_logic_only.replace("x.tsx", "b.tsx")
    split = split_diff_by_file(merged)
    if sorted(split) != ["a.tsx", "b.tsx"]:
        failures.append(f"複数ファイル diff の分割キーが b/ 側パスになっていない: {sorted(split)}")
    elif diff_has_class_attr_change(split["b.tsx"]):
        failures.append("分割後の b.tsx（ロジックのみ）に class 変更ありと誤判定した")
    elif not diff_has_class_attr_change(split["a.tsx"]):
        failures.append("分割後の a.tsx（className 変更あり）を検出できなかった")

    return failures


def _self_test_mutation_test_record_warning() -> list[str]:
    failures: list[str] = []
    style_files = ["app/foo.tsx"]

    def fetcher_with_style(_f: str) -> str:
        return "--- a/x\n+++ b/x\n-  <div className=\"old\">\n+  <div className=\"new\">\n"

    def fetcher_no_style(_f: str) -> str:
        return "--- a/x\n+++ b/x\n-  const x = 1\n+  const x = 2\n"

    # 完了条件1: スタイル変更 + 記録なし → Warning
    got = mutation_test_record_warning(style_files, "本文だけで記録なし", fetcher_with_style)
    if not got:
        failures.append("スタイル変更 + 記録なしで Warning が出ない")

    # 完了条件2: スタイル変更 + `変異テスト:` 記録あり → Warning なし
    got = mutation_test_record_warning(
        style_files, "変異テスト: globals.css の宣言を削除 → E2E が FAIL することを確認", fetcher_with_style
    )
    if got:
        failures.append(f"記録ありなのに Warning が出た: {got}")

    # 完了条件3: スタイル変更なし（ロジックのみ）→ Warning なし（誤検知ゼロ）
    got = mutation_test_record_warning(style_files, "記録なし本文", fetcher_no_style)
    if got:
        failures.append(f"スタイル変更が無いのに Warning が出た: {got}")

    # pr_body=None（判定不能）→ Warning なし（fail-open。誤ブロックの温床にしない）
    got = mutation_test_record_warning(style_files, None, fetcher_with_style)
    if got:
        failures.append(f"pr_body=None なのに Warning が出た: {got}")

    # 誤判定しやすい入力: コードフェンス内の例示だけ → 記録として数えない（Warning が出る）
    fenced_body = "説明\n```\n変異テスト: 例示テンプレート\n```\n"
    got = mutation_test_record_warning(style_files, fenced_body, fetcher_with_style)
    if not got:
        failures.append("コードフェンス内の例示だけなのに記録ありと誤認された（Warning が出ない）")

    # 誤判定しやすい入力: 「変異テスト」という語が値なしで出てくるだけ（メタ行として不成立）
    empty_value_body = "変異テスト:\n"
    got = mutation_test_record_warning(style_files, empty_value_body, fetcher_with_style)
    if not got:
        failures.append("値なしの `変異テスト:` 行を記録ありと誤認した（Warning が出ない）")

    return failures


def _self_test_sprint_meta_warnings() -> list[str]:
    failures: list[str] = []

    # 完了条件 1: Sprint Goal: 行を含まない PR 本文では sp:N / Team: を要求しない（#695 本体）
    non_sprint = (
        "Session-Id: abc-123\n"
        "本 PR は `Sprint Goal:` を持たない改善 Issue 消化 PR です。\n"
    )
    got = sprint_meta_warnings(non_sprint)
    if got:
        failures.append(f"非スプリント PR で Warning が出た（散文の Sprint Goal: に誤発火）: {got}")

    # 完了条件 2: Sprint Goal: 行があり sp:N / Team: が欠けていれば従来どおり Warning
    sprint_missing = "Session-Id: abc-123\nSprint Goal: 何かする\n"
    got = sprint_meta_warnings(sprint_missing)
    if not any("Team:" in w for w in got) or not any("sp:N" in w for w in got):
        failures.append(f"スプリント PR で sp:N / Team: の欠落 Warning が出ない: {got}")

    # Sprint Goal: 行 + sp:N + Team: が揃っていれば Warning なし
    sprint_ok = "Session-Id: abc-123\nSprint Goal: 何かする\nsp:3\nTeam: fan-out(3)\n"
    got = sprint_meta_warnings(sprint_ok)
    if got:
        failures.append(f"スプリントメタが揃っているのに Warning が出た: {got}")

    # 完了条件 3: Session-Id: の検査は PR の種類にかかわらず動く
    for body, label in ((("Sprint Goal: 何かする\nsp:3\nTeam: fan-out(3)\n"), "スプリント PR"),
                        ("改善 Issue の消化です。\n", "非スプリント PR")):
        got = sprint_meta_warnings(body)
        if not any("Session-Id" in w for w in got):
            failures.append(f"{label} で Session-Id 欠落の Warning が出ない: {got}")

    # 値が空のメタ行は「記載あり」とみなさない
    if not any("Session-Id" in w for w in sprint_meta_warnings("Session-Id:\n")):
        failures.append("値が空の Session-Id: 行を記載ありと誤判定している")

    # pr_body=None（手動実行）は従来どおり一般リマインドを返す
    if len(sprint_meta_warnings(None)) != 1:
        failures.append("pr_body=None で従来の一般リマインドが返らない")

    return failures


def _self_test_sprint_pr_closes_detection() -> list[str]:
    """Sprint Goal を持つ PR 内のクローズキーワード検出テスト（Issue #281 / PR #772 指摘 1〜3）。"""
    failures: list[str] = []

    def body(*extra: str) -> str:
        return "Session-Id: abc\nSprint Goal: 何か\n" + "".join(f"{line}\n" for line in extra)

    def want_hit(text: str, label: str) -> None:
        if sprint_pr_closes_detection(text) is None:
            failures.append(f"検出されるべきなのに見逃した（fail-open）: {label}")

    def want_miss(text: str, label: str) -> None:
        got = sprint_pr_closes_detection(text)
        if got is not None:
            failures.append(f"検出されるべきでないのに誤検出した（fail-closed）: {label} → {got}")

    # ケース 1: Sprint Goal: がなければ検出しない
    want_miss("Session-Id: abc\nこんにちは Closes #123\n", "Sprint Goal: なし PR")

    # ケース 2: Sprint Goal: あり + Closes キーワード → Error を返す
    want_hit(body("実装内容: Closes #123"), "Sprint Goal: あり + Closes #123")

    # ケース 3: GitHub が認識する 9 語すべて（大文字小文字混合・ケース 10 と統合）
    for keyword in (
        "close #111", "Closes #222", "CLOSED #333",
        "Fix #444", "FIXES #555", "fixed #666",
        "Resolve #777", "Resolves #888", "resolved #999",
    ):
        want_hit(body(keyword), f"9 語のうち '{keyword.split()[0]}'")

    # ケース 4: 参照形式の網羅（PR #772 指摘 2・旧実装は `#N` 以外を全て見逃していた）
    want_hit(body("Closes https://github.com/kai-kou/gem-hunter/issues/281"), "URL 形式")
    want_hit(
        body("Fixes https://github.com/kai-kou/gem-hunter/issues/281#issuecomment-123"),
        "URL 形式 + コメントフラグメント（同じ Issue を指すので fail-closed 側に倒す）",
    )
    want_hit(body("Closes kai-kou/gem-hunter#281"), "クロスリポジトリ形式")
    want_hit(body("Closes: #281"), "コロン付き")
    want_hit(body("Resolves: kai-kou/gem-hunter#281"), "コロン付き + クロスリポジトリ形式")
    want_hit(body("Closes GH-281"), "GH-N 形式")
    want_hit(body("fixes gh-281"), "GH-N 形式（小文字）")

    # ケース 5: URL 形式の絞り込み（GitHub が実際にはクローズしない形を誤検出しない）
    want_miss(body("Closes https://gitlab.com/kai-kou/gem-hunter/issues/281"), "別ホスト（gitlab.com）")
    want_miss(body("Closes https://notgithub.com/kai-kou/gem-hunter/issues/281"), "別ホスト（notgithub.com）")
    want_miss(body("Closes https://github.com.evil.example/o/r/issues/281"), "ホスト偽装（github.com.evil.example）")
    want_miss(body("Closes https://github.com/kai-kou/gem-hunter/pull/281"), "PR への URL（/pull/）")
    want_miss(body("参考: https://github.com/kai-kou/gem-hunter/issues/281"), "キーワードのない Issue URL")

    # ケース 6: 引用行は **検出する**（PR #772 指摘 1・GitHub は blockquote を除外しない）
    want_hit(body("> 過去の Closes #123 対応では…"), "引用行内の Closes #123")
    want_hit(body(">> Fixes #7"), "入れ子引用内の Fixes #7")

    # ケース 7: コードフェンス・インラインコードは除外する（PR #772 指摘 3）
    want_miss(body("```", "Closes #123", "```"), "``` フェンス内")
    want_miss(body("~~~", "Closes #123", "~~~"), "~~~ フェンス内")
    want_miss(body("````", "```", "Closes #123", "```", "````"), "4 連バッククォートの入れ子フェンス内")
    want_miss(body("```text", "~~~", "Closes #123", "```"), "``` フェンス内の ~~~ で早期クローズしない")
    want_miss(body("説明: `Closes #123` と書くと閉じます"), "インラインコード内")
    want_miss(body("説明: ``Closes #123`` と書くと閉じます"), "2 連バッククォートのインラインコード内")
    # 未閉フェンスは「不成立」として検査対象へ戻す（旧実装は以降が全て無検査 = fail-open）
    want_hit(body("```", "Closes #123"), "未閉フェンス以降（検査対象へ戻す）")
    # フェンスを跨いで `Closes` と `#123` が繋がるのを防ぐ（プレースホルダの回帰）
    want_miss(body("Closes", "```", "x", "```", "#123"), "フェンスを跨いだ Closes / #123 の橋渡し")

    # ケース 8: Sprint Goal: あり + キーワードなし → None を返す
    want_miss(body("実装内容：〜を追加する"), "キーワードなし")

    # ケース 9: 複数のキーワード検出時、最初の 3 つを表示
    multi = body("Closes #111", "Fix #222", "Resolves #333", "Resolves #444")
    got = sprint_pr_closes_detection(multi)
    if got is None:
        failures.append("複数キーワード有 のに検出されない")
    elif "…" not in got:
        failures.append(f"複数キーワード（4件）時に省略表記が無い: {got}")

    # ケース 10: pr_body=None のときは None を返す
    if sprint_pr_closes_detection(None) is not None:
        failures.append("pr_body=None で None 以外が返された")

    # ケース 11: 形式不正・別語は検出しない（誤検出でスプリント PR をブロックしないこと）
    want_miss(body("Closes#123"), "キーワードと参照の間に空白がない")
    want_miss(body("Closes 123"), "# がない")
    want_miss(body("RESPLVES #888"), "誤字 RESPLVES（9 語のいずれでもない）")
    want_miss(body("closest #1"), "closest（close の前方一致に引っかけない）")
    want_miss(body("unfixed #1"), "unfixed（語境界の内側）")
    want_miss(body("fixing #1"), "fixing（9 語のいずれでもない）")

    return failures


def _self_test_sprint_pr_closes_wiring() -> list[str]:
    """main() への配線を、実プロセスの終了コードで検証する（PR #772 指摘 4）。

    純関数テストだけでは配線の欠落を捕まえられない（対照実験で実測: `errors.append(...)` を
    `warnings.append(...)` に変えても、`sprint_pr_closes_detection(...)` を `None` に
    置き換えても `--self-test` は緑のままだった）。ここでは使い捨ての git リポジトリを作り、
    `--pr-body-stdin` のエントリポイントから exit code まで貫通させる。

    ⚠️ 無限再帰を避けるため子プロセスに渡すのは `--self-test` ではなく `--pr-body-stdin`。
    ⚠️ `main()` の当該ブロックは「変更ファイルが 1 件以上 + 作業ブランチが main/master 以外」で
       しか動かないため、初期コミット後にファイルを変更しブランチ名を付け替えてから実行する。
    """
    failures: list[str] = []
    git = shutil.which("git")
    if git is None:
        # 実行できないことを緑にしない（fail-open 防止）
        return ["git が見つからず main() 配線テストを実行できなかった"]

    script = str(Path(__file__).resolve())
    violation = "Sprint Goal: SP-0 配線テスト\n\n> Closes #1\n"
    clean = "Sprint Goal: SP-0 配線テスト\nsp:1\nTeam: fan-out(2)\nSession-Id: self-test\n"

    def run_git(tmp: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [git, "-C", tmp, "-c", "user.email=self-test@example.com",
             "-c", "user.name=self-test", "-c", "commit.gpgsign=false", *args],
            capture_output=True, text=True, timeout=60,
        )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "note.txt").write_text("hello\n", encoding="utf-8")
            for args in (("init", "-q", "."), ("add", "-A"), ("commit", "-qm", "init"),
                         ("branch", "-m", "feat/self-test")):
                r = run_git(tmp, *args)
                if r.returncode != 0:
                    return [f"配線テスト用リポジトリの作成に失敗（git {' '.join(args)}）: {r.stderr.strip()}"]
            # 変更ファイルを 1 件作る（main() の当該ブロックの発火条件）
            (Path(tmp) / "note.txt").write_text("hello\nworld\n", encoding="utf-8")

            for label, pr_body, want_rc in (("違反あり", violation, 1), ("違反なし", clean, 0)):
                proc = subprocess.run(
                    [sys.executable, script, "--pr-body-stdin"],
                    input=pr_body, capture_output=True, text=True, cwd=tmp, timeout=300,
                )
                if proc.returncode != want_rc:
                    failures.append(
                        f"main() 配線: {label} の本文で exit={proc.returncode}（期待 {want_rc}）"
                        f" / stdout={proc.stdout.strip()[:300]} / stderr={proc.stderr.strip()[:200]}"
                    )
    except (OSError, subprocess.SubprocessError) as e:
        failures.append(f"main() 配線テストの実行に失敗: {type(e).__name__}: {e}")

    return failures


def run_self_test() -> int:
    # グループを追加したらこのリストに 1 行足すだけでよい（件数を別途手で数えない）
    groups = [
        ("glob マッチャー境界", _self_test_glob_match),
        ("テストパス判定", _self_test_is_test_path),
        ("3 層タッチ判定", _self_test_touched_layers),
        ("縦切り(vertical_slice_check)", _self_test_vertical_slice_check),
        ("C-5 レイヤー分割検出", _self_test_layer_split_check),
        ("C-5 重複SPブランチ検出", _self_test_duplicate_sp_branch_warning),
        ("TDD コミット順序", _self_test_tdd_commit_order_warnings),
        ("SP-n/US-n 単語境界（issue2 回帰）", _self_test_sp_us_word_boundary),
        ("commit_files --root（issue3 回帰）", _self_test_commit_files_root_flag),
        ("補助チェッカー出力の振り分け", _self_test_subcheck_outcome),
        ("デバッグ痕跡検出（自己誤検出の回帰）", _self_test_debug_trace),
        ("スプリントメタ Warning の射程（#695）", _self_test_sprint_meta_warnings),
        ("Sprint Goal 時の Closes キーワード検出（#281）", _self_test_sprint_pr_closes_detection),
        ("Closes 検出の main() 配線（exit code 通貫・PR #772）", _self_test_sprint_pr_closes_wiring),
        ("スタイル変更検出（#698）", _self_test_style_change_detection),
        ("変異テスト記録リマインド（#698）", _self_test_mutation_test_record_warning),
    ]
    failed_groups = 0
    total_failures = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed_groups += 1
            total_failures += len(failures)
            for f in failures:
                print(f"FAIL[{name}]: {f}")

    if total_failures:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed_groups} グループ失敗 "
              f"({total_failures} 件の不一致)")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0



# pre-pr-create-check.sh は self_review_check.py プロセス全体を外側 timeout 90 秒で包む。
# ツール単体に近い秒数を許すと合計が外側予算を超え、timeout コマンドが exit=124 で
# プロセスごと強制終了する（本リポジトリのフックは 124 を fail-open で可視化する運用のため、
# ここでの自制が主防衛線になる）。
SELF_TEST_PER_TOOL_TIMEOUT = 15
SELF_TEST_BUDGET_SECONDS = 40


def self_test_errors(files: list[str]) -> list[str]:
    """差分に含まれる --self-test 対応ツールを実行し、失敗を Error として返す（base#508）。

    対象判定はソース内の "--self-test" 文字列の有無で機械的に拾う（ハードコードの
    許可リストを持たないため、新設ツールが自動的に対象へ加わる）。差分に該当ツールが
    無ければ何も実行しない（既存 PR の所要時間を増やさない）。

    本ファイル自身はこの docstring 内にも "--self-test" 文字列を含むため、対象判定に
    そのまま乗せると自分自身をサブプロセスとして再帰起動し無限にハングする。ファイル
    パスで自己除外する。

    対象はさらに、解決後の実パスが tools/ または scripts/ の実体配下にあるものに限定する
    （シンボリックリンク経由でリポジトリ外の任意ファイルを実行させない）。
    """
    errs: list[str] = []
    repo_root = Path(".").resolve()
    self_path = Path(__file__).resolve()
    allowed_dirs = (repo_root / "tools", repo_root / "scripts")

    def _is_allowed(path: Path) -> bool:
        for d in allowed_dirs:
            try:
                if path.is_relative_to(d):
                    return True
            except AttributeError:  # pragma: no cover - Python 3.8 互換フォールバック
                try:
                    path.relative_to(d)
                    return True
                except ValueError:
                    pass
        return False

    targets = [
        f for f in files
        if (f.startswith("tools/") or f.startswith("scripts/")) and f.endswith(".py")
        and Path(f).resolve() != self_path
        and _is_allowed(Path(f).resolve())
    ]

    started = time.monotonic()
    for f in targets:
        elapsed = time.monotonic() - started
        if elapsed > SELF_TEST_BUDGET_SECONDS:
            errs.append(
                f"--self-test 未実行: {f}（PR 前ゲートの実行時間予算 {SELF_TEST_BUDGET_SECONDS}秒を"
                f"超過。ローカルで `python3 {f} --self-test` を確認してから再度 PR 作成してください）"
            )
            continue
        try:
            text = Path(f).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "--self-test" not in text:
            continue
        remaining = max(1, int(SELF_TEST_BUDGET_SECONDS - elapsed))
        per_call_timeout = min(SELF_TEST_PER_TOOL_TIMEOUT, remaining)
        try:
            proc = sh([sys.executable, f, "--self-test"], timeout=per_call_timeout)
        except subprocess.TimeoutExpired:
            errs.append(f"--self-test タイムアウト: {f}（{per_call_timeout}秒超）")
            continue
        except Exception as e:  # noqa: BLE001 - サブプロセス起動失敗等もフェイルオープンさせない
            errs.append(f"--self-test 実行エラー: {f}: {e}")
            continue
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = tail[-1] if tail else "(出力なし)"
            errs.append(f"--self-test 失敗: {f}（exit={proc.returncode}）: {detail[:200]}")
    return errs


def main(pr_body: str | None = None) -> int:
    if not Path(".git").exists() and sh(["git", "rev-parse", "--git-dir"]).returncode != 0:
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    files = changed_files()

    for f in files:
        p = Path(f)
        try:
            size_mb = p.stat().st_size / (1024 * 1024)
            if size_mb > MAX_MB:
                errors.append(f"巨大ファイル: {f}（{size_mb:.1f}MB > {MAX_MB}MB）。Git LFS か別管理を検討してください。")
                continue
            # バイナリは内容スキャンしない
            raw = p.read_bytes()
            if b"\x00" in raw[:4096]:
                continue
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if any(line.startswith(m) or line == m for m in CONFLICT_MARKERS):
                errors.append(f"マージコンフリクト痕跡: {f}:{i}")
            low = line.lower()
            if has_debug_trace(low):
                warnings.append(f"デバッグ痕跡の可能性: {f}:{i}")

        # CJK Markdown 半角スペース（CLAUDE.md「Markdown 出力ルール」）
        # 目視では見落とすため機械化（AI レビュアーの同種指摘を未然に防ぐ）
        if f.endswith((".md", ".markdown")) and not (
            _cjk_is_excluded is not None and _cjk_is_excluded(f)
        ):
            cjk_lines = cjk_violation_lines(text)
            if cjk_lines:
                shown = ", ".join(str(n) for n in cjk_lines[:8])
                ellipsis = "…" if len(cjk_lines) > 8 else ""
                warnings.append(
                    f"CJK 半角スペース違反: {f}（{len(cjk_lines)} 行: {shown}{ellipsis}）"
                    f" → python3 tools/check_cjk_markdown.py --fix {f}"
                )

        # Python 危険パターン（FAIR Layer 0 強化・#56）
        # ERROR=コマンドインジェクション/eval/pickle 等の高危険（ブロック）、WARNING=資格情報ハードコード等。
        # SELF_REVIEW_SECURITY=warn で ERROR を非ブロック化する逃げ道を用意（保守的運用）。
        if f.endswith(".py") and _scan_py is not None:
            block_security = os.environ.get("SELF_REVIEW_SECURITY", "block").lower() != "warn"
            try:
                for lineno, sev, code, msg in _scan_py(text, f):
                    entry = f"危険パターン {code}: {f}:{lineno} {msg}"
                    if sev == "ERROR" and block_security:
                        errors.append(entry)
                    else:
                        warnings.append(entry)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"危険パターン検査でエラー: {f}: {e}")

    # --self-test を持つツールの自動実行（base#508・PR 作成前ゲート）
    # SELF_REVIEW_SELFTEST=warn で Error を非ブロック化する逃げ道を用意
    # （SELF_REVIEW_SECURITY と同じパターン。フレークな self-test 調査中の一時回避用）。
    selftest_findings = self_test_errors(files)
    if os.environ.get("SELF_REVIEW_SELFTEST", "block").lower() == "warn":
        warnings.extend(selftest_findings)
    else:
        errors.extend(selftest_findings)

    # TDD コミット順序 / 縦切り(3層) / C-5 検査（whiteboard sprint-cycle-design-20260818 確定内容）
    tdd_errors, tdd_warnings = tdd_and_sprint_checks(files)
    errors.extend(tdd_errors)
    warnings.extend(tdd_warnings)

    # base-update-notes 追記リマインド（Issue #211・Warning 一本。Error 化は実測後に再検討）
    note_warn = update_notes_reminder(files)
    if note_warn:
        warnings.append(note_warn)

    # base-sync-state マーカー未コミット検出（Issue #206）
    state_warn = base_sync_state_reminder()
    if state_warn:
        warnings.append(state_warn)

    # docs/rules/*.md 削除行の実ケース記載リマインド（Issue base#469・削減の品質バー）
    citation_warn = rule_deletion_citation_reminder(files)
    if citation_warn:
        warnings.append(citation_warn)

    # Hot 層予算チェック（Issue base#469・実測とログの乖離・再棚卸しの合図を機械判定）
    budget_warn = hot_budget_reminder(files)
    if budget_warn:
        warnings.append(budget_warn)

    # サブエージェント定義の `tools` がフィルタで全滅していないか（#367）
    # 全滅すると委譲が「空回答」になり、しかも Claude Code は削除をエラー報告しない。
    if any(f.startswith(".claude/agents/") for f in files):
        run_subcheck(["tools/check_agent_definitions.py"], "サブエージェント定義",
                     errors, warnings, timeout=30)

    # クリーンアーキテクチャの依存規則（#47・#32）
    # 変更ファイルだけを渡す（全体走査だと差分外の既存違反で無関係な PR がブロックされる）。
    arch_files = [f for f in files if f.startswith(("app/", "src/")) and f.endswith(ARCH_CODE_SUFFIXES)]
    if arch_files:
        run_subcheck(["tools/check_architecture_boundaries.py", *arch_files], "依存規則",
                     errors, warnings, timeout=30)

    # 月次コストテレメトリの feature PR 混入チェック（#106・#242 回帰検知）
    # cost_monthly は gitignore 対象で、telemetry/cost-data ブランチへのみ永続化する（#242）。
    # 回帰シグナルは 2 種（#243 レビュー）:
    #   a) ブランチのコミット済み差分に追加/変更(A/M/R/C)として現れた（WIP 除外の破れ）
    #   b) 未追跡かつ非 ignore で現れた（gitignore エントリの破れ。--flush が再生成する）
    # 追跡解除（削除差分）と、旧ブランチ上の未コミット worktree 変更では発火させない。
    tele_prefix = "content/analytics/cost_monthly/"
    if any(f.startswith(tele_prefix) for f in files):
        ns = sh(["git", "diff", "--name-status", f"origin/{default_branch()}...HEAD"]).stdout
        committed = set()
        for line in ns.splitlines():
            parts = line.split("\t")
            if parts and parts[0][:1] in "AMRC" and parts[-1].startswith(tele_prefix):
                committed.add(parts[-1])
        untracked = set(
            sh(["git", "ls-files", "--others", "--exclude-standard", "--", tele_prefix])
            .stdout.splitlines()
        )
        tele = sorted({f for f in files if f in committed or f in untracked})
        if tele:
            warnings.append(
                "月次コストテレメトリが feature 差分に混入しています（#106・#242 回帰）: "
                f"{', '.join(tele)} → gitignore と Stop hook の WIP add 除外を確認し、差分から外してください"
            )

    # ruff 補助セキュリティチェック（FAIR Layer 0 補完・#56・opt-in）
    # 既定 OFF（誤検知ノイズ回避）。SELF_REVIEW_RUFF=1 かつ ruff 在の時のみ S(=bandit) を Warning 表示。
    if os.environ.get("SELF_REVIEW_RUFF") == "1" and shutil.which("ruff"):
        py_files = [f for f in files if f.endswith(".py")]
        if py_files:
            rr = sh(["ruff", "check", "--select", "S", "--output-format", "concise", *py_files])
            for line in (rr.stdout or "").splitlines():
                s = line.strip()
                if s and ".py:" in s and not s.lower().startswith(("found", "warning:", "error:")):
                    warnings.append(f"ruff(S): {s}")

    # スプリントメタのリマインド（session-sprint-rules.md §2/§5・#45・非ブロッキング）
    # PR の Session-Id / sp:N 記載漏れを未然に防ぐ（done_sp・セッション別ベロシティ計測のため）。
    # PR 本文・ラベルはこの時点で未確定のため Error にはせず Warning に留める（PR template と二重防御）。
    if files:
        br = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        cur = br.stdout.strip() if br.returncode == 0 else ""
        if cur not in ("", "main", "master", "HEAD"):
            warnings.extend(sprint_meta_warnings(pr_body))
            # Sprint Goal: を持つ PR 内のクローズキーワード検査（Issue #281）
            closes_error = sprint_pr_closes_detection(pr_body)
            if closes_error:
                errors.append(closes_error)
            # 変異テスト記録リマインド（sprint-development-rules.md SD-2・Issue #698）
            mutation_warn = mutation_test_record_warning(files, pr_body)
            if mutation_warn:
                warnings.append(mutation_warn)

    if warnings:
        print("[self-review] Warning:")
        for w in warnings[:20]:
            print(f"  - {w}")
    if errors:
        print("[self-review] Error（PR 作成をブロックします）:")
        for e in errors[:20]:
            print(f"  - {e}")
        return 1
    print("[self-review] OK（Error なし）")
    return 0


if __name__ == "__main__":
    _parser = argparse.ArgumentParser(add_help=True)
    _parser.add_argument(
        "--self-test", action="store_true",
        help="git・ネットワーク不要のユニットテストを実行する（検査 A/B/C のロジック検証）",
    )
    _parser.add_argument(
        "--pr-body-stdin", action="store_true",
        help="標準入力から PR 本文を読み、Sprint Goal: 行を持つスプリント PR にだけ "
             "sp:N / Team: を要求する（#695。未指定時は従来どおり一般リマインドを出す）",
    )
    _args = _parser.parse_args()
    if _args.self_test:
        sys.exit(run_self_test())
    _pr_body = sys.stdin.read() if _args.pr_body_stdin else None
    try:
        sys.exit(main(_pr_body))
    except Exception as e:
        print(f"[self-review] checker error: {e}", file=sys.stderr)
        sys.exit(2)
