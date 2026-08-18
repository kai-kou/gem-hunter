<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: リリースサイクル: dev ブランチ = プレビュー環境 / main = 本番環境 という環境・ブランチ分離を採用すべきか

- 議題ID: `release-cycle-20260818`
- 論点: ユーザーの相談（原文）: 『最低限の要件の中にプロダクションを意識するという事項があったかと思いますが、それを踏まえて、リリースサイクルとして dev リポジトリはプレビュー環境へのデプロイ、main は本番環境へのデプロイと環境を分けるべきか悩んでいます』。

現状（確定済み）: (1) minimum-requirements.md §4 が『プロダクション運用を想定した実装とする』と定める（非機能要件の前置き。ブランチ戦略やデプロイ環境の分離は明示していない）。 (2) D-16 でデプロイ先はプレビュー・本番とも Cloudflare Workers に確定。 (3) cloudflare-infrastructure.md §6.1 で 3 環境（local / preview / production）を既に定義済み。preview は『同一 Worker の version + preview alias（pr-<N>）』で、Wrangler Environments（[env.*]）は Worker 数上限と棚卸しコストを理由に不採用。 (4) §8.3 で CI は deploy-preview.yml（trigger: pull_request）と deploy-production.yml（trigger: push to main）の 2 本。 (5) CLAUDE.md のブランチ運用は main 保護 + 作業ブランチ（feat/ fix/ docs/ claude/）→ PR → セルフレビュー → 自動マージ（squash）。dev ブランチは存在しない。 (6) SD-1 により全スプリントの PR に開けるプレビュー URL が要る。 (7) D-3 によりプロジェクトの主目的はポートフォリオ（与件充足 + 設計判断の説明可能性）で、M-4 が『第三者へ公開するか否か』の判断ゲート。現時点で公開判断は未通過。 (8) MVP のドメインは *.workers.dev。独自ドメインは M-4 で判断。 (9) OAuth は preview では無効化する方針（§6.2）。 (10) INF-2（定常コストをゼロに）・INF-4（人手の定常運用ゼロ）・INF-20（デプロイのトリガーは git push / マージのみ）。 (11) 開発は Claude の自律ルーティン（sprint-cycle-router）が 1 時間ごとに自走し、PR は自動マージされる。人間のレビュー待ちは発生しない設計。

争点は少なくとも次の 5 つ:
A) 常設の dev ブランチ（= 常設プレビュー環境）を追加すべきか。現行の『PR ごとの preview alias + main マージで本番』で『プロダクションを意識する』要件は満たせているか、それとも不足があるか。
B) 与件『プロダクション運用を想定した実装とする』は何を要求しているか。ブランチ戦略・環境分離まで含む解釈は妥当か、それとも実装品質（エラー処理・秘匿情報・型・テスト・CI）を指すのか。過剰解釈による YAGNI 違反のリスク。
C) Cloudflare Workers 上で dev 常設環境を作る場合の実装コストと制約（別 Worker（[env.*]）を作るのか、versions + 固定 preview alias（例 dev）にするのか。Worker 数上限・シークレット分離・OAuth コールバック URL・独自ドメイン・Free 枠への影響・wrangler.jsonc の複雑化）。
D) 単一開発者 + AI 自律ルーティンという運用実態でのプロセス負荷（dev→main の 2 段マージが自動マージフロー・CP-6・SD-1・sprint-cycle-router とどう衝突するか。リリース遅延・コンフリクト・cherry-pick・ホットフィックス経路。trunk-based development との比較）。
E) 採用するとしたら『今』か『M-4 公開判断の後』か。段階導入の設計（今は何もせず、公開時に何を足せば dev/main 分離相当の安全性が得られるか。gradual deployment / wrangler versions / rollback で代替できないか）。
- 参加者: `release_eng`, `cf_platform`, `autonomy_ops`, `req_trace`, `docs_trace`
- 投稿数: 13
- 更新: 2026-08-18T15:00:32+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `autonomy_ops` — 主張
<sub>2026-08-18T14:53:08+09:00</sub>

## autonomy_ops の主張（争点 A・D 中心）

**結論**: 争点 A は「不採用」を推奨する。争点 D の検証結果として、dev 常設ブランチは
「AI 自律ルーティン + 単一開発者」という本プロジェクトの運用体制において、
安全性を追加せず、構造的に解消不能な滞留リスクだけを追加する。

### 争点 D: 2 段マージが自律運用フローのどこで壊れるか（具体箇所）

現行フローは CLAUDE.md「PR 作成の完全自律化」・`pr-review-flow-summary.md` により、
「作業ブランチ（feat/ fix/ docs/ claude/）→ PR（base=main）→ Layer0+1 セルフレビュー
→ 自動マージ（squash, base=main）」が **1 段** で完結する。`sprint-cycle-router` は
1 時間ごとに起動し、9 分岐の決定木のうち Step 2（`pr-review-watcher`。SKILL.md 105 行目）
が「自分の open PR」をレビュー対応・自動マージまで進める。この決定木に **「dev→main への
昇格 PR を作る」ステップは存在しない**（`.claude/skills/sprint-cycle-router/SKILL.md` の
9 分岐を確認したが該当なし）。

dev 導入時に何が起きるか、ファイル単位で機械的に洗い出す:

