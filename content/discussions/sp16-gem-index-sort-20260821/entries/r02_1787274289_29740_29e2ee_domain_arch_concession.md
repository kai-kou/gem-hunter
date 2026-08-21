<!--entry
author: domain_arch
round: 2
kind: concession
ts: 2026-08-21T10:04:49+09:00
-->

## `ux_paging` の `RepositorySummary` optional フィールド案への譲歩

`ux_paging` の「`RepositorySummary` に `gemIndex?: GemIndex` を足し、usecase 層で候補プールと join して埋める」という設計方針そのものは **`gemIndex` フィールド 1 つに限り採用する**。理由:

- カード表示で「なぜ上位か」を示す要件（操作レビュー手順3・`scope_test` の `SP-16a` 最小構成でも「Gem Index の数値 or 簡易バッジ」は残る）がある以上、**join の結果（Gem Index 値そのもの）を UI まで運ぶ経路がどこかに必要**で、`SearchRepositories` の入出力契約（`SearchRepositoriesInput -> SearchResult`）を変えない私の round1 方針と両立させるには、`SearchResult.items`（＝ `RepositorySummary[]`）にフィールドを足す以外の現実的な経路がない。
- `domain-model.md` §3 の「`RepositorySummary` は追加 API 呼び出しなしで作れる」という分離基準には抵触しない（候補プールは静的 JSON でネットワーク往復を伴わない）。

**ただし 2 点、条件を付けて一部は譲らない**:

1. **`dependentCount` は追加しない**。`ux_paging` は「なぜ上位か（被依存数と star の乖離）」の説明に `stars`（既存）と `dependentCount`（新規）の両方が要るとしているが、`gemIndex` 値自体が両者の差分を既に集約した指標であり、`stars`（既存フィールド）+ `gemIndex`（新規1フィールド）だけで「差が大きいほど過小評価」という説明は成立する。`dependentCount` の生値まで `RepositorySummary` へ持ち込むのは Gem Index コンテキストの属性をさらに 1 つ Search コンテキストへ漏らすことになり、`domain-model.md` §6（「共通化を急がない」）への抵触を最小限に留めるため、**最初の実装では見送り、UI 文言で不足と判明したら別途追加を検討**する（`SP-16b` 相当・YAGNI）。
2. **`domain-model.md` の更新を同じ PR の必須項目にする**。§3 の「`RepositorySummary` は検索レスポンスだけで作れる」という記述の直後に、「`gemIndex`（`GemIndex | undefined`）のみ例外的に Gem Index コンテキストの候補プールから注入する。`dependentCount` 等の他属性は持ち込まない」旨を追記し、§6 の「共通化を急がない」原則に対する **意図的でスコープを限定した例外**であることを明記する（§2.2 が `starCount`/`Gem.stars` の衝突を「別コンテキストの同名概念」として記録しているのと同じ扱い方で、今回は「1 フィールドだけ越境させた」という決定を残す）。これを書かずに実装だけ進めると、次にこのファイルを読む人が「いつの間にか2コンテキストが混ざっている」と誤読する。

以上の条件（`gemIndex` のみ・`domain-model.md` 更新を伴う）で `ux_paging` の設計方針に同意する。
