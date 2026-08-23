<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: Gem 候補一覧が検索結果のバッジ付き候補を取りこぼす問題の対応方針

- 議題ID: `gem-list-match-20260823`
- 論点: 飼い主フィードバック（Issue #453）: (F-1)『この検索語の Gem 候補を一覧で見る』を押すと、検索結果には Gem マークが複数付いているのに一覧は 1 件しか出ない。(F-2) 検索結果タイトルの下に Gem マークの説明を端的に含めてほしい。

【一次調査で判明した事実（実データ計測済み）】検索結果のバッジは GemIndexPort#lookup（= 候補プールへの所属照会のみ・検索語と無関係）で付く。一方 Gem 一覧は GemIndexPort#search（= repositoryFullName と packageName を単語境界で割ったトークン列に対する全語 AND 一致・D-37）で絞る。q=next.js は tokenizeQuery で ['next','js'] に割れ、npmjs-org シャードでの AND 一致は vercel/next.js の 1 件だけ（'next' 単独なら 19 件）。緩和（selectMostSelectiveToken）は『全語 AND が 0 件のとき』にしか発火しないため、1 件ヒットしたこのケースでは効かない。さらに chimurai/http-proxy-middleware は GitHub 側が description（'…for connect, express, next.js and more'）でヒットさせたもので、名前照合では原理的に一覧へ出ない（プールには載っているのでバッジは付く）。

【関連実装】app/[locale]/page.tsx（検索結果・GemListLink を結果一覧の上に置く / lookupGemIndexes を検索結果 fullName に対して引く）、app/[locale]/gems/page.tsx（一覧・searchGemsUseCase）、src/usecases/search-gems.ts、src/domain/model/gem-keyword.ts（照合規則の正本）、src/infrastructure/platform/static-gem-index.ts（2 段遅延構築: プール約 82ms / 検索インデックス追加 122ms・cold 実測 2.78s）、src/ui/repository-list.tsx（gemBadgeNote は一覧の末尾に 1 回だけ描画）、src/ui/gem-badge.tsx、messages/{ja,en}.json（home.gemBadge.label/srHint/note・home.gemListLink.label・gems.*）。

【制約】D-36（バッジは並び順を変えない注釈・sort=gem-index は復活させない / 印が付かないことが低評価を意味しない旨の注記は必須）、D-37（絞り込みの照合は repo 名・パッケージ名の単語境界一致のみ・部分一致は入れない / 緩和は 1 段だけ・あいまい一致に広げない）、D-38（レジストリ別静的シャード + isolate 内メモリ索引・DB を持たない）、F-01（クエリ語数上限 16・CPU 枯渇防止）、F-02（Gem 一覧に GitHub 検索 API の 50 ページ上限を適用しない）、F-05（取得失敗を 0 件に潰さない）、F-14（照合不能クエリはポート呼び出し前に 0 件へ倒す）、NFR-3（クライアント JS を増やさない）、NFR-12/13（a11y・見出し階層・色だけで意味を伝えない）、INF-2（Cloudflare Workers の CPU/コスト制約）、ARCH（ドメイン層はフレームワークに依存しない・app は infrastructure を直接 import しない）、GitHub 検索 API は認証済みで 30 req/min・1 クエリ最大 1000 件。

【争点】A) 一覧の母集団をどう定義し直すか — 案1『今の検索結果（GitHub Search）のうちプールに載っているものを Gem Index 順に並べる』= バッジと定義が完全一致するがプール全体からの発見力を失い GitHub API 依存とレート枠消費が増える / 案2『プールベースのまま緩和条件を見直す（AND のヒット数が閾値未満なら 1 語緩和へ倒す等）』= 既存設計と D-37 を保つが chimurai/http-proxy-middleware のような description ヒット分は依然出ない / 案3『ハイブリッド（検索結果の Gem を必ず含めつつプール名照合の結果も出す）』= 期待に最も近いが 2 系統のマージ・並び順・ページングの整合が要る。どれを採るか、成果物がどう変わるかを比較し、ユーザー確認に出す 2 択（推奨つき）まで落とす。B) 緩和規則を変える場合の具体（発火条件・段数・注記文言・D-37 の書き換えが要るか / next.js のような『.js 付き製品名』を特別扱いせず一般規則で救えるか）。C) 期待のズレを UI 側で埋める手当（導線ラベル・一覧の見出し・注記で『この一覧はパッケージ名/リポジトリ名の一致で絞っている』ことをどう伝えるか / 0 件・少数件のときの導線）。D) F-2 の設計（検索結果見出し直下に置く説明文の文言（ja/en）・既存 home.gemBadge.note との関係＝重複を作らないか・末尾注記を残すか移すか・描画条件（バッジが 1 件も無いときも出すか）・a11y と見出し構造・E2E での固定方法）。E) パフォーマンスとリスク（採用案が cold start・CPU・レート枠に与える影響 / 既存 E2E・単体テストのどれが壊れるか / SP-18 で出荷済みのバッジ経路を回帰させないか）。
- 参加者: `search_semantics`, `arch_perf`, `ux_writer`, `docs_trace`
- 投稿数: 4
- 更新: 2026-08-23T10:04:14+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `docs_trace` — 主張
<sub>2026-08-23T10:03:03+09:00</sub>

