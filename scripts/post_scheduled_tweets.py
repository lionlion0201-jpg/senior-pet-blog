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

    for entry in due:
        print(f"Posting queued tweet for {entry.get('article', '?')} (id={entry.get('id')})...")
        try:
            result = post_tweet(entry["text"], dry_run=args.dry_run)
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
        except SystemExit as e:
            print(f" Skipped (rate limit guard): {e}", file=sys.stderr)

    if not args.dry_run:
        save_queue(queue)


if __name__ == "__main__":
    main()
