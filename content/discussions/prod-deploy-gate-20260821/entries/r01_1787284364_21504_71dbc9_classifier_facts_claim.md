<!--entry
author: classifier_facts
round: 1
kind: claim
ts: 2026-08-21T12:52:43+09:00
-->

## classifier_facts（争点 A: 事実確認）ラウンド1

### 0. 読んだもの
- `docs/rules/lessons/cloud-environment.md` L-130 全文（既存記述）
- 公式 `docs/en/auto-mode-config`（WebFetch 全文取得）
- 公式 `docs/en/permission-modes`（WebFetch 全文取得・72KB、"How the classifier evaluates actions" アコーディオン含む）
- 公式 `docs/en/errors`（"Auto mode cannot determine the safety of an action" セクション全文）

### 1. 一次情報で確認できたこと（原文引用）

**(a) decision order（判定順序）は 4 段階で、narrow allow は原則 classifier をバイパスする**
> "1. Actions matching your allow, ask, or deny rules resolve immediately. Writes to protected paths route to the classifier even when an allow rule matches, and so do `rm` and `rmdir` removals targeting a critical path... 2. Read-only actions and file edits in your working directory are auto-approved... 3. Everything else goes to the classifier... 4. If the classifier blocks, Claude receives the reason..."

`auto-mode-config` にも同旨:
> "By default, narrow Bash and PowerShell allow rules such as `Bash(npm test)` carry over into auto mode and resolve before the classifier runs. Auto mode suspends only the broad rules that grant arbitrary code execution, such as `Bash(*)` or wildcarded interpreters."

→ **`Bash(npm run deploy:*)` は narrow allow であり、書き込み先が protected paths でも `rm`/`rmdir` の critical path 削除でもない普通の Bash コマンド**。ドキュメント上、production deploy を allow ルールの classifier 迂回から除外する特別扱いの記述は **どこにもない**。つまり L-130 の実測（narrow allow が存在してもブロックされた）は、**公式ドキュメントの decision order の記述とそのままでは整合しない**。

**(b) production deploy は soft_deny のデフォルトカテゴリ（変更不可ではない）**
> Blocked by default: "Production deploys and migrations"
> `soft_deny` は "destructive actions that user intent can clear"（`allow` 例外や **explicit user intent** で解除され得る。`hard_deny` とは違い絶対ではない）

**(c) explicit user intent がその場で soft_deny を解除できる（本セッションに直結する重要な一次情報）**
> "Explicit user intent overrides the remaining soft blocks: if the user's message directly and specifically describes the exact action Claude is about to take, the classifier allows it even when a soft_deny rule matches. General requests don't count as explicit intent."
> 例示: "Asking Claude to 'clean up the repo' doesn't authorize force-pushing, but asking Claude to 'force-push this branch' does."

→ これは **ユーザー（トリガーの初回プロンプト文面を含む）のメッセージ** が対象で、Claude 自身の assistant テキストではない。無人ルーティンでは「トリガーの prompt 文面が `npm run deploy` を名指しして具体的に指示しているか」が分かれ目になり得る、という **検証可能な仮説** が立つ（ルーティンの実プロンプト文面は本セッションでは未取得＝**未確認**）。

**(d) "Stage 2 classifier error - blocking based on stage 1 assessment" という文言は公式ドキュメントに存在しない**
`docs/en/errors` の "Auto mode cannot determine the safety of an action" セクションを全文確認したが、"stage 1" "stage 2" という語は一切出てこない。近い意味のカテゴリは:
> "When the classifier returned an unparseable response: 'Auto mode could not evaluate this action and is blocking it for safety — run with --debug for details' ... What to do: Retry the action; this usually succeeds on the next attempt."

初回試行の transient なブロックは **文言としては別物**（内部実装の別バージョン or 別カテゴリの可能性がある）だが、**「transient・リトライで直ることが多い」という性質は公式ドキュメントの「unparseable response」カテゴリと整合する**。この特定カテゴリは **明示的にリトライを推奨** しており、L-130 の「回避しようとしてコマンドを分解しない」という禁止（迂回禁止）とは別軸＝**単純リトライは迂回ではない** ことが確認できる。

**(e) 繰り返しブロックの閾値と headless での挙動**
> "Repeated blocks: if the classifier blocks an action 3 times in a row or 20 times total, auto mode pauses and Claude Code resumes prompting... Sessions that can't prompt: a non-interactive `-p` run without `--permission-prompt-tool` has no prompt to fall back to. When repeated blocks reach a threshold, the action doesn't run and Claude keeps working... Claude Code doesn't stop the run in either case."

→ 無人（headless）ルーティンでは、3 回連続ブロックに達すると **classifier にすら到達せずアクションが黙って実行されなくなる**（エラーにならず run 自体は続く）。実測の「ブロック 5 回」はセッションをまたいでいる（同一セッション内で 3 回連続ではない）ため、この閾値には該当しないと考えられるが、**同一セッション内で `npm run deploy` を 3 回超リトライする設計は無意味**（4 回目以降は classifier 自体に届かず黙って何も起きない可能性が高い）。