# docs_trace 矛盾検出レポート

## 検証対象: D-36/D-37/D-38 と既存ドキュメントの整合性

### A1. **D-36（バッジ + 検索語連動 Gem 一覧）の矛盾**

#### 🔴 メッセージ層の不整合

| 不整合点 | 発見箇所 | 現状 | spec 要件 |
|---------|---------|------|----------|
| **A. 検索結果見出し下への Gem 説明** | spec §2 F-2 / `output_verbosity_rules.md` | `messages/ja.json` に該当キーがない | 「見出し直下に Gem 印説明を 1〜2 文で載せ、既存 home.gemBadge.note との重複を整理」が未着手 |
| **B. 注記文言の配置** | `messages/ja.json`:`gems.empty` vs `home.gemBadge.note` | 両方に「評価が低いことを意味しない」と重複記載 | D-36「見出し直下の説明に統合し、既存末尾注記の重複削減」→ 配置分離のみで統合されていない |
| **C. 検索結果の見出し構造** | spec §4 D-F / user-story-map.md `SP-18` 操作レビュー手順 | 見出しレベル（h1/h2/h3）が messages に記載なし。e2e の `GEM_LIST_HEADING_ID` は `gems-heading`（Gem 一覧用）で、検索結果見出しとの使い分けが不明 | `SDN.1` 確認: 見出し階層・a11y（NFR-12）と連動すべき |

#### 🟡 E2E テストとの矛盾

| 箇所 | テスト期待値 | 仕様書記載 |
|------|------------|----------|
| sp-18.spec.ts step 2 | 「並び順がスタブ返却順（関連度順）のまま」 = D-36 の中核制約 | ✅ 記載あり（D-36 の constraint として） |
| sp-18.spec.ts step 3 条件②③ | **バッジ件数 > 0 の場合のみ** 注記を 1 回だけ表示 | 🔴 messages の `gemBadge.note` は常に出現する可能性（`min(badgeCount, 1)` 式が messages 生成時に機械検証されていない） |

### A2. **D-37（照合規則 + 緩和）の矛盾**

#### 🔴 照合規則の詳細が分散

| 規則 | 記載先 | 問題点 |
|------|-------|-------|
| 単語境界一致の定義 | `src/domain/model/gem-keyword.ts`（実装） | 📍 仕様書 prd.md / messages には **記載なし** → ユーザーに見える `gems.description` / `gems.unmatchableQuery` の記述が実装と乖離の可能性 |
| 緩和条件（全語 AND = 0 → 1 語へ）| spec + sp-19.spec.ts | messages の `gems.relaxedNotice` テンプレート `{token}` は置換対象として定義されているが、**緩和が発火する条件「全語 AND が 0 件のとき」が messages に明記されていない** |
| 日本語-ASCII 混合・非 ASCII 処理 | sp-19.spec.ts コメント + `gem-keyword.ts` | messages の `gems.unmatchableQuery` が「日本語だけの検索語では候補を絞り込めません」と述べるが、仕様本体（prd.md）には **この制約が受け入れ基準として記載されていない** → AC-n 対応不明 |

#### 🟠 「母集団定義」の仕様化

| 項目 | 現状 | 要件 |
|------|------|------|
| レジストリ別成層化の具体値 | `D-37(1)` に「各レジストリから被依存数降順で同数を取る固定枠」と定義 | messages に「12 のパッケージレジストリ」と記載（✅）だが、**各レジストリから何件取るか** の枠の値が messages に **記載なし** |
| 汚染フィルタ・repo 単位 dedupe | `D-37(1)` の内容だが詳細未確認 | messages に関連記述なし |

### A3. **D-38（レジストリ別シャード + メモリ索引）の矛盾**

#### 🔴 配信データの出典表記が messages と乖離

| 項目 | sp-19.spec.ts 実装 | messages 記載 | 矛盾 |
|------|------------------|-------------|------|
| 出典情報の読み込み元 | `public/data/gem-index/index.json` から `source` / `sourceUrl` / `license` を動的読み込み（ハードコード禁止） | `gems.description` に「12 のパッケージレジストリ」と記載のみ | **出典 URL・ライセンス（CC BY-SA 4.0）が messages に固定値として記載されていない** → 配信元変更時にメンテが漏れうる |

#### 🟡 CPU 予算の記録

| 要件 | 記載先 | 状態 |
|------|-------|------|
| `limits.cpu_ms` の段階的引き上げ（50→200→400） | infrastructure/cloudflare-infrastructure.md + adr/0014 | **messages には記載なし**（当然ながら、ユーザー向け UI メッセージではなく内部制約） |

### B. messages キーの不足・追加要件

#### 必須追加キー（D-36 / D-2（見出し下説明））

```json
{
  "search": {
    "gemExplanation": {
      "heading": "（新）見出しレベル (h2)",
      "text": "（新）「この一覧に Gem マークが複数ついているのに Gem 一覧に 1 件しか出ないのはなぜ？」への説明（1〜2 文）"
    }
  }
}
```

