# 週末公開レビュー(人間によるチェックフロー)

## 位置づけ

週末(土曜9時JST。2026-09-12に日曜から変更)に自動生成される5〜6本の記事は、生成された時点では**すべて非公開のドラフト状態**(フロントマターに`published: false` / `permalink: false` / `eleventyExcludeFromCollections: true`)。ディレクターの承認はあくまで機械的なルール照合であり、実際にサイトへ公開するかどうか・いつ公開するかは、週末にこのチェックフローに沿って人間が判断する。

承認された記事は、**毎日自動で公開・SNS投稿される**(`publishAt`フィールドとGitHub Actionsの毎日の定期リビルド、および`tweet_schedule.json`キューと毎日の投稿タスクによる)。人間が実際に手を動かすのは週末のレビュー作業のみで、公開・投稿自体は仕組みが自動で行う。

**2026-09-06変更**: 公開・SNS投稿の頻度を火・木・土(週3回)から**毎日**に変更した。理由は、週次生成(5〜6本)に対して週3回公開では未公開ドラフトが恒常的に滞留してしまうため。この変更に伴い、既存の未公開バックログ35本(記事本体35本のpublishAt)を2026-09-07から1日1本ペースで再配分し、`docs/tweet_schedule.json`の対応する日付・`.github/workflows/deploy.yml`と`post-tweets.yml`のcronスケジュールも毎日実行に変更済み。

## 週末レビューの手順(2026-09-21にHTML選択式へ移行)

従来はこのファイルのチェックリストを見ながらフロントマターを手で書き換えていた。
2026-09-19の実作業で見落としが起きたこと、また同日に未公開記事のページ出力を止めた結果
「リンク先がまだ公開されていない記事へのリンクは公開時に404になる」という目視では
追えない制約が生まれたことから、機械チェック付きのレビュー画面を用意した。

```
python3 scripts/build_review.py
  → docs/review/review.html が生成される。ブラウザで開く
  → 記事ごとに 承認/見送り・公開日・SNS投稿の型 を選ぶ
     (j/k で移動、a で承認、s で見送り)
  → 「決定を書き出す」で decisions.json がダウンロードされる
  → docs/review/ に置く

python3 scripts/apply_review.py --dry-run   # 何が起きるか確認
python3 scripts/apply_review.py             # 反映

git add -A src/posts docs && git commit && git push
```

`apply_review.py` がやること:

1. フロントマターから `published: false` / `permalink: false` /
   `eleventyExcludeFromCollections: true` を外し、`date` と `publishAt` を付ける
2. 選んだSNS投稿案を `docs/tweet_schedule.json` に登録する(記事の公開日と同じ日付)

公開日は既存の予約の最終日の翌日から連番で提案される。画面上で変更できる。

### レビュー画面が自動で見てくれること

| チェック | 重さ | 背景 |
|---|---|---|
| 内部リンク先の公開日が、その記事より前か | error | リンク先が未公開だと404になる。2026-09-19の変更で生まれた制約 |
| 「こんな場合は動物病院へ相談を」があるか | error | 2026-09-19におむつ記事で欠落していた。人間もディレクターも見落とした |
| Amazonタグと `rel="nofollow sponsored"` | error | タグ漏れは報酬の取りこぼしに直結する |
| タイトルの重複 | error | |
| 断定表現(必ず/絶対に/治ります 等) | warn | 共通ルールの「絶対NG表現」 |
| 季節性と公開予定日のずれ | warn | 2026-09-19に2件発生(除湿=旬を逃しかけ、熱中症=旬を過ぎ) |
| 本文の分量 | warn | |

### 人間が見るべきこと

機械が拾えないのはここ。**レビューの時間はここに使う。**

```
[ ] 紹介している商品・案件が実在し、リンク先が妥当か
[ ] 数字・事実関係に明らかな誤りがないか
[ ] 保険・獣医療について、断定を避けた書き方になっているか(機械チェックは語句レベルまで)
[ ] 文章として読めるか
[ ] 既存記事と主張が矛盾していないか
```

### 見送る場合

何もしなくてよい。下書きのまま残るので翌週以降に再利用できる。
見送った理由は `docs/cycles/` のログに追記しておくとよい。

### 補足

- `apply_review.py` は適用直前にもう一度チェックする。画面を開いてから決定するまでに
  他の記事の公開日が動いていると、リンクの順序が壊れることがあるため
- error が残っていると中断する。`--force` はあるが原則使わない
- `review.html` と `decisions.json` は `.gitignore` に入れてある
- iCloud同期下で `git commit` すると稀に `.git/index.lock` が残ることがある。
  その場合は `/tmp` に `git clone` し、変更ファイルを `rsync` でコピーしてから commit する

## 毎日自動で起きること(人間の作業は不要)
1. GitHub Actionsが毎日09:00 JSTに定期リビルドし、`publishAt`が当日以前になった記事を自動公開する
2. GitHub Actions(`.github/workflows/post-tweets.yml`、毎日09:30 JST)が `scripts/post_scheduled_tweets.py` を実行し、`tweet_schedule.json`でその日付の`posted: false`エントリを見つけてX APIで実投稿し、`posted: true`と実際の`tweet_id`を記録・commitする

**補足(2026-08-02)**: 当初はCoworkのスケジュールタスク(`domestic-tweet-queue-poster`)でこの投稿を行う設計だったが、Coworkのサンドボックス環境から`api.twitter.com`への通信が恒常的にブロックされている(403 Forbidden)ことが判明したため、実際の投稿はGitHub Actions側に移行した。GitHub Actionsのランナーは通常のインターネットアクセスを持つため、ここでは問題なく動作する。`domestic-tweet-queue-poster`タスクは無効化済み。X APIの認証情報はリポジトリのGitHub Actions Secretsに設定する必要がある(`X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET`)。

## エンゲージメント計測(土曜9時、生成サイクルの一部として自動実行)
`scripts/fetch_tweet_metrics.py` が過去に投稿した`tweet_id`のインプレッション数・いいね数等を取得し、`docs/engagement_log.json`に記録する。これにより次サイクルのアナリスト役が「一般的ベンチマークで代替」ではなく実データを使えるようになる。X APIは2026年2月から従量課金制(サブスクなし)になっており、自分のアカウントの投稿を読む場合は割引レート($0.001/件)が適用されるため、週数件のチェックであれば実質無視できるコスト。ただし無料枠は無いため、`console.x.com`で事前に少額のクレジットをチャージしておく必要がある。

## 頻度の目安
生成: 週1回(土曜、自動、5〜6本のドラフト。2026-09-12に日曜から変更)
公開判断・publishAt割り当て・SNS投稿キュー登録・push: 週1回(週末、人間がこのチェックリストに沿って実施)
実際の記事公開・SNS投稿: 毎日(自動、人間の作業不要。2026-09-06に火木土から変更)
