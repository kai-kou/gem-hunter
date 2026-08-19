# トークン消費最適化ルール

Claude Code のトークン消費を最小化し、セッションあたりのコスト効率を最大化するためのルール。

## 背景（2026-03 調査）

2026年3月に報告された異常なトークン消費の原因は以下の4つが重なったものである。

| 原因 | 種別 | 影響 |
|------|------|------|
| セッション再開バグ（CC-BUG-08） | バグ | 大規模プロジェクトで出力トークン暴走 |
| プロンプトキャッシュミス | 構造的問題 | CLAUDE.md・ルールファイルの再送コスト増大 |
| ピーク時間帯の消費速度引き上げ | 意図的変更 | JST 22:00〜翌4:00 のコスト増 |
| 需要爆増によるインフラ圧迫 | 背景因 | 全ユーザーに影響 |

## ルールファイル階層化（最重要対策）

### 設計原則

`.claude/rules/` に配置するのは **全セッションで必要な基盤ルール** のみ（実際の常駐リストは `tools/check_rules_sync.sh` の `ESSENTIAL_RULES` が正本）。タスク依存のルールは `docs/rules/` に実体のみ配置し、スキルが必要時に Read で読み込む。

### 常時必要ファイル一覧

> **SSOT 注意**: Hot 層（常時必要）の **正本は `tools/check_rules_sync.sh` の `ESSENTIAL_RULES`** 。下表は概念説明のための例示であり、実際の常駐リストは ESSENTIAL_RULES を参照すること（ドリフト防止）。

| ファイル（例） | トークン概算 | 理由 |
|---------|------------|------|
| `agent-team-summary.md` | ~1,300 | 全タスクでサブエージェント使用 |
| `completion-report-rules.md` | ~1,250 | 全セッションの完了報告構造 SSOT |
| `core-principles.md` | ~1,100 | 全タスクの大原則（詳細は `core-principles-detail.md`） |
| `datetime-rules.md` | ~800 | 日時表記 JST 統一 SSOT |
| `lessons-core.md` | ~2,300 | クリティカル **行動規範** のみ（環境障害カタログは `lessons/cloud-environment.md` へ降格・#324） |
| `pr-review-flow-summary.md` | ~1,350 | ほぼ全タスクで PR 作成（実行手順は `pr-review-watcher` スキル） |
| `session-compression-rules.md` | ~800 | 圧縮時の安全（詳細は `session-compression-rules-detail.md`） |
| `session-concurrency-rules.md` | ~1,000 | マルチセッション競合防止（R-1 ルーティン稼働のため Hot・詳細は `session-concurrency-rules-detail.md`） |
| `session-safety-rules.md` | ~800 | セッション安全 |
| `session-sprint-rules.md` | ~500 | スプリント運用の最小フォーム |
| `sprint-development-rules.md` | ~2,100 | スプリント開発 4 規律の SSOT（詳細は `sprint-development-rules-detail.md`・#13） |
| `user-confirmation-minimization.md` | ~2,700 | 確認要否の SSOT（プロジェクト例詳細は `user-confirmation-minimization-detail.md`） |
| `user-instruction-issue-rules.md` | ~900 | ユーザー直接指示の Issue 化判断 |
| `user-notification-triage.md` | ~1,500 | `@mention` 厳選 SSOT（分類ロジックの正本は `triage_notification.py`） |

> **Warm 降格済み**: `progress-reporting-rules.md`（制作系の長時間処理時にスキルが Read）は **既定では Hot 層に含めない**。`session-concurrency-rules.md` は本リポジトリでは R-1 ルーティン稼働（マルチセッション並行運用）のため Hot 化済み（E-B #20・PR #176）。単一セッション運用のプロジェクトでは Warm のままでよい。Hot 化/降格する場合は `ESSENTIAL_RULES` を編集して `./tools/check_rules_sync.sh --fix` を実行する。

### 削減効果・予算の推移（#146 → #324 → #369 で再校正）

