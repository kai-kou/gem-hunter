# HTTP クライアント集約判定ルール（HTTP Client Consolidation Rules・SSOT）

> **このファイルは「`tools/` 配下に似た HTTP クライアント実装（ページネーション・PR 除外・
> gh フォールバック等）が複数見つかったとき、集約するかどうかをどう判定するか」の唯一の正本
> （SSOT）である。**（Issue #825・PR #824 のレトロスペクティブ由来）
>
> **タスク依存ルール**（Hot 層に常駐させない）: `tools/github_rest.py` / `tools/github_api.py` /
> 類似の共通クライアントモジュールを新設・改修するとき、または新しいツールで GitHub REST /
> gh CLI 呼び出しを書く前に Read する。

---

## 0. なぜ基準が要るか（実測された取りこぼし）

PR #824 で `tools/github_rest.py` を新設し、GitHub REST のページネーションと PR 除外を集約した。
その **同じセッション内で「名指しされているのに集約も見送り記録もされていない実装」が 3 回連続で
見つかった**（`tools/check_roadmap_status.py` / `tools/gh_shim.py` / `tools/triage_improvements.py`）。

根本原因は 3 層:

- **直接原因**: 集約対象の洗い出しを Issue 本文の `grep` 結果に依存し、実装時に全数を突き合わせなかった
- **中間原因**: 「同型と確認できたものだけ集約する」という基準が主観的で、判定の再現手順が無かった
- **根本原因**: 集約の判定枠（何を見て対象/非対象を決めるか）がどこにも明文化されておらず、
  `tools/github_rest.py` の docstring という **成果物の中** にしか残っていなかった。新しいツールを
  追加する人が参照する導線が無いため、同じ判定が再現できず取りこぼしが繰り返された

本ファイルは、その場しのぎで各実装の docstring に書き足すのをやめ、**判定の型そのものを 1 箇所に
固定する**ために作った。

---

## 1. 判定軸（5 つ）

似た実装を見つけたら、以下 5 軸すべてを **表にして** 当てはめる（結論だけを書かない・§3 参照）。
1 つでも「違う」判定が出れば、無理に 1 つの抽象へ寄せない（YAGNI）。

| # | 軸 | 見るもの |
|---|----|----------|
| 1 | **認証方式** | `urllib` + `GH_TOKEN`/`GITHUB_TOKEN` を自前で組み立てるか、`gh api` サブプロセス経由で認証するか。後者はトークンをプロセス内で扱わないため、前者の実装へ寄せると認証の責務境界が壊れる |
| 2 | **打ち切り条件の性質** | ページ数上限（`max_pages`）か、件数上限（`limit`）か、空バッチで打ち切りか、応答内メタデータ（`result_info` 等の総件数・総ページ数）か。継続判定の形が違うと、共通化すると「使われない方の分岐」を常に抱える |
| 3 | **エラー時に倒れる向き** | 取得できなかったページがあるとき、取得済み分を返す fail-open か、判定不能として打ち切る fail-closed か。既存挙動を変えずに集約できるかを左右する |
| 4 | **既存 self-test のモック差し替え点を壊さずに移行できるか** | 呼び出し元が `globals()["_http_get"]` 等の module-level 関数をモック差し替えている場合、集約すると差し替え口が変わり既存 self-test の書き直しが要る。書き直しコストが小さいか大きいかを見る |
| 5 | **再テストコストが重複削減効果に見合うか（YAGNI）** | 1 ファイル内で完結し他から import されない実装を、わざわざ外出しして再テストする価値があるか。すでに「その実装専用の self-test」が整備済みなら、重複削減の便益が薄いことが多い |

---

## 2. 判定の型（決定木ではなく「全軸を見る」）

```
似た実装を見つけた
  ↓
5 軸すべてを表にして当てはめる（§3 のテンプレート）
  ↓
軸 1〜4 が全て「同型」→ 集約する（軸 5 で再テストコストが極小なら尚更）
軸 1〜4 のいずれかが「異なる」→ 原則集約しない。ただし「形（インターフェース設計）だけ踏襲する」
                                （実体は共有しない）という選択肢もある（例: `#476` の判断）
軸 1〜4 が全て「同型」だが軸 5 で再テストコストが見合わない → 見送ってよい（理由に軸 5 を明記）
  ↓
いずれの結論でも、判定した実装の docstring（または呼び出し元ファイルの docstring）に
「集約したもの」または「集約しなかったもの」として記録する（実体は書かない・本ファイルを参照するだけ）
```

**「同型に見えて実は違う」の典型パターン**（既出の実例）:

- 認証方式が違う（`urllib` vs `gh api` サブプロセス） — 例: `tools/gh_shim.py` / `tools/generate_project_context.py`
- 打ち切り条件の形が違う（ページ数上限 vs 件数上限 vs 応答内メタデータ） — 例: `tools/gh_shim.py`（件数上限）/ `tools/retire_preview_aliases.py`（Cloudflare `result_info`）
- 1 ファイル内で完結し、既に self-test 済みの独立実装 — 例: `tools/check_pending_pr_reviews.py` の `_rest_get_all_pages`

---

## 3. 記録の書き方（実体は 2 箇所に置かない）

判定結果は、判定対象のコードが属するモジュールの docstring に **簡潔に** 書く。書く内容は
「①どの軸で②どう判定したか③結論」の 3 点で十分（軸の定義そのものは本ファイルへのリンクで済ませる）。

```
- **`tools/xxx.py` の `yyy()`**: 認証方式は同型（urllib + GH_TOKEN）だが、打ち切り条件が
  件数上限で `paginate_json_array()` と異なるため集約しない（判定基準は
  `docs/rules/http-client-consolidation-rules.md`）。
