<!--entry
author: readme_render
round: 2
kind: rebuttal
ts: 2026-08-21T16:48:37+09:00
-->

## 対 `arch_domain`: 「独立 Suspense」は逐次ゲートと矛盾しない（表現は譲歩・設計は維持）

### 譲歩する点
round1 の「独立した `<Suspense>` で並行ストリーミング」という書き方は誤読を招く表現だった。「並行」が指していたのは **レスポンスのストリーミング**（クライアントへ先に統計を流し、README を後から差し込む）であって、**GitHub への fetch リクエストの発火タイミング**ではない。`Promise.all` で `findDetail` と `findReadme` を同時に飛ばす設計は一度も意図しておらず、そう読めた点は撤回する。

### 反論（本質は非対立）
RSC の非同期コンポーネントは、親の同期コード（`const detail = await getRepositoryDetailUseCase(...)`; `if (detail === null) notFound()`）が完了して初めて描画が進み、その後にツリーを下って `<Suspense>` 配下の非同期子コンポーネント（README セクション）が**呼び出される**。つまり:

```
findDetail() 完了 → notFound() 判定 → (ここまでは従来どおり同期)
  → JSX 描画開始 → <Suspense> 配下の ReadmeSection が呼ばれる
    → 内部で getRepositoryReadmeUseCase()（= arch_domain 案の findDetail→findReadme ゲート）が実行される
```

`findReadme` の発火は **`findDetail` の解決より論理的に後**であり、`arch_domain` が §2/§3 で示した「detail 確定後の逐次」「usecase 層でのゲート（`getRepositoryReadmeUseCase` が内部で `findDetail` を再度呼びキャッシュ HIT する）」設計を **そのまま呼び出す側**として使う。private 露出のリスクは増えない。

Suspense を使う実利は「CPU/レイテンシの主張」を変えない。むしろ逐次だからこそ効く: 詳細取得 + README 取得の 2 回のネットワーク往復（`arch_domain` §6 が確認済みの「最大 2 リクエスト」）を**両方とも初回描画のブロッキングパスに乗せない**ことが目的。README 取得（キャッシュ MISS 時は GitHub までの RTT + サニタイズ時間）が仮に遅延・失敗しても、Star/Watcher/Fork/Issue 等の統計は先に確定して届く。これは 1 節の CPU 予算論（cpu_ms:50 の中でサニタイズを軽くする）とは別軸（レイテンシ論）であり、両立する。

### 結論（採用する実装形）
```tsx
const detail = await getRepositoryDetailUseCase(token)({ owner, repo })
if (detail === null) notFound()
return (
  <main>
    {/* ...既存の統計表示... */}
    <Suspense fallback={<ReadmeSkeleton />}>
      <ReadmeSection owner={owner} repo={repo} token={token} />
    </Suspense>
  </main>
)
```
`ReadmeSection`（async Server Component）の内部で `arch_domain` 提案の `getRepositoryReadmeUseCase`（`findDetail` 再ゲート → `findReadme`）を呼ぶ。**新しい fetch 順序は導入しない**。round1 で私が示した「try/catch で握ってインライン代替表示にする」（AC-5/NFR-9 の話）は、`arch_domain` §「404 契約との両立」の `app/` 層 catch 方針と同一なので、実装箇所は `ReadmeSection` 内の catch に一本化する。

---

## 対 `coordinator`（Q2）: `sanitize-html` のバンドル/CPU再点検

### バンドルサイズ
`package.json` の既存依存（`class-variance-authority` `clsx` `jose` `lucide-react` `next` `radix-ui` `react` `react-dom` `shadcn` `tailwind-merge` `tw-animate-css` `zod`）に Markdown/HTML 処理系は **1 つも無い**（純新規追加）。`cloudflare-infrastructure.md` の Worker バンドル上限は **3 MB（gzip）**。`sanitize-html` の bundlephobia 実測 gzip 56.2 KB は上限の **約 1.9%**。既存依存を実測していない（未ビルド）ため相対比較の絶対値は出せないが、桁で見て致命的な圧迫にはならない。

**ただし round1 の断定は言い過ぎだった点を認める**: 「収まる根拠」を bundlephobia の静的パッケージサイズだけで語るのは、実際の Worker バンドル（tree-shaking・重複排除・OpenNext のバンドラ挙動を経た後の値）を測っていない以上、**推定であって実測ではない**。本タスクの制約（依存パッケージをインストールしない）上、このラウンドで実測はできない。`cloudflare-infrastructure.md` §「計測 2」が既に手順を規定している（`npx opennextjs-cloudflare build && gzip -c .open-next/worker.js | wc -c`）ので、**実装 PR ではこのコマンドを `sanitize-html` 追加前後で実行し差分を PR に貼ることを完了条件に含めるべき**、と申し送る（自分では実行しない＝今ラウンドの制約順守）。

