#!/usr/bin/env python3
"""
Fetch impression/engagement metrics for tweets we've already posted, and log
them to docs/engagement_log.json so the weekend pipeline can use real data
instead of guessing ("benchmark") the way the analyst role currently has to.

How it keeps cost near-zero:
- X API pricing (2026-02-06 onward) is pay-per-usage, no free tier.
- Looking up posts via GET /2/tweets (arbitrary IDs) costs $0.005/post.
- Looking up posts via GET /2/users/{id}/tweets, where {id} is the
  authenticated account's OWN user ID, qualifies for "Owned Reads" pricing:
  $0.001/post (5x cheaper). This script always uses the owned-reads endpoint
  (tweepy's Client.get_users_tweets), never the arbitrary-ID lookup.
- The account's numeric user ID is fetched once via GET /2/users/me (a
  one-time ~$0.01 charge) and cached locally in scripts/.x_user_id_cache so
  we never pay for it again.

Usage:
  python3 fetch_tweet_metrics.py [--dry-run] [--max-results 25]

--dry-run prints what would be fetched/logged without calling the API or
writing files (useful for checking credentials/config are wired up).

Requires a credit balance on the X Developer account (console.x.com) — with
no balance, requests will fail with a 402/insufficient-credit style error,
which this script surfaces clearly rather than silently failing.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import tweepy  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

JST = timezone(timedelta(hours=9))
SCRIPT_DIR = os.path.dirname(__file__)
USER_ID_CACHE = os.path.join(SCRIPT_DIR, ".x_user_id_cache")
QUEUE_FILE = os.path.join(SCRIPT_DIR, "..", "docs", "tweet_schedule.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "..", "docs", "engagement_log.json")


def get_client():
    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_secret = os.environ.get("X_ACCESS_TOKEN_SECRET")
    if not all([api_key, api_secret, access_token, access_secret]):
        raise SystemExit("X API credentials missing in .env")
    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )


def get_own_user_id(client, dry_run=False):
    if os.path.exists(USER_ID_CACHE):
        with open(USER_ID_CACHE) as f:
            cached = f.read().strip()
            if cached:
                return cached

    if dry_run:
        print("[DRY RUN] Would call GET /2/users/me to resolve + cache own user ID (one-time ~$0.01)")
        return "DRY_RUN_USER_ID"

    me = client.get_me()
    user_id = str(me.data.id)
    with open(USER_ID_CACHE, "w") as f:
        f.write(user_id)
    return user_id


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-results", type=int, default=25, help="How many recent own tweets to check (max 100)")
    args = parser.parse_args()

    queue = load_json(QUEUE_FILE, [])
    # Only entries that were actually posted and have a real tweet_id are worth checking.
    posted_entries = {e["tweet_id"]: e for e in queue if e.get("posted") and e.get("tweet_id")}

    if not posted_entries:
        print("No posted tweets with a recorded tweet_id yet — nothing to fetch.")
        return

    client = get_client()
    user_id = get_own_user_id(client, dry_run=args.dry_run)

    if args.dry_run:
        print(f"[DRY RUN] Would call GET /2/users/{user_id}/tweets (Owned Reads, $0.001/post) "
              f"with tweet.fields=public_metrics, max_results={args.max_results}")
        print(f"[DRY RUN] Would then match against {len(posted_entries)} known tweet_id(s) in tweet_schedule.json "
              f"and append results to {os.path.basename(LOG_FILE)}")
        return

    try:
        resp = client.get_users_tweets(
            id=user_id,
            max_results=max(5, min(args.max_results, 100)),
            tweet_fields=["public_metrics", "created_at"],
        )
    except tweepy.TweepyException as e:
        print(f"X API error while fetching metrics: {e}", file=sys.stderr)
        print("If this is a credit/balance error, add credits at https://console.x.com", file=sys.stderr)
        sys.exit(1)

    if not resp.data:
        print("No tweets returned from the API for this account.")
        return

    log = load_json(LOG_FILE, [])
    checked_at = datetime.now(JST).isoformat()
    matched = 0

    for tweet in resp.data:
        tid = str(tweet.id)
        if tid not in posted_entries:
            continue
        entry = posted_entries[tid]
        metrics = tweet.public_metrics or {}
        log.append({
            "checked_at": checked_at,
            "tweet_id": tid,
            "article": entry.get("article"),
            "type": entry.get("type"),
            "posted_date": entry.get("date"),
            "impression_count": metrics.get("impression_count"),
            "like_count": metrics.get("like_count"),
            "retweet_count": metrics.get("retweet_count"),
            "reply_count": metrics.get("reply_count"),
            "quote_count": metrics.get("quote_count"),
        })
        matched += 1

    if matched:
        save_json(LOG_FILE, log)
        print(f"Logged metrics for {matched} tweet(s) to {os.path.basename(LOG_FILE)}.")
    else:
        print("Fetched recent tweets, but none matched a known queued tweet_id (may be outside max_results window).")


if __name__ == "__main__":
    main()
