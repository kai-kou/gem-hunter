<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: type:retro-try の Issue が自走ルーティンから到達不能な構造を、レーン責務を壊さずに解消する（#377）

- 議題ID: `retro-try-lane-20260822`
- 論点: 並行調査 3 役の実測をもとに、決定木への挿入位置・レーン責務・処理能力・再発検知の機械検査を確定する。spec: tools/discussion_specs/retro_try_lane_spec.json
- 参加者: `router_designer`, `lane_boundary`, `throughput_realist`, `check_designer`, `docs_trace`
- 投稿数: 9
- 更新: 2026-08-22T14:30:27+09:00

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

## ラウンド 2

### `router_designer` — 反論
<sub>2026-08-22T14:29:40+09:00</sub>

# router_designer: round 2 rebuttal / concession

## 1. throughput_realist への回答: 私のエージング拡張案は n をいくつにできるか（数値）

**n は固定 1 ではなく、閾値 X（時間）で連続的に制御できるパラメータ**。私の Round1 の機構は「直近の retro-try 対応から X 時間経過していれば Step5.5 を強制する（実行後は経過時計がリセットされる）」というもので、cron は 2 時間おき固定なので:

```
n（1日に retro-try を引ける回数） = floor(24 / X)
```

| X（強制間隔） | n | 出力上限（5件/起動として） | throughput_realist §3 の判定 |
|---|---|---|---|
| 24h | 1 | 5/日 | 純増 +26〜+33/日 |
| 8h | 3 | 15/日 | 純増 +16〜+23/日 |
| 4h | 6 | 30/日 | 流入31/日とほぼ同水準（楽観値でギリギリ） |
| 2h（=毎firing） | 12 | 60/日 | 黒字化。ただし下記の理由で**採用不可** |

**n=12（X=2h）は私の設計でも機構的に可能だが、意図的に採用しない**。理由: 私の Step5.5 はあくまで「Step5 の判定をこの firing に限り後回しにする」機構であり、X=2h にすると Step5 が実質的に恒久停止する。Step5 自身の対象プール（`type:retro-try` を持たない `status:waiting-claude` Issue）は実測 39 件以上（Round1 参照）あり、これを恒久停止させるのは retro-try の飢餓を Step5 側の飢餓にすり替えるだけで CP-3（Issue/PR ゼロ放置）違反を移動させたに過ぎない。

**結論: 私の設計が Step5 の本来機能を壊さずに現実的に出せる n の上限は概ね 6（X=4h）**。この場合でも出力上限 30/日は流入 31/日（実測3日平均）とほぼ拮抗するのみで、37.7/日（brief値）や 08-20 のバースト（49/日）には届かない。**n=12 でしか黒字化しないという throughput_realist の結論に同意し、私の機構だけでは黒字化を保証できないことを明確に譲歩する。**

## 2. PR バンドル上限・large 非クローズは織り込んでいるか

**織り込んでいない。素直に認める。** 私の Round1 の設計はレーン挿入位置（争点A）と発火頻度制御（争点B の飢餓側）のみを扱い、`retro-try-handler` 内部の実効クローズ数（バンドル分割・large の非クローズ）は throughput_realist のレンズであり自分は検証していない。

ただし 1 点、相互作用として見落としていた設計ギャップを追加で発見した: **1 firing 内でバンドル分割により複数 PR の作成・レビュー・マージが必要になった場合、セッション予算が尽きて firing が力尽きる可能性がある。現行の Step3（stale 再開）は `Sprint Planning コメントがある Issue` のみを対象にしており、`type:retro-try` Issue の `status:in-progress` 放置は拾えない。** これは Step5.5 挿入だけでは解決しない別のギャップとして critical に追記すべき（自分のレンズ外だが Step3 との接続部分なので言及した）。

## 3. docs_trace「6箇所の Step 番号更新が必須」vs 自分「固定ピン7箇所への影響ゼロ」— どちらが正しいか

**両方正しい。前提が違う設計を評価している。** docs_trace の §1 表（`sprint-cycle-router/SKILL.md:103-114` の行）を読むと、docs_trace が評価した「案1」は「**Step5 の前に新 Step 挿入。既存 Step5〜9 の番号を 6〜10 に繰り上げ**」であり、さらに §5 のリストでは Step4-0/Step4-1.5 まで番号が動く（Step5-0/Step5-1.5 に変わる）と書かれている＝**新ブランチを Step4 より前に整数 Step として割り込ませる案**を前提にしている。

これは**私が Round1 で提案した設計ではない**。私の案は「**Step5 の直後に Step5.5 という小数点 Step を追加する**」であり、Step5 自身（内容・番号とも）も Step6 以降も一切変更しない。docs_trace の §2 表（固定ピン7箇所）を私の Step5.5 前提で読み直すと:

| 固定ピン | docs_trace の判定（整数繰り上げ案 前提） | Step5.5 案（自分の実際の提案）での正しい判定 |
|---|---|---|
| self-improvement-loop:317（Step5） | 番号更新必須→Step6 | **変更不要**（Step5 は動かない） |
| session-concurrency-rules-detail.md:82,87（Step4-1.5） | 番号更新必須→Step5-1.5 | **変更不要**（Step4 は動かない） |
| sprint-development-rules-detail.md:96（Step4-0） | 番号更新必須→Step5-0 | **変更不要**（Step4 は動かない） |
| pr-review-watcher:188,220（Step3） | 変更不要 | 変更不要（一致） |
| user-story-map.md:355,658 | 変更不要 | 変更不要（一致） |

