<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: Issue #308（初見フィードバック 10 件対応）のスプリントレビュー判定

- 議題ID: `sprint-review-issue308-20260821`
- 論点: PR #312 が main へ squash マージ済み（4a8e113）。Sprint Goal: 初見ユーザーが説明なしで「何ができるツールか」「この数値は何か」を掴める状態にし、待たせた末に空振りする経路をなくす。飼い主の決定により sort=gem-index を撤去し、今日の Gem は残して説明を強化し、指標は名称変更＋生値廃止を実施した。受け入れ可否・デプロイ可否・残課題の仕分けを判定する。
- 参加者: `acceptance`, `residuals`
- 投稿数: 2
- 更新: 2026-08-21T14:06:23+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `acceptance` — 主張
<sub>2026-08-21T13:46:34+09:00</sub>

# 受け入れ判定（Issue #308 / PR #312・sp:8）

## 0. 前提確認（実結果ベース）

- PR #312: `mergeable_state` 取得済み、**`state=closed` / `merged=true`**（`merged_by=kai-kou`・`merge_commit=4a8e113`）。G-3 の実結果確認を満たす。
- `git log origin/main` の先頭が `4a8e113`（本 PR のマージコミット）であることも確認済み。

## 1. デプロイ可否（必須確認事項①）

`python3 tools/check_deploy_gate.py` を実行した結果（exit=1）:

```
デプロイ待機: 以下の Issue がゲートを塞いでいます
  #308 improvement: 初見ユーザーのフィードバック 10 件に対応する（用語・説明・データ整合・体感速度） — Sprint Review 判定が未実施です
```

→ **ゲートが塞がっている唯一の理由は「本判定が未実施」であること自体**（コードの欠陥ではない）。PR 側の `run_checks.sh` 全項目（Lint / tsc / vitest / E2E / Lighthouse / 依存規則 / UI 寸法 / コントラスト / ADR-README / 副作用GET / CJK / セルフレビュー / self-test 群）は PR 本文記載どおり全 PASS。本番影響のある欠陥は検出していないため、**`accepted_with_conditions` を選ぶ場合でも `deploy: yes`**（条件はプロセス上の残課題であり本番影響なし）。本判定の投稿自体がこのゲートを解く前提条件になる。

## 2. 設計ドキュメントのポインタ追跡（1 ホップ先まで）

- `user-story-map.md` §5.3 `SP-16` → 🔴 撤去注記あり（`D-33` 参照、節は履歴として残置）。`US-34` も撤去済みの取り消し線表記。§2 の GR-4 記述も撤去反映済み。
- `prd.md` §6/§11: `AR-2` 備考「Gem Index 順は D-33 により撤去済み。現在は関連度/star/更新の3つ」、`GR-4` 備考に撤去理由（候補プール227件・一致0〜8件）明記。§13 未決事項の `Gem Index の算出方法` は既に決定済みで対象外。
- `open-questions.md` `D-33`: 実測根拠（227件・react=8/test=7/cli=6・一般語ほぼ0件）、却下した代替案 2 つ、再導入条件（🔵 npm 以外を含み一般語上位100件で30%以上）、撤去範囲（`SortPicker`/`SortOrder`/`search-repositories.ts`/`list-gem-facets.ts`（削除）/`repository-list.tsx`）、非撤去範囲（`GemIndex` 型・`computeGemIndex`・`Gem` 型・候補プール）まで具体的に記録されている。反映先ポインタ（`user-story-map.md`/`prd.md`/`ADR 0009`）も実際にすべて更新されていることを grep で確認した。
- `cloudflare-infrastructure.md` §8.2: 本番デプロイは auto mode classifier に非決定的にブロックされうる仕様（§8.2.2）。今回のマージ後デプロイはこの判定（本コメント）を経由する設計どおりで、コード側に問題はない。

