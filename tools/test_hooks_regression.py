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
HOOKS_DIR = REPO_ROOT / '.claude' / 'hooks'
STOP_SLACK_NOTIFY = HOOKS_DIR / 'stop-slack-notify.sh'
STOP_GIT_CHECK = HOOKS_DIR / 'stop-git-check.sh'
PRE_PR_CREATE_CHECK = HOOKS_DIR / 'pre-pr-create-check.sh'

_FAILURES: list[str] = []


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=30
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    result = _run(['git', *args], cwd)
    if result.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} 失敗: {result.stderr}')
    return result


def _run_hook(
    hook_path: Path, cwd: Path, stdin_payload: dict, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run(
        ['bash', str(hook_path)],
        cwd=str(cwd),
        input=json.dumps(stdin_payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _make_isolated_repo(tmp_dir: Path) -> Path:
    """bare リモート + それを clone した作業リポジトリ（main に 1 コミット済み）を作る。"""
    bare = tmp_dir / 'origin.git'
    work = tmp_dir / 'work'
    _run(['git', 'init', '--bare', '-b', 'main', str(bare)], tmp_dir)
    _run(['git', 'clone', str(bare), str(work)], tmp_dir)
    _git(work, 'config', 'user.email', 'test@example.com')
    _git(work, 'config', 'user.name', 'Hook Test')
    (work / 'README.md').write_text('initial\n', encoding='utf-8')
    _git(work, 'add', 'README.md')
    _git(work, 'commit', '-m', 'initial commit')
    _git(work, 'push', '-u', 'origin', 'main')
    return work


def _check(label: str, condition: bool, detail: str = '') -> None:
    status = 'PASS' if condition else 'FAIL'
    print(f'[{status}] {label}')
    if not condition:
        _FAILURES.append(f'{label}: {detail}')


def test_stop_slack_notify_skips_during_merge() -> None:
    """マージ進行中は WIP 自動コミットをスキップし、警告のみ出す。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _make_isolated_repo(Path(tmp))
        _git(work, 'checkout', '-b', 'feature')
        (work / 'README.md').write_text('changed\n', encoding='utf-8')
        git_dir = work / '.git'
        (git_dir / 'MERGE_HEAD').write_text(
            _git(work, 'rev-parse', 'HEAD').stdout.strip() + '\n', encoding='utf-8'
        )
        before_head = _git(work, 'rev-parse', 'HEAD').stdout.strip()

        result = _run_hook(
            STOP_SLACK_NOTIFY, work, {'stop_hook_active': False}, {'CLAUDE_CODE_REMOTE': 'true'}
        )
        after_head = _git(work, 'rev-parse', 'HEAD').stdout.strip()

        _check(
            'stop-slack-notify: MERGE_HEAD 中は新規コミットを作らない',
            before_head == after_head,
            f'before={before_head} after={after_head}',
        )
        _check(
            'stop-slack-notify: MERGE_HEAD 中は警告メッセージを出す',
            'マージ/リベース/チェリーピック進行中' in result.stderr,
            result.stderr,
        )


def test_stop_slack_notify_commits_tracked_only() -> None:
    """追跡済み変更のみコミットし、未追跡ファイルは巻き込まない（Issue #94 / PR #120）。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _make_isolated_repo(Path(tmp))
        _git(work, 'checkout', '-b', 'feature')
        (work / 'README.md').write_text('tracked change\n', encoding='utf-8')
        (work / 'scratch.tmp').write_text('untracked\n', encoding='utf-8')
        before_head = _git(work, 'rev-parse', 'HEAD').stdout.strip()

        _run_hook(STOP_SLACK_NOTIFY, work, {'stop_hook_active': False}, {'CLAUDE_CODE_REMOTE': 'true'})

        after_head = _git(work, 'rev-parse', 'HEAD').stdout.strip()
        log = _git(work, 'log', '-1', '--pretty=%s').stdout.strip()
        status = _git(work, 'status', '--porcelain').stdout

        _check(
            'stop-slack-notify: 追跡済み変更があれば [wip] コミットを作る',
            before_head != after_head and log.startswith('[wip]'),
            f'before={before_head} after={after_head} log={log}',
        )
        _check(
            'stop-slack-notify: 未追跡ファイルは git status に残る（コミットに巻き込まない）',
            'scratch.tmp' in status,
            status,
        )


def test_stop_git_check_warns_on_stash() -> None:
    """stash 残存は非ブロッキング警告（exit 0 のまま）。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _make_isolated_repo(Path(tmp))
        _git(work, 'checkout', '-b', 'feature')
        (work / 'README.md').write_text('will be stashed\n', encoding='utf-8')
        _git(work, 'stash')
        # working tree はクリーン・feature は main と同一コミットなので unpushed=0

        result = _run_hook(STOP_GIT_CHECK, work, {'stop_hook_active': False})

        _check(
            'stop-git-check: stash 残存時も exit 0（非ブロッキング）',
            result.returncode == 0,
            f'exit={result.returncode} stderr={result.stderr}',
        )
        _check(
            'stop-git-check: stash 残存を stderr に警告する',
            '警告' in result.stderr and 'stash' in result.stderr.lower(),
            result.stderr,
        )


def test_pre_pr_create_check_warns_on_wip_commit() -> None:
    """[wip] コミット残存は警告のみで PR 作成をブロックしない（Issue #94）。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = _make_isolated_repo(Path(tmp))
        _git(work, 'checkout', '-b', 'feature')
        (work / 'README.md').write_text('wip change\n', encoding='utf-8')
        _git(work, 'add', 'README.md')
        _git(work, 'commit', '-m', '[wip] セッション終了前自動コミット（テスト）')
        # ブランチを push 済みにしておく（未 push チェックで先にブロックされないように）
        _git(work, 'push', '-u', 'origin', 'feature')

        dummy_body = (
            'Sprint Goal: test\n\n## run_checks 結果\n\n| check | result |\n|---|---|\n| dummy | PASS |\n'
        )
        result = _run_hook(
            PRE_PR_CREATE_CHECK,
            work,
            {
                'tool_name': 'mcp__github__create_pull_request',
                'tool_input': {'body': dummy_body},
            },
        )

        _check(
            'pre-pr-create-check: [wip] コミット残存でも exit 0（ブロックしない）',
            result.returncode == 0,
            f'exit={result.returncode} stdout={result.stdout} stderr={result.stderr}',
        )
        combined = result.stdout + result.stderr
        _check(
            'pre-pr-create-check: [wip] コミット警告を出力する',
            '[wip]' in combined and '警告' in combined,
            combined,
        )


def main() -> int:
    for hook in (STOP_SLACK_NOTIFY, STOP_GIT_CHECK, PRE_PR_CREATE_CHECK):
        if not hook.is_file():
            print(f'SKIP: {hook} が見つかりません')
            return 0

    test_stop_slack_notify_skips_during_merge()
    test_stop_slack_notify_commits_tracked_only()
    test_stop_git_check_warns_on_stash()
    test_pre_pr_create_check_warns_on_wip_commit()

    if _FAILURES:
        print(f'\n{len(_FAILURES)} 件失敗:')
        for f in _FAILURES:
            print(f'  - {f}')
        return 1
    print('\n全テスト PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
