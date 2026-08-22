<!--entry
author: evidence_auditor
round: 2
kind: rebuttal
ts: 2026-08-22T13:07:29+09:00
-->

# evidence_auditor: Round 2 rebuttal/concession

## #77 / #63（dedupe_skeptic への回答）
`.github/workflows/` は実機確認済み（`ls` → No such file or directory）。dedupe_skeptic が依頼した「両方陳腐化の疑い」の裏付けは取れている。

**結論: duplicate ではなく、両方 not_planned で個別に閉じるべき。**
`duplicate` という state_reason は「片方が生きていて、もう片方の要求をそちらが引き受ける」関係を表す。しかし #63/#77 はどちらも生きていない——.github/workflows/ 自体が撤去され、GitHub Actions 経由のデプロイという **両者共通の前提そのものが構造的に消滅した**（D-23/D-31/D-32）。#77 を keep にして #63 を duplicate で閉じると、「#77 は今も有効で追跡すべき Issue」という誤った含意が残る。実際には #77 が要求する「Actions の課金確認」自体が無意味（Actions 経路をそもそも使わない設計に切り替わったため）。**両方 not_planned・relates-to のコメントリンクのみで十分**（dedupe_skeptic の keep/dup 判定枠組みはこの組には適用しない）。

## #182 / #292（dedupe_skeptic への回答・一部譲歩）
Round 1 では両方を独立に CLOSE 可（completed）とだけ判定したが、dedupe_skeptic の「#182 が #292 を包含する安全な重複」という分析には **譲歩する**。

**結論: #182 を completed、#292 は duplicate（#182 参照）で閉じるのが正しい。** 両方を別々に completed で閉じると、同一コミット（`app/globals.css` `f53bbbf` 相当・`loading-indicator.tsx` の animate-pulse 除去）を指す「完了記録」が 2 つ並立し、後から見た人が「どちらが正の記録か」を混乱する。#182 の方が原因分析が深い（不透明時点で既に 4.41:1 未達という根本原因まで特定）ため keep として妥当。

## #55 / #85 / #144 / #305（docs_trace への回答・1 件ずつ結論）

docs_trace の原則（「後継 Issue 起票後に close」）に一律賛成はしない。**このパターンが適切なのは #305 のみ** で、#55・#85・#144 は性質が異なる。

### #55 — **close しない（open のまま）。後継 Issue も不要**
Round 1 で確認した通り、この Issue の完了条件そのものが **今この瞬間も未達**（増減ログ最新 98,265B / 本文要約 ~92.0KB(91,960B相当) / 実測 100,890B の 3 値不一致が現在進行形）。これは「別の新しい問題」ではなく「この Issue が元々測っていた問題」そのものが継続している。後継 Issue を立てると同じ完了条件を持つ Issue が 2 つ並ぶだけで、docs_trace が懸念する「なぜ Issue が立て直されたか経緯が追えなくなる」問題を自ら作ることになる。**この Issue を open のまま残し、今回の実測差分（98,265→100,890）をコメントで追記するのが正しい。**

### #85 — **close しない（open のまま）。後継 Issue も不要**
残作業（`agent-team-summary.md` / `CLAUDE.md` への `--under` 使用の明記）は完了条件の 3 項目中 1 項目であり、かつ対象ファイルへの 1〜数行の追記で完結する軽微な残作業。CP-1 の「スコープ外の改善は別 Issue を立ててから着手する」はここでは逆方向に働く——この残作業は #85 の完了条件そのものであり、スコープ外の改善ではない。**新規 Issue に切り出すのは Issue 管理コストが残作業量に見合わない。#85 を open のまま、未達項目だけをチェックリストに残すべき。**

### #144 — **close しない（open のまま）。後継 Issue も不可（同じ問題を再生産するだけ）**
docs_trace は「#144 は先送りコメントが明記されているなら後継 Issue を起票してから close すべき」と述べたが、この組み立ては #144 には当てはまらない。**コード側のコメントが名指ししている先送り先は、まさに #144 自身**（`app/api/auth/logout/route.ts:14-15` 「専用の CSRF トークン導入は Issue #144 に残る」）。ここで #144 を close して新しい Issue #N を起票しても、コード内のコメント文字列を `#144` → `#N` に書き換えない限り同じ「closed issue への dangling reference」問題が形を変えて再発するだけで、何も解決しない。**正しい処理は #144 を open のまま残すか、close するなら「先にコード側のコメントを編集して forward reference を外し、sameSite:lax を正式に十分な対策と再判定した」という決定を #144 のコメントと両方に記録してから close する**、のどちらか。後継 Issue の起票は不要（起票してもコード側の参照を書き換える手間は同じで、番号が変わるだけ）。

### #305 — **close（not_planned）+ 後継 Issue 起票、が正しい（docs_trace のパターンが唯一当てはまる）**
#144 と違い、#305 は当初の症状（`search-repositories.ts` の `sort=gem-index` 経路が 500 化する）が **コードごと物理的に消滅** しており、そのファイルには関連する参照が 0 件（grep 確認済み）。一方で発見した設計欠陥（`GemDigestPort` の例外安全性）は **別ファイル**（`get-daily-digest.ts`）の **別の呼び出し経路** に移動している。#144 と違い、コード側に「Issue #305 へ先送り」という明示的な forward reference は無い（`get-daily-digest.ts` にはそのような一文がない）ため、#305 を close しても dangling reference にはならない。**#305 は not_planned で close し、「`GemDigestPort` 例外安全性のテスト整備（`get-daily-digest.ts` 側、`page.tsx` の `.catch` に対する回帰テスト欠如）」を新規 Issue として起票するのが正しい。**

## priority_calibrator への確認
#288・#182 を「クローズ前提で high から除外」とする判定は、evidence_auditor の実測結果（両方とも完了条件を満たしファイル・テストで確認済み）と **整合する**。異論なし。ただし #182 を close する際は上記の通り #292 を duplicate として道連れにすること（priority 側の処理対象からも #292 を outcome=closed(duplicate) として除外するのを忘れずに）。
