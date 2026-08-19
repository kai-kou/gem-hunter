<!--entry
author: guardrail_eng
round: 2
kind: rebuttal
ts: 2026-08-19T09:56:17+09:00
-->

## guardrail_eng round2: rebuttal / concession

### 1. process_design の具体案を読んだ → ①「入れない」は維持。ただし「気づき方」を1点追加提案する

process_design の書き換え案（session-sprint-rules.md §2「単独実行は原則禁止・例外は編成欄に理由1行」）は
**ドキュメント規律の強化** であって、検知手段そのものではない。私が① を却下した理由（Issue コメントは
API 経由でしか読めない／self_review_check.py は git ローカル情報のみで完結する設計／Lv3 ブロッキング
ゲートに API 依存を持ち込むと 403 で無関係な PR まで巻き込む）は、この書き換え後もそのまま成立する。
**結論は維持する: bash hook（Lv3・PR 作成前）に①のチェックは入れない。**

再発時に誰がどう気づくか、を具体化する:
- 現状（process_design の C 案どおりに実装しても）**気づく経路が無い**。retro_facilitator の今回の
  KPT（P5）が拾えたのは「セッション内の当事者が自己申告した」からで、これは再現性のある検知ではない
  （単独実行を選んだセッションが、自分でそれを Problem として書かない限り誰も気づかない）。
- **代替案（process_design への提案・追加コストほぼゼロ）**: process_design の C 案が新設する
  「マージ直後の Sprint Review fan-out 2 役割」は、そもそも対象 Issue のコメント履歴を読む
  （受け入れ判定の根拠にするため）。そこに **「Sprint Planning コメントの編成欄が『単独実行』かつ
  sp:1 の 1 ファイル例外に該当しない場合は Problem として記録する」の 1 行を混ぜ込むだけ**でよい。
  これは bash hook ではなく **エージェント駆動のステップ**（既に MCP アクセスを正規に持つ）なので、
  私が①で懸念した「API 403 が Lv3 ゲートを無関係にブロックする」リスクが発生しない
  （失敗しても Sprint Review の結果精度が落ちるだけで、PR 作成自体は止まらない）。
  → これは私の **部分的な譲歩（concession）**: 「機械強制（hook）」としては入れないが、
  「プロセス埋め込み（Sprint Review ステップの 1 チェック項目）」としてなら process_design 案に
  タダ乗りできる。process_design 側で C 案の Sprint Review 手順に 1 行追記することを推奨する。

---

### 2. 記録先が決まった場合、② は実装可能になるか → **可能。ただし当初案とは実装点が変わる**

process_design の C 案で記録先が確定した（Sprint Review 判定＝対象 Issue コメント／sp:8 の議論全文＝
`content/discussions/sprint-review-SP-{n}-{日付}/`／Retro＝既存 retrospective スキルの出力）。
**これは私が round1 で前提にした「ローカル grep で拾える」を裏切る**: 主たる記録は Issue コメント
（API 経由）であり、`content/discussions/` はあくまで sp:8 の副産物にすぎない。したがって
round1 で出した「PostToolUse(issue_write) + ローカル grep」案は **そのままでは機能しない**
（sp:8 以外は grep 対象が存在しないため常に空振り Warning になる）。

**修正した最小実装案**（process_design の C 案が「pr-review-watcher 内部で 1 箇所」と定めたことに乗る）:

- **場所**: 新規 hook ファイルは作らない。既存の `.claude/hooks/post-merge-publish-check.sh`
  （`PostToolUse` / matcher `mcp__github__merge_pull_request`・既に repo root で動く）に **+12〜15 行**:
  マージされた PR の本文（`tool_response` から取得可能）に `Sprint Goal:` 行があれば、
  additionalContext に「この PR は Sprint Review + Retro が必須（process_design C 案）。
  完了報告前に対象 Issue へ Sprint Review コメント／retrospective スキルの実行を確認すること」
  という **Warning リマインドを注入するだけ**（実施有無の検証はしない＝ API 呼び出し不要）。
- **検証は Stop 側に置く**: `.claude/hooks/stop-completion-report-check.sh`（既に Stop で走り、
  同種の完了報告フォーマット検査を行っている）に **+20〜25 行**: `orchestrator-directive.sh` が
  既に使っている手法（**transcript JSONL をローカルファイルとして末尾から読む＝ API 呼び出しゼロ**）
  を流用し、直近でマージされた `Sprint Goal:` 付き PR がある場合に、そのセッションの transcript 内で
  `mcp__github__add_issue_comment`（または `discussion_whiteboard.py post`／`retrospective` 系の
  ツール呼び出し）が merge 後に発生したかどうかを検索する。**見つからなければ Warning**（Stop を
  ブロックしない＝ exit 0 + メッセージ）。
- **Warning か Error か**: **Warning のみ**（両方の追加箇所とも）。理由は③と同じ（下記参照）。
  加えてキーワードマッチである以上、Issue コメントの文言が想定外だと false negative になりうるため、
  Error にすると正しく実施したセッションまで誤ブロックする恐れがある。
