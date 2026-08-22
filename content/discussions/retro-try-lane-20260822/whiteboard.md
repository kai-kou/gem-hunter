<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: type:retro-try の Issue が自走ルーティンから到達不能な構造を、レーン責務を壊さずに解消する（#377）

- 議題ID: `retro-try-lane-20260822`
- 論点: 並行調査 3 役の実測をもとに、決定木への挿入位置・レーン責務・処理能力・再発検知の機械検査を確定する。spec: tools/discussion_specs/retro_try_lane_spec.json
- 参加者: `router_designer`, `lane_boundary`, `throughput_realist`, `check_designer`, `docs_trace`
- 投稿数: 5
- 更新: 2026-08-22T14:26:17+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `docs_trace` — 主張
<sub>2026-08-22T14:24:18+09:00</sub>

# Issue #377 既存記述との整合性検証（docs_trace ラウンド 1）

## 1. 変更が必要なファイルと行番号の一覧

| ファイル:行 | 現在の記述（要約） | 案 1（新ブランチ挿入）で必要な変更 | 案 2（除外撤廃）で必要な変更 |
|---|---|---|---|
| `docs/routines/sprint-cycle-routine.md:10-14` | "開発・改善 Issue 消化・衛生・リファインメント・spec-sync を **すべて 1 本の決定木**に束ねている" | Step 5 の前に新 Step 挿入に対応。§0 の「9 ブランチから」が「10 ブランチから」に変更 | 変更なし |
| `docs/rules/improvement-lane-map.md:14-15` | 振り返りレーンの起動元は `pr-review-watcher`（`SP-n` スコープ）のみ実装済み。他パイプラインからの `retrospective` 起動は未実装 | 「未実装」の記述を削除。新ブランチが追加されたことを反映 | 変更なし（但し「（本ファイルは参照のみで実行フローは複製しない）」が有効か確認） |
| `docs/rules/improvement-lane-map.md:46-61` | 一意判定ルール 1-5。特にルール 2: `type:retro-try` は振り返りレーン、ルール 5 は `type:retro-try` を除外 | ルール順序・内容変わらず（retro-try-handler の起動元が追加されても判定ルール自体は変わらない） | ルール 2 と ルール 5 の条文から「except retro-try」を削除。全レーンが type:retro-try を扱う可能性が出現 |
| `.claude/skills/retro-try-handler/SKILL.md:24` | トリガー条件に「日次の消化スロット（プロジェクト定義）+ 週次の{親ワークフロー}（プロジェクト定義）内からの呼び出し」 | プレースホルダ `{親ワークフロー}` を「sprint-cycle-router」に置換 **（案 1 の場合）** | 置換不要。プレースホルダが残ったままでも「他パイプラインからも呼ばれる可能性」を表現できる |
| `.claude/skills/sprint-cycle-router/SKILL.md:103-114` | 決定木表（Step 1-9）と説明 | Step 5 の前に新 Step 挿入。既存 Step 5〜9 の番号を 6〜10 に繰り上げ。参照番号の全更新 | 変更なし。ただし「**`type` で絞らない**（孤児 Issue の回収）」の説明が無効化される（もし全レーンが type:retro-try を扱うなら、孤児が消える） |
| `.claude/skills/sprint-cycle-router/SKILL.md:137-152` | Step 5（改善 Issue 消化）の説明。`type:retro-try` を除外する理由を明記 | Step 6 へ移動・番号更新。理由説明は維持（重複計算の防止が相変わらず必要） | Step 5 の説明からルール 1 レーン の記述を削除。除外理由が削除される |
| `.claude/skills/sprint-cycle-router/SKILL.md:154-158` | エージング（Step 4 の飢餓防止） | Step 5 へ移動（番号更新のみ） | Step 4 そのまま |
| `.claude/skills/sprint-cycle-router/SKILL.md:160-165` | Ready の定義 | Step 6 へ移動（番号更新のみ） | Step 5 そのまま |

## 2. Step 番号の固定ピン参照 7 箇所の実確認結果

| ファイル:行 | 参照内容 | どの Step を指しているか | 案 1 での影響 | 案 2 での影響 |
|---|---|---|---|---|
| `.claude/skills/self-improvement-loop/SKILL.md:317` | "CP-3。`sprint-cycle-router` SKILL.md Step 5 と対" | Step 5（改善 Issue 消化） | 番号更新必須（Step 6 に変更） | 変更不要（Step 5 のまま） |
| `.claude/skills/pr-review-watcher/SKILL.md:188` | 「`sprint-cycle-router` Step 3 の stale 再開判定が読むマーカー」 | Step 3（stale 再開） | 変更不要（Step 3 は位置変わらず） | 変更不要 |
| `.claude/skills/pr-review-watcher/SKILL.md:220` | "Step 3（`status:in-progress` かつ open の stale Issue を再開）が拾えなくなる" | Step 3 | 変更不要 | 変更不要 |
| `docs/rules/session-concurrency-rules-detail.md:82` | "呼び出し元は `sprint-cycle-router` Step 4-1.5" | Step 4-1.5 | 番号更新必須（Step 5-1.5 に変更） | 変更不要 |
| `docs/rules/sprint-development-rules-detail.md:96` | "sprint-cycle-router スキルの Step 4-0 ハードゲート" | Step 4-0 | 番号更新必須（Step 5-0 に変更） | 変更不要 |
| `docs/02_requirements/user-story-map.md:355` | "次の firing の着手時に分割する（`sprint-cycle-router` SKILL.md §8）" | §8（失敗モード別の自己回復） | 段落位置は変わらないが内容確認が必要 | 変更不要 |
| `docs/02_requirements/user-story-map.md:658` | "着手順序は **未 Closed の最小 `SP-N`**（§5.5 の依存グラフは番号が既に体現しているため）" | Step 順序（7 つの固定参照ではなく段落参照） | 変更不要 | 変更不要 |

## 3. retro-try-handler を参照している全箇所

**計 21 箇所**（定義・description・参照・ルール整備・最適化記録）:

| ファイル:行 | 参照の性質 | 変更影響 |
|---|---|---|
| `sprint-cycle-router/SKILL.md:151` | Step 5 の説明で型:retro-try 除外の理由に言及 | 案 1: Step 6 へ移動 / 案 2: 説明削除 |
| `project-sync/SKILL.md:224` | retro-try-handler が type:retro-try を担当と明記 | 両案: 変更不要 |
| `self-improvement-loop/SKILL.md:3,37` | description / Step 説明で振り返りレーン明記 | 両案: 変更不要 |
| `self-improvement-loop/SKILL.md:298` | 消化モード実行フロー の見出し | 両案: 変更不要 |
| `workflow-health-check/reference.md:80-81` | retro-try-handler の消化ペース を監視レポート対象 | 両案: 変更不要 |
| `retro-try-handler/SKILL.md:2,24,61,191` | スキル本体（name, トリガー, ブランチ名, 完了サマリー） | 案 1: L24 のプレースホルダ `{親ワークフロー}` を「sprint-cycle-router」に置換 / 案 2: 置換不要 |
| `retrospective/SKILL.md:3,204,210,216` | description / Try Issue の対応フロー指定 / 関連スキル表 | 両案: 変更不要 |
| `retrospective/reference.md:347` | 本文で実装は retro-try-handler と明記 | 両案: 変更不要 |
| `claude-code-optimization.md:104,1222` | 最適化記録・スキル最適化履歴 | 両案: 変更不要 |
| `agent-team.md:323,328` | Haiku 推奨スキル一覧・モデル指定 | 両案: 変更不要 |
| `autonomous-operation-policy.md:43,145` | システム改善パス / Try 自動実行 | 両案: 変更不要 |
| `token-optimization-rules.md:196` | 参考ドキュメント指定 | 両案: 変更不要 |
| `improvement-lane-map.md:14,22` | 振り返りレーン定義・起動元未実装の警告 | 案 1: L14-24 の「未実装」削除 / 案 2: 変更不要 |

