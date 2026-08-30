# generate_gem_digest.mjs

Gem Index の候補プール（**12 レジストリ・10 万リポジトリ級**）を Ecosyste.ms REST API から生成する Node CLI にゃ（`SP-17` / Issue #387）。

決定の正本は [`open-questions.md`](../docs/02_requirements/open-questions.md) の **`D-36`（母集団の拡大）** / **`D-37`（成層化・汚染フィルタ・dedupe）** / **`D-38`（レジストリ別シャード配信）** / **`D-40`（定期実行の起動経路・日次実行 / 週次反映）**。

## 何をするか

1. **収集**（`tools/gem-pool/collect.mjs`）: 12 レジストリそれぞれに **被依存数（`dependent_packages_count`）降順** で問い合わせ、**レジストリごとに同数の固定枠**（既定 15,000 件）を取る。母数比例枠は採らない（npm が枠の大半を占め、1 レジストリ支配を再現するため・`D-37` (1)）
2. **整形**（`tools/gem-pool/pipeline.mjs` の `projectPackage`）: 生 JSON から数値・識別子だけを取り出す
3. **順位付け**（同 `buildPool`）: 汚染フィルタ（star 数の欠損と真の `0` を区別する・`D-37` (2)）と **repo 単位 dedupe**（代表は被依存数最大の flagship パッケージ・`D-37` (3)）を通し、**自前プール内でレジストリ別に順位を再計算** して Gem Index を出す（`ADR 0009` §2.1）
4. **出力**（`tools/gem-pool/output.mjs`）: レジストリ別シャードと「今日の Gem」の候補プールを書き出す。どちらにも **出典メタデータ**（`source` / `license` / `sourceLicenseUrl` / `generatedAt`）を付ける（`D-29`・帰属表示は必須）

## 生成物

| パス                                         | 用途                                                                                                                                |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `public/data/gem-index/{registry-slug}.json` | レジストリ別シャード。isolate の cold start で並列取得して単一 `Map` にマージする配信データ（`D-38`）                               |
| `public/data/gem-index/index.json`           | どのシャードがあるかの入口（各シャードの `registry` / `ecosystem` / `fileName` / `count` と全体の `totalCount` / `meta` / `stats`） |
| `public/data/daily-digest.json`              | 「今日の Gem」の候補プール。新プールの Gem Index 上位 N 件（既定 300 件）のスライス                                                 |

### シャードの形（タプル形式）

```json
{
  "registry": "npmjs.org",
  "ecosystem": "npm",
  "meta": {
    "source": "Ecosyste.ms",
    "sourceUrl": "...",
    "license": "CC BY-SA 4.0",
    "sourceLicenseUrl": "...",
    "generatedAt": "..."
  },
  "columns": ["repositoryFullName", "packageName", "dependentCount", "stars", "gemIndex"],
  "entries": [["microsoft/TypeScript", "typescript", 488056, 110165, -0.05]]
}
```

- **キー名の反復を消すためのタプル形式**。10 万件級ではキー名の反復がそのまま転送量と `JSON.parse` の CPU（`D-38` の論点）に乗る
- 読む側が位置に依存しなくてよいよう `columns` を必ず同梱する
- `entries` は `gemIndex` 昇順（同値は `repositoryFullName` → `packageName`）で **入力順に依存しない決定論**。内容が同じなら git 差分も出ない
- シャードは **非整形 JSON**（サイズ優先）、`index.json` と `daily-digest.json` は差分を読むため整形して書く

### `daily-digest.json` の形

既存の shape（`date` / `meta` / `candidates`）を保ったまま、各候補に **`registry` を追加** した（`D-36` の「あるレジストリだけ緊急除外できるように」）。読み手は [`src/infrastructure/platform/static-gem-digest.ts`](../src/infrastructure/platform/static-gem-digest.ts)。

```json
{
  "date": "YYYYMMDD",
  "meta": { "...": "..." },
  "candidates": [
    {
      "packageName": "...",
      "repositoryFullName": "...",
      "dependentCount": 0,
      "stars": 0,
      "gemIndex": 0,
      "registry": "npmjs.org"
    }
  ]
}
```

## 使い方

