# 補完リサーチ: ディープリサーチで空白になった 4 領域（2026-08-20 JST）

> `20260820-zero-query-discovery_deep_research.md` の敵対的検証で調査項目 3 / 5 / 6 の主張が全滅したため、
> 役割分担型 fan-out（4 並列・WebSearch/WebFetch）で補完した。本ファイルは **議論（`content/discussions/`）の入力**。
> 情報ランク: [A] 一次情報・公式・査読済み / [B] 信頼できる二次情報 / [C] 要検証。

---

## 1. AI エージェント時代の OSS 発見

### 1.1. 偽 star と被依存数の操作耐性（🔴 ミッションの中核を裏付ける）

- ICSE 2026 採択論文「Six Million (Suspected) Fake Stars on GitHub」（arXiv:2412.13459）。StarScout が 2019〜2024 の GitHub イベント全体から **約 600 万件の疑わしい偽 star / 18,617 リポジトリ / 301,000 アカウント** を検出 [A]。
- 🔴 **star を水増しされた 738 パッケージのうち 70.46% が依存パッケージ数ゼロ、77.50% が依存リポジトリ数ゼロ** [A]。→ **star は買えるが被依存数は買えない**。`project-mission.md` の「被依存数（実利用）を起点にする」という選択に実証的裏付けがある。
- 論文の提言も「star 単独を高リスク判断に使うべきでない」「サードパーティのシグナルで補完・代替せよ」[A]。
- ⚠️ ただし **AI slop リポジトリが被依存数そのものを偽装する手口を直接測定した研究は未確認**。上記は star 側の観測からの間接的傍証である。
- 出典: https://arxiv.org/html/2412.13459v2

### 1.2. AI slop の実害

- Merriam-Webster が "slop" を 2025 年の Word of the Year に選出 [B]。
- curl が 2026 年 2 月にバグバウンティを停止（通常比約 8 倍の流入・約 5 件に 1 件が実在しない脆弱性報告）。Jazzband は AI 生成スパムで維持不能となり事実上終了 [B]。
- USENIX Security 2025 の研究で、LLM のパッケージ幻覚率は **商用モデル 5.2%・OSS モデル 21.7%**、ユニークな幻覚パッケージ名 205,474 件 [A]。slopsquatting（幻覚パッケージ名の先取り登録）の実被害が 2026 年 1 月に確認 [B]。
- 出典: https://www.usenix.org/publications/loginonline/we-have-package-you-comprehensive-analysis-package-hallucinations-code / https://thenewstack.io/ai-slop-open-source/

### 1.3. MCP という「UI ではない提示面」

- **Context7**（Upstash）: `resolve-library-id` / `get-library-docs` の 2 ツールで、バージョン固有ドキュメントをエージェントへ直接供給。UI ではなく「エージェントが呼ぶ API」自体が製品 [A] https://github.com/upstash/context7
- **Socket MCP**（Socket.dev）: パッケージのセキュリティスコアを MCP 経由で提供。ホスト版（OAuth・キー不要）とセルフホストの両方 [A] https://socket.dev/blog/socket-mcp
- Microsoft NuGet / WinGet / Homebrew が公式 MCP サーバーを提供開始 [B]。公式 **MCP Registry**（Linux Foundation 傘下）が 2025-09-08 にプレビュー公開 [A] https://modelcontextprotocol.io/registry/about
- ⚠️ npm 社自身の公式 MCP サーバーは **未確認**（サードパーティ製のみ確認）。

### 1.4. 未確認

- 「AI エージェントがライブラリ選定を代行する割合」の定量調査（Stack Overflow / JetBrains / Octoverse いずれにも該当設問が見つからず）。
- Octoverse 2025 の確定値: 開発者 1.8 億人・リポジトリ 6.3 億件（前年比 +25%）[A]。ただし発見経路の内訳データは無い。

---

## 2. DB レス・ログイン不要のパーソナライズ

### 2.1. 🔴 Safari ITP の 7 日キャップ（設計を左右する制約）

