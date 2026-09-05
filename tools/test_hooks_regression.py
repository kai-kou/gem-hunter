#!/usr/bin/env python3
"""hooks の主要分岐を隔離 git リポジトリへの状態注入で機械検証する（Issue #194）。

`bash -n`（構文チェック）はシェルスクリプトの機能退行を検知できない
（実測: #94 のロジックが PR #120 / PR #143 で複数回リグレッションした）。
本スクリプトは `/tmp` 配下に隔離した git リポジトリを作り、状態
（MERGE_HEAD の有無・追跡/未追跡ファイルの組み合わせ・stash の有無・
`[wip]` コミットの有無）を注入してフックを実際に実行し、出力・コミット
状態をアサートする。リポジトリ本体の `.git` には一切触れない。

実行:
    python3 tools/test_hooks_regression.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
STOP_SLACK_NOTIFY = HOOKS_DIR / "stop-slack-notify.sh"
STOP_GIT_CHECK = HOOKS_DIR / "stop-git-check.sh"
PRE_PR_CREATE_CHECK = HOOKS_DIR / "pre-pr-create-check.sh"

_FAILURES: list[str] = []


def _run(
    cmd: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=30
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    result = _run(["git", *args], cwd)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗: {result.stderr}")
    return result


def _run_hook(
    hook_path: Path,
    cwd: Path,
    stdin_payload: dict,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(hook_path)],
        cwd=str(cwd),
        input=json.dumps(stdin_payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _make_isolated_repo(tmp_dir: Path) -> Path:
    """bare リモート + それを clone した作業リポジトリ（main に 1 コミット済み）を作る。"""
    bare = tmp_dir / "origin.git"
    work = tmp_dir / "work"
    _run(["git", "init", "--bare", "-b", "main", str(bare)], tmp_dir)
    _run(["git", "clone", str(bare), str(work)], tmp_dir)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Hook Test")
    (work / "README.md").write_text("initial\n", encoding="utf-8")
    _git(work, "add", "README.md")
    _git(work, "commit", "-m", "initial commit")
    _git(work, "push", "-u", "origin", "main")
    return work


def _setup_feature_branch(tmp_dir: Path) -> Path:
    """隔離リポジトリを作り feature ブランチへ切り替えた状態で返す（全テスト共通の前段）。"""
    work = _make_isolated_repo(Path(tmp_dir))
    _git(work, "checkout", "-b", "feature")
    return work


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        _FAILURES.append(f"{label}: {detail}")


def test_stop_slack_notify_skips_during_merge() -> None:
    """マージ進行中は WIP 自動コミットをスキップし、警告のみ出す。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _setup_feature_branch(tmp)
        (work / "README.md").write_text("changed\n", encoding="utf-8")
        git_dir = work / ".git"
        (git_dir / "MERGE_HEAD").write_text(
            _git(work, "rev-parse", "HEAD").stdout.strip() + "\n", encoding="utf-8"
        )
        before_head = _git(work, "rev-parse", "HEAD").stdout.strip()

        result = _run_hook(
            STOP_SLACK_NOTIFY,
            work,
            {"stop_hook_active": False},
            {"CLAUDE_CODE_REMOTE": "true"},
        )
        after_head = _git(work, "rev-parse", "HEAD").stdout.strip()

        _check(
            "stop-slack-notify: MERGE_HEAD 中は新規コミットを作らない",
            before_head == after_head,
            f"before={before_head} after={after_head}",
        )
        _check(
            "stop-slack-notify: MERGE_HEAD 中は警告メッセージを出す",
            "マージ/リベース/チェリーピック進行中" in result.stderr,
            result.stderr,
        )


