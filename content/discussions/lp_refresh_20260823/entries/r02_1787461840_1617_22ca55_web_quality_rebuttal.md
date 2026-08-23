<!--entry
author: web_quality
round: 2
kind: rebuttal
ts: 2026-08-23T14:10:40+09:00
-->

# web_quality — Round 2: rebuttal / concession

対象ファイルは再読しない。round 1 の自分の分析とホワイトボードの他レンズ投稿のみで反論する。

## 1. 撮影経路（`page.route` + `curl fulfill` で本番を撮る）を恒久化すべきか

**恒久化には反対。既定は変えず、明示 opt-in の環境変数として追加すべき。**

理由:

- **本番の共有 API レート枠を消費する**。`site/README.md`「先に言っておく制約」（現行文）は「共有の API レート枠で動いています。混み合う時間帯は検索が一時的に失敗することがあります」と明記している。撮影スクリプトの既定経路を本番直叩きに変えると、**LP 更新のたびに実ユーザーと同じ枠を消費する** 副作用が生まれる。ローカル `next build && next start` は（別トークン運用であれば）この枠を侵さない。この差はスクリプトのコメントに一度も出てこないため、恒久化するなら副作用として明記が必須
- **再現性が壊れる**。既存スクリプトの設計意図は「本番ビルドをローカルで起動して撮る」＝ **決定論的な入力**（コードは固定、GitHub API のレスポンスだけが変動）。本番を直接叩く経路は、①アプリのコード ②GitHub API の実データ の両方が撮影のたびに変わりうる。「今日のコード」と「今日のデータ」が区別できなくなり、`shot-mobile` 撮り直しが実は本番デプロイの遅延を検出しているだけ、という取り違えが起きうる
- **`curl` 経由の `route.fulfill` は今回のサンドボックス固有の回避策**（Chromium の直接/プロキシ経由 HTTPS が `ERR_CONNECTION_RESET` になる、という環境制約への対処）。ローカル開発機・将来の CI 環境では発生しない可能性が高い問題を、全実行環境の既定動作に組み込むのは筋が違う

**具体案**: `LP_SHOT_BASE`（既存）はそのまま維持し、`LP_SHOT_BASE=https://gem-hunter.kinamocchi-tech.workers.dev` を明示すれば本番を対象にできる据え置き設計は変えない。その上で `curl` 経由フェッチだけを新しい opt-in フラグ（例 `LP_SHOT_FETCH_VIA_CURL=1`）でオンにし、既定は off（従来どおり `page.goto` 直行）にする。`site/README.md`「スクリーンショットの更新」に「このクラウドサンドボックスで直接 HTTPS が通らない場合の回避策」として追記し、恒久のベストプラクティスとは書かない。

## 2. 新規ショット（Gem 一覧）追加時に確定形で足すべきもの

**`tools/capture_lp_screenshots.mjs`**:
- `SHOTS` 配列に `visual_assets` が提案した `shot-gems` エントリを追加（`name: 'shot-gems'`, `path: '/ja/gems?q={term}'`, `viewport`, 出力 `width`。フルページ撮影ならプロパティ追加不要、`clipFrom` を使うなら `shot-digest` と同じパターンで関数を書く）
- それ以外の変更は不要。撮影後の width/height 突き合わせ（末尾のマッチングロジック）は `written` 配列にプッシュされた `SHOTS` の要素を自動で拾うため、**配列に追加するだけで自動的にこの新画像も検証対象になる**（コード変更なし）

**`tools/check_site.py`**: **コード変更は不要**（round 1 §4 で列挙した 6 項目はすべて `index.html` を汎用走査する実装で、画像ファイル名のホワイトリストを持たない）。必要なのは `index.html` 側の記述:
- `<img src="./assets/img/shot-gems.webp" width="{実寸幅}" height="{実寸高さ}" loading="lazy" decoding="async" alt="{具体的な代替テキスト}">` を正しい属性で書く（`width`/`height` 欠落・縦横比不一致はどちらも `check_page()` が fail させる）
- `shot-gems.webp` を `site/assets/img/` に実際に置く（参照切れチェック対象）
- `--self-test` は `site/assets/img/*` を全走査するので、新ファイルを置いた時点で自動的に画像デコード可否も検証される（追加設定不要）

## 3. インフォグラフィック 1 点だけ載せる場合の技術的な最低条件（`visual_assets` の「14 点とも不使用」を支持した上での先回り）