```

🔴 **判定基準（5 軸の定義・判定の型）は本ファイルにしか書かない。** `tools/github_rest.py` /
`tools/github_api.py` の docstring は、この基準を **個別の実装へ当てはめた結果** だけを書き、
基準そのものを逐語コピーしない（コピーすると更新のたびに両方直す必要が生まれ、片方だけ古くなる）。

---

## 4. 新規ツール追加時のチェックリスト

新しく GitHub REST / gh CLI を呼ぶツールを書く前に:

- [ ] `tools/github_rest.py`（純粋な REST ページネーション・PR 除外）と `tools/github_api.py`
      （gh → urllib フォールバックの共通化）の docstring を読み、同じパターンが無いか確認した
- [ ] 同じパターンがあれば §1 の 5 軸で当てはめ、集約するか判定した
- [ ] 集約しない場合、判定結果を §3 の形式で当該ツールの docstring に 1 行以上記録した
- [ ] Cloudflare API 等、GitHub REST と「ページネーション」という言葉だけが同じ別レスポンス仕様
      （応答内メタデータ方式）を意図的に分けたままにするという既存決定（#476）を上書きしていない

---

## 5. 「名指しされた対象の全数」を機械的に確認する手順（Issue #825 の再発検知）

Issue 本文や PR レトロスペクティブが「集約対象かもしれない」と名指しした実装の一覧に対して、
各対象が「集約済み（`github_rest` / `github_api` の関数を実際に import・呼び出している）」か
「見送り記録済み（docstring に判定結果がある）」のいずれかであることを、次のコマンドで確認する。

```bash
# ① tools/ 配下で「PR 除外」の自前実装（`"pull_request" in item` / `"pull_request" not in item`
#    という membership test の実際のイディオム）を洗い出す。`pull_request` という語の言及
#    （mcp__github__pull_request_read・pull_request_url 等）まで拾うと無関係なノイズが
#    大量に混ざるため、実際の判定式の形に絞る。
grep -rln '"pull_request" in \|"pull_request" not in ' tools/*.py | grep -v "^tools/github_rest.py"

# ② ①の各ファイルが github_rest / github_api を実際に import しているか確認する
#    （import していれば集約済みとみなせる。exclude_pull_requests をまだ呼んでいなくても、
#    同モジュールを import した状態で個別に判定記録があれば OK）
for f in $(grep -rln '"pull_request" in \|"pull_request" not in ' tools/*.py | grep -v "^tools/github_rest.py"); do
  if grep -q "^from github_rest import\|^import github_rest\|^from github_api import\|^import github_api" "$f"; then
    echo "$f: 集約済み（github_rest/github_api を import）"
  else
    echo "$f: 未 import → github_rest.py / github_api.py の docstring に見送り記録があるか確認"
  fi
done

# ③ import していないファイルについて、github_rest.py / github_api.py の docstring に
#    「集約しなかったもの」としてファイル名が記録されているか確認する
for f in $(grep -rln '"pull_request" in \|"pull_request" not in ' tools/*.py | grep -v "^tools/github_rest.py"); do
  if ! grep -q "^from github_rest import\|^import github_rest\|^from github_api import\|^import github_api" "$f"; then
    base=$(basename "$f")
    grep -q "$base" tools/github_rest.py tools/github_api.py \
      && echo "$f: 見送り記録あり（github_rest.py / github_api.py の docstring）" \
      || echo "$f: ⚠️ 未判定（§1〜§3 で判定し記録すること）"
  fi
done
```

実行結果の期待値（2026-09-07 JST 実測・Issue #825 完了時点）: 対象は
`tools/check_deploy_gate.py` / `tools/check_lane_reachability.py` / `tools/check_roadmap_status.py`
（②で「集約済み」判定）、`tools/generate_project_context.py` / `tools/gh_shim.py`
（③で「見送り記録あり」判定）の 5 ファイル。`⚠️ 未判定` の出力は 0 件。今後この手順が
`⚠️ 未判定` を出したら、新しく PR 除外を自前実装した箇所が現れたということなので、§1〜§3 で判定する。

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| `tools/github_rest.py` | GitHub REST 共通ページネーション・PR 除外（Issue #602）。「集約したもの」に本基準の適用結果を書く |
| `tools/github_api.py` | gh → urllib フォールバック共通化（Issue #238）。「集約しなかったもの」に本基準の適用結果を書く |
| `docs/rules/check-tool-design-rules.md` | 検査ツール（`tools/check_*.py`）の終了コード設計基準。本ファイルとは対象が異なる（本ファイルは共通クライアントモジュールへの集約可否、あちらは検査ツールの fail-open/fail-closed） |
| `docs/rules/agent-team-summary.md`「検査ツール・ゲートを直すタスクの委譲プロンプト必須項目」項目 0（#1019） | 委譲前に既存共通モジュールを列挙する規律。本ファイルの §1〜§4 はその「列挙したあとどう判定するか」を担う |
