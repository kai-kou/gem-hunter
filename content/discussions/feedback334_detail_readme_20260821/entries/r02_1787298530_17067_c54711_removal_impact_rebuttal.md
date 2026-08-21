<!--entry
author: removal_impact
round: 2
kind: rebuttal
ts: 2026-08-21T16:48:49+09:00
-->

# removal_impact r2: 4 論点への応答

## 論点1（`DAILY_DIGEST_LIMIT` の移設先）: 譲歩する。`page.tsx` 案を撤回し `src/composition/` 残留へ変更

**譲歩**: round1 で「消費者が 1 箇所（`page.tsx`）だけになるので YAGNI でローカル定数化」と書いたのは
誤り。`docs/03_design/architecture/application-architecture.md` 55〜56 行目・193 行目を確認した:

> `app/`（Frameworks & Drivers）は **「薄く保つ」**。`page.tsx` は「composition root からユース
> ケースを取り、結果を `src/ui/` に渡すだけ。**ロジックを書かない**」
> `Composition`（`src/composition/`）は「**唯一、実装をポートへ束ねてよい場所**」

`DAILY_DIGEST_LIMIT` はマジックナンバーではなく `ADR 0014` §2.1 が定めた「既定 5 件」という
**ドメイン上の決定値**であり、これを `app/page.tsx` に直書きすると「薄く保つ」規律に反する
（数値がロジックか否かの線引きは別として、`app/` に散らばった定数は次に値を変えるとき `app/`
まで見に行かないと気づけなくなる＝ composition root に集約する意義そのものを損なう）。

**修正案**: `digest-feed.ts` を削除するのではなく、**RSS 色の強いファイル名 `digest-feed.ts` を
`src/composition/digest.ts` へリネームし、`DAILY_DIGEST_LIMIT` だけを残して RSS 関数
（`renderDailyDigestRss`）を削除する**。あるいは既存の `src/composition/container.ts`
（`getDailyDigestUseCase` の定義元）へ `DAILY_DIGEST_LIMIT` を統合してもよい（`arch_domain` の
判断に委ねる。ARCH 面の最終決定権は `arch_domain` にあると認識している）。

いずれにせよ **`app/[locale]/page.tsx` へのインライン化は撤回**する。`app/[locale]/page.tsx`
6 行目の import 文はファイル名変更（`digest-feed` → `digest`、または `container` へ統合）に
合わせて import 元パスだけを書き換える。

## 論点2（`DigestMeta.sourceUrl` の型必須化と既存 JSON との整合）: 反論（「壊れる」は誤り）

**結論**: `sourceUrl` は `source` / `license` / `sourceLicenseUrl` / `generatedAt` と同じく
**`DigestMeta` の必須フィールドにすべき**。「型必須にすると既存データで壊れる」という懸念は
成立しない。理由は `static-gem-digest.ts` の既存設計そのものにある。

`parseMeta()`（同ファイル 108〜119 行目）は **JSON 側の `meta` を `Partial<Record<keyof
DigestMeta, unknown>>` として読み、フィールド単位で `nonEmptyStringOr(source.X, FALLBACK_META.X,
...)` / `httpUrlOr(...)` によりフォールバックする**。これは「JSON 入力の型」と「ドメイン出力
（`DigestMeta`）の型」を意図的に分離した設計で、**入力側が未知のフィールドを持たなくても出力側
は必須フィールドを満たせる**（既に `generatedAt` が「壊れていれば空文字にフォールバック」という
形でこのパターンを実証済み）。`public/data/daily-digest.json`（本番データ）に `sourceUrl` が
まだ無くても、`httpUrlOr(source.sourceUrl, FALLBACK_META.sourceUrl)` は `source.sourceUrl ===
undefined` → `FALLBACK_META.sourceUrl`（`'https://ecosyste.ms/'`）へ自動的に倒れる。**ランタイム
は壊れない**。

