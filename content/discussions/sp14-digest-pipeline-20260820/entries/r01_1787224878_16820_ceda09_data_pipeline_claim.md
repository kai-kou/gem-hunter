<!--entry
author: data_pipeline
round: 1
kind: claim
ts: 2026-08-20T20:21:17+09:00
-->

## data_pipeline round1: データ取得方式とレート制限内での実現可能性

### 0. 本ラウンドで新たに実測した事実（2026-08-20・すべて生 curl / WebFetch で確認済み）

| # | 実測内容 | 結果 |
|---|---|---|
| a | `GET /api/v1/registries/npmjs.org`（レジストリ全体情報） | `packages_count: 5,760,152`（Ecosyste.ms 自身が管理する npm レジストリの母集団件数。npm 公式レプリケーションの 4,038,347 件（2026-05-15・Web 検索）より大きい＝Ecosyste.ms 側のカバレッジ／履歴込みの数） |
| b | `GET /api/v1/registries/npmjs.org/packages?sort=dependent_packages_count&order=desc&per_page=1000` | **200 OK・server-side sort + pagination が機能する**。`Link` ヘッダで next/first が返る。1 ページ（1000 件）のレスポンスサイズ実測 **135,240,498 bytes（≈135MB、1 件あたり ≈135KB）** |
| c | `GET /api/v1/registries/npmjs.org/packages/typescript` の `rankings` フィールド | `{"downloads":0.0041,"dependent_repos_count":0.0139,"dependent_packages_count":0.0,"stargazers_count":0.0505,"forks_count":0.359,"docker_downloads_count":0.0195,"average":0.0745}`。**一覧エンドポイントの各レコードにも同じ `rankings` が同梱されている**（typescript を dependents 降順で 1 位取得した際に確認） |
| d | ecosyste-ms/packages のソースコード（GitHub, `package.rb` の `load_rankings`） | `rankings[:stargazers_count] = registry.top_percentage_for(self, :stargazers_count)` のように **`registry` オブジェクト経由で計算** — **rankings は registry（= npm）単位で閉じて事前計算済み**。ADR 0014 §2.6「母集団はエコシステム内で閉じる」に整合することがソース上で確認できた |
| e | `docs.ecosyste.ms/open-data` / `packages.ecosyste.ms/open-data` を WebFetch | **Anubis**（proof-of-work 型 anti-bot）による Access Denied。JS 実行を要求する種類のブロックで、単純な GET では突破できない |
| f | `https://ecosystems-data.s3.amazonaws.com/`（バケットルート一覧） | `403 AccessDenied`（S3 標準の XML エラー。Anubis ではなく **バケットポリシーそのものが匿名 ListBucket を拒否**） |
| g | `packages-2026-{01,06,07,08}-01.tar.gz` を推測して直接 GetObject | 全て `403 AccessDenied`（`NoSuchKey` ではない＝ファイル名の当て推量ミスではなく、**匿名 GetObject 自体が拒否されている**） |
| h | `rankings` の向き（typescript で検証） | `dependent_packages_count=488,056`（実利用トップクラス）に対し `rankings.dependent_packages_count=0.0` → **値は「上位からの順位割合」で 0.0 が最上位、1.0 に近いほど下位**という向きだと推定できる（逆方向サンプルでの追検証は round2 送り） |

---

### 1. S3 バルクダンプ全量処理 vs REST API 個別呼び出し のコスト・実現可能性比較

3 方式で比較する（②は当初想定していなかったが実測 b で判明した第 3 の道）。

| 方式 | リクエスト数 | 転送量 | レート制限適合 | 判定 |
|---|---|---|---|---|
| ① S3 バルクダンプ全量処理 | 1 ファイル | 未計測（全 registry 込みで過去実績 13.1M パッケージ分、npm 単体は不明） | 無関係（S3 は Ecosyste.ms のレート制限外） | **f/g により匿名アクセス自体が拒否**され現状不成立 |
| ② REST 個別呼び出し（1 パッケージ = 1 リクエスト） | npm 5,760,152 件 | 小（1 件 ≈ 数 KB〜数十 KB） | 5,760,152 / 5,000 req/h ≈ **1,152 時間 ≈ 48 日** | **完全に非現実的**（バッチの実行時間として成立しない） |
| ③ REST **一覧エンドポイント**をページネーション（`per_page=1000`） | 5,760,152 / 1,000 ≈ **5,761 リクエスト** | **≈135MB × 5,761 ページ ≈ 778GB** | リクエスト数はほぼ 1 時間分の枠に収まる（わずかに超過するため 2 時間で分割） | **リクエスト数は現実的だが、転送量（≈778GB）が新たなボトルネック** |

