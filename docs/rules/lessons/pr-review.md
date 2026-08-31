# Warm 層 教訓 — PR レビュー・自動マージ

PR 作成・AI レビュー監視・自動マージに関するカテゴリ別教訓（タスク依存で Read）。

---

## L-050: PR 作成直後に存在確認しないとサイレントスキップを見逃す（2026-06-13）

**パターン**: `gh pr create` がプロキシ環境やエラーで失敗しても、戻り値を確認せず
「PR 作成済み」と思い込んで次の処理（レビュー依頼・マージ）に進む。実際には PR が無く、
作業がサイレントに失われる。

**根本原因**: PR 作成コマンドの成否を検証していない（Time-of-Check の欠落）。

**対策**: PR 作成の **直後に必ず存在確認** する。`pr-review-flow-summary.md` の必須フォーム。

クラウド（一次経路・L-114）:
```
mcp__github__list_pull_requests(owner="kai-kou", repo="gem-hunter",
                                head="kai-kou:{branch}", state="all")
```

ローカル実行用:
```bash
gh pr list --head {branch} -R kai-kou/gem-hunter --limit 1 --json number,url,state \
  --jq '.[0] | select(.url != null) | "PR #\(.number) \(.state): \(.url)"'
```

存在確認が取れない場合は PR 作成を再試行する（マージへ進まない）。

---

## L-102: AI レビュー指摘対応はユーザーに報告しない（サイレント原則）（2026-06-13）

**パターン**: AI レビュー（Gemini / Copilot 等）の指摘対応をチャットや Slack `@mention` で
逐次ユーザーに報告し、ユーザーをレビューの門番にしてしまう（Human-in-the-loop アンチパターン）。

**根本原因**: 指摘対応は境界内（自律実行）の作業なのに、進捗を逐次共有すべきと誤解している。

**対策**: 指摘対応の記録は **PR スレッド返信・Resolve・Issue コメントのみ**。チャット逐次報告・
Slack `@mention`・完了報告アウトカムへのレビュー対応混入は禁止。例外は A-1〜A-6
（サーキットブレーカー発動・ファクト致命的 NG 等）のみ。完了報告の `--outcome` は
「初回指示で何ができるようになったか」だけを書き、指摘件数・修正サイクルは書かない。

---

## L-109: 他セッションが対応中の PR に介入しない（アクティビティロック）（2026-06-13）

**パターン**: 共通プリフライト（`check_pending_pr_reviews.py`）で全オープン PR を見るため、
別セッションが作成・対応中の PR に催促・指摘対応・問題なし判定・マージ・subscribe で
重複参入してしまう（レンダリング等の二重実行事故）。

**根本原因**: `status:in-progress` の論理ロック（CP-4 レイヤー 2）は PR レビューフェーズには効かない。

**対策**: `check_pending_pr_reviews.py` が各 PR の人間側最終アクティビティを `last_activity_min`
として算出し、**直近 10 分以内に活動がある PR を `active_session: true` として
`--actionable-only` から除外** する。出力に現れない PR は別セッションが現役対応中
（`--include-active` での強制取得も禁止）。自分が作成した PR の監視は `--json` + PR 番号
フィルタで従来どおり行う。詳細は `session-concurrency-rules.md` レイヤー 5。

---

## L-120: 高頻度で自動更新される git 追跡テレメトリを feature の WIP 自動コミットに相乗りさせない（2026-06-27）

**パターン**: 月次コスト集計（`content/analytics/cost_monthly/`）を Stop hook の `--flush` が
毎セッション書き換え、直後の WIP 自動コミット `git add -A` がそれを作業中の feature ブランチへ
無差別にステージ。結果、全 feature PR に無関係な cost churn が混入し、レビューセッションが
正しく「無関係 churn」と判定して破棄しようとする不健全なループに陥った（実例: PR #101 が
本来 3 ファイルなのに cost_monthly 25 行が混入）。

**根本原因**: 「高頻度で自動更新される git 追跡ファイル（テレメトリ）」と「feature ブランチ上の
無差別 `git add -A` 自動コミット」が構造的に両立しない。永続化（追跡）と churn 隔離（feature
差分を汚さない）を分離する仕組みが無かった。

**対策**（#106 で実装 → #242 で永続化レーンを刷新）:
- Stop hook の WIP `git add -A` から `content/analytics/cost_monthly/` を **pathspec 除外**
  （`git add -A -- . ':(exclude)content/analytics/cost_monthly/'`）。