## 4. 矛盾を新たに作る恐れのある提案

### 案 1（新ブランチ挿入）のリスク

1. **プレースホルダ {親ワークフロー} の置換漏れ**  
   `retro-try-handler/SKILL.md:24` のプレースホルダが「sprint-cycle-router」と置換されないと、スキル実行時に曖昧さが残る（どのパイプラインから呼ばれるのか不明確）。既存の「日次の消化スロット」と「週次の」だけでは不完全

2. **改善レーン（self-improvement-loop）と重複判定の自動性喪失**  
   `sprint-cycle-router/SKILL.md:137-152` Step 5 の説明に「二重取得はしない」と明記されているが、新 Step が捷度の判定をする際に self-improvement-loop との関係が明文化されない可能性。self-improvement-loop の手順書（`.claude/skills/self-improvement-loop/SKILL.md:317`）で対応 Step を明示する必要がある（現在は「Step 5 と対」と書かれている）

3. **Step 3 再開（stale 判定 4 時間）の対象が曖昧に**  
   既存 Step 3（stale 再開）の説明（pr-review-watcher:220 等）で「Step 3が拾えなくなる」と言及されているが、新ステップ挿入後に「どの Step が拾えなくなる」のかの記述が自動で更新されない。例えば「`Closes #{}` で Issue が早期に閉じると、(新 Step 4 の対象 Issue を)拾えなくなる」といった細部の文言確認が必要

### 案 2（Step 5 の除外撤廃）のリスク

1. **「`type:retro-try` は振り返りレーン専管」の決定（Issue #160）の破壊**  
   `improvement-lane-map.md:46-61` ルール 1-5 から type:retro-try の除外を削除すると、「retro-try-handler が実装」「self-improvement-loop が消化」という明確な役割分割が曖昧になる。特にルール 2「`type:retro-try` → 振り返りレーン」が相互排他性を失い、他レーンのソート・優先順位付けに type:retro-try が混在しうる

2. **孤児 Issue 回収ロジックの前提崩壊**  
   `sprint-cycle-router/SKILL.md:137-152` Step 5 の説明「`type` で絞らない理由（孤児 Issue の回収）」は、type:retro-try が **他レーンの対象ではない** ことを前提としている。この前提が崩れると、type を問わず全件を対象に含める根拠が薄れ、「なぜ type:retro-try だけは除外から外すのか」の説明が循環参照になる

3. **Issue#160 記録ドリフト**  
   `improvement-lane-map.md:59-61` で「ルール 5 が `type:retro-try` を除外する理由（将来の変更者へ）: ルール 2（`type:retro-try` は振り返りレーンの専管）は #160 でレーン間の奪い合いを防ぐために決着した条項である」と明記されている。案 2 で除外を削除すると、この明示的な決定ログが事実と矛盾する（条項が「撤廃された」という新情報が記録されないと、次の変更者が同じ議論を繰り返す）

## 5. step 参照番号の機械更新リスト（案 1 のみ）

必ず実施が必要：

1. `self-improvement-loop/SKILL.md:317` → `Step 6` に更新
2. `session-concurrency-rules-detail.md:82` → `Step 5-1.5` に更新
3. `sprint-development-rules-detail.md:96` → `Step 5-0` に更新
4. `sprint-cycle-router/SKILL.md` 本文の段落：§3 表の Step 番号（1-9 → 1-10 へ繰り上げ）、§8 失敗モード別の自己回復表のセル内容

確認が必要（文脈確認後の判断）：

5. `user-story-map.md:355` → "§8 の分割判定" が新ブランチ挿入後も指す内容が変わるかどうか
6. `pr-review-watcher/SKILL.md:188,220` → "Step 3 の stale 再開判定" の説明文中に「Step 番号の繰り上げに伴う参照更新」が必要か確認

---

## 結論

**案 1（新ブランチ挿入）は 7 ヶ所以上の機械更新 + 1 ヶ所の プレースホルダ置換 必須**。  
**案 2（除外撤廃）は既存記述の自動性を保つが、Issue #160 の記録ドリフト対策が必須**。

### `check_designer` — 主張
<sub>2026-08-22T14:24:58+09:00</sub>

# 争点D: レーン到達性の再発検知スクリプト設計

## 0. 前提の確認（file:line）

- `tools/check_skill_references.py:1-374`: 骨格の土台。`extract_referenced_paths()`（143-160行）が行マーカー `<!-- refcheck:ignore -->`（80行）とブロックマーカー `<!-- refcheck:ignore-start/end -->`（81-82行）を実装済み。`--self-test`（270行台 `run_self_test()`）・`--json`・終了コード（0=正常/1=検出あり、333行）のパターンをそのまま踏襲する。
- `docs/rules/improvement-lane-map.md:11-15`（3レーン表）+ `:28-30`（第4レーン表）: 「主な起動」列に自然言語で起動元を書いているが、L21-24 で「振り返りレーンの起動元は現時点で `pr-review-watcher`（`SP-n` スコープ）のみ実装済み」と自ら告白している＝**表の記述は仕様であって実装の証拠にならない**。
- `.claude/skills/sprint-cycle-router/SKILL.md:103-114`: 決定木 Step 1〜9 のパイプテーブル。「委譲先スキル」列にスキル名。Step 7 は `<!-- refcheck:ignore -->` マーカー付きで `self-improvement-loop 整理モード Step G-1.5〜G-6` と書かれている（既存除外規約が既にこのファイルで使われている実例）。
- `.claude/skills/pr-review-watcher/SKILL.md:214`: `4. 続けて **`retrospective` スキルを起動** する（KPT 生成と Try の Issue 化。既存仕様のまま）。` — これが `retrospective` の実際の到達経路。決定木（sprint-cycle-router）には一切現れないが、これは断絶ではない。
- `.claude/skills/retro-try-handler/SKILL.md:24`: `- 日次の消化スロット（プロジェクト定義）+ 週次の{親ワークフロー}（プロジェクト定義）内からの呼び出し` — `{親ワークフロー}` が未置換のプレースホルダのまま。実際にこれを呼ぶルーティン・スキル本文はリポジトリ内のどこにも無い（`grep -rn "retro-try-handler" .claude/skills/*/SKILL.md docs/routines/*.md` で確認要・これが #377 の実体）。

