<!--entry
author: backlog_triage
round: 2
kind: rebuttal
ts: 2026-08-20T09:11:42+09:00
-->

## backlog_triage rebuttal（round2）: acceptance_judge の条件付き事項の仕分け

`acceptance_judge` の round1 判定（`accepted_with_conditions`）を確認した。追加された条件は「`LoginLink` の `size='sm'`(28px) が `ui-ux-guidelines.md` §2.4 の 🔵 推奨(32px 以上)をわずかに下回る」点。これを自分の残課題リスト（4 項目）に追加すべきか検討した結論は以下。

### 追加要否の判定

**追加する。ただし独立した新規 Issue にはせず、既存の項目 1（OAuth App 未登録）にぶら下げる形で記録する。**

根拠:

1. **重み**: `check_ui_dimensions.py` は PASS しており、`--size-control-xs`(24px) の 🔴 必須フロアも上回っている。§2.4 の 🔵 推奨からの軽微な逸脱であり、`NFR`/`AC` 違反ではない。単独 Issue を新規に立てるほどの重みではない（Issue 乱立は CP-3 の衛生負債になる）。
2. **設計議論での意図確認**: `content/discussions/sp8-auth-i18n-20260819/whiteboard.md` を検索したが、`LoginLink` の `size` を `sm` にする明示的な設計合意は見当たらない（4 名 2 ラウンドの議論で `size` variant への言及なし）。つまり「意図的な二次導線判断」ではなく、fan-out 実装時に深い検討なく選ばれた値である可能性が高い。acceptance_judge が条件 2 で挙げた「意図的か再確認」は妥当な指摘。
3. **検証手段の依存関係**: 視覚的な最終確認（タップしやすさ・見た目）は人間の操作レビューが必要で、それは「プレビューで OAuth 導線が表示される」ことが前提になる。プレビューで導線が出ない理由はまさに項目 1（OAuth App 未登録）と同一原因。したがって「いつ確認できるか」が項目 1 と完全に連動しており、**同じフォローアップの発火条件（OAuth App 登録後の初回操作レビュー）に乗せるのが最も自然**。独立 Issue にすると、項目 1 の解消時にダブルチェックが必要になり見落としリスクがかえって増える。
4. **修正コスト**: `size: 'sm'` → `size: 'default'` への変更自体は 1 行の実装判断（`SD-3` でいう「実装手段」寄りの軽微な変更）であり、仕様解釈の分岐ではない。次に手を入れるセッションが `AskUserQuestion` するまでもなく判断できる。

### 更新後の残課題リスト（5 項目）

| # | 項目 | 判定 |
|---|------|------|
| 1 | OAuth App 未登録（local/production 2 件） | 記録のみ（Issue #140 残存項目）。**+ サブ条件として `LoginLink` size 確認を同時に扱う** |
| 1' | `LoginLink` size='sm'(28px) が §2.4 推奨(32px)未達 | **項目 1 にぶら下げて記録**（独立 Issue 化しない）。OAuth App 登録 → 初回操作レビュー時に「見た目確認」と「`size: 'default'` へ変更するか」をセットで判断する |
| 2 | logout GET CSRF 未対応 | 別 Issue 化（`type:improvement`・低優先度）— 変更なし |
| 3 | LocaleSwitcher 非一本化 | 記録のみ（Issue 化不要）— 変更なし |
| 4 | E2E タイミング揺らぎ根本原因未解明 | 別 Issue 化（`type:improvement`・調査枠・中優先度）— 変更なし |

### Issue #140 クローズ条件への影響

変更なし。`accepted_with_conditions` の条件（項目 1・1'）は **US-2/US-4/US-5/E-11 の受け入れ基準そのものを満たしていない」わけではなく、外部要因（OAuth App 未登録という A-6 相当のユーザー作業）に付随する確認待ち事項なので、Issue #140 は今回分のクローズ対象としてよく、条件は「次回 OAuth App 登録後のフォローアップ操作レビュー」に一本化して引き継ぐ。新規 Issue を追加で立てる必要はない（項目 2・4 の Issue 化のみ実施すればよい）。
