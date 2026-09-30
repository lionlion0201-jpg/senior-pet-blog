#!/usr/bin/env python3
"""
Post today's queued tweets from docs/tweet_schedule.json.

Intended to be run by the Tue/Thu/Sat scheduled task, right after the
GitHub Pages rebuild has published that day's embargoed (publishAt) articles.

docs/tweet_schedule.json format (a list of entries):
[
  {
    "id": "2026-08-04-rougan-dansa-taisaku",
    "date": "2026-08-04",        # JST date this tweet should go out (matches the article's publishAt date)
    "article": "rougan-dansa-taisaku",
    "text": "新着記事:...",
    "posted": false,
    "posted_at": null
  }
]

Usage:
  python3 post_scheduled_tweets.py [--dry-run] [--date YYYY-MM-DD]

--date overrides "today" (JST) for manual testing; otherwise today's JST date is used.
Only entries with posted == false and date == target date are posted.
This script NEVER invents or edits tweet text - it only posts what a human
already approved into the queue during the weekend review.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from post_to_twitter import post_tweet  # noqa: E402
import tweepy  # noqa: E402

QUEUE_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "tweet_schedule.json")
JST = timezone(timedelta(hours=9))


def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
        f.write("\n")


SITE_FILE = os.path.join(os.path.dirname(__file__), "..", "src", "_data", "site.json")


def article_url(slug):
    """記事の本番URLを組み立てる。

    2026-09-21まで、キューのテキストは「記事はこちら👇」で終わっていながら
    URLが一切入っていなかった。投稿21件すべてがリンク無しで流れており、
    Xからの流入は1件も発生していなかった。

    URLは site.json から組み立てる。ベタ書きしないのは、独自ドメインへ
    移行したときに自動で追従させるため。
    """
    if not slug:
        return None
    try:
        with open(SITE_FILE, encoding="utf-8") as f:
            site = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    base = (site.get("url") or "").rstrip("/")
    return f"{base}/posts/{slug}/" if base else None


X_LIMIT = 280
X_URL_WEIGHT = 23  # t.co 短縮後の長さ。URLの実際の長さに関係なく23で数えられる


def char_weight(ch):
    """X の文字数の数え方(twitter-text の既定設定)での1文字の重み。

    ラテン文字・一般的な記号は1、それ以外(日本語・絵文字など)は2。
    2026-09-22 の2件は len() では280以内でも、この数え方では超過しており 403 で拒否された。
    """
    cp = ord(ch)
    if (cp <= 0x10FF or 0x2000 <= cp <= 0x200D or 0x2010 <= cp <= 0x201F
            or 0x2032 <= cp <= 0x2037):
        return 1
    return 2


def x_length(text):
    return sum(char_weight(c) for c in text)


def with_link(text, slug):
    """本文の末尾に記事URLを付ける。すでにURLが入っていれば触らない。

    X の上限(日本語は1文字2、URLは23で数える)を超える場合は、URLが欠けないよう本文の側を削る。
    """
    if "http" in text:
        return text
    url = article_url(slug)
    if not url:
        return text

    # 本文 + 改行(1) + URL(23)
    room = X_LIMIT - 1 - X_URL_WEIGHT
    if x_length(text) <= room:
        return f"{text}\n{url}"

    # まず末尾の行(ハッシュタグ行など)から丸ごと外す。文の途中で切れるのを避けるため
    lines = text.rstrip().split("\n")
    while len(lines) > 1:
        lines.pop()
        trimmed = "\n".join(lines).rstrip()
        if x_length(trimmed) <= room:
            return f"{trimmed}\n{url}"

    # 1行でも収まらないときだけ、「…」(重み2)の分を空けて本文を詰める
    cut, used = [], 0
    for c in text:
        w = char_weight(c)
        if used + w > room - 2:
            break
        cut.append(c)
        used += w
    return f"{''.join(cut).rstrip()}…\n{url}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", help="Override target date (YYYY-MM-DD, JST). Defaults to today in JST.")
    args = parser.parse_args()

    target_date = args.date or datetime.now(JST).strftime("%Y-%m-%d")
    queue = load_queue()
    due = [e for e in queue if e.get("date") == target_date and not e.get("posted")]

    if not due:
        print(f"No queued tweets due for {target_date}.")
        return

    api_errors = 0
    for entry in due:
        print(f"Posting queued tweet for {entry.get('article', '?')} (id={entry.get('id')})...")
        try:
            text = with_link(entry["text"], entry.get("article"))
            result = post_tweet(text, dry_run=args.dry_run)
            print(" ->", result)
            if not args.dry_run:
                entry["posted"] = True
                entry["posted_at"] = datetime.now(JST).isoformat()
                # Save the real X post ID so fetch_tweet_metrics.py can look up
                # impressions/likes/etc. for this specific tweet later.
                if isinstance(result, dict) and result.get("id"):
                    entry["tweet_id"] = result["id"]
        except tweepy.TweepyException as e:
            print(f" X API error, leaving in queue for manual retry: {e}", file=sys.stderr)
            api_errors += 1
        except SystemExit as e:
            print(f" Skipped (rate limit guard): {e}", file=sys.stderr)

    if not args.dry_run:
        save_queue(queue)

    # 2026-09-28: 以前はAPIエラーを握りつぶして正常終了していたため、9/22〜9/28に
    # 11件が未投稿のままワークフローは「成功」表示だった。失敗を Actions 上で見えるようにする。
    # (成功分の posted 記録は上で保存済み。ワークフロー側のコミットは if: always() で走る)
    if api_errors:
        print(f"{api_errors} tweet(s) failed. 402ならX Developer Consoleのクレジット残高を確認。"
              f" 再投稿は --date {target_date} で手動実行。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