```sh
# 既定（12 レジストリ × 15,000 件）。10 分級の実行になる
node tools/generate_gem_digest.mjs

# 書き込まず統計だけ見る（オプションの効き方を確かめるとき）
node tools/generate_gem_digest.mjs --dry-run

# 一部レジストリだけ様子を見る（既定では配信データを書き換えない・非ゼロ終了）
node tools/generate_gem_digest.mjs --registries npmjs.org,crates.io --quota 2000

# 一部レジストリだけで配信データを作り直す / 緊急除外する（明示の逃げ道）
node tools/generate_gem_digest.mjs --registries npmjs.org,crates.io --allow-partial-write

# 実行統計を JSON で残す（実測を PR に貼るとき）
node tools/generate_gem_digest.mjs --report content/analytics/gem-pool-report.json
```

> 🔵 **値の正本は `--help` の出力**（`generate_gem_digest.mjs` の `DEFAULT_*` 定数。既定値は `tools/generate_gem_digest.test.mjs` が固定している）。下表はその写しなので、食い違いを見つけたら `--help` を信じて表を直す。

| オプション                | 既定                            | 説明                                                                                                                                    |
| ------------------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `--quota N`               | `15000`                         | レジストリごとの取得枠（`D-37` (1) の固定枠）                                                                                           |
| `--per-page N`            | `1000`                          | 1 リクエストあたりの件数（API 上限 `1000` を超える値は切り詰める）                                                                      |
| `--registries a,b,c`      | 全 12 件                        | 対象レジストリ。未知の名前を渡すと候補一覧付きで失敗する                                                                                |
| `--min-stars N`           | `5`                             | 汚染フィルタ: star 数の下限（実測で決めた採用値・`D-37`）                                                                               |
| `--high-dependent-rank N` | `100`                           | 汚染フィルタ: 被依存数の「上位帯」をパーセンタイルで定義する。既定 `100` は **全帯** を対象にする（被依存帯による絞り込みを無効化する） |
| `--digest-limit N`        | `300`                           | `daily-digest.json` に載せる件数                                                                                                        |
| `--out-dir path`          | `public/data/gem-index`         | シャード出力先                                                                                                                          |
| `--digest-out path`       | `public/data/daily-digest.json` | 今日の Gem の候補プールの出力先                                                                                                         |
| `--report path`           | なし                            | 実行統計を JSON で書き出す（`--dry-run`・書き込み拒否時でも書く）                                                                       |
| `--allow-partial-write`   | off                             | 部分実行でも配信データを書き換える（下記「部分実行と配信データの保護」）                                                                |
| `--dry-run`               | off                             | ファイルを書かず統計だけ出す                                                                                                            |
| `--help` / `-h`           | —                               | ヘルプ                                                                                                                                  |

- 必要な Node バージョン: **22+**（グローバル `fetch` を使う）
- **進捗は stderr**（レジストリ名・ページ・累計件数・経過秒を 1 行ずつ）、**実測サマリーは stdout**（リクエスト数・取得件数・ユニーク repo 数・実行時間・出力ファイルとサイズ・レジストリ別構成比・除外理由別件数・Gem Index 上位 20 件の表）
- **1 レジストリの失敗では収集を止めない**（stderr に警告を出して残りを続ける・`NFR-8` と同じ思想）。ただし **揃わなかった実行では配信データを書き換えない**（下記）
- **全レジストリが失敗したとき、または候補プールが 0 件になったとき** は収集段で非ゼロ終了し、生成物は更新しない
- 引数エラー・致命的エラーは stderr へ 1 行 + 非ゼロ終了

### 部分実行と配信データの保護

配信データ（シャード / `index.json` / `daily-digest.json`）は **12 レジストリぶんが揃った実行でだけ** 書き換える。

| 実行                                                           | `--out-dir` / `--digest-out`             | 終了コード |
| -------------------------------------------------------------- | ---------------------------------------- | ---------- |
| 全 12 レジストリ成功                                           | 書き換える（+ 孤児シャードを削除）       | `0`        |
| `--registries` で部分指定した / 収集に失敗したレジストリがある | **書き換えない**（理由を stderr に出す） | `1`        |
| 同上 + `--allow-partial-write`                                 | 書き換える（+ 孤児シャードを削除）       | `0`        |
| `--dry-run`                                                    | 書かない（サイズだけ算出）               | `0`        |

