# パイプライン運用ルールブック(国内版)

## 全体フロー

役割定義は `agents/` 配下の6ファイル(analyst / marketer / architect / reviewer / director / promoter)。基本構造は米国版(海外アフィ)と同じ。

```
[週1回・日曜・自動] 5〜6本のテーマについて以下を繰り返す
アナリスト ── 前サイクルのデータを分析
    ↓
マーケター ── 次の記事テーマ・狙う国内ASPを提案
    ↓
アーキテクト ── 商品/案件スコアリング→記事の見出し構成・リンク配置を設計
    ↓
レビュワー ── 設計図どおりに日本語本文を執筆
    ↓
ディレクター ── Obsidian共通ルール+チェックリストで最終確認(承認 or 差し戻し)
    │
    ├─ 差し戻し → アーキテクトまたはレビュワーに戻ってやり直し
    │
    └─ 承認 → プロモーター(SNS投稿案を作成、保存のみ)
                ↓
        記事は非公開ドラフトとして保存(published: false)。5〜6本たまったら生成サイクル終了
                ↓
[週末・人間] docs/weekly_publish_review.md のチェックリストで各記事をレビュー
    → 承認した記事に publishAt(火/木/土のいずれか)を割り当て、
      対応するSNS投稿案を docs/tweet_schedule.json のキューに追加してpush
                ↓
[火・木・土・自動] GitHub Actionsが定期リビルド → publishAtが到来した記事を自動公開
              同時に別のGitHub Actions(post-tweets.yml)が tweet_schedule.json の当日分をX APIで投稿
                ↓
        次サイクルのアナリストへ
```

## X投稿の実行環境について(2026-08-02)

X投稿(`tweet_schedule.json`の当日分をX APIで投稿する処理)は、当初Coworkのスケジュールタスク(`domestic-tweet-queue-poster`)で実行する設計だったが、**Coworkのサンドボックス環境から`api.twitter.com`への通信が恒常的にブロックされている**(403 Forbidden、2026年8月時点で確認済み)ことが判明したため、実際の投稿処理は`.github/workflows/post-tweets.yml`としてGitHub Actions側に移行した(火・木・土09:30 JSTに実行)。GitHub Actionsのランナーは通常のインターネットアクセスを持つため問題なく動作する。

これに伴い、Coworkの`domestic-tweet-queue-poster`タスクは無効化済み。GitHub Actions側でX投稿を成立させるには、リポジトリのSettings→Secrets and variables→Actionsで以下4つのシークレットを手動登録する必要がある(`scripts/.env`と同じ値、api.github.comもサンドボックスからブロックされているため自動登録は不可):
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

記事生成(週次バッチ)・週末レビュー・公開自体(deploy.ymlの定期リビルド)はこの制約の影響を受けず、従来どおりCowork側で実行する。

## 生成と公開の分離、および週次バッチ化(2026年7月〜)

週1回(日曜)、スケジュールタスクが1回の実行で記事を5〜6本まとめて自動生成する。**生成された記事はすべて`published: false`の非公開ドラフトとして保存され、そのままではサイトに反映されない**。公開するかどうか・いつ公開するかの最終判断は、週末に`docs/weekly_publish_review.md`のチェックリストに沿って人間が行う。承認された記事は`publishAt`(火・木・土のいずれかの日付)を割り当てられ、その日にGitHub Actionsの定期リビルドで自動的に公開される。SNS(X)投稿も同様に、承認時に`docs/tweet_schedule.json`のキューへ追加しておき、対応する火・木・土に別のスケジュールタスクが自動投稿する(X APIには「下書き」を作成する公式エンドポイントが存在しないため、投稿文言そのものは週末に人間が承認したものをそのまま使い、投稿タイミングだけを自動化している)。

自動生成タスク自体はgit操作・X投稿を一切行わない。

## 米国版との違い

- 対象言語: 日本語(レビュワーは日本語で執筆)
- 対象ASP: Amazon.co.jp / A8.net / もしもアフィリエイト / afb(米国5ASPとは別枠)
- 対象法令・規約: 日本の景品表示法・保険業法(保険案件を扱う場合)・各ASP規約
- Pinterest: 導入は任意(Xのみでも可)
- Obsidianルール: 別ファイル `rule of domestic affiliate.md`(米国版の`rule of foreign affiliate.md`とは別)

## Obsidian連携

ボルト「国内アフィ」内に共通ルールを配置する想定。`agents/director.md`から絶対パスで参照する。

## 週次自動実行について

米国版と同様、スケジュールタスクで週次実行する場合は、別タスクとして新規作成する(米国版のタスクに相乗りさせない。対象言語・ASP・記事フォルダが異なるため)。

## 差し戻しが多い場合の見直しポイント

同じ指摘が3サイクル続けて出る場合、その指摘はディレクターのチェックリストからルール自体に格上げする。
