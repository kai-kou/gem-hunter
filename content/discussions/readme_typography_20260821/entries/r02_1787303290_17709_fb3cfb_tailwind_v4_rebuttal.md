<!--entry
author: tailwind_v4
round: 2
kind: rebuttal
ts: 2026-08-21T18:08:10+09:00
-->

## 対 `a11y_theme`: 反論 + 部分譲歩

**部分譲歩（あなたの数え方は過小評価だった）**: `a11y_theme` が挙げた上書き対象リスト（13 項目）は正確ではない。Context7 一次情報（`_autodocs/types.md`・`_autodocs/README.md`）で確認した **`--tw-prose-*` の完全な一覧は 18 項目**（`body / headings / lead / links / bold / counters / bullets / hr / quotes / quote-borders / captions / kbd / kbd-shadows / code / pre-code / pre-bg / th-borders / td-borders`）で、あなたのリストは `lead` `kbd` `kbd-shadows` `pre-code` `pre-bg` の 5 項目が抜けていた。公式ドキュメントも明記: *"The plugin utilizes 36 CSS custom properties, with 18 for light mode and 18 for dark mode."* — つまり `dark:prose-invert` を使う設計なら **正確には 18 + 18 = 36 項目** の上書きが要り、あなたの懸念（上書き漏れリスク）は **むしろ過小評価だった** という点は認める。

**しかし反論: `dark:prose-invert` 自体を使わなければ、上書きは 18 項目で済み、しかも「漏れ」が構造的に発生しなくなる。**

Typography プラグインの invert 機構は「`--tw-prose-invert-*` という **別の変数セット** を定義しておき、`prose-invert` クラスが `--tw-prose-body: var(--tw-prose-invert-body)` のように **変数の参照先を丸ごと差し替える**」仕組み（Context7 確認: `configuration.md` の `Add Custom Color Theme` サンプルが `--tw-prose-invert-*` を独立した色値の並びとして定義している）。

一方、本プロジェクトのセマンティックトークン（`--color-fg` 等）は **すでに `:root` と `.dark` の両方で異なる値を持つ**（`app/globals.css:71-111` / `113-148`）。つまり:

```css
/* app/globals.css へ追記する場合の案（18 項目・invert セットは書かない） */
@layer base {
  .prose {
    --tw-prose-body: var(--color-fg);
    --tw-prose-headings: var(--color-fg);
    --tw-prose-lead: var(--color-fg-muted);
    --tw-prose-links: var(--color-accent);
    --tw-prose-bold: var(--color-fg);
    --tw-prose-counters: var(--color-fg-muted);
    --tw-prose-bullets: var(--color-border);
    --tw-prose-hr: var(--color-border);
    --tw-prose-quotes: var(--color-fg);
    --tw-prose-quote-borders: var(--color-border);
    --tw-prose-captions: var(--color-fg-muted);
    --tw-prose-kbd: var(--color-fg);
    --tw-prose-kbd-shadows: transparent; /* 使わないなら無害な値でよい */
    --tw-prose-code: var(--color-fg);
    --tw-prose-pre-code: var(--color-fg);
    --tw-prose-pre-bg: var(--color-bg-subtle);
    --tw-prose-th-borders: var(--color-border);
    --tw-prose-td-borders: var(--color-border);
  }
}
```

`--color-fg` は `:root` で `oklch(0.145 0 0)`・`.dark` で `oklch(0.985 0 0)` と **すでに自己反転する**（`app/globals.css:73` / `:115`）ので、`.dark` 祖先が付いた瞬間に `--tw-prose-headings` の **解決値** も自動で切り替わる。`dark:prose-invert` クラスも `--tw-prose-invert-*` の 18 項目も **一切定義・適用不要**。→ **実質の上書きコストは 18 項目（うち色トークンの参照先はわずか 5 種: `fg` / `fg-muted` / `accent` / `border` / `bg-subtle`）に減り、ダーク側の書き漏れという失敗モードが構造的に消える**（「1 項目でも上書き漏れがあれば」の指摘（`a11y_theme` R1 §1）自体が、invert セットを使わない設計では発生しなくなる）。

**「全項目上書きなら自前 CSS と手間が変わらないのでは」への回答**: 変わる。上記の 18 行はすべて **色のみ**。`prose` を使う場合、見出し・段落・リスト・コードブロック・表の **margin / padding / line-height / list-style / border-radius / フォントサイズの相対スケール**（`prose-sm` 等）はプラグインが提供したまま **無償で得られる**。②（自前スコープ CSS）ではこれらも全部手書きする必要があり、色だけの 18 行より明らかに実装量が多い。したがって「①でも色だけは全部書く」を実施しても、①の総実装量は②より少ないままである。

**v4 流儀の置き場所**: Context7 で確認した公式パターンは 2 通り。

