# セキュリティポリシー / Security Policy

> English follows Japanese.

## 対象範囲

| 区分 | 対象 |
|---|---|
| ✅ 対象 | 本リポジトリのコード（`src/` / `app/` / `e2e/` / `config/` / `messages/`）と、[`https://gem-hunter.kinamocchi-tech.workers.dev`](https://gem-hunter.kinamocchi-tech.workers.dev) で稼働しているアプリケーション |
| ✅ 対象 | 自律運用ハーネス（`tools/` / `.claude/`）のうち、**秘匿情報の取り扱いに関わる部分** |
| ❌ 対象外 | 依存パッケージそのものの脆弱性（各上流へ報告してほしい。本リポジトリでは Dependabot が追跡している） |
| ❌ 対象外 | GitHub / Cloudflare など、本プロダクトが利用しているプラットフォーム側の問題 |
| ❌ 対象外 | [`NOTICE`](../NOTICE) に記載した第三者著作物の内容 |

## サポートするバージョン

本プロダクトはリリースタグを発行しておらず、**`main` ブランチと本番デプロイのみをサポート** する。過去のコミットに対する修正提供は行わない。

| 対象 | サポート |
|---|---|
| `main`（および本番デプロイ） | ✅ |
| それ以外のブランチ・過去コミット | ❌ |

## 報告方法

🔴 **公開 Issue に脆弱性の詳細を書かないでほしい。** 修正前に攻撃手段が公開されることになる。

**[Security タブ → Report a vulnerability](https://github.com/kai-kou/gem-hunter/security/advisories/new)** から非公開で報告してほしい（GitHub の Private vulnerability reporting）。

報告に以下が含まれていると調査が早い。

- 再現手順（可能ならリクエストの内容）
- 影響（何ができてしまうか）
- 影響を受ける箇所（ファイル・エンドポイント・URL）

## 対応の流れと期待値

⚠️ **本プロダクトは個人開発のポートフォリオであり、専任のセキュリティ担当はいない。** 対応は best-effort で、SLA は提示しない。

1. 報告を受け取ったら、内容を確認して再現を試みる
2. 再現できた場合は修正を実装し、`main` へ反映してから本番へデプロイする
3. 修正後、報告者の希望に応じて GitHub Security Advisory を公開する

## 🔵 既知の「脆弱性ではないもの」

以下は **意図的なもの** であり、報告は不要である。

| 事象 | 説明 |
|---|---|
| **テスト内の固定鍵・ダミー資格情報** | `src/infrastructure/platform/session-cookie.test.ts` / `e2e/stub/e2e-env.mjs` / `playwright.config.ts` に固定文字列がある。いずれも **テスト専用のダミー** で本番の値とは無関係。「異なる鍵では復号できない」ことの検証や、E2E スタブへの注入に必要 |
| **未認証時に GitHub API のレート枠が狭いこと** | 環境変数を設定しない構成を意図的に許容している（[README](../README.md#環境変数)）。仕様であって不具合ではない |
| **`telemetry/cost-data` ブランチに開発コストが記録されていること** | 公開する判断を明示的に行っている。秘匿情報は含まない |
| **リポジトリの設定・運用ルールが全公開であること** | `CLAUDE.md` と `docs/rules/` を含め、AI 自律開発の運用を意図的に公開している |

## 関連ドキュメント

- [`docs/rules/security-posture-controls.md`](../docs/rules/security-posture-controls.md) — 自律運用（`bypassPermissions`）を安全にしている補償統制
- [ADR 0003](../docs/adr/0003-github-app-authentication.md) — サーバー側の GitHub 認証方式
- [ADR 0012](../docs/adr/0012-optional-github-oauth.md) — 任意 OAuth ログインとセッション Cookie の暗号化
- [ADR 0013](../docs/adr/0013-public-operation-under-github-terms.md) — 公開運用にあたっての GitHub 利用規約上の制約

---

# Security Policy (English)

## Scope

**In scope**: the code in this repository (`src/`, `app/`, `e2e/`, `config/`, `messages/`), the application running at [`https://gem-hunter.kinamocchi-tech.workers.dev`](https://gem-hunter.kinamocchi-tech.workers.dev), and the parts of the automation harness (`tools/`, `.claude/`) that handle secrets.

**Out of scope**: vulnerabilities in third-party dependencies themselves (please report those upstream; Dependabot tracks them here), issues in platforms this product uses (GitHub, Cloudflare), and the third-party materials listed in [`NOTICE`](../NOTICE).

## Supported versions

This project publishes no release tags. Only `main` and the production deployment are supported. No fixes are backported to older commits.

## Reporting a vulnerability

🔴 **Please do not open a public issue with vulnerability details.**

Use **[Security → Report a vulnerability](https://github.com/kai-kou/gem-hunter/security/advisories/new)** to report privately. Reproduction steps, impact, and the affected file/endpoint help a lot.

## What to expect

⚠️ This is an individual's portfolio project with no dedicated security staff. Handling is best-effort and no SLA is offered. Confirmed issues are fixed on `main` and deployed to production; a GitHub Security Advisory is published afterwards if the reporter wants one.

## Known non-issues

Fixed dummy keys and credentials in tests (`session-cookie.test.ts`, `e2e/stub/e2e-env.mjs`, `playwright.config.ts`) are intentional test fixtures unrelated to production values. Narrow GitHub API rate limits when no environment variables are set is documented behaviour, not a defect. The development-cost telemetry on the `telemetry/cost-data` branch is published deliberately and contains no secrets.