## 1. 「到達可能」の定義

レーンスキル `S` が到達可能とは、以下の **A〜C いずれか** を満たす実装上の経路が実在すること。「D: 自然文トリガーのみ」は原則不可（理由は下記）。

| 経路 | 具体的な判定根拠 | 採用可否 |
|---|---|---|
| **A. 決定木からの委譲** | `sprint-cycle-router/SKILL.md` 決定木テーブル（§3, 現在L103-114）の「委譲先スキル」列にスキル名が出現 | ✅ 採用 |
| **B. 他スキルの実行手順内での明示的呼び出し** | 他の `.claude/skills/*/SKILL.md` の **「実行フロー」節（Step 見出し配下の本文）** に、バッククォート付きスキル名 `` `S` `` の近傍（同一行または直後1行以内）に起動動詞（`起動する`/`起動し`/`呼び出す`/`委譲`/`合流`/`継続`）が現れる | ✅ 採用 |
| **C. hooks 配線** | `.claude/settings.json` の hooks 定義、または `.claude/hooks/*.sh` 内でスキル起動コマンド（`claude -p` 等）に `S` の名が出現 | ✅ 採用（現状該当なしでも将来のため定義だけ持つ） |
| **D. 自然文トリガーのみ**（frontmatter `description` の「〜して」「/S」表記だけ） | improvement-lane-map.md L17-19 が「単発オペレーション」として明示的にレーン外認定した4スキル（`project-manager`/`waiting-user-handler`/`skill-audit`/`audit-runner`）**に限り** 到達可能とみなす。レーン表（§1/§1.1）に載る6スキル（`self-improvement-loop`/`retrospective`/`retro-try-handler`/`workflow-health-check`/`project-sync`/`sprint-cycle-router`）には適用しない | ⚠️ 限定採用 |

**Bを「表の記述」ではなく「実行手順内の文」に限定する理由**: `improvement-lane-map.md` の「主な起動」列は自然言語の仕様記述であり、L21-24 自身が「表に書いてあるが実装されていない」ケースを認めている。表の文言を到達性の証拠に使うと、#377 のような「書いてあるだけで呼ばれていない」断絶を **見逃す**（偽陰性)。逆に `retro-try-handler/SKILL.md:24` の `{親ワークフロー}` はプレースホルダであり具体的スキル名を含まないため、B の正規表現には最初からマッチしない＝これも正しく「未到達」判定される。

## 2. 検査対象の抽出方法

### 2.1 レーンスキル一覧の取得（チェック対象そのもの）
`improvement-lane-map.md` §1（3レーン表, 現L11-15）+ §1.1（第4レーン表, 現L28-30）の「スキル」列からバッククォート内のスキル名を正規表現 `` `([a-z][a-z0-9-]+)`(?:（|$|\s) `` で抽出する。`self-improvement-loop（発見 / 整理 / 消化の3モード）` のような括弧注記・`retrospective` → `retro-try-handler` のような `→` 連結は `→` で分割してから個別に正規表現を当てる（1セルに複数スキル名が入る行がある）。

**除外**（Bの理由と同じ判定軸を使う）: L17-19 の「単発オペレーション」列挙4スキルは D 経路で到達可能とみなし、チェック対象リストから最初から除く（表の一部だが自然文起動のみを公式に許容された宣言なので、A/B/C 不在を FAIL にしない）。

### 2.2 決定木テーブルのパース（経路A）
`sprint-cycle-router/SKILL.md` の `## §3 決定木` 見出し以降、最初のパイプテーブルを対象に、ヘッダー行から「委譲先スキル」列のインデックスを特定してから各データ行を読む。

前処理の注意点:
- **`→` 連結**: `` `workflow-health-check` 軽量版 → `project-sync` `` のように1セルに複数スキルが入る。`→` で分割し両方を委譲先として登録する。
- **日本語補足**: `` `claude-code-spec-sync` Step1 ``・`` `self-improvement-loop` 消化モード `` のようにスキル名の後ろに補足語が続く。バッククォートの中身だけを取ればよい（PATH_PATTERN と同様、バッククォート境界で切る）ので影響なし。
- **`Step1` サフィックス**: 上と同じくバッククォートの外側なので抽出対象に含まれない。**逆に「同じスキルの Step 番号違いを別スキットとして二重カウントしない」ため、抽出後にスキル名文字列だけで集合化する**。
- **`tools/*.py` 委譲の除外**: `` `tools/sprint_backlog_sync.py` `` のようにスクリプト直接委譲の行がある（Step 3.5）。スキル名抽出の正規表現は `.claude/skills/` 配下に実在するディレクトリ名の集合との **積集合** を取ることで、`tools/*.py` や `docs/*.md` のバッククォート片を自動的に除外する（ホワイトリスト方式・誤って拾わない）。
- **`—`（Step 9: no-op）**: 委譲先なしの行はスキップ。

### 2.3 他スキルの実行手順内スキャン（経路B）
`.claude/skills/*/SKILL.md` 全ファイルを対象に、各行について:
1. `` `([a-z][a-z0-9-]+)` `` にマッチするスキル名候補を抽出し、2.1と同じホワイトリスト（実在スキルディレクトリ名集合）で絞る
2. その行 **または直後1行** に起動動詞パターン `(起動する|起動し|呼び出す|委譲する|合流)` が含まれるか確認
3. 両方満たせば「そのスキル名 → 呼び出し元ファイル」を到達証拠として記録

自己参照除外: ファイル `X/SKILL.md` 内で自分自身のスキル名 `X` を記述しても証拠にしない（無意味な自己ループ防止・`path.parent.name != skill_name` で弾く）。

### 2.4 hooks配線スキャン（経路C）
`.claude/settings.json` を JSON パースし、hooks の command 文字列を結合したテキストに対して 2.1 のホワイトリストと同じ照合をかける。`.claude/hooks/*.sh` も同様にテキスト grep。現状はレーンスキルへの直接 hooks 起動は無い見込みだが、将来の再発防止のため経路として定義しておく（0件でも FAIL 要因にはしない＝A/B いずれかがあれば十分）。

## 3. 除外マーカーの設計

**既存の `<!-- refcheck:ignore -->` 規約に乗せず、新しいマーカーを導入する。**

理由: `refcheck:ignore` は「この行のパス参照をリンク切れ検証しない」という **既存ツールの意味論** を持つ。本チェックは全く別の主張（「このスキルは意図的に決定木・SKILL.md 明示呼び出しの外にある」）をするため、同じマーカーを流用すると意味が混線し、`check_skill_references.py` 側の除外テストと本チェックの除外テストが同じ文字列を取り合って偽陰性を生むリスクがある（例: 誰かが `check_skill_references.py` の除外目的で置いた `<!-- refcheck:ignore -->` を本チェックが「到達性チェックの除外指定」と誤読する)。

新マーカー: **`<!-- lanecheck:natural-trigger-only -->`**