**結論**: ②（個別呼び出しで全量走査）は数値上ありえない。①（S3）は現状アクセス不能（§3 参照）。③（一覧 API のページネーション）は **レート制限の観点では現実的**（リクエスト数は 5,761 で 1〜2 時間枠に収まる）が、**転送量 778GB がそのままでは重すぎる**。この転送量は `repo_metadata` / `keywords_array` / `funding_links` / `issue_metadata` 等、Gem Index の計算に不要な大きいフィールドが 1 件 ≈135KB のほとんどを占めていることが原因（実測 c の `rankings` 自体は数百バイト）。**フィールド絞り込み（`fields=` 相当のクエリパラメータの有無）を round2 で確認できれば、③の転送量は 1〜2 桁圧縮できる見込み**（未確認・要検証事項として提起する）。

---

### 2. 母集団パーセンタイル計算に必要な件数 ×レート制限 5000req/hour の整合性（数値検証）

- npm 全体の母集団件数: **Ecosyste.ms 視点で 5,760,152 件**（実測 a）。ADR 0014 §2.6 は「母集団を npm 全量で閉じて計算し、サンプリングしない」ことを不変条件としているため、この件数を割り引くことはできない。
- **自前でパーセンタイルを計算する場合**（＝母集団全件のスコアを収集してソートし直す場合）: 上記③の 5,761 リクエスト・778GB が必要件数。
- **一方、`rankings` フィールド（実測 c・d で npm 内で閉じて事前計算済みと確認）をそのまま使う場合**、自前でのパーセンタイル再計算は不要になる。この場合に必要なのは「候補として提示しうるパッケージの `rankings` を読む」ことだけであり、件数は候補プールの規模（ADR 0014 §5.3.2 の「上位数百〜数千件」）に縮小する。
  - 例: 候補プール 5,000 件を `per_page=1000` の一覧 API で取得 → **5 リクエスト**（体感ゼロコスト。5,000 req/h の 0.1%）。
  - ただし「候補プールをどう選ぶか」自体が母集団全体を見ないと決められない（後述 §3 の circularity）。

**数値としての結論**: 個別 REST 呼び出しでの母集団全量走査（48 日）は 5000req/h と整合しない。一覧 API のページネーションなら**リクエスト数としては整合する**（5,761 req ≈ 1〜2 時間）が、**転送量 778GB という別の制約が新たに発生**するため、「整合する／しない」は一次元のレート制限だけでは判定できない、という点を報告する。

---

### 3. S3 バルクダンプの bot 保護回避策、および API 経由での母集団パーセンタイル構成の具体案

**回避策の探索結果（本ラウンドで実施・すべて不成立）**:
- open-data ページは Anubis（JS 実行必須の proof-of-work 型）で保護されており、単純 HTTP GET では突破不可（実測 e）
- S3 バケットへの直接アクセス（ルート一覧・推測ファイル名への GetObject）はいずれも `AccessDenied`（実測 f/g）。これは Anubis 由来のブロックではなく **S3 バケットポリシー自体が匿名アクセスを拒否している**ため、Anubis を回避しても解決しない可能性が高い
- 本セッションには `aws` CLI が未導入で、AWS SigV4 署名済みリクエスト（`--no-sign-request` 含む）での再検証は未実施。生 curl の匿名 GET と署名済みリクエストで挙動が変わる可能性はゼロではないため、**「S3 は完全に不可能」と断定はしない**（round2 で `boto3`/`aws-cli` 導入後の再検証を推奨）

**「無ければ API 経由でどう構成するか」の具体案（本命として提案）**:

1. **`GET /registries/npmjs.org/packages?sort=dependent_packages_count&order=desc&per_page=1000&page=N` を全ページ走査**し、各レコードの `rankings.dependent_packages_count` と `rankings.stargazers_count`（npm 内で閉じて Ecosyste.ms が事前計算済み・実測 d で裏付け済み）をそのまま Gem Index の入力にする。**自前でパーセンタイルを再計算しない**（ADR 0009 §2.2「既存スコアを再実装しない」の精神とも整合）。
2. **転送量対策**: レスポンスをストリーミングパース（`ijson` 等）し、`name` / `dependent_packages_count` / `rankings` / `repository_url` 等 Gem Index に必要な数十バイト〜数百バイトだけを抽出してから残りを即破棄する。これにより **メモリ・ディスク使用量は転送バイト数（778GB）ではなく抽出後のデータ量**（5.76M 件 × 数百バイト ≈ 1〜2GB 相当）に抑えられる（転送そのものは発生するため帯域コストは残るが、ストレージ・後続処理コストは実用範囲に収まる）。
3. `rankings` に **star 側のパーセンタイルも含まれる**ため（実測 c）、「dependents 降順」以外の追加ソートは不要 — 1 回のフルスキャンで Gem Index = f(rankings.dependent_packages_count, rankings.stargazers_count) を全件計算できる。
4. **健全性フィルタ（`criticality_score`）** はこの一覧エンドポイントには含まれていない（未確認）ため、別経路（OpenSSF の公開データセット等）との突合が別途必要 — ADR 0014 §5 未確定事項 4 と同一の宿題として残る。

