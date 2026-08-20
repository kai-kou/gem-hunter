# generate_gem_digest.mjs

キーワード非依存の日次ダイジェスト（`SP-14` / `ADR 0014`）の候補プール `public/data/daily-digest.json` を生成する Node CLI にゃ。

## 何をするか

- Ecosyste.ms REST API（`https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages`）に **被依存数（`dependent_packages_count`）の降順** で問い合わせ、上位 N 件を取得する
- 各パッケージの `rankings.dependent_packages_count` と `rankings.stargazers_count`（Ecosyste.ms 側で日次計算済みのパーセンタイル順位・0〜100・0 が最上位）から Gem Index を差分で算出する（`ADR 0009` §2.1）
- 出力 JSON のトップレベルに **出典メタデータ**（`source` / `license` / `sourceLicenseUrl` / `generatedAt`）を付与する（`D-29`・帰属表示は必須）

## 使い方

```sh
# 既定: 50 件を取得して public/data/daily-digest.json に書き出す
node tools/generate_gem_digest.mjs

# 件数と出力先を上書き
node tools/generate_gem_digest.mjs --limit 100 --out public/data/daily-digest.json
```

- 必要な Node バージョン: **21+**（グローバル `fetch` を使う）
- ネットワークエラー時は非ゼロ終了 + stderr へ 1 行

## データ更新頻度

- 更新は `D-28` の方針どおり **Cloudflare の外**（セッション or Routine の cron）で行い、生成した JSON を git commit → デプロイで Static Assets ごと差し替える
- 本 CLI は「更新の実行手段」を用意するだけで、CI やスケジューラでの自動実行は **別レーン**（本 CLI 自体は cron からは呼ばれない）

## ライセンス表示義務（`D-29`）

- 出力データは Ecosyste.ms の CC BY-SA 4.0 に基づく。UI 側でも `Data via Ecosyste.ms（CC BY-SA 4.0）` + ライセンス URL + 改変の明示を出す
- Ecosyste.ms の生テキスト（`description` 等）は再配信しない。本 CLI は数値・識別子・自作の派生値（`gemIndex`）だけを出力する
