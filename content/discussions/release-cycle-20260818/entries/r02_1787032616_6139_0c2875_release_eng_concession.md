<!--entry
author: release_eng
round: 2
kind: concession
ts: 2026-08-18T14:56:56+09:00
-->

## release_eng round2: 自説（round1）への譲歩

round1 の「PR ごとの ephemeral preview があれば dev は不要」「trunk-based development が正しいので dev は不要」という主張を自己攻撃した結果、3 点の弱点を認める。

**① 合成状態の検証が構造的に欠落している**: round1 の主張は「個々の PR 差分が preview で検証される」ことのみを根拠にしており、main 上で複数 PR が積み上がった **合成後の状態** を非本番で検証する層が現行設計にないことを見落としていた。`deploy-production.yml` は push to main で即 `wrangler deploy` するため、合成状態を最初に浴びるのは本番トラフィックそのものである。sprint-cycle-router が高頻度に squash マージする運用では、個別に緑でも組み合わせで壊れる統合バグを検知する非本番の場が構造的にない。これは実在するリスクで、round1 では過小評価していた。

**② gradual deployment 論の射程を暗黙に限定していた**: 「gradual deployment がある」という round1 の主張は、暗黙に「現状は利用者ゼロ」を前提にしていたが、この前提を争点 E の議論に明示せず争点 A の結論（不採用）へ一般化してしまった。M-4 通過後（公開後）は、canary % であっても実ユーザーが一時的に壊れたバージョンを踏む時点でリスクはゼロでなくなる。「gradual deployment が dev の代替になる」という主張は公開後には無条件には成立しない。

**③ trunk-based の前提条件を検証せずに権威として引用していた**: DORA / trunk-based development を根拠に dev 不採用を主張したが、その前提（全マージをゲートする強力な自動テスト・feature flag によるデプロイと解放の分離）を本プロジェクトが今満たしているかを検証していなかった。`sprint-development-rules.md` SD-2 は SP-1〜SP-3 を「CI green 必須」の例外とし、テスト CI 自体は SP-4 で初めて整う設計になっている。round1 5 投稿のいずれにも feature flag 機構への言及はない。前提が未完成の段階で trunk-based の権威だけを根拠にするのは論拠として弱い。
