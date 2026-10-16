#!/usr/bin/env python3
"""
記事単位のファネル表を docs/metrics/digest.md に生成する。

設計の背景: アフィリエイト/共通/計測設計.md
  - 判断の主軸はアフィリエイトリンクのクリック(GA4 affiliate_click)。インプレッションは
    クリックが伸びない原因の切り分けにだけ使う
  - サンプル数が足りない比較は「データ不足」と書き、結論を出さない

国内(JP)・海外(US)どちらのリポジトリでも同じファイルを置いて動く。
  JP: docs/tweet_schedule.json + docs/engagement_log.json
  US: docs/metrics/posted_assets.json + x_metrics.json + pin_metrics.json

GA4 のクリック(affiliate_click)は Data API 未連携のため取り込まない。
docs/metrics/ga4_clicks.json が置かれたら読む(形式は下の load_ga4_clicks を参照)。
それまでは表に「未取得」と出す。推測で埋めないこと。

Usage:
  python3 scripts/build_digest.py [--today YYYY-MM-DD]
"""
import argparse
import glob
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DOCS = os.path.join(ROOT, "docs")
METRICS = os.path.join(DOCS, "metrics")
OUT = os.path.join(METRICS, "digest.md")

# JPのX投稿は 2026-09-21 までURLが入っていなかった(流入を生まない)。型の比較から除外する。
LINK_ERA_START = "2026-09-22"
# 計測設計.md「読み方のルール」1 の目安
MIN_POSTS_PER_TYPE = 20
MIN_SESSIONS_PER_ARTICLE = 100
MIN_GSC_IMPRESSIONS = 100  # 検索の表示回数。これ未満の記事の順位比較は結論しない
NA = "未取得"
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