def test_stop_slack_notify_skips_during_cherry_pick() -> None:
    """CHERRY_PICK_HEAD 進行中も MERGE_HEAD と同じくコミットをスキップする（実装は 5 状態を同列に見る）。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _setup_feature_branch(tmp)
        (work / "README.md").write_text(
            "changed during cherry-pick\n", encoding="utf-8"
        )
        git_dir = work / ".git"
        (git_dir / "CHERRY_PICK_HEAD").write_text(
            _git(work, "rev-parse", "HEAD").stdout.strip() + "\n", encoding="utf-8"
        )
        before_head = _git(work, "rev-parse", "HEAD").stdout.strip()

        result = _run_hook(
            STOP_SLACK_NOTIFY,
            work,
            {"stop_hook_active": False},
            {"CLAUDE_CODE_REMOTE": "true"},
        )
        after_head = _git(work, "rev-parse", "HEAD").stdout.strip()

        _check(
            "stop-slack-notify: CHERRY_PICK_HEAD 中は新規コミットを作らない",
            before_head == after_head,
            f"before={before_head} after={after_head}",
        )
        _check(
            "stop-slack-notify: CHERRY_PICK_HEAD 中は警告メッセージを出す",
            "マージ/リベース/チェリーピック進行中" in result.stderr,
            result.stderr,
        )


def test_stop_slack_notify_commits_tracked_only() -> None:
    """追跡済み変更のみコミットし、未追跡ファイルは巻き込まない（Issue #94 / PR #120）。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _setup_feature_branch(tmp)
        (work / "README.md").write_text("tracked change\n", encoding="utf-8")
        (work / "scratch.tmp").write_text("untracked\n", encoding="utf-8")
        before_head = _git(work, "rev-parse", "HEAD").stdout.strip()

        _run_hook(
            STOP_SLACK_NOTIFY,
            work,
            {"stop_hook_active": False},
            {"CLAUDE_CODE_REMOTE": "true"},
        )

        after_head = _git(work, "rev-parse", "HEAD").stdout.strip()
        log = _git(work, "log", "-1", "--pretty=%s").stdout.strip()
        status = _git(work, "status", "--porcelain").stdout

        _check(
            "stop-slack-notify: 追跡済み変更があれば [wip] コミットを作る",
            before_head != after_head and log.startswith("[wip]"),
            f"before={before_head} after={after_head} log={log}",
        )
        _check(
            "stop-slack-notify: 未追跡ファイルは git status に未追跡のまま残る（コミットに巻き込まない）",
            "?? scratch.tmp" in status,
            status,
        )


# ──────────────────────────────────────────────
# Cloudflare コスト閾値チェックブロック（Issue #247・PR #937 Layer 1 指摘）
#
# 隔離リポジトリを cwd にすると、フック内の REPO_ROOT は隔離リポジトリを指す。
# したがって `tools/check_cloudflare_cost.py` を装ったスタブをそこへ置けば、
# 実 API へ触れずに終了コード別の分岐・通知経路の配線をそのまま実行できる。
# スタブは受け取った argv を記録し、期待どおりのサブコマンドで呼ばれたかを検証する
# （終了コードだけを差し替える fake は「呼び出し自体が消えた」変異を見逃すため・#710）。
# ──────────────────────────────────────────────

_COST_STUB = '''#!/usr/bin/env python3
import json, os, sys

log = os.environ.get("CF_STUB_CALL_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\\n")

# 期待どおりのオプションで呼ばれていなければ「想定外の終了コード」へ倒す
# （`--gate-daily` のタイポ変異を検知するための門）。
if sys.argv[1:] != ["--gate-daily"]:
    sys.stderr.write("stub: unexpected argv %r\\n" % (sys.argv[1:],))
    sys.exit(99)

out = os.environ.get("CF_STUB_STDOUT", "")
if out:
    sys.stdout.write(out + "\\n")
sys.exit(int(os.environ.get("CF_STUB_EXIT", "0")))
'''

_SLACK_STUB = '''#!/usr/bin/env python3
import json, os, sys

log = os.environ.get("SLACK_STUB_ARGV_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\\n")
sys.exit(0)
'''

_ALERT_LINE = (
    "⚠️ Cloudflare の課金額が要対応水準です（2026-09）: 月内累計 $42.00 が撤退ライン $10.00 を超過。"
    "Cloudflare ダッシュボードの課金設定で請求上限とプランを確認してください"
    "（A-6: 課金設定はアカウント権限が物理的に必要）。未対応だと請求額が増え続けます。"
)


