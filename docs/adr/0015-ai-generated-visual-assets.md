# ADR 0015: AI 生成ビジュアルアセットを透過 WebP のまま配信する

- **状態**: **承認**
- **日付**: 2026-08-21 JST
- **対応要件**: `NFR-14`（画像の代替テキスト） / `NFR-1`（Core Web Vitals） / `NFR-6`（画像最適化）。ロゴ・待ち受け・0 件・404・OG 画像そのものの追加は与件・`prd.md` に固有の要件番号を持たず、Issue #347 のユーザー指示（「gpt-image-2 を利用して画像生成、活用するようにしてください」「言語ごとに画像を使い分けることも考えてください」）に基づく上乗せ
- **関連**: [議論記録](../../content/discussions/ui_image_assets_20260821/whiteboard.md)（`entries/r04_*_lead_consensus.md` 争点 B・C・`entries/r04_*_lead_verdict.md`・`entries/r02_*_lead_evidence.md`） / [UI/UX ガイドライン §7.4 / §8.6](../03_design/ui-ux/ui-ux-guidelines.md) / [`tools/ui-assets/README.md`](../../tools/ui-assets/README.md)

---

## 1. 文脈

Issue #347 は「gpt-image-2 を利用して画像生成、活用するようにしてください」「言語ごとに画像を使い分けることも考えてください」という 2 点をユーザーが明示した。適用箇所（ロゴ・favicon・未検索・0 件・404・OG）は専門チームの議論（争点 A）で確定済みで、本 ADR は残る 2 点——**アセットをどう生成・変換・配信するか**（争点 C）と、**文字焼き込み・言語別出し分けをどう扱うか**（争点 B）——の決定を記録する。

議論は round 3 で `perf_asset` が「gpt-image-2 の PNG を参照して、エージェントが SVG を手書きで再作図する」という案を出し、いったんそちらへ収束しかけた。lead は round 4 でこれを覆し、gpt-image-2 の生成物をそのまま配信する方針に差し戻した（§2）。

---

## 2. 決定

### 2.1. gpt-image-2 の生成物を透過 WebP のまま配信する（手書き SVG 再作図を採らない）

`tools/infographic/generate.py`（既存の画像生成 API 実装）をそのまま呼び、`background: "transparent"` でアルファ付き PNG を取得したうえで、新規 `tools/ui-assets/to_web_assets.mjs`（`sharp` 使用）で表示寸法へ縮小した透過 WebP へ変換して配信する。Next.js の `icon.*` file convention が WebP を受け付けない（`.ico`/`.jpg`/`.jpeg`/`.png`/`.svg` のみ）ため、**favicon だけ PNG**（`app/icon.png`）にする。既存の `app/favicon.ico` は古いブラウザ・クローラー向けのフォールバックとして削除せず維持する。

| アセット | 生成 | 配信ファイル | 表示寸法 |
|---|---|---|---|
| logo | 1024²・透過 | `public/images/logo.webp`（96px へ縮小） | 24×24 |
| favicon | logo と同じ生成物を流用 | `app/icon.png`（256px） | ブラウザ任せ |
| hero-idle | 1024²・透過 | `public/images/hero-idle.webp`（640px） | 最大 320px |
| empty-result | 1024²・透過 | `public/images/empty-result.webp`（256px） | 96〜120px |
| not-found | 1024²・透過 | `public/images/not-found.webp`（320px） | 160px |
| og-background | 1536×864・不透過 | `public/images/og-background.png`（1200×630 へ変換） | OG 1200×630 |

プロンプトの正本は `tools/ui-assets/prompts/*.txt` に置き、生成手順は `tools/ui-assets/README.md` に記録する。**中間生成物（1024² の原寸 PNG）はコミットしない**。画像生成は非決定的なため、再生成は「同じ結果の復元」ではなく「デザインを変えたいときの起点」であり、正本は git 管理下の配信ファイルそのものとする。

### 2.2. 画像内に文字を焼き込まず、装飾イラストはロケール非依存の 1 枚にする

logo / hero-idle / empty-result / not-found の 4 点は、文字を一切含めず `alt=""` 固定で配信する。ja/en で共用の同一画像 1 枚とし、ロケール別の意匠は持たない。

理由は 2 つある。