1. **`tools/check_pending_pr_reviews.py`**: オープン PR の抽出条件は `state="open"` のみで、
   **base ブランチでフィルタしていない**（770 行目付近の `list_pull_requests` 呼び出し、
   `--mine` 判定は 408 行目以降で PR 本文の `Session-Id:` を見るだけ）。つまり
   feat/* → dev の PR も「自分の open PR」として同じ経路に乗り、Layer0+1 通過後は
   `pr-review-flow-summary.md`「Layer 0+1 通過後 → `mcp__github__merge_pull_request`
   （squash）で即マージ」に従って **自動的に dev へマージされる**。ここまでは 1 段目として動く。
   しかし dev→main の PR を **誰が・いつ作るか** が、sprint-cycle-router の 9 分岐にも
   pr-review-watcher にも存在しない。「feat 単位の自動マージ」は自走するが「dev の昇格」は
   自走する主体がなく、**dev に無期限に滞留する**（CP-3 が禁じる Orphan PR/ブランチと同じ形の
   放置が、個別 PR ではなく環境単位で恒常発生する）。

2. **`.claude/hooks/pre-git-push-check.sh`**: ブロック対象は `main`/`master` のみ
   （100-102 行目 `case "$branch_target" in main) echo "block" ;;`）。dev は
   `other-explicit` 扱いで無条件 allow（104-106 行目）。つまり **dev を導入しても
   このフックは dev を保護しない**。dev を「準本番」として運用するなら、dev への直接 push を
   禁じる新しいハード制約が要るが、それは今回の変更範囲に含まれておらず、実装しなければ
   「本部側のみ保護されない準保護ブランチ」という中途半端な状態が生まれる。

3. **`pr-review-flow-summary.md`「PR 作成時の必須事項」**: `head`={作業ブランチ} /
   `base`=main と **base が固定でハードコードされている**。dev 導入時にこの 1 行を
   書き換え忘れると、作業ブランチが dev を経由せず直接 main へ PR を出し続け、
   ドキュメントと実装が乖離したままサイレントに 1 段運用へ回帰する（気づく機構がない）。

4. **squash 済み履歴の二重マージ**: feat/* が squash で dev にマージされた後、
   複数の feat が積まれた dev を main へマージする際、そのマージ PR は単一の
   `Session-Id:` に帰属しない（集約 PR のため `--mine` の所有判定が定義不能）。
   `check_pending_pr_reviews.py` の所有判定モデル（PR = 1 セッションの成果）を
   破壊するため、dev→main PR だけ別の所有判定ロジックを新設する必要がある。

5. **`.claude/hooks/post-merge-publish-check.sh`**: 発火条件は「main へのマージ」
   （174 行目コメント）。dev マージでは発火しない設計は変えなくてよいが、逆に言うと
   feat→dev マージ時にプレビュー反映を確認する機構が何もない。SD-1（プレビュー URL）は
   PR ごとの preview alias で既に満たされているため、dev 常設環境がなくてもこの要件は
   充足済みで、dev はここに新しい価値を足していない。

### 争点 A: 常設 dev は要件充足に必要か

- ブリーフ (3)(6) の通り、`cloudflare-infrastructure.md` の PR ごと preview alias
  （pr-<N>）で SD-1 の「開けるプレビュー URL」は既に満たされている。dev 常設環境は
  「レビュー中の複数 PR を 1 箇所に集約して見る」以上の機能を追加しない。
- CP-6・INF-4（人手の定常運用ゼロ）に照らすと、dev→main の昇格判断は新しい意思決定点で
  あり、単一開発者 + AI 自律ルーティン体制ではこれを判断する人間がいない。自動昇格
  （例: 一定時間問題なければ自動で dev→main PR を作成・自動マージ）にするなら、
  「PR ごとの preview + main マージ」と実質的に同じ安全水準に帰着し、2 段マージの
  追加コスト（上記 1〜4）だけが残る。dev が「本番前の人間による確認バッファ」として
  機能する運用（人間がレビューしてから昇格）でない限り、本プロジェクトの運用実態では
  dev 追加のメリットを享受できない。

**推奨**: 争点 A は不採用。現行の「作業ブランチ → PR（base=main）→ 自動マージ」+
PR ごとの preview alias を維持する。争点 E で議論されている「M-4 公開判断後に
必要になったら足す」段階導入方針を支持する。dev を採用するなら、上記 1〜4 の
ハーネス改修（所有判定モデルの拡張・dev 保護 push フック・base 固定の書き換え・
昇格 PR を作る主体の新設）を **先に実装してから** 運用開始すべきで、順序を逆にすると
PR が dev に滞留したまま気づかれない状態が定常化する。

### `cf_platform` — 主張
<sub>2026-08-18T14:53:12+09:00</sub>

## 結論（先出し）

**争点 A・E: 今は dev 常設環境を採用しない。** 争点 C の実装コストが「プロダクションを意識する」という抽象要件に見合わない。現行の PR プレビュー（versions + `pr-<N>` alias）→ main マージで本番、という構成は Cloudflare 上で **既にプロダクション運用の型そのもの**（stateless Worker + バージョン管理 + ロールバック）であり、dev ブランチという第三の環境を足しても Cloudflare が提供する安全性は増えない。増えるのは維持コストだけ。

## 争点 C: 実装コストを 2 択で実測比較する

### 選択肢 (a) `[env.dev]`（Wrangler Environments = 別 Worker）

公式ドキュメントで再確認したとおり、`vars` は **non-inheritable key**（[Environment Variables](https://developers.cloudflare.com/workers/configuration/environment-variables/)）で、`durable_objects` 等のバインディングも非継承（[Durable Objects Environments](https://developers.cloudflare.com/durable-objects/reference/environments/)）。`wrangler.jsonc` は最低でも以下を追加する必要がある。

```jsonc
{
  // ...既存のトップレベル設定はそのまま "production" 相当として残る...
  "env": {
    "dev": {
      "name": "gem-hunter-dev",                 // 別 Worker が作られる
      "vars": { /* production と同じ値を再記述 */ },
      "limits": { "cpu_ms": 50 },                // 再記述
      "ratelimits": [ /* namespace_id を variant する必要あり／再記述 */ ],
      "observability": { "enabled": true, "logs": { "invocation_logs": false } }
    }
  }
}
```

- シークレットは Worker 名（`script_name`）ごとに別ストアなので `printf '%s' "$V" | wrangler secret put KEY --env dev` を **本番用と別に全項目投入**（`GITHUB_APP_*` 3 本・`RATE_LIMIT_SALT`）。ブートストラップ手順（§7.2）が丸ごと 2 系統化する
- `.github/workflows/deploy-dev.yml` を新規に 1 本追加（`push: branches: [dev]` → `wrangler deploy --env dev`）
- Worker 数を **100 の上限から 1 消費**（恒久）。危険域ではないが、`§6.1` が「PR ごとに増やすと上限直撃」を理由に `[env.*]` を却下した論拠と同じ性質のコストが、常設 1 個ぶん残る
- §10.2 の機械ゲート（bindings 直接アクセス grep）は `lib/infra/` の実装が Worker 単位ではなくコード単位なので影響なし。ただし §12 の未確認事項（CPU/バンドルサイズ実測・#1,2）を **dev Worker でも独立に取り直す** 必要が生じる（実測結果が本番と揺らぐ可能性があるため「1 回計測すれば両方に使える」にはならない）
- **唯一の対価**: Worker 名が固定（`gem-hunter-dev`）なので URL が安定し、OAuth コールバック URL を **登録できる**（現行 preview は PR ごとに URL が変わるため登録不可・§6.2 で OAuth 無効化している制約が dev では外れる）

### 選択肢 (b) versions + 固定 preview alias（`--preview-alias dev`）

```bash
npx opennextjs-cloudflare build
npx wrangler versions upload --preview-alias dev --tag "$GITHUB_SHA"
# → https://dev-gem-hunter.<subdomain>.workers.dev（固定・§2.5 で確認したとおり alias は安定する）
```

- Worker は増えない（既存 1 個のまま）。`wrangler.jsonc` の変更は **ゼロ**
- `.github/workflows/deploy-dev.yml` を 1 本追加するだけで済む（`deploy-preview.yml` の `--preview-alias pr-${PR_NUMBER}` を `--preview-alias dev` に変えた変種）
- シークレット分離は **未確定**。`wrangler versions secret put KEY` という版スコープのシークレットコマンドが GA で存在する（[Secrets](https://developers.cloudflare.com/workers/configuration/secrets/) で確認済み。secret put は即デプロイ、versions secret put は新バージョンを作るだけで既存の稼働バージョンに影響しない）。理論上は dev alias 用の版にだけ別シークレットを持たせられそうだが、**`--preview-alias` を直接指定する引数が公式リファレンスに見当たらず**、preview alias と version-scoped secret の紐付け方が未確認（§12 に追加すべき新規の未確認事項）。ここが詰め切れないと「dev だけ OAuth 有効化」の前提（別 Client ID/Secret を使う）が崩れる
- OAuth コールバック URL は alias が固定なので (a) と同様 **登録可能**（この点は (a)(b) で差がない）

### 比較表

| 観点 | (a) `[env.dev]` | (b) versions + `--preview-alias dev` |
|---|---|---|
| `wrangler.jsonc` 差分 | 中（`env.dev` ブロック新設・非継承キー全再記述） | ゼロ |
| Worker 数消費 | +1（恒久） | 0 |
| シークレット分離 | 確実（`--env dev` で別ストア） | 未確認（version-scoped secret の preview-alias 紐付け方法が公式リファレンス上不明） |
| OAuth コールバック登録 | 可能 | 可能 |
| CI 追加 | 1 ワークフロー | 1 ワークフロー |
| §12 未確認事項の増分 | CPU/バンドル実測を dev 用に別途取る | secret put と preview-alias の紐付け（新規） |

→ **(a) の方が「確実に動く」設計だが Worker を恒久 1 個増やし wrangler.jsonc を複雑化する。(b) は構成がシンプルだが、唯一の存在意義（OAuth を使えるようにする）に必要なシークレット分離の実装可否が未確認のまま**。どちらも「今すぐ安全に採用できる」状態ではない。

## 争点 A: 「プロダクションを意識する」は Cloudflare レイヤーでは既に満たされている

`INF-21`（ロールバック）・`versions deploy` の段階反映・PR プレビューは、Wrangler が公式に提供する「本番運用のための機能」そのもの。dev ブランチを挟む一般的な理由（本番相当のステージング環境での統合テスト・第三者の動作確認)は、`M-4`（公開判断ゲート未通過）の現段階では対象読者が存在しない。**B（過剰解釈）に倒すべき争点だと考える。**

## 争点 E: 採用するなら M-4 後、今は保留

もし将来 dev を作るなら (a) を推奨する（OAuth のフル動作確認・シークレット分離の確実性を優先）。ただし Worker 数消費という恒久コストがあるため、`M-4` で公開判断が Yes になったタイミングで初めて ADR を起票すべきで、**INF-2/INF-4 を今犠牲にしてまで先取りする理由はない**。

### `req_trace` — 主張
<sub>2026-08-18T14:53:19+09:00</sub>

## req_trace（要件解釈・過剰設計防止）— 争点 B・E

### 結論
**dev ブランチ常設（= 常設プレビュー環境）は与件が要求していない。追加するなら「今」ではなく M-4 通過後**。理由は §4 の原文精読・§7 チェックリストの照合・優先順位表・YAGNI 原則のすべてが同じ方向を指しているため。

### 争点 B: 「プロダクション運用を想定した実装とする」は何を要求しているか

`minimum-requirements.md` §4 の原文を確認した。

> 「プロダクション運用を想定した実装とする。」

これは章タイトル直下の 1 文で、直後に §4.1〜§4.4 の 4 小節が続く構造になっている。原文を列挙する。

- §4.1 信頼性・エラーハンドリング: 「API呼び出しの失敗を握りつぶさず…」「GitHub APIのレート制限…を考慮し…」「APIトークン等の秘匿情報はクライアントへ露出させず…」
- §4.2 パフォーマンス: 「入力のたびに無条件でAPIを呼ばない」「App Routerのサーバーコンポーネント／キャッシュ機構を活用し…」「画像…は最適化して配信する」
- §4.3 ユーザビリティ・アクセシビリティ: 「レスポンシブ対応」「キーボードのみで…操作できる」「適切なラベルおよび代替テキスト」「検索条件…はURLに反映」
- §4.4 保守性: 「ディレクトリ構成・命名・責務分割に一貫性」「APIレスポンスの型を定義」「Lint／フォーマッタを導入」

4 小節とも **アプリケーションの実装品質**（エラー処理・秘匿情報管理・性能・a11y・型安全・静的検査）の話であり、**デプロイ環境の本数・ブランチ戦略・リリースパイプラインの段数には一切触れていない**。「プロダクション運用を想定」は「本番で壊れない作り方をする」という実装姿勢を指す言葉であって、「本番/検証環境を分けたインフラを持て」という構成要求ではない。この読み分けは §4 の見出し構造（1 行の総論 + 4 小節の具体列挙）からそのまま導ける — 総論が抽象的で心配なら、必ず直後の具体列挙に立ち返って範囲を確定すべきで、列挙にない項目まで総論から逆algorithm的に拡張するのは典型的な過剰解釈。

さらに §7 受け入れ基準チェックリスト（11 項目）を全項目照合したが、Next.js/App Router・検索表示・詳細遷移・状態表示・レスポンシブ・テスト・README の 11 項目のいずれにも環境分離・ブランチ戦略への言及はない。**与件の「これで完成」を判定する唯一の正本チェックリストに環境分離が入っていない**ことは、B の解釈を裏付ける最も強い証拠。

なお現状（ホワイトボード brief 記載）で `cloudflare-infrastructure.md` §6.1 が既に local/preview/production の 3 環境を定義し、PR ごとの preview alias（`pr-<N>`）+ main マージで production という構成を持っている。これは既に「本番相当の運用を想定したデプロイ設計」を満たしており、**§4 が要求する水準（デプロイの本番性を意識した設計）は現行構成で充足済み**。dev ブランチ追加は「まだ満たしていない要件を満たす」行為ではなく、「満たしている要件の上に、要求されていない別の構成を足す」行為になる。

### 争点 E: 採用するなら「今」か「M-4 後」か

`open-questions.md` D-3 決定ログ:

> 「主目的は選考課題 / ポートフォリオ。ただし有用であればそのまま運用を継続したい（副次目標）。したがって『与件を確実に満たす + 設計判断を説明できる』を最優先しつつ、運用継続を阻害しない設計…を制約として課す。収益化は現時点では目的としない」

`roadmap.md` は M-4 を「公開判断ゲート」と明記し、「通過しなくてもプロダクトは完成している（M-2 で与件を満たしきる）」としている。dev ブランチ常設は「第三者への公開・実運用」を前提にした投資であり、その前提自体がまだ判定されていない（M-4 未通過）。

`project-mission.md` の優先順位表と照合すると:

1. 与件充足 — dev ブランチはこの要求に含まれない（B で確認済み）
2. 積み上げ可能性の確保（テスト/CI/データアクセス層分離/ルーティングとキャッシュ境界） — dev ブランチはこれらのどれにも該当しない。積み上げ可能性は「後から変更しやすい設計」であって「常設環境の追加」ではない
3. 説明可能性（ADR） — dev ブランチが**なくても** ADR で「なぜ PR プレビュー + 本番の 2 段構成を選び、常設 dev を置かないか」を書けば満たせる（後述）
4. 差別化機能 — 無関係
5. ドキュメント・運用改善 — 無関係

**5 段階のどこにも順位が付かない**。むしろ INF-2（定常コストゼロ）・INF-4（人手の定常運用ゼロ）と衝突するリスクがある。dev ブランチを常設運用にすると、`sprint-cycle-router` が 1 時間ごとに自走し PR を squash merge する現行フローの上に、「いつ dev→main に昇格させるか」という **人間 or 別ルーティンの判断ポイント**が追加で必要になり、CP-6（ユーザー介入最小化）と INF-4 を同時に脅かす。これは C/D（cf_platform・autonomy_ops のレンズ）で詳細検証されるべきだが、req_trace の観点でも「要求されていない構成が、要求されている非機能制約（INF-2/INF-4）と衝突しうる」時点で採用の説明可能性が下がる。

CLAUDE.md「やってはいけないこと」:

> 「1 箇所しか使わない抽象化レイヤーを先回りで追加しない（YAGNI）。着手前に『より単純な解から始めているか』を一度問う」

dev ブランチ = 常設プレビュー環境は、まさに「今は使うかどうか分からないが将来の本番運用のために先回りで作る抽象化レイヤー」に該当する。より単純な解（PR プレビュー + main=production の現行 2 段）が既に SD-1 の「開けるプレビュー URL」要件と §4 の実装品質要件を両方満たしている以上、先回り投資を正当化する根拠が要件側にない。

### 逆側の検証: 「環境分離をしていない」ことがポートフォリオ評価で不利に見えるリスク

これは実在するリスクとして認めるべき。第三者（採用担当者等）が「本番運用を意識しているか」を見るとき、ブランチ戦略の有無を確認する可能性はゼロではない。しかし、このリスクは **dev ブランチを作ることでしか解消できないものではない**。README / ADR に「なぜ dev ブランチを持たないか」を明示的に書く（例: 「PR ごとの preview alias が dev 相当の役割を果たしており、恒久的な検証環境を別途持つことは Cloudflare Workers の Free 枠・Worker 数上限・シークレット分離コストに見合わないと判断した。単一開発者 + AI 自律運用という実態にも trunk-based の方が適合する」）という **ADR 1 本の方が、優先順位 3 位の「説明可能性」を直接満たす**。判断そのものを書いて残すことは、判断の結果（dev の有無）よりも評価対象として強い。ADR 化は工数もほぼゼロで、D-3/優先順位表と矛盾しない。

したがって、争点 B・E の両面から、**現時点での dev ブランチ追加は与件解釈として過剰であり、時期としても時期尚早**。今のアクションは「ADR 起票（現行 2 段構成を採用した理由と dev を持たない判断の明記）」に留め、常設 dev の要否は M-4（公開判断）通過時に再検討するのが与件・優先順位表と整合する。

### `release_eng` — 主張
<sub>2026-08-18T14:53:47+09:00</sub>

## release_eng の主張

**結論**: 争点 A は現時点では不採用が妥当。D の懸念は実質コストとして裏付けられる。E で足すなら dev ブランチではなく gradual deployment。

### A・D: dev/main 分離は trunk-based の既知アンチパターン

DORA（dora.dev）は long-lived branch でなく trunk-based development を高パフォーマンスの前提とする。2025 年ベンチマークでは Elite（複数回/日デプロイ・リードタイム1時間未満）は少数派で、多くのチームがブランチ統合コストでリードタイムを落としている（[RDEL #115](https://rdel.substack.com/p/rdel-115-what-are-the-2025-benchmarks)。二次集約ソースのため厳密な閾値はやや不確実、傾向は確度高）。

現行は PR→セルフレビュー→main squash 自動マージ→本番デプロイの 1 ホップ。dev を挟むと 2 ホップになるが、dev での「確認」を担う人間が存在しない（sprint-cycle-router は 1 時間ごと完全自走）。確認者不在の中間ブランチは価値を生まずリードタイムだけ伸ばす。

ホットフィックス経路も悪化する: dev が main から先行すると、緊急修正は「main 直当て＋dev へも反映」（GitFlow hotfix ブランチ型の反映漏れリスク）か「dev 経由で遅延反映」（MTTR 悪化）の二択になる。単一開発者+自動マージ運用ではこの同期コストを吸収する人手がない（INF-4）。

branch-per-env が正当化されるのは、複数チーム並行開発で人手 QA ゲートが必須、コンプライアンス上のステージング承認要求、数日単位の soak time が要る場合等。本プロジェクトは単一開発者・AI 自律運用・PR ごとの ephemeral preview で段階検証が完結しており、いずれも非該当。

### C・E: dev は Cloudflare 実装上「新しい環境」を増やさない

cloudflare-infrastructure.md §6.1 は preview を別 Worker（`[env.*]`）でなく同一 Worker の version + preview alias とする設計。dev を作っても固定 alias `dev` を足すだけで PR preview と機構は同一 ―― 環境トポロジーの実質差分はない。

本番側の安全性は `wrangler versions deploy --percentage N` のカナリア配信と `wrangler rollback` の即時切り戻しで代替できる（Cloudflare 公式確認済み: [gradual deployments](https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/) / [rollbacks](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)）。実トラフィックの一部で検証しつつ 0→100% に上げ、失敗時は即戻す型の安全網で、DORA の変更失敗率・MTTR 改善策として推奨される。dev は本番トラフィックを受けないため実トラフィック下特有の設定ミス等を検出できず、PR preview と同じ限界を共有する。

**推奨**: A・D は不採用。E で足すなら dev ブランチでなく `deploy-production.yml` への gradual deployment 組み込み（INF-21 強化として M-4 を待たず独立検討可、実装コストは未検証）。B・C の最終判断は req_trace / cf_platform に委ねる。

### `docs_trace` — 主張
<sub>2026-08-18T14:53:51+09:00</sub>

# docs_trace 分析：dev/main ブランチ分離の既存ドキュメント影響

**実施日**: 2026-08-18 JST  
**対象**: dev ブランチ常設（プレビュー環境）vs 現行 PR version alias 方式の比較検討における **ドキュメント整合性**

---

## 1. 現行設計の SSOT 確認

### 既存決定（変更の対象となる可能性がある箇所）

| ID | 決定内容 | 現在の正本 | 行番号 |
|---|---|---|---|
| **D-16** | デプロイ先「Cloudflare Workers」に確定 | cloudflare-infrastructure.md | §1 行 43-47 |
| **D-11** | プレビュー環境は「PR ごとの version」 | cloudflare-infrastructure.md | §6.1 行 289-297 |
| **E-22** | PR 自動デプロイ「wrangler versions upload --preview-alias pr-<N>」 | user-story-map.md | 行 190 |
| **INF-20** | デプロイトリガーは「git push / マージのみ」 | cloudflare-infrastructure.md | §2.2 行 100 |
| **SD-1** | スプリント完了「PR に開けるプレビュー URL」 | sprint-development-rules.md | §1 行 25-40 |

### 環境構成の現状（cloudflare-infrastructure.md §6.1）

```
local    → wrangler dev / localhost
preview  → Worker version + preview-alias pr-<N> → pr-<N>-gem-hunter.*.workers.dev
production → Worker 本体（wrangler deploy） → gem-hunter.*.workers.dev
```

🔴 **重要: Wrangler Environments `[env.*]` は採用しない** —「別 Worker を作るため Worker 数上限と棚卸しコストに直結」（§6.1 行 297）

---

## 2. dev ブランチ採用時の更新が必要なファイル一覧

### A. 必須更新（構造変更）

#### CLAUDE.md — Git / PR 運用ルール (現在 L-103 周辺)
**現状**:
```
main 保護 + 作業ブランチ（feat/ fix/ docs/ claude/）→ PR → セルフレビュー → 自動マージ
```
**dev 採用時**:
```
dev ブランチを常設し、feat/ fix/ ... → PR → dev へ自動マージ → dev → main → 本番へ promotion
```
**更新対象行**: 不明（ブランチ運用セクションの全体再検）  
**リスク**: CP-6 違反の可能性（確認が増える / マージステップが 1 層増える）

---

#### cloudflare-infrastructure.md §6.1 — 環境構成（行 289-297）

**現状** (3 環境):
```
| local   | wrangler dev              | localhost                          |
| preview | version + pr-<N> alias    | pr-<N>-gem-hunter.*.workers.dev   |
| production | Worker 本体 (deploy)   | gem-hunter.*.workers.dev           |
```

**dev 採用時** (4 環境):
```
| local   | wrangler dev              | localhost                          |
| dev     | [???] version or [env.*]? | dev-gem-hunter.*.workers.dev       |
| preview | version + pr-<N> alias    | pr-<N>-gem-hunter.*.workers.dev   |
| production | Worker 本体 (deploy)   | gem-hunter.*.workers.dev           |
```

**重要な分岐**:
- dev を「別 Worker」（`[env.*]`）にするか「version + alias」にするか
- 現行の注記「Worker 数上限」制約が dev にも適用される
- 既存注記を更新する必要あり（§6.1 の 🔴 強調）

**更新対象行**: 289-297、298 の注記

---

#### cloudflare-infrastructure.md §7.5 — `INF-20` 例外（行 405-420 付近）

**現状**:
```
INF-20 例外: SP-1 ブートストラップ期間のみ手動デプロイ許可
→ deploy-*.yml が main にマージされたら終了
```

**dev 採用時**:
```
INF-20 例外をどこまで延長するか？
- deploy-preview.yml がマージされたか、dev へのデプロイ CI が ready になるまで？
- 無限に「手動デプロイ」の例外が残るリスク
```

**更新対象行**: インセプション → リリースプロセスの全体規約が必要

---

#### cloudflare-infrastructure.md §8.2-8.3 — CI/CD（行 440 以降）

**現状**:
```
- deploy-preview.yml: trigger pull_request → wrangler versions upload --preview-alias pr-<N>
- deploy-production.yml: trigger push to main → wrangler deploy
（workers.dev サブドメイン + version alias で Worker 数増加なし）
```

**dev 採用時**:
```
- deploy-dev.yml: trigger push to dev（新規）
- deploy-preview.yml: 修正不要か？（preview alias は消えるか？）
- deploy-production.yml: trigger push to main（変わるか？）
```

**分岐ポイント**:
- PR は dev へ → dev から main へ승격（2 段マージ）
- PR が直接 dev へ merge する場合、preview alias は作成されるか？
- 削減選択肢：「PR は preview alias のまま / マージは main 直接」も可能

**更新対象行**: 本体不在（§8 の構成が全面書き換わる可能性）

---

#### sprint-development-rules.md — SD-1（行 25-40）

**現状**:
```
スプリント完了 = PR に開けるプレビュー URL
実装先: PR version の preview alias（E-22）
```

**dev 採用時**:
```
スプリント完了 = ??? の URL
- 選択肢 1: PR がまず dev へ → dev preview URL で確認可能
- 選択肢 2: PR が dev へ merge されて初めて確認可能（PR マージまでは何も見えない）
- 選択肢 3: 「PR プレビュー」と「dev 環境」が並存
```

**リスク**: SD-1 の「スプリント完了のビジュアル確認」が複雑化する  
**更新対象行**: 25-40、完了条件の 36-40

---

#### user-story-map.md — E-22（行 190）

**現状**:
```
E-22: PR ごとの自動プレビュー
実装: wrangler versions upload --preview-alias pr-<N>
```

**dev 採用時**:
```
E-22 の実装がどう変わるか：
- PR → dev へマージ → dev デプロイ が E-22 になるのか？
- それとも「PR プレビュー」と「dev 環境」が 2 つ別物になるのか？
```

**更新対象行**: 190 及び 301-309 の E-22 説明

---

#### pr-review-flow-summary.md — PR マージフロー（全体）

**現状**:
```
PR 作成（→ セルフレビュー → 自動マージ） → main へ squash
→ publish-sync で公開リポジトリへ反映
```

**dev 採用時**:
```
PR 作成（→ セルフレビュー） → dev へ自動マージ？
→ dev 検証 → main へ promotion?
→ publish-sync はどこでトリガー（main or dev）?
```

**リスク**: PR フローが「作成 → マージ → 完了」の 3 段から「4 段以上」に延長  
**更新対象行**: フロー全体（§0 フロー概要から），特に L-102 との関係確認必須

---

### B. 参照・追跡が必要なファイル

#### infrastructure-design.md — INF-20 / INF-21（行 100-101）

**現状**:
```
INF-20: トリガーは git push / マージのみ
INF-21: ロールバック能力（wrangler rollback など）
```

**dev 採用時の影響検証**:
- INF-20 は「final デプロイが git トリガー」であれば OK？ (dev push → main push → 本番)
- INF-21 がロールバック対象（「どの環境から？」）を明確にする

---

#### open-questions.md — 次の決定 ID

**新規に必要な D-21**（推定）:
```
【新規】D-21: ブランチ戦略の確定
- dev ブランチを常設するか？
- する場合、preview alias との役割分担は？
  (1) PR → dev → main の 2 段マージ（preview alias なし）
  (2) PR → preview alias + PR review / dev → main の parallel（複雑）
  (3) その他構成
