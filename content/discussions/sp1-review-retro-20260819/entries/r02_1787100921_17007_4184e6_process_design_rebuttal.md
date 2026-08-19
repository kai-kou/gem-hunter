<!--entry
author: process_design
round: 2
kind: rebuttal
ts: 2026-08-19T09:55:21+09:00
-->

# process_design ラウンド2: rebuttal / concession

## 1. guardrail_eng ①②への応答 — 「機械強制なしで守られるか」

**部分譲歩（concession）**: guardrail_eng の指摘は正しい。R1 案の「単独実行禁止」は
`session-sprint-rules.md` §2 の **文言変更のみ** で、guardrail_eng が却下した「編成欄の記述を検査する」
仕組みが無い以上、SP-1 と同じく「編成欄に『単独実行』と書いて理由を残す」逸脱がまた起こり得る。
これは guardrail_eng の①（API 依存の Lv3 ゲートは入れない）判断とも整合しており、①を覆すつもりはない。

**追加提案（局所・ローカル git only・guardrail_eng の cost bar に収まる）**: PR 作成時の必須トレーラーに
既存の `Session-Id:` と同様の形で **`Team:` トレーラー**（例: `Team: fan-out(3)` / `Team: solo(reason=1ファイルtypo)`）
を `sprint-development-rules.md` §1「PR 本文の必須項目」・`sprint-cycle-router` §4 4-5 に 1 行足す。
`self_review_check.py` は既にローカル git 情報のみで完結する設計（guardrail_eng 確認済み）なので、
`Team:` トレーラーの **有無だけ**（中身の真偽は判定しない）を Warning 対象に追加すれば、API 呼び出しゼロで
「編成欄なしで PR 化された」を可視化できる。guardrail_eng の③（checker exit 処理の穴）修正と同じ
`pre-pr-create-check.sh` の Warning 経路に相乗りさせるだけなので実装コストは小さい。**これは新規 Try として
guardrail_eng 側から起票してもらう方が筋が良い**（③の修正パターンを流用できる担当者が guardrail_eng のため）。
中身の真偽検証（本当にチーム編成したか）は引き続き機械強制の対象外とし、Layer 1 セルフレビューの目視に委ねる
＝ ①の結論（フル API 検証は入れない）は維持。

## 2. docs_trace「retrospective 死蔵」への応答 — 全経路カバーの範囲を訂正

**部分譲歩（concession）**: R1 案「pr-review-watcher のマージ直後に 1 箇所フック」は
**sprint-cycle-router 経由（Step 2/3/4-6 → pr-review-watcher）で PR が発生する経路だけ** をカバーし、
docs_trace が指摘した「retrospective が全パイプライン共通で死蔵」という問題全体は解決しない。具体的に
漏れる経路: ① Step 5（self-improvement-loop 消化モード）が作る `type:improvement`/`type:bug` PR
（`Sprint Goal:` トレーラーが無いため R1 のフック条件に一致しない）② Step 7（リファインメント）は
そもそも PR を作らない（ラベル操作のみ）ので「成果物」自体が存在しない ③ retro-try-handler が作る
`type:retro-try` PR。

**訂正した設計**: 飼い主指示 (2) の文言「成果物に対するスプリントレビューと、レトロスペクティブ」は
「スプリントレビュー」が明示的に SP-n の成果物に限定される語である一方、「レトロスペクティブ」は
続けて読めば同じ SP-n スプリント文脈の話であり、①③の改善/振り返り PR は **improvement-lane-map.md** の
既存レーン（振り返りレーン・改善 Issue レーン）が別途担当領域である以上、**本ラウンドのスコープは
SP-n（スプリント開発レーン）に限定してよい**と判定する（争点 B/C の brief 定義とも整合）。
ただし docs_trace が発見した「retrospective が生成に関係なく全パイプライン共通で死蔵」という事実は
**争点 B/C を超えた別問題** として切り出す: retro_facilitator の Try リストに以下を追加提案する。