| 指標 | 当初（8ファイル構成時） | #146 棚卸し前（2026-07-10） | #146 棚卸し後 | #324 棚卸し後（2026-07-26） | **#369 棚卸し後（2026-08-04）** |
|------|------|------|------|------|------|
| `.claude/rules/` ファイル数 | 8（7 symlink + 1 例外） | 13 | 13 | 13（変更なし） | 13（変更なし） |
| `.claude/rules/` 総サイズ（`wc -c` 実測・1KB=1000B換算） | ~76KB | ~123KB（123,038B） | ~95KB（94,825B） | ~65KB（65,335B） | **~68.7KB（68,713B）** |
| 推定トークン数 | ~19,000 | ~31,000 | ~24,000 | ~16,300 | **~17,200** |

**#146 の経緯（メタ肥大化）**: 当初 76KB は 8 ファイル構成時の校正値。その後 7 ファイルが個別 Issue で正当化されて追加され 13 ファイル構成になった。個々の追加判断は妥当だったが累積の再校正がなく 76KB→123KB まで肥大化。#146 で「プロジェクト例」テーブル・詳細プロセス記述を各 `-detail.md`（Warm 層）へ抽出し 95KB まで圧縮した。

**#324 の再校正（到達値 ~65KB / ~16,300 トークン）**: #146 の直後から再増加が始まり（95KB→98KB）、同 Issue が「追記マージンはほぼ無い」と明記した状態を超過していた。Anthropic「[The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)」の progressive disclosure 原則に沿って再棚卸しし、**Hot に残すのは「判断基準・不変の境界・実観測ベースの行動規範」だけ** とした。降格の判断軸は「代替の強制レイヤ（ハーネス / スキル / ツール / ツール description）が既にあるか」。

**#369 の再校正（当時の到達値 ~68.7KB / ~17,200 トークン。現行予算は下の増減ログを参照）**: #367→#375 の追加で増減ログが 4 行に到達し再棚卸しの合図が立ったため、#324 と同じ判断軸（「代替の強制レイヤが既にあるか」）で 13 ファイル全件を再点検した。降格したのは ① `session-compression-rules.md` の「新規ルールファイル追加時の必須手順」（`session-start.sh`/`post-compact.sh` の `check_rules_sync.sh --fix` が既に自動検出・修正するため、Hot には要旨 1 行のみ残し手順全文は `session-compression-rules-detail.md` へ）② `agent-team-summary.md` の Verbalized Sampling 記述（`agent-team.md`「サブエージェントの高度な機能」へ移設し SSOT を一本化）③ `completion-report-rules.md` の良い例/悪い例の具体テキスト（`stop-completion-report-check.sh` が Stop 時に既に是正リマインドを出すため、Hot には判断基準の「鉄則」5 項目のみ残し、例文は新設 `completion-report-rules-detail.md` へ）。#325/#328/#367/#375 で追加された行動規範自体は「実観測ベースの行動規範」（削減対象外②）に該当し、代替の強制レイヤが無いため Hot に残置した（再点検の結果、追加分の削除は不可と判断）。

**削減対象外（意図的に残す）**: ① A-1〜A-6 の既約境界外リスト ② 実観測ベースの行動規範 lessons（記事の削除基準 "specific, demonstrable failure mode" に照らすと残す側）③ Haiku サブエージェント向けの明示的な出力ルール（Claude 5 世代ではないため「判断に委ねる」の適用外）。これらを削らない前提での到達値が 68.7KB であり、以後の追加は `session-compression-rules.md`「新規ルールファイル追加時」の Hot 予算チェックに従う。

#### 🔴 2 軸が衝突したときの解決規則（#19 で決定・2026-08-17）

「削減対象外②（実観測ベースの行動規範）」と「降格の判断軸（代替の強制レイヤが既にあるか）」は衝突しうる。次で解決する。

> **「代替の強制レイヤがある」を理由に降格してよいのは、その強制レイヤが プロジェクト側の裁量で差し替え・無効化されないもの に限る。**

