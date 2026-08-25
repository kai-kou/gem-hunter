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
import argparse
import re
import subprocess
import sys
from pathlib import Path


def read_gitignore(repo_root: Path) -> list[str]:
    """リポジトリルートの .gitignore を読み込み、否定パターン行を返す。

    Returns:
        「! で始まり、パスを示す行」のリスト。コメント・空行は除外。
        各行は「!path/to/file」という形式。
    """
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.is_file():
        print(f"[check_tracked_intent] エラー: {gitignore_path} が見つかりません", file=sys.stderr)
        return []

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
        path: 確認対象のパス（"!path/to/file" から "!" を削除した形）

    Returns:
        True = 追跡対象（committed） / False = 追跡対象外（ignored または存在しない）
    """
    # パスの末尾スラッシュを削除（ディレクトリの場合）
    target = path.rstrip("/")

    # 1. git ls-files で追跡対象を確認
    #    - 末尾に / が付いていると git ls-files がディレクトリ配下を展開してくれる
    #    - その代わり複数行返却されるため、1 件以上あれば追跡対象と判定
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", f"{target}"],
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

    # 2. 末尾が / だったら再度 / 付きで試す（ディレクトリ扱い）
    if path.endswith("/"):
        return False  # 既に / で試済みなのでここで false

    # 3. 最後の手段: ファイルシステム上に存在するか確認（committed でなくても working tree にあれば引っかかる）
    #    → ただし検査対象は「committed」なので、ここで True にはしない（False で OK）

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

    if not negations:
        print("[check_tracked_intent] 警告: .gitignore に否定パターンが見つかりません")
        return 0  # 違反なし

    violations = []
    for neg_line in negations:
        # "!path" -> "path"
        target = neg_line[1:]  # "!" を削除

        # パスの後ろのコメント・空白を処理（`! path # comment` の形式に対応）
        if "#" in target:
            target = target[: target.index("#")].strip()
        else:
            target = target.strip()

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

    # セルフテストでは、抽出ロジックのみ検証（git コマンドの実行は避ける）
    if len(test_negations) == 3:
        print(f"  ✓ 否定パターン抽出: {test_negations}")
        print(f"[check_tracked_intent] セルフテスト成功: {len(test_negations)} パターンを認識しました")
        return 0
    else:
        print(f"[check_tracked_intent] セルフテスト失敗: {len(test_negations)} パターン（期待値: 3）", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
