# generate_gem_digest.mjs

キーワード非依存の日次ダイジェスト（`SP-14` / `ADR 0014`）の候補プール `public/data/daily-digest.json` と、レジストリ別シャード `public/data/gem-index/*.json`（`#388` が消費）を生成する Node CLI にゃ。

`SP-17`（Issue #387）で npm 単一レジストリ・上位 N 件の暫定実装から、**12 レジストリ横断・レジストリ内で固定枠を取得するプール方式** へ刷新した。

## 構成（`tools/gem-pool/` の 4 モジュール + 本 CLI）

本 CLI は **収集 → 変換 → 出力を束ねる薄いオーケストレーション** に徹し、実装本体は役割ごとに分離したモジュールが持つ（`SP-17` 実装契約）。

| モジュール                      | 役割                                                                  | 主なエクスポート                                                                      |
| ------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `tools/gem-pool/registries.mjs` | 対象 12 レジストリの定義                                              | `REGISTRIES` / `DEFAULT_QUOTA` / `DEFAULT_PER_PAGE` / `findRegistry`                  |
| `tools/gem-pool/collect.mjs`    | Ecosyste.ms REST API からレジストリ別に生パッケージ一覧を取得（I/O）  | `collectRegistry` / `collectAll`                                                      |
| `tools/gem-pool/pipeline.mjs`   | 正規化・汚染フィルタ・レジストリ横断 dedupe・順位再計算（純関数のみ） | `buildPool` / `poolStats` / `classifyStars` / `dedupeByRepository` / `recomputeRanks` |
| `tools/gem-pool/output.mjs`     | シャード / daily-digest.json への変換と書き出し                       | `buildShards` / `buildDailyDigest` / `writeOutputs` / `buildMeta`                     |

## 何をするか

1. **収集**（`collect.mjs`）: 12 レジストリそれぞれに対し、Ecosyste.ms REST API（`https://packages.ecosyste.ms/api/v1/registries/{name}/packages`）へ被依存数（`dependent_packages_count`）降順で問い合わせ、レジストリあたり `--quota` 件（既定 15000）を上限に取得する。429 / 5xx は指数バックオフで最大 3 回リトライし、恒久失敗したレジストリは空配列として扱う（1 レジストリの障害で他 11 レジストリを巻き込まない・`NFR-8`）
2. **変換**（`pipeline.mjs`）: 生パッケージを正規化し（GitHub リポジトリへ解決できないものは除外）、汚染候補（`stars === 0` × 高被依存 / フォーク・ミラー / 被依存あたり DL 数が下限未満）を除外し、同一リポジトリはレジストリ横断で dependentCount 最大の 1 件へ dedupe し、レジストリごとに被依存数 / star のパーセンタイル順位を自前プール内で再計算して `gemIndex = dependentRank - starRank`（小さいほど過小評価）を算出する（`D-37`）
3. **出力**（`output.mjs`）: 出典メタデータ（`source` / `sourceUrl` / `license` / `sourceLicenseUrl` / `generatedAt`・`D-29`）を付与し、`daily-digest.json`（gemIndex 昇順の上位 `--digest-limit` 件・既存スキーマに `registry` を追加しただけ）とレジストリ別シャード（`gem-index/{registry}.json`・`#388` が cold start で `Promise.all` 一括 fetch する配信契約）を書き出す

## `D-37` の 3 施策（母集団拡大に伴う対策）

- **レジストリ内固定枠 quota**: 各レジストリで被依存数上位 `quota` 件までを母集団とする（全量は取らない・CPU 予算対策）
- **汚染フィルタ（3 シグナルの OR）**: ① `stars === 0` かつ被依存数が閾値以上（repo 誤紐付けの疑い）② **フォーク / ミラー**（`repo_metadata.fork` / `mirror_url`。フォークはその package の代表リポジトリではなく、本家より star が少ないのは当然なので「過小評価の証拠」にならない）③ **被依存 1 件あたりの総ダウンロード数が下限未満**（1 万パッケージから依存されているのに総 DL が 13 万、というスパム farm の不可能な比を弾く）。🔴 **`downloads` が欠損しているものは汚染扱いにしない**（レジストリごとにカバレッジが違うため。同じ理由で `dependent_repos_count` は判定に使わない — 実測の根拠は下記「汚染フィルタの既定値をどう決めたか」）
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
  --zero-star-dependent-threshold 100 --min-downloads-per-dependent 100 \
  --out-dir public/data --no-shards
