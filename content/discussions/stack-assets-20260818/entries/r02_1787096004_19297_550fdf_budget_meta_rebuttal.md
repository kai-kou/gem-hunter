<!--entry
author: budget_meta
round: 2
kind: rebuttal
ts: 2026-08-19T08:33:24+09:00
-->

# budget_meta Round 2 反論・修正申告

## 実測再計算: 自作スキル 6 本での description 超過

### 現状と許容限界

| 項目 | 実測値 |
|-----|------|
| 現状 description 総量 | 14,506 B |
| スキル数 | 19 件 |
| **1 本あたりの平均** | **763 B** |
| 可視化上限（secondsky 明記） | 15,000 B |
| 残り予算 | 494 B |

### 自作スキル 6 本追加時の試算

```
追加 description 量 = 763 B/本 × 6 本 = 4,578 B
累積 description = 14,506 + 4,578 = 19,084 B
上限超過量 = 19,084 - 15,000 = +4,084 B（+27%）
```

**修正**: R1 で「自作ならスキル 29 本・description ~18.7KB で可視化上限以内」と述べたが、実際は **4,084 B = 27% 超過**する。本修正は `budget_meta` からの誤断定。

### 許容できる追加本数

```
許容限界 = (15,000 - 14,506) / 763 = 494 / 763 ≈ 0.65 本
実質: 0 本（既に上限到達状態）
```

**判定**: R1「自作 6 本 + 参考導入 2 本」は予算観点から **不可能**。

---

## stack_fit / sprint_value の「段階導入」主張への同意・補正

`stack_fit` の「Cloudflare MCP のみ今すぐ、他は SP 到達まで保留」・`sprint_value` の「SP-n ごとにタイミングを分ける」判断は **予算観点からも必須**。

理由:

- **今は Cloudflare Documentation MCP のみ** → description 追加ゼロ（read-only）
- `next-devtools-mcp` / `shadcn` MCP / `Playwright` MCP：**実行可能時点に入れる**
  - `next-devtools` は `next dev` 稼働時から効く（今は無意味）
  - `shadcn` MCP は `shadcn init` 完了後から効く（SP-1 後）
  - `Playwright` MCP は E2E 対象の画面が繋がる時点（SP-4）から効く

**重要**: 死蔵スキルを避ける実利観点（sprint_value）が、ほぼ同じ時点で「予算超過を招く」予算観点と一致している。2 つのレンズが異なる根拠で同じ結論に達した。

---

## conflict_guard が指摘した「description 肥大化リスク」への定量的査証

### 外部スキル導入での description 爆発

`conflict_guard` が「secondsky / wshobson は大量導入で risk」と述べた点を、skill `description` 単位で検証:

| 外部資産 | スキル数 | 平均 desc（推定） | 追加 description | 評価 |
|---------|---------|--------|---------|------|
| secondsky（142 件） | 142 | ~300-400 B | 約 50KB | 🔴 完全不可 |
| wshobson（92 agents 内 skill） | 92 | ~350 B | 約 32KB | 🔴 完全不可 |
| vercel plugin（33 skills） | 33 | ~250 B | 約 8.5KB | ⚠️ 限界超過 |

**どれを採っても現状 14.5KB を圧倒的に超過する。** conflict_guard の警告は定量的に正当化される。

---

## risk_ops の「バージョンピン必須」への予算的中立性

### ピン有無での `.mcp.json` サイズ差

```
ピンなし: "cmd": "npx -y next-devtools-mcp@latest"  (47 bytes)
ピン有：  "cmd": "npx next-devtools-mcp@1.2.3"      (45 bytes)
差分: -2 bytes（ピン化で若干削減）
```

**予算観点**: バージョンピンしても description 総量・ツール定義数は変わらない。**予算的には中立**。

ただし `risk_ops` が指摘した「サプライチェーン・破壊的変更リスク」は予算軸ではなく運用軸のため、本レンズでは確認できない。セッション起動レイテンシ（MCP サーバー起動数に比例）への影響も予算軸ではなく performance 軸。

---

## sprint_value / conflict_guard vs budget_meta: 本数上限の厳しさ比較

### 3 つのレンズの制約

| レンズ | 制約 | 結論 |
|--------|------|------|
| **budget_meta（予算軸）** | description 15,000 B 可視化上限 | **追加 0 本**（既に 14.5KB でほぼ満杯） |
| **sprint_value（実利軸）** | 死蔵スキルを避ける（YAGNI） | 効くスプリント到達まで 0 本（段階導入） |
| **conflict_guard（SSOT軸）** | ADR/ドキュメント矛盾を避ける | 全文レビュー必須のため実質 0-1 本 |

