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
- 投稿数: 5
- 更新: 2026-08-18T14:54:19+09:00

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
