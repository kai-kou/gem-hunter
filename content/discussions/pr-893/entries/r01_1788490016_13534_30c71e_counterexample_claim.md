<!--entry
author: counterexample
round: 1
kind: claim
ts: 2026-09-04T11:46:56+09:00
-->

## 反例: `validate_spec()` は participants の name 重複を検出せず、実質 1 名の議論を「起動プラン」で通す

### 指摘 1（本命）

- **severity**: CRITICAL（fail-open 方向のため 1 段上げ・`code_review.json` synthesizer 指示に準拠）
- **confidence**: CONFIRMED（実際に `validate_spec` と `discussion_whiteboard.py init` を実行して再現）
- **file:line**: `tools/discussion_review_trigger.py:154-172`（`validate_spec()` の `participants` ループ。特に 154-157 行目の `len(participants) < 2` チェックが **リスト長のみ** を見ており、name の一意性を見ていない）

**チェック項目との対応**: ④ 倒れる向き（fail-open）。`validate_spec` 自身のエラーメッセージが
「議論型レビューは相互反論が成立しないと意味がない」と明言しているにもかかわらず、
**その前提を壊す入力（重複 name）を素通りさせる**。

**再現手順**:

```python
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, "tools")
from discussion_review_trigger import validate_spec

spec = {
    "topic": "t", "brief": "b",
    "participants": [
        {"name": "alice", "model": "sonnet", "lens": "x"},
        {"name": "alice", "model": "sonnet", "lens": "y"},   # ← name が重複
    ],
    "synthesizer": {"name": "lead", "instruction": "i"},
    "verdict_schema": {"findings": []},
}
p = Path(tempfile.mktemp(suffix=".json", dir="/tmp"))
p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
print(validate_spec(p))
```

**結果**:
```
(True, 'spec 検証 OK: /tmp/tmpXXXXXX.json（participants 2 名）')
```

`ok=True` で「2 名」と報告される。これにより `main()` は exit 0 で `run_native_discussion_review`
プランを出力し、`pr-review-watcher` / `discussion-review` スキルはこれを「Layer 2 実施可能」として
そのまま起動する。

**downstream での実害（`discussion_whiteboard.py` を実行して確認済み）**:

```
python3 tools/discussion_whiteboard.py init dup-check-xyz \
    --topic "dup test" --participants "alice,alice" --brief "b"
```
生成された `meta.json`:
```json
{
  "participants": ["alice", "alice"]
}
```
（新規 board 作成時は `cmd_init` の `else` 分岐がそのまま使われ、重複除去（`dict.fromkeys`）が
効くのは *既存 meta.json への追記時* だけ。初回 init では重複は残る。）

`discussion-review` SKILL.md Step 1 は「`name`: spec の participant name（そのまま。SendMessage の
宛先になる）」と明記しており、name は Agent Teams の SendMessage 宛先として使われる。同名の 2 プロセスが
並列起動された場合、round 2 でオーケストレーターが「alice」宛にメッセージを送っても **どちらのプロセスに
届くか区別できない**（`docs/rules/discussion-whiteboard-rules.md` にも name の一意性を要求する記述は無い
— grep 済み・ヒット無し）。つまり判定器が「相互反論が成立する 2 名」と保証したはずの spec が、実際には
相互反論が成立しない（もしくは片方が応答不能になる）議論を起動しうる。

**self-test のカバレッジ欠落（区別テストの有無・チェック③）**: 追加された self-test（失敗経路 1〜7）には
name 重複を負ケースとして検証するものが無い。以下の変異は self-test を全て通過する:

```
# 変異: 154-157 行目の重複チェックを足さない（= 現状のコードそのもの）
# → self-test 実行:
python3 tools/discussion_review_trigger.py --self-test
```

実行結果: `OK: discussion_review_trigger self-test passed`（重複 name のケースが無いため無傷で通過）。

**なぜこの PR のスコープ内か**: 本 PR は `--spec` オプションを新設し「下流フォークが自前の spec を
指定できる」ことを明示的な設計目標にしている（`docs/rules/ai-reviewer-strategy.md` 差分）。
`validate_spec` はまさにその「信頼できない/検証されていない自前 spec」を受理するかどうかの唯一のゲートであり、
このゲートの穴は本 PR が新設した攻撃面（`--spec`）に直結する。

**推奨する直し方**: `participants` ループ内で `name` を集合に集めて重複を検出し、
`len(set(names)) != len(participants)` なら `ok=False` を返す（エラーメッセージに重複した name を含める）。
self-test にも重複 2 名・重複 1 名 + 正常 1 名の負ケースを追加する。

---

### 指摘 2（副次・軽微）

- **severity**: NIT
- **confidence**: CONFIRMED
- **file:line**: `tools/discussion_review_trigger.py:158`（`lens`）/ `168`（`synthesizer.get("instruction")`）/ `170`（`verdict_schema`）

これら 3 箇所はいずれも **truthy 判定のみ**（`isinstance` チェック無し）。
`lens: "   "`（空白のみの文字列）・`instruction: 123`（文字列でない）・`verdict_schema: "yes"`
（オブジェクトでない）はいずれも `ok=True` になる（実際に `validate_spec` へ渡して確認済み、
すべて `True` を返した）。実害は小さい（人間が spec を書く前提のため悪意ある入力は想定しにくい）が、
「最小構造を満たす」という docstring の主張に対しては型チェックが緩い。ブロッキングにはしない。

---

**干渉検証**: 対象外（本タスクは反例作成レンズの単独レビューであり、複数対策の相互作用検証は範囲外）。