- **#242 以降**: cost_monthly は gitignore 対象（main では追跡しない）。永続化は
  `tools/commit_cost_telemetry.py` が **テレメトリ専用データブランチ `telemetry/cost-data` へ
  1 日 1 回 plain git push** で行う（gh 非依存・PR レーンは廃止。旧「1 日 1 回の専用 PR」は
  クラウドの gh 403 で機能しなかった）。`chore/cost-telemetry-*` PR はもう作られない。
- `tools/self_review_check.py` が「feature 差分に cost_monthly が追加/変更として現れたら
  回帰」と Warning する。

**判定基準**: hook やスケジュールが「自動で書き換える追跡ファイル」を作るとき、その commit 経路が
feature ブランチに乗らないか（専用ブランチ／専用 PR に隔離されているか）を必ず確認する。

---

## L-118: 局面限定の「マージするな」口頭指示を恒久ポリシーに昇格させてマージ前で止まる（2026-06-26）

**パターン**: セッション中盤（デバッグ・調査など不安定な局面）で受けた一時的な口頭指示
「ストップしたら自動マージしないで」「いったん止めて」を、**その局面が終わった後の通常の PR フローにまで持ち越し**、
Layer 0 + Layer 1 を通過してマージ可能になった PR を「マージ判断待ち」で止めてしまう。
これは L-103（PR を出さず止まる）の姉妹形態で、**PR は出してレビューも済んだのにマージ前で止まる** CP-6 中核違反。

**根本原因**: 一時的・局面限定の口頭指示（session-scoped）と、恒久ポリシー（`CLAUDE.md`「PR 作成の完全自律化」・
auto-merge 既定）の **相互作用ルールが無く**、曖昧なまま最も保守的な「止まり続ける」に倒した。
チャット履歴は圧縮で揮発するが恒久ルール（CLAUDE.md・`.claude/rules/`）はディスクから再読込されるため、
CLAUDE.md/ルールに書かれていない口頭指示は **その局面が終われば失効** するのが正しい解釈。

**対策（判定基準）**:
- 「マージするな」「止めて」等の口頭指示は **発話された局面（デバッグ・中途状態・特定 PR の保留）に限定** して解釈する。恒久ポリシーの上書きとは見なさない。
- ユーザーがその後「進めて」「完遂して」等で **フロー継続を再承認** したら、auto-merge を含む完全自律フローを最後まで走らせる（マージ前で再び止まらない）。
- PR のマージ保留を恒久化したいなら、ユーザーが **現在の・明示の** 保留指示を出しているか、PR に保留ラベルがある場合のみ。それ以外は **Layer 0 + Layer 1 通過 = 自律マージが既定の終端状態**。
- 迷ったら「マージ判断待ち」で止めるのではなく、`pr-review-flow-summary.md` の自律マージへ進む（PR 作成・マージは A-1〜A-6 の既約境界外に **含まれない**＝確認不要）。

---

## L-119: 組み込み `code-review` スキルは `disable-model-invocation` により Claude の自律起動不可（2026-07-21）

**パターン**: 自律セッションで Layer 1 セルフレビューを実行しようと `Skill(code-review)` を呼ぶと
`Skill code-review cannot be used with Skill tool due to disable-model-invocation` で失敗する（v2.1.216 実機確認）。
同じ検証で `Skill(security-review)` は問題なく起動できたため、`code-review` **個別** にモデル自律起動が
禁止されていると判明（一時的な不具合ではなく Anthropic 側の意図的な仕様変更）。

**根本原因**: `disable-model-invocation` は Claude Code 公式の skill frontmatter フィールドで、
`true` にすると Claude（Skill ツール経由の自律起動）を禁止し、**ユーザーが対話セッションで
スラッシュコマンドを手打ちしたときだけ** 起動できる（deploy・publish 等の副作用/不可逆操作を
「テストが通ったから Claude が勝手に決める」のを防ぐ設計）。Anthropic が組み込み `code-review` に
このフィールドを付与したため、Layer 1「Claude 自身が `/code-review` を必ず実行する」前提が崩れた。

**対策（恒久・#280）**: **同名 project スキルで bundled をオーバーライドする**。公式仕様
（skills ドキュメント「A skill at any of these levels also overrides a bundled skill with the same name.
For example, a `code-review` skill in your project's `.claude/skills/` replaces the bundled `/code-review`」）
により、`.claude/skills/code-review/SKILL.md`（自前実装・`disable-model-invocation` なし）を置くと
対話（`/code-review` 手打ち）・自律（`Skill(code-review)`）の両方から起動できる。Layer 1 の標準実行手段は
この自前スキル（SSOT: `docs/rules/ai-reviewer-strategy.md`）。暫定対応期（#275）に使った
`self-reviewer` Step 2 のサブエージェント直接レビューは、自前スキルの解決が bundled 側に倒れて
自律起動エラーが再発した場合のフォールバックとして残す。
`disable-model-invocation` が付与された他の組み込みスキルを自律起動しようとして同種のエラーに
遭遇したら、まずこのフィールドの有無を疑い、恒久利用したい場合は同名 project スキルでの置換を検討する
（対応: #275 → #280）。