#### 拡張が必要なキー（D-37 照合規則の明記）

| キー | 現状 | 必要な追加情報 |
|------|------|--------------|
| `gems.description` | 「過小評価度が高い順」のみ | 🔴 「**パッケージ名・リポジトリ名の英数字トークン一致で絞り込む**」（照合規則の一行説明） |
| `gems.unmatchableQuery` | 「日本語だけでは…」 | 🔴 「…**単語境界一致のため**…」（理由の明記で回帰を防ぐ） |
| `gems.relaxedNotice` | テンプレート | 🔴 「**すべての語を含む** Gem 候補が無かったため…」（緩和発火条件を明記） |

### C. prd.md との接続不足

#### 🔴 受け入れ基準 AC-n が D-36/D-37/D-38 を捕捉していない可能性

spec による「争点 D の設計」に「描画条件・見出し構造・a11y 対応」が含まれるが、prd.md の現行 AC-n（AC-1〜AC-12）にはこれらが **明示的に記載されていない**。

確認要件:
- AC-13 以降で「Gem バッジ・一覧・説明文」の受け入れ条件が定義されているか
- NFR-12/13（見出し・a11y）が「バッジ・一覧機能」と連動しているか

### D. open-questions.md における D-36/D-37/D-38 の記載状況

🔴 **open-questions.md 内に D-36/D-37/D-38 の独立した見出しセクション（`### D-36` 等）が見当たらない**。

- user-story-map.md が「詳細は [`open-questions.md`](./open-questions.md) `D-36`〜`D-38`」と参照しているが、該当セクションが実ファイルに存在しない可能性
- D-36 の一部内容（「バッジは並び順を変えない」「sort=gem-index は復活させない」）が sp-18.spec.ts のコメントに先行実装されている
- D-37 の照合規則が `src/domain/model/gem-keyword.ts` にコード形式で実装済みだが、**仕様書 prd.md の AC-n との対応が不明**

---

## 矛盾整理（アクション順）

### 必須：messages ファイル

1. **ja.json / en.json** に下記キーを追加
   - `search.gems.explanation` （検索結果見出し直下）
   - `home.gemBadge.note` を「末尾注記」から「見出し下説明」へ配置変更し、重複を削減

2. **gems.description** に照合規則を 1 文で追記（トークン / 単語境界 / 英数字）

3. **gems.relaxedNotice** の条件文を明確化（「全語一致が 0 件の場合」）

### 必須：prd.md

4. AC-13+ で「Gem バッジ / 一覧 / 説明文」の受け入れ条件を明示
5. NFR-12/13 と「バッジ・一覧」の紐付けを確認

### 必須：open-questions.md

6. D-36/D-37/D-38 の独立セクション（あるいは統合セクション）を追加し、**決定内容を明文化**（現在は spec.json のみに記載）

### オプション：user-story-map.md の SP-18/SP-19

7. 操作レビュー手順の見出しレベル・焦点順序を `messages` の階層と同期

### `arch_perf` — 主張
<sub>2026-08-23T10:03:24+09:00</sub>

## 結論（先出し）

**案2（プールベースのまま緩和条件を見直す）を推す。案1は却下、案3は「全件取りこぼしなく」は実現不可能（部分実装しかできない）。**

理由は一言で言うと: 案1/3 が要求する「GitHub Search API 呼び出しを `/gems` に持ち込む」は、`GemIndexPort#search` が既に持つ **F-02 の無制限ページング契約**（候補プールは GitHub 検索の 50 ページ / 1,000 件上限を適用しない）と構造的に両立しない。GitHub Search API を経由する限り、その 1,000 件上限からは絶対に逃れられないためである。

---

## 争点 A: 案ごとの実装コストと破壊点

### 案1: 検索結果（GitHub Search）のうちプールに載っているものを Gem Index 順に

**実装が必要な箇所**
- `app/[locale]/gems/page.tsx` を全面書き換え: `searchGemsUseCase()` の代わりに `searchRepositoriesUseCase(accessToken)({ keyword, page, sort, perPage })`（`src/usecases/search-repositories.ts`）を呼び、その `SearchResult.items` に対して `lookupGemIndexes(items.map(i => i.fullName))`（`src/composition/container.ts`）でバッジ判定 → 未ヒットを除外 → `gemIndex` 昇順に並べ替え。
- 新規 usecase が要る（`makeSearchGems` の契約 `SearchGemsResult` を維持するなら中身を丸ごと差し替え、`src/usecases/search-gems.ts` の JSDoc・型はほぼ全て陳腐化する）。