```

| フラグ                              | 既定値        | 説明                                                                                   |
| ----------------------------------- | ------------- | -------------------------------------------------------------------------------------- |
| `--quota N`                         | `15000`       | レジストリあたりの取得件数                                                             |
| `--registries id,id,...`            | 全 12 件      | 対象レジストリ（`npm,pypi,cargo,rubygems,packagist,go,maven,nuget,hex,pub,cpan,cran`） |
| `--digest-limit N`                  | `300`         | `daily-digest.json` に載せる件数                                                       |
| `--zero-star-dependent-threshold N` | `100`         | star=0 汚染判定の被依存数閾値（`0` 以下は指定不可）                                    |
| `--min-downloads-per-dependent N`   | `100`         | 「被依存 1 件あたりの総ダウンロード数」の下限（`0` で無効）                            |
| `--out-dir path`                    | `public/data` | 出力先ディレクトリ                                                                     |
| `--no-shards`                       | —             | レジストリ別シャード JSON を書かない（digest のみ）                                    |
| `--cache-dir path`                  | —             | 収集結果をレジストリ別 JSON でキャッシュし、次回はそこから読む                         |
| `--help`, `-h`                      | —             | ヘルプを表示                                                                           |

- 必要な Node バージョン: **21+**（グローバル `fetch` を使う）
- ネットワークエラー・引数不正時は非ゼロ終了 + stderr へ 1 行
- 標準出力に実行時間・総リクエスト数・レジストリ別件数・最終件数を出す

## 実測値（2026-08-22 JST・`SP-17` 着地時）

| 項目                   | 実測                                                                                                                                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 収集                   | **180 リクエスト / 約 3〜4 分**（12 レジストリ × 15 ページ・`per_page=1000`・匿名 5,000 req/時の枠内）                                                                                             |
| 取得パッケージ         | 180,000 件（12 レジストリ × 15,000 件の固定枠）                                                                                                                                                    |
| 変換（キャッシュから） | 約 1.2 秒                                                                                                                                                                                          |
| 最終候補プール         | **94,856 リポジトリ**（`star=0` の比率 14.8%）                                                                                                                                                     |
| レジストリ別内訳       | packagist 11,707 / hex 11,098 / go 10,328 / pypi 9,749 / pub 9,080 / npm 8,503 / cargo 7,985 / cpan 7,300 / cran 6,696 / rubygems 4,732 / nuget 4,339 / maven 3,339                                |
| 出力サイズ             | `daily-digest.json` 64KB / `gem-index/*.json` 合計 9.4MB（gzip 約 2.4MB・npm シャード単体は raw 1.05MB → gzip 246KB）                                                                              |
| 被覆率                 | 一般語 25 件 × GitHub 検索上位 100 件で **平均 33.4% / 中央値 34%**（`http client` 56% / `orm` 50% ↔ `encryption` 16% / `machine learning` 5%）。`D-36` の 3 クエリ実測（32% / 36% / 19%）と同水準 |

### 汚染フィルタの既定値をどう決めたか（`D-37`）

`--zero-star-dependent-threshold` と `--min-downloads-per-dependent` の既定値は、**実データで上位 20 件を目視する** ことで決めた（`SP-17` 完了条件 2）。

| 設定                                       | プール件数 | 上位 20 件の汚染                                                                                                              |
| ------------------------------------------ | ---------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `zeroStar>=1000` / DL 比 無効              | 99,554     | 🔴 **20/20 がスパム**（rubygems の `superjagger/*`・`a399414/*` — 同一オーナーが機械生成した gem 群が互いに依存し合っている） |
| `zeroStar>=100` / DL 比 無効               | 99,106     | 🔴 `superjagger/http_crawler`（★1・被依存 12,356）ほか 3 件が残る                                                             |
| **`zeroStar>=100` / DL 比 `<100`**（採用） | **94,856** | 🟢 **0 件**（`sphinx-doc/*`・`zopefoundation/*`・`aliyun/endpoint-util` 等、実在する過小評価パッケージだけになった）          |
| `zeroStar>=1` / DL 比 `<1000`              | 77,373     | 🟢 0 件だが pypi へ偏り、母集団を 2 割削る                                                                                    |

**却下した判定シグナル: `dependent_repos_count`**（実測で反証）。「実リポジトリからの依存が 0 ならスパム」という仮説は npm / rubygems / pypi の 5 サンプルでは成立したが、全 12 レジストリで測ると **Ecosyste.ms 側の repos インデックスのカバレッジ欠落** でしかないと判明した（CPAN の 96.1% / NuGet の 80.8% が `repos=0`。決定的な反例として **`newtonsoft.json`（被依存 26,480）が `repos=0`**）。採用していれば CPAN と NuGet がほぼ全滅し、`D-37` のレジストリ別成層化の趣旨を壊していた。

<!-- 実測値の更新手順: プールを再生成したら本節の数値を測り直す（被覆率は D-37 の「枠を見直すときは測り直す」条件と同じ運用）。 -->

## 出力ファイル

- `public/data/daily-digest.json`: `src/infrastructure/platform/static-gem-digest.ts` がバンドル取り込み（import）で読む本番データ。`date` / `meta` / `candidates[].{registry,packageName,repositoryFullName,dependentCount,stars,gemIndex}`
- `public/data/gem-index/{registry}.json`: `#388` が消費するレジストリ別シャード。`{ meta, columns: ['repositoryFullName','packageName','dependentCount','stars','gemIndex'], rows: [[...], ...] }`（`rows` は `gemIndex` 昇順）

## データ更新頻度

- 更新は `D-28` の方針どおり **Cloudflare の外** で行い、生成した JSON を git commit → デプロイで Static Assets ごと差し替える
- 本 CLI は「更新の実行手段」を用意するだけで、定期実行は **別レーン**（本 CLI 自体はまだ cron から呼ばれない）
- 🔵 リポジトリの Public 化で GitHub Actions が使えるようになったため、**この CLI を Actions の cron で定期実行する検討は Issue #415** で行う（`D-23` の失効確認・本番デプロイゲート `D-32` との噛み合わせ・生成物 9.4MB を毎回コミットする履歴肥大の許容ラインが論点）

## ライセンス表示義務（`D-29`）

- 出力データは Ecosyste.ms の CC BY-SA 4.0 に基づく。UI 側でも `Data via Ecosyste.ms（CC BY-SA 4.0）` + ライセンス URL + 改変の明示を出す
- Ecosyste.ms の生テキスト（`description` 等）は再配信しない。本 CLI は数値・識別子・自作の派生値（`gemIndex`）だけを出力する

## テスト

```sh
npx vitest run tools/gem-pool/ tools/generate_gem_digest.test.mjs
```

各モジュール（`tools/gem-pool/*.test.mjs`）は **ネットワークに依存しないテスト**（`fetch` は注入可能）。本 CLI 自身（`tools/generate_gem_digest.test.mjs`）は引数解析（`parseArgs` / `parseIntOption`）とキャッシュ制御（`collectWithCache`）を、収集関数を注入して実ネットワークなしで検証する。

🔴 **`tools/generate_gem_digest.mjs` は実行ガード付き**: `node tools/generate_gem_digest.mjs` として直接実行された時だけ `main()` が起動する（`import.meta.url` と `process.argv[1]` の比較）。テストから `parseArgs` 等を `import` しても本番のネットワーク収集・ファイル書き込みは走らない。

実データでの動作確認は `--cache-dir` にサンプル JSON を置いて `node tools/generate_gem_digest.mjs --cache-dir ... --out-dir /tmp/...` のように隔離実行する。
