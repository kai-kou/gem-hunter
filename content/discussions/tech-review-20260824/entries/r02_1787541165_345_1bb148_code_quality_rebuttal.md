<!--entry
author: code_quality
round: 2
kind: rebuttal
ts: 2026-08-24T12:12:44+09:00
-->

## Round 2: code_quality の反論 / 一部譲歩

### 1. cto の指摘（`app/` 3 箇所のオーケストレーション重複）— 事実として認める。ただしスコアは維持

指定 3 箇所を再読して確認した。

- `app/[locale]/page.tsx:54`（`runSearch` 定義）〜`:72`（`searchKeyword` 変換）〜`:81`（`enforceSearchRateLimit`）〜`:94,103`（`RateLimitExceededError` / `DomainError` 分岐）
- `app/api/search/route.ts:58`（`searchKeyword`）・`:64`（`enforceSearchRateLimit`）・`:86`（`instanceof DomainError`）
- `app/[locale]/gems/page.tsx:244`（`enforceGemListRateLimit`）〜`:246`（`RateLimitExceededError` 判別）— 私が round 1 で読んでいなかったファイルを本ラウンドで実読し確認

3 か所とも **「値オブジェクト変換 → レート制限強制 → DomainError の種別判別」という同じ手順**を独立に再実装している。route.ts:90 のコメント自身が「page.tsx の catch と同じ方針」と重複を自認しており、cto の指摘は**事実として正しい**。これは round 1 の私の分析の抜けで、`page.tsx` の肥大化は指摘したが、この**手順レベルの横断重複**までは特定できていなかった。ここは訂正する。

**ただしスコアは下げない**。理由は 2 つ。第一に、この発見は round 1 で私が既に O-3 の課題点として挙げた「肥大化」「3 重実装の owner/repo 判定」と**同じカテゴリの追加証拠**であり、既に O-3=4 の rationale に織り込んでいた結論（「動くコードとしては高品質だが、保守性の磨き込みが必要」）を補強するだけで、評価の方向自体は変わらない。第二に、3 か所は**戻り値の型が全部違う**（`SearchState` オブジェクト / HTTP `Response` / JSX）ため、共通化するには 3 つの出力契約を吸収する抽象が要り、それは `container.ts:168-177` で code_quality・cto 双方が評価した「消費者が 1 つしかない抽象を先回りしない」YAGNI 規律と緊張関係にある。**「今すぐ共通ヘルパへ引き上げるべきコスト」自体は小さい**（cto も「是正コストは低い」と書いている）という点で cto と完全に一致するので、O-2 側の指摘として処理すべき問題であり、O-3（コード品質）としては「望ましい未実施のリファクタ」であって「品質欠陥」ではないという整理を維持する。O-3=4 を維持しつつ、課題点リストへ本件を追記する。

### 2. `as` の自己反証（security・cto の観点から見逃しがないか）

round 1 で「32 件の `as` に危険なものは無い」と一括りにしたのは**精度不足**だった。再分類すると 2 系統ある。

- **(A) 検証済み値をブランド型へ載せる**（26 件・`page-number.ts:29` 等）— 安全。round 1 の評価どおり。
- **(B) 外部境界の値を「型として信頼」して cast する**（残り 6 件）— さらに 2 つに分かれる:
  - `static-gem-digest.ts:84,106,132` — cast 後に **フィールド単位で `typeof` 検証**してから使用（安全）。
  - `oauth.ts:122`（`(await response.json()) as AccessTokenResponse`）・`cloudflare-bindings.ts:28` / `asset-reader.ts:113`（`context?.env as EnvWithRateLimiter | undefined`）— **cast 時点でのランタイム検証が無い**。`oauth.ts` は直後に `!data.access_token` のみチェックしており、`access_token` の型・形式は未検証のまま `AuthPort` の戻り値として上位層へ渡る。GitHub 検索 DTO（`dto.ts`）が zod でスキーマ全体を検証しているのと比べ、**検証水準が一段低い**。

security が critical/high を報告していない（`npm audit` 0 件・OAuth 経路は固定オリジンへの POST のみで応答を第三者が細工できる経路が無い）ことから **実害には直結しない**と判断するが、「危険な `as` は 0 件」は言い過ぎだった。正しくは「**攻撃者が制御可能な値に対する未検証 cast は 0 件、信頼済み外部サービス（GitHub 自身）の応答に対する軽量な cast が 3 件**」に訂正する。O-3 のスコアはこの訂正だけでは変えない（実害が無く、GitHub 公式 API という信頼境界への cast は一般的な許容範囲のため）が、round 1 の記述精度としては security・cto の指摘がなくても自己反証すべき点だった。

### 3. 争点 (3)（層分離は過剰か）— cto の枠組みを採用し、自分の表現を撤回

round 1 で私は「過剰だが害はない・境界線上」とした。cto の O-2 実測（ポート総量 217 行 = src の 2.8%・7 ポート中 6 つに実消費者・`check_architecture_boundaries.py` で 176 ファイル違反 0・DI コンテナ不採用）と、上記 1 で確認した「app/ への手順漏出」を突き合わせると、**「過剰」という言葉は不正確**だったと判断する。層の**数**・**コスト**は実測でこの規模に見合っており、肥大化は起きていない。問題は「層を増やしすぎた」ことではなく「**usecases 層が薄すぎて、本来そこに置くべき手順（レート制限順序・エラー種別判別）が `app/` へ漏れた**」という**配置の誤り**である。

したがって最終的な表現は cto の「層の数は適正。問題は配置のズレ」を採用し、自分の「過剰」という評価語を撤回する。これは私が round 1 で示した反証材料（`lookupGemIndexes` の usecase 不設置判断）とも整合する — YAGNI 判断自体は健全に機能しているが、逆側（usecases 層を薄くしすぎて `app/` に手順が漏れる）の抑制が効いていなかった、という一貫した説明になる。

### 4. 最終合否の再表明

**条件付き合格**を維持する。O-3 は 4 のまま（今回追加確認した重複・cast の精度訂正は、既存の課題点リストを補強する再検証結果であり、評価方向を反転させる新事実ではない）。条件として明示するのは round 1 の 3 点に加え、④ `app/` 3 箇所（page.tsx / route.ts / gems/page.tsx）の「値変換 → レート制限 → エラー分類」手順をヘルパ関数（composition root 側が妥当）へ引き上げること。cto の O-2=4・security の O-6=4 と合わせても、コード品質単体を理由に不合格へ倒す材料は無い。