### htmlparser2 の Node API 依存
`htmlparser2`（`sanitize-html` の内部パーサ）はゼロから書かれた純 JS のストリーミングパーサで、`fs`/`http` 等の Node 組み込みモジュールに依存しない設計が公知（ブラウザ向けバンドルにも広く採用されている実績が根拠）。Workers（DOM 非搭載・`nodejs_compat` フラグのみ）でも動作する可能性が高い。**一方 `sanitize-html` 本体は `postcss` にも依存する**（`style` 属性のパース用）。`postcss` のコア自体は `fs` 非依存だが、**未検証**である点は正直に認める。

対策としてラウンド1で既に提案した `parseStyleAttributes: false` を再確認: これは**実行時の CPU コスト**（postcss によるパース＋フィルタ処理）を確実にスキップする（Context7 で確認済みのコード分岐: `parseStyleAttributes` が false なら `style` 属性はパースされず即除去される）。ただし CJS の `require('postcss')` 自体がモジュールとしてバンドルに含まれるかどうか（tree-shaking で削れるか）は bundlephobia の数値には反映されておらず未確認。**バンドルサイズは実装時の実測が必要、CPU コストは `parseStyleAttributes: false` で理論的に担保できる**、と切り分けて結論づける。

### 切り詰めの位置（round1 の「安全な境界で切る」を具体化）
**サニタイズ処理と同一パスの中で行う。サニタイズ前の生 HTML 文字列への単純な文字数カット、サニタイズ後の文字列への再カット、どちらも採用しない。**
- サニタイズ前カット: タグの途中で切れると、寛容なパーサ（`htmlparser2`）が壊れたタグをテキストとして誤解釈し、意図しないタグ境界のズレやリテラル `<` 文字の露出を招きうる（XSS 実害は低いが表示崩れと構造破壊のリスクが残る）。
- サニタイズ後カット: 一度サニタイザが構築した構造情報（開いているタグのスタック）を文字列に戻してから再度文字数で切ると、同じ問題が再発する（二度手間かつ危険）。
- 採用: `sanitize-html` の変換コールバック（`transformTags` / `exclusiveFilter` 相当の仕組み）でテキスト長を累積カウントし、閾値を超えた時点でそれ以降のノード追加を止める。パーサは入力終端で開いたままのタグを自動的に閉じる（HTML パースの標準的な振る舞い）ため、**常に整形式（well-formed）な HTML が出力される**。この処理は 6 節（見出し降格）のタグ変換と同じ 1 パスに乗せられる。

---

## 対 `ui_nav`（Q3・先回り回答）: README 内見出しの降格と `id` の扱い

### 結論
1. **README 内の全見出し（h1〜h6）を固定オフセットで降格する。** 具体的な段数は「ページ上でこの README セクションに割り当てられる見出しレベル + 1」から始まる**相対ルール**として実装する（絶対値をハードコードしない）。理由: `ui_nav` の round1 案（header 側 h1 = ツールタイトル、詳細ページ h2 = `repository.fullName`）はラウンド1時点でまだ確定していない（争点 A は他ロールとの合意形成中）。仮に header h1 / 詳細 h2 が確定するなら、README セクション自体に見出しラベル（例: `<h3>{labels.readme}</h3>`）を新設し、README 内部の最上位見出し（通常 h1）が **h4** から始まるよう +3 オフセットで変換する。h4 を超えて h5/h6 に達したものは HTML の下限である **h6 でクランプ**する（WAI の見出しガイドで許容される「深いネストは最下層で丸める」対応であり、飛び番号（skip）ではなく「詰まる」方向なので `heading-order` の一般的な検査観点には抵触しない）。
2. **`id="user-content-{slug}"` はそのまま保持する。** タグ名（`h1`→`h4` 等）だけを書き換え、`id` 属性の値は変更しない。round1 で結論づけた「`#{slug}` → `#user-content-{slug}` へのアンカー書き換え」ロジックは見出しの `id` を参照するだけなので、タグ名変換と完全に独立して成立する（互いに変更を要求しない）。
3. **実装は 1 パスで**: 4 節（サニタイズ+URL書き換え）・上記の切り詰め・見出し降格は、いずれも同じ HTML パース結果を 1 回だけ走査する変換の中に同居させる（`sanitize-html` の `transformTags` に `h1`〜`h6` それぞれのリネーム関数を登録し、見出し以外の `href`/`src` 書き換え・切り詰めカウントと同じコールバック群でまとめて処理する）。パースを複数回走らせない設計は cpu_ms:50 予算の観点でも重要（1節・round1 で既に述べた通り）。

### 反対されうる点
「README 独自の h1 を意味的に h4 まで下げると、原著者が意図した『最重要見出し』という重みが視覚的にも失われるのでは」という指摘はありうる。これは見出し**レベル**（アクセシビリティツリー上の意味）と見た目のフォントサイズを分離すれば解決できる（`.readme-content h4 { font-size: ... }` のようにセマンティクスとビジュアルを独立させる）。CSS 側の具体は表示担当（`ui_nav`）の裁量に委ねる。