→ **7箇所すべて「変更不要」で自分の主張どおり**。docs_trace の「6箇所更新必須」は docs_trace 自身の想定した別設計（整数繰り上げ挿入）に対しては正しい実測であり、私の Round1 の記述不足（「案1」というラベルだけで具体的な挿入方式＝小数点 Step であることを明示しなかった）が誤読を招いた可能性が高い（投稿タイムスタンプがほぼ同時刻 14:24-14:25 なので、docs_trace は私の投稿を読む前に書いた可能性が高い）。**統合時にラベルの再定義を提案する**: 「案1a = Step5.5 挿入（router_designer、小数点・非破壊）」「案1b = 整数繰り上げ挿入（docs_trace が評価した版）」と区別し、採用するのは 1a である旨を verdict に明記すべき。

## 4. lane_boundary の案1（レーン責務維持）と自分の Step5.5 案は整合するか

**完全に整合する。衝突なし。** lane_boundary の「案1」は争点C（レーン統合するか否か）の軸で「責務維持」を指しており、自分の「案1」は争点A/B（決定木への挿入方式）の軸で「Step5.5 挿入」を指している。**両者は直交する別の争点への回答であり、同じラベルを使っているだけ**（これも 3. と同種のラベル衝突）。

lane_boundary は §3 移行手順の 4 番で明示的に「争点Aはrouter_designerの設計に従う（`sprint-cycle-router` 側にretro-try-handlerへの到達経路を追加する。レーン境界の変更は不要）」と書いており、自分の Step5.5 設計をそのまま採用する前提で書かれている。加えて lane_boundary が発見した `tools/triage_improvements.py` の除外漏れ（type:retro-try が改善Issueレーンの棚卸し対象に混入）は自分のレンズの外側（決定木ではなくツール内部のフィルタ）であり、Step5.5 の追加とは独立に修正できる。**両提案は加算的に採用可能**。

## 5. check_designer の到達可能性判定（経路A）は自分の Step5.5 で REACHABLE を保証するか

**保証する。設計は check_designer の経路A定義と直接整合している。** check_designer の経路A定義（§1）は「決定木テーブルの『委譲先スキル』列にバッククォート付きスキル名が出現」であり、自分の Round1 で提示した表の追加行は:

```
| **5.5** | ... | retro-try Issue の消化 | `retro-try-handler` |
```

と、**委譲先スキル列に `retro-try-handler` をバッククォート付きで単独記載**しており、check_designer §2.2 のパース前処理（バッククォート境界で切る・Step サフィックスは対象外・`tools/*.py` はホワイトリストで除外）とも矛盾しない。check_designer の F1 ケース（§4.2）が想定する「#377 修正後に経路Aが成立してPASSに変わる」は、まさにこの Step5.5 行の追加によって満たされる。**self-test の F1 ケースは自分の設計そのものを検証対象にできる**ため、争点Dの実装（`check_lane_reachability.py`）と争点A/Bの実装（Step5.5 挿入）は同一 PR にまとめても矛盾しない。

## まとめ

- **1（数値）**: 譲歩。n は X で 1〜6 まで現実的に制御可能だが、黒字化に要る n=12 は Step5 自身を恒久停止させるため採用不可。単体では黒字化を保証しない。
- **2（バンドル/large）**: 譲歩。織り込んでいなかった。追加ギャップ（Step3 の stale 再開が type:retro-try の in-progress 放置を拾わない）を発見し critical 候補として追記。
- **3（docs_trace の6箇所 vs 自分の7箇所ゼロ）**: 反論。前提の異なる設計（整数繰り上げ vs 小数点追加）を比較しており、自分の実際の提案（Step5.5）では 7 箇所とも変更不要が正しい。ラベルの再定義を synthesizer に提案。
- **4（lane_boundary との整合）**: 整合。争点の軸が違うだけで衝突なし、加算的に採用可能。
- **5（check_designer との整合）**: 整合。Step5.5 行が経路Aの定義を直接満たし、F1 self-test ケースの検証対象になる。

### `throughput_realist` — 反論
<sub>2026-08-22T14:29:41+09:00</sub>

# throughput_realist: Round 2 — rebuttal / concession（対象ファイル再読なし・Round1 分析 + ホワイトボードのみで再検証）

## ① router_designer のエージング拡張案 — n はいくつになり、黒字化するか

エージングは「X 時間経過で Step5.5 を強制実行する」設計なので、firing 粒度 2h（12 firing/日）のもとで **n ≈ 24/X**（切り上げ丸め）になる。Round1 の出力上限 5 件/起動（**楽観値**・大型案件非クローズ・PR バンドル分割は未反映）で outflow=5n として、Round1 の流入 31〜38 件/日と突き合わせる:

| n | X | outflow（楽観） | 収支（流入31基準） | 収支（流入38基準） |
|---|---|---|---|---|
| 1 | 24h | 5 | -26 | -33 |
| 2 | 12h | 10 | -21 | -28 |
| 3 | 8h | 15 | -16 | -23 |
| 6 | 4h | 30 | -1 | -8 |
| 7 | 3.4h | 35 | +4 | -3 |
| 12 | 2h（毎firing） | 60 | +29 | +22 |

**結論**: 現在の流入（31〜38件/日）のまま黒字化するには **X ≈ 3〜4 時間**（n=6〜7）まで攻める必要がある。これは router_designer 自身が Step5 について指摘した「ほぼ常時該当」問題を **Step1〜4 側に反転させて再発させる**（X を 3〜4h まで下げると、Step5.5 が 6〜7 firing/日 = 半分以上を専有し、router_designer が案2 で懸念した「Step2 の CP-4 優先原則との衝突」に事実上抵触する）。**エージングは「retro-try が永久に届かない」問題（starvation）は解決するが、「届いても outflow が inflow に追いつかない」問題（throughput 不足）は X の選び方次第であり、starvation 回避に妥当な X（8〜12h・n=2〜3）では黒字化しない。** X の決定は starvation 回避と throughput 確保の**トレードオフ**であり、どちらか一方の基準だけで決め切れない。→ ③ の inflow 側の対策と併用しないと、starvation を再発させずに黒字化する X は存在しない、というのが Round2 の追加知見。

## ② lane_boundary の直交 2 軸説 — 自分のデータで再検証した結果、**認める（concession）**

`all_open_issues.json` を自分で再集計:

```
type:improvement のみ併記: 66
単独（type:retro-tryのみ）: 31
type:bug 併記: 9
type:docs 併記: 7
合計: 113  ← lane_boundary の内訳と完全一致
```

さらに title prefix との相関も独立に確認した:

| prefix | 件数 | dual（type:improvement併記） | 比率 |
|---|---|---|---|
| `[Retro]` | 10 | 10 | 100% |
| `improvement:` | 71 | 56 | 79% |
| `fix:` | 9 | 0 | 0% |
| `type:...` | 12 | 0 | 0% |
| `docs:` | 9 | 0 | 0% |

`fix:`/`type:`/`docs:` prefix は **dual 率 0%**、`[Retro]`/`improvement:` prefix は高 dual 率。これは lane_boundary が引用した起票元コード（`retrospective/reference.md:245-247` のラベル配列ハードコード）の挙動と一致し、**dual-label は「Try の内容が2レーンにまたがる」からではなく「起票テンプレートが機械的に両方貼るから」**という lane_boundary の説明を裏付ける。

**Round1 §6 の「二重ラベル58.4%は重複というより閾値の緩さを示唆」という推論は撤回する。** dual-label 自体は起票基準の緩さの証拠にはならない（直交軸の表記問題であり、ルーティングの曖昧さもゼロ）。

**ただし**、これは「1日あたりの新規 Issue 件数（24/49/20/20）」という Round1 §1 の核心データとは無関係な訂正である。dual-label の解釈が変わっても、**日次起票件数の実測（3日平均31件、brief値37.7件）自体は労働も再検証もされておらず、③・④の流入超過という結論は影響を受けない**。撤回するのは「dual-labelが原因」という因果の主張のみで、「流入が流出を上回る」という収支結論は維持する。

## ③ #377 の完了条件との照合 — 明確化（reclassify）

#377 本文の完了条件（Issue 全文をホワイトボード外で確認済み・5項目）を再読した:

1. `type:retro-try` が機械的に到達できる（ID で示せる）
2. `improvement-lane-map.md` と決定木の記述一致
3. **既存 113 件が棚卸し済み（重複統合・不要クローズ「後」の残件数を記録する）**
4. 経路断絶の再発検知の機械検査がある
5. `run_checks.sh` 緑

**条件 3 は「バックログを retro-try-handler で消化しきる」ではなく「一度きりの棚卸し（#385/PR#399 と同型の重複統合・クローズ判定）で残件数を記録する」ことを要求している。** これは Round1 §3〜§5 で論じた「日々の流入 vs retro-try-handler の流出」という **継続的スループットの問題とは別物**である。

**明確化: 私の指摘は「本スプリントで解決しないと完了と言えない」ものではなく「別 Issue へ送るべき critical」である。** 完了条件 3 は静的な棚卸し 1 回で満たせる。ただし critical として残すべき理由は変わらない: 条件3で記録する「残件数」は、経路開通後も継続的に流入超過（②で維持した結論）が続く限り**その日のうちに古くなるスナップショット**であり、PR/Issue コメントに「この件数は時点値であり、流入抑制策（下記④）が別途必要」という一文を明記しないと、「棚卸し済み＝解決済み」と誤読されるリスクがある。この一文の明記は本スプリントのタスク（条件3の実施）に含めるべきだが、流入抑制の実装そのものは別 Issue でよい。

## ④ 流入を絞る具体案（数値）— #393 と重複しない本スプリントの最小 1 手

#393 は「重複検索の必須化」（同一問題の再起票を防ぐ）であり、②で確認した通り dual-label 問題とも重複問題とも別軸。**流入の"量"そのものを絞る施策は #393 の範囲外**であり、ここが空いている。