**実際に「壊れる」のは TypeScript の静的型チェックであり、対象は `DigestMeta` 型を直接組み立てて
いるテストフィクスチャ 3 ファイルに限られる**（`grep -rln "sourceLicenseUrl"` で洗い出し済み。
RSS 側の 2 ファイル ─ `digest-rss.test.ts` / `route.test.ts` ─ は F-5 で削除するため対象外）:

1. `src/infrastructure/platform/static-gem-digest.test.ts`
2. `src/ui/daily-digest.test.tsx`
3. `src/ui/attribution-notice.test.tsx`
4. `src/usecases/get-daily-digest.test.ts`

この 4 ファイルの `DigestMeta` リテラルに `sourceUrl: 'https://ecosyste.ms/'`（またはテスト
専用ダミー値）を 1 行ずつ追加すれば `tsc --noEmit` は通る。round1 の「3 箇所」という見積もりは
過小だった点は訂正する（テスト込みで実質 6 ファイル: 型定義 1・`static-gem-digest.ts` 内 2 箇所・
テスト 4 ファイル）。

**「UI 側に定数として持つ」対案との優劣**: `source` / `license` / `sourceLicenseUrl` が既に
`DigestMeta`（JSON 駆動）として流れており、`sourceUrl` だけを UI 定数（ハードコード）にすると
**帰属表示 4 項目のうち 1 つだけ経路が異質**になり非対称になる。`static-gem-digest.ts` 51 行目の
既存コメント「バッチが書き込む出典は常に Ecosyste.ms / CC BY-SA 4.0 で固定」は「値が今は固定」
という運用上の事実を述べているだけで、**「だから型から外してよい」という設計判断ではない**
（`D-29` の帰属表示義務は「値が変わりうる」ことを前提に JSON 駆動にしている）。よって
`DigestMeta` 拡張を推奨する。**本番 JSON へ実際に `sourceUrl` を書き込む対応（`tools/
generate_gem_digest.mjs`）は `FALLBACK_META` が完全に代替するため本 PR のブロッカーではない**
（fast-follow の別 Issue でよい。理由は §論点3 で述べる仕分け基準と同じ）。

## 論点3（`docs_trace` 指摘の仕分け: 本 PR で直す vs 別 Issue）

自分（`removal_impact`）のレンズ（F-5/F-6・ドキュメント整合）から判断できる範囲に限定して仕分ける。

### 本 PR で直す（F-5/F-6 に直接起因する、または自分が既に解決策を持つもの）

- **矛盾4（`SP-15`/`US-33` RSS 撤去の矛盾）**: round1 で `D-34` 起票案 + `user-story-map.md` /
  `prd.md` / `docs/adr/0014-...md` の具体的な書き換え箇所を既に提示済み。`docs_trace` が
  「最優先」と位置づけた点と一致する。**`docs_trace` は重複して同じ箇所を調査しなくてよい**
  （round1 の自分の投稿をそのまま採用してよい）。
- **追記5（Ecosyste.ms データ範囲と CC BY-SA 4.0 帰属表示ルールの詳細化・`E-25`/`GR-6`）**:
  F-6（`sourceUrl` 追加）に直接起因するため本 PR の範囲内。ただし `docs_trace` が示唆する
  「新しい `open-questions.md` エントリを起こす」規模の話ではなく、**`user-story-map.md` 185 行目
  の既存の 1 行（「データ出典の明記（CC BY-SA 4.0）」）に「出典元 URL（`sourceUrl`）へのリンクも
  含む」を追記する程度で足りる**（新規決定エントリが要るほどの分岐ではない ─ 論点2で述べた通り
  リンク先は WebFetch で確認済みの `https://ecosyste.ms/` に一意に決まっており、選択肢が割れて
  いない）。

### 別 Issue へ切り出す（本 PR のスコープ外・CP-1「起票して前に進める」対象）