配置場所: `improvement-lane-map.md` の該当行末（例: L17-19 の単発オペレーション列挙文の行末）。あるいはレーン表に新規スキルを追加する側が、自然文起動のみで良いと判断した行に付ける。

```markdown
`project-manager`（Issue / Milestone の個別 CRUD）・`waiting-user-handler`（`status:waiting-user` のトリアージ）・
`skill-audit`（Agent Skills 資産の構造監査）・`audit-runner`（外部監査プロトコルによるセットアップ構成監査）は
上記 3 レーンのいずれにも属さない **単発オペレーション** で、本マップの対象外。<!-- lanecheck:natural-trigger-only -->
```

**マーカーが無いスキルは経路A/B/Cのいずれかが必須**（マーカーは「例外を選んだことの記録」であり、無条件の逃げ道にしない）。マーカーを付けられるのは improvement-lane-map.md の作成・更新者だけ（Bのときと同じ理由: 自己申告した「これは自然文起動でよい」という判断を可視化し、レビューで見える形にする）。

## 4. self-testケースの具体的列挙

### 4.1 純粋関数テスト（パーサの入出力・実ファイル非依存）

```python
# 決定木テーブルのパース
("→ 連結を2スキルとして拾う",
 "| 6 | ... | ... | `workflow-health-check` 軽量版 → `project-sync` |\n",
 {"workflow-health-check", "project-sync"})

("Step サフィックスがスキル名に混入しない",
 "| 1 | ... | ... | `claude-code-spec-sync` Step1 |\n",
 {"claude-code-spec-sync"})

("tools/*.py 委譲は委譲先スキル集合に含めない（ホワイトリスト方式で自動除外）",
 "| 3.5 | ... | ... | `tools/sprint_backlog_sync.py` |\n",
 set())  # ホワイトリスト（実在skillディレクトリ名）に無いので除外される

("no-op行（—）は委譲先なし",
 "| 9 | ... | ... | — |\n",
 set())

# 実行手順内スキャン（経路B）
("バッククォート名 + 同一行の起動動詞をヒットとして拾う",
 "4. 続けて `retrospective` スキルを起動する（KPT生成）。\n",
 True)  # is_reachable_via_skill_body("retrospective", text) == True

("スキル名だけでは拾わない（起動動詞が無い表内の言及）",
 "| 振り返りレーン | `retrospective` → `retro-try-handler` | ... |\n",
 False)  # 起動動詞が無いので B の証拠にならない（表記述と実装呼び出しを混同しない）

("自己参照は証拠にしない",
 # ファイル retro-try-handler/SKILL.md 内で自分自身を「起動する」と書いても無視
 self_skill="retro-try-handler",
 text="このスキル `retro-try-handler` を起動する運用は行わない。\n",
 expect=False)
```

### 4.2 統合ケース（実ファイルを読んで判定・#377修正前後で結果が変わることを固定する）

```
[FAIL-before-fix / PASS 期待は #377 修正後]
ケースF1: retro-try-handler の到達性
  - 経路A: sprint-cycle-router 決定木テーブルに `retro-try-handler` が出現しない（現状）→ A不成立
  - 経路B: 全 SKILL.md の実行手順内を走査しても `retro-try-handler` を明示的に「起動する」箇所が無い
    （retro-try-handler/SKILL.md:24 自身の `{親ワークフロー}` はプレースホルダでスキル名を含まないため
     経路Bの正規表現に最初からマッチしない）→ B不成立
  - 経路C: hooks 配線なし → C不成立
  - 除外マーカー: improvement-lane-map.md のレーン表側に `<!-- lanecheck:natural-trigger-only -->` は無い
  → **現状は UNREACHABLE と判定され、self-test はこのケースを「今は FAIL する」ことを固定する**
    （#377 の決定木修正がマージされたら、Step 5.5 等に `retro-try-handler` が追加され A が成立し PASS に変わる。
     self-test はこの1ケースを「fixture 文字列に決定木の断片を直接埋め込んだユニットテスト」として持つため、
     本体の sprint-cycle-router/SKILL.md が将来変わっても意図せず緑化しない）

[真陰性の固定 = 偽陽性防止の中核]
ケースF2: retrospective の到達性（決定木に無いが断絶ではない）
  - 経路A: sprint-cycle-router 決定木に `retrospective` は出現しない → A不成立
  - 経路B: pr-review-watcher/SKILL.md の実行手順内に
    「続けて `retrospective` スキルを起動する」という行があり、スキル名+起動動詞が同一行に成立 → B成立
  → **REACHABLE 判定。self-test はこのケースが常に PASS することを固定する**
    （このテストが無いと「決定木に無い=断絶」という誤検出をしてしまう、というレンズの主眼そのもの）

ケースF3: sprint-cycle-router 自身（決定木の主体・自己ループにならないことの確認）
  - improvement-lane-map.md §1.1 に `sprint-cycle-router` が「スプリント開発レーン」として掲載
  - 経路A: 決定木は自分自身の中に自分の名前を書かない（自己言及しない設計）→ A不成立
  - 経路B: `.claude/routines/` や `docs/routines/sprint-cycle-routine.md` からcron起動される、という記述が
    ある場合はそれを経路Bの拡張（起動元がSKILL.mdでなくrouteドキュメント）として扱うか、
    ここだけ経路Dの追加類型「cronルーティン定義からの直接起動」を新設するかは実装時に確定させる
    （本設計では「経路Dの限定4スキルに含めず、cronルーティン起動を経路Aの亜種として扱う」ことを推奨）
  → 設計未確定点として明示。self-testには両解釈のいずれかで PASS することのみを固定し、
    実装時にどちらを選んだか docs/rules/improvement-lane-map.md への追記コメントで残す
```

**F1が最重要**: これが「#377の修正前は本当にFAILし、修正後はPASSする」ことを実測で示す唯一のケース。他の争点（A/B/C/E）の決定と無関係に、このスクリプトだけは独立して先に書ける（決定木への追加方法が案1でも案2でも、追加された委譲先スキル名が経路Aまたは経路Bで検出できれば緑化する）。

## 5. スクリプト名・配置・引数・終了コード・配線

- **配置**: `tools/check_lane_reachability.py`（`check_skill_references.py` と対の命名。「参照切れ」ではなく「到達性」を見るので別スクリプトとして分離する。1ファイルに機能を混ぜると `--self-test` の責務が曖昧になるため）
- **引数**:
  - 無引数: 人間向けレポート（到達不能レーンの一覧・file:line 相当の根拠）
  - `--json`: 機械可読
  - `--self-test`: 4.1/4.2 のケースを実行