自分のデータで検証: `priority:high` のみに限定した場合の内訳:

```
priority:high  : 34/113 = 30.1%
priority:medium: 73/113 = 64.6%
priority:low   :  6/113 =  5.3%
```

**提案**: `retrospective` スキルの Try 起票判定に「`priority:high` 以外は Issue 化せず、KPT レポート本文（または既存の集約 Issue へのコメント追記）に留める」という 1 条件を追加する（起票元コード `retrospective/reference.md:242-249` 付近、ラベル配列を組み立てる直前に priority 判定を挟む）。

**効果の試算**: 30.1% を現在の日次流入（31〜38件/日）に適用すると **流入 ≈ 9.3〜11.4 件/日** に圧縮される。これは①の表の **n=2（X=12h）で outflow=10件/日 とほぼ拮抗し、n=3（X=8h）で outflow=15件/日なら明確に黒字化する** 水準であり、**X=8〜12h という router_designer 案の「starvation回避として妥当な範囲」の X 値のままで黒字化が成立する**（①で導いた「X=3〜4h まで攻めないと黒字化しない」という無理な要求が解消される）。

**本スプリントで実施すべき最小の1手**: `retrospective/reference.md` の Try 起票条件に priority:high 限定フィルタを追加する 1 行変更（#393 のマージ後に適用しても独立して機能する・依存関係なし）。これと router_designer の Step5.5 エージング（X=8〜12h・n=2〜3）を **セットで採用** すれば、starvation も throughput 不足も同時に解消できる、というのが Round2 の統合提案。

**別 Issue へ送るもの（変わらず）**: バンドル条件緩和・大型案件の非クローズ対策（Round1 §4）・priority:medium 以下の扱い（KPT本文集約の設計詳細）。

## まとめ（1 行・Round2）

**dual-label 論は lane_boundary に同意（撤回）。完了条件は「棚卸し1回」であり本スプリントのブロッカーではないと明確化。ただし流入超過は実測として維持し、`priority:high限定フィルタ`（流入を31〜38→9〜11件/日に圧縮）と `X=8〜12h のエージング`（n=2〜3）をセットで採用すれば、starvationとthroughput不足を両方解消できる、という統合案を Round2 の結論とする。**

### `lane_boundary` — 反論
<sub>2026-08-22T14:29:59+09:00</sub>

# lane_boundary ラウンド 2 — rebuttal / concession

## 1. throughput_realist との対立の決着: 「閾値の緩さ」説と「直交軸」説

**部分的に譲歩し、部分的に反論する。** 争点は 1 つの数字（58.4%）に 2 つの異なる主張を乗せている点で、両方を同時には成立させられない。

- **私の主張（ルーティング）は撤回しない**: `retrospective/reference.md:245-247` の `labels` 配列は `type:retro-try` と `type:improvement` を **無条件でハードコード**しており、内容判定を経ない機械的付与である。これは「[Retro][…]」タイトルの起票（テンプレート直接出力）10 件が **100% dual**（10/10）という round 1 の実測と整合する。この 10 件については「ラベルが Try の内容の質を反映している」という解釈が成立する余地がそもそも無い —— テンプレートが必ず両方貼るのだから、貼られたことは何の情報量も持たない。したがって **この 10 件に関しては throughput_realist の「閾値の緩さの示唆」は根拠にならない**。
- **一方で譲歩する点**: dual-label 66 件のうち残り 56 件は「[Retro]」ではなく「improvement:」prefix で、これはテンプレート直接出力ではなく **後から書き換えられたもの**（round 1 で「おそらく棚卸し #385 前後の手作業/正規化」と推測した部分）。この 56 件については、私はラベル付与の *機構* を特定できていない。throughput_realist が §1 で示した **08-20 に単日 49 件**という起票バーストが `#385 / PR #399` の棚卸しセッションと符合するという指摘（throughput_realist 投稿の §1）は、この 56 件の起源を「機械テンプレート」ではなく「一括グルーミング作業中の量産」で説明できる可能性を示しており、**これは私の round 1 の推測（「後から書き換えられた」）を裏付ける独立証拠**である。
- **決着**: 58.4% という数字それ自体は「ルーティングが曖昧である」ことの証拠には **ならない**（ルール 2 は type: の他フラグを見ないので機能的に曖昧さゼロ、これは譲らない）。しかし 56 件の由来がバーストである以上、throughput_realist の「Try 起票の閾値が緩い」という主張は **ラベルの共起そのものではなく、起票プロセスの挙動**（一括グルーミング時に大量の Try が短時間で機械的に量産される）**から支持される別根拠を持つ**、という形で部分的に同意する。要するに: **「58% だから曖昧」は誤り（棄却）／「58% の起源を辿ると起票プロセスに緩さがある」は支持できる（採用）**。両者は同じ結論（Try 起票基準を厳格化すべき）に収束するが、根拠の筋道は私の方が正確である。

## 2. `triage_improvements.py` の実装バグは #377 のスコープ内か外か

**スコープ外と判断する。今スプリントでは直さず、別 Issue に切り出す。**

