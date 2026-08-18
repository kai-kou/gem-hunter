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
from pathlib import Path

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
except ImportError:
    # ツール自体が無い場合のみ黙って無効化（任意機能）
    _cjk_process_text = None
except Exception as _e:  # noqa: BLE001
    # ツールはあるが壊れている → 黙殺すると再発防止が機能しないので原因を出す
    print(f"[self-review] Warning: check_cjk_markdown の読み込みに失敗（CJK 検査を無効化）: {_e}",
          file=sys.stderr)
    _cjk_process_text = None

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
_LAYER_LABEL_TOKEN = r"layer:(?:frontend|backend|infra(?:structure)?)"
LAYER_LABEL_PATTERN = re.compile(
    rf"^[ \t]*(?:[-*・]\s*)?(?:labels?\s*[:：]\s*)?"
    rf"({_LAYER_LABEL_TOKEN}(?:\s*[,、]\s*{_LAYER_LABEL_TOKEN})*)"
    r"[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# テストパス判定（whiteboard 確定パターン）
TEST_PATH_GLOBS = (
    "**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx",
    "e2e/**", "**/__tests__/**", "**/*_test.py", "tests/**",
)

# 3 層の判定対象（BRIEF.md 3 層定義テーブル・whiteboard round2 §1.2 と完全一致）
FRONTEND_GLOBS = ("app/**/page.tsx", "app/**/layout.tsx", "src/ui/**")
BACKEND_GLOBS = ("app/**/route.ts", "src/usecases/**", "src/domain/**", "src/infrastructure/**")
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
    r = sh(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("/")[-1]
    return "main"


def changed_files() -> list[str]:
    base = f"origin/{default_branch()}"
    r = sh(["git", "diff", "--name-only", f"{base}...HEAD"])
    # split() ではなく splitlines()。スペースを含むパスを 1 件として扱う
    files = r.stdout.splitlines() if r.returncode == 0 else []
    # ステージ済み・作業ツリーの変更も含める
    for extra in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]):
        rr = sh(extra)
        if rr.returncode == 0:
            files += rr.stdout.splitlines()
    # 未追跡（git add 前の新規ファイル）も含める。git diff は untracked を出さないため、
    # これが無いと新規 .md が CJK 検査から漏れて AI レビュー指摘が再発する（#63）
    ru = sh(["git", "ls-files", "--others", "--exclude-standard"])
    if ru.returncode == 0:
        files += ru.stdout.splitlines()
    # 実在する追跡対象ファイルのみ、重複排除
    seen, out = set(), []
    for f in files:
        if f not in seen and Path(f).is_file():
            seen.add(f); out.append(f)
    return out


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
    ]
    for p in true_cases:
        if not is_test_path(p):
            failures.append(f"is_test_path({p!r}) は True を期待したが False")
    false_cases = [
        "src/domain/foo.ts", "app/foo/page.tsx", "src/usecases/handler.ts",
        "tools/self_review_check.py", "src/infrastructure/db.ts",
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


def main() -> int:
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
            if "console.log(" in low or "debugger;" in low or "import pdb" in low:
                warnings.append(f"デバッグ痕跡の可能性: {f}:{i}")

        # CJK Markdown 半角スペース（CLAUDE.md「Markdown 出力ルール」）
        # 目視では見落とすため機械化（AI レビュアーの同種指摘を未然に防ぐ）
        if f.endswith((".md", ".markdown")):
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

    # サブエージェント定義の `tools` がフィルタで全滅していないか（#367）
    # 全滅すると委譲が「空回答」になり、しかも Claude Code は削除をエラー報告しない。
    if any(f.startswith(".claude/agents/") for f in files):
        proc = sh([sys.executable, "tools/check_agent_definitions.py"], timeout=30)
        matched = False
        for line in (proc.stdout or "").splitlines():
            if line.startswith("❌"):
                errors.append(f"サブエージェント定義: {line[2:].strip()}")
                matched = True
            elif line.startswith("⚠️"):
                warnings.append(f"サブエージェント定義: {line[2:].strip()}")
                matched = True
        # 検査自体が壊れて無警告で素通りするのを防ぐ（他の補助ツールと同じ方針）
        if proc.returncode != 0 and not matched:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else "(出力なし)"
            warnings.append(
                f"サブエージェント定義チェックが異常終了しました（exit={proc.returncode}）: {tail[:200]}"
            )

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
            sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
            sid_hint = f"Session-Id: {sid}" if sid else "Session-Id: $CLAUDE_CODE_SESSION_ID を PR 本文へ"
            warnings.append(
                "スプリントメタを PR 本文に記載してください（session-sprint-rules.md §2/§5）: "
                f"{sid_hint} ＋ sp:N ラベル（project-mission.md 工程別標準値 + Dynamic 補正）"
            )

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
    _args = _parser.parse_args()
    if _args.self_test:
        sys.exit(run_self_test())
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[self-review] checker error: {e}", file=sys.stderr)
        sys.exit(2)