def _run_cost_block(
    tmp: str,
    *,
    exit_code: int,
    stdout: str = "",
    stop_hook_active: bool = False,
    dirty_tracked: bool = False,
) -> tuple[subprocess.CompletedProcess, list, list]:
    """コスト検査スタブを仕込んだ隔離リポジトリでフックを実行し、(結果, 検査 argv, 通知 argv) を返す。

    作業ディレクトリは `Path(tmp) / "work"`（`_make_isolated_repo` の規約）なので、
    呼び出し側は必要ならそこを直接検査できる。
    """
    work = _setup_feature_branch(tmp)
    tools_dir = work / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "check_cloudflare_cost.py").write_text(_COST_STUB, encoding="utf-8")
    (tools_dir / "slack_notify.py").write_text(_SLACK_STUB, encoding="utf-8")
    if dirty_tracked:
        (work / "README.md").write_text("tracked change\n", encoding="utf-8")

    # ログはリポジトリ外に置く（隔離リポジトリの git status を汚さない）
    cost_log = Path(tmp) / "cost_calls.log"
    slack_log = Path(tmp) / "slack_calls.log"

    result = _run_hook(
        STOP_SLACK_NOTIFY,
        work,
        {"stop_hook_active": stop_hook_active, "session_id": "cost-test"},
        {
            "CLAUDE_CODE_REMOTE": "true",
            "CF_STUB_EXIT": str(exit_code),
            "CF_STUB_STDOUT": stdout,
            "CF_STUB_CALL_LOG": str(cost_log),
            "SLACK_STUB_ARGV_LOG": str(slack_log),
        },
    )

    def _read(path: Path) -> list:
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    return result, _read(cost_log), _read(slack_log)


def test_cost_check_exit0_is_silent() -> None:
    """exit 0（閾値内）: 検査は呼ばれるが警告も通知も出さない。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, cost_calls, slack_calls = _run_cost_block(
            tmp, exit_code=0, stdout="閾値内: 2026-09 の月内累計 $1.00"
        )
        _check(
            "cost-check: exit 0 でも検査ツールは --gate-daily で呼ばれる",
            cost_calls == [["--gate-daily"]],
            f"cost_calls={cost_calls}",
        )
        _check(
            "cost-check: exit 0 では Slack 通知を呼ばない",
            slack_calls == [],
            f"slack_calls={slack_calls}",
        )
        _check(
            "cost-check: exit 0 では Cloudflare 警告を stderr に出さない",
            "Cloudflare" not in result.stderr,
            result.stderr,
        )
        _check(
            "cost-check: exit 0 でもフック自身は exit 0",
            result.returncode == 0,
            f"exit={result.returncode}",
        )


def test_cost_check_exit1_notifies_with_tool_stdout() -> None:
    """exit 1（超過）: 検査ツールの stdout が「加工されずに」通知経路へ渡る（#247 完了条件 4）。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, cost_calls, slack_calls = _run_cost_block(
            tmp, exit_code=1, stdout=_ALERT_LINE
        )
        _check(
            "cost-check: exit 1 で検査ツールが --gate-daily で呼ばれる",
            cost_calls == [["--gate-daily"]],
            f"cost_calls={cost_calls}",
        )
        _check(
            "cost-check: exit 1 で Slack 通知（waiting）が 1 回呼ばれる",
            len(slack_calls) == 1 and slack_calls and slack_calls[0][0] == "waiting",
            f"slack_calls={slack_calls}",
        )
        argv = slack_calls[0] if slack_calls else []
        _check(
            "cost-check: exit 1 の通知に --issues でツールの stdout がそのまま渡る（A-6 判定の前提）",
            "--issues" in argv and _ALERT_LINE in argv,
            f"argv={argv}",
        )
        # `--branch` が無いと slack_notify.py 側の本文組み立てが崩れる（引数配線の固定）
        _check(
            "cost-check: exit 1 の通知に --branch が渡る",
            "--branch" in argv,
            f"argv={argv}",
        )
        _check(
            "cost-check: exit 1 では判定 1 行を stderr にも残す",
            "月内累計 $42.00" in result.stderr,
            result.stderr,
        )
        _check(
            "cost-check: exit 1 でもフック自身は exit 0（Stop をブロックしない）",
            result.returncode == 0,
            f"exit={result.returncode}",
        )


