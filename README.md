# シニアペットのくらし — 国内アフィリエイトサイト

老犬・老猫との暮らしをサポートするグッズ・保険の比較サイト(国内Amazon/A8.net/もしもアフィリエイト/afb向け)。

## 中身

- Eleventy(11ty)で構築した静的サイト(無料でGitHub Pagesにホスティング可能)
- 日本語記事3本(段差対策、見守りカメラ・自動給餌器、ペット保険)
- 国内ASP登録ガイド(`docs/asp_playbook.md`)
- 6ロールパイプライン定義(`docs/agents/`)、運用ルールブック(`docs/pipeline_runbook.md`)
- デプロイ・ASP登録手順(`docs/setup_guide.md`)

## クイックスタート

```
npm install
npx @11ty/eleventy --serve
```

詳細は`docs/setup_guide.md`を参照。米国版(`海外アフィ/website/`)とは別プロジェクトとして独立管理する。
