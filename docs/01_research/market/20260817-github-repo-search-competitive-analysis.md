# GitHub パブリックリポジトリ検索プロダクト — 競合調査とホワイトスペース分析（2026年8月時点）

## TL;DR

- 「 セマンティック検索精度 × データ拡充（ 品質・依存・活性度 ）」の交差点はまだ誰も本気で埋めていない最大のホワイトスペースであり、特に「 AIエージェント/MCP が自律的にライブラリを選定するための構造化された信頼シグナル API 」が最有望。純粋なコード検索（ GitHub Blackbird ）とドキュメント化（ DeepWiki ）と品質評価（ Scorecard/Socket ）が別々に存在するが、それらを統合して「 エージェントが選定判断に使える単一の検索・スコアリング層 」は空白。
- 技術的にはコーパス全体の埋め込み生成コストは意外に安い（ DeepWiki 相当の 4B 行 ≒ 約320億トークンでも text-embedding-3-small なら数百ドル規模 ）。真のコスト・参入障壁は GitHub Search API の 1000件制限・レート制限、ベクトルDBの保管/クエリコスト、そして継続的な鮮度維持にある。
- 収益化は「 MCP/API 従量課金 」が最も筋が良い。Exa（ AI向け検索API、2026年5月20日に a16z 主導で $2.2B 評価・$250M Series C を調達 ）、Context7（ LLM向けドキュメント配信 ）が先行事例。シート課金の SCA/コードレビュー（ Snyk、Socket、Greptile ）は市場が大きいが差別化軸が「 検索精度 」ではない。

## Key Findings

1. **GitHub 純正が「発見（ discovery ）」を埋めていない**。Blackbird は世界最高峰の完全一致/正規表現コード検索エンジン（ Rust製、180M+リポジトリ・480TB超をインデックス ）だが、これは「 既知の文字列を探す 」ためのもので、「 良いライブラリを見つける 」意味的発見ではない。Search API は最大1000件・コード検索10 req/分という厳しい制約があり、サードパーティが純正の上に発見レイヤーを作る余地がある。

2. **セマンティック検索の勝者は「 Web検索API 」勢**（ Exa ）であり、リポジトリ発見に特化した専業プレイヤーは薄い。Exa は自前の埋め込みモデル+neural indexで急成長中だが、汎用Web向け。「 GitHubリポジトリの発見に特化したセマンティック検索 」はニッチとして空白。

3. **AIエージェント時代の新需要が急拡大**。MCPサーバは各ディレクトリで数万件規模に達し、Context7（ LLM向け最新ドキュメント配信 ）、DeepWiki（ リポジトリをwiki化、公開MCP無料 ）が「 LLMがリポジトリを理解する 」層を押さえた。だが「 LLMがどのライブラリを選ぶべきか 」という選定・比較レイヤーは未成熟。slopsquatting（ 幻覚パッケージによるサプライチェーン攻撃 ）という新しい脅威が、逆に「 エージェント向けの検証済みライブラリ推薦 」需要を生んでいる。Spracklen et al.『 We Have a Package for You! A Comprehensive Analysis of Package Hallucinations by Code Generating LLMs 』（ USENIX Security 2025、UTSA/オクラホマ大/バージニア工科大 ）は、16モデルによる223万コードサンプル中440,445件（ 19.7% ）が幻覚パッケージを含み、205,474個のユニークな架空パッケージ名を検出したと報告した（ OSSモデル平均21.7%、商用モデル5.2% ）。

4. **データ拡充系は豊富だが分断されている**。deps.dev（ Google ）、Ecosyste.ms、OpenSSF Scorecard、Socket.dev、Snyk、Libraries.io（ Tidelift/Sonar傘下 ）がそれぞれ依存グラフ・セキュリティ・活性度データを持つが、「 セマンティック検索の結果ランキングにこれらの信頼シグナルを統合する 」プロダクトは存在しない。star数の信頼性崩壊——He et al.『 Six Million (Suspected) Fake Stars on GitHub 』（ CMU/NC State/Socket、ICSE 2026査読済み ）が StarScout で 20TB の GHArchive データ（ 2019年7月〜2024年12月、67億イベント・3.26億star ）を分析し約600万個の偽star・18,600リポジトリ・約301,000アカウントを検出——が、代替シグナルへの需要を裏付ける。

