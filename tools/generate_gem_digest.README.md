# generate_gem_digest.mjs

Gem Index の候補プール（**12 レジストリ・10 万リポジトリ級**）を Ecosyste.ms REST API から生成する Node CLI にゃ（`SP-17` / Issue #387）。

決定の正本は [`open-questions.md`](../docs/02_requirements/open-questions.md) の **`D-36`（母集団の拡大）** / **`D-37`（成層化・汚染フィルタ・dedupe）** / **`D-38`（レジストリ別シャード配信）**。

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

# 一部レジストリだけ再生成する / 緊急除外する
node tools/generate_gem_digest.mjs --registries npmjs.org,crates.io --quota 2000

# 実行統計を JSON で残す（実測を PR に貼るとき）
node tools/generate_gem_digest.mjs --report content/analytics/gem-pool-report.json
```

| オプション                | 既定                            | 説明                                                         |
| ------------------------- | ------------------------------- | ------------------------------------------------------------ |
| `--quota N`               | `15000`                         | レジストリごとの取得枠（`D-37` (1) の固定枠）                |
| `--per-page N`            | `1000`                          | 1 リクエストあたりの件数                                     |
| `--registries a,b,c`      | 全 12 件                        | 対象レジストリ。未知の名前を渡すと候補一覧付きで失敗する     |
| `--min-stars N`           | `1`                             | 汚染フィルタ: star 数の下限                                  |
| `--high-dependent-rank N` | `10`                            | 汚染フィルタ: 被依存数の「上位帯」をパーセンタイルで定義する |
| `--digest-limit N`        | `300`                           | `daily-digest.json` に載せる件数                             |
| `--out-dir path`          | `public/data/gem-index`         | シャード出力先                                               |
| `--digest-out path`       | `public/data/daily-digest.json` | 今日の Gem の候補プールの出力先                              |
| `--report path`           | なし                            | 実行統計を JSON で書き出す（`--dry-run` でも書く）           |
| `--dry-run`               | off                             | ファイルを書かず統計だけ出す                                 |
| `--help` / `-h`           | —                               | ヘルプ                                                       |

- 必要な Node バージョン: **22+**（グローバル `fetch` を使う）
- **進捗は stderr**（レジストリ名・ページ・累計件数・経過秒を 1 行ずつ）、**実測サマリーは stdout**（リクエスト数・取得件数・ユニーク repo 数・実行時間・出力ファイルとサイズ・レジストリ別構成比・除外理由別件数・Gem Index 上位 20 件の表）
- **1 レジストリの失敗では止まらない**（stderr に警告を出して継続する・`NFR-8` と同じ思想）。**全レジストリが失敗したとき、または候補プールが 0 件になったときだけ** 非ゼロ終了し、生成物は更新しない
- 引数エラー・致命的エラーは stderr へ 1 行 + 非ゼロ終了

## 実測値

<!-- 実測値は SP-17 の実行後に親セッションが追記 -->

| 項目                                  | 実測値 |
| ------------------------------------- | ------ |
| 実行時間（12 レジストリ × 15,000 件） |        |
| 総リクエスト数                        |        |
| 総取得パッケージ数                    |        |
| プール件数（ユニーク repo 数）        |        |
| シャード合計サイズ（raw）             |        |
| 最大シャードのサイズ（raw）           |        |
| `daily-digest.json` のサイズ          |        |
| レジストリ別構成比（上位 3 件）       |        |
| 除外理由別件数                        |        |

## 候補プールの制約（`D-36` で解消済み）

`SP-14` 時点の候補プールは **npm 限定・被依存数降順の上位 294 件** で、[`ADR 0014`](../docs/adr/0014-zero-query-daily-digest.md) §2.6 の母集団不変条件を満たしていなかった。**この制約は `D-36` で解消した**:

- **npm 限定という構造的限界** → 12 レジストリへ拡大した（実測で検索ヒットの **52% が非 npm**・npm は母集団の 9.2%）
- **10 万件はバンドル 3MB(gzip) を圧迫する** → **Static Assets はバンドル枠に計上されない**（`D-38` のシャード配信へ変更）
- **上位 N 件が有名パッケージに偏り `R-2`（GitHub Trending の劣化コピー）に近づく** → 母集団 10.9 万リポジトリ + レジストリ別成層化 + 汚染フィルタで緩和した（`D-37`）

🔵 **残る境界**: `sort=gem-index`（検索結果の主ソート軸）は復活させない（`D-33` のこの部分は維持・理由は `D-36` の「ソート軸としての体験破綻」）。

## データ更新頻度

- 更新は `D-28` の方針どおり **Cloudflare の外**（セッション or Routine の cron）で行い、生成した JSON を git commit → デプロイで Static Assets ごと差し替える
- 本 CLI は「更新の実行手段」を用意するだけで、CI やスケジューラでの自動実行は **別レーン**（本 CLI 自体は cron からは呼ばれない）

## ライセンス表示義務（`D-29`）

- 出力データは Ecosyste.ms の CC BY-SA 4.0 に基づく。UI 側でも `Data via Ecosyste.ms（CC BY-SA 4.0）` + ライセンス URL + 改変の明示を出す
- Ecosyste.ms の生テキスト（`description` / `topics` 等）は再配信しない。本 CLI は数値・識別子・自作の派生値（`gemIndex`）だけを出力する（`GR-6`）

## テスト

```sh
npx vitest run tools/gem-pool/output.test.mjs   # 生成物の形（純粋関数）
npx vitest run tools/gem-pool                   # 収集・順位付けを含む gem-pool 全体
```
