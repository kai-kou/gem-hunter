# Google スライドへのアップロード手順（gws CLI）

参照ワークフローの Step 5 / 11 / 15（Google ドライブアップロード）を、このクラウド実行環境で実施するための手順。
当初は `gws` が無いため「リポジトリ内配置 + PR」に読み替えていたが、飼い主が Google Workspace の
OAuth クライアントを環境変数へ供給したため、**原典どおり Google スライドへ上げる経路が使えるようになった**。

## 前提

| 項目 | 値 |
|---|---|
| CLI | `gws` 0.22.5（`npm install -g @googleworkspace/cli` で導入。GitHub Releases のバイナリを取得する） |
| 認証情報 | `GOOGLE_WORKSPACE_CLI_CLIENT_ID` / `GOOGLE_WORKSPACE_CLI_CLIENT_SECRET`（セッション env に供給済み） |
| 保存先 | `Presentations/gem-hunter/`（`Presentations` は既存フォルダ） |

## 認証（初回のみ・ユーザー操作が要る）

`gws auth login` はローカルループバック（`http://localhost:<ランダムポート>`）で認可コードを待ち受ける。
**コンテナの `localhost` はユーザーのブラウザから見えない** ため、素直に実行するだけでは完了しない。
次の 3 手で通す。

```bash
# 1. 待ち受けを起動し、表示された認可 URL を控える（バックグラウンドで走らせる）
nohup gws auth login -s drive > /tmp/claude/gws-login.log 2>&1 &
sleep 8 && cat /tmp/claude/gws-login.log

# 2. ユーザーがその URL をブラウザで開いて許可する
#    → http://localhost:<PORT>/?code=... へリダイレクトされ、ブラウザは接続エラーになる（正常）
#    → アドレスバーの URL をそのまま貼ってもらう

# 3. 受け取ったクエリをコンテナ内の待ち受けへ流し込む（gws がトークン交換まで済ませる）
curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:<PORT>/?code=<CODE>'
```

- スコープは `-s drive` で Drive のみに絞る（既定は他サービスも含む）
- 認可コードは 1 回限り・短時間で失効する。ファイルにもログにも残さない
- 認証情報は `~/.config/gws/credentials.enc`（AES-256-GCM）に保存される。**クラウドのコンテナは破棄されるため、セッションをまたいで残らない**（次のセッションでは再度この手順が要る）
- ヘッドレスで keyring が使えない場合は `GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file` を設定する

## アップロード

```bash
# フォルダ ID を取得（無ければ作る）
gws drive files list --params '{"q":"name='\''Presentations'\'' and mimeType='\''application/vnd.google-apps.folder'\'' and trashed=false","fields":"files(id,name)"}'
gws drive files create --json '{"name":"gem-hunter","mimeType":"application/vnd.google-apps.folder","parents":["<PRESENTATIONS_ID>"]}'

# PPTX を Google スライドへ変換しながらアップロードする
# （metadata の mimeType に application/vnd.google-apps.presentation を指定するのが変換の指示になる）
gws drive files create \
  --json '{"name":"gem-hunter_text","parents":["<FOLDER_ID>"],"mimeType":"application/vnd.google-apps.presentation"}' \
  --upload content/slides/project-explanation-20260822/output/gem-hunter_text.pptx \
  --upload-content-type application/vnd.openxmlformats-officedocument.presentationml.presentation

# アップロード後は必ず一覧で実在を確認する（レスポンスだけで成否を判断しない）
gws drive files list --params '{"q":"'\''<FOLDER_ID>'\'' in parents and trashed=false","fields":"files(id,name,mimeType)"}'
```

URL は `https://docs.google.com/presentation/d/<FILE_ID>/edit`。

## 差し替え（フィードバック反映時）

🔴 **`files update` で中身だけ差し替える。`delete` → `create` はしない**（2026-08-23 に実機確認）。
同じ `fileId` へ PPTX をアップロードすると、**ファイル ID も URL も変わらないまま**
Google スライドとして再変換される（`mimeType` は `application/vnd.google-apps.presentation` のまま）。
`slide-guide.md` など他のドキュメントがこの URL を指しているため、ID が変わると全部を書き換える羽目になる。

```bash
gws drive files update \
  --params '{"fileId":"<FILE_ID>"}' \
  --upload content/slides/project-explanation-20260822/output/gem-hunter_text.pptx \
  --upload-content-type application/vnd.openxmlformats-officedocument.presentationml.presentation
```

**アップロード後は必ず往復で検証する**（レスポンスだけで成否を判断しない・L-113）。
Google スライド側を PPTX へ書き出し直して、枚数と見出しを手元の成果物と突き合わせる。

```bash
# -o は「カレントディレクトリの外」を拒否するので、リポジトリ内へ出してから消す
gws drive files export \
  --params '{"fileId":"<FILE_ID>","mimeType":"application/vnd.openxmlformats-officedocument.presentationml.presentation"}' \
  -o roundtrip-check.pptx
python3 -c "from pptx import Presentation; p=Presentation('roundtrip-check.pptx'); print(len(p.slides._sldIdLst))"
rm -f roundtrip-check.pptx
```

<details>
<summary>旧手順（delete → create）を使わない理由</summary>

当初は「同名で作り直すと重複するので `gws drive files delete` で消してから作り直す」としていたが、
これだと差し替えのたびに URL が変わる。`files update` なら重複も起きず URL も保たれるため、
**旧手順は使わない**。`files delete` は成功時にレスポンス本体が空で、`gws` が
カレントディレクトリに `download.html` を書き出す副作用もある。

</details>

## 現在の成果物

| 版 | ファイル ID | URL |
|---|---|---|
| テキスト版 | `1uEk0V-YowdUY8hKU7yliTBfaQoppBLS3710pGt9r10g` | https://docs.google.com/presentation/d/1uEk0V-YowdUY8hKU7yliTBfaQoppBLS3710pGt9r10g/edit |
| 画像版 | `1DNO_Pi0nZrN1nHIj3oWA2iopxGuSTqst_GlJacspCqE` | https://docs.google.com/presentation/d/1DNO_Pi0nZrN1nHIj3oWA2iopxGuSTqst_GlJacspCqE/edit |