**何が壊れるか（具体）**
1. **F-02 との直接矛盾**: `SearchResult` の母数は GitHub Search API 由来で、`src/domain/model/page-number.ts` の `tryPageNumber`（`MAX_PAGE = 50`）に縛られる。実データで `com` 8,913 件・`github` 8,156 件・`core` 1,631 件がプールに実在する（`gem-index-port.ts` の JSDoc に明記）。案1を採ると、これらの語で Gem 一覧を開いた瞬間に **50 ページ目より後ろが再び到達不能になる**（`SP-19` が既に直した F-02 の後退）。
2. **`totalCount` の整合が取れない**: GitHub Search API の `totalCount` は「検索一致件数」であり Gem 一致件数ではない。バッジが付いたものだけを事後フィルタすると、ページごとに Gem の混入率が変わり、`totalCount` と実際にページャへ表示すべき件数が一致しなくなる（`Pagination` コンポーネントの `maxPage` 計算 = `Math.ceil(totalCount / perPage)` が壊れる）。
3. **レート枠消費の純増**: `TTL_SEARCH_SECONDS = 60`（`container.ts`）のキャッシュはあるが、検索結果ページと `/gems` ページは別ナビゲーションで別リクエストのため、同一キーワードで両方開くと GitHub API 呼び出しが 2 倍になる（30 req/min 枠を消費）。
4. **cold start**: `StaticGemIndex` の第 2 段（検索インデックス構築・warm 追加 122ms）を全く使わなくなる分は軽くなるが、GitHub API のネットワーク往復（ユーザー体感遅延）が新たなボトルネックになる。トレードオフであって純減ではない。

**影響するテスト**: `src/usecases/search-gems.test.ts`（前提が全て変わるので実質書き直し）、`src/infrastructure/platform/static-gem-index.test.ts` の `search()` 関連ケース（呼ばれなくなる可能性）、`e2e/sp-19.spec.ts`（操作レビュー手順そのものが変わる）、`src/usecases/search-repositories.test.ts`（新たな呼び出しパターンが増える）。

**結論**: 却下。バッジと定義は完全一致するが、F-02 を意図的に壊す以外に実装しようがない。

---

### 案3: ハイブリッド（検索結果の Gem を必ず含めつつプール名照合も出す）

**実装が必要な箇所**
- `/gems` は独立ナビゲーション（`GemListLink` は `href` に `keyword` だけを渡す。`app/[locale]/page.tsx` の `state.result.items` を URL 越しに引き継ぐ手段が無い）。ハイブリッドを成立させるには `/gems` 側で **改めて** GitHub Search API を叩く必要があり、案1と同じ経路を内包する。
- 2 系統（プール名前一致 = `GemPoolSearchResult` / GitHub 検索ヒットのうち `lookup()` で拾えたもの）をマージする新ロジックが要る。マージ先はおそらく新 usecase（`src/usecases/search-gems.ts` を置き換えるか並置）。

**何が壊れるか（具体）**
1. **「取りこぼしなく全部含める」は事実上不可能**: chimurai/http-proxy-middleware のような description ヒット分を **漏れなく** 拾うには、GitHub 検索の全ヒット（最大 1,000 件・50 ページ）を全部フェッチして `lookup()` にかける必要がある。1 回の一覧表示で 30 req/min の枠をほぼ使い切る計算になり、INF-2（Workers の CPU/コスト制約）以前にレート枠制約で非現実的。
2. **ページングの基準が非対称**: プール名前一致側は GitHub API 上限を持たない無制限ページング（F-02）、GitHub 検索側は 50 ページ上限。1 ページ目だけ両者を混ぜて 2 ページ目以降はプール側だけ、のような部分実装は「2 ページ目以降でまた取りこぼす」新たな期待のズレを作るだけで、F-1 の解決にならない。
3. **並び順の破綻**: `gemIndex` 昇順という単一の決定論的キーで両系統を安定してインターリーブできない（GitHub 検索由来の候補は「検索一致度」で決まった順で来ており、`gemIndex` はプール側の意味しか持たない値。混ぜた瞬間に「どちらの順序原理を優先するか」という新しい未決事項が生まれる）。
4. **`GemIndexPort` の契約変更が必要**: 現状の `search()` は「プール全件」を母集団とする契約（`gem-index-port.ts` の JSDoc に明記）。ハイブリッド母集団は別概念なので、契約を変えるか新ポートを増やすかの選択を迫られる（YAGNI 違反・ARCH の層責務が曖昧になるリスク）。

**影響するテスト**: 案1のもの全部 + `src/infrastructure/platform/static-gem-index.test.ts`（`search()` の母集団定義が変わるなら全面改修）+ `src/composition/container.test.ts`（新しい配線が要る）。

**結論**: 却下（少なくとも今回のスコープでは）。「期待に最も近い」のは事実だが、決定論的なページング・並び順・レート枠のいずれかを犠牲にしないと成立せず、犠牲にした瞬間に F-1 とは別の新しい取りこぼしバグを生む。

---

### 案2: プールベースのまま緩和条件を見直す（推奨）

**実装が必要な箇所（ピンポイント）**
- `src/infrastructure/platform/static-gem-index.ts` の `search()` 内、`matched.length === 0` の判定（276 行目）を「閾値未満」に緩める。`countSingleTokenHits`（445 行目）はそのまま使い回せる（呼び出し条件を変えるだけで、ループの向き・CPU 特性は無改修）。
- 具体的な閾値・発火段数の設計は `search_semantics` の担当（`D-37` の書き換えが要るならそこが決める）。**自分（arch_perf）が担保するのは「閾値をどう変えても計算コストは既存の O(records) 線形走査から増えない」という一点**。