- **終了コード**: `0` = 全レーン到達可能 / `1` = 到達不能レーン検出 or self-test失敗
- **`run_checks.sh` への配線**（`tools/run_checks.sh:245-260` の実例パターンに倣う）:
  ```bash
  # レーン到達性 self-test（#377 再発防止）。本判定（引数なし実行）は
  # improvement-lane-map.md / sprint-cycle-router の決定木という「文書の現在の記述」に依存し、
  # 意図的な将来のレーン再設計時にも赤くなりうるため、self-test だけを配線する
  # （判定ロジック自体の退行は機械で守るが、文書更新のたびにPRを赤くしない・#288と同じ判断）。
  if [ -f "$REPO_ROOT/tools/check_lane_reachability.py" ]; then
    run_check "レーン到達性 self-test (check_lane_reachability.py --self-test)" python3 tools/check_lane_reachability.py --self-test
  else
    skip_check "レーン到達性 self-test (check_lane_reachability.py --self-test)" "スクリプトが見つかりません"
  fi
  ```
  本判定（引数なし）は `skill-audit` スキルまたは `workflow-health-check` の週次監査から呼ぶ運用を推奨（`check_skill_references.py` と同じ SSOT: `.claude/skills/skill-audit/SKILL.md` に追記）。

## 6. 他レンズへの申し送り

- 争点A（決定木への追加方法）がどちらの案になっても、本設計のF1ケースは「委譲先に `retro-try-handler` という文字列が経路A/Bいずれかで検出できるか」だけを見るため、実装非依存で書ける。ただし **決定木がStep 5.5でなくStep 5の除外撤廃（案2）を選ぶ場合**、`improvement-lane-map.md` L52 の `type:retro-try` 除外規定も書き換わるため、2.1のレーン一覧抽出パーサがその改訂後の表も正しく読めるか確認が要る（案2採用時は本設計を再レビューする）。
- 争点E（`{親ワークフロー}` プレースホルダの穴埋め）が決まれば、経路Bの正規表現がそのまま `retro-try-handler/SKILL.md:24` の新文言にマッチするかを実装時に self-test へ追加する。

### `router_designer` — 主張
<sub>2026-08-22T14:25:00+09:00</sub>

# router_designer: 決定木の設計（争点 A / B）

## ① Step 1〜5 発火頻度の見積もり（判定条件の文言引用）

| Step | 判定条件（SKILL.md 該当行の文言） | 見積もり頻度 |
|---|---|---|
| 1 | 「`lane:claude-code-spec` かつ `[CC-Sync][破壊的変更]` の open Issue が存在する」(L105) | 低（Claude Code 本体の破壊的変更検知時のみ。稀） |
| 2 | 「`check_pending_pr_reviews.py --mine --actionable-only`（相当）が非空」(L106) | 中〜高。設計側も自己申告済み — L156「Step2 が毎回埋まり続けると Step4 に永久に到達しない構造的リスクがある」と明記され、既に Step4 用のエージング（§5, L264-278）が実装されている |
| 3 | 「`status:in-progress` かつ Sprint Planning コメントがある Issue のうち `updated_at` が 4 時間超 stale」(L107) | 低〜中（前回 firing が力尽きた場合のみ） |
| 3.5 | 「Ready 判定を満たす次の `SP-n` の Issue が **無い**」(L108) | 低（バックログが補充されている限り非該当） |
| 5 | 「`status:waiting-claude` の Issue のうち、タイトルが `SP-n` 規約（`^SP-(\d+):`）に一致しないものが存在する（**`type` は問わない**）」(L110) | **ほぼ常に真** — 実測で裏取り済み（下記） |

### Step5「ほぼ常に真」の実測根拠（推測ではなく実際に `mcp__github__list_issues` を実行）

`state:OPEN` かつ `status:waiting-claude` の Issue は **合計 184 件**（`totalCount:184`）。先頭 100 件を精査したところ、`type:retro-try` を持たない（＝ Step5 の除外対象外）かつタイトルが `^SP-(\d+):` に一致しない Issue が **39 件**（#403, #402, #401, #394, #393, #392, #389, #388, #372, #371, #366, #365, #355, #354, #352, #345, #338, #336, #335, #324, #317, #313, #310, #309, #306, #287, #276, #272, #268, #267, #253, #247, #242, #238, #237, #236, #228, #222, #221）。SP-n 形式のタイトル（`SP-19:` 等）は 1 件も存在しない（#389/#388 は `feat: SP-19 ...` という接頭辞付きで正規表現に一致しない）。

→ Step5 の対象プールは**常時 2 桁の在庫を抱えている**。自走ルーティンの自律 Issue 生成（self-improvement-loop 発見モード等）が継続する限りこのプールが空になる見込みは薄い。

## ② 結論: 飢餓は起きる

**Step5 より下（現行なら Step6〜9、今回 retro-try を Step5 の直後に単純挿入した場合も同様）は、Step5 が真であり続ける限り永久に到達しない。** これは推測ではなく上記実測（39 件/184 件が Step5 の即時該当対象）で裏付けられる。「1 firing = 上から該当する最初の1ブランチだけ実行する」(L40, L100) という設計上、Step5 が真の firing では Step5.5 以降は**評価すらされない**。

## ③ 飢餓回避案（2 案）

### 案1（推奨）: Step4 と同型のエージング拡張

**書き換える行**:
- `.claude/skills/sprint-cycle-router/SKILL.md` §3 の表（L103-114）: Step5 行（L110）と Step6 行（L111）の間に新規行を追加:
  `| **5.5** | \`status:waiting-claude\` かつ \`type:retro-try\` の Ready Issue が存在する | retro-try Issue の消化 | \`retro-try-handler\` |`
- §5「飢餓防止（エージング）」(L264-278) に第 2 項として追記:
  ```
  4. Step5 と Step5.5 の飢餓防止: type:retro-try かつ status:waiting-claude の Ready Issue が
     存在し、直近の retro-try 対応時刻（直近に closed された type:retro-try Issue の
     closed_at — `mcp__github__list_issues(state=CLOSED, labels=["type:retro-try"],
     orderBy=UPDATED_AT, direction=DESC, perPage=1)`）から X 時間以上経過していれば、
     この firing に限り Step5 の判定を後回しにして Step5.5（retro-try-handler）を実行する。
  ```
  X の具体値は throughput_realist の流入/流出計算と整合させるべき（自分のレンズでは決め切らない）。
- §10 完了定義（L365-374）に「Step5.5 のエージングが機能し starvation していない」を追加。
- §11 参照表に `retro-try-handler/SKILL.md` を Step5.5 の委譲先として追加。

**状態の永続化**: ローカルファイル禁止（`session-concurrency-rules.md`）なので、Step4 のエージング（L270-277 の「直近マージ済み SP-n PR のマージ日時」パターン）に倣い、**GitHub 側のアーティファクト**（直近 closed の `type:retro-try` Issue の `closed_at`）を単発クエリで逆算する。新規 state ファイル・新規ラベルは不要。

**固定ピン 7 箇所への影響**: **ゼロ**。Step5 の条件・番号は変更しない。Step6 以降の番号も変更しない（純粋な追加行）。`Step 3.5` が既に前例（L108, user-story-map.md:355,658 から固定参照される実在の小数点 Step）であり、`Step 5.5` も同型の追加として安全に挿入できる。

### 案2: 時間帯スロット制（Step6 衛生スロットと同型）

Step0.1 早期リターン（§2, L80-94）の e 項目として「本日まだ retro-try 枠を実行していない」を追加し、Step1 の後・Step2 の前に新規ブランチとして差し込む。

