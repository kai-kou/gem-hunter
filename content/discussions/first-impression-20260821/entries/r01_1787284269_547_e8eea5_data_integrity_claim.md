<!--entry
author: data_integrity
round: 1
kind: claim
ts: 2026-08-21T12:51:08+09:00
-->

# data_integrity: フィードバック⑦（一覧と詳細でスター数不一致）の分析

## 1. 不一致の原因（コード確認済み）

- **一覧（ダイジェスト）**: `tools/generate_gem_digest.mjs` が手動 / 非定期実行のバッチで
  Ecosyste.ms から取得し `public/data/daily-digest.json` に焼き込む静的スナップショット
  （`static-gem-digest.ts` が `import` で読む）。`generatedAt` は現物で `2026-08-20T16:56:03Z`
  （今日 2026-08-21 時点で 1 日前）。CI 自動実行なし（スクリプト冒頭コメントに明記）ため、
  実運用では **数日〜数週間単位で古くなりうる**。
- **詳細**: `get-repository-detail.ts` → `RepositoryQueryPort.findDetail` = GitHub API を
  `CachingRepositoryQuery` 経由でライブ取得（ADR 0005・TTL 300 秒）。
- したがって一覧と詳細は **設計上そもそも別ソース・別鮮度**（バッチ静的 vs ライブ 300 秒
  キャッシュ）であり、不一致は「バグ」ではなく **アーキテクチャ上の必然**。

## 2.「repository 名の誤解決」は事実誤認（実測で否定）。ただし別の真の欠陥を発見

依頼された前提（`react` → `react/react` は誤りで正しくは `facebook/react`）を実測で検証した結果、
**これは誤りではない**。

- Ecosyste.ms API 実測: `react` パッケージの `repository_url` も `repo_metadata.full_name` も
  両方とも `react/react`（`repo_metadata.stargazers_count: 247323`, `archived: false`）
- GitHub 実測（WebFetch）: `github.com/react/react` は 200 で実在し 247k star（一致）。
  `facebook/react` ではなく `react/react` が現在の正規ロケーション（2026-08 時点で react org へ
  移管済みと見られる）。
- `owner === repo` 形式の候補を機械検出したところ 294 件中 85 件ヒットしたが、サンプル確認した
  `eslint/eslint` `prettier/prettier` `webpack/webpack` `axios/axios` `lodash/lodash` 等は
  すべて実在の正しい自己名リポジトリ、`DefinitelyTyped/DefinitelyTyped` `babel/babel` は
  意図通りのモノレポ集約（複数パッケージが同一リポジトリを指すのは仕様どおり）。
  → **404 を生む欠陥ではない。今スプリントで対応すべき別 Issue も不要。**

### 発見した真の欠陥（未報告・出所の非同期）

`generate_gem_digest.mjs` の `toGem()` は 1 件の Gem を作る際に **2 つの異なる鮮度のフィールドを
無自覚に混在** させている:

```js
const repo = extractGithubFullName(pkg?.repository_url)       // npm registry 由来（比較的新鮮）
const stars = pkg?.repo_metadata?.stargazers_count             // Ecosyste.ms 独自クロール由来
```

`repo_metadata.last_synced_at`（Ecosyste.ms が GitHub をクロールした最終時刻）はパッケージごとに
バラつきが大きく、実測サンプル（候補プールからランダム 20 件）で:

| packageName | full_name | last_synced_at からの経過日数 |
|---|---|---|
| husky | typicode/husky | 0 日 |
| ts-jest | kulshekhar/ts-jest | 1 日 |
| gulp-sass | dlmanning/gulp-sass | 23 日 |
| grunt-contrib-clean | gruntjs/grunt-contrib-clean | **714 日** |
| gulp | gulpjs/gulp | **858 日** |
| node-sass | sass/node-sass | **858 日** |
| postcss | postcss/postcss | **859 日** |
| @babel/cli 等（babel/babel） | babel/babel | **974 日**（≈2.7 年） |

20 件中 6 件（30%）が **700 日超**（1.9〜2.7 年）Ecosyste.ms 側で未更新。つまり「一覧の star が
古い」の主因は **①自分たちのバッチが日次で回っていないこと** だけでなく、**②データ元
（Ecosyste.ms）自体のクロール鮮度が銘柄ごとに最大 2.7 年単位でバラつく** ことにもある。
`generatedAt`（バッチ実行時刻）を「as of」として案内しても、実際の値の鮮度はそれより古い
場合がある、という点は fix 案の精度に関わる注記として残す（今スプリントでの追加対応は不要、
将来 `repo_metadata.last_synced_at` を候補に持たせて個別表示する改善は別 Issue 候補）。