## Details

### 1. 既存ツールの棚卸し（ カテゴリ別 ）

#### A. GitHub 純正

- **GitHub Code Search (Blackbird)**: Rust製の自前検索エンジン。GitHub公式blog『 The technology behind GitHub's new code search 』によれば 180M+リポジトリ・480TB超のソースコードをインデックスし、「 The code search index is by far the largest cluster that GitHub runs, comprising 5184 vCPUs, 40TB of RAM, and 1.25PB of backing storage, supporting a query load of 200 requests per second on average and indexing over 53 billion source files 」。約120,000ドキュメント/秒でインデックス。完全一致・正規表現・シンボル検索対応。**強み**: スケール・速度・精度で他を圧倒。**弱み**: 意味的発見（「 〜のようなライブラリ 」）は非対応。あくまで文字列/シンボル検索。
- **GitHub Search API (REST/GraphQL)**: **最大1000件/クエリ**の上限。検索は認証時30 req/分（ コード検索は10 req/分・認証必須、2023年4月変更 ）。単一PATでは本番運用が破綻するため、GitHub App化してインストールごとにレート枠を得るのが定石（ 1,000インストール ≒ 30,000 req/分 ）。**これがサードパーティ検索プロダクトの最大の技術制約**。
- **GitHub Copilot / Explore / Trending / GitHub Models**: Copilotはコード生成中心。Trendingは単純なstarベースで発見ツールとしては貧弱。GitHub Modelsはモデルカタログでリポジトリ検索とは別軸。
- **公式 GitHub MCP Server**: リモート/ローカル両対応、toolset単位で機能を有効化。エージェントからのリポジトリ操作の標準実装だが、「 発見・選定 」より「 操作 」に主眼。

#### B. OSS 探索・発見系

| プロダクト | アプローチ | 料金 | 強み | 弱み |
|---|---|---|---|---|
| Libraries.io | 32パッケージマネージャ・10M+パッケージのメタデータ集約（ スクレイピング ） | 無料 | 広範なエコシステム横断、依存数の可視化 | データ未検証・鮮度に難、UIが古い。Tidelift（ Sonar傘下 ）が運営 |
| Ecosyste.ms | オープンなAPI群（ repos/packages/advisories等 ）、Scorecard連携 | 無料/OSS | 商用フリー・API充実・依存とScorecardを統合可能 | 発見UIは弱く、開発者向けデータ基盤に近い |
| deps.dev (Google Open Source Insights) | 依存グラフ・ライセンス・Scorecard・advisory を統合API | 無料 | Google運営の信頼性、推移的依存の可視化 | 検索/発見機能ではなくルックアップ中心 |
| Sourcegraph | 公開コード検索は縮小、Enterprise Search（ $49/user/月 ）中心。Cody（ AIコード ）は2025年7月に無料/Pro終了、Enterprise専用（ $59/user/月 ）。新製品Ampへ移行、2025年12月にAmpを別会社としてスピンオフ発表 | Enterprise Search $49、Cody Enterprise $59 | 大規模コードベース横断検索の老舗 | 個人開発者向け無料層を撤退、発見用途では高価 |
| grep.app | 公開リポジトリの高速完全一致/正規表現検索 | 無料 | 軽量・高速なコード横断grep | 意味検索なし、メタデータ乏しい（ ※Vercel関連の動向は未確認 ） |
| OpenHub (Black Duck) | 古典的OSSディレクトリ | 無料 | 歴史的データ | ほぼメンテ停止状態、実質レガシー |