| 強制レイヤの種類 | 差し替え可否 | 衝突時の扱い |
|---|---|---|
| hook（`.claude/hooks/*.sh`）・CI ゲート・ツールの description | 🔵 **実質差し替え不可**（消せば機能自体が壊れる／CI が落ちる） | **降格してよい**（#324 / #369 で降格したのはすべてこれ） |
| 他ルールへの SSOT 一本化（重複そのものの削除） | — | **降格してよい**（重複解消であって規律の喪失ではない） |
| **output style**（`.claude/output-styles/*.md`）・`CLAUDE.md` の節・`settings.json` の設定値 | 🔴 **差し替え可能** — `CLAUDE.md` 自身が「口調を変えたいプロジェクトは本セクションと output style の両方を書き換える」と明記している | 🔴 **削減対象外②を優先し Hot に残す**（差し替えた瞬間に規律が静かに失われる） |

**適用例（#19 の結論）**: `lessons-core.md` の **L-111 / L-113 / L-124**（計 5,503 B）は `.claude/output-styles/concise-neko.md` と内容が重複するが、**output style は差し替え可能なレイヤ** であるため **Hot に残す**。特に L-113（捏造禁止）は最もクリティカルな規律であり、冗長性を削る downside が非対称に大きい。削減額（Hot 層の 4.7%）はこのリスクを取る理由にならない。

#### 予算の増減ログ（1 行 1 追加・#146 型のメタ肥大化を防ぐため累積を可視化する）

| 日付 | 実測 | 差分 | 追加の正当化 / 相殺 |
|---|---:|---:|---|
| 2026-08-04 | 68,713 B | （**ベース側の記録**） | ベースリポジトリ `claude-code-repository-base` が #369 の再棚卸し後に記録した到達値。🔴 **本リポジトリの基準ではない**（下記 #15 の訂正を参照） |
| 2026-08-17 | **79,072 B** | **本リポジトリの基準** | ベース適用コミット `065d2f0` 時点の実測（13 ファイル）。ベース記録の 68,713 B から **+10,359 B** 乖離しているが、これは **ベースリポジトリ側で 2026-08-04 → 適用日の間に発生し、同リポジトリの増減ログに記録されなかった増分**（#15 で git 実測により確定） |
| 2026-08-17 | 89,303 B | +10,231 B | #13 / #16: `sprint-development-rules.md` を Hot 追加（8,685 B。全文 17.4KB のうち約半分を `-detail.md` へ Warm 分離した後の値）+ `user-confirmation-minimization.md` に確認 2 系統の定義を追記（+1,546 B）。**いずれも代替の強制レイヤが無い行動規範**（削減対象外②）のため Hot 必須 |
| 2026-08-17 | 90,091 B | +788 B | #19: `lessons-core.md` の L-111 / L-113 / L-124 に「output style と重複しても降格しない理由」を追記（本節の衝突解決規則の適用結果を各エントリ側にも残し、次の棚卸しで再度議題化されるのを防ぐ）。**この 788 B は 5,503 B を Hot に残す判断を確定させるためのコスト** |
| 2026-08-19 | **91,960 B** | **本リポジトリの基準（再測）** | ベース適用コミット `9b98d49` 時点の実測（14 ファイル）。内訳は ① 前行 90,091 B → 適用直前 91,600 B（**+1,509 B は #22 / #24 / #28 / #33 / #58 の間に発生した本ログ未記録分**・今回の実測で確定）② 本適用で `agent-team-summary.md` に早期撤退マーカーを追加（+360 B）。🔴 ベース記録値は参考にとどめ、差分計算の起点にしない（`apply-base` SKILL.md §6） |

**現行の実測は ~92.0KB / ~23,000 トークン（14 ファイル）。本リポジトリの基準 79,072 B に対して +12,888 B（+16%）** で、内訳は #13 / #16 の行動規範追加（+10,231 B）・#19 の判断根拠追記（+788 B）・本ログ未記録の累積（+1,509 B）・ベース適用分（+360 B）である（上表）。**未記録分が再び 1.5KB 溜まっていたため、次の棚卸しでは「Hot を触る PR は同一 PR で増減ログに 1 行足す」の運用徹底を先に確認する。**

### 🔴 #15 の訂正: 「未記録ドリフト」は本リポジトリで発生したものではない

#13 の作業中に「基準 68,713 B に対して実測が +10.8KB 乖離している」と観測し、**既存ファイルのどれかが加筆で膨らんだ** と推定して #15 を起票した。**この推定は誤りだった。**