- **なぜ拒否するか**: 部分実行の結果で上書きすると `index.json` の `shards` が今回集めた分だけに置き換わり、**索引から消えたシャードが孤児としてディスクに残る**。配信側（#388）は索引経由で読むためレジストリが丸ごと消え、`tools/measure_gem_coverage.py` はディレクトリ内の全 JSON を読むため被覆率だけが水増しされる
- **`--report` は常に書く**（実測の記録用途を潰さないため。拒否した実行でもサイズ・統計は算出される）
- **孤児シャードの削除**: 書き込む実行では、今回の `index.json` に載らない `*.json` を `--out-dir` から削除して索引とディスクを一致させる。削除したファイル名は stdout のサマリーと stderr に出す（黙って消さない）

## 実測値

2026-08-22 JST・既定オプション（12 レジストリ × 15,000 件 / `--min-stars 5` / `--high-dependent-rank 100` / `--digest-limit 300`）でクラウドセッションから実行した結果にゃ。

| 項目                                  | 実測値                                                                               |
| ------------------------------------- | ------------------------------------------------------------------------------------ |
| 実行時間（12 レジストリ × 15,000 件） | **3m 24s**（実行ごとに 2m37s〜8m07s。Ecosyste.ms 側の応答時間に左右される）          |
| 総リクエスト数                        | **180**（12 レジストリ × 15 ページ・`per_page=1000`。匿名 5,000 req/時の枠内）       |
| 総取得パッケージ数                    | **180,000**                                                                          |
| プール件数（ユニーク repo 数）        | **62,483**                                                                           |
| シャード合計サイズ（raw）             | **3.47 MiB**（12 ファイル）                                                          |
| 最大シャードのサイズ（raw）           | **563.2 KiB**（`proxy-golang-org.json`）                                             |
| `daily-digest.json` のサイズ          | **65.0 KiB**（上位 300 件）                                                          |
| レジストリ別構成比（上位 3 件）       | npm 15.49% / PyPI 14.93% / Go 13.49%（最小は CPAN 1.55%）                            |
| 除外理由別件数                        | star 欠損 13,750 / 被依存 0 件 14,344 / 低 star の汚染疑い 27,311 / repo 重複 29,639 |

- 🔵 **1 レジストリが支配していない**（最大の npm でも 15.5%）。`D-37` が却下した「レジストリ内順位の素の混在」（上位 100 件が Maven 87 / hex 13）と「素のグローバル再計算」（上位 100 件の 90 件が npm）のどちらの偏りも起きていない
- 🔵 **Gem Index 上位帯にも偏りが出ていない**: 上位 20 件は 9 レジストリ（packagist 4 / Go 3 / npm 4 / Maven 2 / CRAN 2 / PyPI 2 / hex 1 / pub.dev 1 / crates 1）、`daily-digest.json` の上位 60 件は 11 レジストリ、上位 300 件は 12 レジストリすべてにまたがる。
  🔴 **これは段順に依存する**（`buildPool` は **汚染フィルタと dedupe を通したあとの生き残りだけで順位を再計算する**）。順位をフィルタ前に計算すると、除外率がレジストリごとに 4.8%〜86.9% と違うため除外率の高いレジストリの `starRank` が切り詰められ、**上位 300 件が npm + Maven で 84%・6 レジストリがゼロ** になる（実測）。段順を変えるときは必ずこの分布を測り直すこと
- 🔵 **Gem Index 上位 20 件に `stars=0` の自動生成ミラー・repo 誤紐付けは 0 件**（失敗判定条件は「3 件以上混ざっていない」・出典は Issue #387 の完了条件 / 議論記録の lead 裁定）
- 被覆率の再測定は `python3 tools/measure_gem_coverage.py` で行う（クラウドでは `mcp__github__search_repositories` の結果を `--search-results` へ渡す・`L-114`）。**一般語 24 件で平均 34.5% / 中央値 34.5% / 最小 5.0% / 最大 57.0%・0 件ヒットのキーワードなし**。入力と結果のスナップショットは [`docs/01_research/data/20260822-gem-coverage-search-results.json`](../docs/01_research/data/20260822-gem-coverage-search-results.json) / [`20260822-gem-coverage.json`](../docs/01_research/data/20260822-gem-coverage.json)
- 生成物の機械検査は `python3 tools/check_gem_shards.py`（索引整合・件数整合・列・型・サイズ予算・`gemIndex` 昇順。`run_checks.sh` に配線済み）

