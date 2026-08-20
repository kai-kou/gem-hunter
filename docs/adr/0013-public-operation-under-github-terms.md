# ADR 0013: 第三者へ公開して運用する際の GitHub 利用規約上の立場を確定する

- **ステータス**: 採用
- **日付**: 2026-08-20
- **関連**: `R-8`（[open-questions.md](../02_requirements/open-questions.md)）/ `RK-10`（[inception-deck.md](../00_concept/inception-deck.md)）/ `M-4`（[roadmap.md](../02_requirements/roadmap.md)）/ `INF-11` / `NFR-5` / `NFR-7`

## 1. 背景

`R-8`（GitHub 利用規約・AUP・API Terms の一次確認）は「**第三者へ公開する時点** で確認する」と定められ、フェーズ番号ではなく公開の有無で判断する未決事項として意図的に開かれていた。`RK-10`（規約抵触による公開停止）は「判断基準を設定済み・一次確認は未実施」の状態だった。

リポジトリのパブリック化にあたり、プレビュー URL を伏せずに公開する判断（2026-08-20）を採ったため、**第三者がアプリへ到達できる状態** になる。`M-4` の通過判定として本 ADR で一次確認を行う。

## 2. 決定

**現在の実装のまま、第三者へ公開して運用してよい。** 規約上の制約は以下 4 点として明文化し、**設計制約として固定する**（将来の変更でこの前提を崩さない）。

| # | 制約 | 現在の実装での満たし方 |
|---|---|---|
| **T-1** | **スクレイピングをしない。データ取得は GitHub API のみ** とする | `src/infrastructure/github/` の 2 経路（検索 / 詳細）だけが外部通信を行い、いずれも REST API を叩く。HTML の取得・解析は行わない |
| **T-2** | **アバター画像を再配信しない**（自サーバーを経由させない） | `next/image` の最適化を使わず素の `<img>` で `avatars.githubusercontent.com` を直接参照し、サイズ調整は GitHub 側のクエリパラメータ（`?s=80` / `?s=128`）に委ねる（`INF-11`・`src/ui/repository-list.tsx` / `repository-detail.tsx`） |
| **T-3** | **過度な自動一括リクエストを行わない** | キャッシュ（`NFR-5`・検索 60 秒 / 詳細 300 秒）とクライアント単位のレート制限（`NFR-7`・60 req/60 秒）で上流への流量を抑える。クロール・巡回・事前インデックス構築は行わない |
| **T-4** | **取得した情報をスパム目的・個人情報の販売に使わない** | 本プロダクトは検索結果の表示のみを行い、メールアドレス等の個人情報を収集・保存・送信しない。DB を持たない（[ADR 0007](./0007-no-database-client-side-state.md)）ため蓄積自体が起こらない |

## 3. 根拠（一次情報の該当箇所）

### 3.1. 「API 経由の取得はスクレイピングではない」（AUP）

> "Scraping refers to extracting information from our Service via an automated process, such as a bot or webcrawler. **Scraping does not refer to the collection of information through our API.**"
> — [GitHub Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies) "Information Usage Restrictions"

本プロダクトは API のみを使うため、AUP がスクレイピングに課す制約の対象外である（`T-1`）。

### 3.2. 情報利用の禁止事項は「スパム・個人情報の販売」（AUP）

> "You may not use information from the Service (whether scraped, collected through our API, or obtained otherwise) **for spamming purposes**, including for the purposes of sending unsolicited emails to users or **selling personal information**, such as to recruiters, headhunters, and job boards."

禁止されているのはスパムと個人情報の販売であり、**公開リポジトリのメタデータを検索・表示すること自体は禁止されていない**（`T-4`）。

⚠️ 同節には「研究者は公開・非個人情報を、成果がオープンアクセスである場合に限り研究目的で使ってよい」「アーカイブ担当者は公開情報をアーカイブ目的で使ってよい」という許可列挙がある。これを **「列挙された用途以外は禁止」と読むと本プロダクトは成立しない**。しかし当該列挙は「スクレイピングで得たか API で得たかを問わず」と前置きされたうえで、直後に禁止事項（スパム・個人情報販売）を挙げる構成であり、**個人情報の一括収集を念頭に置いた節** と読むのが自然である。加えて API Terms が API 利用を正面から許容している（§3.3）ため、API 経由の通常利用が禁止されていると解する余地はない。

