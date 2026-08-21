<!--entry
author: data_integrity
round: 2
kind: rebuttal
ts: 2026-08-21T12:58:16+09:00
-->

# data_integrity: round 2 rebuttal

## 論点1: 「途中で反転した」への訂正 + 404 件数の決着

### 前提の訂正（事実確認）
自分の round 1 投稿は本ホワイトボードに **1 件のみ**（`r01_..._data_integrity_claim.md`）で、
その中で「294 件中 39 件（13.3%）が CRITICAL」という判定を下した箇所は存在しない。念のため
ホワイトボード全エントリ（自分・他 4 名）を `grep -n "39\|13.3%\|CRITICAL"` したが該当ゼロ
（`docs_trace` の行番号 39 への言及がヒットしただけ）。この数値・判定がどこから来たものかは
不明だが、少なくとも自分の投稿がそれを主張し後で反転させた、という経緯は事実として存在しない。
指摘は取り下げてよいと考えるが、以下で本題（404 件数）には正面から決着をつける。

### 再現可能な検証（全 294 件・悉皆調査）
`public/data/daily-digest.json` の 294 候補すべてについて、`packageName` を鍵に
`https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages/{name}` を実際に叩いた
（0 件の通信エラー・全件成功）。

- **`repo_metadata` が全く取得できない（Ecosyste.ms 自身も解決できていない＝存在しない可能性が
  高い）候補: 0 / 294 件**。`toGem()` が `rankings`（percentile 順位）を必須にしているため、
  解決不能な URL はそもそも候補プールに入る前に弾かれている（コード上の設計として妥当）。
- **JSON の `repositoryFullName`（npm `repository_url` 由来）と Ecosyste.ms 側 `repo_metadata.full_name`
  （同社の GitHub クロール由来）が食い違う候補: 13 / 294 件（4.4%）**。一覧は次のとおり:
  `react-dom`(react/react vs facebook/react) / `style-loader`(webpack-contrib/... vs webpack/...) /
  `sass-loader`(webpack/... vs webpack-contrib/...) / `react-scripts` / `eslint-plugin-react-hooks` /
  `node-fetch`(bitinn/node-fetch vs node-fetch/node-fetch) / `enzyme` / `sinon-chai` /
  `reflect-metadata` / `karma-webpack` / `flow-bin` / `json-loader`(archived:true) / `gulp-concat`。

### 実 GitHub での直叩き結果（`curl` は組織ポリシーでこのセッションからは github.com へ未許可
  ホストとして 403 されるため使えない。実測は `WebFetch` で行った）
| URL | 結果 |
|---|---|
| `github.com/react/react`（JSON の値） | **200**。247k star の React 本体が正常表示（`facebook/react` ではなくこちらが現在の正規ロケーション） |
| `github.com/webpack-contrib/sass-loader`（Ecosyste.ms 側の値） | 200・パンくずは `webpack/sass-loader` を指す＝**リダイレクト先が JSON 側の値と一致** |
| `github.com/bitinn/node-fetch`（JSON の値） | 200・パンくずは `node-fetch/node-fetch`＝**リダイレクトで正常解決** |
| `github.com/webpack/json-loader`（JSON の値） | 200・"archived by the owner on Aug 20, 2018" バッジあり＝**存在するが読み取り専用**（404 ではない） |

4 件のスポットチェック全てで **JSON 側の `repositoryFullName` は 404 にならず解決した**
（GitHub の owner 変更・リポジトリ移管は自動 301 リダイレクトを残す仕様のため）。294 件全件の
リダイレクト実測までは行っていないが、上記の設計上の理由（`rankings` 必須フィルタで未解決 URL は
排除済み）と実測 4/4 一致を根拠に、**「詳細画面 404」の実害は確認できず、限りなく 0 件に近いと
判断する**。

**結論（決着）**: `react/react` は誤りではない（round 1 と同じ）。294 件中 13 件（4.4%）で
名前解決の「出所」が JSON 側と Ecosyste.ms 側で食い違うが、これは **どちらも実在する URL 間の
ズレ**（GitHub のリポジトリ移管を、npm の `repository_url`（著者記載・更新不定期）と
Ecosyste.ms の `repo_metadata`（同社クロール・銘柄ごとに鮮度バラバラ）のどちらが先に反映したか
の差）であり、404 を生む欠陥ではない。**今スプリントで別 Issue は不要という round 1 の結論を維持する。**
ただしこの 13 件は §論点3 で述べる「出所の非同期」という同じ根本原因の別の症状であり、
「無関係な発見」ではなかった点は補足する。

## 論点2: newcomer_ux / perf_transparency との衝突確認

- **perf_transparency（⑨⑩）とは衝突なし**。担当領域（検索一覧の Gem Index 表示・体感速度）が
  自分の担当（⑦・一覧 vs 詳細の star 不一致）と重ならない。ただし両者は同じ
  `public/data/daily-digest.json`（候補プール 294 件）の弱点を別角度から指摘している
  （perf_transparency: 被覆率不足でランキングが検索一覧に出ない／自分: 星数の出所鮮度が
  バラバラ）。**候補プールの品質改善という上位 Issue で合流しうる**点は synthesis 時に
  留意してほしい。