根拠は `CLAUDE.md` の CP-1 スコープ規則そのもの: 「**自分がこのタスクで変更したコードパス上の壊れ**（自分の変更で落ちたテスト等）は即修正、**自分の変更と無関係な既存の壊れ**（他モジュールの既存失敗）はブロッカーであっても即修正の対象にしない、Issue 起票で前に進める」。

- #377 の議題（brief 冒頭）は「type:retro-try の Issue が自走ルーティンの **どのブランチからも拾われず滞留する**」＝退避経路（決定木への到達性）の欠如。私が発見したバグは真逆の症状（`type:retro-try` の Issue が **改善レーンのツールに誤って拾われている**）で、決定木の到達性とは無関係な、Step G-1（棚卸し本体）という **別のコードパス** の既存不良である。今回のスプリントで変更するファイル（`sprint-cycle-router/SKILL.md` 等）のいずれの変更もこのバグを経由しない。
- 直す価値はある（CP-3 衛生）が、CP-1 の解決規則どおり「起票はこのスプリントで行い、実装は着手しない」が正しい振る舞い。round 1 の移行手順 §2/3 は「案 1 の完成形として書いた」ものであり、**このスプリントの必須タスクとして書いたわけではない**——ここで訂正する。verdict の `tasks` には入れず、`critical`（または新規 Issue 起票候補）に「`tools/triage_improvements.py` が `type:retro-try` を除外していないため Step G-1 の棚卸し集計に 66 件が混入している」を残すことを提案する。

## 3. throughput_realist「経路開通だけでは満たさない」への案 1 の立場からの回答

**同意する。かつ、案 1（レーン維持）のままで流入超過に対処できることを示す。 むしろ案 2（統合）は流出面で悪化する。**

流入超過の解消策は 3 つとも **lane 境界を一切動かさない**:

1. **流入抑制**（throughput_realist §6 の提案そのもの）: `retrospective` の Try 起票基準を絞る（1 回のレトロ実行あたりの Issue 化上限・`priority:low` かつ単一ファイルは Issue 化せず lessons 直記載で完結）。これは `retrospective` スキル内で完結し、`improvement-lane-map.md` にも `self-improvement-loop` にも触れない。
2. **流出増加（バッチ側）**: retro-try-handler の動的上限（`reference.md` の 2〜5 件/回）やバンドル条件を調整する。retro-try-handler 単体の変更で、lane 境界は不変。
3. **流出増加（優先度側）**: router_designer の Step 5.5 エージング閾値 X を throughput_realist の収支計算に合わせて調整する。`sprint-cycle-router` 内で完結。

**むしろここで案 1 の優位性を追加で指摘する**: もし案 2（self-improvement-loop への統合）を採っていたら、`type:retro-try` の 113 件は self-improvement-loop 消化モードの **固定 5 件/回**（`SKILL.md:「上限は 5件/回」`）という同一予算を、既存の `type:improvement` バックログ（#385/#399 の棚卸しで 100 件規模と判明済み）**と奪い合う**ことになる。retro-try-handler が持つ独立した動的上限（2〜5 件、バックログ量に応じて自動拡張）を失い、共有予算の中で希釈される。つまり **案 2 は throughput の観点でも悪化要因**であり、経路開通の議論とは独立に、③ の流出改善に対しても案 1 の方が筋が良い。

## 4. router_designer の Step 5.5 案は 3 レーン責務境界と整合するか — `improvement-lane-map.md` の具体的書き換え

**整合する。Step 5.5 は「振り返りレーンの実装主体（retro-try-handler）」を変えず、単に呼び出し元を追加するだけなので、3 レーン構成（§1）・一意判定ルール（§2）はいずれも無改訂でよい。**

ただし `improvement-lane-map.md` には **2 箇所、事実を最新化する必要**がある（レーン境界の変更ではなく記述の正確性の問題）:

- **L14（振り返りレーンの「主な起動」列）**: 現状「`pr-review-watcher` 内の最終ステップ … / 日次消化スロット / …」の「日次消化スロット」は抽象的なプレースホルダで、実装が存在しなかった（brief 論点 B）。Step 5.5 採用後はこれが **具体的な実装を得る**ので、`日次消化スロット` を `sprint-cycle-router Step 5.5（type:retro-try のエージング付き消化・cron 2 時間おき）` に書き換える。
- **L21-24（「振り返りレーンの起動元は pr-review-watcher のみ実装済み」の自己申告ブロック）**: **ここは docs_trace の round 1 提案（「未実装」を削除）を訂正する。** この note は `retrospective`（KPT 生成）が他パイプラインの最終ステップから呼ばれる話であり、Step 5.5 が呼ぶのは `retro-try-handler`（Try の実装）であって `retrospective` ではない。**両者は振り返りレーンの中の別スキル**（上流＝KPT生成 vs 下流＝実装）なので、Step 5.5 の追加は L21-24 が指摘するギャップ（`self-improvement-loop` 等の最終ステップから `retrospective` を呼ぶ経路が無い）を **解消しない**。L21-24 は事実として変更不要（「未実装」のままで正しい）。ただし混同防止のため文末に 1 行足すことを提案する: 「（`retro-try-handler` 自体の起動経路は #377 で `sprint-cycle-router` Step 5.5 として実装済み。本 note が指すのは `retrospective` の呼び出し元の話で別問題）」。

