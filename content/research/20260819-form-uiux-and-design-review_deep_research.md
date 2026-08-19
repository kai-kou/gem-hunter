# Deep Research: フォーム操作性の寸法基準とデザインレビューの仕組み

- 実施日: 2026-08-19 JST
- エンジン: ネイティブ `/deep-research`（Workflow・106 エージェント）
- 回収方法: 最終 synthesis エージェント（`af74a27dea35fa81b`）が `StructuredOutput` のスキーマ検証に 3 回失敗し、最終的にプレースホルダ（`summary: "test"` 等）を提出して完了した。しかし **1 回目の提出試行**（`findings` フィールドの入れ子が壊れてスキーマ違反になっただけで、中身は本物の合成結果）と、同エージェントが `Bash` で書き出した `scratchpad/findings.json`（7,703 バイト）が journal 上に無傷で残っていたため、これを正規の一次回収物として採用した。加えて journal.jsonl（212 エントリ）と各エージェントの個別トランスクリプト（`agent-<id>.jsonl`）を Python で走査し、検索結果・クレーム抽出・敵対的検証の生データを突き合わせて再構成した。
- 検証統計: 質問分解 5 角度 / 検索エージェント 5（URL 30 件） / クレーム抽出エージェント 24（claims 86 件抽出） / 敵対的検証（3 票制）25 クレーム・のべ 75 票 → **confirmed 20 / killed 5**

---

## 0. 調査の切り口（5 角度）

最初の質問分解エージェント（`a84b8adf31e0ea1dc`）が立てた 5 角度。各角度が元の質問 1〜7 にどう対応するかも含め、journal に記録されている通りに再掲する。

| 角度 | 検索クエリ | 対応する元質問 |
|---|---|---|
| デザインシステム実寸比較 | Material Design 3 / Apple HIG / GOV.UK / GitHub Primer の最小タップターゲット高さ・px | 質問 1 |
| WCAG アクセシビリティ標準と iOS Safari ズーム挙動 | WCAG 2.5.8 / 2.5.5 の例外条項、iOS Safari 16px 自動ズーム | 質問 2・3 |
| 2026 年の検索フォーム UX トレンド | type="search"・クリアボタン・オートコンプリート・レイアウトシフト | 質問 4 |
| Tailwind CSS v4 + shadcn/ui 実装パターン | サイズ variant・疑似要素タッチターゲット拡張・デザイントークン | 質問 5 |
| デザイン QA 運用と AI エージェントによるデザインレビュー | Claude Code Agent Skills の design-review・Playwright 視覚回帰 | 質問 6・7 |

---

## 1. 入力欄・ボタンの推奨寸法（デザインシステム比較）

🔴 **この節は journal からほとんど回収できなかった**。最終 synthesis も明示的に「質問 1（MD3/HIG/GOV.UK/MOJ/Primer の実寸比較表）は検証を通過したクレームの中にほぼ材料がなく、今回の調査では未回答。追加のディープリサーチが必要」とキャリブレーションしている（`attempt1_summary.txt` caveats）。以下は敵対的検証を **経ていない** 生クレーム（クレーム抽出段階の出力のみ）であり、数値の裏取りは別途必要。

| デザインシステム | 記載内容 | ソース品質 | 検証状態 | 出典 URL |
|---|---|---|---|---|
| GOV.UK Design System | text-input コンポーネントのページに具体的な高さ・パディング・フォントサイズの px 値は **記載なし**。`<input type="number">` 非推奨・`inputmode="numeric/decimal"` 推奨・`autocomplete` 属性で WCAG 1.3.5 を満たす方針のみ | primary（一次） | 未検証（抽出のみ） | https://design-system.service.gov.uk/components/text-input/ |
| GOV.UK Design System（textarea） | 高さは固定 px でなく `rows` 属性で制御（既定 5 行、大きい用途は 8 行の例） | primary | 未検証 | https://design-system.service.gov.uk/components/textarea/ |
| GitHub Primer | フォーム全体は「縦積みをデフォルトにする」方針、ラベルは 3 語以内。**px 値・高さ・パディング・フォントサイズの記載は一切ない** | primary | 未検証 | https://primer.github.io/design/ui-patterns/forms/overview/ |
| shadcn/ui Button（公式現行 docs） | `size` prop は `default / xs / sm / lg / icon / icon-xs / icon-sm / icon-lg` の **8 種類**（旧来の 4 種から拡張）。ただし **具体的な px 高さ・パディング値はドキュメント本文になく、CVA のソースコード側にのみ存在**（docs のテキストからは非公開） | primary | ✅ 検証済み（3-0・confirmed） | https://ui.shadcn.com/docs/components/base/button |
| （third-party まとめサイト） top10k.com | 「MD3 は 48×48dp」「Apple HIG は 44×44pt」「WCAG 2.5.5(AAA) は 44×44px」「WCAG 2.5.8(AA) は間隔例外込みで 24×24px 相当」と主張 | **unreliable**（信頼度低） | 敵対的検証の対象外（未検証） | https://top10k.com/tool/touch-target-size-checker |
| （third-party まとめリポジトリ）ehmo/platform-design-skills | Apple HIG・MD3・WCAG 2.2 から抽出したルール集と称するが、**具体的な px 値・タッチターゲット寸法の記載自体がこのページには存在しない**（規模主張「450+ ルール」自体も敵対的検証で 1 対 2 の不確定＝信頼できない） | blog | 一部検証済み（構造は 3-0 confirmed、規模主張は not-confirmed） | https://github.com/ehmo/platform-design-skills |