def test_cost_check_exit2_is_undecidable_without_notify() -> None:
    """exit 2（判定不能・fail-closed）: 超過通知には倒さず、判定不能の警告だけを出す。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, cost_calls, slack_calls = _run_cost_block(tmp, exit_code=2)
        _check(
            "cost-check: exit 2 で検査ツールが呼ばれる",
            cost_calls == [["--gate-daily"]],
            f"cost_calls={cost_calls}",
        )
        _check(
            "cost-check: exit 2 では Slack 通知を呼ばない（判定不能を超過に丸めない）",
            slack_calls == [],
            f"slack_calls={slack_calls}",
        )
        _check(
            "cost-check: exit 2 は「判定できませんでした」と報告する",
            "判定できませんでした" in result.stderr,
            result.stderr,
        )
        _check(
            "cost-check: exit 2 でもフック自身は exit 0",
            result.returncode == 0,
            f"exit={result.returncode}",
        )


def test_cost_check_exit124_reports_timeout() -> None:
    """exit 124（timeout）: 判定不能扱いの専用メッセージを出し、通知はしない。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, _cost_calls, slack_calls = _run_cost_block(tmp, exit_code=124)
        _check(
            "cost-check: exit 124 はタイムアウトとして報告する",
            "タイムアウト" in result.stderr,
            result.stderr,
        )
        _check(
            "cost-check: exit 124 では Slack 通知を呼ばない",
            slack_calls == [],
            f"slack_calls={slack_calls}",
        )
        _check(
            "cost-check: exit 124 でもフック自身は exit 0",
            result.returncode == 0,
            f"exit={result.returncode}",
        )


def test_cost_check_unexpected_exit_code_reported() -> None:
    """想定外の終了コードは専用メッセージへ倒す（超過にも判定不能にも丸めない）。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, _cost_calls, slack_calls = _run_cost_block(tmp, exit_code=3)
        _check(
            "cost-check: 想定外の終了コードを終了コード付きで報告する",
            "想定外の終了コード 3" in result.stderr,
            result.stderr,
        )
        _check(
            "cost-check: 想定外の終了コードでは Slack 通知を呼ばない",
            slack_calls == [],
            f"slack_calls={slack_calls}",
        )


def test_cost_check_skipped_when_stop_hook_active() -> None:
    """再帰防止: stop_hook_active=true では検査ブロック自体が起動しない。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, cost_calls, slack_calls = _run_cost_block(
            tmp, exit_code=1, stdout=_ALERT_LINE, stop_hook_active=True
        )
        _check(
            "cost-check: stop_hook_active=true では検査ツールを呼ばない",
            cost_calls == [],
            f"cost_calls={cost_calls}",
        )
        _check(
            "cost-check: stop_hook_active=true では Slack 通知も呼ばない",
            slack_calls == [],
            f"slack_calls={slack_calls}",
        )
        _check(
            "cost-check: stop_hook_active=true でもフック自身は exit 0",
            result.returncode == 0,
            f"exit={result.returncode}",
        )