### 3.3. API Terms が課すのはレート制限の遵守（Terms of Service §H）

> "**Abuse or excessively frequent requests** to GitHub via the API may result in the temporary or permanent suspension of your Account's access to the API."
> "You may not share API tokens to exceed GitHub's rate limitations."
> — [GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) "H. API Terms"

制裁の対象は **濫用と過度に頻繁なリクエスト** であり、上限そのものの遵守が要件になる（`T-3`）。「トークンを共有してレート上限を超える」ことの禁止は、[ADR 0010](./0010-no-token-rotation.md)（複数トークンのローテーションを採用しない）と **同じ方向を向いている**。当時 YAGNI と運用コストを理由に不採用としたが、規約上もこれが正しい選択だったことをここで確認する。

### 3.4. 公開リポジトリの内容は第三者が利用できる（Terms of Service §D.8）

> "These Terms do not restrict lawful access to or use of the contents of public repositories by third parties, or by GitHub or its Affiliates."

本プロダクトが扱うのは公開リポジトリのみ（`NFR-33` / `AC-12` でアプリ側から公開限定を強制している）であり、この節が扱う範囲に収まる。

### 3.5. 「Service の複製・再販の禁止」（AUP "Services Usage Limits"）は本プロダクトに当たらない

> "You will not reproduce, duplicate, copy, sell, resell or exploit **any portion of the Service**, use of the Service, or access to the Service without our express written permission."

対象は **Service そのもの**（GitHub というサービスの複製・再販）であって、API が返すデータを表示するアプリケーションではない。本プロダクトは GitHub の代替提供を行わず、GitHub API へのアクセスを再販もしない。

## 4. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **アバターを自サーバーで最適化・キャッシュして配信する**（`next/image`） | 与件 §4.2 の「画像は最適化して配信する」を満たす手段としては魅力的だが、**GitHub の資産を自サーバー経由で再配信する形** になり `RK-10` を現実化させる。GitHub 側のサイズパラメータ（`?s=`）で同等の効果が得られるため、リスクを取る理由がない（`INF-11`） |
| **公開前に GitHub へ書面で許諾を求める** | §3 のとおり通常の API 利用は規約が正面から許容しており、"express written permission" が要求されるのは Service 自体の複製・再販（§3.5）。照会は不要で、返答待ちのリードタイムだけが増える |
| **`R-8` を未確認のまま公開する** | `RK-10` の影響は「公開停止」であり、事後に気づくと最も高くつく。確認コストは一次情報 2 本の読解で済む |

## 5. 結果

- ✅ `R-8` をクローズする（`M-4` の通過判定 1 項目を満たす）
- ✅ `RK-10` の対策状態を「判断基準を設定済み」から **「一次確認済み・制約を `T-1`〜`T-4` として固定」** へ更新する
- 🔴 **`T-1`〜`T-4` は今後の設計制約** である。特に `T-2`（アバターを再配信しない）は、パフォーマンス改善の名目で `next/image` を導入すると **静かに破られる**。`INF-11` と本 ADR の両方が根拠であることを実装コメントに残してある
- ⚠️ 本 ADR は **規約の解釈** であって法的助言ではない。規約は改定されうるため、公開運用を続ける限り年 1 回程度は §3 の該当節を読み直す

## 6. 再決定の条件

以下のいずれかが起きたら本 ADR を見直す。

- GitHub が AUP / API Terms の該当節を改定した
- Phase 2（Gem Index）で **GitHub 以外のデータ源**（Ecosyste.ms・OpenSSF・BigQuery）を併用し、それらのデータを蓄積・再配布する構成になった
- アバター以外の GitHub 資産（README 本文・OG 画像等）を自サーバーで再配信する必要が生じた
- 事前インデックス構築（クロール的な一括取得）を行う構成へ変更する