**MOJ Design System**: 検索エージェント 5 体のいずれの結果にも MOJ 固有の URL は含まれていなかった。journal から回収できず（要追加調査）。

---

### 1.1. 追補: 一次情報の追加取得（2026-08-19 JST・本セッションで実施）

上記の穴を埋めるため、`WebFetch` が本文を取得できなかった SPA（Material Design 3 / Apple HIG）を **実ブラウザ（Playwright + プリインストール Chromium）でレンダリングして逐語取得** し、GOV.UK / Primer / MOJ はドキュメントとソースを直接取得した。以下はすべて **一次情報からの逐語確認済み**。

| デザインシステム | 項目 | 値 | 逐語・変数名 | 出典 |
|---|---|---|---|---|
| Apple HIG | ボタンの最小ヒット領域 | **44×44 pt**（visionOS は 60×60 pt） | "a button needs a hit region of at least 44x44 pt — in visionOS, 60x60 pt" | https://developer.apple.com/design/human-interface-guidelines/buttons |
| Material Design 3 | アイコンボタンのターゲットサイズ | **48×48 dp** | "Extra small and small icon buttons must have a target size of 48x48dp or larger to be accessible." | https://m3.material.io/components/buttons/specs |
| Material Design 3 | テキストフィールドの高さ / ターゲットサイズ | **56 dp**（filled / outlined 共通） | `Default container height 56dp` / `Target size 56dp` | https://m3.material.io/components/text-fields/specs |
| GOV.UK Frontend | text input の高さ | **40px**（2.5rem） | `height: base.govuk-px-to-rem(40px)` | `alphagov/govuk-frontend` `packages/govuk-frontend/src/govuk/components/input/_mixin.scss` |
| GOV.UK Frontend | text input のフォントサイズ | **19px / 行間 25px**（ブレークポイントに依らず固定） | `govuk-font($size: 19)`・スケール定義に "Stay at 19/25 at all sizes" | `settings/_typography-responsive.scss` |
| GOV.UK Frontend | ボタンの実効高さ | **約 38px**（line-height 19 + padding 8/7 + border 2/2） | `_mixin.scss` の padding 計算 | `packages/govuk-frontend/src/govuk/components/button/_mixin.scss` |
| GOV.UK | 44px タップターゲットの保証 | **していない** | Issue #2060 で「WCAG AAA の 44×44px は満たしていないが、要求されているのは AA のみ」とチームが回答 | https://github.com/alphagov/govuk-frontend/issues/2060 |
| MOJ Design System | フォームコントロールの寸法 | **GOV.UK を継承**（固有指針なし） | "Use the MOJ Design System alongside the GOV.UK Design System." | https://design-patterns.service.justice.gov.uk/ |
| GitHub Primer | control size トークン | xsmall **24px** / small **28px** / medium **32px** / large **40px** / xlarge **48px** | `--control-*-size` | https://primer.style/foundations/primitives/size |
| GitHub Primer | coarse pointer 時のコントロール高さ拡大 | **なし**（変化するのは要素間 gap のみ: coarse 0.75rem/1rem・fine 0.5rem） | 同ページ "Responsive control stack sizes" | https://primer.style/foundations/primitives/size |
| shadcn/ui（`new-york-v4`） | Button / Input の高さ | `default: h-9`（36px）/ `sm: h-8` / `lg: h-10` / Input `h-9` | registry ソース | `shadcn-ui/ui` `apps/v4/registry/new-york-v4/ui/button.tsx` |

**食い違いの整理と採用方針**:

- **44px（Apple HIG・WCAG 2.5.5）と 48dp（M3）と 40px（GOV.UK / Primer large）で食い違う**。dp は Android の密度非依存単位で CSS px と 1:1 対応しないため、Web の実装基準としては **CSS px 基準で一致する 44px（WCAG 2.5.5 = Apple HIG）を主要導線に採る** のが妥当。
- **GOV.UK は 44px を保証していない**（AA 適合を要件としているため）。つまり「公共系の実装でも 40px は妥当な水準」であり、二次的コントロールの `--size-control-lg` を 40px に置く根拠になる。
- **shadcn/ui のデフォルト（36px）はどのガイドラインの推奨も満たさない** 中間値であり、主要導線にそのまま使わない。

**環境上の注意（後続セッション向け）**: このコンテナの Chromium は TLS 1.3 のハンドシェイクに失敗するため、Playwright で外部サイトを開く場合は `launch({ args: ['--ssl-version-max=tls1.2'] })` が必要（TLS 検証の無効化ではない）。また Apple HIG は `networkidle` を待つとタイムアウトするため `domcontentloaded` + 待機に切り替える。