def test_cost_check_does_not_abort_wip_autocommit() -> None:
    """干渉検証（#725）: コスト検査の stdout 捕捉が後段の WIP 自動保全を止めないこと。

    `set -euo pipefail` 下でコマンド置換の非ゼロ終了を `|| _cf_cost_rc=$?` で受けそこねると、
    フックがその場で落ちて **下の WIP 自動コミットが一切走らなくなる**（L-100 の後退）。
    「フック自身が exit 0」だけでは、途中で落ちても最後の `exit 0` に見えるケースと
    区別できないため、後段の副作用（[wip] コミットの発生）まで検証する。
    """
    for exit_code in (1, 2, 124):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            result, _cost_calls, _slack_calls = _run_cost_block(
                tmp, exit_code=exit_code, stdout=_ALERT_LINE, dirty_tracked=True
            )
            log = _git(work, "log", "-1", "--pretty=%s").stdout.strip()
            _check(
                f"cost-check: 検査が exit {exit_code} でも後段の WIP 自動コミットは実行される",
                log.startswith("[wip]") and result.returncode == 0,
                f"exit={result.returncode} log={log} stderr={result.stderr}",
            )


def test_stop_git_check_warns_on_stash() -> None:
    """stash 残存は非ブロッキング警告（exit 0 のまま）。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _setup_feature_branch(tmp)
        (work / "README.md").write_text("will be stashed\n", encoding="utf-8")
        _git(work, "stash")
        # working tree はクリーン・feature は main と同一コミットなので unpushed=0

        result = _run_hook(STOP_GIT_CHECK, work, {"stop_hook_active": False})

        _check(
            "stop-git-check: stash 残存時も exit 0（非ブロッキング）",
            result.returncode == 0,
            f"exit={result.returncode} stderr={result.stderr}",
        )
        _check(
            "stop-git-check: stash 残存を stderr に警告する",
            "警告" in result.stderr and "stash" in result.stderr.lower(),
            result.stderr,
        )


def _pr_body_with_evidence(work: Path) -> str:
    """他のゲート（Sprint Goal / 層 2 証跡の表・鮮度）を通過する最小の PR 本文を作る。

    4.8 節（自動保全コミットの件名ガード）だけを単独で検証したいので、それ以外の
    ブロック要因を先に潰しておく。`実行時点コミット:` は現在の HEAD と一致させる（#751）。
    """
    head_sha = _git(work, "rev-parse", "HEAD").stdout.strip()
    return (
        "Sprint Goal: test\n\n"
        "## run_checks 結果\n\n"
        f"実行時点コミット: `{head_sha}`\n\n"
        "| check | result |\n|---|---|\n| dummy | PASS |\n"
    )


def test_pre_pr_create_check_blocks_on_wip_commit() -> None:
    """単一の [wip] 自動保全コミットのままの PR 作成はブロックする（base#483）。

    squash マージのタイトルは単一コミットの件名をそのまま継承するため、意味を成さない
    件名が main の永続履歴に残る。正本は `pr-review-flow-summary.md` 項目 0.7。
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = _setup_feature_branch(tmp)
        (work / "README.md").write_text("wip change\n", encoding="utf-8")
        _git(work, "add", "README.md")
        _git(work, "commit", "-m", "[wip] セッション終了前自動コミット（テスト）")
        # ブランチを push 済みにしておく（未 push チェックで先にブロックされないように）
        _git(work, "push", "-u", "origin", "feature")

        result = _run_hook(
            PRE_PR_CREATE_CHECK,
            work,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {"body": _pr_body_with_evidence(work)},
            },
        )

        _check(
            "pre-pr-create-check: 単一 [wip] コミットは PR 作成をブロックする（exit 2）",
            result.returncode == 2,
            f"exit={result.returncode} stdout={result.stdout} stderr={result.stderr}",
        )
        combined = result.stdout + result.stderr
        _check(
            "pre-pr-create-check: ブロック理由に件名と base#483 を示す",
            "PR 作成をブロックしました" in combined and "base#483" in combined,
            combined,
        )