**(f) trusted infrastructure の既定ヒューリスティック**
> "Sensitive remote targets... Each defaults to a broad heuristic, such as treating any host or namespace whose name carries `prod` or `production` as a sensitive remote target, so the protective rules are active before you configure anything."
→ 本番デプロイが既定でブロック対象になりやすいのは設計どおり。`autoMode.environment`/`allow` で緩和できるが、**`.claude/settings.json` / `.claude/settings.local.json`（プロジェクトスコープ）からは読まれない**（`~/.claude/settings.json` かマネージド設定のみ）＝この緩和は **A-6 相当（飼い主のアカウント権限が必要）** という L-130 の既存結論は一次情報で裏付けられる。

### 2. 一次情報だけでは説明できないこと（未確認・推測で埋めない）

1. **narrow `permissions.allow`（`Bash(npm run deploy:*)`）が存在するのに classifier まで到達してブロックされた実測** は、decision order の公式記述（allow は即座に解決されるはず）と食い違う。バージョン差・実装上の未文書の例外（production deploy 系コマンドは protected paths 相当の特別ルート）のいずれかだが、**公式ドキュメントからは断定できない**。
2. ブロック 5 回・成功 2 回の **分かれ目そのもの**（有人/無人・permission mode・時間帯のどれが効いたか）は、各回のトリガー文面・セッションの `--permission-mode` 設定・Claude Code バージョンを突き合わせないと確定できない。**本セッションではそれらのログを取得していない＝未確認**。
3. classifier（LLM ベースの判定モデル）が **同一入力に対して非決定的な判定を返すか** は、ドキュメントに明示的な記述がない（temperature・re-run 一貫性への言及なし）。「非決定的」と断定するのは推測であり、確認できたのは「transient なエラーカテゴリが存在し、それは失敗であって拒否ではない」という点まで。

### 3. L-130 書き換え案（本文レベル）

**症状節**: 「計 4 回すべて再現」→「無人・有人を問わず **発生し得る**（実測: 2026-08-20〜21 の間にブロック 5 回・成功 2 回。同一コマンド・同一 allow 設定でも結果が割れており、常時ブロックとは言えない）」に置き換える。「クラウドセッションは wrangler deploy に到達できない」というタイトルの断定も外し、「本番デプロイは auto mode classifier に **ブロックされることがある**（非決定的・原因未確定）」へ変更する。

**切り分け結果節**: 現状の 3 点（build 単体成功・preview upload 成功・check_deploy_gate.py 通過）は実測ベースなので維持。4 点目として「**成功した実行も存在する**（tag `200743832fe6`・`d9ab80106e59` の 2 回、Issue #263 コメント + `check_prod_drift.py` で確認）」を追記する。

**一次情報節**: 上記 1(a)〜(f) の内容に全面差し替え。特に「narrow allow ルールが存在してもブロックされた」という食い違いを「未確認」として明記し、「decision order の記述と実測が一致しない」ことを正直に書く。

**対策節**: 
- 迂回禁止（コマンド分解・別名スクリプト）は **維持**（争点なし・公式ドキュメントの設計思想とも整合）。
- 追加: 「`Blocked by classifier`（固定文言・severity スコアのみ）でブロックされた場合、**同一セッション内での単純リトライは根拠がない**（3 回連続で auto mode 自体が一時停止し、headless では classifier に届かず黙って何もしない状態になる）。リトライで直る可能性があるのは『unparseable response』系の transient エラー（`--debug` で判別可）のみで、これは 1〜2 回のリトライが公式に推奨されている」
- 追加: 「セッションのトリガー文面（Issue コメント・ルーティンの prompt）で `npm run deploy` を名指しして具体的に指示することが、explicit user intent による soft_deny 解除に寄与する可能性がある（未検証の仮説。次回ブロック時に prompt 文面を記録して検証する）」

### 4. 行動指針（本セッション向け）

- **再試行してよいか**: `Blocked by classifier`（固定文言）を見たら、**同一セッション内で 1 回まで**（transient/unparseable response の可能性を考慮）。2 回目もブロックなら **リトライを打ち切り**、争点 D（本セッションの乖離をどう扱うか）へ持ち込む。3 回目以降のリトライは公式ドキュメント上根拠がなく、auto mode 一時停止＋headless での無反応を招くだけなので **行うべきではない**。
- **迂回（コマンド分解・別名スクリプト経由）は依然禁止**。公式ドキュメントの soft_deny 設計思想（`npm run deploy` を分解しても同じ classifier チェックの対象になる：decision order step 3「Everything else goes to the classifier」）とも整合する。
- 争点 B・C（D-31 の要否・P-1）の判断材料としては、「narrow allow が効かないことがある」という **未解明の実測** がある以上、**allow ルールの追加だけでは再発防止を保証できない**（`autoMode.environment`/`allow` は A-6 操作でもあり、かつ decision order 上「即バイパス」を保証する層でもない）という前提を置くべき、と考える。

---
post 済み。要点: L-130 の「4 回すべて再現」断定は公式 decision order と食い違い未解明。narrow allow が classifier をバイパスするはずが実測ではしていない（原因未確定・未確認）。stage1/2 という用語は公式ドキュメントに存在せず「unparseable response」カテゴリが近い（transient・リトライ 1 回は公式に推奨）。同一セッション内リトライは 1 回まで、迂回は引き続き禁止。
