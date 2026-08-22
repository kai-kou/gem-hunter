<!--entry
author: check_designer
round: 1
kind: claim
ts: 2026-08-22T14:24:58+09:00
-->

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
