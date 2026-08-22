# generate_gem_digest.mjs

キーワード非依存の日次ダイジェスト（`SP-14` / `ADR 0014`）の候補プール `public/data/daily-digest.json` と、レジストリ別シャード `public/data/gem-index/*.json`（`#388` が消費）を生成する Node CLI にゃ。

`SP-17`（Issue #387）で npm 単一レジストリ・上位 N 件の暫定実装から、**12 レジストリ横断・レジストリ内で固定枠を取得するプール方式** へ刷新した。

## 構成（`tools/gem-pool/` の 4 モジュール + 本 CLI）

本 CLI は **収集 → 変換 → 出力を束ねる薄いオーケストレーション** に徹し、実装本体は役割ごとに分離したモジュールが持つ（`SP-17` 実装契約）。

| モジュール | 役割 | 主なエクスポート |
|---|---|---|
| `tools/gem-pool/registries.mjs` | 対象 12 レジストリの定義 | `REGISTRIES` / `DEFAULT_QUOTA` / `DEFAULT_PER_PAGE` / `findRegistry` |
| `tools/gem-pool/collect.mjs` | Ecosyste.ms REST API からレジストリ別に生パッケージ一覧を取得（I/O） | `collectRegistry` / `collectAll` |
| `tools/gem-pool/pipeline.mjs` | 正規化・汚染フィルタ・レジストリ横断 dedupe・順位再計算（純関数のみ） | `buildPool` / `poolStats` / `classifyStars` / `dedupeByRepository` / `recomputeRanks` |
| `tools/gem-pool/output.mjs` | シャード / daily-digest.json への変換と書き出し | `buildShards` / `buildDailyDigest` / `writeOutputs` / `buildMeta` |

## 何をするか

1. **収集**（`collect.mjs`）: 12 レジストリそれぞれに対し、Ecosyste.ms REST API（`https://packages.ecosyste.ms/api/v1/registries/{name}/packages`）へ被依存数（`dependent_packages_count`）降順で問い合わせ、レジストリあたり `--quota` 件（既定 15000）を上限に取得する。429 / 5xx は指数バックオフで最大 3 回リトライし、恒久失敗したレジストリは空配列として扱う（1 レジストリの障害で他 11 レジストリを巻き込まない・`NFR-8`）
2. **変換**（`pipeline.mjs`）: 生パッケージを正規化し（GitHub リポジトリへ解決できないものは除外）、`stars === 0` かつ被依存数が閾値以上の「汚染」候補（repo 誤紐付け・自動生成ミラーの疑い）を除外し、同一リポジトリはレジストリ横断で dependentCount 最大の 1 件へ dedupe し、レジストリごとに被依存数 / star のパーセンタイル順位を自前プール内で再計算して `gemIndex = dependentRank - starRank`（小さいほど過小評価）を算出する（`D-37`）
3. **出力**（`output.mjs`）: 出典メタデータ（`source` / `sourceUrl` / `license` / `sourceLicenseUrl` / `generatedAt`・`D-29`）を付与し、`daily-digest.json`（gemIndex 昇順の上位 `--digest-limit` 件・既存スキーマに `registry` を追加しただけ）とレジストリ別シャード（`gem-index/{registry}.json`・`#388` が cold start で `Promise.all` 一括 fetch する配信契約）を書き出す

## `D-37` の 3 施策（母集団拡大に伴う対策）

- **レジストリ内固定枠 quota**: 各レジストリで被依存数上位 `quota` 件までを母集団とする（全量は取らない・CPU 予算対策）
- **star=0 汚染フィルタ**: `stars === 0` かつ被依存数が閾値以上の候補は repo 誤紐付けの疑いが強いため除外する
- **レジストリ別順位の自前再計算**: Ecosyste.ms の `rankings`（全レジストリ横断の順位）は使わず、収集した自前プール内でレジストリごとにパーセンタイル順位を計算し直す

## 使い方

```sh
# 既定: 全 12 レジストリ・quota 15000・digest 上位 300 件
node tools/generate_gem_digest.mjs

# 一部レジストリだけ収集
node tools/generate_gem_digest.mjs --registries npm,pypi

# 収集結果をレジストリ別 JSON でキャッシュし、次回はそこから読む
# （10 分近くかかる収集を試行錯誤のたびに走らせないため）
node tools/generate_gem_digest.mjs --cache-dir .gem-cache

# その他のフラグ例
node tools/generate_gem_digest.mjs --quota 20000 --digest-limit 500 \
  --zero-star-dependent-threshold 1000 --out-dir public/data --no-shards
```

| フラグ | 既定値 | 説明 |
|---|---|---|
| `--quota N` | `15000` | レジストリあたりの取得件数 |
| `--registries id,id,...` | 全 12 件 | 対象レジストリ（`npm,pypi,cargo,rubygems,packagist,go,maven,nuget,hex,pub,cpan,cran`） |
| `--digest-limit N` | `300` | `daily-digest.json` に載せる件数 |
| `--zero-star-dependent-threshold N` | `1000` | star=0 汚染判定の被依存数閾値 |
| `--out-dir path` | `public/data` | 出力先ディレクトリ |
| `--no-shards` | — | レジストリ別シャード JSON を書かない（digest のみ） |
| `--cache-dir path` | — | 収集結果をレジストリ別 JSON でキャッシュし、次回はそこから読む |
| `--help`, `-h` | — | ヘルプを表示 |

- 必要な Node バージョン: **21+**（グローバル `fetch` を使う）
- ネットワークエラー・引数不正時は非ゼロ終了 + stderr へ 1 行
- 標準出力に実行時間・総リクエスト数・レジストリ別件数・最終件数を出す

<!-- 実測値: 親が追記 -->

## 出力ファイル

- `public/data/daily-digest.json`: `src/infrastructure/platform/static-gem-digest.ts` がバンドル取り込み（import）で読む本番データ。`date` / `meta` / `candidates[].{registry,packageName,repositoryFullName,dependentCount,stars,gemIndex}`
- `public/data/gem-index/{registry}.json`: `#388` が消費するレジストリ別シャード。`{ meta, columns: ['repositoryFullName','packageName','dependentCount','stars','gemIndex'], rows: [[...], ...] }`（`rows` は `gemIndex` 昇順）

## データ更新頻度

- 更新は `D-28` の方針どおり **Cloudflare の外**（セッション or Routine の cron）で行い、生成した JSON を git commit → デプロイで Static Assets ごと差し替える
- 本 CLI は「更新の実行手段」を用意するだけで、CI やスケジューラでの自動実行は **別レーン**（本 CLI 自体は cron からは呼ばれない）

## ライセンス表示義務（`D-29`）

- 出力データは Ecosyste.ms の CC BY-SA 4.0 に基づく。UI 側でも `Data via Ecosyste.ms（CC BY-SA 4.0）` + ライセンス URL + 改変の明示を出す
- Ecosyste.ms の生テキスト（`description` 等）は再配信しない。本 CLI は数値・識別子・自作の派生値（`gemIndex`）だけを出力する

## テスト

```sh
npx vitest run tools/gem-pool/registries.mjs tools/gem-pool/*.test.mjs
```

各モジュールは **ネットワークに依存しないテスト**（`fetch` は注入可能）。実データでの動作確認は `--cache-dir` にサンプル JSON を置いて `node tools/generate_gem_digest.mjs --cache-dir ... --out-dir /tmp/...` のように隔離実行する。