`visual_assets` の判定（① 社内文脈の管理コードが読者に無意味 ② ADR 0015 の文字焼き込み禁止に抵触 ③ 縮小で可読性崩壊）に同意する。round 1 のサイズ実測（205〜324KB/枚）もこの判定を補強する。それでも 1 点だけ載せる案が通るなら、最低限：

| 項目 | 条件 |
|---|---|
| コピー先 | `docs/infographics/` を直参照しない。`site/assets/img/` へコピーする（round 1 §3。相対パスが GitHub Pages のサブパス配信で `gh-pages` ブランチには `docs/` が存在せず壊れるため） |
| 配置 | ファーストビュー外（`#trust` 以降の下位セクション）。LCP 要素を `shot-mobile.webp`（63KB）から差し替えないため |
| `loading` | `lazy` 必須 |
| `width`/`height` | 実寸（16:9、例 1536×864）をそのまま記載。`check_site.py` の縦横比チェック（許容誤差 0.01）を通す |
| ファイルサイズ | 原寸 205〜324KB は現行画像合計（337KB）と同等の重さが 1 枚で乗るため不可。**再圧縮・リサイズして 1 枚あたり 100KB 未満を目標** にする（`check_site.py` にサイズ上限チェックは無いので人力で守る） |
| alt | `docs/infographics/README.md` の見出し語（例 `alt="Gem Score 算出ロジック"`）を **転用しない**。画像内の主要な事実（何を示す図か・読者が持ち帰る結論）を 1〜2 文で書く。`04-prd.webp` 等の管理コード（`FR-n`/`AC-n`）はそのまま読み上げても意味を持たないため、**コードは alt に含めず結論だけを言い換える** |
| 相対パス | `./assets/img/...`（`site/` 基準） |
| 検証 | 追加後に axe を再実行し `image-alt` ルールが引っかからないことを確認する（round 1 §6 のスクリプトで再現可能） |

## 4. `site/README.md`「設計上の約束」違反チェック — 名指し

`info_arch`（formula ブロック書き換え・bento 新タイル・制約文更新・FAQ 更新）、`visual_assets`（`shot-search`/`shot-mobile` 撮り直し・`shot-gems` 新規・`why-divider` 装飾画像 1 点提案）の round 1 ドラフトを確認した。

**違反なし**。内訳:
- 外部 CDN 依存: `info_arch` のドラフトはテキストと既存と同じインライン SVG のみ、`visual_assets` の新規画像は自前生成（gpt-image-2 → `to_web_assets.mjs`）で `site/assets/img/` へ配置する前提。CDN 参照ゼロ
- ページ内 JavaScript: 両者ともマークアップ・画像の追加のみ。`<details>` や `<a href>` 以外のインタラクション（モーダル等）は提案されていない
- `opacity` アニメ: 提案なし。`visual_assets` の新規装飾画像も静的な `<img>` で、`.reveal`/`hero-in` の `transform` 方式を流用する前提と読める（明示はされていないが、opacity への言及は一切ない）
- prettier 整形: 言及なし（懸念事項として round 1 で先出ししただけ）
- 本番で無効な機能の記載: `info_arch`・`fact_sync` の Gem バッジ／Gem 一覧はいずれも `fact_sync` が実装済みと実測確認済み（PR #435/#440 ほか）。未実装の言及なし

**補足で 1 点フラグ**: `info_arch` の bento 新タイルは新しい inline SVG アイコンを使う（`<!-- アイコンはタグ/バッジ系を実装側で選定 -->` と未確定のまま）。既存の icon 用 SVG は **`width`/`height` 属性を持たず** `.icon { width:20px; height:20px }` の CSS クラスでサイズを決めている（round 1 では気づいていなかった点として補足: `check_site.py` の width/height 検査は `<img>` タグのみが対象で `<svg>` は対象外なので、実装側がこの新アイコンにも `width`/`height` 属性を **付けない** 限り機械検査には抵触しない。既存パターンを踏襲するよう実装側に申し送りたい）。

## 補足: fact_sync の「682→1061」修正への同意

round 1 では現行数値（682 ケース）をそのまま前提に画像重量の話をしたが、この数値変更はテキストのみで画像・CLS・LCP に影響しない。`fact_sync` の実測（954+107=1061）を追認する。ページ重量の実測結論（round 1 §1）は変更なし。