**書き換える行**: §2 (L80-94) に e 項目追加 + §3 の表に新規行（Step 1.5 等）。

**問題点**: Step2 より優先させると、L106「新規スプリント着手より優先。中途 PR を放置して新規に手を広げない」という既存原則（CP-4）と衝突する。Step2 より後段に置くなら結局「他の分岐が今回すでに真かどうか」の判定が絡み、実質エージングと同じ複雑さになる。

## ④ 推奨と理由

**案1（エージング拡張）を推奨**。理由:
1. 差分が最小（§5 に 1 ブロック追加 + §3 に 1 行追加のみ）で、Step4 エージングという**既存の設計パターンをそのまま再利用**できる（設計の一貫性）。
2. Step2 の「PR 継続を最優先する」原則（CP-4）と衝突しない（案2 は衝突する）。
3. 状態永続化に新規ファイル・新規ラベルが不要（GitHub の既存アーティファクトの単発クエリで完結）。
4. 固定ピン参照 7 箇所への影響がゼロで、`Step 3.5` という実在前例に倣った安全な数値挿入。

**残る課題（自分のレンズ外・他役に委ねる）**: エージング閾値 X の具体値は throughput_realist の流入(37.7件/日)/流出(5件/起動 × 発火確率)計算と整合させる必要がある。また `retro-try-handler/SKILL.md:24` の未置換プレースホルダ `{親ワークフロー}` は、本設計採用時は「`sprint-cycle-router` の Step5.5」に置換すべき（lane_boundary / docs_trace 領域）。

### `lane_boundary` — 主張
<sub>2026-08-22T14:25:20+09:00</sub>

# レーン責務境界（争点 A の案 2 / 争点 C）— lane_boundary 分析

## 1. #160 の決定は今も妥当か

`docs/rules/improvement-lane-map.md:52` のルール 2（`type:retro-try` → 振り返りレーン専管・改善 Issue レーンは扱わない）は **今も機能的に妥当** と判断する。「58% が二重ラベル」という実測は事実だが、その原因を実際に追うと **レーン分割の失敗ではなく、ラベルの直交軸が同じ `type:` prefix を共有しているだけ**、かつ **別レイヤーの実装漏れ（後述 §2）** であることが分かった。

### 二重ラベルの発生源を特定した

`open_issues.json`（113 件の `type:retro-try`）を `type:` 系ラベルの組み合わせで集計:

```
66 (type:improvement, type:retro-try)
31 (type:retro-try,)                 ← 単独
 9 (type:bug, type:retro-try)
 7 (type:docs, type:retro-try)
```

`type:improvement` だけでなく `type:bug`（9 件）`type:docs`（7 件）とも同型に共起している。「type:improvement を持つ Issue は改善レーンにも属する」という主張が成立するなら、「type:bug を持つ Issue はバグレーンにも属する」も成立しなければならないが、そんなレーンは存在しない。つまり `type:*` は **2 つの直交する軸**（① 内容分類＝improvement/bug/docs、② 由来＝retro-try）を 1 つの prefix に同居させているだけで、**dual-label は「両方のレーンが処理すべき」を意味しない**。

これは起票元（`retrospective/reference.md:242-249`）を読むと裏が取れる。新規 Try Issue のラベル配列はハードコードで:

```python
labels = [
  "type:retro-try",                       # ← フィルタ用の主キー（必須）
  "type:improvement",
  ...
]
```
（`retrospective/reference.md:245-247`）

コメント自身が `type:retro-try` を「フィルタ用の主キー」と明記しており、`type:improvement` はルーティングキーではなく **内容カテゴリの固定付与**（Try の性質上ほぼ全件が「改善」に分類されるため常時付く）。実際、title prefix と dual-label の相関を見ると `[Retro][...]` テンプレート由来の 10 件は 100% dual、`improvement:` に後から書き換えられた 56 件も dual、一方で `type:...:` / `fix:` / `docs:` prefix の 30 件は 0 件が dual（別の起票経路・おそらく棚卸し #385 前後の手作業/正規化）。多数派が dual なのは「テンプレートが機械的に両方貼るから」であって「内容が両属性を要求するから」ではない。

**ルール 2 自体は迷いなく機能する**: 一意判定ルールは「対象が `type:retro-try` →振り返りレーン」であり、他の `type:*` の有無を見ない。曖昧さはゼロ。

## 2. 案 1 と案 2 の比較

### 案 2（レーン統合）を採った場合に実際に壊れるもの

`type:retro-try` の除外は `improvement-lane-map.md` 1 箇所ではなく、**`self-improvement-loop/SKILL.md` 内に最低 3 箇所** 独立に埋め込まれている（実測）:

- `SKILL.md:37`「`type:retro-try` は振り返りレーンの担当。本スキルの消化モードは扱わない（奪い合い防止・#160）」
- `SKILL.md:142`（Step G-1.5 リファインメント対象抽出の除外条件）「`type:retro-try`（振り返りレーンの専管・#160 の奪い合い防止）」
- `SKILL.md:314`（消化モード実行フロー）「`type:retro-try`（振り返りレーンの担当）… を除外し、残り全件を…」
- frontmatter の `description` 冒頭にも「type:retro-try（振り返り由来の Try）は retro-try-handler … が担当する」と明記

案 2 は `improvement-lane-map.md` の書き換えだけでは終わらず、上記 4 箇所すべての除外条件を撤廃し、**さらに retro-try-handler が持つ専用ロジックを self-improvement-loop 側へ移植するか、失うかの二択**を迫られる。両者は処理の詳細度が全く別物と確認した:

| | retro-try-handler | self-improvement-loop 消化モード |
|---|---|---|
| 優先順位 | urgency ラダー（blocker→dep:blocking→quality/high→…）+ doc-only は **月曜のみ処理** という特殊規則 | priority:high→medium→なし→low の単純順 |
| 分類 | 8 カテゴリ（doc/script/validate/skill/user/tool-update/domain/dev-tool）× `reference.md` C-1〜C-7 の専用手順 | 「小〜中なら実装」という粗い工数判定のみ |
| 処理上限 | バックログ残件数に応じ動的 2〜5 件 | 固定 5 件/回 |
| model | `haiku`（安価・frontmatter 明記） | 指定なし（既定 `sonnet`。発見/整理モードは並列サブエージェント・discussion-review も抱える高コスト経路） |

統合すると (a) urgency ラダー・doc-only 月曜スキップという細かい制御を失うか、(b) それを self-improvement-loop に移植して二重実装になるかのどちらかで、**どちらも純増のリスクであって #377（到達不能の解消）には寄与しない**。さらに model 差（haiku vs sonnet 既定）はコスト面でも統合の根拠を弱める。これは `improvement-lane-map.md:78-82`「振り返り・監査/衛生は frontmatter（model/effort）と自動起動点が異なるため統合しない」という既存決定と正面から一致しており、今回の実測はこの決定を覆す根拠にならない、むしろ補強する。

### 案 1（責務維持）を採った場合に残る歪み