**なぜ perf 的に安全か**
- `GemIndexPort`（`gem-index-port.ts`）の **インターフェース自体は無改修**。`GemPoolSearchInput` / `GemPoolSearchResult` の型もそのまま。契約の文言（`relaxed` / `usedTokens` の意味）も「全語 AND が閾値未満なら 1 語へ緩める」に一般化するだけで、UI 側（`GemList` コンポーネント）の受け取り方は変わらない可能性が高い（争点 D は `ux_writer` 領分）。
- cold start（プール構築 82ms・検索インデックス構築 122ms）・warm 走査（8〜12ms）のどちらにも触れない。`SP-19` の裁定（2026-08-22・転置索引を採らない）はそのまま有効。
- **SP-18 バッジ経路（`lookup()`）に一切触れない**。`container.ts` の `lookupGemIndexes` も `app/[locale]/page.tsx` の `RepositoryList` 呼び出しも無改修 → 回帰リスクなし。

**残る限界（正直に書く）**
- chimurai/http-proxy-middleware のような **description ヒット**（GitHub 側の全文検索がヒットさせたが、リポジトリ名・パッケージ名のどちらにも一致しない）は、案2では **依然として一覧に出ない**。これは `GemIndexPort#search` の契約（`D-37`: 名前の単語境界一致のみ・部分一致やあいまい一致は入れない）の限界であり、解決するには GitHub の description 情報を静的シャード（`D-38`）に持ち込む必要がある。`D-38` は「レジストリ別静的シャード + isolate 内メモリ索引・DB を持たない」と決めており、description 情報（各リポジトリの自由文かつ GitHub 側で日々変わる）を静的シャードに焼き込むのは生成バッチ側の別スコープの大改修になる。**本スプリントでは解決しない前提で UI 側（争点 C/D）が期待値を埋めるしかない**。

**影響するテスト**
- `src/infrastructure/platform/static-gem-index.test.ts`: 緩和発火条件のケース（現状「全語 AND 0 件」を前提にしたテストがあれば、閾値化に合わせて期待値・ケースを追加/修正）。
- `src/usecases/search-gems.test.ts`: `unmatchableQuery` 判定・`isPoolUnavailable` 判定はポートの外側なので直接の変更は少ないはずだが、`relaxed` が立つケースが増える分のフィクスチャ追加はありうる。
- `e2e/sp-19.spec.ts`: 緩和時の注記（`relaxedNotice`）が出るケースが増えるため、操作レビュー手順・アサーションの見直しが要る。
- `src/composition/container.test.ts`: 無影響のはず（配線は変えない）。

---

## 争点 B（perf 観点の補足）: 緩和規則の具体への注文

閾値・段数は `search_semantics` 領分だが、perf 観点で 1 点だけ制約を置きたい: **緩和判定に使う「件数」は `countSingleTokenHits` が返す Map の値をそのまま使うこと**（新たに追加の走査を増やさない）。「next.js のような .js 付き製品名」を一般規則で救う設計にしても、判定ロジックが `records` を複数回走査する形にはしない（現状 1 パス）。

## 争点 E（まとめ）

| 観点 | 案1 | 案2（推奨） | 案3 |
|---|---|---|---|
| cold start (2.78s) 影響 | 影響小（第2段不要）だが GitHub API 遅延が新規発生 | 無影響 | 最大（両方発生） |
| レート枠 30req/min | 消費増（キーワードごとに +1 呼び出し） | 無影響 | 消費増（全件フェッチが必要なら枠を使い切る） |
| CPU (INF-2 / F-01) | 影響小 | 無影響（既存 O(records) のまま） | 影響小〜中 |
| F-02 との整合 | **矛盾**（50ページ上限が復活） | 整合（無改修） | 部分的に矛盾（GitHub 側の上限を引きずる） |
| GemIndexPort 契約 | 変更不要（`lookup`のみ使用）だが usecase 全面書き換え | **無改修** | 契約変更 or 新ポートが必要 |
| SP-18 バッジ経路への回帰リスク | 低 | **ゼロ** | 低〜中（配線が増える分リスク面が広がる） |
| 実装スコープ | 中 | **小** | 大 |

### `search_semantics` — 主張
<sub>2026-08-23T10:03:40+09:00</sub>

## 主張（争点 A）: 案3（ハイブリッド）を推奨・案2 は「発火条件をどう調整しても」F-1 の症状を解消できない

### 実測（`public/data/gem-index/*.json` 全 13 シャード・62,483 件、`gem-keyword.ts` の `tokenizeIdentifier`/`tokenizeQuery` を Python で再実装して python3 で全件走査）

**チェック1: バッジ=所属照会と一覧=名前照合の乖離は「1 件だけ不足」ではなく「原理的に届かない集合」がある**