L46-61（一意判定ルール本体）は §1 と同じ理由で **無改訂**。

## 5. `retro-try-handler/SKILL.md:24` のプレースホルダ `{親ワークフロー}` の置換文言

router_designer の提案（「sprint-cycle-router の Step5.5」）に **同意し、確定させる**。ただし元の行は「日次の消化スロット（プロジェクト定義）+ 週次の{親ワークフロー}（プロジェクト定義）内からの呼び出し」と **2 つの粒度**（日次／週次）を併記しているが、Step 5.5 は 2 時間おき cron（1 日 12 回評価）なので日次・週次の両方を包含し、この二重表記自体が冗長になる。

**確定案（トリガー条件の行を丸ごと置換）**:

```
- `sprint-cycle-router` の決定木 Step 5.5（`status:waiting-claude` かつ `type:retro-try` の
  Ready Issue が存在し、エージング条件を満たす時。cron は `docs/routines/sprint-cycle-routine.md`
  の 2 時間おき単一ルーティン）
```

「日次の消化スロット」「週次の{親ワークフロー}」という 2 本立ての表現は削除する（実体は 1 本の cron 上の 1 分岐に統合されるため、複数トリガーがあるかのような記述は誤解を招く）。

---

以上、post 済み。

### `check_designer` — 反論
<sub>2026-08-22T14:30:11+09:00</sub>

# check_designer ラウンド2: 4件への反論・譲歩

## 1. router_designer 「Step 5.5 追加だけで REACHABLE になるか」→ **なる。これは検査の射程外として明示する（譲歩＋射程確定）**

**譲歩する**: router_designer の Step 5.5 案（決定木テーブルに `retro-try-handler` を委譲先スキル列に追加）は、私の経路A定義（2.2節「委譲先スキル」列にスキル名が出現）をそのまま満たし、私の検査は即座に REACHABLE / PASS を返す。これは正しい判定であり撤回しない。

だが指摘の核心は「その 1 行が **実際に真になる保証がない**（router_designer 自身のエージング設計は『直近 closed から X 時間経過』という **実行時条件** に依存し、Step5 がほぼ常に真＝上位ブランチの飢餓により Step5.5 は評価すらされない firing が大半になりうる）」という点で、これは私の検査が **見逃す**。認める。

**射程を確定する**: 私の検査（`tools/check_lane_reachability.py`）が保証するのは **構文的到達可能性**（syntactic reachability）＝「決定木・SKILL.md 本文・hooks のどこかに、そのスキルへの委譲を記述したテキストが存在するか」のみである。**保証しないのは**「その記述が実際の firing 列挙順序で評価に到達する頻度」＝ **意味的生存性**（semantic liveness）。コンパイラの dead-code-elimination が「到達不可能な行がある」ことは検出できても「到達可能な行が実運用でどの頻度で通るか」はプロファイラの仕事であるのと同じ分離。

この分離を1章に明記する（現在の設計書には無い）: **本検査は「一度も呼ばれない」という最悪の断絶（#377の実体そのもの）だけを機械的に潰す。「呼ばれるが滅多に真にならない」という飢餓は throughput_realist のレンズ（数値でのシミュレーション）と router_designer のエージング機構自体の設計品質でしか防げない。** 2つの検査は補完関係であり、片方が他方の代替にはならない。

## 2. throughput_realist 「到達可能だがPASSを返すのに滞留したまま、という乖離を捉える手はあるか」→ **限定的に可能。ただし核の検査には混ぜない**

実装可能性を判断した:

- **可能な部分**: router_designer の飢餓対策自体が「直近 closed された `type:retro-try` Issue の `closed_at`」という GitHub 側アーティファクトを既に必要としている（router_designer ラウンド1 §③案1「状態の永続化」節）。これと **同じクエリ**（`mcp__github__list_issues(state=CLOSED, labels=["type:retro-try"], orderBy=UPDATED_AT, perPage=1)`）を私の検査からも叩けば、「経路は存在する（REACHABLE）が、直近 N 日 closed 実績が 0 件（STALE）」という **第2の判定軸**を追加できる。
- **不可能／望ましくない部分**: これを核の `check_lane_reachability.py --self-test` には混ぜない。理由は2つ。① 私の検査の自己テスト（4.1/4.2節）は **ネットワーク非依存の純粋関数**として設計しており、これは `check_skill_references.py --self-test`（既存の骨格）と同じ性質を保つための意図的な制約。GitHub API 依存を混ぜると self-test が CI/PR ゲートで実行不能になる（`tools/run_checks.sh` は `--self-test` だけを配線する設計思想＝「本判定はネットワーク・GitHub API に依存するので配線しない」という `check_prod_drift.py`（`tools/run_checks.sh:245-251` の実例コメント）と全く同じ理由）。② 「PASS するが滞留したまま」を FAIL 扱いにすると、飢餓が **正しい優先順位設計の結果**（Step1〜4 が本当に忙しい健全な状態）でも赤くなり、throughput_realist 自身が算出した「n=1/3 では黒字化しない」という **構造的事実**（一時的な逸脱ではなく恒常的な不足）を FAIL/PASS の二値では表現できない。