「二重ラベルの Issue はどちらのレーンが拾うのか」自体は歪みではない（ルール 2 で明確に retro-try が勝つ）。しかし **実装のバグとして #160 の除外が 1 箇所だけ漏れている** ことを発見した:

`tools/triage_improvements.py`（Step G-1「棚卸し」本体＝重複統合・Epic 化・priority/sp 補完のデータソース）は `--label type:improvement`（既定値、`triage_improvements.py:524`）で無条件フェッチし、`type:retro-try` を除外するコードが **どこにもない**（`fetch_issues`/`label_names` 全文 grep で `retro` 0 件ヒット）。

一方 `self-improvement-loop/SKILL.md` は Step G-1.5（リファインメント・142 行目）と消化モード（314 行目）では明示的に `type:retro-try` を除外しているのに、**Step G-1（棚卸し本体）だけ除外条件が実装されていない**（`SKILL.md:121`「Step G-1 のレポートは type:improvement に限定されるため本 Step では使わない」は G-1.5 の話で、G-1 自体の除外漏れには触れていない）。結果として **66 件の retro-try Issue が改善 Issue レーンの重複統合・Epic 化対象に混入している**。これは「レーン分割の設計ミス」ではなく「#160 のルール実装が 1 ツールだけ追従できていない」という **実装バグ**であり、案 1 のもとで直せば消える歪みである。

## 3. 結論

**案 1（責務維持）を推す。** #160 の決定・`improvement-lane-map.md` の一意判定ルール（L46-61）は書き換え不要。理由: (1) dual-label は直交軸の共有によるラベル表記の問題であって、ルーティングは既に一意（曖昧さ実測ゼロ）。(2) 案 2 は self-improvement-loop 内 4 箇所の除外条件撤廃＋retro-try-handler 専用ロジックの喪失/二重実装という実コストを生み、#377（到達不能の解消）には寄与しない。(3) 案 1 で唯一実在した歪みは lane 設計ではなくツールのバグで、狭い修正で閉じる。

### 移行手順（案 1 採用・バグ修正のみ）

1. `docs/rules/improvement-lane-map.md`: **変更不要**（L46-61 のルール 2 はそのまま維持）。
2. `tools/triage_improvements.py`: `fetch_issues()`（154-169 行目付近）の返り値、または呼び出し側で `type:retro-try` を含む Issue を除外する 1 行フィルタを追加する（Step G-1.5 が既に実装している除外条件と同じロジックを Step G-1 のデータソースにも揃える）。
3. `.claude/skills/self-improvement-loop/SKILL.md`: Step G-1 の説明（99-121 行目）に「`triage_improvements.py` は `type:retro-try` を除外済み（ツール側対応）」の 1 行注記を足し、G-1 と G-1.5 の除外条件が揃っていることを明記する。
4. 争点 A（決定木への挿入）は router_designer の設計に従い、`sprint-cycle-router` 側に retro-try-handler への到達経路を追加する（レーン境界の変更は不要、起動経路の欠落を埋めるだけ）。

以上、post 済み。

### `throughput_realist` — 主張
<sub>2026-08-22T14:25:59+09:00</sub>

# throughput_realist: 争点 B — 経路開通だけで滞留は解消しないと数値で示す

## 0. 使用データ

- `all_open_issues.json`（scratchpad・open Issue 188 件中 `type:retro-try` を抽出）
- `.claude/skills/retro-try-handler/SKILL.md` L115-126（バッチ上限テーブル）
- `.claude/skills/retro-try-handler/reference.md` L178-193（PR バンドル条件・D 節）
- `docs/routines/sprint-cycle-routine.md` L16-24（cron `0 0/2 * * *`）
- `.claude/skills/sprint-cycle-router/SKILL.md` L106-109（Step 2 = 自 PR 回収が Step 5 系より優先）
- Issue #393 本文（`all_open_issues.json` 内）

## 1. 流入の実測（3 分足りず・日ごと集計。単純平均ではなくバースト性を見る）

```python
retro = [i for i in data if 'type:retro-try' in i['labels']]
len(retro) == 113
```

| 日付（UTC） | 起票件数 |
|---|---|
| 2026-08-19 | 24 |
| 2026-08-20 | 49 |
| 2026-08-21 | 20 |
| 2026-08-22（04:51 UTC 時点・部分日） | 20 |
| **合計** | **113** |

- 完全 3 日（19〜21）平均 = `(24+49+20)/3 = 31.0 件/日`
- brief の `113/3 = 37.7 件/日` は「起票期間の日数」で単純割りした値であり、実測の日次分布はそれより**バースト性が強い**（08-20 に単日 49 件＝ #385 / PR #399 の棚卸しセッションと符合）
- 08-22 は **04:51 UTC までの約 4h51m で 20 件**（同ペースを 24h に引き伸ばすと ≈99 件/日相当）だが、これは特定セッション（棚卸し/監査系）による突発生成である可能性が高く、定常レートの根拠にはしない。**「定常的に 30〜38 件/日流れ続ける」という前提と「間欠的に数十件のバーストが来る」という前提のどちらでも、以下の結論（経路開通だけでは不十分）は変わらない**ことを先に明記する。
- SP 合計 244（113 件・平均 2.16 SP/件）
- `type:improvement` との二重ラベル: **66/113 件（58.4%）**

## 2. 流出の上限（n = retro-try ブランチを引ける回数/日）

- バックログ 113 件 ≥ 30 件 → バッチ上限は **5 件/起動**（SKILL.md L122）
- cron: 2 時間おき = **12 firing/日**、1 firing = 1 ブランチのみ実行

| ケース | n（1日に retro-try を引く回数） | 出力上限（issue/日） |
|---|---|---|
| 保守的 | n=1 | 5 |
| 中間 | n=3 | 15 |
| 非現実的上限（毎 firing 引く） | n=12 | 60 |

n=12 は「決定木の下位ブランチが毎回選ばれる」＝上位 8 ブランチ（spec-sync/PR回収/stale再開/新規着手/改善消化/衛生/週次リファインメント等）が**常に偽**という状態であり、設計上あり得ない（起こるなら他ブランチが機能不全ということ）。上限として計算するが実現可能性は router_designer の飢餓分析に従う。

## 3. 収支（定常状態でバックログは増えるか減るか）

流入を 2 通り（実測 3 日平均 31/日、brief 値 37.7/日）で評価:

| n | 出力/日 | 純増減（流入31 基準） | 純増減（流入37.7 基準） | 判定 |
|---|---|---|---|---|
| 1 | 5 | **+26/日** | **+32.7/日** | 増加（滞留悪化） |
| 3 | 15 | **+16/日** | **+22.7/日** | 増加（滞留悪化） |
| 12（非現実的） | 60 | **-29/日** | **-22.3/日** | 減少 |

**n=1 と n=3（現実的なレンジ）ではどちらも流入が流出を上回り、バックログは減らずむしろ増え続ける。** 経路を開通させても、113 件の現在バックログはおろか、日々の新規流入すら吸収できない。

n=12（非現実的上限）だけが黒字化する。既存 113 件を新規流入ゼロと仮定して純消化する場合の所要日数:

| n | 出力/日 | 113件を消化する日数（新規流入ゼロ想定） |
|---|---|---|
| 1 | 5 | 22.6 日（約 3 週間） |
| 3 | 15 | 7.5 日（約 1 週間） |
| 12 | 60 | 1.9 日 |

実際には新規流入が止まらない（§1）ため、n=1/n=3 では**この表の日数はいつまで経っても到達しない**（漸近的に無限大）。

## 4. PR 作成のボトルネック（相互作用）

`retro-try-handler` SKILL.md Step 5 は **PR 作成 → Layer1 セルフレビュー → 指摘対応 → 自動マージまでを同一セッション内で完結**させる設計（外部 AI レビュアー廃止・自己完結レビュー）。したがって「正常系」では Step 2（自 PR 回収）への持ち越しは発生しない。

ただし 2 つの追加リスクがあり、n=3〜5 のケースではどちらも無視できない:

1. **バンドル上限による PR 分割**: `reference.md` D 節（L184-187）— バンドル可能なのは「同一カテゴリ・全て small・ファイル競合なし・2〜3 件」のみ。5 件のバッチは 8 カテゴリ（doc/script/validate/skill/user/tool-update/domain/dev-tool）に分散しやすく、**最良ケースでも 5 件 → 最低 2 PR**（3+2）、カテゴリが割れれば **4〜5 PR** になり得る。1 firing 内で複数 PR の作成・自己レビュー・マージを直列にこなす必要があり、セッション予算（`session-safety-rules.md` の 1 ターン 8 ツール制限・複数ターンには分散できるが firing 自体は 1 本）を圧迫する。
2. **large 見積もりは閉じない**: SKILL.md Step 2（L126）「`large` は実装計画コメントのみ投稿」— これは `status:waiting-claude` のまま残る（クローズされない）。つまり **「5 件処理」の一部は実際にはバックログを 1 件も減らさない**。§3 の「出力上限 5/起動」は**上限値**であり、実効値はこれより低い。small/medium 比率が不明なため定量補正はしないが、§3 の黒字化ライン（n=12）はさらに厳しくなる方向にしか動かない。

→ 結論: 正常系では PR レビュー自体は追加 firing を要さないが、**バンドル分割による同一 firing 内の作業量増大**と **large 案件の非クローズ**の 2 点により、§3 の「出力上限」は楽観値であり、実際の消化ペースはさらに悪化する。

## 5. 経路開通だけで #377 の完了条件を満たすか

**満たさない。critical として明記すべき。**

- n=1/3（現実的レンジ）ではどちらも流入超過で滞留悪化。n=12（黒字化ライン）は決定木の設計上到達不可能な非現実値。
- 「type:retro-try が決定木から到達可能になる」ことと「バックログが解消に向かう」ことは別の命題。#377 の議題名は前者（到達不能構造の解消）だが、飼い主が最終的に期待するのは後者（滞留の解消）である可能性が高く、経路開通のみでは後者を満たさない。
- **verdict の `critical` に「経路開通後も流入超過が続く限りバックログは減らない（n=1/3 で純増 +16〜+33/日）」を明記し、解決策（流入抑制の追加設計）を持たないまま「開通したので解決」と書かない**（spec の synthesizer instruction と一致）。

## 6. 流入を絞る案と #393 の関係

Issue #393（`improvement: レトロスペクティブの Try 起票時に既存 Issue の重複検索を必須にする`）は、**「同一問題が日を跨いで複数回起票される」重複を防ぐ**施策であり、`retrospective` スキルの Try 起票手順に `mcp__github__search_issues` での事前検索を必須ステップとして入れる。

- **#393 で防げるのは「文字通りの重複」のみ**。今回の 113 件バーストの主因が重複か否かは本データからは断定できない（重複検出には Issue 本文の意味的近似が要り、本分析では計算していない）。
- ただし **二重ラベル 58.4%**（`type:retro-try` かつ `type:improvement`）という事実は、少なくとも半数超が「本来どちらのレーンの管轄か曖昧な指摘」であることを示唆し、Try 起票の閾値（何を Try 化する価値があると判定するか）自体が緩い可能性を補強する。#393 は重複の後始末であり、**Try 化の閾値そのものを厳格化する施策ではない**。
- したがって #393 がマージされても、§3 の流入 31〜38/日が半分以下（n=3 の黒字化ラインである 15/日未満）まで下がる保証はない。**#393 は必要条件だが十分条件ではない。**
- 追加で要る施策（このスプリントのスコープ外・別 Issue 案件）: ① 1 回のレトロスペクティブ実行あたりの Try 起票数に上限を設ける（例: 上位 N 件のみ Issue 化、残りは KPT レポートのみに留める） ② `priority:low` かつ影響範囲が単一ファイルの Try は Issue 化せず lessons や `docs/rules/` への直接追記で完結させる（Issue 化のコストそのものを避ける）。

## 7. 流出を増やす案（制約内）

バッチ上限引き上げ・複数ブランチ同時実行・追加 cron はいずれも brief の制約で禁止。制約内で流出を増やせる余地:

- **決定木内での retro-try 優先度の引き上げ**（router_designer の飢餓対策と表裏）: n を 1→3 に上げるだけで出力は 5→15/日（3 倍）になるが、§3 の通りそれでも流入に追いつかない。優先度を上げるほど Step1〜4（spec-sync・PR回収・stale再開・新規スプリント）を圧迫するトレードオフが生じる（lane_boundary / router_designer の判断領域）。
- **バンドル条件の緩和**（同一カテゴリ縛りを緩める・小粒 medium もバンドル対象に含める）は §4 の PR 分割問題を緩和し、1 firing あたりの実効クローズ数を押し上げる可能性があるが、これは「制約内での実装変更」であり検討対象になり得る（バッチ上限そのものは変えない）。

## 8. このスプリントで実施すべきもの / 別 Issue に送るべきもの

| 区分 | 内容 |
|---|---|
| **このスプリントで実施**（#377 のスコープ） | 決定木への retro-try 経路挿入（争点 A/B の設計）。ただし挿入と同時に、n=1/3 では流入超過が解消しないことを PR 本文・Issue コメントに明記し、「解決」ではなく「経路の開通」であることを言明する |
| **別 Issue へ送る（このスプリントでは実施しない）** | ① Try 起票数の上限設計（レトロ 1 回あたりの Issue 化上限・優先度フィルタ）② `type:retro-try`/`type:improvement` 二重ラベル 58.4% の扱い（lane_boundary の争点 C と連動、統合すれば実質的な流出経路が 2 倍になる可能性があるため優先度高） ③ バンドル条件緩和による 1 firing あたりの実効クローズ数改善 |

## まとめ（1 行）

**n=1/3（現実的レンジ）では流入 31〜38 件/日 > 流出 5〜15 件/日で純増、経路開通だけではバックログは解消しない。黒字化するのは決定木の設計上あり得ない n=12 のみ。critical として残し、流入抑制（#393 は必要条件止まり）と流出増加（優先度引き上げ・バンドル緩和）を別 Issue で追う。**