`chimurai/http-proxy-middleware` は `npmjs-org.json` シャードに実在する（プール所属＝badge が付く）。しかしそのトークン列は `['http','proxy','middleware']` で、`next` も `js` も一切含まない。したがって `selectMostSelectiveToken` の閾値をどう調整しても——AND=0 で発火させても、AND<3 で発火させても——この 1 件を `q=next.js` の一覧へ引き込む経路は存在しない（緩和は「クエリのトークンのどれかを残す」操作であり、クエリに無い語を使った全文一致は D-37 が明示的に禁止している「あいまい一致」そのもの）。**案2 はこの F-1 の核心症状を原理的に解決できない**。これは閾値設計の巧拙の問題ではなく、母集団の定義（バッジ=プール所属 vs 一覧=名前一致）が違う限り必ず残る構造的ギャップ。

**チェック2: `q=next.js` の AND 一致は実際に 1 件だけ（緩和は発火しない）**

- `tokens=['next','js']` → AND 一致 **1 件**（`vercel/next.js`）
- 単独: `next`=38 件、`js`=684 件
- 現行ロジック（AND=0 でのみ緩和）は AND=1 なので **緩和は発火しない**（ドキュメント記載どおり再現）

**チェック3: 「AND ヒット数が閾値未満なら 1 語緩和」（案2 の具体案）を仮に next.js へ適用すると、ノイズがすぐ支配的になる**

`next` 単独 38 件の中身を見ると、実際に Next.js 本体（`vercel/next.js`）以外は `dirs-next`（Rust crate）・`ffmpeg-next`・`encoding-next`・`riptide-next` 等、**"next" を接尾辞に持つ無関係な Rust/Node パッケージがほとんど**（`next` というブランド名とは無関係な `-next` 命名規則の衝突）。閾値緩和で 1 件→38 件に増やしても、そのうち 37 件はノイズであり、`orm→normalize` が禁じたのと同種の「意図しない語がヒットに紛れる」問題を別の経路（サフィックス語の頻出）で再現する。`js` 側を緩和候補にすると 684 件で論外（`js` は語彙頻度 2 位クラスの超頻出トークン）。**閾値ベースの緩和拡張は、D-37 が守ろうとしたノイズ排除の原則と正面衝突する。**

**チェック4: 「.js 付き製品名」を一般規則で救う案（グルー語からの `js` 接尾辞分割）も同様にノイズを持ち込み、かつ本件を解決しない**

グルー表記（区切り文字なしで `xxxjs` になっている識別子。例: `vuejs`・`nodejs`・`nestjs`・`phantomjs`）は全プール中 **382 種・延べ 1,510 件**存在する（全体の約 2.4%）。これを「末尾 `js` を切って `xxx`+`js` の 2 トークンに割る」一般規則にすると:
- `TensorRT` を `tensor`+`rt` に割らない、という `gem-keyword.ts` の既存不変条件（キャメルケース非分割）と同じ理由で、**形態素解析への第一歩**になり D-37 の「単語境界一致であって形態素解析ではない」という設計方針を破る
- しかも実際に検証すると **`vuejs/vue`（Vue.js 本体）は現行ロジックでもこのルールを適用しても `q=vue.js` に完全一致しない**（owner が `vuejs` で repo が `vue`。トークンは `['vuejs','vue','template','compiler']`。分割ルールで `vuejs`→`vue`+`js` にしても、`vue` は元から居るので実質的に足されるのは `js` 1 語だけ。これは「たまたま効く」ケースであり、`socket.io`（`io` は 893 件の超頻出語）のような別ブランドでは同じ理屈が破滅的なノイズになる）
- そして本件の主症状（`chimurai/http-proxy-middleware`）には **一切効かない**（グルー語分割はクエリ側 or 対象語のどちらかに `js` が含まれる場合の話であり、`http-proxy-middleware` には `next` も `js` もそもそも登場しない）

**結論**: 争点 A は **案3（ハイブリッド）を推奨**。理由は「この検索語の Gem 候補」というラベルの意味に最も忠実だから——badge が「この検索結果に Gem が付いている」と主張した対象を一覧が必ず含む、という同一性がラベルの素朴な期待そのもの。案1（検索結果ベースへ全面置換）は badge との定義一致では案3と同等だが、プール全体（62,483 件・GitHub 検索が届かない非 npm 52% を含む）からの発見力を失う。これは `D-36` が「10.9 万リポジトリの母集団を活かさない」として明示的に却下した現状維持案の再来に近い後退であり、避けるべき。案3 なら「検索結果由来の Gem を必ず含める」ことで badge との不一致（F-1 の症状）を構造的に消しつつ、プール全体の発見力（AND 一致の残り）も維持できる。

### 争点 B（緩和規則の具体設計への提案）