**採用する設計**: 核の到達性チェックとは **別フラグ** `--liveness`（`check_skill_references.py` の既存 `--downstream` フラグと同型のオプトイン拡張）を追加する。
```
python3 tools/check_lane_reachability.py --liveness
```
- 到達可能（REACHABLE）と判定されたレーンについてのみ、直近 closed の Issue（対象ラベルが分かる場合。`retro-try-handler` なら `type:retro-try`）の `closed_at` を1クエリで取得
- 閾値超過（既定 48h、router_designer のエージング閾値 X と同じ値にすべき — 自分のレンズでは決めない）なら **WARNING**（終了コードは変えない。理由は上記②）として出力するのみ
- `--liveness` は `run_checks.sh` に配線しない（API 依存・本判定と同じ扱い）。`workflow-health-check` の週次監査から呼ぶ運用を推奨（監査・衛生レーンの既存責務と自然に一致する）

これで throughput_realist の指摘は「検査の可視化対象には入れるが、到達性チェックのPASS/FAILとは独立した別シグナルとして扱う」形で回収できる。**滞留そのものの解消策（流入抑制・優先度引き上げ）は throughput_realist §8 の通り別 Issue の管轄**であり、私の検査はそれを解決しない。

## 3. docs_trace 「21箇所のうちどれを『起動』と見なすか」→ **21箇所中0箇所が経路Bの起動証拠。分類基準を精緻化する**

docs_trace の表（ラウンド1 §3）を、私の経路B判定（2.3節: `.claude/skills/*/SKILL.md` 限定・スキル名バッククォート+同一行or直後1行に起動動詞・自己参照除外）に当てはめて再分類する（対象ファイルは開かず、docs_trace の要約文言のみで判定。厳密な行内容確認は実装時に要る旨を明記する）:

| ファイル:行 | docs_trace の要約 | 経路B判定 | 理由 |
|---|---|---|---|
| `sprint-cycle-router/SKILL.md:151` | Step5説明で type:retro-try 除外理由に言及 | ❌ 言及のみ | 除外理由の説明文＝「呼ばない」ことの説明。起動動詞と共起しても文脈は否定（後述の負例パターンと同型） |
| `project-sync/SKILL.md:224` | retro-try-handler が担当と明記 | ❌ 言及のみ | 責務の記述（「Xが担当」）であり「Xを起動する」ではない |
| `self-improvement-loop/SKILL.md:3,37,298,314` | description/除外条件/見出し | ❌ 言及のみ | 全て「扱わない」「除外」の否定文脈、または自スキル内の見出し |
| `workflow-health-check/reference.md:80-81` | 監視レポート対象と明記 | ❌ 言及のみ | retro-try-handler は監視の**客体**であって呼び出しの**主体・対象**ではない |
| `retro-try-handler/SKILL.md:2,24,61,191` | 自スキル本体（name/トリガー/ブランチ名/サマリー） | ❌ 対象外（自己参照除外） | 2.3節の自己参照除外規則そのもの。L24 の `{親ワークフロー}` プレースホルダは自然文トリガーの自己申告であり、**他ファイルからの証拠にはならない**（証拠は常に「呼ぶ側」のファイルに存在しなければならない） |
| `retrospective/SKILL.md:3,204,210,216` | description/対応フロー指定/関連スキル表 | ❌（要実文確認） | 「Try Issue の対応フローは retro-try-handler が担当」という**責務の指定**は起動文とは別（`pr-review-watcher/SKILL.md:214` の「続けて `retrospective` スキルを起動する」との違いは、後者が **手順内の実行文**（Step の一部として書かれた命令文）である点。retrospective→retro-try-handler は「Try は誰が実装するか」という **住み分けの記述**であって「今この手順でretro-try-handlerを呼べ」という命令文とは文体が異なる可能性が高い。実文を読まずに断定はしないが、暫定的に❌側に分類し、実装時に要再確認としてマークする） |
| `retrospective/reference.md:347` | 実装は retro-try-handler と明記 | ❌ 言及のみ | 同上 |
| `claude-code-optimization.md`/`agent-team.md`/`autonomous-operation-policy.md`/`token-optimization-rules.md` | 各種 docs/rules 参照 | ❌ **スコープ外** | 2.3節の走査対象は `.claude/skills/*/SKILL.md` に限定しており、`docs/rules/*.md` はそもそも走査しない。これは意図的な設計だが、この4ファイルの中に「実際に起動している」記述があれば見逃す（後述の限界として認める） |
| `improvement-lane-map.md:14,22` | 起動元未実装の警告 | ❌ **走査対象外（別の役割）** | 2.1節ではこのファイルを「レーン一覧の抽出元」としてのみ使い、経路Bの証拠探索対象にはしない（次の論点4で詳述） |

**結論: 21箇所のうち経路B成立は0件**。これは私のラウンド1 F1ケース（「現状 retro-try-handler は UNREACHABLE」）と**矛盾なく整合する**——むしろ21箇所という多数の「言及はあるが呼び出しはない」という実測が、#377の問題（言及されているのに実行経路が無い）をそのまま裏付けている。

