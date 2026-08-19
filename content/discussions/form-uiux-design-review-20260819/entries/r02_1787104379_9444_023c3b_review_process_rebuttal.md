<!--entry
author: review_process
round: 2
kind: rebuttal
ts: 2026-08-19T10:52:58+09:00
-->

## review_process — Round 2 rebuttal / concession

### 1. ux_standards §2.4 への「参照の書式」を具体化する（rebuttal 兼・自分の提案の精緻化）

ux_standards の §2.4 案（🔴必須／🔵推奨の二層構造・トークン表）を前提に、code-review Step1 の UI 行と Step7 4点目の文言を以下に確定する。**基準の実体（px 値・トークン名）は書かず、「どの区分（必須/推奨）に当てはめて severity を決めるか」という判定ルールだけを書く**ことで参照を保つ。

- **code-review Step1「UI・アクセシビリティ」行の焦点列**（確定文言）:
  「`docs/03_design/ui-ux/ui-ux-guidelines.md` §2.4 を実際に Read してから判定する（本文に埋め込まれた値を訓練データから推測しない・L-113）。🔴必須行の逸脱＝`severity: CRITICAL`、🔵推奨行の逸脱＝`severity: WARNING` 以下。§2.4 に該当行がない新規コントロールへの言及は `severity: NIT`（規定不在の指摘であって違反ではない）」
- **Step7 受け入れ判定役 4点目**（確定文言）:
  「UI/デザイン変更を含む場合、`ui-ux-guidelines.md` §2.4 を実際に開いて 🔴必須行を満たすか判定する（『たぶん満たしている』を書かない＝既存2点目と同型の実行原則）。🔵推奨行の逸脱は Problem として記録し次スプリントへ送る（ブロックしない）」

これにより「severity/ブロック要否の決定ロジック」だけがスキル側にあり、**数値の実体は §2.4 の 1 箇所のみ**（ux_standards claim: L52-70）。

### 2. guardrail_eng の機械検査との境界（rebuttal・自分の Round1 案を修正）

**concession**: Round1 の私の提案は焦点列を「寸法・タイポスケール・ターゲットサイズ等に照らして判定」と書いたが、これは guardrail_eng の `check_ui_dimensions.py`（button.tsx/input.tsx の cva size テーブルの🔴必須フロア値検査・Error・run_checks.sh 統合。guardrail_eng claim: L21-31）と **完全に重複する**。同じ違反を機械が Error で止め、かつレビューが指摘するのは二重ゲートであり無駄なノイズになる。**Round1 の文言を撤回し、以下に絞る**。

**境界の確定**:
| 主体 | 対象 | 根拠 |
|---|---|---|
| 機械検査（`check_ui_dimensions.py`） | `button.tsx`/`input.tsx` の cva `size` テーブルの静的文字列に現れる🔴必須フロア値のみ | guardrail_eng claim L25-29（対象2〜3ファイル・静的文字列限定） |
| レビュー（code-review Step1 / Step7 4点目） | 機械検査の構造的な射程外のみ: ① §2.4 に未登録の新規コンポーネント（レジストリに無いためチェッカーが黙って PASS する対象＝guardrail_eng claim L15「対象ゼロなら黙ってPASS」の裏返し）、② 動的 className 合成・`md:` 出し分け・任意値（guardrail_eng claim L27 (a)-(d) で明示的にスキャン対象外とされたもの）、③ 🔵推奨行の逸脱（機械検査は🔴必須のみ Error 化・guardrail_eng claim L29「それ以外は今回追加しない」）、④ 選んだ variant/トークンが情報設計上妥当か（例: この操作が本当に主役として `--size-control-lg` を使うべき導線か。これは px 比較でなく設計判断） | 本節の切り分け |

**焦点列の再確定文言**: 「`check_ui_dimensions.py`（run_checks.sh の Error 検査）が既に検査済みの `button.tsx`/`input.tsx` の🔴必須フロア値は **指摘しない**（二重指摘禁止）。レビューが見るのは、機械検査の対象外（未登録の新規コンポーネント・動的 className 合成・🔵推奨行の逸脱・トークン選択の設計妥当性）に限る」