#### C. リポジトリ品質・活性度評価系

| プロダクト | アプローチ | 料金 | 状態 |
|---|---|---|---|
| OpenSSF Scorecard | セキュリティ健全性を18+チェックで0-10点化、REST API（ CDLA Permissive 2.0 ）。上位100万リポジトリを週次スキャン | 無料/OSS | 活発。ただしヒューリスティックで誤検知あり、全リポジトリ非対応 |
| Socket.dev | 依存パッケージの「 振る舞い解析 」でマルウェア検知（ CVEに依存しない ）。2026年5月に$1B評価で$60M Series C（ Thrive Capital ）、累計$125M。27,000+組織・1.5M repos保護 | フリー層+シート課金 | 急成長。slopsquatting対策で注目 |
| Snyk | 開発者向けセキュリティ（ SCA/SAST ）。2025年10月に$530M調達、評価$8.5B。2026推定ARR約$326M | シート課金/Enterprise | 市場リーダーだがARR成長鈍化（ 2026年2月時点で前年比7% ） |
| npms.io / npm trends / Bundlephobia / Moiva.io | パッケージ単位の品質/サイズ/トレンド比較 | 無料 | npmエコシステム限定、単一言語 |
| Openbase | パッケージレビュー（ ★評価 ） | — | **サービス終了済み**（ 2020年前後に運営停止 ） |
| StackShare / SimilarTech | 技術スタック採用状況 | フリー/有料 | リポジトリ検索ではなくツール採用調査 |

#### D. トレンド・ランキング系

- **Star History / GitStar Ranking**: star推移の可視化。単純だが定番。
- **OSS Insight (PingCAP/TiDB)**: GH Archive由来の10B+行イベントデータを分析、自然言語クエリ対応。ランキング・比較・トレンド。無料。**強み**: 深い分析。**弱み**: 発見よりアナリティクス。
- **Runa Capital ROSS Index**: GitHub star成長率（ AGR ）で急成長OSSスタートアップTop20を四半期公開。VC視点。透明性重視で単一指標（ star ）に絞る。

#### E. セマンティック/AI検索・LLM変換系

| プロダクト | アプローチ | 料金 | 状態 |
|---|---|---|---|
| Exa (旧Metaphor) | 自前埋め込みモデル+neural indexのAI向け検索API。Websets、Exa Research、Exa Fast(<425ms) | API従量課金 | 2026年5月20日に a16z（ Sarah Wang が取締役就任 ）主導で $250M Series C を $2.2B 評価で調達（ 前年秋の $700M 評価から3倍超 ）。Exa公式blog『 Exa Raises $250M Series C to Build the Search Engine for AIs 』によれば Cursor・Cognition・HubSpot・OpenRouter・Monday.com および40万人超の開発者にsearchを提供（ 顧客5,000社超 ）。汎用Web向け |
| Context7 (Upstash) | LLMに最新・バージョン別のライブラリドキュメントを配信するMCP。resolve-library-id → query-docsの2段階。30+クライアント対応 | 無料+APIキーで上限緩和 | 「 幻覚・古いコード生成 」を防ぐ層として定着 |
| DeepWiki (Cognition/Devin) | 任意の公開リポジトリをAI生成wiki化（ github.com→deepwiki.com ）。50,000+の人気リポジトリを事前インデックス。公開MCP（ ask_question等 ）無料 | 公開無料、privateはDevin課金 | 2025年5月launch。「 コードのWikipedia 」。強力な単一リポジトリ理解 |
| gitingest / Repomix / uithub | リポジトリを1つのLLM向けテキストに変換 | 無料/OSS | 「 コンテキスト供給 」ツール。検索ではなく変換 |
| Phind / Perplexity / You.com / Devv.ai | AI検索（ コード含む ） | フリー/有料 | 汎用AI検索。リポジトリ発見特化ではない |
| Bloop.ai | セマンティックコード検索 | — | ピボット/縮小したとみられる（ 要確認 ） |
| Greptile | リポジトリ全体のセマンティックグラフindex+AIコードレビュー。82%バグ検知。MCPサーバあり | $30/seat（ 2026年3月に50レビュー+$1/レビューの従量制へ変更し炎上 ） | 2025年9月に$25M Series A（ Benchmark ）、評価$180M。累計$30M。用途はコードレビュー |

