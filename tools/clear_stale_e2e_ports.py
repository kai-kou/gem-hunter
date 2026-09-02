#!/usr/bin/env python3
"""clear_stale_e2e_ports.py — E2E 実行前に居残りサーバーとポート占有をクリアする

背景（実測・SP-10 レトロ・Issue #204）: 別エージェントが停止し損ねた `next-server` が
E2E 対象ポート（3100・8788）を掴んだまま残り、Playwright がそれに接続して旧コードを検査した
結果、10 件以上のテストが誤って失敗した。プロセスを停止してクリーンビルドしたら全 PASS になった。

`playwright.config.ts` の webServer は `reuseExistingServer: !process.env.CI` で既存サーバーを
再利用する設定のため、居残りサーバーが「新しい実装のはず」の検証を「古いコード」に対して行って
しまう。本ツールは E2E 実行直前に対象ポートを占有しているプロセスを検出し、**自セッションの
リポジトリ配下から起動された孤児プロセスに限って**停止する。

巻き込み事故の防止（他セッションのサーバーを誤って停止しない・Layer 1 レビュー指摘 #635）:
以下の 3 条件すべてを満たす場合のみ停止対象とする。
  1. cwd（`/proc/<pid>/cwd`）が本リポジトリのルートと一致する
  2. コマンドラインが既知の起動パターン（`next start` / `npm start` / `node .../server.mjs` 等）に一致する
  3. **孤児プロセスである**（親プロセスが既に終了し init(1) に再親化されている・`/proc/<pid>/stat` の
     PPid で判定）。本プロジェクトは CP-4（常に複数セッションが並行稼働している前提）を掲げており、
     同一リポジトリ cwd で別セッションが `run_checks.sh`/webServer を稼働中の可能性がある。そのセッションの
     親プロセスチェーン（playwright → npm start → next-server）が生きている限り PPid は 1 にならないため、
     「今まさに稼働中の他セッションのサーバー」は対象から除外され、「親が死んで取り残された孤児」だけを消せる。

停止時のプロセス同一性再検証（TOCTOU 対策・Layer 1 レビュー指摘 #635）: SIGTERM 送信後のポーリング中に
PID が別プロセスへ再利用されると無関係プロセスへ SIGKILL してしまうため、検出時点の cmdline + 起動時刻
（`/proc/<pid>/stat` の starttime）をスナップショットとして保持し、シグナル送信の直前に再取得して
一致する場合のみ次のシグナルへ進む。不一致になった時点で即座に打ち切る。

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
from typing import Callable

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


class PortScanUnavailable(Exception):
    """lsof が実行できず、対象ポートの占有状況を検査できなかったことを示す。"""


def find_pids_on_port(port: int) -> list[int]:
    try:
        out = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise PortScanUnavailable("lsof コマンドが見つかりません") from exc
    except subprocess.TimeoutExpired as exc:
        raise PortScanUnavailable("lsof の実行がタイムアウトしました") from exc
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


def read_proc_stat_fields(pid: int) -> list[str] | None:
    """/proc/<pid>/stat をフィールド配列で返す（comm 内の空白・括弧に耐えるパース）。"""
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            raw = f.read()
    except OSError:
        return None
    # フォーマット: "pid (comm) state ppid ... starttime ..."
    # comm はファイル名由来で空白・括弧を含みうるため、最後の ")" で分割する。
    after_comm = raw.rsplit(")", 1)
    if len(after_comm) != 2:
        return None
    return after_comm[1].split()


def read_proc_ppid(pid: int) -> int | None:
    fields = read_proc_stat_fields(pid)
    if fields is None or len(fields) < 2:
        return None
    try:
        return int(fields[1])
    except ValueError:
        return None


def read_proc_starttime(pid: int) -> str | None:
    fields = read_proc_stat_fields(pid)
    # state(0) ppid(1) pgrp(2) session(3) tty_nr(4) tpgid(5) flags(6) ... starttime は 22 番目
    # フィールド（`)` 直後を 0 始まりで数えた index 19）。
    if fields is None or len(fields) < 20:
        return None
    return fields[19]


def is_orphaned(pid: int) -> bool:
    """親プロセスが既に終了し init(1) に再親化されている（＝取り残された孤児）かどうか。"""
    ppid = read_proc_ppid(pid)
    return ppid == 1


def proc_identity(pid: int) -> tuple[str, str] | None:
    """kill 前後の同一性チェック用スナップショット（cmdline, starttime）。"""
    cmdline = read_proc_cmdline(pid)
    starttime = read_proc_starttime(pid)
    if cmdline is None or starttime is None:
        return None
    return (cmdline, starttime)


def collect_stale_candidates(ports: list[int], repo_root: str) -> list[tuple[int, int, str]]:
    """(port, pid, cmdline) のうち自リポジトリ配下・既知コマンド・孤児プロセスのものだけを返す。"""
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
            if not is_orphaned(pid):
                # 親プロセスが生きている = 他セッションが現在稼働中の可能性があるため対象外。
                continue
            candidates.append((port, pid, cmdline))
    return candidates


def kill_pid(
    pid: int,
    expected_identity: tuple[str, str],
    *,
    signal_fn: Callable[[int, int], None] = os.kill,
    sleep_fn: Callable[[float], None] = time.sleep,
    identity_fn: Callable[[int], tuple[str, str] | None] = proc_identity,
) -> bool:
    """expected_identity と一致する間だけ SIGTERM→SIGKILL を進める。成功したら True。

    `signal_fn` / `sleep_fn` / `identity_fn` は self-test から実プロセスへ触らず
    副作用の発生点（シグナル送信）まで到達させるための注入点（#817）。既定は本番と
    同じ `os.kill` / `time.sleep` / `proc_identity`。
    """
    if identity_fn(pid) != expected_identity:
        return False  # 検出後、シグナル送信前に別プロセスへ入れ替わっていた
    try:
        signal_fn(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    for _ in range(20):
        sleep_fn(0.1)
        try:
            signal_fn(pid, 0)
        except ProcessLookupError:
            return True
        if identity_fn(pid) != expected_identity:
            return False  # PID 再利用を検知。SIGKILL を送らず打ち切る
    if identity_fn(pid) != expected_identity:
        return False
    try:
        signal_fn(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        return False
    return True


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

    # /proc/<pid>/stat のパース（comm に空白・括弧を含むケースも通す）
    sample_stat = "123 (next-server (v16)) S 456 123 123 0 -1 4194560 100 0 0 0 5 2 0 0 20 0 4 0 987654321 0 0"
    fields = sample_stat.rsplit(")", 1)[1].split()
    assert fields[1] == "456", "ppid フィールドの位置がずれている"
    assert fields[19] == "987654321", "starttime フィールドの位置がずれている"
    checks += 1

    # 自身の pid は現在のシェル/親が生きているはずなので孤児ではない（is_orphaned の実プロセス動作確認）。
    if sys.platform == "linux" and os.path.exists(f"/proc/{os.getpid()}"):
        assert is_orphaned(os.getpid()) is False
        checks += 1

    # --- kill_pid() の副作用発生点を実プロセスに触らず検証する（#817・#686 と同型の穴の再発防止） ---
    # 旧実装は is_known_e2e_command 等の純粋関数だけを検証しており、実際にシグナルを送る
    # kill_pid() は一度も呼ばれていなかった。signal_fn/identity_fn/sleep_fn を注入し、
    # kill_pid() の本体ロジック（identity 不一致検知・SIGTERM→ポーリング→SIGKILL）を通す。

    fake_identity = ("node /repo/e2e/stub/server.mjs", "123456")

    # ケース 1: 検出直後に別プロセスへ入れ替わっていたら signal_fn は一切呼ばれず False。
    def _fail_if_called(pid: int, sig: int) -> None:
        raise AssertionError("identity 不一致のときは signal_fn を呼んではならない")

    result = kill_pid(
        999,
        fake_identity,
        signal_fn=_fail_if_called,
        sleep_fn=lambda s: None,
        identity_fn=lambda pid: ("別のプロセス", "999999"),
    )
    assert result is False, "identity 不一致を検知できていない"
    checks += 1

    # ケース 2: SIGTERM 後、次のポーリングで ProcessLookupError（消滅）→ True。
    sigterm_calls: list[int] = []

    def _signal_terminates_immediately(pid: int, sig: int) -> None:
        sigterm_calls.append(sig)
        if sig == 0:
            raise ProcessLookupError

    result = kill_pid(
        999,
        fake_identity,
        signal_fn=_signal_terminates_immediately,
        sleep_fn=lambda s: None,
        identity_fn=lambda pid: fake_identity,
    )
    assert result is True, "SIGTERM 後の終了を検知できていない"
    assert signal.SIGTERM in sigterm_calls, "kill_pid が SIGTERM を送っていない（副作用未到達）"
    checks += 1

    # ケース 3: SIGTERM 後も生き続け、ポーリング上限まで粘って最終的に SIGKILL が送られる。
    sigkill_calls: list[int] = []

    def _signal_survives_until_sigkill(pid: int, sig: int) -> None:
        sigkill_calls.append(sig)
        # sig==0（生存確認）は常に「まだ生きている」を返す（例外なし）。SIGKILL 到達を強制する。

    result = kill_pid(
        999,
        fake_identity,
        signal_fn=_signal_survives_until_sigkill,
        sleep_fn=lambda s: None,
        identity_fn=lambda pid: fake_identity,
    )
    assert result is True
    assert signal.SIGKILL in sigkill_calls, "生存し続けた場合に SIGKILL まで到達していない"
    checks += 1

    # ケース 4: main() の CLI 入口（build_arg_parser → run）を実際に通して、
    # 検出 → kill_fn 呼び出しまで到達することを確認する（内部関数の直呼びだけに留めない）。
    fake_candidates = [(3100, 4242, "node /repo/e2e/stub/server.mjs")]
    run_kill_calls: list[tuple[int, tuple[str, str]]] = []

    def _fake_collect(ports: list[int], repo_root: str) -> list[tuple[int, int, str]]:
        return fake_candidates

    def _fake_kill(pid: int, identity: tuple[str, str]) -> bool:
        run_kill_calls.append((pid, identity))
        # ここで実際の kill_pid ロジックへ委譲し、フェイクの signal_fn で副作用点まで通す。
        return kill_pid(
            pid,
            identity,
            signal_fn=_signal_terminates_immediately,
            sleep_fn=lambda s: None,
            identity_fn=lambda p: identity,
        )

    cli_args = build_arg_parser().parse_args(["--repo-root", "/repo"])
    exit_code = run(
        cli_args,
        collect_fn=_fake_collect,
        identity_fn=lambda pid: fake_identity,
        kill_fn=_fake_kill,
    )
    assert exit_code == 0
    assert run_kill_calls == [(4242, fake_identity)], "main() 入口から kill_fn まで到達していない"
    checks += 1

    print(f"[clear-stale-e2e-ports] self-test OK（{checks} 項目）")
    return 0


def run(
    args: argparse.Namespace,
    *,
    collect_fn: Callable[[list[int], str], list[tuple[int, int, str]]] = collect_stale_candidates,
    identity_fn: Callable[[int], tuple[str, str] | None] = proc_identity,
    kill_fn: Callable[[int, tuple[str, str]], bool] = kill_pid,
) -> int:
    """CLI 引数解釈より後ろの本体。`main()` の入口を経由しつつ、self-test からは
    `collect_fn` / `identity_fn` / `kill_fn` を差し替えて副作用の発生点（`kill_pid`
    のシグナル送信）まで到達させられる（#817）。既定値は本番の実装そのもの。"""
    if sys.platform != "linux":
        print("[clear-stale-e2e-ports] SKIP: /proc ベースの判定は Linux 専用のため何もしません")
        return 0

    ports = [int(p) for p in args.ports.split(",") if p.strip()]

    try:
        candidates = collect_fn(ports, args.repo_root)
    except PortScanUnavailable as exc:
        # lsof 不在等で検査自体ができなかった。「ゼロ件検出」と混同しないよう明示的に警告する
        # （黙って exit 0 を返すと、実際に居残りサーバーがあっても素通りしてしまう）。
        print(f"[clear-stale-e2e-ports] WARN: ポート占有の検査ができませんでした（{exc}）。クリーンアップをスキップします")
        return 0

    if not candidates:
        print("[clear-stale-e2e-ports] 居残りサーバーは検出されませんでした")
        return 0

    for port, pid, cmdline in candidates:
        print(f"[clear-stale-e2e-ports] 検出: port={port} pid={pid} cmd={cmdline}")

    if args.dry_run:
        print(f"[clear-stale-e2e-ports] --dry-run のため停止しません（{len(candidates)} 件）")
        return 0

    stopped = 0
    for port, pid, cmdline in candidates:
        identity = identity_fn(pid)
        if identity is None:
            print(f"[clear-stale-e2e-ports] スキップ: port={port} pid={pid}（検出後に消滅した可能性）")
            continue
        print(f"[clear-stale-e2e-ports] 停止します: port={port} pid={pid}")
        if kill_fn(pid, identity):
            stopped += 1
        else:
            print(f"[clear-stale-e2e-ports] WARN: port={port} pid={pid} の停止に失敗しました（別プロセスへの誤操作を避けるため中断）")

    print(f"[clear-stale-e2e-ports] {stopped}/{len(candidates)} 件の居残りサーバーを停止しました")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--ports",
        default=",".join(str(p) for p in DEFAULT_PORTS),
        help="検査するポート番号（カンマ区切り・既定: 3100,8788）",
    )
    parser.add_argument("--repo-root", default=os.getcwd(), help="自リポジトリのルートパス（既定: カレントディレクトリ）")
    parser.add_argument("--dry-run", action="store_true", help="停止せず候補一覧のみ表示する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク・プロセス非依存のユニットテストを実行する")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.self_test:
        return self_test()

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