**Apple HIG「44×44pt」の扱い**（重要な注意）: superdesign.dev のブログが「Apple HIG の最小タップターゲットは 44×44pt で、オリジナル iPhone 以来の慣行」と主張したクレームは、敵対的検証で **2 票が反証・KILLED 判定**（詳細は §9）。ただし反証の内容は「44×44pt という数値自体」ではなく「オリジナル iPhone 以来という歴史的経緯」の部分であり、数値自体は複数の反証票の中でも「現行の Apple HIG ガイダンスとしては正しい」と評価されている。**44×44pt という数値は journal 内で正式に primary（Apple 公式 HIG ページ）から直接引用・逐語確認されてはいない**（JS レンダリングのため WebFetch が本文を取得できなかったと検証エージェントが報告している）ため、実装前に `developer.apple.com/design/human-interface-guidelines` を直接確認することを推奨する。

---

## 2. WCAG 2.2 Target Size（正確な要件・例外条項）

✅ この節は W3C 一次情報を直接 fetch した上で 3-0（全会一致）で確定した、信頼度の高い節。

### 2.5.8 Target Size (Minimum) — Level AA
- **要件**: ポインタ入力のターゲットは少なくとも **24×24 CSS px** 以上。判定は「ターゲット内に軸整列した 24×24px の正方形を完全に収められるか」であり、ターゲットの外形そのものが正方形である必要はない。
- **5 つの例外**: Spacing（間隔）／Equivalent（等価コントロール）／Inline（インライン）／User Agent Control（ユーザーエージェント制御）／Essential（本質的）
  - **Spacing 例外の具体条件**: 24px 未満のターゲットでも、各ターゲットの外接矩形中心に 24px 直径の円を置いたとき、隣接ターゲットの円と交差しなければ適合とみなせる。
  - **Equivalent 例外**: 同一ページ上の「別のコントロール」が **2.5.8 自体を満たしていれば**（＝24×24px 以上であれば）よいという自己参照的な緩い規定。
  - **User Agent Control 例外**: サイズがブラウザ既定値のままで著者が変更していない場合は適用除外。
- 出典: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html （primary・検証 3-0 confirmed）

### 2.5.5 Target Size (Enhanced) — Level AAA
- **要件**: ポインタ入力のターゲットは少なくとも **44×44 CSS px** 以上。
- **4 つの例外**（2.5.8 と異なり **Spacing 例外がない**）: Equivalent／Inline／User Agent Control／Essential
  - **Equivalent 例外の違い**: 2.5.8 と異なり、2.5.5 では代替コントロールが **明示的に 44×44px 以上であること** が要求される（2.5.8 のような自己参照的な緩さがない）。
  - **Inline 例外の文言差**: 2.5.5 は「非ターゲットテキストの line-height に制約される」という表現、2.5.8 は「文または文のブロック内」というやや広い表現（`w3c/wcag` Issue #3714 で明文化）。
  - **Essential 例外の文言差**: 2.5.5 のみ「法的に要求される」という句が含まれる。
- 出典: https://www.w3.org/WAI/WCAG21/Understanding/target-size.html （primary・検証 3-0 confirmed）／両 SC の例外文言差分の一次証跡: https://github.com/w3c/wcag/issues/3714（primary・検証 3-0 confirmed）

### 2.5.8 を満たすだけでは操作性が不足するケース
- 2.5.8（AA・24×24px）は Spacing 例外により **視覚上さらに小さいターゲットでも間隔さえ確保すれば適合しうる**。これは法規適合の最低ラインであり、実際のタップ操作しやすさ（誤タップ防止・手指の震え・粗大運動障害への配慮）を最大化するものではない。
- 2.5.5（AAA・44×44px）は Equivalent 例外が厳格（代替コントロールも 44×44px 必須）なため、AA よりも実質的に緩和されにくい規定になっている。

---

## 3. iOS Safari の自動ズーム

✅ 複数の独立ブログ・技術記事で一致し、3-0 で確定した高信頼度の節。

- **発生条件**: iOS Safari は **input のレンダリング後（computed）フォントサイズが 16px 未満** のとき、フォーカス時に自動でビューポートをズームする。**16px 以上であればズームは発生しない**。
  - 閾値は宣言 CSS 値ではなく、**transform 等適用後の実効フォントサイズ** で判定される。
  - 出典（相互に独立し内容が一致）:
    - https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/（blog・敵対的検証で当該クレーム 3-0 confirmed）
    - https://defensivecss.dev/tip/input-zoom-safari/（blog・同 3-0 confirmed。解決策は「input に font-size: 16px を追加するだけ」というシンプルな記述）
    - https://takazudomodular.com/pj/zudo-tauri/docs/mobile/ios-input-auto-zoom/（blog・「16px 未満で発生」の主張は 3-0 confirmed）
- **`maximum-scale=1` を使わない回避策**:
  - 検証で確定した安全な実装は、**メディアクエリ等の条件分岐に頼らず、無条件に input / textarea / select へ `font-size: 16px` 以上を適用する** こと。
  - 🔴 **反証された手法（重要）**: 「`@media (pointer: coarse)`（タッチデバイス限定）にスコープして `font-size: 16px` を適用すべき」という推奨は、敵対的検証で **3 票中 0 票（0-3・KILLED）** となり **採用不可**。詳細と反証理由は §9 を参照。
