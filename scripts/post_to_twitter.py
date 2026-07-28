#!/usr/bin/env python3
"""
Post a tweet to X via API v2 (OAuth 1.0a user context) using tweepy.

Usage:
  python3 post_to_twitter.py --text "新着記事:老犬の段差対策..." [--dry-run]
"""
import argparse
import os
import sys
import tweepy
from dotenv import load_dotenv

load_dotenv()

STATE_FILE = os.path.join(os.path.dirname(__file__), ".post_count_state")


def _posts_made_today():
    if not os.path.exists(STATE_FILE):
        return 0
    with open(STATE_FILE) as f:
        return int(f.read().strip() or 0)


def _record_post():
    count = _posts_made_today() + 1
    with open(STATE_FILE, "w") as f:
        f.write(str(count))
    return count


def post_tweet(text, dry_run=False):
    max_per_run = int(os.environ.get("MAX_POSTS_PER_RUN", "6"))
    current = _posts_made_today()
    if current >= max_per_run:
        raise SystemExit(
            f"Refusing to post: MAX_POSTS_PER_RUN ({max_per_run}) already reached this run cycle. "
            f"Reset scripts/.post_count_state to override."
        )

    if dry_run:
        print("[DRY RUN] Would post tweet:")
        print(" ", text)
        return {"dry_run": True}

    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_secret = os.environ.get("X_ACCESS_TOKEN_SECRET")
    if not all([api_key, api_secret, access_token, access_secret]):
        raise SystemExit("X API credentials missing in .env (X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET)")

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )
    resp = client.create_tweet(text=text[:280])
    _record_post()
    return resp.data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        result = post_tweet(args.text, args.dry_run)
        print(result)
    except tweepy.TweepyException as e:
        print(f"X API error: {e}", file=sys.stderr)
        sys.exit(1)
