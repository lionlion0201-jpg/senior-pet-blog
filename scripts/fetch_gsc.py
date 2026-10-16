#!/usr/bin/env python3
"""
Search Console API から検索のデータを取得し、docs/metrics/ に保存する。

2026-10-16 に X の自動投稿を止めて検索(SEO)に集中する方針にした。その判断材料として、
記事ごとに「検索結果に載っているか」「どれだけ表示・クリックされたか」「何位か」
「どんな検索語で出たか」を毎日取る。

出力:
  docs/metrics/gsc_pages.json    記事ごとの表示回数・クリック数・平均掲載順位(直近28日)
  docs/metrics/gsc_queries.json  検索語 × 記事ごとの表示回数・クリック数・平均掲載順位(直近28日)
  docs/metrics/gsc_index.json    サイトマップの各URLのインデックス状態(URL検査API)

Search Console のデータは2〜3日遅れて確定するため、期間の終わりは3日前にしている。

必要な設定(GitHub Actions):
  Secret GA4_SA_KEY(GA4 と同じサービスアカウント。Search Console の各プロパティにユーザーとして追加済み)
  Google Cloud で Search Console API を有効化済みであること

Usage:
  python3 fetch_gsc.py [--days 28] [--no-inspect]
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

JST = timezone(timedelta(hours=9))
ROOT = os.path.join(os.path.dirname(__file__), "..")
METRICS_DIR = os.path.join(ROOT, "docs", "metrics")


def site_url():
    with open(os.path.join(ROOT, "src", "_data", "site.json"), encoding="utf-8") as f:
        url = json.load(f)["url"].rstrip("/")
    return url + "/"


def get_service():
    key = os.environ.get("GA4_SA_KEY", "").strip()
    if not key:
        raise SystemExit("GA4_SA_KEY が設定されていません")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(key), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def query(svc, prop, start, end, dims):
    rows, start_row = [], 0
    while True:
        resp = svc.searchanalytics().query(siteUrl=prop, body={
            "startDate": start, "endDate": end, "dimensions": dims,
            "rowLimit": 25000, "startRow": start_row,
        }).execute()
        batch = resp.get("rows", [])
        rows += batch
        if len(batch) < 25000:
            return rows
        start_row += 25000


def save(name, data):
    os.makedirs(METRICS_DIR, exist_ok=True)
    with open(os.path.join(METRICS_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sitemap_urls(prop):
    with urllib.request.urlopen(prop + "sitemap.xml", timeout=30) as r:
        return re.findall(r"<loc>([^<]+)</loc>", r.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--no-inspect", action="store_true", help="URL検査(インデックス状態)を行わない")
    args = parser.parse_args()

    prop = site_url()
    svc = get_service()
    today = datetime.now(JST).date()
    end = (today - timedelta(days=3)).isoformat()
    start = (today - timedelta(days=3 + args.days)).isoformat()
    period = {"period_start": start, "period_end": end}

    # 1. 記事ごと
    try:
        page_rows = query(svc, prop, start, end, ["page"])
    except Exception as e:
        if "sufficient permission" not in str(e):
            raise
        # 権限エラーの切り分け用。メールアドレスとアクセスできるプロパティは秘密情報ではない
        email = json.loads(os.environ["GA4_SA_KEY"]).get("client_email")
        sites = [s["siteUrl"] + "(" + s["permissionLevel"] + ")"
                 for s in svc.sites().list().execute().get("siteEntry", [])]
        raise SystemExit(f"{prop} を見る権限がありません。サービスアカウント: {email}\n"
                         f"このアカウントがアクセスできるプロパティ: {sites or 'なし'}\n"
                         f"Search Console の {prop} →「設定」→「ユーザーと権限」に上のアドレスを追加してください。")
    pages = [{"page": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"],
              "position": round(r["position"], 1), **period}
             for r in page_rows]
    save("gsc_pages.json", pages)

    # 2. 検索語 × 記事
    queries = [{"query": r["keys"][0], "page": r["keys"][1], "clicks": r["clicks"],
                "impressions": r["impressions"], "position": round(r["position"], 1), **period}
               for r in query(svc, prop, start, end, ["query", "page"])]
    save("gsc_queries.json", queries)
    print(f"{prop} {start}〜{end}: 表示 {sum(p['impressions'] for p in pages)}回 / "
          f"クリック {sum(p['clicks'] for p in pages)}回 / 表示されたページ {len(pages)} / 検索語 {len({q['query'] for q in queries})}")

    # 3. インデックス状態(URL検査API。1プロパティ1日2000件まで。記事数は十分小さい)
    if args.no_inspect:
        return
    index, errors = [], 0
    checked_at = datetime.now(JST).isoformat()
    for url in sitemap_urls(prop):
        try:
            res = svc.urlInspection().index().inspect(body={"inspectionUrl": url, "siteUrl": prop}).execute()
        except Exception as e:  # 1件の失敗で全体を止めない
            errors += 1
            print(f"URL検査に失敗: {url}: {str(e).splitlines()[0][:150]}", file=sys.stderr)
            continue
        r = res.get("inspectionResult", {}).get("indexStatusResult", {})
        index.append({"url": url, "verdict": r.get("verdict"), "coverage": r.get("coverageState"),
                      "last_crawl": r.get("lastCrawlTime"), "google_canonical": r.get("googleCanonical"),
                      "checked_at": checked_at})
    save("gsc_index.json", index)
    passed = sum(1 for i in index if i["verdict"] == "PASS")
    print(f"インデックス済み {passed} / 検査 {len(index)} URL(失敗 {errors})")
    if errors and not index:
        sys.exit(1)


if __name__ == "__main__":
    main()
