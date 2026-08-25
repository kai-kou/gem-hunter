#!/usr/bin/env python3
"""clear_stale_e2e_ports.py — E2E 実行前に居残りサーバーとポート占有をクリアする

背景（実測・SP-10 レトロ・Issue #204）: 別エージェントが停止し損ねた `next-server` が
E2E 対象ポート（3100・8788）を掴んだまま残り、Playwright がそれに接続して旧コードを検査した
結果、10 件以上のテストが誤って失敗した。プロセスを停止してクリーンビルドしたら全 PASS になった。

`playwright.config.ts` の webServer は `reuseExistingServer: !process.env.CI` で既存サーバーを
再利用する設定のため、居残りサーバーが「新しい実装のはず」の検証を「古いコード」に対して行って
しまう。本ツールは E2E 実行直前に対象ポートを占有しているプロセスを検出し、**自セッションの
リポジトリ配下から起動されたプロセスに限って**停止する。

巻き込み事故の防止（他セッションのサーバーを誤って停止しない）: プロセスの cwd
（`/proc/<pid>/cwd` のシンボリックリンク先）が本リポジトリのルートと一致し、かつコマンドラインが
既知の起動パターン（`next start` / `npm start` / `node .../server.mjs` 等）に一致する場合のみ
停止対象とする。他リポジトリ・他ワークツリーのプロセスは cwd が一致しないため対象外になる。

使い方:
  python3 tools/clear_stale_e2e_ports.py                # 対象ポート既定値（3100,8788）を検査・停止
  python3 tools/clear_stale_e2e_ports.py --ports 3100    # ポートを指定
  python3 tools/clear_stale_e2e_ports.py --dry-run       # 停止せず候補一覧のみ表示
  python3 tools/clear_stale_e2e_ports.py --self-test     # ネットワーク・プロセス非依存のユニットテスト
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time

DEFAULT_PORTS = [3100, 8788]

# 本プロジェクトの E2E webServer が実際に起動するコマンドのみを対象にする（誤検知で無関係な
# プロセスを殺さないため、意図的に狭く絞る）。
KNOWN_COMMAND_PATTERNS = [
    re.compile(r"next\s+start"),
    re.compile(r"npm\s+start"),
    re.compile(r"node\s+.*server\.mjs"),
]


def is_known_e2e_command(cmdline: str) -> bool:
    return any(p.search(cmdline) for p in KNOWN_COMMAND_PATTERNS)


def is_same_repo_cwd(proc_cwd: str, repo_root: str) -> bool:
    try:
        return os.path.realpath(proc_cwd) == os.path.realpath(repo_root)
    except OSError:
        return False


def find_pids_on_port(port: int) -> list[int]:
    try:
        out = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    pids = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def read_proc_cwd(pid: int) -> str | None:
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None


def read_proc_cmdline(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def collect_stale_candidates(ports: list[int], repo_root: str) -> list[tuple[int, int, str]]:
    """(port, pid, cmdline) のうち自リポジトリ配下・既知コマンドに一致するものだけを返す。"""
    candidates = []
    for port in ports:
        for pid in find_pids_on_port(port):
            cwd = read_proc_cwd(pid)
            cmdline = read_proc_cmdline(pid)
            if cwd is None or cmdline is None:
                continue
            if not is_same_repo_cwd(cwd, repo_root):
                continue
            if not is_known_e2e_command(cmdline):
                continue
            candidates.append((port, pid, cmdline))
    return candidates


def kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        time.sleep(0.1)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def self_test() -> int:
    checks = 0

    assert is_known_e2e_command("node /repo/e2e/stub/server.mjs")
    checks += 1
    assert is_known_e2e_command("sh -c next start -- --port 3100")
    checks += 1
    assert is_known_e2e_command("npm start -- --port 3100")
    checks += 1
    assert not is_known_e2e_command("python3 -m http.server 3100")
    checks += 1
    assert not is_known_e2e_command("vim server.mjs")
    checks += 1

    assert is_same_repo_cwd("/repo", "/repo")
    checks += 1
    assert is_same_repo_cwd("/repo/", "/repo")
    checks += 1
    assert not is_same_repo_cwd("/other-repo", "/repo")
    checks += 1
    assert not is_same_repo_cwd("/repo-worktree-2", "/repo")
    checks += 1

    print(f"[clear-stale-e2e-ports] self-test OK（{checks} 項目）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--ports",
        default=",".join(str(p) for p in DEFAULT_PORTS),
        help="検査するポート番号（カンマ区切り・既定: 3100,8788）",
    )
    parser.add_argument("--repo-root", default=os.getcwd(), help="自リポジトリのルートパス（既定: カレントディレクトリ）")
    parser.add_argument("--dry-run", action="store_true", help="停止せず候補一覧のみ表示する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク・プロセス非依存のユニットテストを実行する")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if sys.platform != "linux":
        print("[clear-stale-e2e-ports] SKIP: /proc ベースの判定は Linux 専用のため何もしません")
        return 0

    ports = [int(p) for p in args.ports.split(",") if p.strip()]
    candidates = collect_stale_candidates(ports, args.repo_root)

    if not candidates:
        print("[clear-stale-e2e-ports] 居残りサーバーは検出されませんでした")
        return 0

    for port, pid, cmdline in candidates:
        print(f"[clear-stale-e2e-ports] 検出: port={port} pid={pid} cmd={cmdline}")

    if args.dry_run:
        print(f"[clear-stale-e2e-ports] --dry-run のため停止しません（{len(candidates)} 件）")
        return 0

    for port, pid, cmdline in candidates:
        print(f"[clear-stale-e2e-ports] 停止します: port={port} pid={pid}")
        kill_pid(pid)

    print(f"[clear-stale-e2e-ports] {len(candidates)} 件の居残りサーバーを停止しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