- WebKit 公式ブログの逐語 [A]: *"deleting all of a website's script-writable storage after seven days of Safari use without user interaction on the site"*
- 対象は **IndexedDB・localStorage・sessionStorage・Service Worker 登録/キャッシュ** を含む「スクリプトが書き込めるすべてのストレージ」。
- カウント基準は「Safari の使用日数」。**該当サイトでのユーザー操作でリセットされる**。ホーム画面に追加した Web アプリは対象外。
- 出典: https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- 🔴 **含意**: localStorage だけに依存した「前回訪問からの差分」は、**週 1 未満のアクセス頻度の Safari ユーザーでは機能しない**。「リマインド」を localStorage に乗せるなら、この穴を塞ぐ設計（URL 共有・ブックマーク導線・RSS 等）とセットにする必要がある。

### 2.2. クライアント完結のファイル解析 UX（前例あり）

- **npmgraph**（https://github.com/npmgraph/npmgraph）: `package.json` を貼り付け / ドロップすると `FileReader` でブラウザ内のみ解析。**カスタム情報は URL ハッシュに JSON エンコードして保持** し、共有はハッシュ付き URL で完結（サーバー送信なし）[B]。
- 同種のクライアント完結ツールが複数実在し、共通の訴求パターンは ① "never leaves your browser" 系の明示コピー ② 技術的根拠の明記（FileReader / JSON.parse）③ **DevTools の Network タブで検証できると読者に促す** [C]。
- 「データは外に出ません」は使い古された主張で実際に検証されないことも多い、という批判も存在 [C]。→ **検証可能性そのものが訴求材料になる**。

### 2.3. 決定論的シードによる静的 JSON の並べ替え

- 日付を `YYYYMMDD` 等にフォーマットしてシード化すれば、同じ日は全員・全レンダリング経路で同じ並びを再現できる（`seedrandom` 等）[C]。
- Cloudflare Workers Free は 10ms CPU/リクエスト。**ネットワーク待ちは CPU time に計上されない** が、大きな JSON パースや重いループは容易に上限を超える [B]。
- 🔵 **含意**: 並べ替え・絞り込みの計算は **クライアント側で行い、Worker は静的 JSON 配信 + エッジキャッシュに徹する** 設計が安全。
- ⚠️ 「静的 JSON + 決定論的シード + クライアント再ランキング」を明示的に組み合わせた実践事例は **未発見**（要素技術は個別に確認できた）。

### 2.4. プライバシー訴求の言い回し

- Plausible Analytics 公式サイトの実コピー [A]: *"No cookies, just insights." / "No cookie banner required" / "No cookies, no persistent identifiers, no cross-site or cross-device tracking"*
- ⚠️ Kagi は **アカウント必須**（検索履歴を Kagi 側が保持）で、本プロジェクトの「ログイン不要」とは前提が違う [C]。

---

## 3. 独自スコアの提示 UI と枯渇問題

### 3.1. スコア提示の主流は「単一値 + 多軸内訳」の 2 層

- **Snyk**: 総合スコア（例 89/100）+ Security / Popularity / Maintenance / Community の 4 カテゴリを **状態文と生データで併記**（"114,903,004 downloads a week" 等）[B]。
- **Socket.dev**: 5 カテゴリの重み付き平均。正規化関数・指数減衰・γ 補正でスコアを圧縮する設計を公式ドキュメントで開示 [A] https://docs.socket.dev/docs/package-scores
- **OpenSSF Scorecard**: 18 種のチェックを 0-10 点で出し加重平均。公式ビジュアライザは **レーダーチャート** でチェック単位の内訳を強調 [A]。
- 🔵 **説明可能性**: Explainable Recommendation は透明性・信頼・満足度を有意に高めることが実証されている [A] arXiv:1804.11192。ただし「説明があれば常に良い判断を助ける」わけではなく、**トラストキャリブレーションの誤り**（説明に釣られて非合理的に同意する）も報告されている [A] PMC8327305。

### 3.2. gaming への対処

- Socket.dev はソフトキャップ（0.25 で頭打ち）と γ 指数によるスコア圧縮で人為的操作の影響を緩和 [A]。同社ドキュメントは「実運用と文書が完全一致する保証はない」と自認。
- Goodhart の法則への定石は **単一指標への最適化圧力を分散させる**（複合指標・非公開の重み付け・敵対的シグナルの併用）[B]。
- 🔵 gem-hunter が「被依存数（star より操作コストが高いシグナル）」を主軸に据える設計自体が、StarScout 論文の提言・Socket.dev の設計思想の双方と整合する。→ 初期段階で追加の anti-gaming ロジックは不要（YAGNI）。

