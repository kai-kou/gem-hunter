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

---

## 2. 道具（採用と役割）

| 道具 | 役割 | 備考 |
|---|---|---|
| **Vitest 4** | ユニット・結合の実行基盤 | 4.0 で Browser Mode が stable 化。既定は `jsdom`、UI の実ブラウザ検証が要る場合のみ Browser Mode を使う |
| **React Testing Library** | コンポーネントの振る舞い検証 | 実装詳細（内部 state・クラス名）ではなく **アクセシブルな役割・ラベル** で取得する（`NFR-10`〜`NFR-12` と同じ向き） |
| **MSW 2** | HTTP 境界のモック | 🔴 **ACL（`src/infrastructure/github/`）のテストでのみ使う**。上位層はフェイクのポート実装を使う（§4） |
| **Playwright** | E2E（`async` RSC・主要フロー） | 操作レビュー手順の写し。`SP-4` で導入する |
| **@axe-core/playwright** | 自動アクセシビリティ検査 | `NFR-26`。E2E の各主要画面で実行する |
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

> **配置の規約**: テストは **実装と併置**（`foo.ts` の隣に `foo.test.ts`）。E2E だけ `e2e/` に置く。この 2 つは `tools/self_review_check.py` の `TEST_PATH_GLOBS` と一致している（TDD コミット順序の機械チェックが効く）。

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
| `NFR-5` / `NFR-17`（キャッシュ） | 結合（`X-Cache-Status` の assert・[Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §4.5）+ E2E |

🔵 **自動テストの対象外**: `AC-1`（Next.js v16 + App Router で構築されている）と `AC-11`（README の記載）は構成・文書の確認事項であり、テストではなくセルフレビューのチェックリストで見る（対応が無いことを明示しておく）。

**カバレッジ率のゲートは設けない**（数値を追うと薄いテストが増える）。代わりに上表の対応づけを PR 本文でチェックする。

---

## 7. 禁止事項

- 🔴 テストを **スキップ・無効化・quarantine** して緑にする（`SD-2`）
- 🔴 仕様と矛盾するテストを通すために、正しい実装を黙って書き換える（`intent-gate-rules.md`・権威順は ユーザー明示 > 仕様 > テスト > 現行コード）
- 🔴 **実行せずに「テストが通る」と報告する**（L-113。実結果でのみ断定する）
- ユニットテストから実ネットワークへ出る（`NFR-24`）
- スナップショットを主たる assert にする（変更検知にはなるが仕様を語らない）
- `getByTestId` を第一選択にする（役割・ラベルで取れないなら、それはアクセシビリティの問題でもある）

---

## 8. コマンド（`NFR-25`）

```bash
npm test              # Vitest（ユニット + 結合）。CI ではこの 1 本が緑であること
npm run test:e2e      # Playwright（E2E + axe）
```

CI は PR ごとに両方を実行する（`E-12` / `SP-4`）。

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