- **WCAG 1.4.4（拡大の阻害禁止）との関係**: `maximum-scale=1` や `user-scalable=no` によるズーム抑制は、モバイルにおける WCAG 1.4.4（Resize Text・200% 拡大）達成の主要手段であるピンチズームそのものを奪うため、**公開 Web ページでは避けるべき** という結論が 3-0 で確定。ネイティブアプリのバンドル内（例: Tauri）では著者の裁量で許容されうるという意見もあるが、これは Web 標準の要求ではなく著者個人の判断にすぎない。出典: https://takazudomodular.com/pj/zudo-tauri/docs/mobile/ios-input-auto-zoom/

---

## 4. 検索フォーム UI のベストプラクティス

🔴 この節は synthesis の caveats でも「質問 4（2026 年の検索フォーム UI トレンド）は検証済みクレームがゼロで、今回の調査では未回答」と明記されている。以下はクレーム抽出段階の **未検証の生データ**（敵対的検証を経ていない）。

| 項目 | 内容 | ソース品質 | 出典 URL |
|---|---|---|---|
| クリアボタン | `type="search"` は Chrome/Safari/Edge ではネイティブのクリアボタンを提供するが、**Firefox は非対応**。クロスブラウザ一貫性にはカスタム実装が必要。サンプル実装は `width: 16px; height: 16px; padding: 2px` という **WCAG 2.5.8（24×24px）を下回るサイズ** で、`aria-label`／`title` で補っている | blog | https://nikitahl.com/input-clear-button |
| 送信ボタンの配置 | モバイルでは検索欄に隣接した専用の送信ボタンが必須。ユーザーは端末側のキーボード検索キーではなくページ UI 側を見る傾向があり、ボタンがないと強い不満につながる。テスト対象モバイルサイトの **27% がこの配置要件を満たしていない** | secondary（Baymard の調査ベース） | https://baymard.com/blog/mobile-ux-ecommerce |
| オートコンプリート | ほとんどの利用者がオートコンプリート候補に依存しており、軽微なスペルミスで候補が消えると検索が失敗する。修正提案（スペル補正）を出すべき | secondary | https://baymard.com/blog/mobile-ux-ecommerce |
| オートコンプリート候補数 | 5〜8 件が理想とされる（具体的根拠・実証データは示されていない） | blog | https://www.designmonks.co/blog/search-ux-best-practices |
| 検索バーの一貫配置 | 全ページで一貫した位置に置くべき（一般論、数値なし） | blog | https://www.designmonks.co/blog/search-ux-best-practices |
| モバイルの触りやすさ | 「touch-friendly な入力欄」「レスポンシブなフィルター」が必要と述べるのみで、具体的な px 値やしきい値の記載はない | blog | https://www.designmonks.co/blog/search-ux-best-practices |

**type="search" のキーボード制御・レイアウトシフト回避・送信中フィードバック**: journal から回収できず（要追加調査。designstudiouiux.com の記事は fetch されたがクレーム抽出結果は 0 件だった）。

---

## 5. Tailwind v4 + shadcn/ui の実装パターン

一部は敵対的検証済み（3-0 confirmed）で信頼度が高い。

- **shadcn/ui Button の size variant（現行 docs・primary・検証 3-0 confirmed）**: `default / xs / sm / lg / icon / icon-xs / icon-sm / icon-lg` の 8 種。旧来の `default/sm/lg/icon` の 4 種構成から拡張されている。**具体的な px 値（高さ・パディング）は docs 本文になく CVA ソースコード側にのみ存在**（journal からは回収不可）。出典: https://ui.shadcn.com/docs/components/base/button
- **Tailwind v4 の cursor 挙動変更**: v4 ではボタンの既定が `cursor: pointer` から `cursor: default` に変わり、shadcn/ui docs は明示的な上書きが必要と注記している（未検証・クレーム抽出のみ）。出典: 同上
- **ローディング表示パターン**: shadcn/ui は `<Spinner />` を子要素として置き `data-icon="inline-start"` / `data-icon="inline-end"` 属性でスペーシングを制御するパターンを提供（未検証）。出典: 同上
- **既存コンポーネントを壊さない size variant 拡張パターン（forum・未検証）**: shadcn/ui の `Calendar` は `Button` の既定サイズクラス（`h-9/px-3` のナビボタン、`h-7/w-7` の日付セル）に内部依存しているため、`buttonVariants` の既存キーを直接上書きすると Calendar のレイアウトが壊れる。回避策として (1) 既存サイズを保持したまま `app-sm`/`app-default`/`app-lg` のような新規 named variant を追加する、(2) `class-variance-authority`（cva）+ `cn` でラップした独立の `AppButton` コンポーネントを作る、(3) Tailwind の arbitrary/data-attribute variant セレクタで Calendar 内部要素だけを個別に固定する、の 3 パターンが提示されている。出典: https://github.com/shadcn-ui/ui/discussions/10788
- **疑似要素によるタッチターゲット拡張（✅ 検証済み・3-0 confirmed）**: `::after` 等の疑似要素を絶対配置し `inset` や独自の width/height を親に対して設定することで、**視覚上のボックスサイズを変えずに** クリック／タッチ／ホバー判定領域だけを拡張できる。具体パターン:
  ```css
  @media (pointer: coarse) {
    .button::after {
      content: '';
      position: absolute;
      inset: -8px; /* アイコンボタンなど非常に小さい要素は -12px 以上を検討 */
    }
  }
  ```
  親要素には `position: relative` が必要。出典: https://ishadeed.com/article/clickable-area/ ／ https://modern-css.com/larger-touch-targets-without-changing-element-size/（両方 primary blog・検証 3-0 confirmed）
