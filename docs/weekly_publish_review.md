# 週末公開レビュー(人間によるチェックフロー)

## 位置づけ

週末(日曜9時JST)に自動生成される5〜6本の記事は、生成された時点では**すべて非公開のドラフト状態**(フロントマターに`published: false` / `permalink: false` / `eleventyExcludeFromCollections: true`)。ディレクターの承認はあくまで機械的なルール照合であり、実際にサイトへ公開するかどうか・いつ公開するかは、週末にこのチェックフローに沿って人間が判断する。

承認された記事は、翌週の火・木・土に**自動で公開・SNS投稿される**(`publishAt`フィールドとGitHub Actionsの定期リビルド、および`tweet_schedule.json`キューとTue/Thu/Sat投稿タスクによる)。人間が実際に手を動かすのは週末のレビュー作業のみで、公開・投稿自体は仕組みが自動で行う。

## 週末レビューの手順

### ステップ1: 今週分のドラフトを確認する
- `src/posts/` 内で `published: false` になっているファイルを確認する(通常5〜6本)
- 対応する `docs/cycles/YYYY-MM-DD.md`(サイクルログ)を読み、各記事についてのアナリスト/マーケター/アーキテクト/ディレクターの判断根拠を確認する

### ステップ2: 記事ごとのチェックリスト
```
[ ] ディレクターの判定が「承認」になっているか(差し戻しのまま残っていないか)
[ ] Obsidian共通ルール(rule of domestic affiliate.md)と矛盾する表現がないか、人間の目でも再確認する
[ ] 保険・獣医療について断定的な表現がないか
[ ] 紹介している商品・案件が実在し、リンク先が正しいか
[ ] Amazonリンクにtag=seniorpet-22とrel="nofollow sponsored"が付いているか
[ ] 既存の公開済み記事とテーマ・タイトルが重複していないか
[ ] 数字・事実関係に明らかな誤りがないか(ディレクターはここまでチェックできないため人間の役割)
[ ] ローカルビルド(`npx @11ty/eleventy --serve`)で見た目・レイアウト崩れがないか
```

### ステップ3: 判断する
- **承認する記事**: フロントマターから `published: false` / `permalink: false` / `eleventyExcludeFromCollections: true` の3行を削除し、代わりに `publishAt: "YYYY-MM-DDTHH:MM:SS+09:00"` を追加する(公開したい火・木・土の日付、時刻は当日09:00+09:00でよい)。承認した記事すべてに、翌週の火・木・土のいずれかへ均等に振り分けて割り当てる(例: 5本なら火2本・木2本・土1本など)
- **見送る記事**: ファイルは残したまま(`published: false`のまま)にするか、`docs/cycles/`のログに見送り理由を追記する。翌週以降に書き直して再利用してもよい

### ステップ4: SNS投稿をキューに登録する
- 承認した記事ごとに、`docs/cycles/`に保存されているプロモーターのSNS投稿案から、価値が高いと判断したものを1〜2件選ぶ
- `docs/tweet_schedule.json` に以下の形式でエントリを追加する(`date`はステップ3で割り当てた`publishAt`の日付と揃える)。`type`には選んだ投稿の型(`hook`/`list`/`before_after`/`cta`のいずれか)を必ず入れる。これが`docs/engagement_log.json`でどの型の反応が良いかを比較する際のタグになる:
  ```json
  {
    "id": "2026-08-04-rougan-dansa-taisaku",
    "date": "2026-08-04",
    "article": "rougan-dansa-taisaku",
    "type": "hook",
    "text": "投稿案の本文...",
    "posted": false,
    "posted_at": null
  }
  ```
- 投稿後は`tweet_id`が自動的に記録される(`post_scheduled_tweets.py`が追記)。これを使って後日`scripts/fetch_tweet_metrics.py`がインプレッション数等を取得する

### ステップ5: まとめてpushする
- 承認・publishAt付与・キュー登録が終わったファイルをすべて `git add` → `git commit` → `git push`
- 補足: このフォルダ(iCloud同期下)で直接`git commit`すると、まれに`.git/index.lock`が残ってしまい削除できなくなることがある(iCloud同期領域の制約)。その場合は `/tmp` 等の別ディレクトリに`git clone`し、このフォルダの変更ファイルを`rsync`でコピーしてからcommit/pushするとよい
- この時点ではまだサイトに反映されない(`publishAt`が未来日付の記事は非表示のまま)。実際の公開は各記事の`publishAt`の日にGitHub Actionsの定期リビルドで自動的に行われる
- 公開予定日以降に、実際のURLで表示を確認する(手動チェック推奨)

## 火・木・土に自動で起きること(人間の作業は不要)
1. GitHub Actionsが09:00 JSTに定期リビルドし、`publishAt`が当日以前になった記事を自動公開する
2. GitHub Actions(`.github/workflows/post-tweets.yml`、09:30 JST)が `scripts/post_scheduled_tweets.py` を実行し、`tweet_schedule.json`でその日付の`posted: false`エントリを見つけてX APIで実投稿し、`posted: true`と実際の`tweet_id`を記録・commitする

**補足(2026-08-02)**: 当初はCoworkのスケジュールタスク(`domestic-tweet-queue-poster`)でこの投稿を行う設計だったが、Coworkのサンドボックス環境から`api.twitter.com`への通信が恒常的にブロックされている(403 Forbidden)ことが判明したため、実際の投稿はGitHub Actions側に移行した。GitHub Actionsのランナーは通常のインターネットアクセスを持つため、ここでは問題なく動作する。`domestic-tweet-queue-poster`タスクは無効化済み。X APIの認証情報はリポジトリのGitHub Actions Secretsに設定する必要がある(`X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET`)。

## エンゲージメント計測(日曜9時、生成サイクルの一部として自動実行)
`scripts/fetch_tweet_metrics.py` が過去に投稿した`tweet_id`のインプレッション数・いいね数等を取得し、`docs/engagement_log.json`に記録する。これにより次サイクルのアナリスト役が「一般的ベンチマークで代替」ではなく実データを使えるようになる。X APIは2026年2月から従量課金制(サブスクなし)になっており、自分のアカウントの投稿を読む場合は割引レート($0.001/件)が適用されるため、週数件のチェックであれば実質無視できるコスト。ただし無料枠は無いため、`console.x.com`で事前に少額のクレジットをチャージしておく必要がある。

## 頻度の目安
生成: 週1回(日曜、自動、5〜6本のドラフト)
公開判断・publishAt割り当て・SNS投稿キュー登録・push: 週1回(週末、人間がこのチェックリストに沿って実施)
実際の記事公開・SNS投稿: 火・木・土(自動、人間の作業不要)