#### F. AIエージェント向け（ MCPエコシステム ）

- **MCPディレクトリの規模**: Glama 72,000+サーバ、PulseMCP 18,240+、mcp.so 20,222（ 2026年4月 ）、Smithery 7,000+、公式MCP Registryは36,950（ 2026年半ば ）。急拡大中だが玉石混交で「 品質でフィルタする 」需要が発生。
- **Context7 MCP / DeepWiki MCP**: 前述。LLMにドキュメント/wikiを供給。
- **GitMCP / context8（ OSS版context7+deepwiki ）**: Tree-sitterでのAST分割、ベクトル+BM25のハイブリッド検索（ RRF融合 ）。プライベート版のニーズを示唆。

### 2. ユーザーの不満・現状の限界（ 一次情報 ）

- **star数の信頼性崩壊**: He et al.（ CMU/NC State/Socket、ICSE 2026 ）が約600万個の偽star、18,600リポジトリで検出。2024年7月ピーク時は50star超リポジトリの16.66%が偽star活動に関与。2022年以降、偽starの最大成長カテゴリはAI/LLMプロジェクト。Hacker NewsやLibraries.io作者 Andrew Nesbitt も「 starは品質でなく注目度、Facebookのlikeに近い 」と一貫して主張。実例: `debug_inspector` は25 starだが111,000+のOSSプロジェクトが依存。
- **メンテ状況が分からない**: HNで「 最終コミットが3年前で数コミット、メンテナが実質1人 」というプロジェクトを掴むリスクが繰り返し議論される。開発者は手動でcommit cadence・open/closed issue比・README/docsの質・最古〜最新コミットの期間差を確認しているが、これは自動化されていない。
- **AIエージェントの課題（ slopsquatting ）**: USENIX Security 2025論文（ 前掲、Spracklen et al. ）で16モデル・223万コードサンプルのうち19.7%（ 440,445件 ）が幻覚パッケージを含むと報告。Python幻覚パッケージの8.7%がnpmに実在（ クロスレジストリ混同 ）。実際に237リポジトリに幻覚パッケージが伝播した事例（ Charlie Eriksen ）。なお「 slopsquatting 」という語は、Andrew Nesbitt（ Libraries.io作者 ）が2025年4月に Seth Larson（ Python Software Foundation Developer-in-Residence ）との会話で命名した経緯がある。→ エージェントが「 実在し・メンテされ・安全な 」ライブラリを選ぶための検証層が必要。

### 3. 技術的制約とコスト構造

- **GitHub API制約**: Search API 最大1000件、コード検索10 req/分・認証必須（ 2023年4月変更 ）。GitHub App化でインストール単位のレート枠が定石。全数取得は不可能で、qualifier（ language/path/filename ）での絞り込みが前提。
- **代替データソース**:
  - **GH Archive**: 2011年〜の全公開イベントをBigQueryで提供。**BigQueryは$5/TBスキャン**（ 月1TB無料+初回$300クレジット ）。2017-2021の5年分クエリで約10TB処理。API不要で即クエリ可。
  - **ClickHouse GitHub dataset**: GH Archive由来3.1B+レコードを再配布（ 研究目的 ）。高速。
  - **GHTorrent**: 実質メンテ停止（ レガシー ）。GH Archiveが事実上の後継。
  - **Software Heritage**: 全ソースコードのアーカイブ。網羅性は高いがリアルタイム性・検索性は限定的。