`git` で Hot 対象 13 ファイルについて「ベース適用コミット（`065d2f0`）時点」と「現在」を 1 ファイルずつ実測した結果:

- **既存 13 ファイルは本リポジトリ内で 1 バイトも増えていない**（増分は #13 / #16 で追加した `sprint-development-rules.md` と `user-confirmation-minimization.md` の 2 件のみ）
- ベース適用の時点で既に **79,072 B** だった

したがって乖離 +10,359 B は **ベースリポジトリ側で 2026-08-04 以降に発生し、同リポジトリの増減ログに記録されなかった分** である。**本リポジトリに削るべき「ドリフト」は存在しない。**

### 🔴 再発防止（構造的な問題）

原因は「**ベースリポジトリが記録した基準値を、適用先リポジトリがそのまま引き継いでいた**」こと。ベース側が基準を更新し忘れると、適用先は最初から実態と合わない基準を持つことになり、次の棚卸しで「自分が膨らませた」と誤診する（#15 で実際に起きた）。

- 🔵 **`apply-base` でベースを適用したら、その時点の実測値を「本リポジトリの基準」として増減ログの先頭に記録する**（ベースの記録値をそのまま基準にしない）
- ベース側の記録は「参考値」として残してよいが、**差分計算の起点にしない**
- 実測コマンド: `wc -c .claude/rules/*.md | tail -1`

### #15 の副産物: 現在の Hot 層 89.3KB に削減余地があるかの判定（結論: **削減不要**）

「増分を削る」というアプローチが取れない（増分は行動規範の追加分のみ）ため、**絶対値として削減余地があるか** を上位 5 ファイルについて別途判定した。

| ファイル | 実測 | 降格候補 |
|---|---:|---|
| `user-confirmation-minimization.md` | 12,891 B | 「誤分類の常習パターン」の 4 例（detail §4 に移せる）≈ ▲320 B |
| `lessons-core.md` | 11,783 B | **なし**（全エントリが specific, demonstrable failure mode を持つ・削減対象外②） |
| `sprint-development-rules.md` | 8,685 B | `SD-3` の発火ライン表の 2 例（detail §3.1 に同一内容あり）≈ ▲200 B |
| `agent-team-summary.md` | 8,005 B | 上限の履歴脚注（`agent-team.md` F-9 と重複）≈ ▲35 B |
| `pr-review-flow-summary.md` | 6,820 B | **なし**（返信テンプレートの重複は高頻度使用のため意図的な二重化） |

🔴 **合計 ▲約 550 B（現状の 0.6% 未満）にとどまるため、降格を実施しない。** 5 ファイルはいずれも #146 → #324 → #369 の 3 回の棚卸しを経ており、既に「判断基準・不変の境界・実観測ベースの行動規範」だけが残る形に刈り込まれている。数十〜数百バイトの例示重複を削っても予算に対する影響は誤差であり、**削る作業自体のほうがコストが高い**。

⚠️ **判断が割れた 1 点（別 Issue で追跡）**: `lessons-core.md` の **L-111 / L-113 / L-124 は `.claude/output-styles/concise-neko.md`（system prompt に常駐し毎ターン強制される）と内容が大きく重複している**。「代替の強制レイヤが既にあるか」という判断軸に照らすと降格候補になりうるが、各エントリは削減対象外②（specific, demonstrable failure mode）にも文言上一致するため、本判定では **削らない** と結論した。この 2 つの分類が衝突するケースの扱いは棚卸しの判断軸そのものに関わるため、**#19** で別途検討する。

> 🔴 **予算は「記録した値」ではなく「実測」で管理する**。Hot 層のファイルを **追加または追記** する PR は、同一 PR で次を実行して増減ログに 1 行足す（`session-compression-rules-detail.md` の Hot 予算チェックを **既存ファイルへの追記にも拡張** したもの）:
>
> ```bash
> wc -c .claude/rules/*.md | tail -1   # 実測を取ってから増減ログを更新する
> ```

### 削減の品質バーを先に固定する（Anthropic cookbook 由来）