- **現行の「全語 AND=0 のときだけ 1 語緩和」は変更しない**（閾値化するとチェック3 のとおりノイズが支配的になる。閾値化で next.js を救おうとすると `next` 単独の 37/38 件がノイズという実測が出ている以上、閾値変更は「1 件しか出ない」不満を「ノイズだらけの 38 件」に置き換えるだけで、UX 上の改善にならない可能性が高い——ここは ux_writer 陣営とも要すり合わせ）
- **`.js` 特別扱い・グルー語の接尾辞分割は導入しない**（チェック4 のとおり一般化の代償が大きく、本件の解決にも寄与しない）
- 案3 採用時、案2 側（プール名照合）の緩和ロジック自体は現状維持でよい。ハイブリッドの「検索結果由来の Gem」の枠がそもそも AND=0/1 のケースを別ルートで拾うため、緩和の閾値をいじる動機自体が薄れる

### 弱点（反論されうる点）

1. 「382 種・1,510 件」は全体の 2.4% と小さく、"稀なケースのために一般化を諦めるのは過剰反応では" という反論はありうる。ただし件数の小ささは同時に「グルー語分割で救えるクエリも少ない」ことを意味するので、コストに見合うリターンが薄いという結論を弱めない。
2. chimurai の 1 例だけで「案2 は原理的に無理」と断定するのは早計という反論はありうる。ただしこれは D-37 の設計方針（`topics` を配信データに載せない・GitHub の description 全文検索とは別物）そのものに起因する構造的制約であり、サンプル数を増やしても同じ結論になる（プールが持つデータは repo 名 + package 名のみで、description 由来のヒットを再現する情報がそもそも配信データに無い）。
3. 案3 のマージ設計（並び順・ページング）は自分のレンズ外。arch_perf の裁定と整合させる必要がある。

### `ux_writer` — 主張
<sub>2026-08-23T10:04:00+09:00</sub>

# ux_writer round1 claim

## 争点 A への立場（文言だけで期待のズレを埋められるか）

**埋められない・埋めるべきではない。** バッジ＝候補プールへの所属照会（`lookup`）、一覧＝リポジトリ名／パッケージ名の単語境界一致（`search`・`D-37`）という**定義そのものの差**が原因であり、これは文言の問題ではなくデータ／照合ロジックの問題（争点 A/B の射程）。文言でできるのは以下の 2 つまで:

1. 「この一覧は何を根拠に絞り込んでいるか」を**事前に**伝え、驚きを減らす（期待調整）
2. 実際にズレが起きた個別ケース（0 件・1 件・薄いヒット）で「なぜ薄いか」を説明する（`gems.unmatchableQuery` / `gems.empty` は既にこの役目を果たしている）

一方で、**「Gem マークが付いているのに一覧に出ない」という具体的な訴え（F-1）そのものは文言では解消しない**。chimurai/http-proxy-middleware のように名前照合では原理的に出ないケースがある限り、どんな文言を書いても実際の一覧には出てこない。ここで文言に「全部出ます」と読める約束をしないことが最重要（誤解を埋めるのではなく、誤解を**生まない**書き方に倒す）。したがって争点 A/B の設計判断（母集団をどう広げるか）を文言の代替にしない、という立場を明示しておく。

## 争点 D: 検索結果見出し直下の説明文

### 配置とレンダリング条件

- **場所**: `app/[locale]/page.tsx` の `SearchBody`（`state.status === 'ok'` を確認済みのブロック）内、`GemListLink` の**直前**（＝結果本体の先頭、`h2#results-heading` の直後に見える最初のコンテンツ）。`aria-live="polite"` の `#search-status` セクションの**外**（既存の `SearchStatusText` と同じ非ネスト構造を維持。ライブリージョンに入れると件数変更のたびに再読み上げされてノイズになる）。
- **条件式（推奨）**: `state.result.items.length > 0`（`GemListLink` と同じゲート）。**バッジの有無（`shownGemBadgeCount`）では条件分岐しない** — 理由は次項。
- **「バッジ 0 件のときも出すか」への回答**: **出す。** 検索結果はあるが今回のページに Gem 印が 1 つも無いケースでも表示する。理由: この説明文は「今のページに付いている印の説明」ではなく「Gem という機能自体の説明」であり、印が無いページこそ「なぜ無いのか」「この検索語で Gem を探すには一覧へ行けば良い」という導線理解が必要。既存の `gemBadgeNote`（付かないことが低評価でない旨）は `shownGemBadgeCount > 0` のときだけ出す設計のままでよい（役割が違うので条件を揃える必要はない）。
- **検索結果 0 件（`items.length === 0`）のときは出さない**: 説明する対象（バッジが付きうるカード）自体が存在せず、空状態表示の直前に唐突な機能説明が挟まるのは `ui-ux-guidelines.md` の一貫性方針に反する。`GemListLink` の非表示条件と揃える。
- **エラー・idle 時**: `SearchBody` はそもそも `state.status === 'ok'` のときしか呼ばれないため自然に非表示。追加の条件分岐は不要。

### 見出し構造への影響

新しい `<h2>` は作らない（`ui-ux-guidelines.md` §7.0: 各ページ固有見出しはすべて `h2`、1 ページに `h1` は共有ヘッダー 1 つのみという制約に抵触させない）。単なる `<p>`（`text-muted-foreground text-sm` 程度の既存トーンに合わせる）として `h2#results-heading` の内容としてではなく後続の**兄弟要素**に置く。スクリーンリーダーでの読み上げ順は「検索結果（h2）→ 説明文（p）→ Gem 一覧導線リンク → 件数（ライブリージョン、DOM 順は上だが実際は別ブロック）→ カード一覧」になる。色だけに意味を持たせる要素はないため NFR-12/13 は満たす（可視テキストのみで完結）。

