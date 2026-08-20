<!--entry
author: backlog_hygiene
round: 1
kind: claim
ts: 2026-08-20T09:28:00+09:00
-->

## backlog_hygiene: 争点B（Epic化の粒度）・E（取りこぼし/レーン侵犯）を主担当

### 争点E から先に出す（B の前提になる構造問題を発見したため）

**最重要指摘: 今回の棚卸し対象そのものが `improvement-lane-map.md` の Rule 2（`type:retro-try` は振り返りレーンの専管・#160）に触れる境界事例である。**

`improvement-lane-map.md` §2 Rule 2「対象が `type:retro-try`（振り返り由来の Try）→ **振り返りレーン**（改善 Issue レーンは扱わない・#160）」、および `self-improvement-loop/SKILL.md` の他レーン境界節「`type:retro-try` は振り返りレーン（`retrospective` → `retro-try-handler`）の担当。本スキルの消化モードは扱わない（奪い合い防止・#160）」を確認した。一方で `retro-try-handler/SKILL.md` を実際に Read したところ、実行フローは Step0（ブランチ作成）→ Step1（取得・ソート）→ Step2（分類）→ Step3（small/medium 実装）→ Step4-6（PR・マージ・サマリー）のみで、**重複統合・Epic 化・優先度再査定に相当するステップが一切存在しない**。つまり「似たものはマージ、優先度設定、トリアージする」というユーザー原文の指示を実現できる既存スキルは、振り返りレーン側に無い。

結論として、本セッションが `self-improvement-loop` の Step G-3/G-4/G-6 の **判断ロジックを借用** しつつ `type:retro-try` を対象に直接棚卸しを行うのは、①ユーザーの明示指示（CP-1「自律的判断」+ `user-instruction-issue-rules.md` の指示分類）に基づく **単発の直接対応** であり、②`self-improvement-loop` スキル自体の自動発火（発見/整理/消化スロット）を `type:retro-try` に向けているわけではない、という点で Rule 2 の禁止（自動化されたレーン奪い合い防止）には抵触しないと判断する。ただし、これを **この場限りの例外として明示せず** 今後も同様のことを繰り返すと、#160 の決定がなし崩しになる。したがって verdict の `critical` または `open_questions` に **「retro-try-handler に棚卸し相当のステップ（重複統合・Epic化・優先度再査定）を追加すべきか、それとも棚卸しは今後も改善 Issue レーンへの単発委任で良いのかを次の改善 Issue として起票し検討する」** を明記することを提案する。ここで判断を打ち切らず先送りにするのは、`improvement-lane-map.md` §4 の「境界の変更は本ファイルを先に更新し、各 SKILL.md は参照 1 行に留める」という手続きを、今回の議論の verdict だけで済ませてはならないため。

**孤児化リスクの具体的指摘（B と直結）**: `self-improvement-loop/SKILL.md` Step G-4 は「Epic 自体に `type:improvement` ＋（@owner 判断で）`priority:` / `sp:` を付与」と規定している。しかし今回作る Epic の子はすべて `type:retro-try` である。Epic に文言通り `type:improvement` を付けると、`improvement-lane-map.md` §2 Rule 1「`type:improvement` が典型だが type では絞らない…除外するのは `type:retro-try` と `SP-n` のみ」に従い、この Epic は **改善 Issue レーン（消化モード）に拾われてしまう**。しかし Epic の子は全員 `type:retro-try` で振り返りレーンの専管物であり、改善 Issue レーンの消化モードがこの Epic を「実装対象」として選んでしまうのは Rule 2 違反そのものである。逆に Epic に何もラベルを付けなければ、`retro-try-handler` Step 1 の `labels: ["type:retro-try"]` 取得にも `self-improvement-loop` 消化モードの `status:waiting-claude` 取得にも拾われず、**「どのレーンも拾わない孤児 Issue」** になる。

→ 提案: 今回作る Epic には `type:retro-try` を付与する（G-4 の文言をそのまま適用しない、明示的な逸脱）。これにより Epic は `retro-try-handler` Step 1-A の取得対象に留まり、子 Issue のクローズなし運用（G-4「子 Issue はクローズせず残す」）とも整合する。この逸脱理由を Epic 本文に 1 行明記すること。

### 争点B（Epic 化の粒度）

`self-improvement-loop/SKILL.md` Step G-4「`epic_candidates`（同一カテゴリ集中）について追跡 Epic を自動生成する」と、Step G-1 の記述「Epic 統合候補（同一カテゴリに `--epic-threshold`〔既定 6〕件以上集中）」を根拠に、**閾値 6 件を機械的な足切り線として使う**。争点 A の統合結果（process_skeptic・app_quality の技術判断待ちだが、backlog 構造の立場からは #130+#139 のみ merge を支持し、#100+#110・#85+#93・#129+#136・#117+#124 は "切り口が違う" として link_only を支持する。理由は後述）を反映した後のカテゴリ件数は以下の通り:

- **machine-check: 8 件**（#69 #70 #101 #104 #109 #116 #130 #134。#139 は #130 に吸収してクローズ）→ **6 件超なので Epic 化する**
- **parallel-safety: 8 件**（#85 #91 #93 #94 #99 #103 #112 #138）→ **6 件超なので Epic 化する**（争点 C で #138 が drop されても 7 件で依然として閾値超）
- **preview-ops: 4 件**（#100 #110 #117 #124）→ 閾値未満、**Epic 化しない**
- **review-quality: 4 件**（#68 #111 #123 #137）→ 閾値未満、**Epic 化しない**（#137 が drop されれば 3 件でなお下）
- **doc-record: 5 件**（#102 #115 #129 #136 #146）→ 閾値未満、**Epic 化しない**（6 件目に届かない。ここを無理に束ねると「追跡単位が増えて逆に見通しが悪くなる」というブリーフ自身の懸念に抵触する）
- **app: 3 件**（#92 #125 #135）→ Epic 化しない
- **other: 4 件**（#84 #86 #118 #131）→ **これは「カテゴリ」ではなく分類漏れの残余集合** である点を明記したい。G-4 は「同一カテゴリに集中」が前提条件であり、内容がバラバラな other を Epic化すると、後から見た人が「このEpicは何を束ねているのか」を理解できなくなる。**other は Epic 化候補から除外し、各 Issue を個別に争点 C（やめる/取り組む/保留）で処理すべき**。

したがって B の確定案: **Epic を作るのは machine-check と parallel-safety の 2 本のみ**。preview-ops・review-quality・doc-record・app・other は現状の件数では束ねず、`link_only`（相互リンク）または個別処理に留める。これは `session-sprint-rules.md` §2 の「リファインメント（`self-improvement-loop` 整理モード）: 議論型 `discussion-review`」の運用コストにも見合う——Epic を 2 本に絞ることで @owner が priority/sp を判断する対象も 2 Epic + 非 Epic 個票に整理され、消化モードの選択順（priority 降順 → sp 昇順）が機能する状態を保てる。

### 争点A（統合候補・backlog 構造の観点から）

`self-improvement-loop/SKILL.md` Step G-3 の境界「自律クローズの境界: 内容の同一性に確信が持てる場合のみ。少しでも切り口が異なれば残す（消し過ぎより取りこぼしを許容）」を判断基準に、5 候補を個別に見る:

- **#100 + #110**: #110 本文が「#100 と役割が近く着手時に統合可否を判断する」と **自ら保留** している。#100 は「疎通・ステータスの自動検証」、#110 は「デプロイを1コマンドに束ねる」で、前者は検証、後者はデプロイ手順の統合と役割が異なる。確信度が低いため **merge ではなく link_only** を支持する。
- **#85 + #93**: 「一括整形ツールが並行編集中ファイルを巻き込む」（フォーマッタというツールのスコープ）と「並行実行中の破壊的 git 操作の禁止」（git 操作というレイヤ）は防ぐ対象の技術的な層が異なる。**link_only** を支持する。
- **#130 + #139**: 「domain-model.md の語彙変換表と実装命名の整合検査」と「ドキュメントのコード例示と実装の乖離検査」はどちらも「ドキュメント記述 vs 実装の乖離を機械検査する」という同一の検査ツール拡張の話であり、machine-check カテゴリの中でも特に切り口が重なる。**merge を支持**（技術的にワンツールで両方カバーできるかは process_skeptic / app_quality の判断を仰ぐ）。
- **#129 + #136**: 「GitHub API の nullable フィールド一覧を書く」と「選択肢依存の計算値ハードコード禁止をルール化する」はブリーフ自身が言う通り「同一節周辺を触る」だけで、扱う知見の中身は別物（データ形状の記録 vs コーディング規律）。同じファイルを触るというだけで統合すると、後から片方の知見だけ検索性が落ちる。**link_only** を支持する。
- **#117 + #124**: 「Cloudflare レート制限で止めない」（インフラ運用のガード）と「プレビュー動作実測の手順化・PR チェックリスト化」（ドキュメント/プロセス）は問題領域が異なる。**link_only** を支持する。

### 争点C・D（主担当外だが所感）

C は mission_po の CP-5 貢献度判定が主導すべきだが、backlog 構造の立場から 1 点補足する: `self-improvement-loop/SKILL.md` の G-6 出口表にある通り「やめる」は `state_reason="not_planned"` によるクローズで **再オープン可能**（可逆）。したがって「消しすぎ」の被害は限定的であり、#137 #138 #118 #131 のような検討・計測系は疑わしければ積極的に drop してよい、というのが構造面からの後押しになる。

D については、`priority:high` が 13 件残っている状態は消化モードの選択順（`self-improvement-loop/SKILL.md` 消化モード Step1「priority ラベル順（high → medium → なし → low）でソート」）を事実上無効化する。high の定義が緩いと「high 内で何を先にやるか」が結局 createdAt 頼みになり、優先度ラベルが機能しなくなる。B で Epic 化する machine-check・parallel-safety の子 Issue は、Epic 化後は「Epic 自体の priority/sp」で代表させ、子個々の priority は @owner の再査定時に high を絞る方向を支持する（個票が high のまま残ると、Epic とバラで二重にhigh対象が積み上がる）。

### まとめ（Issue番号を明示した結論)
- Epic化する: machine-check（#69 #70 #101 #104 #109 #116 #130 #134）/ parallel-safety（#85 #91 #93 #94 #99 #103 #112 #138）の2本のみ。Epic ラベルは `type:improvement` ではなく **`type:retro-try`** を付与する（レーン孤児化防止）。
- Epic化しない: preview-ops（#100 #110 #117 #124）/ review-quality（#68 #111 #123 #137）/ doc-record（#102 #115 #129 #136 #146）/ app（#92 #125 #135）/ other（#84 #86 #118 #131）。
- merge支持: #130+#139 のみ。
- link_only支持: #100+#110 / #85+#93 / #129+#136 / #117+#124。
- open_questions への追記提案: 「retro-try-handler に棚卸し（重複統合・Epic化・優先度再査定）ステップを追加すべきか」を次の改善 Issue として起票し検討する。