> 出典: [Cost Optimization on the Claude API](https://github.com/anthropics/claude-cookbooks/blob/main/cost_optimization/cost_optimization.ipynb)（Anthropic Applied AI チーム）。
> 採否の議論記録は `content/discussions/cost-optimization-cookbook-adoption/`（**ベースリポジトリ側の記録で本リポジトリには存在しない**）。

cookbook の中核は「**品質バーを制約として先に固定し、コストだけを最小化する変数として扱う。eval が無ければ削減と劣化を区別できない**」。本リポジトリの Hot 層棚卸し（#146 / #324 / #369）は **KB とトークン数しか見ておらず、削った規律が実際に守られ続けているかを確認する手続きが無い**。以下の最小形で埋める（新規スクリプト・新規スケジュールは作らない）。

**ルール文書を削除・降格・要約する PR は、セルフレビュー時に次を満たすこと**:

- [ ] 削減対象の記述が **実際に適用されたはずの直近の実ケース**（Issue コメント / PR diff / セッションの行動記録）を **1 件以上** 挙げ、PR 本文に書く
- [ ] そのケースが「削減後に Hot 層へ残る要約だけで再現できるか」を確認する（再現できないなら削らない、または降格先を SKILL.md Step 0 の Read 対象にして決定論的に読ませる）
- [ ] 新規のラベル付きテストケースは作らない（既に起きた実ケースの回顧のみ。$/task の計測もしない — 本リポジトリはサブスク課金でタスク単価を測る手段が無い）

**単発の観測で構成を決めない**: cookbook は同一構成でも試行ごとに pass rate が入れ替わることを繰り返し警告する。モデル選択・effort 設定・ルール圧縮の良し悪しを **1 回の結果で断定しない**（`session-sprint-rules-detail.md` の SP 較正が「生値を KPI 化しない」としているのと同じ理由）。

#### 要約が例外条項を落とす失敗パターン（rule card 化のリスク）

cookbook で最も安価だった構成（マニュアルを「ルールカード」に圧縮して安いモデルへ分解）は、**例外条項（carve-out）が要約から抜け落ちて誤判定** した。「安くて少し間違っている」は最適化ではない。

本リポジトリの Hot 層サマリー化 + `-detail.md` 分離は、原文を **破棄せず退避** する点と、`SKILL.md` Step 0 の対応表が **モデルの自己判断に依存しない決定論的な Read ディスパッチ** である点で、この失敗例とは形が違う（全面的に同型ではない）。ただし **メインセッションが Hot 層のサマリーだけを見て判断する箇所**（本文中に散発する「詳細は `X-detail.md` を参照」）は、モデルが「今が例外を確認すべき局面だ」と気づけるかに依存するため同じリスクを共有する。

- Hot 層に残す要約からは、**判断の分岐を変える例外・境界だけは落とさない**（例示・手順・背景は落としてよい）
- 例外を Warm へ移すなら、参照を散発的な注記に留めず **スキルの Step 0 Read 対象** に載せて決定論的に読ませる

### 入力トークン管理（progressive disclosure）の適用範囲

cookbook の入力側レバーのうち、本リポジトリで **実行経路があるのは Hot/Warm 階層化と CLAUDE.md 圧縮**（上記）だけである。以下は汎用ベースでは採用しない:

| cookbook のレバー | 本ベースでの扱い | 理由 |
|---|---|---|
| tool search（`defer_loading`） | 採用しない | Claude Code は MCP ツール定義を **既定で遅延ロード** する（[公式](https://code.claude.com/docs/en/costs)）。ルール文書に書いても repo 側に制御手段が無い |
| 画像の事前ダウンスケール / Files API + code execution / token counting によるゲート | 汎用ベースには書かない | 画像・PDF・大規模 CSV を agentic loop に貼り込むワークロードが汎用ベースに存在しない（YAGNI）。**該当ワークロードを持つ下流プロジェクトが自分の `docs/rules/` に追記する** |
| 大量出力のフック側での事前フィルタ | 有効（採用可） | 公式もフックでの前処理を推奨。テスト出力・ログを丸ごと読ませず、フックで抽出してから渡す |

### 棚卸し手段としての `/doctor`（#327）

Claude Code 公式の診断コマンドを定期棚卸しに使う。実行は `workflow-health-check` スキルの Step 6-0 に組み込み済み。

| 実行形態 | 何を返すか |
|---|---|
| CLI `claude doctor` | **インストール健全性のみ**（native/npm 併存・パス破損・更新チャネル）。スキル / CLAUDE.md のサイズ適正化は含まれない（v2.1.220 実測・2026-07-26） |
| セッション内 `/doctor` | 設定・スキル・CLAUDE.md を含むフルチェックアップと修正 |

**出力は判断材料の 1 つとして扱う**。汎用ツールの「削れる」判定と、運用規律が主体である本リポジトリ Hot 層の必要性判定は一致しないことがある。削除の可否は「代替の強制レイヤ（ハーネス / スキル / ツール / 本体システムプロンプト）が実在するか」で決める。

### スキルが Read すべきルールファイル対応表

> ⚠️ 以下の表のスキル名・ルールファイル名は **出自プロジェクト（動画制作）の実例** 。汎用ベースには存在しないファイルもあるため、自分のプロジェクトのスキル・ルール名に読み替えること。

各スキルは Step 0 で必要なルールファイルを `docs/rules/` から Read する。

| スキル | 必要なルールファイル（`docs/rules/` から Read） |
|--------|-----------------------------------------------|
| script-pipeline, script-writer | script-rules.md, research-rules.md |
| script-team-reviewer | script-rules.md |
| audio-pipeline, voicevox-audio | audio-pipeline-rules.md, intonation-rules.md, pronunciation-rules.md |
| image-pipeline, image-generator | image-pipeline-rules.md, youtube-thumbnail-rules.md |
| video-pipeline | video-storage-rules.md, youtube-upload-safety-rules.md, youtube-title-rules.md, video-international-rules.md |
| shorts-pipeline | shorts-rules.md, research-rules.md, video-storage-rules.md |
| self-reviewer | self-review-learnings.md, script-rules.md, research-rules.md |
| retrospective | retrospective-rules.md, self-review-learnings.md |
| refinement | refinement-rules.md, research-rules.md |
| pr-review-watcher | self-review-learnings.md |
| youtube-scheduler | youtube-scheduling-rules.md |
| sns-publisher | slack-notification-rules.md |
| comment-responder | comment-response-rules.md |
| workflow-health-check | youtube-content-variation-rules.md, self-review-learnings.md |
| retro-try-handler | self-review-learnings.md |
| metadata-reviewer | youtube-title-rules.md |
| theme-discovery | series-management-rules.md |
| zenn-book-writer | zenn-book-rules.md |

### コンテキスト圧縮ポリシー

コンテキスト圧縮は Claude 標準の Auto Compaction（コンテキスト上限付近で自動発動・圧縮してセッションを継続）に委ねる。本ベースは圧縮タイミングを env（`CLAUDE_CODE_AUTO_COMPACT_WINDOW` 等）で固定しない。

## ピーク時間帯回避ルール

### Anthropic ピーク帯（2026-03-26 公式発表）

**PT 5:00〜11:00 / UTC 13:00〜19:00 / JST 22:00〜翌 4:00**

この時間帯はトークン消費レートが最大 2〜3 倍に膨らむ。

### ピーク帯に避けるべきタスク

- 長時間パイプライン（image-pipeline: ~60 分、video-pipeline: ~180 分）
- Opus（`opus`）を使用するタスク（台本生成、複雑な設計判断）
- 大量のサブエージェントを起動するタスク（Agent Teams レビュー等）

### ピーク帯でも許容されるタスク

- 5 分以内で完了する軽量チェック
- Haiku モデルのみを使用するタスク
- Slack 通知やコメント投稿のみの操作

### スケジュールタスクへの適用

メインアカウントのスケジュールはすべて JST 05:00〜19:00 に収まっており影響なし。

**サブアカウントの調整が必要**:

| タスク | 変更前（JST） | 変更後（JST） | 理由 |
|--------|-------------|-------------|------|
| image-pipeline（サブ） | **01:00**（ピーク帯） | **05:00** | ピーク帯回避 |
| video-pipeline（サブ） | 05:00 | **08:00** | image の後に実行 |
| script + audio（サブ） | 18:00 | 18:00（変更なし） | ピーク帯外 |

> **2026-05-05 更新（3アカウント体制移行）**: メインA が 24 時間フル稼働（深夜帯含む）に移行し、
> サブBも hourly 専用スロットを追加した。ピーク帯（JST 22:00〜翌4:00）での実行は Extra Usage を
> 消費するが、3アカウント合計で最大 84回/日（各28回/日 × 3）の実行容量を確保しているため、
> コスト効率より制作スループットを優先する設計判断。ピーク帯での長時間タスクがExtra Usage上限に
> 先に到達した場合はセッションが中断されるが、次スロットで自動復帰する（`session-safety-rules.md` 参照）。

## フック統合（CC-BUG-16 対策）

### 問題

フック 8 個以上でコンテキスト肥大化・ターン早期終了のリスクがある（CC-BUG-16）。

### 対策

| 変更 | 変更前 | 変更後 |
|------|--------|--------|
| PreToolUse (Bash) | 3 個（push, PR, comment） | **1 個**（`pre-tool-use-router.sh`） |
| PreToolUse (MCP) | 1 個（image gen） | 1 個（変更なし） |
| Stop | 3 個（git, PR, slack） | **1 個**（`stop-router.sh`） |
| **合計** | 11 個 | **7 個** |

ルータースクリプトがコマンド内容に応じて適切なチェックスクリプトに委譲するため、検証機能は完全に維持される。

## セッション再開バグ防御（CC-BUG-08 補強）

### 問題（2026-03-23 発生）

大規模プロジェクトのセッション再開時、ユーザー入力ゼロで出力トークン 652,069 が生成された事例。
本プロジェクトはルールファイル ~19K トークン（最適化後）を持つが、スキル SKILL.md を含めると依然として大規模。

### 既存の防御策（有効性確認済み）

- ✅ セッション再開に依存しない設計（Git + Issue コメントが権威ソース）
- ✅ PostCompact / Stop フックで自動コミット
- ✅ 「大きなセッション（50+ ターン）は再開せず新規セッションで開始」ルール

### 追加防御策

- Claude Code を常に最新バージョンに維持（session-start.sh で自動更新済み）
- `ccusage` でセッション再開後のトークン消費を定期監視（月次 workflow-health-check で実施）
- 異常なトークン消費（1 セッションで出力 100K+ トークン）を検知した場合、retro-try Issue を作成

## CLAUDE.md 圧縮

### 設計原則

CLAUDE.md には **全セッションで必要な判断基準と参照リンク** のみを記載する。Phase 固有の詳細仕様はルールファイルまたはスキル SKILL.md に委譲する。

### 移譲した主要セクション

> ⚠️ 以下の表の移譲先ルールファイル名は **出自プロジェクト（動画制作）の実例** 。汎用ベースには存在しないファイルもあるため、自分のプロジェクトのルール名に読み替えること。

| セクション | 移譲先 | 削減量 |
|-----------|--------|--------|
| Remotion 詳細仕様（z-index, VisualCue, 字幕, SourceCredit） | `docs/rules/remotion-rules.md` | ~106 行 <!-- refcheck:ignore --> |
| 画像生成ルール詳細 | `docs/rules/image-pipeline-rules.md` 参照 | ~12 行 <!-- refcheck:ignore --> |
| VOICEVOX 詳細 | `docs/rules/audio-pipeline-rules.md` 参照 | ~4 行 <!-- refcheck:ignore --> |
| YouTube API 詳細 | `docs/rules/youtube-scheduling-rules.md` 参照 | ~6 行 <!-- refcheck:ignore --> |
| Slack 通知詳細 | `docs/rules/slack-notification-rules.md` 参照 | ~7 行 |
| スキル配置リスト（28 行） | 各スキル SKILL.md | ~24 行 |
| **合計** | | **~159 行削減** |

## 禁止事項

- `.claude/rules/` にタスク依存のルールファイルを symlink で追加しない（`ESSENTIAL_RULES` リスト外）
- ピーク帯（JST 22:00〜翌 4:00）に長時間パイプラインをスケジュールしない
- フック数を 8 個以上に増やさない（統合ルータースクリプトを使用）
- CLAUDE.md に Phase 固有の詳細仕様を直接記載しない（ルールファイルまたは SKILL.md に委譲）
