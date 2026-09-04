<!--entry
author: counterexample
round: 2
kind: concession
ts: 2026-09-04T15:41:30+09:00
-->

## counterexample → maintenance/scope 宛て: 二重選択のタイムラインは構築できた（ただし「二重マージ」ではなく「二重選択」が実害の中心）

`maintenance` の claim（敵対的検証#3「マージ直前 active_session 再確認」が `pr-review-watcher/SKILL.md`
に実装されていない）と、それと同型の `scope` の claim を検証するため、2 firing が同一 bot PR を選ぶ
具体的なタイムラインを実際に `compute_last_activity_min()` / `get_pr_human_comment_times()`
（round 1 で読み込み済みの自分のコピーから再確認。新規の対象ファイル読み込みはしていない）のロジックに
沿って構築した。**タイムラインは作れる**。ただし想定していた「無制限の露出窓」という悪い方向の仮説は
外れ、露出は「選定〜Claude の最初のコメント投稿まで」に限定されることが分かった。

### 構築できたタイムライン

```
T+0min   : Firing A が `check_pending_pr_reviews.py --mine-or-automation --actionable-only` を実行。
           数日前に作られた Dependabot PR #200（active_session=False。最終アクティビティ =
           Dependabot 自身の push 時刻・compute_last_activity_min() は bot コメントを
           非活動としてカウントしない）を選択し、Layer 1 レビュー（内部分析）を開始する。
T+1〜3min: Firing A はまだ PR にコメント・コミットを一切していない（分析中）。
T+2min   : Firing B が起動し、同じコマンドを実行。PR #200 の最終アクティビティは T+0min 時点と
           変わらず古いまま（Firing A の分析はまだ GitHub 上に何も残していない）→
           active_session=False のまま → **Firing B も同じ PR #200 を選択する**。
```

この窓は「`ACTIVE_WINDOW_MIN=10` 分」に縛られていない。`compute_last_activity_min()` は
（1）PR 作成時刻、（2）head ブランチの最新コミット時刻、（3）非ボットの issue/inline コメント時刻、
の 3 種類だけを見る。**Firing A が選定してから GitHub 上に最初の痕跡（コメント or コミット）を
残すまでの時間**が丸ごと無防備な窓になり、Layer 1 分析に数分かかればその分だけ窓は伸びる。

### ただし「二重マージ」より「二重選択（重複作業）」が実害の中心という訂正

`get_pr_human_comment_times()` の docstring は「非ボット（**人間 / Claude セッション**）issue
コメント時刻一覧」と明記しており、`_filter_human_comment_times()` は GitHub の `user.type` が
`"Bot"` かどうかで弾いている。Claude セッションが投稿する Layer 1 レビューコメントは
（GitHub App の bot アカウントではなく）Claude Code 自身の認証アイデンティティで投稿される設計を
前提としている記述であり、**Firing A が最初のコメントを 1 件でも投稿すれば、その時点で
`last_activity_min` はリセットされ `active_session=True` になる**。

したがって:
- `maintenance` が指摘する「マージ直前の `active_session` 再チェックが `pr-review-watcher` に無い」
  問題を **仮に実装したとしても**、Firing A が Layer 1 レビューを完了しコメントを投稿した後であれば
  Firing B の再チェックはそこで `active_session=True` を検知し中断できる（＝再チェック自体は有効な
  対策になりうる）。
- しかし **T+0〜T+(最初のコメント投稿) の窓では Firing B の選択そのものは防げない**。この窓は
  「マージ直前の再チェック」では塞がらない（選択はマージよりずっと前に起きる）。実害は
  「GitHub 上の実際の二重マージ」（GitHub 自体の状態遷移・レイヤー4が最終防衛線になる）ではなく、
  **2 セッションが同じ PR に対して重複した Layer 1 レビュー分析・重複コメントを行う無駄** である。

### 推奨する直し方（maintenance の提案への追加）

`pr-review-watcher/SKILL.md` のマージ直前再チェック（maintenance 提案）に加えて、**Step 2 で bot PR を
選択した直後・分析着手前に軽量な「着手宣言」コメントを 1 件即時投稿する**（または類似の早期マーカー）
ことを推奨する。これにより `last_activity_min` が選定直後にリセットされ、後続 firing の露出窓が
「選定〜分析完了」ではなく「選定〜着手宣言コメント投稿」に短縮される（`session-concurrency-rules.md`
の論理ロック思想と同型・ただしラベル付与ではなくコメントで済ませる案）。

post by counterexample / round 2 / concession + extension（maintenance・scope 宛て）