- **埋め込み+ベクトルDBのコスト試算**（ サブエージェント調査、2026年8月時点 ）:
  - **埋め込みAPI単価（ /1M入力トークン ）**: OpenAI text-embedding-3-small $0.02（ batch $0.01 ）/ 3-large $0.13（ batch $0.065 ）/ Voyage voyage-code-4 $0.12 / Cohere embed v4 $0.12 / Google gemini-embedding-001 $0.15（ batch $0.075 ）。**10億トークンで約$20〜150**。
  - **コーパス規模の目安**: 実コードは約8トークン/行。DeepWiki相当の4B行 ≒ 約320億トークン → 3-smallで**約$640**、3-largeで**約$4,160**（ 純粋な埋め込みコストのみ ）。**→ 埋め込み自体は安い**。
  - **DeepWikiの約$300,000**（ 報道ベース、Cognition公式blogには記載なし・要注意 ）は主にLLMによるwiki生成推論コストであり埋め込みではないと推定。50,000リポジトリ事前インデックスは公式確認済み。
  - **ベクトルDB**: Pineconeサーバレス storage $0.33/GB-月（ RU/WU課金あり、10Mベクトルで約$70/月〜、100Mで$1,000-3,000+/月 ）。Turbopuffer（ Cursorが採用、オブジェクトストレージベース ）storage約$0.02/GB・$1/PBスキャン、100M-1Bベクトルで$500-2,000/月とPineconeの数分の一。**次元選択が4倍のコストレバー**（ 1536次元float32で1Mベクトル≒6GB、HNSW等で約1.5倍オーバーヘッド ）。
  - **真のコスト**: 初回埋め込みではなく、(1)継続的な鮮度維持（ 毎分230リポジトリ新規作成、10億commit/年 ）、(2)ベクトルDBのクエリ課金、(3)LLM要約/エンリッチ推論。
- **ライセンス/利用規約**: GitHub Acceptable Use Policies上、**研究目的のスクレイピングは成果物がオープンアクセスの場合のみ許可**。API経由の取得はスクレイピングに該当せず（ Section H の API Terms に従う ）。**商用検索エンジンによるスクレイピングは明示的に許可されていない**ため、API/GH Archive/Software Heritage経由が安全。各リポジトリのコード自体は個別ライセンスに従う（ 再配布・埋め込み生成の可否はライセンス依存 ）。

### 4. 市場規模・収益化

- **SCA市場**: 調査会社により大きく幅がある。2025年で$353.6M（ Research and Markets、2032年$1.2B/CAGR 18.4% ）〜$4.589B（ Market Research Future、2035年$24.45B/CAGR 18.21% ）。**推定に幅があり、定義次第**。共通するのはCAGR 18-27%の高成長。
- **AI向け検索インフラ市場**: Exaの評価が9ヶ月で$700M→$2.2Bへ3倍。Tavily（ 競合、開発者100万人超 ）が2026年2月にNebiusへ買収された（ 報道により最大$400Mまたは$275M・約98倍のレベニューマルチプルと幅があり、単一額として断定できない ）。**「 エージェント向け検索 」に資本が集中**。
- **収益化モデルの実例**:
  - **API従量課金**: Exa（ 検索API ）、Context7（ 無料+APIキーで上限緩和 ）。エージェント需要と相性最良。
  - **MCP経由**: DeepWiki（ 公開無料でDevin本体へ誘導 ）、Context7。無料MCPで裾野を広げ本体製品で収益化するファネル。
  - **シート課金**: Sourcegraph（ $49-59/user ）、Snyk、Greptile（ $30/seat、従量制移行で炎上→従量課金の受容性の低さを示す教訓 ）。
  - **フリーミアム**: Socket（ 無料Firewall→Enterprise ）。

### 5. ホワイトスペースの特定と評価

以下、優先度順に列挙。各項目に「 なぜ空白か 」と実現可能性/反撃可能性/持続性を付記。