**矛盾・記述漏れ**: `ADR 0009` §末尾に `D-33（2026-08-21）追記` として撤去の経緯と「定義そのものの妥当性は否定されていない」旨が明記済み。`ADR 0014` は Gem Index 定義を再定義しない立場のまま変更なし（整合）。`domain-model.md` の `SortOrder` / `GemFacet`（撤去済み・型ごと削除の記録あり）/ Gem Index コンテキストの記述も D-33 に揃っている。**撤去済み機能を現行機能として書いた記述は grep で見つからなかった**（`gem-index`/`Gem Index` の残存箇所はすべて「今日の Gem」用途 or 撤去済みの明記のいずれか）。

## 3. 機械チェックの実行結果（実行して断定）

```
$ npx vitest run
 Test Files  62 passed (62)
      Tests  503 passed (503)

$ npx vitest run app/api/search/route.test.ts src/domain/model/sort-order.test.ts
 Test Files  2 passed (2)
      Tests  23 passed (23)
（`?sort=gem-index` の後方互換テストを含む: 「撤去済みの ?sort=gem-index を付けても 500 にならず 200 を返す」「既定並び順へフォールバックする」の 2 テストとも PASS）

$ python3 tools/check_architecture_boundaries.py
✅ 依存規則 OK（144 ファイル・Warning 0 件）

$ python3 tools/check_ui_dimensions.py
✅ UI 寸法検査 OK（Warning 0 件）

$ python3 tools/check_contrast.py
[check_contrast] PASS: 11 ペア × ライト/ダーク 計 22 判定、全てしきい値を満たしています
```

→ 「たぶん満たしている」ではなく実行結果で断定。**`?sort=gem-index` の後方互換フォールバックは実際に動作している**（`tryParse('gem-index')` が `DEFAULT_SORT_ORDER` を返す・API が 500 ではなく 200 を返す、の両テストを個別に確認）。

## 4. チーム編成（単独実行チェック）

Sprint Planning コメント（Issue #308・作成時刻 03:47 JST）:
> **編成**: `discussion-review`（議論型 Agent Teams・5 レンズ: newcomer_ux / domain_naming / data_integrity / perf_transparency / docs_trace）→ 決定後に `fan-out(3+)` で実装

PR #312 本文の `Team:` トレーラー: `discussion-review(5) → fan-out(3)` — Sprint Planning の編成欄と同期しており **一致**。`sp:8` の既定（着手前に議論型 1 ラウンド → fan-out 実装）どおりで、**単独実行ではない**。Problem 該当なし。

軽微な観察（ブロッカーではない）: Sprint Planning コメント本文は決定ログ ID を「D-32」と予告していたが、実際の決定ログは競合により「D-33」で採番されている（`open-questions.md` 冒頭の "一度振った ID を変更・再利用しない" 原則に基づく繰り下げと同型の事情）。実害なし・記録の整合は取れている。

## 5. UI/デザイン観点（§2.4 コントロールサイズトークン）

🔴 **画面を実際に開いた目視確認はしていない**（私はプレビュー画面を開けない）。以下は PR 本文が示すプレビュー URL（`https://pr-308-gem-hunter.kinamocchi-tech.workers.dev`）を前提に、**コードで** 確認した結果である。

- `git diff` で `app/[locale]/page.tsx` / `src/ui/repository-list.tsx` / `src/ui/daily-digest.tsx` / `src/ui/sort-picker.tsx`（テストのみ変更）を確認: **新規のコントロール（ボタン・入力欄）は追加されていない**。変更は既存要素の条件描画化（idle 時の非表示化）と文言・データ構造の削除が中心で、`h-*`/`size-*` の生数値やサイズ関連の新規 className 追加は見当たらない。
- `tools/check_ui_dimensions.py` が Warning 0 件で PASS（新規/未登録コンポーネントの検知漏れ Warning も 0 件）。
- `tools/check_contrast.py` が ライト/ダーク 計 22 判定全て PASS（文言・アイコン変更に伴う配色トークンの逸脱なし）。

