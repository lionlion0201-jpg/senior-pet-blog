#!/usr/bin/env python3
"""
GA4 Data API から、記事ごとのアフィリエイトリンクのクリック数(affiliate_click)と
セッション数を取得し、docs/metrics/ga4_clicks.json に保存する。

build_digest.py はこのファイルを読んで、ファネル表の「リンククリック」
「クリック到達率」の列を埋める。インプレッションではなくクリックで判断するための土台。

記事の特定には GA4 標準の pagePath(イベントが発生したページ)を使う。
カスタムディメンション(customEvent:article 等)の登録状況に左右されないようにするため。
商品単位の内訳(customEvent:link_target / customEvent:product)は、登録されていれば
docs/metrics/ga4_products.json に追加で保存する。登録されていなければ飛ばす。

必要な設定(GitHub Actions):
  Secret   GA4_SA_KEY       サービスアカウントの JSON 鍵(中身まるごと)
  Variable GA4_PROPERTY_ID  数字のプロパティID

Usage:
  python3 fetch_ga4.py [--days 30]
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Filter, FilterExpression, Metric, RunReportRequest,
)
from google.oauth2 import service_account

JST = timezone(timedelta(hours=9))
METRICS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "metrics")
OUT_FILE = os.path.join(METRICS_DIR, "ga4_clicks.json")
PRODUCTS_FILE = os.path.join(METRICS_DIR, "ga4_products.json")

# affiliate_click の計測は 2026-09-20 に開始し、当日は動作確認のため自分でクリックしている。
# その分が混ざらないよう、翌日以降だけを集計する。
FLOOR_DATE = "2026-09-21"


def get_client():
    key = os.environ.get("GA4_SA_KEY", "").strip()
    if not key:
        raise SystemExit("GA4_SA_KEY が設定されていません(GitHub の Secrets に登録が必要)")
    info = json.loads(key)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    return BetaAnalyticsDataClient(credentials=creds)


def run(client, prop, start, end, dims, metric, event_name=None):
    req = RunReportRequest(
        property=f"properties/{prop}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=metric)],
        limit=10000,
    )
    if event_name:
        req.dimension_filter = FilterExpression(filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(value=event_name)))
    resp = client.run_report(req)
    rows = []
    for r in resp.rows:
        rows.append(([v.value for v in r.dimension_values], int(float(r.metric_values[0].value or 0))))
    return rows


def norm_path(p):
    p = (p or "").split("?")[0].split("#")[0]
    if p and not p.endswith("/"):
        p += "/"
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    prop = os.environ.get("GA4_PROPERTY_ID", "").strip()
    if not prop:
        raise SystemExit("GA4_PROPERTY_ID が設定されていません(GitHub の Variables に登録が必要)")

    today = datetime.now(JST).date()
    start = max((today - timedelta(days=args.days)).isoformat(), FLOOR_DATE)
    end = today.isoformat()
    client = get_client()

    agg = defaultdict(lambda: {"affiliate_clicks": 0, "sessions": 0})

    # 1. クリック: イベントが発生したページ × 流入元
    for (path, source), n in run(client, prop, start, end, ["pagePath", "sessionSource"],
                                 "eventCount", event_name="affiliate_click"):
        agg[(norm_path(path), source)]["affiliate_clicks"] += n

    # 2. セッション: ランディングページ × 流入元(クリック到達率の分母)
    for (path, source), n in run(client, prop, start, end, ["landingPage", "sessionSource"], "sessions"):
        agg[(norm_path(path), source)]["sessions"] += n

    out = []
    for (path, source), v in sorted(agg.items()):
        if not v["affiliate_clicks"] and not v["sessions"]:
            continue
        out.append({
            "article": path,
            "source": source,
            "affiliate_clicks": v["affiliate_clicks"],
            "sessions": v["sessions"],
            "period_start": start,
            "period_end": end,
        })

    os.makedirs(METRICS_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    clicks = sum(r["affiliate_clicks"] for r in out)
    sessions = sum(r["sessions"] for r in out)
    print(f"{start}〜{end}: affiliate_click {clicks}件 / セッション {sessions} / {len(out)}行 → ga4_clicks.json")

    # 3. 商品単位(カスタムディメンションが登録されている場合だけ)
    products = []
    for dim in ("customEvent:link_target", "customEvent:product"):
        try:
            rows = run(client, prop, start, end, ["pagePath", dim], "eventCount", event_name="affiliate_click")
        except Exception as e:  # 未登録のディメンションは API がエラーを返す
            print(f"{dim} は取得できないので飛ばします: {str(e).splitlines()[0][:150]}")
            continue
        for (path, value), n in rows:
            if value and value != "(not set)":
                products.append({"article": norm_path(path), "dimension": dim.split(":", 1)[1],
                                 "value": value, "affiliate_clicks": n,
                                 "period_start": start, "period_end": end})
    if products:
        with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"商品単位の内訳 {len(products)}行 → ga4_products.json")


if __name__ == "__main__":
    main()