1. **WCAG 1.4.5（Images of Text）**: 画像に文字を焼き込むと、拡大・配色変更・読み上げのいずれにも硬直するテキストを増やすことになる
2. **locale は言語であって文化圏ではない**: 言語ごとに異なるモチーフを割り当てると、特定言語の話者に特定の文化的意匠を紐づけるステレオタイプ化のリスクを負う。文字なし・情報量ゼロの意匠差自体は WCAG 上許容されうるが、そのために資産を 2 倍持ち生成・レビュー・同期し続けるコストに見合わない

### 2.3. OG 画像だけは `next/og` の実行時テキスト合成でロケール別にする

OG 画像（`app/[locale]/opengraph-image.tsx`）は、`og-background.png`（文字なし・不透過）を背景に、`next/og` の `ImageResponse` が `getMessages(locale)` から取得したタイトルを **実行時に合成** する。これは画像への文字の焼き込みではないため、`messages/*.json` の文言を直せば画像側の作業なしに追随し、「テキストは新しいが画像は古い」というドリフトが構造的に起こらない。OG 画像は SNS クローラーが取得するのみでブラウザの DOM に現れないため、`alt` 属性・ライブリージョン・axe・Lighthouse のいずれの検査対象にもならない。

「言語ごとに画像を使い分ける」というユーザー指示は、この OG 画像の実行時テキスト合成をもって満たされたと判断する。

---

## 3. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **PNG を参照してエージェントが SVG を手書きで再作図する**（`perf_asset` round 3 案） | ユーザー指示は「gpt-image-2 を利用して……画像生成、活用する」であり、手書き再作図は gpt-image-2 をムードボードに格下げし、実際に配信される絵をエージェントの自作に置き換える。指示の実質的な不履行になる。加えて予算超過という前提も実測で成立しなかった（§4）うえ、LLM が手書きするベクターパスの品質は未検証で、実測済みの gpt-image-2 出力より優れる保証がない |
| **装飾イラスト（logo / hero-idle / empty-result / not-found）をロケール別に 2 枚持つ** | 文字なし・情報量ゼロの意匠差のために資産を 2 倍持って同期し続けるコストに見合わず、locale と文化圏を紐づけるステレオタイプ化のリスクを負う（§2.2） |
| **OG 画像も装飾イラストと同様に文字を焼き込んだ静止画にする** | ロケールが増える・文言が変わるたびに画像側の再生成が必要になり、`messages/*.json` とのドリフトが構造的に発生する |

---

## 4. 結果（この決定がもたらすもの）

### 良い方向

- gpt-image-2 の実際の生成品質がそのままユーザーに届く（未検証の中間工程を挟まない）
- 実測（`tools/infographic/generate.py` + `sharp`）で 256px の透過 WebP は約 10.6KB。表示寸法（24〜320px）に対して十分な余裕があり、`ui-ux-guidelines.md` §8.6 の予算（1 ページ合計 100KB・個別 30KB）を大きく下回る。**予算は制約になっていない**
- OG 画像のロケール追従が `messages/*.json` の更新だけで完結し、画像側の手作業を要しない

### 受け入れる代償

- 画像生成が非決定的なため、同一プロンプトで再生成しても既存の配信ファイルと完全一致する保証はない。デザインを維持したまま再生成したい場合は、既存の配信ファイルを正本として扱い、変更が必要になるまで再生成しない
- `tools/infographic/generate.py` と `tools/ui-assets/to_web_assets.mjs` の 2 段構成になり、生成 → 目視検証 → 変換という手作業のステップが残る（自動化は本 ADR の範囲外）

---

## 5. この決定に付随する未確認事項（実装着手時に潰す）

`content/discussions/ui_image_assets_20260821/entries/r04_*_lead_verdict.md` の `critical` を転記する。

| # | 未確認事項 | 影響 |
|---|---|---|
| 1 | `opengraph-image.tsx` が `readFile(process.cwd() + 'public/...')` で背景画像を読む方式が、OpenNext + Cloudflare Workers のビルドで成立するか | 成立しなければ背景埋め込みを諦め、`ImageResponse` 内で図形とテキストだけを組む形に落とす（ロケール別テキスト合成という要件自体は維持できる） |
| 2 | ロケール切替時に共有ヘッダー配下が remount されるか（`LocaleSwitchAnnouncer` の初回ガードに影響） | E2E で実機確認する。本 ADR の対象範囲外（`ui-ux-guidelines.md` §7.4 / ADR ではなく実装 Issue 側で扱う） |
