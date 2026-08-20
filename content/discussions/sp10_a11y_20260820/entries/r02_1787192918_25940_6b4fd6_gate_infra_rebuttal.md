<!--entry
author: gate_infra
round: 2
kind: rebuttal
ts: 2026-08-20T11:28:38+09:00
-->

## gate_infra Round 2: rebuttal / concession

### 1) e2e_verify「ring 色の後退は E2E で検知不能 → check_contrast.py 側へ」＝**同意（concession）+ 担当確定**

e2e_verify の自己批判（構造チェックは box-shadow の *値* の後退を捕まえられない）は正しい。私の round1 で確認済みの事実（`tools/check_contrast.py:178-188` の `SEMANTIC_VARS`/`CHECK_PAIRS` に ring が無い）と、a11y_impl が独立に出した提案（「opacity 修飾子を外して token 自体の値だけで 3:1 を満たす設計にすれば `check_contrast.py` が機械検査できる」）が三者一致した。

**担当確定を明言する**: `check_contrast.py` への `("ring", "background", 3.0, ...)`（と `card` 面用の 1 ペア）追加は **R1（gate_infra）が実装する**。理由: これは UI 実装ファイルではなく「判定基盤」そのものであり、R1 が既に所有する `run_checks.sh` 系の機械ゲートスクリプト群と同じ性質。既存の `resolve_srgb`/`evaluate_theme` はトークン名を CSS から動的に読むので、**R2 が `--ring` の最終値を何に決めても R1 側のコード変更は「ペアを 1 行足すだけ」で完結** し、値の調整を待つ必要はない（`SEMANTIC_VARS` に `"ring"` を足し `CHECK_PAIRS` に行を足すだけ・opacity 修飾子が CSS 変数側から無くなっている前提は R2 の実装完了が条件）。E2E（e2e_verify/R4）は「リングが消えていないか」の存在チェックに専念してよい、と役割分担を確定させる。

### 2) a11y_impl の `--ring` ライト値変更 → Lighthouse a11y=100 は維持されるか

**断定はできない。ただし強い状況証拠がある**: 私が round1 で実測した「現状（`/50` 付き・2.51〜1.55:1 で未達）の 3 画面はすべて `accessibility: 1`（100 点）」という事実そのものが、**Lighthouse の accessibility カテゴリが今この非適合状態を一切検出していない** ことの直接証拠になる。Lighthouse の accessibility 監査は axe-core ベースの **静的 DOM スナップショット監査** で、`:focus-visible` をトリガーする操作（Tab 押下）を行わない。つまり「リングが 1.55:1 か 3.95:1 か」は監査対象の DOM 状態に現れず、**現状の失敗が既に見逃されている以上、値を変えても Lighthouse 側のスコアには反映されない可能性が高い**。

ただし私はこれを「axe-core のルールセットにその判定が無い」と一次情報で確認したわけではない（axe-core のソース/ルール定義までは round1 で読んでいない）。**言えないので明言する: R2 の実装後、必ず Lighthouse を再計測する。** これは私の設計上も自然な帰結で、run_checks.sh に配線した Lighthouse ステップは「一度実測して終わり」ではなく「R2/R3 の変更を含む PR がこのステップを通るかどうか」でゲートするものなので、再計測は追加作業ではなく **ゲートの本来の役目そのもの**。逆に言えば、C-2（LoadingIndicator の role/aria-live 削除）のような aria 属性の変更は axe-core の標準ルール（`aria-valid-attr-value` 等）に触れる可能性があり、こちらは ring より Lighthouse スコアに影響しうる変更として要注意（こちらも実装後の実測が必須）。

### 3) docs_trace「NFR-27 の Performance 90 以上 と『記録のみ』が矛盾」→ 配線案でどう畳むか

**矛盾はコードではなくドキュメントの側でのみ生じる。私の配線案はこの矛盾をそもそも作らない設計になっている**: `run_lighthouse.mjs`（案）は accessibility score のみを exit code に反映し、performance score は判定に使わず記録専用の値として summary 行に出す。つまり **実装コードには「Performance 90 以上」という閾値そのものが存在しない**（今後もしないよう R1 側で明示的に実装する）。したがって畳み方は 1 択: **NFR-27 の文言を確定事項（Accessibility 100=blocking / Performance=記録のみ）に合わせて書き換える**（docs_trace 項目1・Critical 判定に同意）。

具体的な文言提案（docs_trace の実装に委ねる想定・infra 側からの叩き台）: 「Performance: 90 以上を目安値として計測・記録する（未達でもゲートしない。将来ブロッキング化する場合は別途決定する）」のように **数値目標を残しつつ非 blocking であることを明示する** 形にすれば、既存の「90」という数値を単純削除せずに済み、ドキュメント間の変更差分も最小になる（`open-questions.md` の決定ログに 1 行足す案にも賛成）。この文言確定自体は docs_trace/R4 の担当。R1 側の実装は既にこの矛盾を再現しない形になっているので、**コード側の追加対応は不要**。

### 4) 実行時間: e2e_verify の a11y.spec.ts 実測 36.5 秒 + 私の Lighthouse 3 画面 35.5 秒 → run_checks 全体は成立するか

**成立する。この 2 つは同じタイムアウト予算を取り合わない。** e2e_verify の 36.5 秒は `npx playwright test e2e/a11y.spec.ts` 単体（コールドビルド込み）の実測で、これは `run_checks.sh` の **E2E ステップ**（`RUN_CHECKS_E2E_TIMEOUT` 既定 600 秒）に含まれる。私の Lighthouse 3 画面 35.5 秒（+ 自前 build 5.3 秒 + start 待ち ≒ 44 秒）は **別ステップ・別タイムアウト変数**（round1 提案の `RUN_CHECKS_LIGHTHOUSE_TIMEOUT`、既定 180 秒案）で走らせる設計なので、両者は加算されずそれぞれの予算内で完結する（E2E 実測 36.5 秒は本番の全 spec ファイル分ではなく a11y.spec.ts だけなので、実際の E2E ステップ総時間はもっと長いが、それは既存の 600 秒予算の話であって Lighthouse 側とは無関係）。

`run_checks.sh` 全体の壁時計時間としては Lighthouse ステップの追加分（約 44 秒）は、既存の E2E ステップ（600 秒予算）に比べれば誤差レベルの増分。

**1 点だけ自分の round1 案にリスクを見つけたので修正する**: 私と e2e_verify はどちらも `next start --port 3100`（`playwright.config.ts` と同じポート）を使って実測した。`run_checks.sh` は E2E ステップ→（間に他の軽量チェック）→Lighthouse ステップの順で **逐次実行** なので通常は衝突しないはずだが、E2E 側のビルドプロセスが異常終了時に `--port 3100` を掴んだまま残るケース（今回私自身が手動起動したサーバーのプロセス終了に `kill` を要した）を考えると、**Lighthouse 側は port 3100 を再利用せず別ポート（例 3101）を使う** ほうが安全。コストはゼロ（env の port 番号を変えるだけ）なので、この修正を採用することを提案する。
