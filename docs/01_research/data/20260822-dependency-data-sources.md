# 被依存数データソースの一次リサーチ（2026-08-22 JST）

- **目的**: Gem Index（被依存数の順位 − star の順位・[ADR 0009](../../adr/0009-hidden-gem-score-definition.md)）の **母集団を npm 227 リポジトリから脱出させる** ための、データソースと配信方式の実現可能性を一次情報で確定する
- **背景**: [`open-questions.md`](../../02_requirements/open-questions.md) `D-33` が「候補プールが npm 限定・ユニーク 227 リポジトリで、検索上位 100 件との一致がほぼ 0」を理由に検索の Gem Index ソートを撤去した
- **位置づけ**: 事実の記録（**決定はしない**）。決定は議論記録 [`gem-index-feasibility-20260822`](../../../content/discussions/gem-index-feasibility-20260822/whiteboard.md) と決定ログが持つ
- **取得日**: 2026-08-22 JST（すべて実 API レスポンスまたは公式ドキュメントの逐語）

---

## 1. GitHub API 単独では被依存数は取れない（再確認）

| API | 取れるもの | 逆方向（dependents） | 備考 |
|---|---|---|---|
| GraphQL `repository.dependencyGraphManifests` | **順方向のみ**（自分が依存する側） | ✗ | `hawkgirl-preview` ヘッダ必要・要認証 |
| REST `GET /repos/{o}/{r}/dependency-graph/sbom` | SPDX JSON（順方向） | ✗ | 要 Bearer |
| `dependencyGraphDependents` 等の逆方向 API | — | **存在しない**（公式ロードマップなし） | [community #175773](https://github.com/orgs/community/discussions/175773) |
| `GET /search/repositories` | 検索結果 | — | 1,000 件上限・認証 30 req/分・`sort` は stars / forks / help-wanted-issues / updated のみ（**利用度軸は無い**） |
| `GET /search/code` | コード出現数 | 間接的 | 要認証 **10 req/分**・既定ブランチのみ・384KB 未満・`total_count` は推定値 |
| `GET /repos/{o}/{r}/stargazers`（`starred_at`） | star 時系列 | — | 🔴 **2026-07 から admin / collaborator 限定**。第三者リポジトリの star 履歴は API では取れない |
| Releases アセットの `download_count` | 累計 DL 数 | — | 匿名可。CLI・バイナリ配布系には効くがライブラリ系には効かない |
| Traffic API（views / clones） | — | — | **push 権限必須**。他人のリポジトリでは取得不可 |

- HTML の "Used by" 表示の取得は **スクレイピング** に該当する。[Acceptable Use](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies) は "Scraping does not refer to the collection of information through our API." と明記しており、**API 経由の取得は問題ないが HTML 取得は方針として採らない**（`R-8`）。
- 結論: **被依存数は GitHub 外のデータソースでしか得られない**。この前提は `ADR 0009` §3.1 から変わっていない。

## 2. Ecosyste.ms（現行データソース）の実力

出典: [registries API](https://packages.ecosyste.ms/api/v1/registries) / [open-data](https://packages.ecosyste.ms/open-data) / [licences](https://docs.ecosyste.ms/docs/usage/licences/)

- **109 レジストリ・合計 約 1,470 万パッケージ**（`total-count` ヘッダの実測値・2026-08-22）。主要どころは npm 5,764,611 / Go 2,281,833 / PyPI 929,795 / NuGet 842,021 / Maven 617,071 / Packagist 510,768 / crates.io 327,700 / RubyGems 211,249。
- 一覧 API は **`per_page=1000` が通り、深いページ（offset 30 万）でも 200**。1 レコードに `rankings`・`repository_url`・`repo_metadata.stargazers_count`・`dependent_packages_count`・`dependent_repos_count` が同梱されるため、**1 パスの取得だけで Gem Index を計算して GitHub の `owner/repo` へ正規化できる**（個別 fetch 不要）。
- レート制限は **匿名 5,000 req/時**（実測ヘッダ `x-ratelimit-limit: 5000`）。polite pool（UA に連絡先）で 15,000 req/時。
- 🔴 **`rankings` はレジストリ内順位**（値域 0〜100・0 が最上位）。PyPI `requests` も npm `lodash` も `dependent_repos_count` 順位は 0.0 付近になるため、**レジストリを混ぜてそのまま並べると小さいレジストリの無名パッケージが上位を占拠する**。横断ランキングを作るなら収集後に全体パーセンタイルを再計算する必要がある。
- バルクダンプは `packages-2026-02-05.tar.gz` = **63.7GB**・更新は不定期（2023-10 → 2024-03 → 2024-06 → 2026-02）。repos ダンプは 2023-08 で陳腐化。**API 巡回のほうが速く新しい**。
- `GET /api/v1/packages/lookup?repository_url=https://github.com/{owner}/{repo}` で **リポジトリ URL から全レジストリ横断でパッケージを引ける**（検索結果との突き合わせに使える）。
- ライセンスは **データ CC BY-SA 4.0 / コード AGPL-3**。派生データの再配布には帰属・改変明示・継承が要る（`GR-6` / `D-29`）。

## 3. 代替・補完データソース

| データ源 | 取れるもの | 規模 | 一括取得 | 更新 | ライセンス | 判定 |
|---|---|---|---|---|---|---|
| **deps.dev BigQuery** `bigquery-public-data.deps_dev_v1` | `DependentsLatest`（辺単位）→ 自前集計。`Projects` に **stars 同梱** | 8 エコシステム全量（数十億辺） | SQL 集計 → GCS へ CSV export | 日次相当のスナップショット | **CC-BY 4.0**（SA でない） | 🔵 精度・規模では本命。⚠️ Dependents 系のフルスキャンで **無料枠 1TB を一撃で超える事故報告**（[google/deps.dev#109](https://github.com/google/deps.dev/issues/109)）。ドライラン必須 |
| deps.dev API v3alpha `:dependents` | `dependentCount` / direct / indirect | 1 リクエスト = 1 バージョン | ✗ | 継続 | — | バージョン単位なので集約ルールが要る（express@4.18.2 = 2,189 vs Ecosyste.ms のパッケージ単位 93,237） |
| **OpenSSF criticality_score** の公開 CSV | `repo.url` / `star_count` / `depsdev.dependent_count` ほか 20 列 | 585,601 行（119MB） | 単一 CSV | 🔴 **2025-08-13 で停止** | Apache-2.0（生成物は明記なし） | ❌ 恒久データ源にしない（`dependent_count` の充填率 **6.8%**・約 1 年更新なし） |
| OpenSSF **Scorecard**（`api.scorecard.dev`） | 健全性チェック | 100 万件規模・週次 | BigQuery `openssf:scorecardcron.scorecard-v2` | 週次 | — | 🔵 健在。`GR-2`（健全性の足切り）はこちらへ寄せる |
| Libraries.io Open Data | `dependent_repos_count` ほか | 24.9GB | Zenodo | 🔴 **2020-01 で凍結** | CC BY-SA 4.0 | ❌ 使わない |
| GH Archive / ClickHouse `github_events` | star・fork・issue の **時系列** | 70 億イベント・10 分ごと | [play.clickhouse.com](https://play.clickhouse.com/play)（ログイン不要） | 10 分 | CC-BY | 🔵 被依存の代替にはならないが、GitHub API で取れなくなった **star 履歴** の唯一の入手経路 |
| crates.io DB dump / RubyGems dump | 依存関係を自前集計可 | — | 日次 / 週次 | — | 各レジストリ | 補完用。Ecosyste.ms で足りるなら不要 |

## 4. 母集団を広げたときの被覆率（実測）

Ecosyste.ms の一覧 API を **12 レジストリ × 被依存数降順** で巡回して候補プールを作り、GitHub 検索の一般語での上位 100 件と突き合わせた（`D-33` の再導入条件そのものの測定）。

| プール | 取得パッケージ | ユニーク GitHub repo | react | test framework | image processing |
|---|---|---|---|---|---|
| 現行（npm 限定） | 294 | 227 | 6% | 3% | 0% |
| 8 レジストリ × 1,000 | 8,000 | 4,926 | 11% | 19% | 5% |
| 8 レジストリ × 2,500 | 20,000 | 12,558 | 23% | 23% | 7% |
| **12 レジストリ × 15,000** | **180,000** | **109,469**（rankings 完備） | **32%** | **36%** | **19%** |

- 収集コスト: **180 リクエスト（12 レジストリ × 15 ページ・`per_page=1000`）・約 10 分**（匿名 5,000 req/時の枠内）。
- **母集団の構成**: npm は 10,026 件で **全体の 9.2%**（各レジストリから同数を取る固定枠のため）。**検索ヒット 87 件のレジストリ内訳** は npm 42 / PyPI 13 / Maven 7 / Packagist 7 / Go 7 / RubyGems 5 / crates 2 / NuGet 2 / pub.dev 1 / Hex 1 で、**ヒットの 52% が非 npm**。`D-33` が指摘した「npm 限定という構造的限界」は **レジストリを増やすことで実際に解消する**。
- 生成物のサイズ: `owner/repo → gemIndex`（小数 2 桁）の最小 JSON で **raw 3.3MB / gzip 1.34MB**（109,469 件）。
- ⚠️ この時点の Gem Index 上位は hex / CRAN / pub.dev の極小パッケージに偏る（レジストリ内順位をそのまま混ぜた副作用・§2 の 🔴 と同じ問題）。**横断ランキングにはパーセンタイルの再計算が要る**。

## 5. Cloudflare Workers Free での配信制約（一次情報）

出典: [workers/platform/limits](https://developers.cloudflare.com/workers/platform/limits/) / [pricing](https://developers.cloudflare.com/workers/platform/pricing/) / [static-assets/billing-and-limitations](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)

| 項目 | Free の上限 |
|---|---|
| Worker バンドル | **3MB（gzip）** |
| **Static Assets** | **20,000 ファイル / version・1 ファイル 25MiB**。🔵 **バンドル 3MB 枠に計上されない**。リクエストは **無料・無制限**（10 万 req/日 にも計上されない） |
| CPU | **10ms / リクエスト**（ネットワーク待ちは非算入） |
| subrequest | **50 / invocation**（`env.ASSETS.fetch()` も Cache API も消費） |
| メモリ / 起動 | 128MB / startup 1 秒 |
| D1 | 読み **500 万行 / 日**・書き 10 万行 / 日・5GB |
| KV | 読み **10 万 / 日**・書き 1,000 / 日 |
| R2 | 10GB・Class A 100 万 / 月・Class B 1,000 万 / 月・**Range GET 可** |

- 🔴 **`D-33` の「10 万件は Workers Free のバンドル 3MB 上限を圧迫する」という判断は、現行実装（JSON を `import` でバンドルへ焼き込む）に固有の制約** であり、Static Assets へ置けば **プラットフォーム上の制約ではなくなる**。
- ただし **CPU 10ms** のため 3MB 級 JSON を毎リクエスト `JSON.parse` するのは非現実的（1 回に parse する塊は数十〜200KB が安全ライン）。**subrequest 50** のため 100 件を 100 シャードに分けて引くこともできない。→ 分割設計そのものが論点になる。
- ⚠️ Workers Caching（新機能）を有効化すると、**本来無料の静的アセットリクエストが課金対象リクエストに変わる**（`INF-2` に抵触）。有効化しない。`caches.default`（Cache API）は別物。

## 6. この調査で確定したこと / 残った未検証

**確定**

1. 被依存数は GitHub API では取れない（`ADR 0009` の前提は今も正しい）。
2. Ecosyste.ms の API 巡回で **10 万リポジトリ級の母集団を 10 分・180 リクエストで作れる**（バルクダンプ不要）。
3. 母集団を広げると被覆率は実際に上がる（0〜6% → 19〜36%）。npm 限定という構造的限界は解消する。
4. Static Assets はバンドル 3MB 枠の外であり、`D-33` のサイズ根拠は配信方式の変更で崩れる。

**未検証（実装時に潰す）**

- レジストリ横断の全体パーセンタイル再計算の妥当性（どの母集団を 100% とするか・`Q-3` 従属事項）
- モノレポ（1 リポジトリ複数パッケージ）の集約ルール（min / max / 合算）による順位の変動
- パッケージ側が申告する `repository_url` の信頼性（未検証メタデータ・偽陽性）
- deps.dev BigQuery を使う場合の実クエリ課金量（ドライラン必須）
- 被覆率をさらに上げたときの上限（30 万・100 万件でどこまで伸びるか）