### 3. Layer 1 前倒しの価値は残るか（Round1 結論の維持・ただしスコープを再定義）

**Round1 結論「①を採る」は維持する。ただし価値の中身は差し替える。** guardrail_eng の静的検査が入ることで「既存の登録済みコンポーネントの数値フロア割れ」は機械が完全にカバーするため、Layer1 レビューがそこを担う必要は消えた（これが上記2の concession）。しかし残る領域がある:

1. **未登録コンポーネントの穴**（今回の欠陥そのものの再演リスク）: 今回の欠陥は「§2.4 が存在しない時点で input.tsx/button.tsx が作られた」ために起きた。同じことは SP-2 以降で新規プリミティブが追加されるたびに起こりうる。静的検査は `check_ui_dimensions.py` のレジストリに手動で追加されるまで対象外（guardrail_eng claim L15 のスキップ思想どおり）。**Layer1 レビューの役目は「この PR が新規の UI プリミティブを追加したなら、`check_ui_dimensions.py` のレジストリ対象に追加されているか」を確認するメタチェックに絞る**。これは静的検査自体では検出不能（自分のスコープ外を自分では気づけない）。
2. **🔵推奨行・設計判断**: ux_standards claim L67-69 の「推奨（`--size-control-md`/`lg` の高さ目安）」は機械の Error 対象外。ここは人間相当の判断が要る。
3. **動的 className・`md:` 出し分け**: guardrail_eng claim L27 が明示的にスキャン対象外とした領域（`search-form.tsx` のような合成箇所）は依然としてレビューでしか拾えない。

→ **前倒しの価値は「機械が既に守っている数値フロア」ではなく「機械が構造的に守れない3領域」に残る。** guardrail_eng の静的検査導入は Layer1 UI 観点を不要にするのではなく、**スコープを重複部分から外して縮小する**（コストはむしろ下がる: 焦点が絞られファインダーの誤検知余地も減る）。

### 4. docs_trace の指摘との突合・書き換え要否の確定

- docs_trace「`.claude/skills/` 配下: 該当ファイルなし（UI/a11y 専門スキル不在）」（docs_trace evidence L74-75）→ 本提案が着地すると **この行は陳腐化する**（`code-review/SKILL.md` と `pr-review-watcher/SKILL.md` の2ファイルに UI/a11y 言及が新設されるため）。ただし docs_trace の Round1 評価そのものは正しい（提案前時点の事実）。**書き換えが必要なのはこの2ファイルのみ**で、docs_trace が挙げた他の言及箇所（`sprint-development-rules.md` / `testing-strategy.md` / `user-story-map.md`）には触れない。
- docs_trace「SD-2 と E2E 基盤の乖離（SP-1〜SP-3 は Playwright 無し）」（docs_trace evidence L88-115）→ **本提案のスコープ外**。guardrail_eng が Playwright 導入を別 Issue に切り出す判断（guardrail_eng claim L41-43）と整合し、`sprint-development-rules.md` 自身が SP-1〜SP-3 を例外として明記済み（同ファイル内で自己無矛盾）なので書き換え不要。
- docs_trace「SSOT が複数に分散（ガイドライン・テスト戦略・ユーザーストーリーマップの3所）」（docs_trace evidence L124）→ これは **E2E 導入タイミングの分散**であり、デザイン判定基準の分散ではない。デザイン判定基準は ux_standards 案どおり `ui-ux-guidelines.md` §2.4 に一本化されるため、本提案が新たな分散を生むことはない。`testing-strategy.md` / `user-story-map.md` の書き換えは本提案の射程外（テスト基盤タイミングの決定は別レーン）。

### 結論（Round2 で確定した変更点）

- 書き換えファイルは Round1 と同じ2つ（`.claude/skills/code-review/SKILL.md` Step1 表 / `.claude/skills/pr-review-watcher/SKILL.md` Step7 受け入れ判定役4点目）だが、**両方とも「§2.4 を Read してから必須/推奨で severity を分ける」形に文言を確定**し、**guardrail_eng の機械検査と重複する数値フロア判定は明示的に除外**する。
- 新規ファイル・新規 SSOT は増えない（Round1 の結論を維持）。
