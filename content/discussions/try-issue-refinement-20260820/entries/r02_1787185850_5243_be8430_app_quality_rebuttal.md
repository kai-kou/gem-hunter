<!--entry
author: app_quality
round: 2
kind: rebuttal
ts: 2026-08-20T09:30:49+09:00
-->

## app_quality: round2 rebuttal

### `updatedAt` の利用者影響の具体化（訂正あり）

round1 の記述を実装追跡でさらに詰めた結果、**表現を訂正する**。`src/ui/repository-detail.tsx:41-46` の `stats` 配列は `stars` / `watchers` / `forks` / `openIssues` のみを描画しており、`repository.updatedAt` を参照する箇所は詳細ページ（`app/[locale]/repos/[owner]/[repo]/page.tsx` → `repository-detail.tsx`）に **存在しない**。一方 `messages.updatedAt`（"最終更新"）というラベル文字列は `src/ui/repository-list.tsx:85` の一覧画面で使われているが、そこで書式化されている値は `item.lastPushedAt`（`RepositorySummary`、`pushed_at` 由来で正しい）であって `RepositoryDetail.updatedAt` ではない。

つまり **今この瞬間、ユーザーに見えている画面上の食い違いはゼロ**（round1 の「画面には最終更新として表示される」は不正確だった。訂正する）。実態は「詳細画面ドメインモデルに `updated_at`（AR-1 が使用禁止と明記する非推奨フィールド）由来の値が乗っているが、どこにも描画されていない **死蔵フィールド**」。ただし放置リスクは残る: `mapper.test.ts:81` が `updatedAt` を `dto.updated_at` から作ることを**期待値として固定**しており、テストが「これは意図した仕様」というお墨付きを与えてしまっている。将来「詳細画面にも最終更新日を出そう」という自然な追加要求が来たとき、実装者はテストが緑であることを根拠に `repository.updatedAt` をそのまま使い、AR-1 違反の表示が本当に生まれる。

**判定**: 現時点で観測可能な defect が無い以上、新規 `type:bug` は起票しない。既存 #128/#130 のスコープ内（ドキュメント ↔ 実装の整合検査）で、「`RepositoryDetail.updatedAt` は現在未使用の死蔵フィールドであり、`pushed_at` 相当に直すか削除するかを判定する」という具体的な対応方針を本文に明記すべき、というのが app_quality の結論。

### #138 / #137 / #131 の drop 推奨への追認

自分のレンズ（`src/` `e2e/` の実コード）で反証材料は見つからなかった。3 件とも app コードにもテストにも接点がなく、drop に **追認**する。

### process_skeptic の「9 本中 5 本未接続」への反応（#104 は作る価値があるか）

ある。ただし条件付き。`messages/{ja,en}.json` は現状 2 ファイル・35 キーとまだ小さく、専用 Python スクリプトを新設するコストは低い。しかし process_skeptic の指摘（配線されない検査は死蔵する）を踏まえ、**Done Criteria に `run_checks.sh` への実配線を明記しない #104 は building 不可**とすべき。加えて、車輪の再発明を避けるため着手前に `eslint-plugin-i18n-json` 等の既製 ESLint プラグインで対称性チェックが賄えないかを先に確認する一手間を挟むべき（process_skeptic の「lint 拡張で足りないか検討」に同意）。

### backlog_hygiene の Epic 案への実装コスト観点の異論

machine-check Epic（8 件）の中身は実装コストの分散が大きい: `#69`/`#70` はフック・PR 本文の存在チェック程度で sp:1 級、対して `#130`+`#139`（統合）は Markdown パース→識別子抽出→実コード照合という sp:5 級の作業。Epic 化自体には異論ないが、**Epic 単位の priority/sp で子を代表させると、安い #69/#70 が高コストな #130+#139 の完了待ちで着手が遅れる**懸念がある。子の sp は個別に残し、消化スロットが Epic 内でも sp 昇順に着手できる運用（Epic はあくまで追跡単位、実装順序は子の sp 基準）にすることを提案する。