## 3. 4 案の評価

| 案 | NFR-3（トップは client JS 無し） | NFR-5（レート予算） | D-29（Ecosyste.ms 帰属・再配信規律） | ADR 0005（キャッシュ設計） | 総合 |
|---|---|---|---|---|---|
| **(1) 一覧の star をライブ取得に寄せる** | 直接違反はしない（SSR 内で fetch すれば JS 追加は不要）が、ADR 0014 §2.2 の「候補プールは静的 JSON のみ・ゼロクエリでサーバー状態を持たない」設計を破る。detail 用の `RepositoryQueryPort` を digest usecase にも配線する新規結合が要る（`GemDigestPort` と `RepositoryQueryPort` の分離を壊す） | 日次ダイジェストは同一 URL で edge cache されうる設計（ADR 0014 §2.2）だが、`?date=` バリエーションや初回キャッシュミス時に candidates 中 表示件数分（既定 5）の GitHub API 呼び出しが毎回発生しうる。`R-5` の逆算は「1 検索 = 1 API 呼び出し」前提（ADR 0005 追補・`SP-16`）で、ダイジェスト用の呼び出しは検討対象外のため予算の再逆算が要る | 影響なし（star はもともと数値のみで再配信禁止の対象は生テキスト） | `CachingRepositoryQuery` の TTL 300 秒に乗せれば軽減できるが、それでも「候補プールは静的・実行時 API 呼び出しゼロ」という ADR 0014 の根本設計を変える | **却下寄り**: スコープが 1 スプリントに収まらない設計変更（ADR 改訂が要る） |
| **(2) 一覧の表示から star を落とす** | 影響なし | 影響なし（呼び出しが減るだけ） | 影響なし | 影響なし | 実装コストは最小だが、比較検討という製品価値（`Gem Index` と並ぶ判断材料）を一覧から奪う。newcomer_ux 側の要望（#10: 一覧に数値が欲しい）とも逆行 |
| **(3) 鮮度を明示して仕様として説明する（推奨）** | 影響なし（テキスト追加のみ、JS 不要） | 影響なし | **相性が良い**: D-29 が既に要求する帰属表示（`AttributionNotice`）と同じ場所に「{生成日時} 時点のスナップショット」を併記でき、実装済みの `meta.generatedAt`（実測値あり・空でない）をそのまま使える | 影響なし。既存のバッチ/静的配信設計をそのまま維持 | **推奨**: 追加実装は UI 文言 + i18n ラベルのみ。ADR・NFR のいずれにも抵触しない。ただし §2 の注記どおり「生成日時」は必要十分条件ではなく Ecosyste.ms 側鮮度のバラつきまでは説明しきれない（それでも「一覧はスナップショット・詳細はライブ」という設計の説明としては十分） |
| **(4) 詳細側にも同じ出所の値を併記する** | 影響なし | 影響なし（GitHub 呼び出し追加なし） | 影響なし | 影響なし | 詳細ページはダイジェスト経由以外（検索結果経由）でも表示されるため、294 件の候補プールを毎回 detail 側でも読み込んで該当有無を調べる新規結合が必要（YAGNI寄り・detail の責務が `GemDigestPort` に染み出す）。得られる価値はダイジェスト経由の少数ケースのみ。費用対効果が低く**非推奨** |

## 4. 結論

- **推奨は (3)**: `daily-digest.tsx` の star 表示付近（または帰属表示と同じ箇所）に
  `meta.generatedAt` を使い「この一覧の数値は {日付} 時点のものです。最新の値は詳細ページでご確認
  いただけます」を追加する。実装コストは UI 文言 + i18n のみで、A-1〜A-6 相当のリスクも
  ADR/NFR 抵触もない。
- **「repository 名の誤解決」は今スプリント対応不要**（実測で欠陥ではないと確認済み）。ただし
  Ecosyste.ms 自体のクロール鮮度が銘柄ごとに最大 2.7 年ばらつく事実は (3) の文言設計時に
  「バッチ実行日 = 全銘柄の実際のデータ鮮度」ではない点として認識しておくべき（過剰な精度を
  文言で約束しない）。将来的に `repo_metadata.last_synced_at` を候補データに持たせて銘柄ごとの
  鮮度を出す改善は、価値はあるが本スプリントのスコープ外・別 Issue 候補。