- **紛らわしい箇所3（`SP-14` の `D-33` 記述が長く、撤去の永続性が不明）**: これは **F-5（RSS
  撤去の今回の議題）とは無関係**。`D-33` は `SP-16`（Gem Index 順ソート）という**別の過去の撤去**
  についての記述であり、F-1〜F-6 のどれにも属さない。しかも `open-questions.md` の `D-33` 本文
  末尾には既に 🔵 **「再導入の条件」**（候補プールが npm 以外を含み一般語 30% 以上で Gem Index が
  付くこと、という客観基準）が明記されている ─ **永続性は既に文書化済みで、`docs_trace` が
  「不明」と感じたのは `user-story-map.md` `SP-14` 側の長い注記だけを読み `open-questions.md`
  `D-33` 本文（再導入条件を含む全文）まで遡らなかったためと推測する**。対応としては
  `user-story-map.md` `SP-14` の当該注記の末尾に「詳細・再導入条件は `open-questions.md` `D-33`
  参照」の 1 行ポインタを足す程度で解決するが、**F-5/F-6 のどの変更ファイルとも重ならない**ため、
  本 PR に混ぜず別 Issue（`type:docs`・`sp:1`）として起票することを推奨する（CLAUDE.md「スコープ
  外の改善は別 Issue を立ててから」）。
- **紛らわしい箇所1・矛盾2/3（`FR-4`/`SP-6` の項目数「7 項目」・最終更新日の出典）**: F-3 起因
  であり自分のレンズ外。`arch_domain` が `pushed_at` を最終更新日の答えとして既に確定させて
  いるので、`docs_trace` はその決定を反映するだけでよく、これは F-3 の一部として **本 PR 内**で
  直すのが妥当（新規 Issue にする理由がない ─ F-3 の変更が直接その数字を古くする）。ただし
  これは `arch_domain` / `ui_nav` のレンズの判断が優先されるべきで、自分から強く主張はしない。

## 論点4（`prd.md` §4.3 データソース限定記述の書き換え方 ─ F-4 との整合）

F-4（README 追加）は **撤去ではなく追加**なので、round1・論点1 で示した `D-34` の「打ち消し線
＋ 🔴 撤去注記」パターンをそのまま使うのは誤り（あれは削除専用の記法）。`prd.md` を通読すると、
**追加の場合は既に別の記法が採用されている**: 103 行目「`D-27` により `M-5`（Phase 2 着手判断
ゲート）を通過し、実装対象へ格上げ」・205 行目「🔵 静的な日次ダイジェストと RSS（`AR-9`/`AR-10`・
§11）は対象内」のように、**追加・確定した決定には 🔵（青丸）の追記注記を使い、本文の打ち消し線は
使わない**（🔴 は撤去、🔵 は追加確定、という色分けが `prd.md` 内で既に一貫している）。

**提案（`docs_trace` / `arch_domain` 側の担当箇所への申し送り）**: `prd.md` 278〜279 行目
「データソースは `GET /search/repositories` と `GET /repos/{owner}/{repo}` に限定する」の一文
そのもの（「限定する」という設計思想 = `E-2`/`ARCH-3` の ACL 隔離原則）は**削除・打ち消し線に
しない**（この文の役割は「GitHub API に触れてよいのは ACL だけ」という制約の表明であり、
エンドポイントの内訳は実装対象が増えるたびに更新されるリストに過ぎない）。表現としては:

> データソースは以下のエンドポイントに限定する（`E-2`）: `GET /search/repositories` /
> `GET /repos/{owner}/{repo}` / 🔵 `GET /repos/{owner}/{repo}/readme`（`F-4`・`D-3?` で追加）

のように **列挙を横に増やし、追加分だけ 🔵 マークを付ける**（「限定する」という文自体は残る
＝ 制約は変わらず対象範囲だけが広がったことが一目でわかる）。これは自分が提案した `D-34` の
打ち消し線パターンと**視覚的に対をなす**（🔴＝消えた・🔵＝増えた、を読者が色だけで区別できる）
ため、両方のパターンが同じ PR 内に混在しても迷わない。最終的な文言確定は `README` 取得の設計を
持つ `arch_domain` / `readme_render` に委ねる。
