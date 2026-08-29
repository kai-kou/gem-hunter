# テスト戦略（TDD・SSOT）

> **このファイルは「何を・どの層で・どの道具でテストするか」の唯一の正本（SSOT）である。**（`R-11` の回答）
> **どう回すか（Red → Green → Refactor の規律）の正本は [`sprint-development-rules.md`](../rules/sprint-development-rules.md) `SD-2`** であり、本ファイルはその **具体化** にあたる。
> 層とディレクトリの正本は [アプリケーションアーキテクチャ](../03_design/architecture/application-architecture.md)。
>
> 対応要件: `NFR-23`（主要フローのテスト）/ `NFR-24`（外部 API のモック化）/ `NFR-25`（コマンド 1 つ・CI 実行）/ `NFR-26`（axe）/ `AC-10`
> 基準日: 2026-08-18（採用ツールのバージョン前提を含む。陳腐化したら `CP-2` に従い更新する）

---

## 1. 前提となる制約（ここから戦略が決まる）

| 制約 | 出典 | 戦略への影響 |
|---|---|---|
| 🔴 **`async` Server Component はユニットテストで描画できない** | [Next.js 公式テストガイド](https://nextjs.org/docs/app/guides/testing)（16.3 時点で「`async` コンポーネントは E2E を推奨」と明記） | データ取得を伴う画面の検証は **E2E に置く**。逆に **ロジックを `async` RSC の中に書かない**（ユースケースへ出す）ことがテスト容易性の条件になる |
| 外部 API に依存しない再現性が要る | `NFR-24` | ネットワークは **既定で遮断**。モックの位置は §4 で層ごとに決める |
| コマンド 1 つで実行でき CI で回る | `NFR-25` / `AC-10` | `npm test`（ユニット・結合）と `npm run test:e2e` の 2 本に固定する |
| 実行環境は Cloudflare Workers | `D-16` | 事業者バインディングに触れるアダプタだけ Workers ランタイムで検証する（§3 の任意層） |
| 🔴 **Workers ランタイムでしか観測できない振る舞い**（`RATE_LIMITER` binding 等） | `Issue #188`（PR #184 レビュー指摘・`next start` では binding が常に `undefined` でフェイルオープンする） | 既定の `npm run test:e2e`（`next start`）では踏めない。`playwright.workers.config.ts`（`wrangler dev` を webServer に使う）を **別コマンド**（`npm run test:e2e:workers`）として用意し、`e2e/workers/*.spec.ts` に置く（§8「Workers ランタイム E2E」） |

---

## 2. 道具（採用と役割）

| 道具 | 役割 | 備考 |
|---|---|---|
| **Vitest 4** | ユニット・結合の実行基盤 | 4.0 で Browser Mode が stable 化。既定は `jsdom`、UI の実ブラウザ検証が要る場合のみ Browser Mode を使う |
| **React Testing Library** | コンポーネントの振る舞い検証 | 実装詳細（内部 state・クラス名）ではなく **アクセシブルな役割・ラベル** で取得する（`NFR-10`〜`NFR-12` と同じ向き） |
| **MSW 2** | HTTP 境界のモック | 🔴 **ACL（`src/infrastructure/github/`）のテストでのみ使う**。上位層はフェイクのポート実装を使う（§4） |
| **Playwright** | E2E（`async` RSC・主要フロー） | 操作レビュー手順の写し。`SP-4` で導入済み（`e2e/*.spec.ts`） |
| **@axe-core/playwright** | 自動アクセシビリティ検査 | `NFR-26`。`e2e/a11y.spec.ts` で E2E の各主要画面に対して実行する |
| **@cloudflare/vitest-pool-workers**（任意） | `src/infrastructure/platform/` を Workers ランタイムで検証 | Vitest 4.1 以上が前提。**必要になるまで導入しない**（バインディングを実際に使い始めた時点で判断する） |

セットアップは Next.js 公式手順（`vitest` / `@vitejs/plugin-react` / `jsdom` / `@testing-library/react` / `@testing-library/dom` / `vite-tsconfig-paths`）に従う。独自の雛形を先に作らない。

---

## 3. 層とテストの対応（この表が分担の正本）

| 対象 | 種別 | 道具 | 置き場所 | 🔴 やらないこと |
|---|---|---|---|---|
| `src/domain/`（値オブジェクト・エンティティ・ドメインサービス・エラー） | ユニット | Vitest | `src/domain/**/*.test.ts`（併置） | モックを使わない（依存が無いのだから要らない） |
| `src/usecases/` | ユニット（フェイク注入） | Vitest | `src/usecases/*.test.ts` | MSW を使わない。ネットワークを触らない |
| `src/infrastructure/github/`（ACL・DTO 検証・mapper） | 結合 | Vitest + **MSW 2** | `src/infrastructure/github/*.test.ts` | 実 API を叩かない。**実レスポンスを縮めた固定 JSON** を fixture に置く |
| `src/infrastructure/platform/`（キャッシュ・レート制限） | 結合 | Vitest（必要なら Workers pool） | 併置 | 事業者 SDK を上位層でモックしない（境界はここで閉じる） |
| `src/ui/`（コンポーネント） | コンポーネント | Vitest + RTL | 併置 | スナップショットを主たる assert にしない |
| `app/`（同期 Server Component・Route Handler） | ユニット | Vitest | `app/**/*.test.tsx` | ロジックを持たせない（持たせたら設計側を直す） |
| `app/`（`async` Server Component・画面遷移・URL 状態） | **E2E** | Playwright | `e2e/*.spec.ts` | ユニットで描画しようとしない（公式に未対応・§1） |
| アクセシビリティ | E2E | Playwright + axe | `e2e/*.spec.ts` | 手動チェックだけで済ませない（`NFR-26`） |
| Workers ランタイム依存の振る舞い（`RATE_LIMITER` / KV / D1 / Durable Objects 等の binding） | **E2E（`wrangler dev`）** | Playwright（別 config） | `e2e/workers/*.spec.ts` | 既定の E2E（`next start`）で代替しようとしない（binding が常に `undefined` になり検証が空振りする・`Issue #188`） |

> **配置の規約**: テストは **実装と併置**（`foo.ts` の隣に `foo.test.ts`）。E2E だけ `e2e/` に置く。この 2 つは `tools/self_review_check.py` の `TEST_PATH_GLOBS` と一致している（TDD コミット順序の機械チェックが効く）。

### 3.1 検査層の死角カタログ（「通った」≠「満たした」の実例）

🔴 **各検査層は「何を見て・何を見ないか」が固定されている**。上表の「やらないこと」列だけでは把握しきれない、実インシデントで判明した死角をここに集約する。新しい死角を見つけたら追記する（新しい SSOT を作らない・`SP-10` レトロ #201 / #350 統合）。

| 検査層 | 見ているもの | 見ていないもの（死角） | 実例 |
|---|---|---|---|
| `tools/check_contrast.py` | `app/globals.css` の CSS カスタムプロパティの **宣言値** | ブラウザが実際に描画するコントラスト比。`:root` / `.dark` 固定パースのため、新規トークン・派生変数（`--tw-prose-*` 等）に追随しない | `SP-10`: フォーカスリングのコントラスト不足が宣言値レベルでは検出できなかった |
| E2E（Playwright）の構造チェック | DOM 属性・スタイルの **構造**（例: `box-shadow !== 'none'`） | 実際に描画された色・コントラスト比そのもの | `SP-10`: `box-shadow` が「ある」ことは確認できても、色のコントラストは見ていない |
| Lighthouse / axe | 静的な DOM 構造・ARIA 属性 | `:focus-visible` は自然なキーボード操作でしか発火せず、自動化ツールは発火させない | `SP-10`: フォーカスリング自体が axe/Lighthouse の検査対象に上がらない |
| Playwright `setViewportSize` | ブラウザのビューポート寸法 | OS/ブラウザの `devicePixelRatio` には依存しない（実機の見え方とズレうる） | `SP-10` |
| Next.js 16.3.1 の `viewport` export | 明示的に指定した viewport meta | `viewport` export が無くても Next.js が既定の meta タグを自動出力するため、「未指定 = meta 無し」という前提が崩れる | `SP-10` |
| SSR (`generateMetadata`) | サーバー側で確定した値（例: タイトル） | クライアント側の hydration 後処理（`SetDocumentTitle` 等）が SSR の値を上書きする経路 | `SP-10`: `generateMetadata` で設定したタイトルをクライアント側処理が hydration 後に上書き |
| `check_architecture_boundaries.py` | import 方向のみ | 「正本を自称する表」（`application-architecture.md` §2 ポート一覧・`domain-model.md` §2.1 等）に実装側の要素（新規ポート・新規ドメイン語）が追記されているか | `SP-19`: `GemIndexPort.search()` 追加漏れ・`GemPoolEntry` 等の新規ドメイン語が `domain-model.md` に未反映のまま `npm run check` 全 PASS（#450 に機械検査の起票あり） |

> **運用**: 新しいスプリントで検査層のすり抜けに気づいたら、この表に 1 行追記する（レトロスペクティブの Try Issue 化とは別に、カタログ自体を更新する）。

---

## 4. テストダブルの方針（優先順位を固定する）

```
① フェイクのポート実装（手書き）  ← 既定。ユースケース・上位層はこれだけ
② MSW（HTTP 境界）              ← ACL のテストに限る
③ vi.mock（モジュール差し替え）  ← 🔴 最終手段。自作モジュールには使わない
```

- ポートのフェイクは `src/domain/ports/` の interface に **型で適合させる**（`satisfies`）。契約が変わればテストが壊れるので、乖離が検知できる。
- 🔴 **`vi.mock` で自作モジュールを差し替えたくなったら、それは依存性注入ができていないサイン**。テストではなく設計を直す。
- 時刻・乱数は `ClockPort` 経由にする（アーキテクチャ §2）。`Date.now()` を実装に直書きしない。

---

## 5. TDD の回し方（二重ループ）

```
外側（受け入れ）: user-story-map §5.3 の「操作レビュー」手順を E2E に写す → Red
   └─ 内側（ユニット）: Red → Green → Refactor を分単位で繰り返す
外側を再実行 → Green になったらスプリント完了（SD-1 / SD-2）
```

1. **着手時**: 該当スプリントの操作レビュー手順を、そのまま E2E テスト名にする（手順 1 行 = 1 assert が目安）。この時点では **落ちてよい**（外側の Red）。
2. **内側**: 値オブジェクト → ユースケース → ACL → UI の順に、失敗するユニットテストを先に書く。
3. **コミット順序**: `test:`（テストのみ）→ `feat:`（実装）の順に分けてコミットする。順序違反は `tools/self_review_check.py` が Warning で検知する。
4. **完了判定**: 外側の E2E が緑 + `npm test` が緑 + CI 緑（`SP-4` 以降・`SD-2` 完了条件）。

> ⚠️ **`SP-1`〜`SP-3` の緩和**（`sprint-development-rules-detail.md` §2）: テスト基盤が揃うのは `SP-4`。それまでは「テストを書ける対象（値オブジェクト・mapper・純粋関数）から書く」に緩和する。**緩和は「書かない」ではない。**

---

## 6. 何をテストするかの下限（トレーサビリティ）

🔴 **`AC-n` は必ず 1 つ以上の自動テストに対応づける**（`AC-10` の要求）。対応が無い `AC` を残したまま「完了」と言わない。

| 受け入れ基準 | 主たるテスト層 |
|---|---|
| `AC-2`（検索・URL 状態の再現） | E2E |
| `AC-3`（一覧表示項目） | E2E + UI コンポーネント |
| `AC-4`（詳細ページ・直接アクセス・復帰） | E2E |
| `AC-5`（詳細 7 項目・Not Found） | E2E + ACL（mapper の対応表・ドメインモデル §2.2） |
| `AC-6`（詳細ページからトップへ戻れる） | E2E |
| `AC-7`（ページネーションで 2 ページ目以降） | E2E + 値オブジェクト（`AR-2` ソート / `AR-3` 件数も同じ層で見る） |
| `AC-8`（読み込み中・0 件・エラーの判別） | ACL（ステータス → ドメインエラー変換）+ E2E |
| `AC-9`（レスポンシブ・キーボード完走） | E2E + axe（`NFR-11` / `NFR-26`） |
| `AC-12`（認証済みでも private が表示されない・`NFR-33`） | 単体（キーワードの修飾子構文の拒否・`is:public` の付与・検索結果マッパーでの `private: true` 除外と `totalCount` 保持・詳細応答が `private: true` のときの「見つからない」扱い）+ E2E |
| `NFR-5` / `NFR-17`（キャッシュ） | 結合（`X-Cache-Status` の assert・[Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §4.5）+ E2E |

🔵 **自動テストの対象外**: `AC-1`（Next.js v16 + App Router で構築されている）と `AC-11`（README の記載）は構成・文書の確認事項であり、テストではなくセルフレビューのチェックリストで見る（対応が無いことを明示しておく）。

**カバレッジ率のゲートは設けない**（数値を追うと薄いテストが増える）。代わりに上表の対応づけを PR 本文でチェックする。

🔵 **テストでは届かない領域（入力空間・データ分布の境界）**: 実装もテストも正しいのに、実際の入力分布がテストの想定より広いために起きる欠陥は、上表のような自動テストの対応づけでは検出できない（変異テストで壊しても、その入力自体がテスト実行中に一度も生成されないため落ちない）。この領域は自動テストではなく実測で埋める。**入力境界表の作成・敵対的入力の実機投入・実データでのコーパス数え直しの正本は [`sprint-development-rules.md`](../rules/sprint-development-rules.md) `SD-1` 完了条件**（本ファイルでは重複定義しない）。

---

## 7. 禁止事項

- 🔴 テストを **スキップ・無効化・quarantine** して緑にする（`SD-2`）
- 🔴 仕様と矛盾するテストを通すために、正しい実装を黙って書き換える（`intent-gate-rules.md`・権威順は ユーザー明示 > 仕様 > テスト > 現行コード）
- 🔴 **実行せずに「テストが通る」と報告する**（L-113。実結果でのみ断定する）
- 🔴 ある挙動の回帰点を **否定アサーションだけ**（`expect(fn).not.toHaveBeenCalled()` 等）で守る。実装をまるごと no-op にしても緑のままになり検証が空振りする（vacuous）。同じ挙動を **positive に固定するテストを必ず 1 本併置する**（例: 「正常データでは警告が出ない」を置くなら「壊れたデータでは警告が出る」も置く）
- 🔴 「有無に依存しない不変条件」を、対象が **0 件でも成立する形のまま** 置く（実装は正しいのにフィクスチャが対象状態を一度も生成せず、テストが要件を避けて書かれた形で緑になる。変異テストでも検出できない — 壊す対象がそもそも実行中に一度も動いていないため）。不変条件テストを書くときは、その不変条件が意味を持つ状態（対象が 1 件以上存在する状態）を **最低 1 ケース明示的にアサートしてから** 不変条件を検証する（例: `expect(badges.first()).toBeVisible()` で前提を固定してから並び順を検証する）
- 🔴 **コード内コメントで「唯一」「必ず」「常に」等の不変条件を主張しておきながら、それを検証するテストを書かない**（実装と主張が乖離していても、テストが架空の仮定を信じて書かれるため、実行時に初めて矛盾が顕在化する）。「`role="status"` はこの要素だけが持つ」等の不変条件をコメントで追加した場合は、同じ PR でその不変条件をテスト（ユニット or E2E の assert）で検証することを必須とする（Issue #206）
- 🔴 **テストの期待値に実装側の定数・関数を参照しない（リテラルで書く）**。実装から import した値をそのまま期待値に使うと、実装を巻き戻しても両者が一致し続ける自己参照（トートロジー）になり、退行検知力がゼロになる（Issue #154・実測: `CACHE_SCHEMA_VERSION` を巻き戻しても 20 tests passed のまま）
- 🔴 **新しく書いたテストは、守りたい振る舞いを 1 箇所壊して赤くなることを確認してから完了とする**（Issue #154）。TDD の Red → Green と実質同じだが、**既存実装に後からテストを足す場合**（Red を通らないケース）はこの確認が抜け落ちやすいので明示的に行う。E2E はクライアント側実装や外部ツールの挙動（Playwright の `setViewportSize` 等）に検証がマスクされることがあるため、SSR/meta export のようなサーバー専用の戻り値は単体テストで直接呼んでアサートする。ガード条件が絡む複雑な条件式（`A and B` のような複合アサーション）は、**条件の一部だけを変異させても他の条件が必ず結果を確定させてしまう** ケースがあるため、複数の異なる変異パターンを試す（実測: `state_text` 側のガードが常に真になり `all_closed` 側の変異が一度も検出されなかった事例・#154 コメント参照）
- 🔴 **複数レイヤー（ランタイム本体・子プロセス・ブラウザコンテキスト・テスト実行プロセス）にまたがる設定変更（TZ・ロケール・ネットワーク遮断等）は、「設定した」ことと「全レイヤーで効いている」ことの間にギャップが生まれやすい**。着手前に「この設定はビルドプロセス / 実行時プロセス / 子プロセス / ブラウザコンテキストのどのレイヤーに効くべきか」を列挙し、**各レイヤーの実効性を固定するテスト（`process.env.X` の直接アサーション等）を実装と同じ PR で書く**（例: `tools/env-tz.test.mjs` の TZ アサーション）。1 レイヤーだけ設定して他が未検証のまま完了としない（Issue #175 実装時に Playwright ランナー自身の TZ 固定が書き漏れ、Layer 1 セルフレビューまで気づかれなかった実例・#665）
- ユニットテストから実ネットワークへ出る（`NFR-24`）
- スナップショットを主たる assert にする（変更検知にはなるが仕様を語らない）
- `getByTestId` を第一選択にする（役割・ラベルで取れないなら、それはアクセシビリティの問題でもある）

---

## 8. コマンド（`NFR-25`）

```bash
npm test                 # Vitest（ユニット + 結合）
npm run test:e2e         # Playwright（E2E + axe。e2e/a11y.spec.ts を含む）
npm run test:e2e:workers # Playwright（Workers ランタイム依存の E2E。wrangler dev 経由・下記参照）
npm run check             # bash tools/run_checks.sh。Lint/型/vitest/E2E 等をまとめて実行し、
                           # PR 本文に貼る Markdown サマリー表を末尾に出力する
```

### E2E の実行方法

- **ローカル既定**: `npm run test:e2e` を実行すると、`playwright.config.ts` の `webServer` が
  ① E2E 用スタブ GitHub API（`node e2e/stub/server.mjs`）と ② `npm run build && npm start -- --port 3100`
  （`GITHUB_API_ORIGIN` をスタブへ向けたアプリ本体）を **自動起動** してから実行する。手動でサーバーを
  立てる必要はない
- **プレビュー URL に対して実行**: `E2E_BASE_URL` を渡すと `webServer` の自動起動をスキップし、
  そのまま指定 URL（例: PR プレビュー環境の Cloudflare Workers URL）に対してテストを実行できる

  ```bash
  E2E_BASE_URL=https://pr-123.example.workers.dev npm run test:e2e
  ```

  🔴 **現状の制約**: 経路自体は用意してあるが、プレビュー環境（Cloudflare Workers）からローカルの
  E2E スタブ GitHub API（`e2e/stub/server.mjs`）へは到達できない。プレビュー先の spec が参照する
  フィクスチャ（`octostub/octo-widgets` 等）は実 GitHub 上には存在しないため、現状のまま
  `E2E_BASE_URL` でプレビューへ実行すると全件失敗する。**スタブに到達できる公開エンドポイントを
  用意できるまでは、主経路は上記の `webServer` 自動起動（ローカル完結）とする。**
- **外部ネットワーク非依存**（`NFR-24`）: `async` Server Component は実 GitHub API ではなく
  上記スタブに対して通信するため、E2E の実行中に実ネットワークへは一切出ない。**加えて、スタブが
  返す HTML フィクスチャ内のサブリソース**（`<img src>` / `<script src>` / `<link href>` /
  `<iframe src>` / `srcset` / CSS `url()`）**も外部 URL であってはならない**。過去に README
  フィクスチャへ外部 URL の `<img>` を混入させた際、`page.goto()` がホスト到達不可のまま
  1 回あたり約 12.6 秒ブロックされた実測があるため、`tools/check_e2e_stub_external_urls.py`
  （`tools/run_checks.sh` に配線済み）が機械検証する
- **所要時間の目安**（`npx playwright test` 実行・テスト 112 件・全 pass。計測条件はコールド =
  `.next` / `.open-next` を削除した直後の初回実行、ウォーム = 直前にビルドキャッシュがある状態での
  再実行）: コールドで約 2 分 20 秒（139.7s）、ウォームで約 2 分 4 秒（123.7s）。ビルド自体は
  コールド約 70 秒・ウォーム約 8 秒まで縮むが、テスト本体（合計 85.6s）が支配的なためコールド/
  ウォームの差は小さい。再計測する場合は上記コマンドを同条件（テスト削除・追加なし）で実行し、
  この表を書き換える

### Workers ランタイム E2E（`Issue #188`）

`playwright.config.ts`（既定）は `next start`（Node.js ランタイム）でアプリを起動するため、
`rateLimiterBinding()`（`src/infrastructure/platform/cloudflare-bindings.ts`）は常に `undefined` を返し
フェイルオープンで即 return する（Workers 実行環境の外）。`RATE_LIMITER` binding のように **Workers
ランタイム上でしか観測できない振る舞い**は、既定の E2E では 1 つも守れない。

- 設定は `playwright.workers.config.ts`（別ファイル・既定の `playwright.config.ts` とは分離）。
  webServer は `npx wrangler dev`（workerd・ローカル実行）で、`env.RATE_LIMITER` / `env.ASSETS` を
  実際に配線する（起動前に `tools/ensure_open_next_assets.mjs` で `.open-next` の鮮度チェックと
  必要なビルドを行う。**src の変更は自動検知しない** ため、`app/` `src/` を触った後にこのコマンドを
  走らせる場合は `npx opennextjs-cloudflare build` で明示的に再ビルドすること）
- テストは `e2e/workers/*.spec.ts` に置く（既定の `e2e/*.spec.ts` とは別ディレクトリ）
- 実行: `npm run test:e2e:workers`
- 🔴 **`tools/run_checks.sh` には未配線**（既定の E2E に比べ `wrangler dev` の起動コストが追加で乗るため。
  実行時間の見積もりが済み、既定 CI 経路に混ぜる判断が付いたら配線する）
- ⚠️ **プレビュー環境（Cloudflare Workers 実機）に対する secret 供給ギャップ**（`Issue #187`）は本節の
  対象外。本節はあくまで **ローカル `wrangler dev` での binding 検証** であり、PR プレビュー版
  （`wrangler versions upload`）に secret / binding が実際に届くかどうかの検証は別問題として残る

### スタブ API のキーワード規約

`e2e/stub/server.mjs` は `e2e/fixtures/repos.json` を配信するだけの薄いスタブ。検索クエリ（`q`）または
リポジトリ名・owner 名に以下のキーワードを **部分一致** させることで、テストから任意の応答を引ける。

| キーワード | 挙動 |
|---|---|
| （通常のキーワード） | `repos.json` から複数件返す（1 ページ目 3 件・2 ページ目 2 件。`total_count` は 2 ページ以上になる値） |
| `zero-hits` | `total_count: 0` / `items: []`（0 件表示の検証用） |
| `upstream-error` | HTTP 500（上流エラー表示の検証用） |
| `rate-limit` | HTTP 403 + `x-ratelimit-remaining: 0` + `x-ratelimit-reset`（レート制限表示の検証用） |
| `not-found`（詳細 API の repo 名 or owner のみ） | HTTP 404（詳細ページの Not Found 表示の検証用） |

### CI の分担（二層構成・`D-42`）

> 🔴 **テストブロッキングの役割は 2 層に分かれる**（2026-08-24・`D-42`・Issue #543）。
>
> **層 1（GitHub Actions・自動）**: `.github/workflows/quality-checks.yml` が `push`（`main`）と `pull_request`
> のたびに **Vitest（ユニット）** を自動実行する（あわせて Prettier `format:check` / ESLint `lint` /
> `tsc --noEmit` も同じ run で走る）。権限は `contents: read` のみで、**自動マージもデプロイも行わない**。
>
> **層 2（セッション実行・手動）**: 🔴 **Playwright（E2E）と Lighthouse は CI 対象外**（E2E は実測 262 秒 / 112 件・2026-08-24 JST +
> ブラウザ導入コストがあり PR ごとの待ち時間に見合わないため・`D-42`）。この 2 つは
> **`bash tools/run_checks.sh`（= `npm run check`）が担当する**（`E-12` / `SP-4`）。PR 作成前にセッションが
> これを実行し、結果のサマリー表を PR 本文に貼る運用は **廃止しない**（`pre-pr-create-check.sh` のブロックも維持）。
> `SKIP_E2E=1 bash tools/run_checks.sh` で E2E だけを明示的にスキップできるが、スキップした事実は
> サマリー表に `SKIP` として必ず残る（黙って緑にしない）。
>
> 🔵 **ワークフローの再導入は対応済み**（`D-42` / Issue #543）。🔴 **ただし解禁されたのは品質チェックだけで、
> 本番・プレビューのデプロイに Actions は使わない**（発火点は Workers Builds・`D-31` / `D-32`）。

### 8.1 赤くなったときの判断手順（flaky レジストリ）

`npm run check` が赤くなったら、まず [`docs/04_development/flaky-tests.md`](./flaky-tests.md) を確認する。
**該当エントリが載っていれば** 既知の flaky として扱ってよい。**載っていなければ本物の失敗として扱う**
（推測で「flaky だろう」と片付けてリトライに逃がさない・`sprint-development-rules.md` `SD-2` の
「テストのスキップ・無効化で緑にしない」を骨抜きにしないため）。

---

## 9. 完了・成功の定義

- [ ] 追加した振る舞いに **先に書かれたテスト** がある（コミット順序が `test:` → `feat:`）
- [ ] 該当スプリントの操作レビュー手順が E2E に写っている（`SP-4` 以降）
- [ ] `npm test` が **実行済みで** 緑（結果を見てから報告する）
- [ ] 外部 API へのアクセスがテスト実行中に発生しない
- [ ] 触れた `AC-n` が §6 の対応づけを満たしている

---

## 10. 参照

| ドキュメント | 関係 |
|---|---|
| [`sprint-development-rules.md`](../rules/sprint-development-rules.md) `SD-2` | TDD の規律（本ファイルはその具体化） |
| [アプリケーションアーキテクチャ](../03_design/architecture/application-architecture.md) | 層と依存規則（テスト容易性の前提） |
| [ドメインモデル](../03_design/data-model/domain-model.md) | 値オブジェクト・ACL 変換表（テスト対象の仕様） |
| [ユーザーストーリーマップ](../02_requirements/user-story-map.md) §5.3 | 操作レビュー手順（E2E の元ネタ） |
| [Next.js 公式テストガイド](https://nextjs.org/docs/app/guides/testing) | `async` RSC の制約の一次情報 |