---

### 4. D-28「Cloudflare 外のセッション / Routine の cron で回す」の実装形（具体案）

**現状で GitHub Actions が使えない**（`CLAUDE.md` / `D-23`）ため、D-28 の「セッション / Routine の cron」は文字どおり **Claude Code Scheduled Tasks（本リポジトリの `docs/routines/` 配下のルーティン定義）** を指すと解釈するのが唯一整合する読み方。

- **ルーティン定義**: `docs/routines/gem-index-batch-routine.md` を新設し、`sprint-cycle-routine.md` と同じ形式（発火間隔・担当スキルの記述）で登録する。実行頻度は §2 の実測（フルスキャンに 1〜2 時間・レート制限枠を跨ぐ）を踏まえ **週次**を提案（S3 の 2〜4 ヶ月更新サイクルよりむしろ高頻度に鮮度を保てる副次効果がある）。
- **実行スクリプト**: `tools/generate_gem_index.py`（新規）。処理は 4 フェーズに分割し、`checkpoint` スキルのパターン（Phase 境界で git commit）で長時間処理のタイムアウト耐性を持たせる。
  1. **fetch**: 一覧 API を `per_page=1000` でページネーションしながらストリーミングパースし、必要フィールドのみを中間ファイル（例 `content/data/_intermediate/npm-rankings-{date}.jsonl`）に追記
  2. **compute**: 中間ファイルから Gem Index（= `rankings.stargazers_count − rankings.dependent_packages_count`。実測 h の向き（0=最上位）に基づく符号は round2 で最終確定）を計算し、上位候補を抽出
  3. **filter**: 健全性シグナル（`criticality_score` 等・別途取得）で足切り
  4. **publish**: 出典メタデータ（`D-29`: `source`/`license`/`source_license_url`/`generated_at`）を含む最終 JSON を `public/data/gems/npm/latest.json`（想定パス）へ書き出し
- **長時間実行対策**: `session-safety-rules.md` の「1 ターン最大 8 ツール呼び出し」制約に対し、fetch フェーズは `Bash(run_in_background: true)` で実行し、`Monitor` で完了を待つ（ポーリング sleep 禁止）。5,761 リクエスト・778GB という規模を踏まえ、**1 回のルーティン発火で完走しない場合は ADR 0014 §5.3.2 の「3 回の firing を跨ぐ分割」と同じ規律**（中間ファイルを commit して次回発火で再開）を適用する。
- **反映**: 生成した静的 JSON は通常の作業ブランチ → PR（`pr-review-flow-summary.md` のフロー）→ マージ → 既存の wrangler デプロイパイプラインで Static Assets として配信（D-28 の「git commit → デプロイで丸ごと差し替え」をそのまま踏襲、Worker 実行時書き込みなしなので `D-18` 抵触なし）。
- **SPOF 無害化**: バッチ失敗時は既存 JSON がそのまま配信され続ける（鮮度劣化のみ・配信停止しない）。`generated_at` を見て閾値（例: 10 日超）を超えたら次回ルーティン発火時に自己修復（再実行 + 失敗時は Issue 自動起票）。

---

### この分析が他の論点に与える影響（要 round2 検討）

- ADR 0014 は D-28 で「S3 バルクダンプを用いる」と明記しているが、本ラウンドの実測では **S3 は匿名アクセスが拒否され、REST 一覧 API + 事前計算済み `rankings` の方が現時点でアクセス可能**という逆転した根拠が得られた。データソースをどちらにするかは ADR の記述を上書きしうる論点のため、他レンズの検証（特にライセンス・帰属表示レンズ）と突き合わせて判断してほしい。
- 転送量 778GB という数字は「フィールド絞り込みができるか」が未確認のままの上限値であり、round2 で `fields=` 系パラメータの有無を確認できれば大きく圧縮できる可能性が高い。