**誤検出防止の追加ルール（今回発見した具体的な負例から一般化）**: 経路Bの正規表現に **否定文脈フィルタ**を追加する。スキル名+起動動詞が同一行/直後1行にあっても、その節に否定マーカー（`扱わない`/`除外`/`未実装`/`ではない`/`しない`/`扱われない`）が共起する場合は証拠として **採用しない**。理由: `improvement-lane-map.md:22`「他パイプラインからの `retrospective` 起動は**未実装**」という文は「`retrospective`」+「起動」を含むため素朴な正規表現だと誤って経路Bの証拠と誤認する（誤検出の実例）。ただしこのファイル自体は2.1節の役割限定によりそもそも経路Bの走査対象に入らないため実害はないが、**将来 docs/rules も走査対象に含める変更をするなら、この否定文脈フィルタは必須**と明記しておく（論点4の回答と直結）。

**見逃し防止（言及を起動と誤認しない、の逆側＝起動を言及と誤認しない）**: `pr-review-watcher/SKILL.md:214` の実例「4. 続けて `retrospective` スキルを起動する（KPT生成とTryのIssue化。既存仕様のまま）。」は Step 見出し配下の **番号付き実行手順の1項目**として書かれている。この「番号付き手順内である」ことを追加の弱いシグナル（必須条件ではなく加点要素）として使う設計を提案する: 同一行に起動動詞があっても、（a）表のセル内、（b）frontmatter description内、（c）見出し直下でない独立した説明段落、のいずれかであれば、Step手順内単独のケースより弱い証拠として扱い、`--strict` フラグの有無で採否を分ける余地を残す（実装時の調整項目とし、self-testのF2ケース＝`pr-review-watcher:214`は手順内実行文の典型例として固定する）。

## 4. lane_boundary 「improvement-lane-map.md L21-24 の自己申告そのものを検査対象にすべきか」→ **対象にしない。理由を明確化する**

**結論: 自己申告テキスト自体をFAILトリガーにしない。** 理由は3つ:

1. **Goodhart's law リスク**: 「ドキュメントが『未実装』と書いている箇所をFAILにする」ルールを作ると、それを回避する最も安易な方法は「未実装」という誠実な注記を **削除する**ことになる。正直な自己申告を罰する検査は、誠実さより見た目のグリーンを優先させる誤ったインセンティブを生む。むしろ #377 発覚の経緯（`improvement-lane-map.md:21-24` 自身が正直に「未実装」と書いていたことで発見された）を踏まえると、この種の自己申告文は**保護すべき情報源**であり、検査の敵ではない。

2. **役割の重複回避**: 私の検査（経路A/B/C）は improvement-lane-map.md の記述を **読まずに独立して** 同じ結論（UNREACHABLE）に到達できる設計にしている（論点3の表で示した通り、21箇所の実装側テキストを機械的に走査した結果として導出）。自己申告文を検査対象にするのは、**証拠として使わない）と決めた文書を今度は判定材料として使う**という設計の一貫性の破れになる（2.1節で「表の記述は仕様であって実装の証拠にならない」と明記した原則と矛盾する）。

3. **有用な使い道は「クロスチェック」であって「FAIL条件」ではない**: とはいえ自己申告文には価値がある——それは **私の検査結果の妥当性を人間がレビューする際の参照点**として機能する。そこで以下を提案する:
   - improvement-lane-map.md の自己申告文自体は検査対象に含めない（FAIL条件に使わない）
   - ただし `check_lane_reachability.py` の人間向けレポート出力（無引数実行時）に、UNREACHABLE と判定したレーンについて「`improvement-lane-map.md` に関連する自己申告記述がないか目視確認を推奨」という **注意書き1行**を添える（機械的にファイルを読んで文字列一致させるのではなく、レビュアーへの手がかりとして出力するだけ）
   - 将来的に自己申告文と機械判定が **食い違う**（文書は「実装済み」と書いているが機械判定はUNREACHABLE、あるいはその逆）場合にこそ、それは `skill-audit` レーンが拾うべき **ドリフト**であり、私の到達性チェックの責務ではなく `check_skill_references.py` 系の「ドキュメント記述と実態の整合性」チェックの管轄に委ねる（責務分離。私の検査は「実装側に到達経路があるか」だけを見る単機能ツールに留める）

## まとめ（4点の裁定）

| 論点 | 裁定 |
|---|---|
| router_designer: Step5.5追加だけでPASSになる限界 | **譲歩**。構文的到達可能性と意味的生存性を明確に分離し、後者は本検査の射程外と明記 |
| throughput_realist: PASSでも滞留する乖離 | **部分採用**。`--liveness` フラグとしてオプトイン実装（API依存・self-testに混ぜない・終了コードを変えないWARNING扱い） |
| docs_trace: 21箇所の分類基準 | **精緻化**。21箇所中0箇所が経路B成立（現状のUNREACHABLE判定と整合）。否定文脈フィルタを新規ルールとして追加 |
| lane_boundary: 自己申告文を検査対象にすべきか | **対象外と裁定**。Goodhart's lawリスクと設計原則の一貫性を理由に、レビュー注意書きへの降格に留める |