1. **【 最有望 】エージェント向け「 ライブラリ選定 API/MCP 」＝セマンティック検索 × 信頼シグナル融合**
   - 内容: 「 PDFをパースするPythonライブラリで、活発にメンテされ、既知の重大脆弱性がなく、ライセンスが許容的なもの 」といった意図ベースのクエリに、意味検索でランキングしつつ Scorecard/Socket/deps.dev/活性度 のシグナルでリランクして返すMCP/API。
   - なぜ空白か: 各ピース（ Exa=意味検索、Scorecard/Socket=信頼、deps.dev=依存、DeepWiki=理解 ）は存在するが**統合されていない**。統合には複数データソースのETL・鮮度維持・ランキング設計という地味な工数が必要で、単に見落とされている＋中程度の技術難易度。
   - 評価: 実現可能性◎（ 既存API合成で MVP 可能 ）、反撃可能性△（ GitHubやExaが将来的に参入しうるが、彼らの主戦場ではない ）、持続性○（ データパイプラインとランキング品質が堀になる ）。slopsquatting対策として明確な課金根拠。
2. **「 メンテナンス活性度 」の予測スコア（ archived予備軍検知 ）**
   - 内容: commit cadence・issue応答時間・bus factor・contributor離脱を時系列でモデル化し「 6ヶ月以内に放置化する確率 」を提示。
   - なぜ空白か: Scorecardは現状スナップショット、活性度の**予測**は誰もやっていない。データはGH Archiveで取得可能。技術難易度は中（ 時系列ML ）。
   - 評価: 実現可能性○、反撃可能性○（ Scorecardが追随しうる ）、持続性○（ モデル精度とヒストリカルデータが堀 ）。
3. **偽star/人工的人気の検出を組み込んだランキング**
   - 内容: 研究ベースの偽star検出（ StarScout/RealStars的手法 ）を検索ランキングに統合し「 本物の採用 」で並べ替え。dependents数・実ダウンロード・多様なcontributorを重視。
   - なぜ空白か: 研究は存在するがプロダクト化が薄い。star依存の既存ツールが多い中での逆張り。
   - 評価: 実現可能性○、反撃可能性△、持続性△（ 検出はいたちごっこ ）。
4. **クロスエコシステムのセマンティック「 代替ライブラリ 」発見**
   - 内容: 「 Xの代替 」「 XのRust版 」を言語・エコシステム横断で意味検索。Moiva/npm trendsは単一言語・手動比較に留まる。
   - なぜ空白か: 言語横断の意味的マッピングが技術的に難しく（ 埋め込み空間の言語バイアス ）、データ統合コストも高い。
   - 評価: 実現可能性△、反撃可能性○、持続性○。
5. **「 このコードで使われているライブラリ 」からの逆引き発見＋健全性監査**
   - 内容: リポジトリ/コードスニペットを入力に、依存を解決し各依存の健全性・代替を提示。gitingest的な取り込み＋deps.dev的な依存解決＋Socket的な監査の統合。
   - なぜ空白か: 各ツールが分断。IDE/エージェントワークフローへの統合UXが鍵。
   - 評価: 実現可能性○、反撃可能性△（ SnykやSocketが隣接 ）、持続性○。
6. **RAG/エージェント向け「 検証済みOSSインデックス 」提供サービス**
   - 内容: 埋め込み済み・信頼スコア付きの公開OSSインデックスをAPI/データセットで提供（ 自前で埋め込みを作らないエージェント開発者向け ）。
   - なぜ空白か: 埋め込み自体は安いが、鮮度維持と信頼シグナル統合の継続運用が参入障壁。
   - 評価: 実現可能性○、反撃可能性△（ Exaが隣接 ）、持続性○（ 運用が堀 ）。
7. **MCPサーバ自体の「 品質検索 」**
   - 内容: 数万件に膨れたMCPサーバを、機能・セキュリティ・活性度で意味検索。既存ディレクトリは列挙中心。
   - なぜ空白か: MCPエコシステムが新しく、品質フィルタが未整備。
   - 評価: 実現可能性◎、反撃可能性△（ ディレクトリ各社が追随可能 ）、持続性△。