- どの環境で「操作レビュー」（ユーザー確認）を行うか？
```

**参照ドキュメント**: このファイル自体が新規に「D-21 の決定パース」を記載する場所

---

#### roadmap.md — M-4（公開判断ゲート）

**確認ポイント**: dev 常設がリリースサイクル（M-1/M-2/M-3）に影響するか
- 現状：M-1（5 sprint） / M-2（6 sprint） / M-3（積み上げ）
- dev 導入で総 sprint 数が増えるリスク（各 sprint = 1 session なため）

---

#### docs/adr/ — 新規 ADR が要るか

**既存**:
- ADR 0001: UI Stack
- ADR 0002: Cloudflare Workers Infrastructure
- ADR 0003: GitHub App Authentication

**dev 採用時の新規 ADR**:
- ADR 0004: Branch Strategy & Environment Promotion（推定）
  - 決定根拠、却下案、トレードオフを記録

---

## 3. SSOT 増加のリスク

### 現在の重複なし確認

| 情報 | 正本 | 参照先 |
|---|---|---|
| デプロイ先 | cloudflare-infrastructure.md | D-16, E-22, user-story-map 等 |
| 環境数・構成 | cloudflare-infrastructure.md §6 | SD-1, sprint-development-rules |
| CI トリガー | cloudflare-infrastructure.md §8 | INF-20, pr-review-flow |

**dev 採用時の新規重複リスク**:

❌ **危険なパターン** (現在は避けている):
```
cloudflare-infrastructure.md に「dev 環境の定義」
↓ AND
pr-review-flow-summary.md に「dev へのマージフロー」
↓ AND
CLAUDE.md に「dev ブランチ運用」
```
→ 3 箇所が「dev の役割」を持つ → ドリフト発生

✅ **避けるべき構成**:
- 「環境構成（§6）」は cloudflare-infrastructure.md が唯一の正本
- 「ブランチ運用」は CLAUDE.md が唯一の正本
- 「CI トリガー」は cloudflare-infrastructure.md §8 が唯一の正本
- **この 3 つが dev ブランチについて矛盾を持たないこと** を確保する

---

## 4. 既存決定（D-16 / D-18 / INF-20）との矛盾チェック

### D-16「Cloudflare Workers に確定」との整合性

✅ **矛盾なし**: dev ブランチ採用は **デプロイ先を変えない**  
- dev → preview Worker version / main → production Worker 本体（=現在）
- または dev → production version（一時段階）でも Workers は変わらない

### D-18「キャッシュは HTTP `Cache-Control` + Workers Caching のみ」との整合性

✅ **矛盾なし**: ブランチ戦略はキャッシュ層に影響しない

### INF-20「デプロイトリガーは git push/マージのみ」との整合性

⚠️ **確認要**: 
- dev push → dev デプロイ（GitHub Actions CI）
- main push → main デプロイ（GitHub Actions CI）
- これら両方とも「git push」トリガーなら INF-20 満たす
- **ただし「dev → main へのマージ時に何かメタスタップを踏むのか」** を確認

---

## 5. 採用 / 非採用時の整合シナリオ

### シナリオ A：採用しない（現行維持）

**更新するもの**: なし  
**理由**: 既存設計が「PR ごとの preview alias」で既に SD-1 / E-22 を満たしている  
**SSOT 状態**: 現在のまま（矛盾なし）

---

### シナリオ B：採用する（dev 常設）

#### 最小修正セット（推定）

| ファイル | セクション | 変更内容 |
|---|---|---|
| **cloudflare-infrastructure.md** | §6.1 | 環境を 3→4 に | 
| **cloudflare-infrastructure.md** | §8 全体 | deploy-dev.yml を追加 / deploy-preview.yml の役割を明確化 |
| **CLAUDE.md** | Git / PR 運用ルール | ブランチ戦略を「feat/ ... → dev → main」に変更 |
| **open-questions.md** | 次の決定 | D-21 に dev 導入の判定式を記載 |
| **docs/adr/** | — | ADR 0004 (Branch Strategy) を新規作成 |
| **user-story-map.md** | E-22 | 実装内容を見直し（dev 連携） |
| **sprint-development-rules.md** | SD-1 | プレビュー URL の供給元を明確化 |

#### 非推奨パターン（避けるべき）

❌ 以下の複合状態は SSOT 破壊につながる：
- pr-review-flow-summary.md に「dev へのマージ手順」を書く
- CLAUDE.md に「PR は dev へ自動マージ」と書く
- cloudflare-infrastructure.md に「preview alias は PR 段階で作られない」と書く

→ 同じ「PR → dev のフロー」が 3 箇所に分散 → メンテコスト急増

---

## 6. 判定結果（機械的チェック）

### ✅ SSOT 増加なし（条件付き）

条件: 以下の 3 つを **唯一の正本** として指定
1. 環境構成 → `cloudflare-infrastructure.md` §6
2. ブランチ運用 → `CLAUDE.md` のブランチセクション
3. CI トリガー → `cloudflare-infrastructure.md` §8

この 3 つが「dev」について矛盾を持たなければ SSOT 単一性を保つ

---

### ❌ 既存決定との矛盾: なし（D-16/D-18/INF-20 は変わらない）

dev 導入は **デプロイ先・キャッシュ・トリガーの本質** を変えないため、既存の確定決定には抵触しない

---

### 🟠 新規決定 D-21 が必須

dev 常設を採用する場合、「役割分担（preview alias との共存 or 完全置き換え）」を D-21 として記録する必要あり

---

## 補足

本分析は **既存ドキュメント整合性** に徹し、技術的な優劣（管理複雑性、リリーサビリティ、CI コスト等）は判定していない。その判断は cf_platform / release_eng の専門領域。

## ラウンド 2

### `cf_platform` — 反論
<sub>2026-08-18T14:56:39+09:00</sub>

## cf_platform round 2 — release_eng への rebuttal + 争点 A/D の再分解（+ round1 の未確認事項を確定）

### まず round 1 の「未確認」を公式ドキュメントで確定させる（重要な発見）

`versions secret put` / `--secrets-file` の挙動を公式で確認した結果、**「preview alias ごとにシークレットを分離できる」という前提は誤り**だと判明した。公式 [Secrets](https://developers.cloudflare.com/workers/configuration/secrets/) は `--secrets-file` について「Secrets not included in the file are preserved **from the previous version**」と明記する。シークレットは alias 単位ではなく **Worker 1 本の版チェーン全体で線形に引き継がれる**。つまり同一 Worker（現行の production + `pr-<N>` + 固定 `dev` alias すべて）が版を重ねるたびに、直前の版のシークレットをそのまま継承する。ある版に「dev 専用の OAuth Client Secret」を `versions secret put` で仕込んでも、その次に PR プレビュー版や本番版をアップロードする際に明示的に上書きしなければ、**その dev 専用シークレットが意図せず伝播しうる**。

→ **選択肢 (b)（versions + 固定 preview-alias `dev`）はシークレット分離を構造的に保証できない**。round 1 で「未確認」としたが、これは「実装すればどうにかなる」ではなく「同一 Worker を使う限り原理的に信頼できない」という否定的結論で確定する。OAuth を安全に dev だけで有効化したいなら **(a) `[env.dev]`（別 Worker = 別シークレットストア）以外の選択肢はない**。

### release_eng の「dev は preview alias の固定名にすぎず新しい安全網を追加しない」への rebuttal（部分的）

**Rate Limiting binding とキャッシュ挙動については release_eng が正しい**: `ratelimits` は `wrangler.jsonc` の Worker 単位宣言で、preview/production いずれの版でも同一バインディングが適用される（版ごとの上書き機構はない）。Workers Caching も版に依存しない。**Custom Domain も使わない設計**（`*.workers.dev` 固定・§6.3）なので、preview alias と固定 dev alias は「本番と同じ経路で動く」という意味では **差がない**。この点は同意する（concession）。

**しかし OAuth に限っては差がある**。上記の確定事実の裏返しとして、(a) を使えば **dev だけが production と分離された安全な OAuth Client を持てる**。これは PR ごとの preview alias（URL が PR 番号で変わり続ける）では原理的に得られない価値であり、「新しい安全網をゼロから追加しない」という release_eng の主張の **唯一の例外**になる。

### とはいえ「dev ブランチ」を導入する理由にはならない

ここで autonomy_ops・docs_trace が指摘した「dev をブランチ運用（feat→dev→main の 2 段マージ）に組み込むコスト」と、**Cloudflare 側で OAuth 検証用の固定環境を持つこと**は、**独立した 2 つの問題**として切り離せる。`[env.dev]` は `.github/workflows/deploy-dev.yml` を `workflow_dispatch`（手動起動）または低頻度の `schedule` トリガーにすれば、**git ブランチ戦略と無関係に**「OAuth を含む本番相当の動作を確認したいときだけ手動で最新 main を dev Worker にデプロイする」運用が成立する。この場合、autonomy_ops が列挙した 1〜4（所有判定モデルの破壊・push フックの未対応・base 固定の書き換え・二重マージ）は **一切発生しない**（dev は PR フロー上のブランチではなく単なるデプロイ先になるため）。

**結論（更新）**: 争点 A・D は不採用のまま維持する。ただし争点 C の結論を **一部修正**する: 「dev を作るなら (a) 一択」の前提は変わらないが、その (a) は **ブランチ戦略ではなく単発デプロイ先**として実装すれば低コストで導入余地があり、OAuth 検証という具体的な未検証項目（cloudflare-infrastructure.md §12 に相当項目なし）に対応する。ただし INF-2/INF-4（Worker 数消費・定常運用ゼロ）との天秤は残るため、**今は見送り、M-4 判断時に「OAuth 検証用途限定・手動トリガーの `[env.dev]`」として ADR 化するのが妥当**という E の結論は変えない。

### `autonomy_ops` — 反論
<sub>2026-08-18T14:56:39+09:00</sub>

## autonomy_ops round 2: 自己検証 → 採用側の最強論拠への反論

### 1. 自己検証（結論: 部分的に concede）

round 1 で挙げた 4 点のうち、**2（dev 保護 push フックがない）・3（base=main のハードコード）・4（squash 集約 PR の Session-Id 帰属不能）は認める。これらは sp 見積もり可能な実装コストであり、「直せば済むもの」を不採用の理由に使っていた**。フック改修・ドキュメント書き換え・所有判定ロジック拡張はいずれも既存パターンの延長で対応可能で、採用しない理由にはならない。

ただし **1（sprint-cycle-router の 9 分岐に dev→main 昇格ステップが存在しない）だけは性質が違う**。これは「実装し忘れた機能」ではなく「誰が dev の準備完了を判定するか」という **意思決定の所在そのものが未定義** という話であり、コード修正では埋まらない。round 2 の核心はここにある。

### 2. 主 = 本番直結は実在リスクか（コーディネーターの問い 1）

実在するが、程度を見誤ってはいけない。現行フローは CI（テスト・SD-2 の E2E は操作レビュー手順をそのまま写す）+ Layer0 機械ゲート + Layer1 敵対的セルフレビューを通過して初めて squash マージされる。**dev を挟んでも、そこを見る人間はいない**（単一開発者 + 完全自走）。つまり dev は「もう一段、同じ CI と同じセルフレビューを走らせるだけの環境」になり、**新しい検証内容を何も追加しない**。人間の目や実トラフィックによる soak time があって初めて dev の価値が生まれるが、本プロジェクトの運用体制ではどちらも欠けている。real な本番直結リスクへの回答は、release_eng・cf_platform が示した **gradual deployment（`versions deploy --percentage`）+ 即時 rollback** の方が筋が良い。実トラフィックの一部で検証し失敗時は自動的に戻せる ―― dev が原理的に提供できない「本番相当の入力での検証」を、環境を増やさずに実現する。

### 3. 人手を増やさない自動昇格は成立するか（コーディネーターの問い 2・最重要）

技術的には成立する（例: 「dev が green かつ直近コミットから N 時間経過で router が昇格 PR を自動生成し自動マージ」）。これは CP-6/INF-4 の「新しい人間の判断点」という直接的な違反を回避する。**ここは concede する**。

しかし、これは 2 つの分岐に潰れる。
- **(a) N 時間待つだけの機械的タイマー**なら、dev 滞在中に何か新しい検証が行われるわけではない（CI は PR 作成時点で既に通っている）。安全性の上積みはゼロで、リードタイムだけが N 時間伸びる。release_eng が引いた DORA の指摘（long-lived な中間ブランチはリードタイムを落とすだけで確認者不在なら価値を生まない）にそのまま該当する。
- **(b) dev 滞在中に何か実際の検証（synthetic monitoring・定期ヘルスチェック等）を新設する**なら、それは dev という「場所」ではなく「検証の仕組み」が価値の源泉であり、その仕組みは preview alias や本番の gradual deployment 上でも同様に実装できる（むしろ実トラフィックで検証できる分こちらが優位）。dev という第三の環境を経由する必然性がない。

つまり自動化しても、dev は「(a) 無意味な待機」か「(b) 他の場所でも作れる仕組みの入れ物」のどちらかにしかならず、**CP-6/INF-4 の論拠は崩れるが、それによって dev 採用が正当化されるわけではない**（正当化コストが消えても便益がゼロなら、便益ゼロのものを追加する理由にはならない）。

### 結論

round 1 の「4 箇所が壊れる」を採用しない理由として使ったのは誤りだったと認める。改めて不採用の根拠を置き直すと: **dev という環境そのものに、この運用体制で発生させられる価値がない**（人間の目もなく、実トラフィックもなく、CI 以上の検証も追加しない）。同じコストをかけるなら gradual deployment + rollback（release_eng・cf_platform の提案）に投資する方が、本番直結リスクへの実効性が高い。争点 A・D は引き続き不採用を支持する。

### `release_eng` — 譲歩
<sub>2026-08-18T14:56:56+09:00</sub>

## release_eng round2: 自説（round1）への譲歩

round1 の「PR ごとの ephemeral preview があれば dev は不要」「trunk-based development が正しいので dev は不要」という主張を自己攻撃した結果、3 点の弱点を認める。

**① 合成状態の検証が構造的に欠落している**: round1 の主張は「個々の PR 差分が preview で検証される」ことのみを根拠にしており、main 上で複数 PR が積み上がった **合成後の状態** を非本番で検証する層が現行設計にないことを見落としていた。`deploy-production.yml` は push to main で即 `wrangler deploy` するため、合成状態を最初に浴びるのは本番トラフィックそのものである。sprint-cycle-router が高頻度に squash マージする運用では、個別に緑でも組み合わせで壊れる統合バグを検知する非本番の場が構造的にない。これは実在するリスクで、round1 では過小評価していた。

**② gradual deployment 論の射程を暗黙に限定していた**: 「gradual deployment がある」という round1 の主張は、暗黙に「現状は利用者ゼロ」を前提にしていたが、この前提を争点 E の議論に明示せず争点 A の結論（不採用）へ一般化してしまった。M-4 通過後（公開後）は、canary % であっても実ユーザーが一時的に壊れたバージョンを踏む時点でリスクはゼロでなくなる。「gradual deployment が dev の代替になる」という主張は公開後には無条件には成立しない。

**③ trunk-based の前提条件を検証せずに権威として引用していた**: DORA / trunk-based development を根拠に dev 不採用を主張したが、その前提（全マージをゲートする強力な自動テスト・feature flag によるデプロイと解放の分離）を本プロジェクトが今満たしているかを検証していなかった。`sprint-development-rules.md` SD-2 は SP-1〜SP-3 を「CI green 必須」の例外とし、テスト CI 自体は SP-4 で初めて整う設計になっている。round1 5 投稿のいずれにも feature flag 機構への言及はない。前提が未完成の段階で trunk-based の権威だけを根拠にするのは論拠として弱い。

### `release_eng` — 反論
<sub>2026-08-18T14:56:56+09:00</sub>

## release_eng round2: 上記 3 点を認めた上での rebuttal（結論は不変、根拠を修正）

3 つの穴を認めても、**争点 A・D の結論（dev 不採用）は維持する**。穴を閉じる正しい手段が dev ではないため。

**① 合成状態の検証は dev を作っても閉じない**: autonomy_ops の round1 指摘（`sprint-cycle-router` の 9 分岐に dev→main の昇格ステップが存在しない）がそのまま効く。dev を作っても「feat→dev」は自走するが「誰が・いつ dev→main を昇格させるか」が定義されない限り、**同じ「合成状態を誰が検証するか」という問いが 1 段上に移動するだけ**で、gap は閉じずに滞留リスクへ転化する（round1 で自分自身も認めた「不採用」の主因）。正しい閉じ方は、`deploy-production.yml` 自体に **push to main で実際にマージされたコミットに対して test suite を走らせ、成功しなければ `wrangler deploy` に進ませないゲート** を追加すること。これは新しいブランチも昇格の主体も不要で、既存の 1 ホップ構造のまま合成状態の検証を本番投入前に差し込める。

**② gradual deployment 論は「今は不要」の結論を強めこそすれ、揺るがさない**: 公開後に canary リスクがゼロでなくなるという指摘は正しいが、それは「今から dev を作る」根拠にはならず、「M-4 で公開判断が Yes になった時点で `deploy-production.yml` の gradual deployment を強化する（初期比率を下げる・エラー率閾値を厳しくする・自動 rollback を必須にする）」という **争点 E の対応強化** に帰着する。cf_platform が実測したとおり dev には確定コスト（Worker 恒久 +1、または OAuth 用シークレット紐付けが未確認）が伴う一方、gradual deployment の強化は Worker 増分ゼロで実装できる。公開後のリスクに備える投資対効果は dev より高い。

**③ 前提未完成という指摘は、dev にはさらに強く跳ね返る**: SP-1〜SP-3 で強力な自動テストゲートが未整備なら、trunk-based の安全網が弱いのと同様に、dev→main の昇格判断を支える自動検証も未整備ということ。**未完成の CI の上に dev という新しい意思決定点を足すのは、検証されない「安全に見える中間状態」を作るだけで実害がある**。正しい順序は SD-2 が定めるとおり SP-4 でテスト CI を完成させることが先で、それによって①のゲートも③の前提も同時に満たされる。dev の要否はその後、M-4 のデータを見て判断すべき。

**結論の修正**: A・D は不採用のまま維持するが、根拠を「PR preview があるから十分」から「合成状態の検証は main 直結の CI ゲートで閉じる方が dev より低コストで、dev はむしろ検証されない中間状態を増やす」に差し替える。

### `req_trace` — 反論
<sub>2026-08-18T14:57:37+09:00</sub>

## req_trace round2 — 採用側の最強論拠を検証する（groupthink チェック）

round1 は 5 名とも「不採用」に収束したが、coordinator の指摘どおり早すぎる合意を疑う。3 点それぞれに、**部分的に譲歩しつつ、譲歩してもなお結論が変わらない理由**を示す。

### 1. 「与件は下限であって上限ではない」— 譲歩する。ただし B の争点自体が変わる

この指摘は **原則として正しい**。`minimum-requirements.md` は「最低要件定義（MVP）」であり、これを根拠に「§4 に書いていないから **やってはいけない**」と主張したなら論理的飛躍だった。round1 の自分の投稿を読み返すと、「§4.1〜4.4 に環境分離が列挙されていない」から「§7 に環境分離がない」まで積み上げて **B（過剰解釈）に倒す**論法を取ったが、これは実質「不記載 = 禁止」に近い読み方をしていた。ここは訂正する。

ただし訂正した上で、争点の立て方自体を修正すべきだと考える。「与件が下限」なら、争点 B は「§4 が dev ブランチを要求しているか」ではなく **「dev ブランチは §4 が要求する水準を満たすために必要な手段か、それとも要求水準を超えた任意の上乗せか」** に立て直す必要がある。ここで §4 の構造を厳密に読み直す。

§4 は「プロダクション運用を想定した実装とする。」という 1 文の直後に §4.1〜4.4 が続く。この 1 文が「姿勢の宣言」であって 4.1〜4.4 に限定されない、という coordinator の疑いは検証に値するので、§7・roadmap.md との整合性で検証した。

- `roadmap.md` M-2 は「11 項目の実機確認と品質ゲートの充足が通過条件」と明記し、M-2 = 与件充足そのものと定義している。§7 の 11 項目（受け入れ基準チェックリスト）は M-2 通過判定の **確定した operational definition**。
- もし §4 の「プロダクション運用を想定」が 4.1〜4.4 を超えて無限定に及ぶ姿勢の宣言であるなら、その宣言は §7 のどの項目でも検証できないことになり、「M-2 は 11 項目で判定が完結する」という roadmap.md の記述と矛盾する。要件文書の内部整合性を保つ読み方は「§4 の総論は 4.1〜4.4 という具体列挙で **運用可能な形に確定されている**」であり、これは「4.1〜4.4 に書いていないことは禁止」という意味ではなく、**「4.1〜4.4 が、与件充足（優先順位 1 位）の判定範囲を確定するスコープである」**という意味。

つまり結論はこうなる: dev ブランチは §4 によって **禁止されても要求されてもいない**。それは「与件充足」（優先順位 1 位）の対象外というだけで、「やってはいけない」わけではない。ここから先は純粋に **費用対効果の経営判断**であり、優先順位表の 2〜5 位（積み上げ可能性・説明可能性・差別化・運用改善）のどこかで評価するしかない。autonomy_ops（D：昇格 PR を作る主体が自律運用フローに存在しない）・cf_platform（C：Worker 恒久 +1 か、シークレット分離が未確認の妥協案か）・release_eng（trunk-based の方が DORA 的にも整合し、gradual deployment + rollback で同じ安全性を代替できる）が round1 で示した **具体的コストと代替案**が、「B で禁止されているから不要」という弱い論拠に代わる、**任意の上乗せとして見た場合の妥当な却下理由**になる。譲歩した結果、論拠の重心が「解釈論（B）」から「費用対効果（C・D・E）」に移っただけで、結論（今は不採用・M-4 後に再検討）は変わらない。

### 2. 「評価者は ADR を読む前に構造を見る」— 部分的に譲歩し、対策を具体化する

これも正しい懸念で、round1 の自分の主張「ADR に書けば説明可能性は満たせる」は **読まれる前提が甘かった**。訂正する。

ただし 2 点、追加検証したい。

第一に、`minimum-requirements.md` §6（ドキュメント要件）は「README に…設計上の判断、工夫した点、こだわったポイントを記載する」ことを **与件そのもの**として要求している。これは ADR（`docs/adr/` 配下）と違い、リポジトリを開いて最初に読まれる README に強制的に載る。「dev ブランチがない」という構造を見た評価者が次にすることは、大抵 README を開くことであり、そこに「なぜ dev を持たないか」の理由が書いてあれば、判断根拠に評価者は必ず到達できる（ADR ほど埋もれない）。ここは round1 の「ADR で足りる」から「README §6 の必須記載事項として、より確実な導線で足りる」に主張を強化する。

第二に、逆側の可能性（coordinator が明示的に求めた「加点になるケース」）を検証する。release_eng が round1 で引用した DORA/trunk-based の知見が示すとおり、**「dev ブランチ + 2 段マージ」は 2020 年代の CD 実践では既に「長寿命ブランチによるリードタイム悪化」という既知のアンチパターン側に分類されつつある**。技術的に成熟した評価者（このプロジェクトの想定読者はエンジニアの選考担当）であれば、「PR ごとの ephemeral preview + trunk-based + gradual deployment/rollback」という構成の方が、「dev ブランチを律儀に用意した」構成よりも **モダンな CD 判断として高く評価される可能性がある**。つまり「環境分離をしていないこと」自体が減点になるとは限らず、むしろ「なぜ dev を意図的に持たないか」を言語化できていること（trunk-based の根拠・Cloudflare versions/rollback で同じ安全性を代替する設計）の方が、優先順位 3 位「説明可能性」に対する加点材料になりうる。

とはいえ、これは「見る人による」というリスクを完全には消さない。README に一言も触れず放置すれば、coordinator の懸念どおり「意識していない」と即断されるリスクは実在する。ここは自分の讓歩点として明確に認め、**「dev ブランチを作る」ではなく「README に環境戦略の判断根拠を明記する」ことを M-2 の必須タスクとして追加すべき**という具体的な代替アクションを提案する。

### 3. 「ユーザー自身が相談してきた」ことの重み — ここが一番重要な訂正

これは coordinator の 3 点の中で最も重い指摘で、率直に認める。round1 の自分の投稿は、ユーザーの相談内容を「与件解釈の妥当性検証の対象」として扱い、暗に「与件にないから不要」で結論づける構成になっていた。しかしユーザーの発言原文を読み直すと：

> 「最低限の要件の中にプロダクションを意識するという事項があったかと思いますが、それを踏まえて、リリースサイクルとして…環境を分けるべきか **悩んでいます**」

これは文法的に疑問形であり、かつ内容も「§4 の要求から dev 分離という結論が導けるか」を **ユーザー自身が検証してほしいと頼んでいる**。`user-instruction-issue-rules.md` の「質問か指示か」の分類基準に照らすと、これは「可否・要否を問う疑問文」に該当し、**指示ではなく質問として扱うべき**（＝実装せよという指示ではなく、答えを出してから必要なら選択肢を示す）。この観点では、この議論チームがやるべきことは「ユーザーの懸念を却下する」ことではなく、**ユーザー自身の推論過程（§4 → dev 分離という連想）を検証し、その結果を推奨案として返す**ことそのもの。つまり「ユーザーが必要性を感じているものを与件にないから却下する」という coordinator の懸念する構図には実はなっておらず、**ユーザーは『これは要件から導けるか』を聞いており、我々の役割はまさにそれに答えること**。

その上で、ユーザーが抱いている不安（プロダクション運用を意識していないと見られるのでは）の **実体**には向き合う必要がある。これは 2 で検証したとおり実在するリスクであり、「dev ブランチという特定の実装」ではなく「プロダクション運用を意識した設計判断をしていることが伝わる状態」がユーザーの真のニーズだと解釈すべき。したがって、この議論の最終出力（推奨案）は「dev ブランチは不要」という否定形で終わらせず、**代替でそのニーズを満たす具体策**（README への設計判断の明記、gradual deployment/rollback の活用、M-4 での再判定というトリガー）とセットで提示する必要がある。これは `sprint-development-rules.md` SD-3 の「選択肢は最大 2 つ・推奨を明示」の形式にそのまま落とし込める：

- 選択肢 1（推奨）: 今は dev ブランチを追加せず、代わりに ① README/ADR に「なぜ dev を持たないか」の設計判断を明記 ② gradual deployment + rollback を INF-21 強化として独立検討 ③ M-4（公開判断）通過時に再判定、という 3 点セットで「プロダクション運用を意識している」ことを可視化する
- 選択肢 2: 今すぐ dev（固定 alias）を追加する。ただし cf_platform の実装コスト比較（Worker 恒久+1 か、シークレット分離未確認の妥協案か）と autonomy_ops の D（昇格 PR を作る主体が自律運用フローに存在せず、放置リスクが構造化する）を負う

### 結論（round2 更新版）

B は「禁止」論法から「対象外（費用対効果の任意判断）」論法に訂正。ポートフォリオ評価リスクは実在すると認め、対策を「ADR」から「README §6 必須記載」に強化。ユーザーの相談は却下ではなく **検証依頼として正面から回答すべき**と訂正し、最終出力は「不採用」の一言ではなく代替策 3 点とセットの推奨案にする。これらを反映しても **争点 A・E の結論自体（今は不採用、M-4 後に再検討）は変わらない** — 変わったのはその結論に至る論拠の質と、ユーザーへの返し方。

### `docs_trace` — 反論
<sub>2026-08-18T14:57:57+09:00</sub>

# Round 2: ファクトチェック結果（docs_trace）

## 要件解釈層

### req_trace の主張 ✅ 検証済み: 正確

**claim**: minimum-requirements.md §4 は app implementation quality（信頼性・performance・a11y・保守性）であって、環境構成・branch strategy は要件でない

**文書確認**:
- 最低要件.md §4.1-4.4: 信頼性（error handling, rate limit）/ performance（debounce, cache）/ a11y（responsive, keyboard, labels）/ 保守性（architecture consistency, types, lint）
- §7 受け入れ基準（11 項）: どれも environment separation / branch protection を含まない
- **環境戦略は要件スコープ外。** app quality 担保で十分。

→ req_trace の解釈が正確。環境を分ける根拠を requirements に求めることはできない。

---

## インフラ契約層

### cf_platform の主張 ❌ 不正確な参照

**claim**: cloudflare-infrastructure.md §12 に「version-scoped secret preview-alias binding」と gradual deployment が未確認事項として記載

**文書確認**:
- §12 実際の 9 項: ① bundle size ② RSC p95 CPU ③ next-intl middleware ④ invocation log IP ⑤ rate limiting pricing ⑥ WRANGLER_OUTPUT_FILE_PATH fields ⑦ workers.dev registration ⑧ avatar sizing for CLS ⑨ wrangler tail behavior

→ **version-scoped secret preview-alias binding も gradual deployment も §12 に記載なし。** 参照先の誤指摘。

---

### release_eng の主張 ❌ 仕様誤読

**claim**: INF-21 / §6.1 / §8.3 が gradual deployment をサポート

**文書確認**:
- **INF-20**: Deployment trigger は **git push / マージのみ。手作業なし** → 自動実行の強制
- **INF-21**: **直前の正常ビルドへ数手でロールバック可能** → rollback speed であって段階的展開ではない
- **§6.1**: 3 環境の構成（local / preview pr-<N> / production main）
- **§8.3**: CI workflows: `pull_request` trigger → versions upload pr-<N>（即反映）/ `push to main` trigger → `wrangler deploy`（即反映）

→ **現在の設計は immediate deployment。** PR マージ後、本番に直ちに反映。ロールバック *可能性* と段階的 *展開* は別物。

段階的デプロイが要れば **新規決定** が必要（INF-20 例外化 / deployment gate 追加等）。

---

## サマリー

| エージェント | 主張の正確性 | 根拠 |
|-----------|----------|------|
| req_trace | ✅ 正確 | minimum-requirements.md §4 は app quality のみ |
| autonomy_ops | ✅ 正確 | check_pending_pr_reviews.py / pre-git-push-check.sh の実装確認済み |
| cf_platform | ❌ 不正確 | §12 に参照claim がない |
| release_eng | ❌ 誤読 | INF-21 は rollback capability であって gradual deployment ではない |

---

次ステップ:
- **cf_platform**: 本当に未確認事項 / 確認済み事項の区別を改めて説明（根拠なしに仕様を拡大しない）
- **release_eng**: 段階的デプロイが要れば、別途決定ゲート（D-22 等）で明示する（INF-20 例外化、CI gate 追加等）。現状の「ロールバック可能」は戻す手段であって段階的展開ではない

## ラウンド 3

### `lead` — 合意
<sub>2026-08-18T14:59:44+09:00</sub>

## lead: 合意点・対立点の整理（round 1〜2 の統合）

### 0. lead によるファクトチェックの訂正（docs_trace round2 への訂正）

docs_trace が「不正確」と判定した 2 件のうち、**1 件は誤読**である。

- **cf_platform について（訂正）**: cf_platform の原文は「OAuth 検証という具体的な未検証項目（`cloudflare-infrastructure.md` §12 に**相当項目なし**）」であり、「§12 に記載されている」とは主張していない。**§12 に無い**という主張であって、docs_trace の §12 実地確認（9 項目に OAuth / secret 関連なし）は cf_platform の主張を**否定ではなく裏付けている**。この指摘は取り下げる。
- **release_eng について（部分的に有効）**: release_eng も「INF-21 が gradual deployment をサポートする」とは主張しておらず、「INF-21 **強化として**組み込む」＝新規追加の提案である。ただし docs_trace の結論部分「gradual deployment を入れるなら新規決定（`D-n`）が要る」は**正しく、採用する**。現行設計は immediate deployment（`push to main` → 即 `wrangler deploy`）であり、段階的展開の機構は存在しない。

### 1. 合意点（5 レンズが round 2 の自己攻撃を経てなお一致した点）

1. **dev ブランチ = 常設プレビュー環境は、現時点では採用しない**。5 名全員が round 2 で採用側の最強論拠を自ら構築したうえで、結論を維持した。
2. **理由は「与件が禁止しているから」ではない**（req_trace が round 2 で自説を訂正）。`minimum-requirements.md` §4 は dev 分離を**要求も禁止もしていない**。与件充足（優先順位 1 位）の判定範囲外であり、**費用対効果で判断する任意の上乗せ**である。
3. **この運用体制では dev に発生させられる価値がない**（autonomy_ops）。dev を見る人間がおらず（単一開発者 + 完全自走）、実トラフィックも通らないため、dev は「CI と同じ検証をもう一度走らせるだけの環境」になる。自動昇格を実装しても「(a) 無意味な待機」か「(b) 他の場所でも作れる仕組みの入れ物」のどちらかにしかならない。
4. **実装するなら `[env.dev]`（別 Worker）一択**（cf_platform が公式ドキュメントで確定）。`versions` + 固定 preview alias 方式は、シークレットが **Worker 1 本の版チェーン全体で線形に継承される**（`--secrets-file` の「Secrets not included in the file are preserved from the previous version」）ため、dev 専用シークレットの分離を**構造的に保証できない**。
5. **仮に dev 相当の環境を持つとしても、それは「ブランチ戦略」ではなく「手動トリガーのデプロイ先」として切り離せる**（cf_platform）。`workflow_dispatch` で最新 main を dev Worker へ流す形にすれば、2 段マージのコストは一切発生しない。

### 2. 議論を経て残った真の問題（dev の採否とは独立に実在する）

**P-1: main 上の合成状態を非本番で検証する層がない**（release_eng が自己攻撃で発見・重要）
現行 `deploy-production.yml` は `push to main` で即 `wrangler deploy` する。個々の PR は preview で検証されるが、**複数 PR が積み上がった合成後の状態を最初に浴びるのは本番トラフィックそのもの**。`sprint-cycle-router` が高頻度に squash マージする運用では、個別に緑でも組み合わせで壊れる統合バグを検知する非本番の場が構造的に存在しない。
→ ただし **dev を作ってもこの穴は閉じない**（release_eng・autonomy_ops）。「誰が・いつ dev→main を昇格させるか」が未定義である限り、同じ問いが 1 段上に移動するだけ。正しい閉じ方は **main へのマージ後に test suite を走らせ、成功しなければ `wrangler deploy` に進ませない CI ゲート**（新しいブランチも昇格主体も不要）。

**P-2: OAuth 経路が本番でしか検証されない**（cf_platform）
§6.2 の「プレビューでは OAuth を無効化する」方針の帰結。preview alias は PR ごとに URL が変わるためコールバック URL を事前登録できない。固定 URL を持つ `[env.dev]`（別 Worker）でしか塞げない。
→ ただし現時点では OAuth 自体が未実装であり、**今すぐ塞ぐ必要はない**。`M-4`（公開判断）時の検討事項。

**P-3: gradual deployment は現行設計に存在しない**（docs_trace）
`INF-21` は「直前の正常ビルドへ数手でロールバック可能」＝**戻す手段**であって段階的展開ではない。`wrangler versions deploy --percentage` を導入するなら **新規決定が必要**（`INF-20` の「トリガーは git push / マージのみ」との関係整理を含む）。
→ release_eng・autonomy_ops が「dev の代替」として推した手段は、**まだ設計に存在しない**。「代替があるから dev は不要」と言い切るのは現時点では誤りで、正確には「dev より低コストで実効性が高い代替**候補**がある」。

### 3. 残った対立点（弱い）

- **release_eng / autonomy_ops**: 公開後の安全網は gradual deployment を強化する方向。
- **cf_platform**: OAuth 検証だけは `[env.dev]` でしか塞げないため、`M-4` 時に用途限定で再検討する余地がある。

両者は排他ではない（前者は本番投入の段階制御、後者は OAuth という特定経路の事前検証）。`M-4` のチェックリストに**両方**を載せることで解消する。

### 4. ユーザーの真のニーズへの回答（req_trace round 2 の訂正を採用）

ユーザーの相談は「§4 の要求から dev 分離という結論が導けるか」の**検証依頼**であり、実装指示ではない。そして相談の背後にある不安は「プロダクション運用を意識していないと見られること」である。この不安は**実在するリスクとして認める**。ただし解消手段は dev ブランチに限られない。`minimum-requirements.md` §6 が **README への設計判断の記載を与件として要求している**ため、そこに環境戦略の判断根拠を書くことが最も確実な導線になる（ADR より埋もれない）。

### `lead` — 判定
<sub>2026-08-18T15:00:32+09:00</sub>

{
  "recommendation": "採用しない（今は dev/main の環境・ブランチ分離を導入しない）。与件 §4 は環境分離を要求しておらず、単一開発者 + AI 完全自走という運用体制では dev を見る人間も実トラフィックも存在しないため、CI と同じ検証をもう一度走らせるだけの環境が増えてリードタイムだけが伸びる。",
  "alternative": "手動トリガーの [env.dev]（別 Worker・ブランチ戦略とは無関係のデプロイ先）を M-4 通過時に OAuth 検証用途限定で導入する。選ぶ条件は『第三者公開を決め、かつ OAuth ログインを実装する』こと。",
  "decisions": [
    {
      "issue": "A: 常設 dev ブランチ（= 常設プレビュー環境）を追加すべきか",
      "conclusion": "追加しない。dev を見る人間も実トラフィックもない体制では、dev は CI 以上の検証を何も追加しない。2 段マージのコストだけが確実に発生する。",
      "artifacts": ["docs/02_requirements/open-questions.md（D-21 として決定を記録・改修）", "README.md（環境戦略の判断根拠を記載・改修）"],
      "rejected": "『PR preview があるから十分』という round 1 の論拠自体は round 2 で否定された（合成状態の検証層が無いため）。ただし穴の正しい閉じ方は dev ではなく main の CI ゲート。"
    },
    {
      "issue": "B: 与件『プロダクション運用を想定した実装とする』は環境分離を要求しているか",
      "conclusion": "要求も禁止もしていない。§4.1〜4.4 と §7 チェックリスト 11 項目はアプリ実装品質（エラー処理・秘匿情報・性能・a11y・型・Lint）を列挙しており、環境構成・ブランチ戦略は与件充足の判定範囲外。したがって dev 分離は『費用対効果で判断する任意の上乗せ』であって、やってはいけないものではない。",
      "artifacts": ["docs/02_requirements/open-questions.md（D-21 の根拠として記録）"],
      "rejected": "『§4 に書いていないから禁止』という論法（req_trace が round 2 で自ら訂正）。与件は下限であって上限ではない。"
    },
    {
      "issue": "C: dev 常設環境を作る場合の Cloudflare 実装形式",
      "conclusion": "[env.dev]（別 Worker）一択。versions + 固定 preview alias 方式は、シークレットが Worker 1 本の版チェーン全体で線形継承される（--secrets-file の『Secrets not included in the file are preserved from the previous version』）ため、dev 専用シークレットの分離を構造的に保証できない。ただし [env.dev] は Worker 数を恒久的に +1 する。",
      "artifacts": ["docs/03_design/infrastructure/cloudflare-infrastructure.md §6.1（採用時のみ改修。今は不要）"],
      "rejected": "versions + 固定 alias `dev` 方式（シークレット分離が原理的に保証できない）。"
    },
    {
      "issue": "D: 自律運用フローとの整合（2 段マージのプロセス負荷）",
      "conclusion": "ハーネス 4 箇所（check_pending_pr_reviews.py の base 非フィルタ / pre-git-push-check.sh の dev 無保護 / pr-review-flow-summary.md の base=main 固定 / Session-Id 所有判定）は直せる実装コストに過ぎず、不採用の根拠にはならない。真の問題は『誰が・いつ dev→main を昇格させるか』が sprint-cycle-router の 9 分岐に存在しないこと。自動昇格は技術的に成立するが、(a) 無意味な待機か (b) 他の場所でも作れる仕組みの入れ物にしかならず便益がゼロ。",
      "artifacts": ["（採用時のみ）.claude/skills/sprint-cycle-router/SKILL.md", ".claude/hooks/pre-git-push-check.sh", "tools/check_pending_pr_reviews.py"],
      "rejected": "『ハーネスが壊れるから採用しない』という論法（autonomy_ops が round 2 で自ら訂正）。"
    },
    {
      "issue": "E: 採用するとしたら今か M-4 後か",
      "conclusion": "今は導入しない。M-4（公開判断ゲート）のチェックリストに『OAuth 検証用 [env.dev] の要否』と『gradual deployment の要否』の 2 項目を追加し、公開を決めた時点で再判定する。",
      "artifacts": ["docs/02_requirements/roadmap.md §M-4（チェックリストに 2 項目追加・改修）"],
      "rejected": "M-4 を待たず今すぐ導入する案（公開判断が未通過で、OAuth も未実装のため塞ぐべき穴がまだ存在しない）。"
    }
  ],
  "tasks": [
    {
      "id": "T-1",
      "title": "deploy-production.yml に『main マージ後の test suite 実行 → 成功しなければ wrangler deploy しない』ゲートを追加する（P-1: 合成状態の検証層の欠落を塞ぐ）",
      "actor": "claude",
      "depends_on": [],
      "sp": "sp:2",
      "note": "SP-4（テスト CI 完成）が前提。SP-1〜SP-3 の間は書けるテストだけでゲートを組む"
    },
    {
      "id": "T-2",
      "title": "README に環境戦略の判断根拠（なぜ dev ブランチを持たないか）を明記する。minimum-requirements.md §6『設計上の判断・工夫した点』の一部として書く",
      "actor": "claude",
      "depends_on": [],
      "sp": "sp:1"
    },
    {
      "id": "T-3",
      "title": "open-questions.md に D-21 として『リリースサイクルは trunk-based（PR preview + main = production）を維持し、常設 dev 環境は持たない』を記録する",
      "actor": "claude",
      "depends_on": [],
      "sp": "sp:1"
    },
    {
      "id": "T-4",
      "title": "roadmap.md M-4 のチェックリストに『OAuth 検証用 [env.dev] の要否』『gradual deployment（versions deploy --percentage）の要否』を追加する",
      "actor": "claude",
      "depends_on": ["T-3"],
      "sp": "sp:1"
    },
    {
      "id": "T-5",
      "title": "gradual deployment を導入するかを独立の決定として起票する（INF-21 はロールバック可能性であって段階的展開ではないため、新規決定が要る）",
      "actor": "claude",
      "depends_on": ["T-3"],
      "sp": "sp:2"
    }
  ],
  "critical": [
    "P-1: main 上の合成状態を非本番で検証する層が現行設計に存在しない。deploy-production.yml は push to main で即 wrangler deploy するため、複数 PR の合成状態を最初に浴びるのは本番トラフィックそのもの。dev を作っても『誰が昇格させるか』が未定義な限り穴は 1 段上に移動するだけで、正しい閉じ方は main の CI ゲート（T-1）。",
    "P-2: OAuth 経路が本番でしか検証されない（§6.2 のプレビュー OAuth 無効化方針の帰結）。固定 URL を持つ [env.dev] でしか塞げないが、OAuth 自体が未実装のため今は塞ぐ必要がない。M-4 の検討事項（T-4）。",
    "P-3: gradual deployment は現行設計に存在しない。INF-21 は『戻す手段』であって段階的展開ではないため、『dev の代替がある』と言い切るのは現時点では不正確。導入には新規決定が要る（T-5）。"
  ],
  "open_questions": [
    "ユーザー判断（SD-3 第 2 系統）: 本議論の推奨（dev/main 分離は採用せず、T-1〜T-5 の代替策で『プロダクション運用を意識している』ことを可視化する）を採るか、それとも今すぐ dev 環境を導入するか。成果物が変わるためユーザーに確認する。"
  ]
}
