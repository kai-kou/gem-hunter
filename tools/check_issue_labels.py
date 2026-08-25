#!/usr/bin/env python3
"""check_issue_labels.py

Open Issue が必須ラベル（type:* / status:* / sp:*）を持っているか検査する。

背景：
  Issue のトリアージ・管理に 3 種類の必須ラベルを使用している：
  - type:feature / type:bug / type:improvement / type:docs / type:retro-try
  - status:waiting-user / status:waiting-claude / status:in-progress / status:blocked
  - sp:1 / sp:2 / sp:3 / sp:5 / sp:8

  定義の SSOT は session-sprint-rules.md 等。タスク受領時に Issue を作成するときは
  これら 3 種を必ず付与すべきだが、手動では漏れが発生する。本ツールで機械検査する。

使い方:
  python3 tools/check_issue_labels.py --check              # GitHub API で open Issue を取得し検査
  python3 tools/check_issue_labels.py --self-test          # セルフテスト
  python3 tools/check_issue_labels.py --repo-root ./.     # リポジトリルート指定

注意：
  GitHub API（`gh` コマンド経由）を呼び出すため、認証と ネットワーク接続が必要。
  CI/run_checks.sh には含めず、手動実行専用スクリプト。

終了コード: 0=OK / 1=違反あり（未必須ラベル Issue 存在） / 2=ツール異常
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def check_gh_available() -> bool:
    """gh コマンドが利用可能か確認（実 gh でなくシムの場合は False）。"""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "gh version" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_open_issues(repo_owner: str, repo_name: str) -> list[dict]:
    """GitHub API (gh) で open Issue を全件取得。

    Args:
        repo_owner: 所有者名（例: "kai-kou"）
        repo_name: リポジトリ名（例: "gem-hunter"）

    Returns:
        Issue 情報のリスト: [{"number": N, "labels": [...]}, ...]
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                f"{repo_owner}/{repo_name}",
                "--state",
                "open",
                "--json",
                "number,labels",
                "--limit",
                "1000",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"[check_issue_labels] エラー: gh issue list が失敗しました", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"[check_issue_labels] エラー: {e}", file=sys.stderr)
        return []


def has_label_prefix(labels: list[dict], prefix: str) -> bool:
    """ラベル一覧に prefix: で始まるラベルがあるか判定。

    Args:
        labels: [{"name": "type:feature"}, ...]
        prefix: "type" など

    Returns:
        True = prefix: で始まるラベルが 1 件以上ある
    """
    for label in labels:
        if label.get("name", "").startswith(f"{prefix}:"):
            return True
    return False


def check_issue_labels(repo_owner: str, repo_name: str) -> tuple[int, list[dict]]:
    """Open Issue の必須ラベル要件を検査する。

    Returns:
        (exit_code, violations)
        violations: [{"number": N, "missing": ["type", "status"]}, ...]
    """
    issues = get_open_issues(repo_owner, repo_name)
    if not issues:
        print("[check_issue_labels] 警告: open Issue が取得できません", file=sys.stderr)
        return 0, []

    required_prefixes = ["type", "status", "sp"]
    violations = []

    for issue in issues:
        number = issue.get("number")
        labels = issue.get("labels", [])

        missing = [p for p in required_prefixes if not has_label_prefix(labels, p)]

        if missing:
            violations.append(
                {"number": number, "missing": missing}
            )

    return (1 if violations else 0, violations)


def main():
    parser = argparse.ArgumentParser(
        description="Check that open Issues have required labels (type/status/sp)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check open Issues via GitHub API",
    )
    parser.add_argument(
        "--repo-owner",
        default="kai-kou",
        help="GitHub repository owner (default: kai-kou)",
    )
    parser.add_argument(
        "--repo-name",
        default="gem-hunter",
        help="GitHub repository name (default: gem-hunter)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test with synthetic data",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.check:
        print("[check_issue_labels] 使い方: --check または --self-test を指定してください", file=sys.stderr)
        return 2

    # 通常検査: GitHub API 経由で open Issue をチェック
    if not check_gh_available():
        print("[check_issue_labels] エラー: gh コマンドが利用不可（API 経由での実行が必要）", file=sys.stderr)
        return 2

    print(f"[check_issue_labels] {args.repo_owner}/{args.repo_name} の open Issue を検査中...", file=sys.stderr)

    exit_code, violations = check_issue_labels(args.repo_owner, args.repo_name)

    if violations:
        print(f"[check_issue_labels] 違反検出: {len(violations)} 件の Issue に必須ラベルが欠落しています")
        for v in violations:
            print(f"  #{v['number']}: 欠落 {v['missing']}")
        return 1
    else:
        print("[check_issue_labels] PASS: 全 open Issue が必須ラベルを保持しています")
        return 0


def self_test():
    """合成データでセルフテストを実行。"""
    print("[check_issue_labels] セルフテスト開始...")

    # テスト用合成データ
    test_cases = [
        {
            "number": 100,
            "labels": [
                {"name": "type:feature"},
                {"name": "status:in-progress"},
                {"name": "sp:3"},
            ],
            "expected_missing": [],
        },
        {
            "number": 101,
            "labels": [
                {"name": "type:bug"},
                {"name": "status:waiting-user"},
                # sp: がない
            ],
            "expected_missing": ["sp"],
        },
        {
            "number": 102,
            "labels": [
                # type: がない
                {"name": "status:in-progress"},
                {"name": "sp:5"},
            ],
            "expected_missing": ["type"],
        },
    ]

    required_prefixes = ["type", "status", "sp"]
    passed = 0

    for test in test_cases:
        labels = test["labels"]
        missing = [p for p in required_prefixes if not has_label_prefix(labels, p)]

        if missing == test["expected_missing"]:
            passed += 1
            print(f"  ✓ Issue #{test['number']}: 期待通り {test['expected_missing']} が欠落")
        else:
            print(f"  ✗ Issue #{test['number']}: 期待 {test['expected_missing']}, 実測 {missing}", file=sys.stderr)

    if passed == len(test_cases):
        print(f"[check_issue_labels] セルフテスト成功: {passed}/{len(test_cases)} テストケース")
        return 0
    else:
        print(f"[check_issue_labels] セルフテスト失敗: {passed}/{len(test_cases)} テストケース", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