**機械検査の対象外（§2.4 表の「レビュー」列）である 4 領域は、事実として以下のとおり**:
1. **動的 className によるサイズ上書き**: 本 PR は className 分岐を増やしていない（条件描画の分岐のみ）ため新規リスクは低いと推定するが、実行時 DOM は未検証。
2. **推奨値（🔵）の妥当性**（主要導線 xl・二次コントロール md 以上）: `sort-picker.tsx` 自体は無変更（選択肢の定数のみ他ファイルで削減）のため tier は従前どおりのはずだが、これも実機で見ていない。
3. **未登録コンポーネント**: 機械検査 Warning 0 件により「config 未登録の新規コンポーネント」は無いと判定できるが、最終確認はレビュー側の役割。
4. **実ブラウザでの体感操作性**（誤タップ・視認性の主観評価）: 完全に対象外。

→ **視覚的な最終判断（プレビュー URL を開いての操作レビュー）は人間に委ねる**。コード上は §2.4 必須行（xs フロア遵守・入力欄 16px・ズーム抑止禁止・cva 経由の一本化）を破る変更が見当たらず、機械ゲートも全て PASS しているため、**UI 観点でブロッカーになる欠陥は検出していない**。

## 6. フィードバック 10 件の決着確認

PR 本文の対応表 + 実際の Issue 検索で裏取り:

| # | 結論 | 裏取り |
|---|---|---|
| 1〜6, 9, 10 | 本 PR で対応済み | コード差分・messages/*.json 差分で確認 |
| 7 | UI 説明強化のみ本 PR、データ側の是正は別 Issue | **#310**（open・`status:waiting-claude`・sp:3）実在確認済み |
| 8 | 別 Issue へ切り出し | **#309**（open・`status:waiting-claude`・sp:5）実在確認済み |

**取りこぼしなし**。10 件全件が「対応済み / 切り出し済み（実在する Issue 番号付き）」のいずれかで決着している。

## 7. 完了条件（Issue #308 本文）との突合

- 「10 件それぞれの決着記録」: PR 本文の対応表に明記 → **満たす**
- 「用語・説明文の変更が ja/en 両方の messages/*.json に反映」: `messages/en.json`（+13/-?）・`messages/ja.json`（+15/-?）両方が diff に含まれる → **満たす**
- 「既存テスト・E2E が緑」: vitest 503 件 PASS（実行確認済み）。E2E は PR 本文記載の PASS（56秒）を採用し自分では再実行していない（vitest + 依存規則で最低限は満たしたと判断）。
- 「プレビュー URL で導線確認できる」: URL は提示されているが視覚確認は未実施（§5 参照）。

## 総合判定

- コード品質・テスト・ドキュメント整合・チーム編成・フィードバック取りこぼしのいずれにも本番影響のある欠陥は検出しなかった。
- 唯一の残課題は「UI の最終視覚確認（人間の操作レビュー）が未実施」であること — これはプロセス上の残課題であり、コードの欠陥ではない。デプロイゲートは本判定の投稿自体を待っている状態。

結果: accepted_with_conditions
デプロイ: yes

**条件**: プレビュー URL（`https://pr-308-gem-hunter.kinamocchi-tech.workers.dev`）での人間による目視の操作レビュー（§2.4 の 🔵 推奨 tier・実ブラウザでの体感操作性）を、次回のドキュメント/UI 変更を伴うスプリントまでに実施すること。ブロッカーではなく確認事項。

### `residuals` — 主張
<sub>2026-08-21T13:46:52+09:00</sub>

## residuals: 残課題の仕分け（round 1）

### 1. 議論で出たが今回実装しなかった提案の仕分け

| # | 提案 | 分類 | 詳細 |
|---|---|---|---|
| 1 | 詳細画面での README 表示（要望⑧・争点 F） | **別 Issue 済み** | #309（`type:feature` / `sp:5` / `priority:P2`）。lead 判定の `artifacts: ["新規 Issue（type:feature）"]` と一致 |
| 2 | 候補プールの star を GitHub API で取り直す（round 2 `data_integrity` 発見・追加発見②） | **別 Issue 済み** | #310（`type:improvement` / `sp:3` / `priority:P2`）。lead 判定の追加発見②と一致 |
| 3 | Gem Index を順位・パーセンタイル表示に変換する案（争点 B） | **意図的に採らない（理由記録済み）** | `newcomer_ux` が round 2 で自ら撤回（新規の派生データが要り「表示名だけ変更」の境界を超えるため）。verdict の `rejected` にも明記済みで、再提起する場合の障壁も whiteboard に残っている。追加の Issue 化は不要 |
| 4 | 理由入りローディング文言で待たせたまま様子を見る案（争点 E の代替案①） | **意図的に採らない（理由記録済み）** | 提唱者 `newcomer_ux` が round 3 で自ら撤回（「実測を知った今となっては誠実さを装った気休め」）。verdict `rejected` に記録済み |
| 5 | 候補プールを 10 万件へ拡大する案（争点 E の代替案②） | **意図的に採らない（理由記録済み）** | Workers バンドル 3MB 上限（`INF-2`/`INF-3`）を圧迫し、かつ npm 限定である限り非 JS 系キーワードには効かないという構造的限界が二重に効く。verdict `rejected` に記録済み。D-33 の再導入条件（他エコシステム対応 + 30% 閾値）がこの案の正しい後継であり、6 番目の項目として扱う |
| 6 | `sort=gem-index` 再導入条件（候補プールが npm 以外のエコシステムを含み、かつ一般語検索上位 100 件で 30% 以上に Gem Index が付くこと・D-33） | **起票すべき** | 詳細は §3 |
| 7 | 一覧の star をライブ GitHub API 取得に寄せる案（争点 D の代替案①） | **意図的に採らない（理由記録済み）** | `NFR-5`（レート予算）・`NFR-3`（詳細画面のみライブでよい方針）・`AC-10` に抵触。verdict `rejected` に記録済み |
| 8 | 一覧の star 表示を削る案（争点 D の代替案②） | **意図的に採らない（理由記録済み）** | Gem の定義（実利用に対し star が小さい）の説明力を失う。verdict `rejected` に記録済み |
| 9 | 銘柄別の鮮度表示（`last_synced_at` を個別に出す・round 2 `data_integrity` 提案 / `newcomer_ux` 賛成） | **意図的に採らない（#310 に吸収）** | #310 完了条件は「生成される daily-digest.json の stars が生成時点の GitHub 値と一致する」＝根本原因（バッチ実行時の古い star 混在）を解消する設計。解消後は個別銘柄ごとの鮮度バラつきという前提自体が消えるため、個別 `last_synced_at` 表示という追加 UI は不要になる。#310 本文にも「Gem Index そのものの鮮度は対象外・必要になったら別途起票」と明記されており、現時点で見送る判断は whiteboard の議論と整合している |
| 10 | Gem Index（ランキング）自体の鮮度検証 | **意図的に採らない（明示的に将来課題として記録済み）** | #310 本文が「🔵 Gem Index そのものの鮮度は本 Issue の対象外。必要になったら別途起票する」と明記。今は起票不要（未確定の将来課題として正しく先送りされている） |

### 2. 切り出し済み 2 件（#309・#310）の妥当性検証

**#309（README 表示・`sp:5` / `type:feature` / `priority:P2`）**: lead 判定の `design`（README API 追加リクエスト・Markdown サニタイズ方針・`NFR-3` との整合が要検討）をそのまま Issue 本文の「着手時に決めること」へ転記しており、内容は whiteboard と一致。見積もりは「取得経路の設計＋サニタイズ方針決定＋実装＋テスト」で複数の未決事項を含むため `sp:5`（複数ファイル改修・新ツール追加相当）は妥当。10 件中唯一の新機能要望で他 9 件とスコープが重ならない点も lead 判定の分離理由と一致。優先度 `P2` は他の残課題（#310 も `P2`）と横並びで、緊急度は高くないが計画済みという位置づけとして妥当。

**#310（候補プール star 取り直し・`sp:3` / `type:improvement` / `priority:P2`）**: whiteboard 争点 D の `rejected`（ライブ取得へ寄せる案は `NFR-5` 抵触）と矛盾しないか要確認したが、#310 は「一覧の検索リクエスト時」ではなく「**バッチ生成時**」の GitHub API 呼び出しであり、Issue 本文でも「これはバッチ実行時のリクエストであり `NFR-5`（リクエスト時のレート予算）とは別会計」と明記している。争点 D で却下されたのは検索リクエスト都度のライブ化であり、#310 のバッチ時取り直しとは別物 — 整合している。見積もり `sp:3`（単一バッチスクリプト改修＋レート見積もり）は妥当。`ADR 0014`（静的配信）を壊さない設計方針も明記されており、意図的な設計制約の継承ができている。

### 3. 🔴 D-33 の再導入条件がバックログとして起票されていない

`open-questions.md` D-33 に条件（「候補プールが npm 以外のエコシステムを含み、かつ一般語の検索上位 100 件で 30% 以上に Gem Index が付くこと」）は **文書として記録済み** だが、`mcp__github__search_issues` で「Gem Index 再導入 / エコシステム / 候補プール拡大」を検索した結果、該当する Issue は 0 件（#294・#310・#296 がヒットしたが、いずれも別件・詳細は §4 参照）。条件を満たすための作業（候補プール生成バッチ `tools/generate_gem_digest.mjs` を npm 以外のエコシステムに対応させる等）は、実行しなければ条件充足の判定自体が発生しないため、**Issue 化しないと再導入の機会が永久に来ない**（CP-3 のリポジトリ衛生の観点でも、条件だけドキュメントに眠らせるのは「発見しても誰も拾わない」状態になる）。

**起票すべき**:
- タイトル案: `explore: sort=gem-index 再導入条件（他エコシステム対応・30% 閾値）の充足を検証する`
- `type:improvement`
- `sp:2`〜`sp:3`（Dynamic 補正: 要リサーチ・仕様未確定のため +1 SP。「候補プールを npm 以外へ拡張する」設計自体が未決なので調査タスクとして小さめに始める）
- `priority:低`（緊急性なし。飼い主が明示的にトリガーしたい時に拾えるよう記録だけしておく位置づけ）
- 本文には D-33 の条件式をそのまま引用し、`tools/generate_gem_digest.mjs` が現状 npm registry 限定である事実（コード確認済み・後述 §4）を「着手時に確認すること」として記載するのが妥当

### 4. `sort=gem-index` 撤去後の「宙に浮いた資産」の grep 確認結果

実際に `grep -rn` で確認した結果:

- ✅ **`src/domain/model/sort-order.ts`**: `ALLOWED_SORT_ORDERS = ['relevance', 'stars', 'updated']` のみ。`gem-index` の文字列は完全に除去済み
- ✅ **`src/usecases/list-gem-facets.ts`**: ファイル自体が存在しない（削除済み、`find` で 0 件）
- ✅ **`gemFacets` / `GemFacet` / `listGemFacets`**: コードベース全体で 0 件（`repository-list.tsx` からも除去済み）
- ✅ **`src/ui/sort-picker.tsx`**: `gem` を含む行なし
- ✅ **`src/usecases/search-repositories.ts`**: `gem` を含む行なし（gem-index 経路は完全撤去）
- ✅ **`messages/ja.json` / `messages/en.json`**: `gemIndexUnavailableHeading` は 0 件（検索結果一覧の区切り見出し文言ごと削除済み）
- ✅ **`e2e/sp-16.spec.ts`**: 削除済み（コミット統計で確認・212 行減）
- ✅ **`GemIndex` 型・`computeGemIndex`・`gemIndex`/`gemIndexValue` 関数・候補プール（`static-gem-digest.ts`・`tools/generate_gem_digest.mjs`）**: D-33 の宣言どおり「今日の Gem」（`get-daily-digest.ts` / `digest-rss.ts` / `daily-digest.tsx`）が引き続き使用しており、残存は正当

**🔴 唯一の未消化資産（grep で実際に確認）: 既存の改善 Issue 2 件が撤去によって前提ごと消滅している**

| Issue | 前提としていたコード | 現況（grep 確認済み） | 判定 |
|---|---|---|---|
| **#294**「Gem Index 順の 1 リクエストで候補プールを 2 回読んでいるのをやめる」 | `search-repositories.ts` の `searchByGemIndex` が `listCandidates()` を呼び、`app/[locale]/page.tsx` の `listGemFacetsUseCase()()` も同じポートを呼ぶ二重呼び出し問題 | `searchByGemIndex` と `listGemFacetsUseCase` はコードベースに 0 件（grep 確認）。`listCandidates()` の呼び出し箇所は `get-daily-digest.ts` の 1 箇所のみに減っている。**二重呼び出し自体が消滅** しているため、Issue の事象そのものが存在しない | 撤去に伴い **クローズすべき**（対応不要ではなく前提消滅） |
| **#296**「『Gem Index 情報なし』の区切りを支援技術にも見出しとして届ける」 | PR #293 で追加された `gemIndexUnavailableHeading` 区切り行（`<li>` 内の a11y 未対応見出し） | `gemIndexUnavailableHeading` はコードベースに 0 件（grep 確認）。区切り行自体が撤去済み | 撤去に伴い **クローズすべき**（対応不要ではなく前提消滅）。whiteboard の「追加発見①」（区切り見出し 0 件バグ）が「争点 E で撤去されるなら消滅する」と明記していたのと同じロジックがこの 2 件にも当てはまる |

この 2 件は「起票すべき」ではなく「**既存 Issue のクローズが必要**」という別種の残課題。今回のスプリントは撤去を実施した張本人でありながら、撤去によって無効化された既存 Issue のクローズまでは手当てしていない（CP-3 リポジトリ衛生の観点で放置扱いになる）。

### 5. フィードバック⑦（一覧と詳細の star 数不一致）の部分対応は妥当か

対応は「UI 文言で出所と鮮度を明示する」（#308 で実施済み・`messages/ja.json` の `attribution` で「参考値」「頃」表現を確認済み）と「データ側の是正は #310 へ」の 2 段構成。

- 実装済みの文言は whiteboard round 2 の `perf_transparency` 提案（「時点」→「参考値」へのトーンダウン）と完全一致しており、精度を実態より高く見せない配慮も反映されている
- 分割の妥当性: 争点 D の verdict が「一覧の star をライブ取得に寄せる案」を `NFR-5`/`NFR-3`/`AC-10` 抵触で明示的に却下しているため、今スプリント内でのデータ側是正はそもそも選択肢になかった。バッチ時取り直し（#310）という是正手段は争点 D の制約に抵触しない設計（バッチ実行時であり配信は静的のまま）であり、技術的に正しい切り出し先
- ユーザー視点での不満残存リスク: 文言で「一覧と詳細で数値が違うことがある」という **事実** は伝わるが、「なぜ今のデータで直さないのか」への納得までは文言だけでは埋まらない。ただし #310 が `priority:P2` で既に起票・追跡可能な状態にあるため、「対応が忘れられている」という状態ではない。初見ユーザー向けの完了条件（Sprint Goal: 説明なしで数値を理解できる）は文言レベルで満たしており、データ精度の改善は次スプリント以降の別軸の作業として適切に接続されている。**分割は妥当。追加のフォローは不要**

---

## サマリー（1 行）

切り出し済み #309・#310 は内容・見積もりとも whiteboard の verdict と整合し妥当。ただし D-33 の再導入条件を追跡する Issue が未起票（起票すべき）、かつ `sort=gem-index` 撤去によって前提が消滅した既存 Issue #294・#296 のクローズが未着手（grep で実コード確認済み）という 2 種類の残課題が残っている。