8. **ライセンス互換性を軸にした発見**
   - 内容: 「 自社のGPL回避方針に合致し、機能Xを満たすライブラリ 」をライセンス制約でフィルタしつつ意味検索。
   - なぜ空白か: ニッチでエンタープライズ寄り。deps.devがライセンスデータを持つが発見と結びついていない。
   - 評価: 実現可能性○、反撃可能性○、持続性○（ エンタープライズの粘着性 ）。

## Recommendations

**段階1（ 0-3ヶ月、MVP検証 ）**: ホワイトスペース#1（ エージェント向けライブラリ選定MCP/API ）に集中。既存API（ GitHub Search API + deps.dev + OpenSSF Scorecard + Ecosyste.ms + Socket ）を合成し、意味検索は初期はExaや埋め込みAPIで代替。**自前の全数埋め込みインデックスは作らない**（ 鮮度維持コストが重い ）。MCPサーバとして公開し無料で裾野を作る。
- 判断基準: MCP経由の週次アクティブ・エージェント呼び出し数、リランクによる選定精度の人手評価。呼び出しが月10万件を超え、かつ「 幻覚パッケージ回避率 」が明確に改善するなら次段階へ。

**段階2（ 3-9ヶ月、堀の構築 ）**: 上位N万リポジトリ（ Scorecardの上位100万相当 ）に絞って自前セマンティックインデックス＋活性度時系列DBを構築。text-embedding-3-small + Turbopuffer（ オブジェクトストレージベースでコスト最適 ）で開始。ホワイトスペース#2（ 活性度予測 ）を差別化機能として追加。
- 判断基準: クエリあたりコスト、インデックス鮮度（ 新規リポジトリの反映遅延 ）、有料API従量課金への転換率。ベクトルDBクエリコストが売上を圧迫するならTurbopufferの$1/PBスキャン設計を活用し次元削減（ 1536→768 ）を検討。

**段階3（ 9ヶ月〜、収益化拡大 ）**: API従量課金＋エンタープライズ（ ライセンス互換性フィルタ=#8、逆引き監査=#5 ）を追加。SCA市場（ CAGR 18%+ ）の周辺として、SnykやSocketが手薄な「 発見・選定 」領域でのポジションを確立。

**やめるべきこと**: シート課金の汎用コードレビュー（ Greptile/CodeRabbitがレッドオーシャン、Greptileの従量制炎上が示す価格感度 ）、star単純ランキング（ 差別化不能 ）、全公開リポジトリの網羅的埋め込み（ コスト対効果が悪く鮮度維持が地獄 ）。

## Caveats

- **市場規模データは調査会社間で数倍の開き**があり（ SCA 2025で$353.6M〜$4.6B ）、定義（ SCA単体かDevTools全体か ）に強く依存する。単一ソースを鵜呑みにせず桁感として扱うべき。
- **DeepWikiの約$300,000という指標は報道ベースでCognition公式未確認**。50,000リポジトリ事前インデックスは公式確認済み。
- **Bloop.aiの現状（ 縮小/ピボット ）、grep.appのVercel関連動向は未確認**。「 終了 」と断定せず「 要確認 」とした。
- **Tavilyの買収額は$275M〜$400Mと報道間で幅**があり確定していない。
- ベクトルDBのRU/WU単価はソース間で$2〜4.5/1M WU、$8.25〜18/1M RUと幅があり、Pinecone公式の最新料金ページで再確認が必要。
- Exa/Socket等の調達・評価額は2026年前半時点。この領域は資本流入が激しく数ヶ月で陳腐化しうる。
- GitHubの利用規約解釈（ 商用スクレイピングの可否 ）は法的助言ではない。実装前に最新のTerms/AUPと各リポジトリのライセンスを個別確認すべき。