- **パディングを当てる対象**: パディングは `<a>`/`<button>` などインタラクティブ要素自身に直接与えるべきで、ラッパー要素に与えても実際にクリックできる領域は広がらない。インラインリンクは `display: block` または `flex` に変更しないとパディングが有効なヒット領域に反映されない（未検証・ishadeed.com のクレーム抽出のみ）。
- **`pointer: coarse` メディアクエリのブラウザサポート**: 2020 年以降利用可能で、グローバルカバレッジ約 96%（未検証・modern-css.com のクレーム抽出のみ）。

デザイントークン化・フォーカスリングの具体実装パターンについては、journal から回収できず（要追加調査）。

---

## 6. デザインレビュー / デザイン QA の運用ノウハウ（人間主体のプロセス論）

🔴 **journal から回収できず**。synthesis の caveats でも「質問 6（人間によるデザインレビュー／QA の運用ノウハウ：実施タイミング・チェックリスト粒度・エンジニアとの役割分担・よくある失敗パターン）についても検証済みクレームがゼロで、今回の調査では未回答」と明記されている。検索エージェントのクエリ自体が AI エージェントによる自動デザインレビュー（質問 7）に寄っており、人間主体の運用ノウハウを扱う一次情報が収集されなかった。要追加調査。

---

## 7. AI エージェントによるデザインレビューの公開資産

この節は最も厚く検証されている。4 つの公開資産の構造を比較する。

### 7.1 Anthropic 公式 `frontend-design` skill（✅ primary・検証 3-0 confirmed）
- **性質**: デザイン **作成・審美的方向づけ** のためのスキルであり、**構造化レビューチェックリスト・役割定義・標準出力フォーマットを持たない**。
- Playwright 等のブラウザ自動化やプログラム的スクリーンショット取得への言及はなく、「環境が対応していれば手動でスクリーンショットを撮る」ことを促す程度に留まる。
- アクセシビリティ/ユーザビリティ面では「モバイルまでレスポンシブ・キーボードフォーカスの可視化・reduced-motion 尊重」という **数値なしの最低限のフロア** のみを設定しており、WCAG のターゲットサイズ基準やフォームコントロールの具体的アクセシビリティ要件への言及はない。
- 出典: https://github.com/anthropics/claude-code/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md

### 7.2 コミュニティ製 `design-review` skill（jezweb/claude-skills）
- **✅ 検証済み（3-0 confirmed）**: レビューチェックリストは **Layout & Spacing / Typography / Colour & Contrast / Visual Hierarchy / Component Consistency / Interaction Design / Responsive Quality** の **7 カテゴリ** で構造化されている。これは AI エージェント向けデザイン QA 定義の骨格として流用可能な粒度。
- **✅ 検証済み（3-0 confirmed）**: 出力フォーマットは "Overall Impression" → severity 別 "Findings"（High=「壊れて見える／プロっぽくない」、Medium=「未洗練に見える」、Low=「重箱の隅」）→ "What Looks Good" → "Top 3 Fixes" の構造。Chrome MCP / Playwright MCP / playwright-cli によるブラウザ自動化を用いる。
- 🔴 **反証された付随主張**（詳細は §9）: 「44×44px を必須とする（WCAG 2.5.5 Enhanced 準拠）」という主張と「エンジニアのコードレビューと明確に役割分離した severity 階層出力フォーマットを持つ」という主張は、いずれも敵対的検証で否定・不確定となった。実際は「Good/Bad 比較表の 1 行」として例示されているに過ぎず、WCAG 2.5.5/2.5.8 への直接言及は原文に一切ない。
- 出典: https://github.com/jezweb/claude-skills/blob/main/plugins/frontend/skills/design-review/SKILL.md

### 7.3 Checklist-Design/skills（✅ primary・検証 3-0 confirmed）
- **2 つの出力モード** を明確に区別: **Audit Mode**（present / partially present / missing / not needed / can't tell というステータスマーカー付きの表形式。Notion/Linear 互換）と **Critique Mode**（階層・レイアウト・タイポグラフィ・色・アクセシビリティ・インタラクション・仕上げについての会話調ピアレビュー）。
- Audit Mode は意図的に数値スコアリングを避け「採点ではなく誠実さを保つ」設計。Critique Mode は「effectively」「leverages」「optimises」等の企業ジャーゴンを明示的に禁止し、本物の強みの指摘も要求する。
- **実際の視覚アクセスを要求する設計**: スクリーンショットのアップロード／Playwright MCP による実 URL キャプチャ／Figma MCP のいずれかが必要で、コードや説明文からの推論だけでは動作しない。
- 112 個のチェックリストをローカルにバンドルし、ネットワークアクセス・API 不要（本人主張。第三者による検証なし）。
- 出典: https://github.com/Checklist-Design/skills