---

## L-125: PR インラインレビュー投稿で必ず踏む GitHub API の地雷 4 件（2026-08-11・#461）

**パターン**: Layer 1 セルフレビューの指摘を PR の行単位インラインコメントとして残す実装で、
以下 4 つは仕様上ほぼ確実に踏む。SKILL.md の手順どおりに回避する
（実装 SSOT: `.claude/skills/code-review/SKILL.md` Step 3-A）。

| # | 地雷 | 症状 | 回避策 |
|---|------|------|--------|
| 1 | 指摘行が diff ハンク外 | `add_comment_to_pending_review` が 422（`line must be part of the diff` 相当） | `get_diff` のハンク表で事前判定 → 外れていれば `subjectType="FILE"` に切替（本文に元の `file:line` を明記）。事後の 422 も 1 回だけ FILE で再投稿 |
| 2 | pending review の二重作成 | 前セッションが `submit_pending` 前に中断していると `create` が失敗（pending は 1 ユーザー 1 PR に 1 件） | 投稿前に `get_reviews` で自分の `state="PENDING"` を検出し `delete_pending` で破棄してから作り直す |
| 3 | 自己 PR への `APPROVE` | PR 著者は自分の PR を承認できず必ず失敗する | `event` は常に `COMMENT`。`REQUEST_CHANGES` も dismiss/更新の method が無く自分で解除できないため使わない |
| 4 | submit 済み review の body 編集不可 | 「あとでサマリーに追記する」設計が成立しない | サマリーは投稿時に確定させ、再レビューは新しいレビューとして投稿する |

**あわせて禁止**: 既存コメントの `file:line` 照合による重複投稿スキップ。修正コミットで行番号がシフトするため、
同じ行に生まれた **別の新規欠陥を「既出」と誤判定して握りつぶす**（L-077 の沈黙禁止と自己矛盾する）。
重複対策は「pending 破棄」と「同一ラウンド内のバッチ dedup」に限定する。
また、失敗した指摘の集約記録に `update_pull_request(body=...)` を使わない（全文置換で PR 説明文を破壊する）。
`add_issue_comment` へ 1 回だけまとめて投稿する。

---

## L-136: 並列観点別ファインダーが独立に同一 CRITICAL を指摘したら根拠が強い（2026-08-24・#630）

**背景**: `SP_TITLE_PATTERNS` のパターン 3（`^feat:\s*SP-(\d+)\b`）に、Python の `\b` が Unicode
`\w` 判定に従うため「数字 → 日本語」の境界で不成立になる欠陥があった。観点別に完全独立起動した
5 体のサブエージェントのうち **2 体（正確性・テスト検証の 2 観点が独立に、正確性は CRITICAL）が
同一箇所を指摘** し、いずれも実際にコードを実行して再現確認していた。

**判定基準**: 事前文脈を共有しない複数の観点別ファインダーが独立に同一の指摘へ収束したら、
反証（Step 2）を待たずとも実害の確度が高いと判断してよい（本ケースでは反証確認の前に自分で
再実行して即再現し、そのまま修正に進んだ）。単一ファインダーの指摘より優先度を上げる。

**あわせて確認した事故**: L-125 地雷 1（ハンク外 422）への対処中、実際には成功していた投稿
（`add_comment_to_pending_review` の成否は結果本文で個別に確認する）を「失敗した」と誤認し、
同じ指摘を FILE 単位で重複投稿した。**バッチで複数コメントを並列投稿したときは、成功/失敗を
呼び出し単位で個別に確認してから FILE 再投稿を判断する**（一括の成否サマリーだけで早合点しない）。

---

## L-138: 修正コミット後にインラインコメントを投稿する運用は許容できる（2026-08-27・#645）

**背景**: Layer 1 セルフレビューの指摘に対し、先に修正コミットを作成 → 修正後の diff を取得
→ インラインコメント本文に指摘内容と「対応済み（コミット SHA）」を一体で書いて投稿、という
順序を採った（通常の「先に指摘投稿 → 対応 → 返信」の逆順）。