### 3.3. 🔴 この領域の製品は続いていない（運用コストが生死を分ける）

- **Openbase**: 2023-04-24 に **正式終了**（YC S20 出身・多メトリクス提示型）[B]。終了理由の一次情報は未取得。
- **npms.io**: 公式リポジトリの Issue で 2023-07-15 時点「スコア算出日が 2023-01-13 のまま半年更新されず」と報告され、メンテナ返信なしで放置 [A] https://github.com/npms-io/npms-api/issues/112 → **実質的な更新停止**。
- **Libraries.io**: 継続中だが Tidelift 買収 → Sonar 買収と運営母体が転々 [B]。
- 🔵 **含意**: 独立系ディスカバリー製品は「作れるか」より「**運用が続くか**」で死ぬ。静的事前計算・OpenSSF 依存という本プロジェクトの低運用コスト設計は、この教訓への構造的な回答になっている。

### 3.4. GitHub Trending / Explore の問題点

- アルゴリズム非公開。「star 数だけを見るため、バイラルな 1 ツイートで未完成プロジェクトが上位に来る一方、毎日 30 人がコミットする活発なプロジェクトが全く出てこない」という批判 [B]。
- 2024-11-13 以降、データパイプライン障害で **Trending の更新が停止** した事象（GitHub 公式コミュニティディスカッション）[A] https://github.com/orgs/community/discussions/179946
- Trending データは公式 API に **含まれていない**（長年の要望あり）[B]。
- 代替の試み: Krihelinator（貢献速度でランク付け）/ Y-Cloninator（HN の議論量で再ランク）/ trending-plus [C]。

### 3.5. 枯渇問題への対処（一次情報は薄い）

- **Console.dev** は稼働継続中で、**明文化された選定基準ページ**（console.dev/selection-criteria）を公開 [B]。
- Product Hunt は 2025 年時点で「AI プロダクトの氾濫」「似たツールばかりで発見の楽しさが薄れた」という倦怠感が報告され、運営は「ホームページ掲載をより厳選」する方向で対応 [B]。
- Hacker News は URL ベースの重複検出 + 「十分話題にならなかった記事は時間を置けば再投稿可」という時間減衰的な緩和ルール [B]。
- ⚠️ JavaScript Weekly / TLDR 等の内部プロセス（候補プール規模・ローテーション方式）の一次情報は **未発見**。

---

## 4. データ源の一次確認（🔴 実現可能性の分かれ目が解決した）

### 4.1. Ecosyste.ms のライセンス（公式ドキュメントの逐語）

出典: https://docs.ecosyste.ms/docs/usage/licences/ [A]

> "ecosyste.ms is licensed in such a way that both the data and code are free to use in any capacity, including commercially, so long as ecosyste.ms is attributed, and that a compatible licence is used for publicly accessible works."
>
> **Data**: "Our data is licenced using the Creative Commons Attribution Sharealike Licence. […] you must give appropriate credit to ecosyste.ms as a source, link to the licence, and indicate if any modifications were made to the data. **Importantly, the above applies if you include 'all or a substantial portion' of ecosyste.ms data alongside data for which you have 'sui generis' database rights.**"
>
> **Code**: AGPL v3。

- `packages` リポジトリ README にも「Data from the API is licensed under CC BY-SA 4.0.」と明記 [A]。
- 🔴 **判定**: PRD `GR-6` の前提「データは CC BY-SA 4.0」は **正しい**（ディープリサーチ側が棄却したのは検証不足だった）。ShareAlike の継承条件は「全部または相当部分 + sui generis database rights」に紐づき、**公式は数値的な線引きを示していない**。保守的には UI に「Data via Ecosyste.ms（CC BY-SA 4.0）+ ライセンスへのリンク + 改変の明示」が必須。
- 商用ライセンス（より緩い条件）は有償で提供されている。

### 4.2. 🔴 S3 バルクダンプが存在する（1,400 万件走査問題の解決）

出典: https://packages.ecosyste.ms/open-data [A]