- **合計コスト**: 新規ファイル 0・既存 2 ファイルへの追記のみ・**35〜40 行**。settings.json の
  matcher 追加も不要（両フックとも既に配線済み）。round1 で見積もった「新規 hook 1 本 40〜50 行」より
  むしろ安くなる（既存の仕組みに相乗りできるため）。
- 残る前提条件: process_design の C 案（「pr-review-watcher 内部 1 箇所」「Sprint Goal: 行での判定」）が
  そのまま採用されること。ここが変わればこの実装点も変わる。

---

### 3. ③ のパッチ断片（そのまま適用可能）

対象: `.claude/hooks/pre-pr-create-check.sh`（現在の L153-169・実測済み行番号）

**変更前**（L162-169）:
```bash
  if [ "$check_exit" -eq 1 ]; then
    hook_block "[pre-pr-create-check] セルフレビュー機械チェックで Error を検出したため PR 作成をブロックしました。

${check_output}

Error を修正してから PR 作成を再実行してください（チェックシート: docs/rules/self-review-checklist.md）。"
  fi
fi
```

**変更後**:
```bash
  if [ "$check_exit" -eq 1 ]; then
    hook_block "[pre-pr-create-check] セルフレビュー機械チェックで Error を検出したため PR 作成をブロックしました。

${check_output}

Error を修正してから PR 作成を再実行してください（チェックシート: docs/rules/self-review-checklist.md）。"
  elif [ "$check_exit" -ne 0 ]; then
    # self_review_check.py 自体の異常終了（内部未捕捉例外 exit=2 / 外側 `timeout 60` による
    # プロセス kill exit=124 等）。ブロックはしない（fail-open・無人ルーティンを止めない）が、
    # 従来は check_output が誰にも表示されず握りつぶされていた（SP-1 で実際に発生した事故・
    # content/discussions/sp1-review-retro-20260819）ため可視化する。
    check_output="${check_output}
[pre-pr-create-check] self_review_check.py が exit ${check_exit} で異常終了しました。セルフレビュー機械チェックが実質未実行のまま PR 作成が続行されています。原因を確認してください（一時的な負荷等でなければ type:bug Issue 化を検討）。"
  fi
fi
```

対象2: 同ファイル L183（`grep -q 'Warning'` の条件）。「checker error」文言は `Warning` を含まないため
上記追記だけでは Step 6 の additionalContext に載らない。ここも変更する。

**変更前**（L183）:
```bash
if printf '%s' "$check_output" | grep -q 'Warning'; then
```

**変更後**:
```bash
if printf '%s' "$check_output" | grep -qE 'Warning|異常終了'; then
```
（`check_exit -eq 0` かつ Warning 皆無の通常パスでは `check_output` が空文字のままなので、この条件緩和が
新たな誤爆を生むことはない。追記した文言に固定で「異常終了」を含めているため単純な文字列一致で足りる。）

**誤検知でルーティンを止めない根拠**:
1. 両変更とも **Warning 経路（additionalContext 注入）のみ** で、`hook_block`（exit 2 ブロック）を
   一切追加していない。`is_pr_create` 判定・既存の Error 分岐（L162）には触れない。
2. `check_exit -ne 0` という条件は「0（正常）でも 1（Error 検出）でもない」という **消去法** であり、
   「チェッカーが正常に完走して違反ゼロと判定した」ケースを誤って拾うことは構造的にありえない
   （0 と 1 は既存分岐が先に消費するため、ここに来る時点で必ず異常系）。
3. sprint-cycle-router のような無人ルーティンにとって、この変更は「今まで見えなかった異常を
   Claude のコンテキストに 1 行足す」だけであり、PR 作成のシーケンス自体（成功/失敗の分岐）は
   一切変えていない。

---

### retro_facilitator の Try-2 との相違点（要調整）

Try-2 の完了条件は「非ゼロ終了で **Error 扱い** にする」と書かれており、これは私の③提案
（Warning のみ・fail-open 維持）と **正面から矛盾する**。私はここで **Error 化には反対** する:
- Error 化（`check_exit -ne 0` も `hook_block` する）は「チェッカーが（違反ではなく）単に落ちた」
  ケースで PR 作成を恒久ブロックする。sprint-cycle-router は人手の即時介入を前提にしていない
  無人ルーティンであり、環境要因（一時的な負荷・依存パッケージの一過性不調等）でチェッカーが
  タイムアウトするだけで PR が二度と作れなくなるデッドロックを持ち込むリスクがある。
- 今回の実バグ（57 秒バックトラック）は「チェッカーが違反を見逃した」のではなく
  「チェッカーが **実行すらできなかった**」ケース。この 2 つは意味が違う: 後者を Error 化するのは
  「アラームが鳴らなかったら家を燃やす」に等しい過剰反応で、原因（バックトラック）を潰した今回のように
  **根本原因を直せば再発しない** 類の一時的異常にまで永続ブロックを適用するのは不釣り合い。
- Try-2 の意図（「サイレント通過を許さない」）自体には完全に同意する。**私の対案は「可視化を Error
  ではなく Warning + additionalContext で達成する」**（本ラウンドの③パッチ）。retro_facilitator には
  Try-2 の完了条件文言を「非ゼロ終了を **Warning として可視化** し、握りつぶさない」に修正することを
  提案する（Issue タイトル・sp 見積もりはそのままでよい）。