## 候補プールの制約（`D-36` で解消済み）

`SP-14` 時点の候補プールは **npm 限定・被依存数降順の上位 294 件** で、[`ADR 0014`](../docs/adr/0014-zero-query-daily-digest.md) §2.6 の母集団不変条件を満たしていなかった。**この制約は `D-36` で解消した**:

- **npm 限定という構造的限界** → 12 レジストリへ拡大した（実測で検索ヒットの **52% が非 npm**・npm は母集団の 9.2%）
- **10 万件はバンドル 3MB(gzip) を圧迫する** → **Static Assets はバンドル枠に計上されない**（`D-38` のシャード配信へ変更）
- **上位 N 件が有名パッケージに偏り `R-2`（GitHub Trending の劣化コピー）に近づく** → 母集団 10.9 万リポジトリ + レジストリ別成層化 + 汚染フィルタで緩和した（`D-37`）

🔵 **残る境界**: `sort=gem-index`（検索結果の主ソート軸）は復活させない（`D-33` のこの部分は維持・理由は `D-36` の「ソート軸としての体験破綻」）。

## データ更新頻度

- 更新は `D-28` の方針どおり **Cloudflare の外** で行い、生成した JSON を git commit → デプロイで Static Assets ごと差し替える
- 🔴 **定期の起動経路は 1 つに定まっている（正本: `D-40`・Issue #458 / #482）**: [`.github/workflows/gem-pool-refresh.yml`](../.github/workflows/gem-pool-refresh.yml) が **日次で本 CLI を実行**（実行時刻の実体は同ファイルの `schedule`。本稿執筆時点で `cron: '17 21 * * *'` = JST 06:17）し、**`main` への反映（PR 作成）は直近の反映コミットから 7 日以上経過した回だけ** に絞る（生成・QA は毎日走らせてパイプラインの健全性を検証し、反映頻度だけを週次に落とす。反映の要否は `tools/gem_pool_qa.mjs --should-publish` が判定する）。手動での即時反映は同ワークフローの `workflow_dispatch`（`force_publish: true`）から行う
- 🔴 **定期実行をセッションが手で回す運用は残っていない**（放置される経路を作らないため）。**例外は 2 つだけ**（いずれも定期経路ではない）: ① 上記 `workflow_dispatch` による手動の即時反映 ② 下記 `--heal`（鮮度が閾値を超えたときにセッションが本 CLI を再実行するフォールバック）。ワークフローは PR を作るところまでを担い、**マージは Claude セッションの既存 PR 回収経路**（`pr-review-flow-summary.md` の `D-43`）が行う。`main` への直接 push・自動マージ・デプロイはワークフロー側では行わない（A-1）
- **鮮度監視も実データに接続済み**: `project-sync` スキル Step 3.85 が `python3 tools/check_digest_freshness.py --json --max-age-hours 192` を実データに対して実行し、stale なら `--heal` で再生成を試行、失敗時は Slack へ FYI 通知する（`E-25` / `NFR-8`）。`run_checks.sh` から呼ばれる `--self-test` は検査ロジックの回帰テストであり、鮮度監視の経路ではない

## ライセンス表示義務（`D-29`）

- 出力データは Ecosyste.ms の CC BY-SA 4.0 に基づく。UI 側でも `Data via Ecosyste.ms（CC BY-SA 4.0）` + ライセンス URL + 改変の明示を出す
- Ecosyste.ms の生テキスト（`description` / `topics` 等）は再配信しない。本 CLI は数値・識別子・自作の派生値（`gemIndex`）だけを出力する（`GR-6`）

## テスト

```sh
npx vitest run tools/generate_gem_digest.test.mjs   # CLI の既定値・引数エラー・書き込み判定
npx vitest run tools/gem-pool/output.test.mjs       # 生成物の形（純粋関数）
npx vitest run tools/                               # 収集・順位付けを含む gem-pool 全体
```