### 7.4 ehmo/platform-design-skills（部分的に信頼度低）
- **✅ 検証済み（3-0 confirmed）**: 各プラットフォーム別スキルは `SKILL.md`（エージェント指示）／`metadata.json`（バージョン・出典）／個別ルールファイル群／`AGENTS.md`（エージェント向け要約コンテキスト）という **4 要素構成** で統一されており、自作デザインレビュースキルのファイル構造テンプレートとして流用できる。
- 🔴 **信頼度が低い主張**: 「Apple HIG／Material Design 3／WCAG 2.2 から抽出した 450 以上のルールを 8 プラットフォームに分けて収録」という規模主張は、リポジトリの README 自体でタイトルが「300+ rules」・本文見出しが「450+ rules」と **内部矛盾** しており、外部監査もない。敵対的検証は 1 対 2 で確定に至らず（KILLED 扱い、詳細は §9）。
- 出典: https://github.com/ehmo/platform-design-skills

### 流用可能な「定義の構造」の要点（4 資産の横断比較）
| 観点 | Anthropic frontend-design | jezweb design-review | Checklist-Design/skills | ehmo platform-design-skills |
|---|---|---|---|---|
| 役割 | デザイン作成・審美的方向づけ | 構造化レビュー（QA） | 構造化レビュー（Audit/Critique 2 モード） | ルールベース参照集（8 プラットフォーム別） |
| 観点リストの粒度 | なし（自由記述の自己批評のみ） | 7 カテゴリ固定チェックリスト | チェックリスト項目単位（present/missing 等） | プラットフォーム別ルールファイル群 |
| severity/ステータス区分 | なし | High / Medium / Low の 3 段階 | 5 段階ステータスマーカー（present〜can't tell） | なし（ルール集のため） |
| 視覚アクセス手段 | 環境が対応していれば手動スクリーンショット | Chrome MCP / Playwright MCP / playwright-cli | Screenshot upload / Playwright MCP / Figma MCP | 該当なし |
| 出力形式 | なし（定型フォーマット不在） | Overall Impression → Findings(severity別) → What Looks Good → Top 3 Fixes | Audit Mode=表形式 / Critique Mode=会話調プローズ | SKILL.md + metadata.json + ルールファイル + AGENTS.md |

---

## 8. 実装指針への落とし込み（判定できる数値）

journal で **敵対的検証を通過した（confirmed）** 情報のみを 🔴 必須、検証未実施だが複数の独立クレームが一致するものを 🔵 推奨として整理する。

### 🔴 必須（W3C 一次情報で 3-0 confirmed）
1. インタラクティブ要素（ボタン・クリアボタン等）の最小ヒット領域は **24×24 CSS px 以上**（WCAG 2.5.8・AA・法的最低ライン）。間隔例外（24px 直径の円が重ならない）を使う場合を除き、視覚サイズをこれ未満に縮めない。根拠: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
2. 入力欄（`input`/`textarea`/`select`）は **条件分岐なしに `font-size: 16px` 以上** を適用する（iOS Safari の自動ズームを閾値未満で確実に回避するため。`@media (pointer: coarse)` 等でのスコープ限定は敵対的検証で否定済み＝§9 参照）。根拠: https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/ ／ https://defensivecss.dev/tip/input-zoom-safari/
3. ズーム抑制のために `maximum-scale=1` や `user-scalable=no` を使わない（WCAG 1.4.4 のピンチズーム手段を奪うため）。根拠: https://takazudomodular.com/pj/zudo-tauri/docs/mobile/ios-input-auto-zoom/

### 🔵 推奨（複数独立情報源が一致、ただし一部は検証未実施）
4. モバイルでの確実な操作性を狙うなら AAA 相当の **44×44 CSS px** をボタン等の目標サイズにする（WCAG 2.5.5・AAA）。根拠: https://www.w3.org/WAI/WCAG21/Understanding/target-size.html
5. 視覚サイズを抑えたい場合は、ボタン本体は 24〜32px 程度に留めつつ、`::after` 疑似要素 + `@media (pointer: coarse) { inset: -8px }`（アイコンボタン等は `-12px` 以上を検討）でタッチ判定領域だけを拡張する。根拠: https://ishadeed.com/article/clickable-area/ ／ https://modern-css.com/larger-touch-targets-without-changing-element-size/
6. パディングは wrapper ではなく `<button>`/`<input>` 自身に直接与える（未検証・ishadeed.com のクレーム抽出のみ、複数ソースで一般に言われる原則と一致）。
7. モバイルでは検索欄に隣接した専用の送信ボタンを必ず表示する（未検証・baymard.com のクレーム抽出のみ、27% のモバイルサイトが違反という具体数値付き）。
8. `type="search"` はブラウザネイティブのクリアボタンを提供するが Firefox は非対応のため、クロスブラウザではカスタムクリアボタンを実装し、24×24px 以上を確保する（nikitahl.com のサンプルは 16×16px で WCAG 2.5.8 未達だったため、そのままの流用は避ける）。