# ---------------------------------------------------------------- 読み込み
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def parse_dt(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(JST)


def load_articles():
    arts = {}
    for path in glob.glob(os.path.join(ROOT, "src", "posts", "*.md")):
        slug = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = re.match(r"^---\n(.*?)\n---", text, re.S)
        fm = {}
        if m:
            for line in m.group(1).splitlines():
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"').strip("'")
        pub = (fm.get("publishAt") or fm.get("date") or "")[:10]
        arts[slug] = {"title": fm.get("title", slug), "date": pub, "category": fm.get("category") or "未設定"}
    return arts


def latest_by(records, key):
    """同じ投稿の時系列から最新の checked_at のものだけ残す(累計値なので最新が正)。"""
    best = {}
    for r in records:
        k = str(r.get(key))
        if k not in best or (r.get("checked_at") or "") > (best[k].get("checked_at") or ""):
            best[k] = r
    return best


def load_ga4_clicks():
    """GA4連携後に置く想定のファイル。形式:
    [{"article": "/posts/<slug>/", "affiliate_clicks": 3, "sessions": 120,
      "source": "x|pinterest|organic|...", "period_end": "YYYY-MM-DD"}]
    """
    path = os.path.join(METRICS, "ga4_clicks.json")
    data = load_json(path, None)
    if not data:
        return None
    agg = defaultdict(lambda: {"clicks": 0, "sessions": 0})
    for r in data:
        m = re.search(r"/posts/([^/]+)/?", r.get("article", ""))
        if not m:
            continue
        agg[m.group(1)]["clicks"] += r.get("affiliate_clicks") or 0
        agg[m.group(1)]["sessions"] += r.get("sessions") or 0
    return agg


# ---------------------------------------------------------------- 投稿の正規化
def load_posts():
    """(site, posts, status) を返す。posts は 1投稿1行の dict のリスト。"""
    status = []
    posts = []
    queue_path = os.path.join(DOCS, "tweet_schedule.json")
    if os.path.exists(queue_path):
        site = "JP"
        queue = load_json(queue_path, [])
        log = load_json(os.path.join(DOCS, "engagement_log.json"), [])
        latest = latest_by(log, "tweet_id")
        status.append(("docs/engagement_log.json(Xメトリクス)", len(log), len(latest), last_checked(log)))
        for e in queue:
            if not e.get("posted"):
                continue
            tid = str(e.get("tweet_id") or "")
            m = latest.get(tid)
            posted_at = parse_dt(e.get("posted_at"))
            posts.append({
                "platform": "X", "id": tid, "article": e.get("article"), "type": e.get("type"),
                "posted_at": posted_at,
                "link_era": bool(posted_at and posted_at.strftime("%Y-%m-%d") >= LINK_ERA_START),
                "impression": m.get("impression_count") if m else None,
                "outbound": None,
            })
        unposted_past = [e for e in queue if not e.get("posted") and LINK_ERA_START <= e.get("date", "") < today_str()]
        return site, posts, status, {"queue": queue, "unposted_past": unposted_past}

    site = "US"
    ledger = load_json(os.path.join(METRICS, "posted_assets.json"), [])
    xlog = load_json(os.path.join(METRICS, "x_metrics.json"), [])
    plog = load_json(os.path.join(METRICS, "pin_metrics.json"), [])
    xl, pl = latest_by(xlog, "tweet_id"), latest_by(plog, "pin_id")
    status.append(("docs/metrics/posted_assets.json(投稿台帳)", len(ledger), len(ledger), "-"))
    status.append(("docs/metrics/x_metrics.json(Xメトリクス)", len(xlog), len(xl), last_checked(xlog)))
    status.append(("docs/metrics/pin_metrics.json(ピンメトリクス)", len(plog), len(pl), last_checked(plog)))
    for r in ledger:
        plat = r.get("platform")
        rid = str(r.get("id"))
        if plat == "x":
            m = xl.get(rid)
            posts.append({"platform": "X", "id": rid, "article": r.get("article"), "type": r.get("type"),
                          "posted_at": parse_dt(r.get("posted_at")), "link_era": True,
                          "impression": m.get("impression_count") if m else None, "outbound": None})
        elif plat == "pinterest":
            m = pl.get(rid)
            posts.append({"platform": "Pinterest", "id": rid, "article": r.get("article"), "type": r.get("type"),
                          "posted_at": parse_dt(r.get("posted_at")), "link_era": True,
                          "impression": m.get("impression") if m else None,
                          "outbound": m.get("outbound_click") if m else None})
    # 台帳外で x_metrics にだけあるツイート(遡及紐付けされたもの)も拾う
    known = {p["id"] for p in posts}
    for tid, m in xl.items():
        if tid not in known:
            posts.append({"platform": "X", "id": tid, "article": m.get("article"), "type": m.get("type"),
                          "posted_at": parse_dt(m.get("created_at")), "link_era": True,
                          "impression": m.get("impression_count"), "outbound": None})
    return site, posts, status, {}


def last_checked(log):
    vals = [r.get("checked_at") for r in log if r.get("checked_at")]
    return max(vals)[:16].replace("T", " ") if vals else "なし"


_TODAY = None


def today_str():
    return _TODAY or datetime.now(JST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 表示
def fmt(v):
    if v is None:
        return NA
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # Pinterest API は回数を 0.0 のような小数で返すことがある
    return f"{v:,}"


def ssum(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def rate(num, den):
    if num is None or den in (None, 0):
        return NA
    return f"{num / den:.2%}"


def group_table(posts, keyfn, label, ga4=None, articles=None):
    groups = defaultdict(list)
    for p in posts:
        groups[keyfn(p)].append(p)
    lines = [f"| {label} | 投稿数 | 計測済み | 配信(imp) | ピン→サイト遷移 | リンククリック(GA4) | クリック到達率 |",
             "|---|---:|---:|---:|---:|---|---|"]
    for k in sorted(groups, key=lambda x: str(x)):
        g = groups[k]
        measured = [p for p in g if p["impression"] is not None]
        lines.append(f"| {k} | {len(g)} | {len(measured)} | {fmt(ssum(p['impression'] for p in g))} | "
                     f"{fmt(ssum(p['outbound'] for p in g))} | {NA} | {NA} |")
    return lines


def slug_of(url):
    m = re.search(r"/posts/([^/]+)/?", url or "")
    return m.group(1) if m else None


def gsc_section(arts):
    """Search Console の記事別の成績(2026-10-16 検索に集中する方針で追加)。

    元データは fetch_gsc.py が毎晩保存する gsc_pages / gsc_queries / gsc_index。
    """
    pages = load_json(os.path.join(METRICS, "gsc_pages.json"), None)
    index = load_json(os.path.join(METRICS, "gsc_index.json"), None)
    queries = load_json(os.path.join(METRICS, "gsc_queries.json"), [])
    L = ["## 検索(Search Console)", ""]
    if not pages and not index:
        return L + ["未取得(`fetch_gsc.py` の実行待ち)。", ""]

    per = {}
    for p in pages or []:
        s = slug_of(p["page"])
        if s:
            per[s] = p
    top_query = {}
    for q in sorted(queries, key=lambda q: -q["impressions"]):
        s = slug_of(q["page"])
        if s and s not in top_query:
            top_query[s] = q
    indexed = {slug_of(i["url"]): i["verdict"] == "PASS" for i in index or [] if slug_of(i["url"])}

    if pages:
        tot_imp = sum(p["impressions"] for p in pages)
        tot_clk = sum(p["clicks"] for p in pages)
        L.append(f"期間: {pages[0]['period_start']}〜{pages[0]['period_end']}(Search Console は2〜3日遅れて確定する)/ "
                 f"表示 {tot_imp:,}回 / クリック {tot_clk:,}回")
    if index:
        L.append(f"検索結果に載っている記事: {sum(indexed.values())} / {len(indexed)}"
                 f"(サイトマップの記事URLを URL 検査 API で確認)")
    L.append("")
    L.append(f"表示が少ない記事の順位は日々大きく動く。表示{MIN_GSC_IMPRESSIONS}回未満の記事どうしの比較は「データ不足」とする。")
    L.append("")
    L.append("| 記事 | 公開日 | 掲載 | 表示 | クリック | クリック率 | 平均順位 | 表示の多い検索語(順位) |")
    L.append("|---|---|---|---:|---:|---:|---:|---|")
    slugs = set(per) | set(indexed)
    for s in sorted(slugs, key=lambda s: (-(per.get(s, {}).get("impressions") or 0), s)):
        a = arts.get(s, {"title": s, "date": "?"})
        # 期間中に一度も表示されなかった記事は gsc_pages に行が無い。未取得ではなく0として出す
        p = per.get(s) or ({"impressions": 0, "clicks": 0, "position": None} if pages is not None else None)
        tq = top_query.get(s)
        mark = {True: "○", False: "×"}.get(indexed.get(s), "-")
        L.append(f"| {a['title'][:40]} | {a['date']} | {mark} | {fmt(p and p['impressions'])} | {fmt(p and p['clicks'])} | "
                 f"{rate(p and p['clicks'], p and p['impressions'])} | {fmt(p and p['position']) if p and p['position'] is not None else '-'} | "
                 f"{(tq['query'][:30] + '(' + str(tq['position']) + ')') if tq else '-'} |")
    L.append("")
    near = [s for s, p in per.items() if 8 <= p["position"] <= 30 and p["impressions"] >= 10]
    if near:
        L.append("**伸ばす候補**(平均8〜30位・表示10回以上。1ページ目の下〜2ページ目にいて、タイトル・説明文・内部リンク・内容の補強で上位を狙える): "
                 + "、".join(f"`{s}`({per[s]['position']}位)" for s in sorted(near, key=lambda s: per[s]["position"])))
        L.append("")
    missing = sorted(s for s, ok in indexed.items() if not ok)
    if missing:
        L.append("**検索結果に未掲載**: " + "、".join(f"`{s}`" for s in missing)
                 + "(Search Console の URL 検査からインデックス登録をリクエストできる)")
        L.append("")
    return L


def build(today):
    global _TODAY
    _TODAY = today
    site, posts, status, extra = load_posts()
    arts = load_articles()
    ga4 = load_ga4_clicks()
    measured = [p for p in posts if p["impression"] is not None]
    L = []
    L.append(f"# ファネル表({site})")
    L.append("")
    L.append(f"生成日: {today} / 生成: `scripts/build_digest.py`(手で編集しない)")
    L.append("")
    L.append("読み方は `docs/agents/analyst.md` の「読み方のルール」に従う。**インプレッションは売上の指標ではない。**"
             "判断の主軸はアフィリエイトリンクのクリック(GA4 `affiliate_click`)。")
    L.append("")

    # --- データの状態
    L.append("## データの状態")
    L.append("")
    L.append("| ソース | レコード数 | 対象投稿数 | 最終取得 |")
    L.append("|---|---:|---:|---|")
    for name, n, uniq, last in status:
        L.append(f"| {name} | {n} | {uniq} | {last} |")
    L.append(f"| GA4 `affiliate_click` | {'あり' if ga4 else NA} | - | {'-' if ga4 else 'Data API未連携(管理画面でのみ閲覧可)'} |")
    gsc_pages = load_json(os.path.join(METRICS, "gsc_pages.json"), None)
    L.append(f"| Search Console | {len(gsc_pages) if gsc_pages else NA} | - | "
             f"{(gsc_pages[0]['period_end'] + ' まで') if gsc_pages else '未取得'} |")
    L.append("")
    warnings = []
    if not measured:
        warnings.append("**配信メトリクスが1件も取得できていない。** 以下の表の配信列はすべて「未取得」。"
                        "取得ワークフロー(`fetch-metrics.yml`)の失敗を先に解消すること")
    if not ga4:
        warnings.append("リンククリック(GA4)は未取得。クリック到達率はすべて「未取得」。推測で埋めない")
    if site == "JP" and extra.get("unposted_past"):
        n = len(extra["unposted_past"])
        warnings.append(f"{LINK_ERA_START}以降の予約のうち {n}件が予定日を過ぎても未投稿"
                        "(`post_scheduled_tweets.py` は当日分しか投稿しないため自動では再投稿されない)")
    if site == "US" and not any(p["platform"] == "X" for p in posts):
        warnings.append("台帳にXの投稿が1件も無い(台帳導入後のX投稿が発生していない、または遡及紐付けが未実行)")
    for w in warnings:
        L.append(f"- ⚠ {w}")
    L.append("")

    # --- 型の比較の判定
    xposts = [p for p in posts if p["platform"] == "X"]
    if xposts:
        L.append("## X投稿の型の比較(hook / cta など)")
        L.append("")
        if site == "JP":
            L.append(f"{LINK_ERA_START}より前の投稿は記事URLが入っておらず流入を生まないため**比較対象外**。")
            L.append("")
        cmp = [p for p in xposts if p["link_era"]]
        L.append(f"| 型 | 比較対象の投稿数 | うち計測済み | 目安 | 判定 |")
        L.append("|---|---:|---:|---:|---|")
        types = sorted({p["type"] or "不明" for p in cmp}) or ["hook", "cta"]
        for t in types:
            g = [p for p in cmp if (p["type"] or "不明") == t]
            m = [p for p in g if p["impression"] is not None]
            if t == "不明":
                # 型の記録が無い投稿の寄せ集め。件数が多くても比較の材料にならない
                verdict = "比較対象外(型が記録されていない)"
            elif len(m) >= MIN_POSTS_PER_TYPE:
                verdict = "判断可(ただしクリック未取得なら保留)"
            else:
                verdict = "**データ不足**(従来方針を維持)"
            L.append(f"| {t} | {len(g)} | {len(m)} | {MIN_POSTS_PER_TYPE} | {verdict} |")
        excluded = [p for p in xposts if not p["link_era"]]
        if excluded:
            L.append(f"| (比較対象外: リンク無し期) | {len(excluded)} | - | - | 混ぜない |")
        L.append("")
        L.append("リンククリック(GA4)が取れていない間は、計測済み件数が目安に達しても型の優劣は結論しない"
                 "(インプレッション単体で型を評価しない)。")
        L.append("")

    # --- 検索(Search Console)
    L += gsc_section(arts)

    # --- 記事単位
    L.append("## 記事単位のファネル")
    L.append("")
    L.append(f"記事の比較はセッション{MIN_SESSIONS_PER_ARTICLE}以上が目安。セッションもGA4由来のため現時点では未取得。")
    L.append("")
    L.append("| 記事 | 公開日 | 投稿数 | 配信(imp) | ピン→サイト遷移 | リンククリック | クリック到達率 |")
    L.append("|---|---|---:|---:|---:|---|---|")
    by_art = defaultdict(list)
    for p in posts:
        by_art[p["article"] or "(記事不明)"].append(p)
    for slug in sorted(by_art, key=lambda s: arts.get(s, {}).get("date", ""), reverse=True):
        g = by_art[slug]
        a = arts.get(slug, {"title": slug, "date": "?"})
        imp = ssum(p["impression"] for p in g)
        clicks = ga4[slug]["clicks"] if ga4 and slug in ga4 else None
        L.append(f"| {a['title'][:40]} | {a['date']} | {len(g)} | {fmt(imp)} | "
                 f"{fmt(ssum(p['outbound'] for p in g))} | {fmt(clicks)} | {rate(clicks, imp)} |")
    L.append("")

    # --- 集計軸
    L.append("## 集計軸")
    L.append("")
    L.append("### テーマ・商品カテゴリ別")
    L.append("")
    if site == "JP":
        L.append("JP記事のフロントマターには `category` が無い。商品カテゴリはGA4の `link_target`(検索キーワード)で見る想定で、"
                 "GA4連携までは記事単位の表で代替する。")
    else:
        L += group_table(posts, lambda p: arts.get(p["article"], {}).get("category", "未設定"), "カテゴリ")
    L.append("")
    L.append("### 投稿の型別")
    L.append("")
    L += group_table([p for p in posts if p["link_era"]], lambda p: f"{p['platform']} / {p['type'] or '不明'}", "チャネル / 型")
    L.append("")
    L.append("### 曜日・時間帯別(JST、投稿時刻)")
    L.append("")
    L += group_table([p for p in posts if p["posted_at"]],
                     lambda p: f"{WEEKDAYS[p['posted_at'].weekday()]} {p['posted_at'].hour:02d}時台", "曜日 時間帯")
    L.append("")
    L.append("### 流入元別")
    L.append("")
    L += group_table(posts, lambda p: p["platform"], "流入元")
    L.append("| 検索 | - | - | 上の「検索(Search Console)」を参照 | - | - | - |")
    L.append("")
    L.append("サイトへの流入(セッション)とリンククリックは流入元を問わずGA4由来のため、現時点では比較できない。")
    L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", help="生成日(YYYY-MM-DD, JST)。省略時は今日")
    args = ap.parse_args()
    today = args.today or datetime.now(JST).strftime("%Y-%m-%d")
    os.makedirs(METRICS, exist_ok=True)
    text = build(today)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