def test_pre_pr_create_check_allows_wip_commit_when_branch_has_multiple_commits() -> None:
    """[wip] が HEAD でもブランチが複数コミットならブロックしない（境界の外側・#750）。

    squash マージは複数コミットの PR では PR タイトルを使い HEAD の件名を継承しないため、
    4.8 節のブロック条件は「件名が自動保全定型 **かつ** ブランチ上のコミット数 <= 1」の AND。
    この負ケースが無いと、AND を落として件名だけで判定する変異を検知できない。
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = _setup_feature_branch(tmp)
        (work / "README.md").write_text("meaningful change\n", encoding="utf-8")
        _git(work, "add", "README.md")
        _git(work, "commit", "-m", "fix: 意味のある 1 つ目のコミット")
        (work / "NOTES.md").write_text("wip change\n", encoding="utf-8")
        _git(work, "add", "NOTES.md")
        _git(work, "commit", "-m", "[wip] セッション終了前自動コミット（テスト）")
        _git(work, "push", "-u", "origin", "feature")

        result = _run_hook(
            PRE_PR_CREATE_CHECK,
            work,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {"body": _pr_body_with_evidence(work)},
            },
        )

        combined = result.stdout + result.stderr
        _check(
            "pre-pr-create-check: 複数コミットなら [wip] が HEAD でもブロックしない",
            result.returncode != 2,
            f"exit={result.returncode} stdout={result.stdout} stderr={result.stderr}",
        )
        _check(
            "pre-pr-create-check: 複数コミットでも [wip] 残存の非ブロッキング警告は出す",
            "[wip]" in combined and "警告" in combined,
            combined,
        )


def test_pre_pr_create_check_allows_meaningful_subject_mentioning_auto_commit() -> None:
    """自動保全の定型文言を **含む** が先頭一致しない件名はブロックしない（境界の外側・#750）。

    4.8 節の正規表現は `^(...)` で各代替に先頭アンカーを効かせている。括弧を落とすと
    `^` が最初の代替にしか係らず、`fix: revert accidental auto-commit before compaction hack`
    のような正当な件名まで部分一致で誤ブロックする。この負ケースがその変異を検知する。
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = _setup_feature_branch(tmp)
        (work / "README.md").write_text("meaningful change\n", encoding="utf-8")
        _git(work, "add", "README.md")
        _git(work, "commit", "-m", "fix: revert accidental auto-commit before compaction hack")
        _git(work, "push", "-u", "origin", "feature")

        result = _run_hook(
            PRE_PR_CREATE_CHECK,
            work,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {"body": _pr_body_with_evidence(work)},
            },
        )

        _check(
            "pre-pr-create-check: 定型文言を含むだけの正当な件名はブロックしない",
            result.returncode != 2,
            f"exit={result.returncode} stdout={result.stdout} stderr={result.stderr}",
        )


def main() -> int:
    # フックが 1 本欠けても他 2 本の検証は続行する（欠けた本数分だけ SKIP を記録）。
    if not STOP_SLACK_NOTIFY.is_file():
        print(f"SKIP: {STOP_SLACK_NOTIFY} が見つかりません")
    else:
        test_stop_slack_notify_skips_during_merge()
        test_stop_slack_notify_skips_during_cherry_pick()
        test_stop_slack_notify_commits_tracked_only()
        test_cost_check_exit0_is_silent()
        test_cost_check_exit1_notifies_with_tool_stdout()
        test_cost_check_exit2_is_undecidable_without_notify()
        test_cost_check_exit124_reports_timeout()
        test_cost_check_unexpected_exit_code_reported()
        test_cost_check_skipped_when_stop_hook_active()
        test_cost_check_does_not_abort_wip_autocommit()

    if not STOP_GIT_CHECK.is_file():
        print(f"SKIP: {STOP_GIT_CHECK} が見つかりません")
    else:
        test_stop_git_check_warns_on_stash()

    if not PRE_PR_CREATE_CHECK.is_file():
        print(f"SKIP: {PRE_PR_CREATE_CHECK} が見つかりません")
    else:
        test_pre_pr_create_check_blocks_on_wip_commit()
        test_pre_pr_create_check_allows_wip_commit_when_branch_has_multiple_commits()
        test_pre_pr_create_check_allows_meaningful_subject_mentioning_auto_commit()

    if _FAILURES:
        print(f"\n{len(_FAILURES)} 件失敗:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("\n全テスト PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