### 実装前に一次情報での再確認が必要な項目
- shadcn/ui の Button size variant の **具体的な px 値**（8 種の名称は確定しているが、実寸は journal に記録がなく docs にも掲載されていない。API 変更頻度が高いためソースコードを直接確認すべき）
- Apple HIG「44×44pt」の一次情報での逐語確認（`developer.apple.com/design/human-interface-guidelines` は JS レンダリングのため WebFetch できず未確認）
- Material Design 3 の「48×48dp」（journal 上では信頼度の低い third-party サイトの言及のみで、公式 Material Design ページは検索・fetch されていない）

---

## 9. 検証で否定された・votes が割れた主張（採用しない／注意して扱う）

敵対的検証で 25 クレーム中 **5 件が KILLED**（3 票中 2 票以上が反証）。

| # | 反証されたクレーム | 反証票 | 反証の要点 | 出典（原クレーム） |
|---|---|---|---|---|
| 1 | jezweb design-review skill は「44×44px on mobile」を **必須要件（mandate）** としており、WCAG 2.5.5(Enhanced) に整合、2.5.8(24px) とは異なる | 3/3 | 原文を直接 fetch すると "44x44px" は Good/Bad 比較表の 1 行（例示）に過ぎず、「必須」と明言する記述ではない。しかも原文には WCAG 2.5.5／2.5.8／"Enhanced"／"Minimum" のいずれの語も **一切登場しない**（全文検索でゼロ件） | https://github.com/jezweb/claude-skills/blob/main/plugins/frontend/skills/design-review/SKILL.md |
| 2 | jezweb design-review skill の出力フォーマットは「エンジニアのコードレビューと明確に分離された」構造である | 2/3 | severity 階層出力・Top3 Fixes・スクリーンショット要求自体は確認されたが、「エンジニアのコードレビューと分離している」という **役割分担の主張自体を裏付ける記述が原文にない**（過大解釈と判定） | 同上 |
| 3 | ehmo/platform-design-skills は「Apple HIG・MD3・WCAG 2.2 から抽出した **450+ ルール**」を 8 プラットフォームに収録している | 2/3 | リポジトリ自身のタイトル・meta は「300+ rules」、README 本文見出しは「450+ rules」と **内部矛盾** しており、いずれの数値も外部監査・第三者検証がない自己申告値 | https://github.com/ehmo/platform-design-skills |
| 4 | Apple HIG の「44×44 点」タップターゲット最小値は「オリジナル iPhone 以来の慣行」である | 2/3 | 反証側は「オリジナル iPhone のホーム画面アイコンは 57×57px であり、'44pt' は Retina（iPhone 4・2010 年）以降に導入された単位のため、2007 年当時の HIG を『44 points』と呼ぶこと自体が時代錯誤」と指摘。**数値自体（現行 44×44pt）は複数の反証票でも「現行ガイダンスとしては正しい」と評価** されており、否定されたのは「歴史的経緯」の部分 | https://superdesign.dev/blog/apple-design-system |
| 5 | iOS Safari のズーム対策として `font-size:16px` を `@media (pointer: coarse)` 等でタッチデバイスに **スコープして適用すべき** | 3/3 | CSS-Tricks／Rick Strahl のブログ／defensivecss.dev など主要な情報源はいずれも「**無条件に** 16px 以上を適用する」ことを標準的な推奨としており、pointer:coarse へのスコープ限定は数ある実装の一つに過ぎず「推奨される第一の解」ではない、という過大解釈だった | https://takazudomodular.com/pj/zudo-tauri/docs/mobile/ios-input-auto-zoom/ |

### confidence: medium（confirmed ではあるが留保が必要）のクレーム
- 実装判断としての「AAA 相当 44×44px を目標にしつつ AA の 24×24px を最低ラインとする」という指針は、個々の数値は high confidence で確定しているが、**「どちらを採用すべきか」という組み合わせ判断自体は一次情報が明示していない合成的知見** のため medium 扱い。
- jezweb design-review skill の 7 カテゴリ構造は 3-0 confirmed（高信頼）だが、付随する「44×44px 必須」「ブラウザ自動化込み出力フォーマット」は上表の通り否定・不確定のため、**この skill を流用する際は原典を必ず直接確認** すること。
- ehmo/platform-design-skills のファイル構造（4 要素構成）は 3-0 confirmed（高信頼）だが、規模の数字（450+ ルール等）は鵜呑みにしないこと。

---

## 10. 出典一覧

journal.jsonl（検索結果・クレーム抽出時の WebFetch・敵対的検証の counterSource）に実際に記録されている URL のみを掲載する。

