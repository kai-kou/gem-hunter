<!--entry
author: process_design
round: 1
kind: claim
ts: 2026-08-19T09:51:45+09:00
-->

# process_design（プロセス設計）ラウンド1

主担当: 争点 B（常時チーム編成の恒久化）・C（レビュー・レトロの差し込み位置）

## B) 協調モード決定表（sp × 性質）

既存 2 ファイルの役割は変えない: `agent-team-summary.md`＝議論型/fan-out の **選び方の仕組み**（汎用）、
`session-sprint-rules.md` §2＝**スプリント編成欄の既定値**（スプリント固有）。今回の恒久指示は
「スプリント編成欄の既定値」を変える話なので、**書き込み先は session-sprint-rules.md §2 の実体 1 箇所のみ**。
agent-team-summary.md は変更不要（sp:8 の議論型トリガーとして「既存 Layer 2 トリガー」を参照するだけで足り、
新しい振り分け軸を増やすと 2 SSOT 化する）。

| スプリント性質 | sp | 既定モード | 単独実行 |
|---|---|---|---|
| Step4 実装（新規/機能） | 1 | fan-out 最小 2 役割（実装+検証） | **不可**。例外は「1 ファイル・typo/設定値 1 個」のみ、理由 1 行を編成欄に記録 |
| Step4 実装 | 2〜3 | fan-out 3 役割以上（既存どおりファイル非重複分割） | 不可 |
| Step4 実装 | 5 | fan-out 3 役割以上並列 | 不可（現行のまま） |
| Step4 実装 | 8 | 着手前に discussion-review 1 ラウンド（設計方針の相互検証）→ fan-out 実装へ | 不可 |
| リファインメント（self-improvement-loop 整理モード） | — | discussion-review（優先度判断は複数視点が必要。飼い主指示(1)が名指し） | 不可 |
| スプリントレビュー（新設・後述 C） | 全 sp | fan-out 2 役割（受け入れ判定＋残課題仕分け）。sp:8 のみ discussion-review | 不可 |
| レトロスペクティブ | 全 sp | 既存の 3 役割並列（実質 fan-out）のまま容認 | 該当なし |

**編集内容（session-sprint-rules.md §2、該当行の置き換え）**:
> 旧: 「既定は役割分担型 fan-out（`sp:5` 以上はファイル非重複分割で並列 / `sp:1`〜`sp:3` は単独実行）。議論型 `discussion-review` は既存 Layer 2 トリガーと `SD-3` グレーゾーン精査に限定し、使う場合のみ理由を添える。」
> 新: 「飼い主の恒久指示により **単独実行は禁止**。既定は役割分担型 fan-out（メインはオーケストレーターに徹し実装コードを自分で書かない。`sp:1`〜`2` は最小 2 役割 / `sp:3`〜`5` はファイル非重複分割で 3 役割以上 / `sp:8` は着手前に議論型 `discussion-review` を 1 ラウンド追加してから fan-out 実装へ）。例外は『1 ファイル・機械的変更（typo・設定値 1 個）』のみ許容し、単独実行を選んだ理由を編成欄に 1 行記録する。議論型のその他の用途（既存 Layer 2 トリガー・`SD-3` グレーゾーン精査）は `agent-team-summary.md` のまま。」

`sprint-development-rules.md` は不変更（4 規律は「作り方」の規律で「編成」は範囲外）。§5 参照表の
「`session-sprint-rules.md`（単位と `sp:N`）」を「（単位・`sp:N`・チーム編成）」に 1 語追記するだけで足りる。
**SD-5 は新設しない**（同じ規則を 2 か所に実体化することになり D の懸念どおりドリフトの温床になる）。

## C) レビュー・レトロの差し込み位置

sprint-cycle-router は「1 firing = 該当ブランチ 1 つ」。Step4 は同一 firing 内で完結しないことがあり
（4-6 で pr-review-watcher に継続 → 予算切れなら次 firing は Step2/Step3 が拾う）、レビュー・レトロを
決定木の新規トップレベル Step にすると、マージが Step2/Step3/Step4 のどれ経由でも二重管理になる。

**結論: 決定木は変更しない。フックは `pr-review-watcher` 内部（マージ＋公開反映の直後、完了報告の前）に 1 箇所だけ追加する。**
理由: マージに到達する経路（Step2 拾い上げ／Step3 再開／Step4-6 直行）が全て最終的に pr-review-watcher の
「マージ→公開反映」を通るため、ここに 1 回差し込めば経路によらず必ず 1 回だけ実行される（決定木側の
分岐追加が不要＝「1 firing = 1 ブランチ」の設計と衝突しない）。

**発火条件**: PR 本文に `Sprint Goal:` 行がある（＝ SP-n スプリントの PR）場合のみ。改善 Issue・retro-try の
PR は対象外（それぞれ自分のレーンの retro/レビューを持つか、対象外でよい）。

**手順（pr-review-watcher SKILL.md への追記案）**:
1. マージ＋公開反映が完了したら、対象 Issue が `SP-n` 規約タイトルか判定
2. 該当すれば Sprint Review を fan-out 2 役割（受け入れ判定 / 残課題の次 firing 送り仕分け）で実行し、
   結果を **対象 Issue へのコメント**（Sprint Planning コメントの続き）として記録。`sp:8` のときだけ
   discussion-review に切り替え、結論サマリーのみ Issue コメントに書いて全文はホワイトボードを参照させる
3. 続けて `retrospective` スキルを起動（既存 3 役割並列のまま）。Try は既存どおり `type:retro-try` で Issue 化
4. 上記が未実施のまま完了報告しない（`pr-review-watcher` の完了条件チェックリストに 1 項目追加）

**記録の置き場所（SSOT を増やさない）**:
- Sprint Review の判定・根拠 → 対象 SP-n Issue のコメント（新規ディレクトリを作らない）
- sp:8 の discussion-review 全文 → `content/discussions/sprint-review-SP-{n}-{日付}/`（既存の `discussion-review` スキルの保存規約をそのまま流用）
- Retro（KPT・Try）→ 既存 `retrospective` スキルの出力仕様どおり（変更提案なし。呼び出しが漏れていた点だけを塞ぐ）

## コスト影響（概算・1 firing あたり）

- 実装 fan-out 強制（sp:1〜2 も最低 2 役割化）: 追加 **+15〜25K トークン/firing**（役割ごとのドキュメント再読込 + 集計サマリー）。sp:1 の typo 例外を残すことで最小変更の firing まで肥大化させない
- sp:8 着手前 discussion-review 1 ラウンド: 参加者 3〜5 名 × (プロンプト 5K + 出力 3K) + 統合 5K ≈ **+45K トークン**（スプリントの最初の 1 回だけ・繰り返し発生しない）
- Sprint Review（fan-out 2 役割）: 2 × (8K+3K) + 統合 3K ≈ **+25K トークン/マージ**
- Retro（3 役割並列、既存仕様の呼び出し漏れを塞ぐだけ）: 3 × (10K+4K) ≈ **+42K トークン/マージ**（今まで呼ばれていなければ純増、呼ばれていれば増分ゼロ）
- 合計: 通常スプリント（sp:3、マージ 1 回）で概算 **+80〜90K トークン**、sp:8 は 着手時 +45K が上乗せで **+125〜135K トークン**。ドル換算・実測較正は既存の `sprint_session_metrics.py` 相当の枠組みで後日検証すべき（本ラウンドでは概算のみ）
