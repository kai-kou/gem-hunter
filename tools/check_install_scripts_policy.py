#!/usr/bin/env python3
"""check_install_scripts_policy.py — 本番ビルド環境の依存インストールが痩せる退行を静的に止める

【背景（Issue #497）】
Cloudflare Workers Builds の本番ビルドが `Cannot find package 'esbuild'` で失敗した。
npm 12 環境で `npm ci` を実行したところ、次の 2 つが同時に起きていた（実測で再現済み）。

  1. **install スクリプトが既定でブロックされる**（npm 11.15 で導入・npm 12 で既定 off）。
     `esbuild` / `workerd` の postinstall が走らず、ネイティブバイナリが配置されない。
     許可は `package.json` の `allowScripts` フィールドで宣言する（`npm install-scripts approve`）。
  2. **`esbuild` が直接依存として宣言されていなかった**。トップレベルの `node_modules/esbuild` は
     `vite` の **optional peer dependency** として入っていただけで、npm 12 の `npm ci` では
     インストールされない。`@opennextjs/cloudflare` は `esbuild` を bare import するのに
     自身の依存として宣言していないため、巻き上げが消えた瞬間に解決できなくなる。

どちらも「ローカルの `node_modules` では動くのに本番ビルドだけ落ちる」形で現れ、
実行するまで気づけない。本スクリプトはこの 2 点を **ネットワーク非依存の静的検査** に落とす。

【検査内容】
  A. `package-lock.json` で `hasInstallScript: true` かつ Linux/x64 で入りうるパッケージが、
     すべて `package.json` の `allowScripts` に載っていること。
  B. `REQUIRED_DIRECT_DEPENDENCIES` のパッケージが root の dependencies / devDependencies に
     直接宣言されていること（巻き上げ頼みの解決に戻る退行を止める）。

【終了コード】
  0 = 違反なし
  1 = 違反あり（詳細を stdout に出す）
  2 = 検査不能（package.json / package-lock.json が読めない等・fail-closed）

使い方:
    python3 tools/check_install_scripts_policy.py
    python3 tools/check_install_scripts_policy.py --json
    python3 tools/check_install_scripts_policy.py --self-test   # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# 本番ビルド環境（Cloudflare Workers Builds）のプラットフォーム。
# lockfile の `os` / `cpu` 制約がこれに一致しないパッケージは、その環境では入らないので検査しない。
BUILD_PLATFORM_OS = "linux"
BUILD_PLATFORM_CPU = "x64"

# 巻き上げ（hoisting）任せにできない bare import。値は「なぜ直接宣言が要るか」の理由。
REQUIRED_DIRECT_DEPENDENCIES = {
    "esbuild": (
        "@opennextjs/cloudflare が dist/cli/build/bundle-server.js から bare import するが、"
        "自身の dependencies に持たない。直接宣言しないと vite の optional peer 経由の巻き上げ頼みになり、"
        "npm 12 の npm ci でトップレベルから消える（Issue #497）"
    ),
}


def package_name_from_lock_key(key: str) -> str | None:
    """lockfile のキー（`node_modules/a/node_modules/@scope/b`）からパッケージ名を取り出す。

    ネストしたキーでも最後の `node_modules/` 以降がパッケージ名になる。root（空文字）は None。
    """
    marker = "node_modules/"
    index = key.rfind(marker)
    if index == -1:
        return None
    name = key[index + len(marker) :]
    return name or None


def is_installable_on_build_platform(entry: dict[str, Any]) -> bool:
    """lockfile エントリが本番ビルド環境（Linux/x64）で入りうるかを判定する。

    `os` / `cpu` が無いエントリは全プラットフォーム対象なので True。
    否定形（`"!win32"`）にも対応する（npm の os/cpu フィールド仕様）。
    """

    def matches(constraints: Any, actual: str) -> bool:
        if not isinstance(constraints, list) or not constraints:
            return True
        negated = [c[1:] for c in constraints if isinstance(c, str) and c.startswith("!")]
        if negated:
            return actual not in negated
        return actual in constraints

    return matches(entry.get("os"), BUILD_PLATFORM_OS) and matches(
        entry.get("cpu"), BUILD_PLATFORM_CPU
    )


def collect_install_script_packages(lock: dict[str, Any]) -> dict[str, list[str]]:
    """`hasInstallScript: true` かつ本番ビルド環境で入りうるパッケージ名 → lockfile キー一覧。"""
    found: dict[str, list[str]] = {}
    for key, entry in (lock.get("packages") or {}).items():
        if not isinstance(entry, dict) or not entry.get("hasInstallScript"):
            continue
        if not is_installable_on_build_platform(entry):
            continue
        name = package_name_from_lock_key(key)
        if name is None:
            continue
        found.setdefault(name, []).append(key)
    return found


def allow_scripts_names(package_json: dict[str, Any]) -> set[str]:
    """`allowScripts` の宣言をパッケージ名の集合に正規化する。

    npm は pin 有無で `{"esbuild": true}` と `{"esbuild@0.28.2": true}` の 2 形式を書くため、
    どちらでも名前として突き合わせられるように `@version` を落とす（スコープ名の先頭 `@` は残す）。
    値が falsy（`deny` された宣言）のエントリは「許可されていない」として除外する。
    """
    allowed: set[str] = set()
    raw = package_json.get("allowScripts")
    if not isinstance(raw, dict):
        return allowed
    for declaration, value in raw.items():
        if not value:
            continue
        at_index = declaration.rfind("@")
        name = declaration[:at_index] if at_index > 0 else declaration
        allowed.add(name)
    return allowed


def direct_dependency_names(package_json: dict[str, Any]) -> set[str]:
    """root の dependencies / devDependencies に直接宣言された名前の集合。"""
    names: set[str] = set()
    for field in ("dependencies", "devDependencies"):
        section = package_json.get(field)
        if isinstance(section, dict):
            names.update(section.keys())
    return names


def find_violations(
    package_json: dict[str, Any], lock: dict[str, Any]
) -> list[dict[str, str]]:
    """検査 A / B を実行し、違反リスト（空なら合格）を返す純関数。"""
    violations: list[dict[str, str]] = []

    allowed = allow_scripts_names(package_json)
    for name, keys in sorted(collect_install_script_packages(lock).items()):
        if name in allowed:
            continue
        violations.append(
            {
                "kind": "install-script-not-allowed",
                "package": name,
                "detail": (
                    f"{name} は install スクリプトを持つ（lockfile: {', '.join(sorted(keys))}）が "
                    "package.json の allowScripts に無い。npm 12 の npm ci ではスクリプトが"
                    "ブロックされ、ネイティブバイナリが配置されないまま本番ビルドが落ちる"
                ),
            }
        )

    direct = direct_dependency_names(package_json)
    for name, reason in sorted(REQUIRED_DIRECT_DEPENDENCIES.items()):
        if name in direct:
            continue
        violations.append(
            {
                "kind": "missing-direct-dependency",
                "package": name,
                "detail": (
                    f"{name} が dependencies / devDependencies に直接宣言されていない。理由: {reason}"
                ),
            }
        )

    return violations


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────
# self-test（ネットワーク・ファイル非依存）
# ──────────────────────────────────────────────


def _self_test_package_name_from_lock_key() -> list[str]:
    cases = [
        ("node_modules/esbuild", "esbuild"),
        ("node_modules/@esbuild/linux-x64", "@esbuild/linux-x64"),
        ("node_modules/wrangler/node_modules/esbuild", "esbuild"),
        ("node_modules/a/node_modules/@scope/b", "@scope/b"),
        ("", None),
    ]
    failures = []
    for key, expected in cases:
        actual = package_name_from_lock_key(key)
        if actual != expected:
            failures.append(f"package_name_from_lock_key({key!r}): expected {expected!r}, got {actual!r}")
    return failures


def _self_test_is_installable_on_build_platform() -> list[str]:
    cases = [
        ({}, True),
        ({"os": ["linux"], "cpu": ["x64"]}, True),
        ({"os": ["darwin"], "cpu": ["arm64"]}, False),
        ({"os": ["linux"], "cpu": ["arm64"]}, False),
        ({"os": ["!win32"]}, True),
        ({"os": ["!linux"]}, False),
        ({"cpu": ["wasm32"]}, False),
    ]
    failures = []
    for entry, expected in cases:
        actual = is_installable_on_build_platform(entry)
        if actual != expected:
            failures.append(f"is_installable_on_build_platform({entry!r}): expected {expected}, got {actual}")
    return failures


def _self_test_allow_scripts_names() -> list[str]:
    cases = [
        ({}, set()),
        ({"allowScripts": {"esbuild": True}}, {"esbuild"}),
        ({"allowScripts": {"esbuild@0.28.2": True}}, {"esbuild"}),
        ({"allowScripts": {"@scope/pkg@1.0.0": True}}, {"@scope/pkg"}),
        ({"allowScripts": {"@scope/pkg": True}}, {"@scope/pkg"}),
        ({"allowScripts": {"esbuild": False}}, set()),
        ({"allowScripts": "nope"}, set()),
    ]
    failures = []
    for package_json, expected in cases:
        actual = allow_scripts_names(package_json)
        if actual != expected:
            failures.append(f"allow_scripts_names({package_json!r}): expected {expected}, got {actual}")
    return failures


def _self_test_find_violations() -> list[str]:
    failures = []

    ok_package_json = {
        "devDependencies": {"esbuild": "^0.28.2"},
        "allowScripts": {"esbuild": True, "workerd": True},
    }
    ok_lock = {
        "packages": {
            "": {"name": "app"},
            "node_modules/esbuild": {"hasInstallScript": True},
            "node_modules/workerd": {"hasInstallScript": True},
            "node_modules/@esbuild/linux-x64": {"os": ["linux"], "cpu": ["x64"]},
            "node_modules/@esbuild/darwin-arm64": {
                "hasInstallScript": True,
                "os": ["darwin"],
                "cpu": ["arm64"],
            },
        }
    }
    violations = find_violations(ok_package_json, ok_lock)
    if violations:
        failures.append(f"合格ケースで違反が出た: {violations}")

    # allowScripts から workerd が抜けた退行を検知する
    missing_allow = {
        "devDependencies": {"esbuild": "^0.28.2"},
        "allowScripts": {"esbuild": True},
    }
    violations = find_violations(missing_allow, ok_lock)
    kinds = {(v["kind"], v["package"]) for v in violations}
    if ("install-script-not-allowed", "workerd") not in kinds:
        failures.append(f"allowScripts 欠落を検知できていない: {violations}")

    # esbuild の直接宣言が消えた退行を検知する（Issue #497 の本体）
    missing_direct = {"devDependencies": {}, "allowScripts": {"esbuild": True, "workerd": True}}
    violations = find_violations(missing_direct, ok_lock)
    kinds = {(v["kind"], v["package"]) for v in violations}
    if ("missing-direct-dependency", "esbuild") not in kinds:
        failures.append(f"esbuild 直接宣言の欠落を検知できていない: {violations}")

    # dependencies 側の宣言でも合格する（devDependencies 限定になっていないこと）
    direct_in_deps = {
        "dependencies": {"esbuild": "^0.28.2"},
        "allowScripts": {"esbuild": True, "workerd": True},
    }
    if find_violations(direct_in_deps, ok_lock):
        failures.append("dependencies 側の直接宣言を合格にできていない")

    # ネストしたキーのパッケージも名前で突き合わせる
    nested_lock = {
        "packages": {
            "": {"name": "app"},
            "node_modules/wrangler/node_modules/esbuild": {"hasInstallScript": True},
        }
    }
    if find_violations(
        {"devDependencies": {"esbuild": "^0.28.2"}, "allowScripts": {"esbuild": True}}, nested_lock
    ):
        failures.append("ネストした esbuild を allowScripts で許可済みと判定できていない")

    return failures


def run_self_test() -> int:
    checks = [
        ("package_name_from_lock_key", _self_test_package_name_from_lock_key),
        ("is_installable_on_build_platform", _self_test_is_installable_on_build_platform),
        ("allow_scripts_names", _self_test_allow_scripts_names),
        ("find_violations", _self_test_find_violations),
    ]
    failures: list[str] = []
    for name, check in checks:
        result = check()
        if result:
            failures.extend(result)
            print(f"  FAIL {name}")
            for line in result:
                print(f"       {line}")
        else:
            print(f"  ok   {name}")
    if failures:
        print(f"self-test: FAIL（{len(failures)} 件）")
        return 1
    print("self-test: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    try:
        package_json = _load_json(REPO_ROOT / "package.json")
        lock = _load_json(REPO_ROOT / "package-lock.json")
    except (OSError, ValueError) as error:
        message = f"⚠️ 検査不能: package.json / package-lock.json を読めません（{error}）"
        if args.json:
            print(json.dumps({"ok": False, "unable_to_check": True, "detail": str(error)}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 2

    violations = find_violations(package_json, lock)

    if args.json:
        print(json.dumps({"ok": not violations, "violations": violations}, ensure_ascii=False, indent=2))
    elif violations:
        print(f"❌ install スクリプト方針の違反が {len(violations)} 件あります（Issue #497 の再発）:")
        for violation in violations:
            print(f"  - [{violation['kind']}] {violation['package']}")
            print(f"      {violation['detail']}")
        print()
        print("対処:")
        print("  - install-script-not-allowed → `npm install-scripts approve <pkg> --no-allow-scripts-pin`")
        print("  - missing-direct-dependency  → `npm install --save-dev <pkg>`")
    else:
        print("✅ install スクリプト方針: 違反なし（allowScripts の網羅・必須の直接依存を確認）")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