### Primary（一次情報）
| URL | 何の根拠か |
|---|---|
| https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | WCAG 2.5.8 の正式要件・5 例外 |
| https://www.w3.org/WAI/WCAG21/Understanding/target-size.html | WCAG 2.5.5 の正式要件・4 例外 |
| https://github.com/w3c/wcag/issues/3714 | 2.5.5 と 2.5.8 の例外文言の逐語差分（W3C WCAG WG） |
| https://design-system.service.gov.uk/components/text-input/ | GOV.UK の text input コンポーネント仕様 |
| https://design-system.service.gov.uk/components/textarea/ | GOV.UK の textarea コンポーネント仕様 |
| https://primer.github.io/design/ui-patterns/forms/overview/ | GitHub Primer のフォーム設計方針 |
| https://ui.shadcn.com/docs/components/base/button | shadcn/ui Button の size variant 一覧・Tailwind v4 挙動注記 |
| https://github.com/anthropics/claude-code/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md | Anthropic 公式 frontend-design skill の構造 |
| https://github.com/Checklist-Design/skills | Checklist-Design/skills の Audit/Critique モード定義 |

### Secondary（二次情報・信頼できる要約/引用元）
| URL | 何の根拠か |
|---|---|
| https://baymard.com/blog/mobile-ux-ecommerce | モバイル検索の送信ボタン配置・オートコンプリート補正の実態調査 |
| https://github.com/jezweb/claude-skills/blob/main/plugins/frontend/skills/design-review/SKILL.md | コミュニティ製 design-review skill（7 カテゴリチェックリスト） |

### Blog（個人/企業ブログ・複数ソース一致で確度を補強）
| URL | 何の根拠か |
|---|---|
| https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/ | iOS Safari 16px ズーム閾値の解説（発端記事） |
| https://defensivecss.dev/tip/input-zoom-safari/ | iOS Safari ズーム回避（font-size: 16px 一本足） |
| https://takazudomodular.com/pj/zudo-tauri/docs/mobile/ios-input-auto-zoom/ | iOS Safari ズームの詳細条件・WCAG 1.4.4 との関係 |
| https://superdesign.dev/blog/apple-design-system | Apple HIG 数値まとめ（歴史的経緯の部分は反証済み） |
| https://ishadeed.com/article/clickable-area/ | 疑似要素によるタッチターゲット拡張パターン |
| https://modern-css.com/larger-touch-targets-without-changing-element-size/ | 同上（inset -8px パターンの具体例） |
| https://nikitahl.com/input-clear-button | クリアボタンのカスタム実装例（型サイズは WCAG 未達の注意点あり） |
| https://www.designmonks.co/blog/search-ux-best-practices | 検索フォーム UX の一般論（数値の裏取りなし） |
| https://github.com/ehmo/platform-design-skills | プラットフォーム別ルール集のファイル構造（規模主張は不確定） |

### Forum（フォーラム・議論スレッド）
| URL | 何の根拠か |
|---|---|
| https://github.com/shadcn-ui/ui/discussions/10788 | shadcn/ui Calendar/Button のサイズカスタマイズパターン 3 種 |

### Unreliable（信頼度が低いと判定・参考程度）
| URL | 何の根拠か |
|---|---|
| https://top10k.com/tool/touch-target-size-checker | MD3/HIG/WCAG の数値まとめ（未検証・裏取り必要） |
| https://mcpmarket.com/tools/skills/design-review | クレーム抽出結果 0 件（内容を確認できず） |

### 反証（counterSource として登場したのみ・敵対的検証エージェントが参照）
| URL | 何の根拠か |
|---|---|
| https://raw.githubusercontent.com/jezweb/claude-skills/main/plugins/frontend/skills/design-review/SKILL.md | jezweb skill の原文 raw ソース（44×44px 必須主張の反証に使用） |
| https://github.com/jezweb/claude-skills/tree/main/plugins/frontend/skills | 同リポジトリのディレクトリ一覧（分離コードレビュースキルの不在確認） |
| https://medium.com/@shoobe01/44-px-why-apple-is-wrong-6bd6f6846871 | オリジナル iPhone のアイコンは 57×57px という反証根拠 |
| https://bigmedium.com/ideas/iphone-tap-target-44.html | 同上（44pt という単位自体が Retina 以降という指摘） |
| https://gitlab.com/gitlab-org/gitlab/-/merge_requests/220666 | pointer:coarse スコープ限定への反証（実際の GitLab 修正 MR） |
| https://weblog.west-wind.com/posts/2023/Apr/17/Preventing-iOS-Textbox-Auto-Zooming-and-ViewPort-Sizing | 同上（無条件 16px 適用が標準という反証根拠） |

---

## 付記: 未回収セクションのまとめ

以下は明示的に「journal から回収できず（要追加調査）」と判定した項目。

- 質問 1: Material Design 3 の公式一次情報、Apple HIG の公式一次情報（JS レンダリングで WebFetch 不可）、MOJ Design System（検索自体が実施されていない）の実寸値
- 質問 4: `type="search"` のモバイルキーボード種別制御・autocomplete 属性の具体的な値一覧・送信中フィードバックパターン・レイアウトシフト回避の具体手法
- 質問 5: フォーカスリングの具体実装・デザイントークン化の具体パターン
- 質問 6: デザインレビュー／QA を人間の開発フローに組み込む運用ノウハウ（実施タイミング・チェックリスト粒度・エンジニアのコードレビューとの役割分担・失敗パターン）全般