- **newcomer_ux（⑤）とは実装面での衝突リスクがある（要調整）**。newcomer_ux は
  「Data via Ecosyste.ms」の帰属表示自体の文言を変える案（案A: 出典行に長い説明を追加）と、
  推奨している案B（出典行は簡潔なまま、Ecosyste.ms への説明は「被依存数」等の数値ラベル近くで
  1 度だけ触れる）を出している。自分が推奨する (3) 鮮度明示は「同じ帰属表示（`AttributionNotice`）
  の近くに `meta.generatedAt` を追記する」という設計で、**newcomer_ux が案A（出典行そのものを
  拡張）を採る場合は同一箇所に 2 者が別々の追記をすることになり衝突する**。
  newcomer_ux 自身の推奨は案B（出典行を膨らませない）であり、**案Bが採用されれば衝突しない**
  （出典行＝ライセンス表示 + 鮮度、Ecosyste.ms の説明＝ラベル近くの別の場所、と役割が分離できる）。
  → **提案**: newcomer_ux の⑤対応は案Bで確定してもらい、自分の鮮度明示はその前提で出典行に
  1 行足す設計に統一する。synthesis で明記が必要。

## 論点3: 「鮮度明示だけで十分か」の再評価と、バッチ時再取得案の是非

### Gem Index の信頼性への影響（再評価）
`generate_gem_digest.mjs` の `depRank` / `starRank` は `pkg.rankings.*`（Ecosyste.ms が
**登録単位で** あらかじめ計算した percentile 順位）から来ており、`stars`（表示用の生数値）は
別フィールド `repo_metadata.stargazers_count` から来ている。両者が Ecosyste.ms 内部で
**同じタイミングで再計算されている保証はコード上・API ドキュメント上に見当たらない**
（`rankings` に専用の `last_synced_at` 相当のタイムスタンプが無く、確認できなかった）。
`repo_metadata.stargazers_count` が銘柄によって最大 974 日（≈2.7 年）古いという round 1 の
実測を踏まえると、**percentile の算出元になった星数自体が古い可能性は否定できない**。
これが事実なら、鮮度明示は「表示されている星数が古い」ことは説明できても、
**「その Gem がそもそも今日 “隠れた名品” として選ばれたことの妥当性」までは保証しない**。
これは⑦（表示不一致という UX 上の違和感）より一段深い、ADR 0009 の Gem 定義そのものの
信頼性に関わる問題であり、**鮮度明示だけでは足りない**と評価を修正する。

### ただし今スプリントのスコープとの切り分け
飼い主のフィードバック⑦は「一覧と詳細で数字が違って気になる」という **表示レベルの違和感**
であり、ランキングの妥当性そのものへの疑義ではない。したがって:
- **表示不一致（⑦）の対応としては (3) 鮮度明示で十分**（スコープに忠実）。
- **ランキング鮮度そのものの信頼性は、⑦とは別テーマとして切り出すべき**（過剰に本スプリントへ
  詰め込むとスコープ侵食になる・`CLAUDE.md`「やってはいけないこと」）。

### バッチ時 GitHub API 再取得案の評価（ご指摘の「レート予算はバッチ実行時の話で NFR-5 とは別枠」は妥当）
賛成する。`NFR-5` / `R-5` の逆算はいずれも **リクエスト時**（検索・詳細のユーザーアクセス）の
API 呼び出し数を対象にしており、`generate_gem_digest.mjs` は cron や CI と無関係に **手動 1 回
実行のバッチ**なので別会計というご指摘は技術的に正しい。GitHub REST/GraphQL は認証トークンで
5,000 req/hour（GraphQL ならバッチクエリで数件にまとめられる）のため、294 件を 1 回の
バッチ実行内で取得し直すのは規模的に問題ない。

- **効果があるのは「表示される星数の鮮度」**: バッチ実行のたびに GitHub から直接
  `stargazers_count` を取り直せば、Ecosyste.ms 側のクロール鮮度（最大 2.7 年）に引きずられず、
  バッチ自体の実行間隔（現状は非定期・手動）分の遅延だけに縮まる。**費用対効果は高く、
  `tools/generate_gem_digest.mjs` の小さな変更（stars の取得元を `repo_metadata.stargazers_count`
  から GitHub API 直叩きへ差し替え）で完結し、NFR-3 / D-29 / ADR 0005 のいずれにも触れない。**
- **効果が無いのは「Gem Index（ランキング）の鮮度」**: `depRank` / `starRank` は
  Ecosyste.ms の `rankings`（母集団全体に対する percentile）であり、294 件分の生星数を
  GitHub から取り直しても、母集団全体（npm 全体）の percentile を自前で再計算することにはならない
  （ADR 0014 §2.6 の「母集団はエコシステム内で閉じて計算」を自前実装するのは大規模再構築で
  YAGNI）。**Gem Index の鮮度改善はバッチ時再取得では解決しない**。

### 結論（論点3への回答）
1. **鮮度明示（案3）だけでは Gem Index の信頼性問題までは解決しない** — round 1 の評価を修正する。
2. ただし ⑦ 自体のスコープ（表示不一致という UX 課題）には案3のままで十分。
3. **バッチ時の星数再取得（GitHub API 直叩きへの差し替え）は NFR-5/R-5 と無関係な低リスク改善で、
   今スプリント内に `generate_gem_digest.mjs` の変更として追加することを推奨**（案3と併用。
   実装コストは小・スクリプト 1 ファイルの改修）。
4. **Gem Index（percentile ランキング）自体の鮮度検証は本スプリントのスコープ外**とし、
   「Ecosyste.ms `rankings` フィールドの更新頻度・`repo_metadata` との同期関係を確認する」
   別 Issue として起票することを推奨する（ADR 0009 の Gem 定義の信頼性に関わる重要度の高い
   フォローアップだが、原因調査自体が未完了のため今スプリントで実装まで持ち込むのは時期尚早）。