- "Open Data Releases" として **AWS S3 で tar.gz を配布**（`https://ecosystems-data.s3.amazonaws.com/packages-[DATE].tar.gz`）。
- 直近リリースは 2026-02-05 時点で **約 1,310 万パッケージ** 収録。2022 年 8 月以降、概ね **2〜4 ヶ月おき** に更新。ライセンスは CC BY-SA。
- ⚠️ ダンプに `dependent_packages_count` / `rankings` 等の **集計フィールドが含まれるかは未検証**（ページ説明は「package, version and dependency metadata」とのみ）。実装前に実ファイル検証が要る。

### 4.3. レート制限・認証

- 無認証（common pool）**5,000 req/時**。User-Agent か `mailto` クエリに email を入れる（polite pool）と **15,000 req/時** [A]（作者 Andrew Nesbitt のブログ + 公式 docs で一致）。
- 参照系 API に **API キーは不要**。一部 API のみ有料認証ユーザー限定。

### 4.4. 🔵 リポジトリ ↔ パッケージの対応付けは API で提供済み

- パッケージ側に `repository_url`（repos.ecosyste.ms へのリンク）、リポジトリ側に `purl`（例 `pkg:npm/lodash`）が入っており **双方向に引ける** [A]（実 API レスポンスで確認）。
- 🔵 **含意**: PRD §11 が「Phase 2 の中核課題」に挙げた **名前解決の負担が大幅に軽くなる**（モノレポ等の例外処理は残る）。

### 4.5. 被依存数のフィールド（実レスポンスで確認）

`dependent_packages_count` / `dependent_repos_count` / `docker_dependents_count` がパッケージオブジェクトに直接存在。加えて `rankings`（downloads / dependent_repos_count / stargazers_count 等のパーセンタイル値と average）も返る [A]。一覧 API の `sort` パラメータでこれらを指定可能。
⚠️ 各フィールドの公式な定義文（doc string）は OpenAPI に **存在しない**。

### 4.6. OpenSSF

- **Scorecard**: 公式 README に「public BigQuery dataset `openssf:scorecardcron.scorecard-v2`」「REST API は `https://api.scorecard.dev`」と明記。週次スキャン対象は **"1 million most critical open source projects"** 規模。週次スキャンは API コストの都合で **CI-Tests / Contributors / Dependency-Update-Tool の 3 チェックを省略** [A]。リポジトリは活発（最終 push 2026-08-19）。
- **criticality_score**: BigQuery `openssf.criticality_score_cron.criticality-score-v0-latest` + GCS の CSV。**GitHub 限定**。リポジトリは archived ではないが **最終 push が 2025-12-02（約 8.5 ヶ月前）で活動低調** [A]。cron が現在も回っているかは **未確認** → 依存するなら実データの鮮度検証が必須。

### 4.7. GitHub 側の再配布制約

- GitHub ToS Section H / AUP を確認した範囲で、**取得した公開メタデータをランキング表示として再配布することを明示的に禁じる条項は無い** [A]。制約は「スパム目的でない」「レート制限を尊重する」「個人情報を販売しない」が中心。AUP は "Scraping does not refer to the collection of information through our API." と明記。

---

## 5. この補完リサーチで解決した / 残った論点

| 論点 | 状態 |
|---|---|
| Ecosyste.ms のライセンスと帰属義務 | ✅ 解決（CC BY-SA 4.0・出典表示必須。ShareAlike の線引きは保守的解釈） |
| 1,400 万件をどう harvest するか | ✅ 解決（S3 バルクダンプ・2〜4 ヶ月毎） |
| リポジトリ ↔ パッケージの名前解決 | ✅ 大幅緩和（API が双方向に提供） |
| OpenSSF の入手経路と対象規模 | ✅ 解決（Scorecard は 100 万件規模・REST API 利用可 / criticality_score は鮮度要検証） |
| 被依存数の操作耐性 | ✅ 実証的裏付けあり（間接） |
| localStorage による「リマインド」の耐久性 | ⚠️ Safari ITP 7 日キャップという上限が判明 |
| 静的 JSON + 決定論的シードの実践事例 | ❌ 未発見（要素技術のみ） |
| 枯渇問題への具体的対処 | ❌ 一次情報が薄い（Console.dev の選定基準公開のみ） |
| S3 ダンプに集計フィールドが含まれるか | ❌ 未検証（実装前に要確認） |
