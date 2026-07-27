# セットアップガイド:デプロイ〜ASP登録(国内版)

## このプロジェクトの中身

米国版(`海外アフィ/website/`)と同じ構造。別プロジェクトとして扱う。

```
website/
├── src/                    ← サイトの中身
│   ├── posts/               ← ブログ記事(日本語Markdown)
│   ├── _includes/           ← レイアウト
│   ├── _data/site.json      ← サイト名・説明文
│   └── assets/style.css     ← デザイン
├── .github/workflows/deploy.yml  ← GitHub Pagesへの自動デプロイ設定(完成済み)
├── docs/                    ← 運用ガイド類
└── package.json
```

## ステップ1: ローカルで確認する(任意)

```
cd "/Users/kisaragisaito/Library/Mobile Documents/iCloud~md~obsidian/Documents/アフィリエイト/国内/国内アフィ/website"
npm install
npx @11ty/eleventy --serve
```

`http://localhost:8080` で確認できる。

## ステップ2: GitHubリポジトリ作成〜push

米国版のときと同じ手順。**別リポジトリ**を新規作成すること(米国版と同じリポジトリに混ぜない)。

```
git init
git add .
git commit -m "initial site (domestic)"
git branch -M main
git remote add origin https://github.com/【ユーザー名】/【新しいリポジトリ名】.git
git push -u origin main
```

GitHubへのpush時は、前回同様Personal Access Token(repo + workflowスコープ)が必要。

## ステップ3: GitHub Pagesを有効化

リポジトリの「Settings」→「Pages」→「Source」を「GitHub Actions」に設定。

## ステップ4: ASP登録

`docs/asp_playbook.md`を参照。Amazon.co.jp → A8.net → もしもアフィリエイト → afb の順で進める。

## ステップ5: Xアカウントを分ける

日本向け発信用に、**米国版とは別のXアカウント**を用意する。自動投稿を行う場合は、そのアカウントで新たにX Developer Appを作成し、Access Token/Secretを取得する(米国版のときと同じ手順を、新しいアカウントで繰り返す)。

## ステップ6: 新しい記事を追加する方法

`src/posts/`に新しい`.md`ファイルを、既存記事と同じフロントマター形式で追加すれば、自動的にトップページと`sitemap.xml`に反映される。

## 運用上の注意点

- Amazonリンクには`rel="nofollow sponsored"`を付ける(テンプレートに組み込み済み)
- 保険・医療(獣医療)関連の断定表現は避ける
- 記事内の広告表記(`/affiliate-disclosure/`)は必須