**判定**: 機能面の問題は無い（レビューコメントは投稿時点の head SHA に紐づき、修正後の行番号を
正しく指せる）。むしろ「指摘 → 対応」の往復コメントが 1 回で済み効率的。**REFUTED（却下）と
判定した指摘は、find→verify→report のフロー上そもそも報告対象外**であり、インラインコメントに
残さないのが `code-review/SKILL.md` の設計（CONFIRMED/PLAUSIBLE のみ全件インライン化）。

**対策**: この 2 点（修正後投稿の許容・REFUTED は報告対象外）は SKILL.md の既存記述から読み取れる
範囲だが、次回セッションが「先に投稿すべきでは」「却下理由も記録すべきでは」と毎回迷わないよう、
迷った場合はこのまま踏襲してよい（cf. #648 で運用基準の明文化を別途検討中）。

---

## L-141: CodeQL アラートの詳細は check-run annotations API で取れる（code-scanning API が 403 でも）（2026-08-31・PR #728）

**症状**: PR の `CodeQL` チェックが failure になり、サマリーは
`1 new alert including 1 high severity security vulnerability` としか出ない。**どのファイルの
どの行が指摘されたか** はサマリーに含まれず、`GET /repos/{owner}/{repo}/code-scanning/alerts` は
クラウド実行環境のトークンでは `403 Resource not accessible by integration` を返す
（`mcp__github__*` にも code scanning の読み取りツールは無い）。

**対処**: **check-run の annotations API は同じトークンで 200 が返る**（2026-08-31 実測）。
`mcp__github__pull_request_read`（`method="get_check_runs"`）で `CodeQL` の check run ID を取り、
次を叩けばファイル・行・列・クエリ名・メッセージが取れる（annotations を返す MCP ツールは無い。
`mcp__github__get_check_run` は `output.summary` までで、指摘箇所は含まれない）。

```bash
curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/kai-kou/gem-hunter/check-runs/{CHECK_RUN_ID}/annotations"
# → [{"path": "tools/check_prod_drift.py", "start_line": 621, ...,
#     "title": "Clear-text logging of sensitive information", "message": "..."}]
```

**やってはいけないこと**: 詳細を取れないまま「差分を読んで原因を推測 → 直して push → CI を見る」を
繰り返す（1 サイクル数分かかるうえ、A-4 のサーキットブレーカーを空振りで消費する）。**推測で直す前に
annotations を取る**。

🔴 **直叩きを一次経路と読み替えないこと**。`github-mcp-fallback-patterns.md` §1 は長らく
「`curl` 直叩きは 403 でフォールバックにならない」と記録しており、2026-08-31 の再検証で 200 へ
回帰したことを同 §1.1 と `cloud-environment.md` L-114 に反映した（#684）。**可否は 1 か月に 5 回
変わった実績がある**ため、暗記せずその場で HTTP コードを計測してから使う。直叩きが要るのは
本件のように **MCP にツールが無い読み取り** だけで、それ以外は従来どおり `mcp__github__*` が一次経路。
なお `code-scanning/*` は 2026-08-31 時点でも 403（プロキシではなく GitHub App トークンの権限不足）。

**あわせて（実例）**: このとき指摘された 3 つの source は `mask_secrets.mask_text()` が既定で読む
`CLOUDFLARE_API_TOKEN` / `GH_TOKEN` / `GITHUB_TOKEN` で、置換先に `mask_value()`（先頭・末尾 4 文字を
残す）を使っていたため、**マスクしたつもりの文字列に実値の断片が 8 文字残っていた**。
**任意テキストへのマスク（出力が Issue / PR コメント・CI ログへ転記される経路）では、置換先に実値由来の
文字列を一切使わない**。先頭・末尾を残すヒント表示が妥当なのは、運用者が自分の環境変数を確認する用途に限る。
あわせて **複数の秘匿値は長さの降順で置換する**（短い値を先に消すと、それを部分文字列に含む長い値が
分断され、長い方の断片が平文で残る）。

---

## L-142: 文字列の部分一致で真偽を決める検査は、意図した範囲より広く当たる（2026-08-31）

**パターン**: 検査ツール・フックが `"キーワード" in text` や アンカーなしの正規表現で真偽を決めると、
**そのキーワードを説明目的で言及しただけの文** や **到達不能コード内の記述** にも一致する。
Layer 1 セルフレビュー（観点「判定ロジックの適用範囲」）が毎回この欠陥を検出している。

実測（PR #732・同一 firing 内で 3 件）:

| 実装 | 反例 | 結果 | 倒れる向き |
| --- | --- | --- | --- |
| `has_agent_rules_suppressed()` が `agentRules: false` を行スキャン | `if (false) { const example = { agentRules: false } }` + 実 config には未設定 | exit 0（PASS） | 🔴 **fail-open** |
| `find_marker_lines()` が部分文字列一致 | マーカーをコードスパンで引用しただけの散文 | exit 1（NG） | fail-closed（正しい記述を書けなくする） |
| `check_parallel_safety.py:253` の `if "Sprint Goal:" not in pr_body:` | 「本 PR は `Sprint Goal:` を持たない」という説明文 | 誤って対象と判定 | fail-noisy（常時 Warning で本物が埋もれる） |

**根本原因**: 「その文字列がテキストのどこかにあるか」と「その設定が実際に効いているか」を同一視している。
前者は字句の存在、後者は **構文的スコープ**（`export default` される対象か・行頭のメタ行か）の話。

**対策**:

1. **メタ行の判定は行単位に固定する**（`re.search(r"(?:^|\n)Sprint Goal:\s*\S", body)`）。`in` を使わない
2. **設定値の判定は構文的スコープを見る**（ブレース深度を数え、実際に export されるオブジェクトの直接プロパティかを判定する）
3. **反例を 3 つ作って実際に通してみせてから** マージする（`docs/rules/sprint-development-rules.md` `SD-2` の変異テストと対。反例を self-test の回帰ケースに入れ、アンカーを外す変異で FAIL することを実測する）
4. 検査ツールを議題にする議論型レビューでは **反例作成レンズを 1 名専任で置く**（`agent-team-summary.md`）。実測では、明示指示した観点だけがこの 2 件を発見し、他 6 観点は素通りした

**倒れる向きを必ず記録する**: fail-open（素通り）なら CRITICAL 相当。fail-closed・fail-noisy でも
「正しい記述が書けなくなる」「本物の警告が埋もれる」という実害があるため放置しない。

**関連**: #244（コードブロック内の例示を実値と誤認した先行事例）/ #590（初版に毎回同じ欠陥が入る）/ #695（非スプリント PR での誤発火）

---

## L-144: Dependabot のグループ分割は、後発 PR 単体では解決できない peer 競合を作る（2026-09-01・PR #755 / #756）

**症状**: Dependabot が `npm-production` と `npm-development` の 2 グループに分けて PR を作ると、
**片方のグループの更新がもう片方の peer 制約を要求する** 組み合わせで、後発 PR の CI が
`npm ci` の `ERESOLVE` で赤くなる。実測（PR #756・head `6899b7f`）:

```
npm error Found: next@16.3.2
npm error peer next@">=15.5.24 <16 || >=16.3.3" from @opennextjs/cloudflare@1.20.4
npm error Conflicting peer dependency: next@16.3.4
```

`@opennextjs/cloudflare` 1.20.4（dev グループ・#756）が `next >= 16.3.3` を要求する一方、
`next` 16.3.2 → 16.3.3 は **production グループ（#755）** にあった。各 PR はそれぞれの
base（`main`）に対して lock を生成するため、**後発（依存する側）の PR は自分の base だけを見ている
限り解決不能** になる（依存される側の更新が `main` に入るまで直しようがない）。逆に **依存される側の
#755 は単体で CI 緑** であり、この非対称性こそが下の対策 1（先にマージする）の根拠になっている。

**やってはいけないこと**: この赤を「Dependabot の壊れた PR」とみなして close する・
`--legacy-peer-deps` / `--force` を足して通す・lock を手で書き換える。いずれも
peer 制約の実体（本当に新しい `next` が要る）を消さない。

**対策（順序が全て）**:

1. **依存される側のグループを先にマージする**（この例では production の #755）
2. 後発 PR の **ブランチを `main` で更新する**（`mcp__github__update_pull_request_branch`。
   lock は領域が離れているため通常は自動マージできる。競合したときだけ `@dependabot rebase`）
3. 更新後の head で **CI と層 2（`bash tools/run_checks.sh`）を測り直す**。
   前の head の結果を流用しない（測った対象が別のツリーになっている・L-113）

**判定のヒント**: `checks` が 10 秒前後で failure に終わっていたら、テスト失敗ではなく
依存解決（`npm ci`）の失敗を疑う。ログ末尾の `npm error Conflicting peer dependency:` が決定打。

**関連**: `D-43`（bot 自動化 PR も回収対象）/ `docs/rules/pr-review-flow-summary.md`
「セッション復帰（PR 放置検出）」。放置すると `open-pull-requests-limit` に達して
Dependabot が黙って止まるため、赤いまま寝かせない。