**3 つのレンズが異なる理由で同じ結論に収束**: 「今は何も足さない」。

- `sprint_value` の「段階導入」（SP 到達時に入れる）は、予算観点でも「その時点で description 再計算する」という逃げ道を開ける
- 例: SP-1 時点で確定スキル 2 本（description +1.5KB）を入れるなら、description 累積は 16KB に上がるが、**まだ可視化上限と無視できない距離**

---

## 重要な修正: R1 の「自作 6 本」推奨は取り下げ

**R1 結論（誤）**:
```
自作スキル 29 本・description ~18.7KB で可視化上限以内に収まる ✗
```

**R2 修正（正）**:
```
現状 14.5KB でほぼ可視化上限（15KB）に到達済み
追加は「段階的 1〜2 本」程度（SP ごとに判断）のみ可能 ✓
```

---

## 最終的な予算判定（修正版）

| 争点 | R1 判定 | R2 修正判定 | 理由 |
|-----|--------|-----------|------|
| **A: MCP 何本** | **2 本**（next-devtools / playwright） | **段階導入・今は 0 本** | Cloudflare 以外は SP 到達まで待つ。予算も死蔵も回避 |
| **B: 外部 vs 自作** | **自作 6 本** | **自作は 0-1 本/SP** | description 上限が既に到達状態。外部導入は不可 |
| **C: TDD Guard** | **スキル化** | **スキル化（後送り）** | 予算影響最小。タイミングは risk_ops に同意 |
| **D: Playwright Agents** | **SP-1 検証** | **SP-4 確定導入** | stack_fit / sprint_value / risk_ops が SP-4 指定 |
| **E: a11y 資産** | **masuP9 参考・自作 1 skill** | **自作ゲートのみ** | description 超過状態では新規 skill 不可 |
| **F: タイミング** | **SP-1 自作のみ** | **今は Cloudflare MCP のみ / 他は SP 到達時** | 3 レンズ合意 |

---

## 最小構成（予算・死蔵・SSOT の 3 軸で許容できる着手案）

**フェーズ A（今・SP-13 着手前）**
- ✅ Cloudflare Documentation MCP（既稼働・追加コストゼロ）
- ❌ 外部スキル一切不導入

**フェーズ B（SP-1 着手時）**
- ✅ 自作スキル 1 本（`@opennextjs/cloudflare` デプロイ手順）→ +763 B → 累積 15,269 B（実質 15.3KB・限界付近）
- ✅ `next-devtools-mcp` / shadcn MCP（ただし `.mcp.json` は作成し entry のみ作成、実際の接続は後続タスク）

**フェーズ C（SP-4 着手時）**
- ✅ Playwright MCP + Playwright Agents（生成物レビュー済みで commit）
- 🤔 追加スキルがあれば description 容量を再計測してから個別判定

**フェーズ D（SP-10 着手時）**
- ✅ masuP9 a11y skills （チェリーピック 1-2 skill）

---

## 予算メタの立場からの最終主張

1. **現状は可視化上限到達状態**。「自作 6 本」「外部 plugin」いずれも実現不可
2. **段階導入が予算・死蔵・SSOT 3 軸で最適**。sprint_value / conflict_guard の実利判定と予算判定が一致している点に注目
3. **description 計測を SP ごとに再実施する運用**が必須（今後も追加候補が出てくるため）

---

## 他エージェントへの同意・補正

| エージェント | 主張 | 予算観点の補正 |
|-------------|------|-------------|
| **stack_fit** | Cloudflare 以外は SP 到達まで保留 | ✅ 同意（予算超過防止） |
| **sprint_value** | 各 SP ごとに必要なものだけ導入 | ✅ 同意（実利と予算が一致） |
| **conflict_guard** | SSOT 矛盾リスク回避 | ✅ 同意（SSOT 破壊も description 超過も招く外部資産が多い） |
| **risk_ops** | バージョンピン・生成物レビュー必須 | ✅ 同意（予算軸とは別軸で重要） |

---

## 訂正の根拠（実測）

- 現状 description 総量: **14,506 B（実測値）**
- スキル当たり平均: **763 B（14,506 ÷ 19 の実測値）**
- 追加 6 本: **4,578 B（763 × 6）**
- 上限 15,000 B に対して: **+4,084 B 超過（確定）**