### 既存 `home.gemBadge.note` との関係

**重複させない。役割を分ける。**

- 新設の説明文（トップ・常時候補）: 「Gem マークとは何か」の**定義**を伝える。
- 既存 `home.gemBadge.note`（末尾・`shownGemBadgeCount > 0` のときだけ）: 「印が無い＝低評価ではない」という**免責注記**。これは個々のバッジが見えている状態でこそ意味を持つ文なので、今の位置・条件のまま**維持**する。

内容が被らないよう、新設文には「付かないことは評価が低いことを意味しない」という文言は**入れない**（それは末尾注記の役目のまま）。逆に末尾注記には「一覧で見られる」という導線案内は**足さない**（それは `GemListLink` のラベルの役目）。3 つの文言（新設説明文・`GemListLink` ラベル・末尾注記）が三重に同じことを言わないよう線引きする。

新規メッセージキー: `home.gemBadge.intro`（ja/en）を追加する。既存 `home.gemBadge.label` / `srHint` / `note` はそのまま。

### 文言案（逐語・複数案）

**採用推奨: 案 A**（最短・F-2 の「端的に」を最も素直に満たす。既存 `srHint` の内容と整合させ、2 箇所で定義がズレるのを防ぐ）

```
ja: 「Gem」マークは、star 数のわりに多くのパッケージから使われているリポジトリに付きます。
en: The "Gem" mark flags repositories that many packages depend on, relative to their star count.
```

**案 B**（製品の狙い＝見過ごされがちな価値、を一言添える版。ただし「見過ごされがち」は評価的に読めなくもないため D-36 の語調チェックが必要）

```
ja: 「Gem」マークは、star 数だけでは伝わりにくい、多くのパッケージから使われているリポジトリの目印です。
en: The "Gem" mark highlights repositories that are used by many packages, even when their star count doesn't show it.
```

**案 C**（2 文構成。定義 + 一覧への軽い導線言及。争点 C を文言側で少し支援したい場合の代替案。ただし `GemListLink` ラベルと言っていることが近くなるため冗長リスクあり — 採用するなら `GemListLink` ラベル側の文言を短くする等の調整とセットで検討すること）

```
ja: 「Gem」マークは、star 数のわりに多くのパッケージから使われているリポジトリに付きます。関連する Gem 候補をまとめて見るには、下の「Gem 候補を一覧で見る」を選んでください。
en: The "Gem" mark flags repositories that many packages depend on, relative to their star count. To browse related Gem candidates together, use "See Gem candidates" below.
```

**私の推奨は案 A**。案 C は F-2 の「端的に」から外れ、かつ争点 A で述べたとおり「一覧に全部出る」という誤解を助長しかねない言い回しになりやすい（「まとめて見る」が完全性を含意しがち）ので不採用が妥当と考える。

D-36 の語調（断定的な優劣評価をしない）は 3 案とも満たしている（「多くのパッケージから使われている」は事実記述であり評価語ではない。「見過ごされがち」を含む案 B のみ、レビューで語調確認が要る）。

## 争点 C: 導線ラベル・見出し・緩和注記・0 件文言の一貫性

- `home.gemListLink.label`「この検索語の Gem 候補を一覧で見る」は**完全性を含意する読み方ができる**（「この検索語の Gem 候補」＝全部、と読める）。争点 A の設計（母集団拡張の有無）が決まった後に、必要なら「関連する Gem 候補を見る」等へ弱める余地を残しておく。**今回のスコープでは変更を提案しない**（母集団の設計判断が先。ラベルだけ弱めても実体が伴わないと別の不整合を生む）。
- `gems.empty` / `gems.unmatchableQuery` / `gems.relaxedNotice` は既に「母集団は限定的」「単語境界一致」「低評価ではない」を明示しており、一貫性は保たれている。新設の検索結果側説明文（案 A）と語彙（「star 数のわりに多くのパッケージから使われている」）を揃えたので、検索結果ページと Gem 一覧ページを行き来しても定義がぶれない。
- 0 件文言の一貫性: 検索結果 0 件時は新設説明文を出さない（上記）。Gem 一覧側の 0 件文言（`gems.empty` / `unmatchableQuery`）は変更不要。

## lead への申し送り（決定表用メモ）

- artifacts: `messages/ja.json` / `messages/en.json`（`home.gemBadge.intro` 追加）、`app/[locale]/page.tsx`（`SearchBody` 内 `GemListLink` 直前に `<p>` 追加、`state.result.items.length > 0` ゲート）
- tests: 既存 `e2e/sp-18*.spec.ts` 系（バッジ表示）に「`items.length>0` かつバッジ 0 件でも説明文が出る」ケースを追加。メッセージカタログの ja/en キー存在チェック（既存の allowlist スクリプトがあれば追従）。