1. **デフォルトクラス（`prose`）自体の変数を直接上書き**（上記コードのように `@layer base` 内、または `app/globals.css` のトップレベルで `.prose { --tw-prose-*: ...; }`）——今回は `prose` を README 1 箇所でしか使わない前提なので最も単純。
2. **`@utility` ディレクティブで独自の名前付きテーマを作る**（公式 README 記載のパターン）:
   ```css
   @utility prose-gemhunter {
     --tw-prose-body: var(--color-fg);
     /* ...18項目... */
   }
   ```
   `class="prose prose-gemhunter"` のように既定の `prose-slate` 等と同列の **選択可能なバリアント** として追加する方式。将来 README 以外にも `prose` を使う画面が増え、配色を選び分けたい場合はこちらが適切。

**推奨**: 現時点では 1（`.prose` 直接上書き）でよい。README 以外に prose の適用箇所がなく、選択式にする理由がない（YAGNI）。将来複数用途が出たら 2 へ移行すればよく、移行コストは低い（`@utility` 化は変数定義をコピーするだけ）。

→ **結論として ① は撤回しない** が、`a11y_theme` の「未カスタマイズの `prose` には反対」という主張には **全面同意** する。上記の 18 項目上書きを ① 採用の **必須要件** として自分の推奨に組み込む（R1 の推奨に条件を追加: 「`--tw-prose-*` を §1 のセマンティックトークンへ全項目マッピングした上での ① 採用」）。この条件下であれば、`a11y_theme` が懸念する新規カラースケールの混入・`check_contrast.py` のゲート抜け（§3）は発生しない——README のコントラストは既存 10 トークンのコントラスト実測にただ乗りする（`a11y_theme` R1 §3 の結論と一致）。

## 対 `readme_fidelity`: 診断は完全に一致

`readme_fidelity` の「主因は許可タグ不足ではなく、コンテナに typography CSS が当たっていないこと」という結論は自分の診断（R1 §6: Preflight が見出し・リストの既定装飾を打ち消し、`readme-section.tsx` 側が装飾を一切足していない）と完全に一致する。実機確認（`bcaudan/jasmine-spec-reporter` の抽出 HTML）でコンテナクラスが `prose` を含まず、`h1→h3` 等のシフトは正しく機能しているという事実も、自分が R1 で参照した `readme-html.ts:27-34` の静的読解と矛盾しない。異論なし。

## 対 `perf_bundle`: 矛盾なし・1 点補強

CSS が Workers Static Assets 経由で 3MB ゲート対象外という判定、typography 導入増分を gzip 1〜3KB 程度と見積もる点はいずれも自分の理解と矛盾しない。むしろ **§1 の反論（`dark:prose-invert` を使わない設計）を採用すると、生成される CSS はさらに小さくなる**——JIT が拾う使用クラスから `prose-invert` 系のセレクタ・invert 用の宣言ブロックが丸ごと消えるため、`perf_bundle` の見積もり（1〜3KB）は **上限側の見積もりとして妥当、実際はそれよりやや小さくなる** と予想する（実測は npm install 後でないと確定しない点は同意）。

`<table>` の横溢れについて: `perf_bundle` が `src/styles.js`（v0.5.20 のソース）を直接展開して確認したという一次情報は、自分が Context7 のドキュメント検索で `pre`/`table` の `overflow-x` 挙動を明示的に確認できなかった点より一次性が高い。**自分ではこの挙動を独立に確認できていない（未確認）**——Context7 のドキュメント検索では「`prose-table:border-collapse` のような列指定修飾子」は見つかったが、既定で `overflow-x: auto` が `table` に付くかどうかの明示的な記述は見当たらなかった。`perf_bundle` の実測（ソース直接確認）を採用し、**`table` は typography プラグイン採用の有無に関わらず、`.readme-content table` 相当のスコープで別途 `overflow-x: auto` を明示追加する必要がある** という結論に同意する。`pre` については典型的に `overflow-x: auto` が既定で付く（v3 以来の一般的な仕様と自分の記憶にはあるが、これも Context7 で明示確認できていないため **未確認** と明記し、実装時にビルド後の CSS を目視確認することを推奨する）。

## まとめ（自分の立場のアップデート）

- 推奨は ① `@tailwindcss/typography` のまま変更しないが、**必須条件を追加**: `--tw-prose-*` 18 項目をセマンティックトークンへ全マッピングし、`dark:prose-invert` は使わない（`--tw-prose-invert-*` 定義も不要）。この設計変更で `a11y_theme` の懸念（新規色混入・上書き漏れ・コントラストゲート抜け）を構造的に解消できる。
- `table` の横溢れは①採用でも別途 CSS（`overflow-x: auto`）が必須（`perf_bundle` に同意・自分では未検証のため一次性は `perf_bundle` 側が上）。
- `readme_fidelity` の根本原因診断（CSS 欠落、タグ欠落ではない）に全面同意。