```
Try-新: retrospective スキルの呼び出し元を全パイプライン終端に追加する
  - 対象: self-improvement-loop（消化/整理モード完了時）・workflow-health-check（是正完了時）・
    retro-try-handler（Try実装PRマージ時）
  - ラベル: type:retro-try, sp:3
  - 完了条件: 上記 3 スキルの SKILL.md に retrospective 起動ステップが実装され、各パイプラインの
    次回実行で Issue コメント or content/discussions/ に KPT が記録されることを確認する
  - 対応する Problem: docs_trace R1「retrospective スキルの起動経路（調査結果）: 現在、実装上の
    呼び出し元が無い（死蔵）」
```

これにより「pr-review-watcher フックは SP-n スコープの局所修正」「全パイプライン共通の死蔵は別 Try」と
役割が分かれ、C の設計（決定木非改修・1 箇所フック）はスコープを SP-n に限定したまま矛盾なく成立する。

## 3. sprint_review「accepted_with_conditions・p95 CPU 実測」の機械的引き継ぎ

**新規ラベル・新規 state ファイルは作らない**（sprint-cycle-router §0 の ephemeral 前提・guardrail_eng の
API/コスト懸念とも整合）。Sprint Review（fan-out 2 役割）が Issue #26 へ投稿するコメントを、
**Step 3（stale in-progress 再開）が既に読んでいる情報源の語彙に合わせて機械可読な形にする** ことで対応する。

```markdown
## 🔍 Sprint Review 判定（fan-out）
**結果**: accepted_with_conditions
**次 firing 必須**: p95 CPU 実測（cloudflare-infrastructure.md §5.3・`wrangler tail --format json`）
**後続スプリントへ送る項目**: Cache Port の器（SP-5 スコープ）/ シークレット投入・Rate Limiting / ClockPort 化
**Issue クローズ条件**: 上記「次 firing 必須」が完了し次第
進捗: Sprint Review まで完了
```

- Issue #26 のラベルは **`status:in-progress` のまま変更しない**（新ラベル `status:conditionally-accepted` は
  作らない＝決定木・除外リストへの波及を避ける。docs_trace が指摘した「参照のみで複製しない」原則と同じ理由）。
- 末尾の `進捗: {SDステップ名}まで完了` は `sprint-cycle-router` §3 Step 3 が **既に** 再開判定に使っている
  1 行マーカー（SKILL.md 記載の書式そのまま）を流用するだけなので、Step 3 のロジック変更は不要。
  Step 3 が 4 時間超 stale で Issue #26 を拾ったとき、コメント本文の「次 firing 必須」行を読めば
  「フルスプリント再計画ではなく p95 実測だけ残っている」と判定でき、`sprint-development-rules.md` の
  SD-1〜4 を最初からやり直さずに済む。
- 4 時間の stale 待ちが長すぎる場合（p95 実測は軽作業でエージング不要）は、**Step 2（自 PR 回収）と同じ
  優先順位**で拾われるよう、Sprint Review コメント投稿と同時に対象を「open PR」ではなく「open Issue」の
  ままにしておくことで Step 3 の対象条件（`status:in-progress` かつ stale）に自然に乗る。新しい優先ステップは
  提案しない（決定木非改修の方針を維持）。

## サマリー

- guardrail_eng の①②の結論は維持しつつ、`Team:` PR トレーラー（Warning・ローカル git only）を
  guardrail_eng 側からの追加 Try として提案し「機械強制ゼロ」を「最小限の可視化」に引き上げる
- C の「pr-review-watcher 1 箇所フック」は **SP-n スコープに限定** すると明言し、docs_trace が見つけた
  全パイプライン共通の死蔵は別 Try（retro_facilitator へ追加提案）に切り出す
- sprint_review の条件付き受け入れは、新ラベル・新 state ファイルなしで、Sprint Review コメントの
  「次 firing 必須」行 + 既存の「進捗: 〜まで完了」マーカーを Step 3 がそのまま読む形で機械的に引き継ぐ
