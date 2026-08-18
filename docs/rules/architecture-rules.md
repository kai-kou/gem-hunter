# 実装時アーキテクチャ規律（Clean Architecture / DDD / TDD の実行ルール・Warm 層）

> **アプリコードを書く / 変更するスプリントに着手したら、まず本ファイルを読む**（`SD-4` の読む順序に組み込み済み）。
> 本ファイルは **判断のためのチェックリスト** であり、定義の正本は各 SSOT に置く。
>
> | 何の正本か | SSOT |
> |---|---|
> | 層・依存規則・ディレクトリ・ポート | [`docs/03_design/architecture/application-architecture.md`](../03_design/architecture/application-architecture.md) |
> | ドメイン語彙・値オブジェクト・ACL 変換表 | [`docs/03_design/data-model/domain-model.md`](../03_design/data-model/domain-model.md) |
> | テストの層分担・道具・下限 | [`docs/04_development/testing-strategy.md`](../04_development/testing-strategy.md) |
> | TDD の規律（Red → Green → Refactor） | [`sprint-development-rules.md`](./sprint-development-rules.md) `SD-2` |

---

## 1. 「このコードをどこに置くか」の判定（迷ったらこの順に問う）

```
① 外部世界（HTTP・キャッシュ・事業者バインディング・環境変数）に触るか？
     → はい: src/infrastructure/（GitHub なら github/・事業者固有なら platform/）
② React の描画か？
     → はい: src/ui/（app/ にはルーティングと受け渡しだけを置く）
③ 「1 つの操作」を最初から最後まで完遂する手続きか？
     → はい: src/usecases/
④ 業務上の意味を持つ値・規則・計算か？
     → はい: src/domain/
⑤ どれでもない（純粋な整形・型ヘルパー）
     → src/shared/
```

🔴 **③ と ④ の見分け方**: 「GitHub が無くても意味が通る規則」ならドメイン（例: 表示件数は 20/50/100 のいずれか）。「この画面の操作としての段取り」ならユースケース（例: キャッシュを見て無ければ検索して詰める）。

---

## 2. 毎回守る 7 つ（違反はセルフレビューで Error になる）

| # | 規律 | 破ったときに何が起きるか |
|---|---|---|
| **A-1** | `src/domain/` は **何も import しない**（`next` / `react` / `zod` を含む） | 中心がフレームワークに縛られ、差し替えもテストもできなくなる |
| **A-2** | ユースケースは **ポートを引数で受け取る**（実装を `import` で掴まない） | テストで実 API を叩くしかなくなる |
| **A-3** | `app/` / `src/ui/` から `src/infrastructure/` を直接 import しない（`src/composition/` 経由） | UI とデータ源が癒着し `W-1` が壊れる |
| **A-4** | 事業者固有バインディングは `src/infrastructure/platform/` の中だけ | `NFR-21` / `INF-5` 違反。事業者を替えられなくなる |
| **A-5** | GitHub API へのアクセスは `src/infrastructure/github/` の中だけ | `NFR-16` 違反 |
| **A-6** | 外部レスポンスは **検証してから** ドメインへ入れる（`zod`） | 上流の変更が画面の崩壊として現れる（`NFR-19`） |
| **A-7** | ユースケースの引数は **値オブジェクト**（生の `string` / `number` を渡さない） | 不正値が奥まで届き、境界での防御が効かなくなる |

機械チェック: `python3 tools/check_architecture_boundaries.py`（PR 前の `self_review_check.py` から自動実行）。

---

## 3. DDD で守るのは 3 つだけ

1. **語彙**: [ドメインモデル](../03_design/data-model/domain-model.md) §2 に無い語を識別子に使わない。**新語は先にドキュメントへ足す**
2. **変換**: GitHub の語（`subscribers_count` / `pushed_at` 等）は ACL で必ず言い換える（§2.2 の表が正本）
3. **不変条件**: 値オブジェクトのスマートコンストラクタで守る（型注釈だけで満足しない）

🔴 **採らないもの**: 集約ルート・リポジトリパターン（永続化）・ドメインイベント・CQRS。DB を持たない MVP では純粋な過剰設計（ドメインモデル §1）。

---

## 4. TDD の最低ライン

- **テストを先に書く。** `test:` コミット → `feat:` コミットの順に分ける（順序違反はセルフレビューが Warning を出す）
- **外側 = 操作レビュー手順の E2E、内側 = ユニット**（二重ループ・テスト戦略 §5）
- **`async` Server Component はユニットで描画しない**（公式に未対応）。E2E に回すか、ロジックをユースケースへ出す
- 上位層のテストで **`vi.mock` を使いたくなったら設計を直す**（フェイクのポート実装を渡す）
- 🔴 **実行していないテストの結果を報告しない**（L-113）

---

## 5. 完了・成功の定義

- [ ] §1 の判定に沿った場所にファイルが置かれている
- [ ] §2 の 7 項目に違反がない（`check_architecture_boundaries.py` が PASS）
- [ ] 新しいドメイン語を導入したなら [ドメインモデル](../03_design/data-model/domain-model.md) を同じ PR で更新した
- [ ] 触れた `AC-n` に対応するテストがある（テスト戦略 §6）
