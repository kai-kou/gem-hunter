#!/usr/bin/env python3
"""check_tracked_intent.py

.gitignore の否定パターン（`!` で始まる行）が指すパスが、
実際に git で追跡対象になっているかを検査するスクリプト。

背景：
  .gitignore には複数の否定パターンがあり、特定のディレクトリ・ファイルを
  「追跡対象のはず」として指定している（例: `!content/analytics/sprint/`）。
  しかし時間経過でそれらのパスが実際には削除されたり、追跡対象が不意に外れたりする
  「追跡意図ドリフト」が発生する。本ツールでそれを機械検査する。

使い方:
  python3 tools/check_tracked_intent.py                 # 検査のみ（違反あれば exit 1）
  python3 tools/check_tracked_intent.py --self-test    # セルフテスト

終了コード: 0=OK / 1=違反あり / 2=ツール異常
"""

# 本判定は run_checks.sh 4.12 節に条件付きで配線済み（.gitignore の全否定パターンに追跡
# ファイルが 1 件以上あるときだけ実行し、未投入の間は skip_check で理由を明示する・#164）。
import argparse
import subprocess
import sys
from pathlib import Path


def read_gitignore(repo_root: Path) -> list[str] | None:
    """リポジトリルートの .gitignore を読み込み、否定パターン行を返す。

    Returns:
        「! で始まり、パスを示す行」のリスト。コメント・空行は除外。
        各行は「!path/to/file」という形式。
        .gitignore 自体が読み込めない場合（ツール異常）は None
        （否定パターンが実際に 0 件のケースと区別するため空リストは返さない）。
    """
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.is_file():
        print(f"[check_tracked_intent] エラー: {gitignore_path} が見つかりません", file=sys.stderr)
        return None

    negations = []
    with open(gitignore_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            # コメント・空行を除外
            if not line or line.startswith("#"):
                continue
            # 否定パターン（! で始まる行）のみを対象
            if line.startswith("!"):
                negations.append(line)
    return negations


def check_git_tracked(repo_root: Path, path: str) -> bool:
    """指定パスが git で追跡対象（committed のファイル/ディレクトリ）になっているか判定。

    Args:
        repo_root: リポジトリルート
        path: 確認対象のパス（"!path/to/file" から "!" を削除した形。
              gitignore 仕様上のルートアンカー表記 "/path" も入力されうる）

    Returns:
        True = 追跡対象（committed） / False = 追跡対象外（ignored または存在しない）
    """
    # gitignore のルートアンカー表記（先頭 "/"）はリポジトリルート基準を意味するだけで
    # パストラバーサルではないため、判定前に取り除く（誤って絶対パス扱いしない）。
    # パスの末尾スラッシュも削除（ディレクトリの場合）。
    target = path.lstrip("/").rstrip("/")

    # パストラバーサル対策: .gitignore 由来の未検証パスをそのまま git コマンドへ渡さない
    if not target or ".." in Path(target).parts:
        return False

    # git ls-files で追跡対象を確認
    #    - 末尾に / を付けて渡すと git ls-files がディレクトリ配下を展開してくれる
    #    - ファイル・ディレクトリのどちらでも 1 件以上マッチすれば追跡対象と判定
    #    - "--" で pathspec 開始位置を明示し、"-" 始まりのパスがオプションと
    #      誤解釈されるのを防ぐ
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--", f"{target}/", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            # 1 件以上マッチした = 追跡対象
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return False


def main():
    parser = argparse.ArgumentParser(
        description="Check that .gitignore negation patterns point to tracked files/dirs"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test with synthetic data",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    # 通常検査
    repo_root = Path.cwd()
    negations = read_gitignore(repo_root)

    if negations is None:
        # .gitignore 自体が読めない = ツール異常（呼び出し元の cwd 誤り等）
        return 2

    if not negations:
        print("[check_tracked_intent] 否定パターンはありません")
        return 0  # 違反なし

    violations = []
    for neg_line in negations:
        # "!path" -> "path"（gitignore の行中 "#" はコメント区切りではなくパターンの
        # 一部なので、行頭コメント除外は read_gitignore 側にすでに任せてありここでは触らない）
        target = neg_line[1:].strip()  # "!" を削除

        if not target:
            continue  # "!" だけの行はスキップ

        is_tracked = check_git_tracked(repo_root, target)

        if not is_tracked:
            violations.append((neg_line, target))

    if violations:
        print("[check_tracked_intent] 違反検出: .gitignore の否定パターンが追跡対象外")
        for neg_line, target in violations:
            print(f"  {neg_line} -> {target} は git では追跡されていません")
        return 1
    else:
        print(f"[check_tracked_intent] PASS: {len(negations)} 個の否定パターンを確認しました")
        return 0


def self_test():
    """合成データでセルフテストを実行。"""
    print("[check_tracked_intent] セルフテスト開始...")

    # テスト用の仮想 gitignore 内容
    test_gitignore = """# 追跡対象外の一般的なもの
__pycache__/
*.pyc
node_modules/

# 但し、以下の特定ファイル・ディレクトリは追跡対象
!content/analytics/sprint/
!content/analytics/retro/
!.env.example
"""

    # テスト対象の否定パターンを抽出
    test_negations = []
    for line in test_gitignore.split("\n"):
        line = line.rstrip("\n")
        if line and not line.startswith("#") and line.startswith("!"):
            test_negations.append(line)

    checks = []
    checks.append(("否定パターン抽出", len(test_negations) == 3))

    # check_git_tracked() の境界値（実装本体を直接呼ぶ・自リポジトリ内で完結するため安全）
    repo_root = Path.cwd()
    checks.append(("パストラバーサル拒否 (../etc/passwd)", check_git_tracked(repo_root, "../etc/passwd") is False))
    checks.append(("空文字列拒否", check_git_tracked(repo_root, "") is False))
    checks.append(("存在しないパスは False", check_git_tracked(repo_root, "__definitely_not_exists__/") is False))
    checks.append(("ルートアンカー表記 (/tools) を追跡対象と判定", check_git_tracked(repo_root, "/tools") is True))

    # read_gitignore() の異常系（存在しないディレクトリ → None）
    checks.append(("read_gitignore は不在時 None を返す", read_gitignore(Path("/__no_such_dir__")) is None))

    passed = 0
    for name, ok in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}")
        if ok:
            passed += 1

    if passed == len(checks):
        print(f"[check_tracked_intent] セルフテスト成功: {passed}/{len(checks)}")
        return 0
    else:
        print(f"[check_tracked_intent] セルフテスト失敗: {passed}/{len(checks)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
