<!--entry
author: acceptance_judge
round: 2
kind: rebuttal
ts: 2026-08-20T09:11:30+09:00
-->

## acceptance_judge: backlog_triage round1 への rebuttal

### 矛盾点: なし

backlog_triage の 4 項目判定（1: 記録のみ／2: 別Issue化／3: 記録のみ／4: 別Issue化）はいずれも「次スプリントへ必須タスクとして送るものはゼロ・Issue #140 のクローズ条件には含めない」という結論であり、自分の総合判定 **accepted_with_conditions**（🔴必須違反なし・条件は視覚確認と tier 選定の2点のみでブロッカーではない）と方向性は一致している。矛盾は検出しなかった。

### 補強点

- **項目1（OAuth App 未登録）**: 自分も `infrastructure-design.md` §8.1 を実読し「(a) プレビューでは OAuth 無効化」が設計文書側の正式な方針であることを確認済み。backlog_triage の「A-6 相当・Claude 側にやることがない」判定を裏付ける一次情報として補強する。
- **項目2（logout GET CSRF）**: 自分のレンズでは評価対象外だったが、`app/api/auth/logout/route.ts` の存在は確認済み（差分 stat・29 行）。GET 実装である点は未検証だが、type:improvement・低優先度への切り出しに異論はない。
- **項目3（LocaleSwitcher 非一本化）**: 自分も `layout.tsx`/`page.tsx`/`repos/[owner]/[repo]/page.tsx` を実読し、`LocaleSwitcher` が layout.tsx ではなく各ページに個別配線されている実装を確認済み。backlog_triage の技術的制約（middleware 非採用・pathname 取得手段なし）という説明はコード構造（`currentPath` を呼び出し元が明示的に渡す設計）と整合する。記録のみで Issue化不要という判断に同意する。
- **項目4（E2E タイミング揺らぎ）**: 自分は origin/main 上で `bash tools/run_checks.sh` を実際に実行し E2E PASS を確認済み（34秒・全項目PASS）。「実装は動作しており受け入れをブロックしない」という backlog_triage の前提を実行結果で裏付ける。

### 新規提起: LoginLink の size='sm' 問題（backlog_triage の仕分けリストに未掲載）

自分の round1 claim で条件付き事項として挙げた「`LoginLink` が `size: 'sm'`(28px) で `ui-ux-guidelines.md` §2.4 の 🔵 推奨（二次的コントロールは `--size-control-md`(32px) 以上）をわずかに下回る」点は、backlog_triage の4項目リストに含まれていない。5件目の残課題として仕分けを依頼する。

**自分の意見: 今すぐの軽微修正は不要。次スプリントの UI タッチ時に拾う軽量フォローアップとして記録するに留めるべき（「記録のみ」寄りだが、完全ノーアクションではなく type:improvement・sp:1 での軽量 Issue 化を推奨）。**

理由:
1. **🔴 必須違反ではない**（§2.4 必須フロアの `--size-control-xs`(24px) は上回っている）。`--size-control-xl`(44px) 系の 🔴 必須違反（例: 検索フォームの主要導線）とは性質が異なり、ブロッカーにする理由がない。
2. **PR #141 は squash マージ済み**。この 1 行のためだけに単独の緊急修正 PR を今すぐ切るのは、変更対象・レビューコストに対して過剰（YAGNI・スコープ厳守の原則）。次に `src/ui/login-link.tsx` か `app/[locale]/layout.tsx` に触れる PR（次スプリントの UI 関連タスク、または本 Issue の残課題としてまとめて）でついでに直せば十分。
3. ただし「記録すら残さない」のは避けたい。§2.4 が明記するとおり「意味論的に正しい tier を選んでいるか」は機械検査でなくレビューが担保する領域であり、機械 PASS だけでは実装者の意図（二次導線として `sm` を意図的に選んだのか、単なる見落としか）が分からない。`LoginLink` の JSDoc コメントには tier 選定理由の説明がなく、意図的判断か見落としかを区別できない。
4. よって backlog_triage の項目3（LocaleSwitcher・記録のみ）よりは項目2寄り（軽量 Issue 化）が適切と考える。理由・原因が「未解明」な項目4と違い、こちらは原因も対処法（`size: 'sm'` → `'default'` への1行変更、または意図的判断ならコメントに理由を追記）も自明なため、`sp:1` の最小サイズで良い。

**提案する仕分け（5件目として）**:

| # | 項目 | 判定 |
|---|------|------|
| 5 | LoginLink size='sm' が §2.4 🔵推奨(32px)をわずかに下回る | 軽量 Issue 化（`type:improvement`・`sp:1`・優先度低）。次スプリントの必須タスクにはしない。Issue #140 クローズ条件には含めない |

この結論も含め、Issue #140 のクローズ条件を「US-2/US-4/US-5/E-11 の受け入れ基準のみで判定する」という backlog_triage のまとめ方針に賛成する。
