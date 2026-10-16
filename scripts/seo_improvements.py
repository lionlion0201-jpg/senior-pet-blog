#!/usr/bin/env python3
"""
既存記事の検索向け改善(タイトル・説明文・内部リンク)を、提案 → 人の承認 → 反映 → 4週間後の振り返り
の流れで扱う。2026-10-16 追加。

なぜ提案と反映を分けるか:
  公開中の記事を書き換えると、push した時点で本番に出る。新しい記事と同じく、
  人(如月さん)が変更前後を見て承認したものだけを反映する。

ファイル:
  docs/seo/proposals/YYYY-MM-DD.json  週次パイプラインが書き出す改善案(記事は書き換えない)
      [{"id": "2026-10-17-1", "slug": "...", "query": "狙う検索語", "reason": "根拠",
        "changes": [{"file": "src/posts/xxx.md", "old": "変更前の文字列(ファイル内で1回だけ出現)", "new": "変更後"}]}]
  docs/seo/improvement_log.json       反映した改善の記録(反映時点の順位・表示・クリックを残す)

使い方:
  python3 scripts/seo_improvements.py list                 未反映の改善案を一覧する(変更前→変更後)
  python3 scripts/seo_improvements.py apply ID [ID ...]     承認された案を記事に反映し、記録に残す
  python3 scripts/seo_improvements.py review                反映から28日以上たった改善の、反映時と現在の比較
"""
import glob
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
ROOT = os.path.join(os.path.dirname(__file__), "..")
PROPOSALS = os.path.join(ROOT, "docs", "seo", "proposals")
LOG = os.path.join(ROOT, "docs", "seo", "improvement_log.json")
GSC_PAGES = os.path.join(ROOT, "docs", "metrics", "gsc_pages.json")
REVIEW_AFTER_DAYS = 28


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def gsc_for(slug):
    for p in load(GSC_PAGES, []):
        if f"/posts/{slug}/" in p["page"]:
            return {"position": p["position"], "impressions": p["impressions"], "clicks": p["clicks"],
                    "period_end": p["period_end"]}
    return {"position": None, "impressions": 0, "clicks": 0, "period_end": None}


def all_proposals():
    out = []
    for path in sorted(glob.glob(os.path.join(PROPOSALS, "*.json"))):
        for p in load(path, []):
            out.append((path, p))
    return out


def applied_ids():
    return {e["id"] for e in load(LOG, [])}


def cmd_list():
    done = applied_ids()
    pending = [(path, p) for path, p in all_proposals() if p["id"] not in done and p.get("status") != "rejected"]
    if not pending:
        print("未反映の改善案はありません。")
        return
    for _, p in pending:
        g = gsc_for(p["slug"])
        print(f"\n[{p['id']}] {p['slug']}  現在 {g['position']}位 / 表示{g['impressions']} / クリック{g['clicks']}")
        print(f"  狙う検索語: {p.get('query', '-')}")
        print(f"  根拠: {p.get('reason', '-')}")
        for c in p["changes"]:
            print(f"  - {c['file']}")
            print(f"    変更前: {c['old']}")
            print(f"    変更後: {c['new']}")


def cmd_apply(ids):
    log = load(LOG, [])
    done = {e["id"] for e in log}
    found = {p["id"]: p for _, p in all_proposals()}
    for i in ids:
        if i in done:
            print(f"{i}: 反映済みのためスキップ")
            continue
        p = found.get(i)
        if not p:
            sys.exit(f"{i}: 改善案が見つかりません")
        # 先にすべての置換が成り立つか確かめてから書き込む(途中まで反映された状態を作らない)
        texts = {}
        for c in p["changes"]:
            path = os.path.join(ROOT, c["file"])
            t = texts.get(path) or open(path, encoding="utf-8").read()
            n = t.count(c["old"])
            if n != 1:
                sys.exit(f"{i}: {c['file']} で変更前の文字列が {n} 回見つかりました(1回である必要があります)。"
                         "記事が提案後に変わった可能性があるので、提案を作り直してください。")
            texts[path] = t.replace(c["old"], c["new"])
        for path, t in texts.items():
            with open(path, "w", encoding="utf-8") as f:
                f.write(t)
        log.append({"id": i, "slug": p["slug"], "query": p.get("query"), "reason": p.get("reason"),
                    "applied_at": datetime.now(JST).date().isoformat(), "before": gsc_for(p["slug"]),
                    "changes": p["changes"]})
        print(f"{i}: {p['slug']} に反映しました")
    save(LOG, log)


def cmd_review():
    today = datetime.now(JST).date()
    rows = [e for e in load(LOG, [])
            if (today - date.fromisoformat(e["applied_at"])).days >= REVIEW_AFTER_DAYS]
    if not rows:
        print(f"反映から{REVIEW_AFTER_DAYS}日以上たった改善はまだありません。")
        return
    print("| 改善 | 反映日 | 狙う検索語 | 順位(反映時→現在) | 表示(反映時→現在) | クリック(反映時→現在) |")
    print("|---|---|---|---|---|---|")
    for e in rows:
        b, n = e["before"], gsc_for(e["slug"])
        print(f"| {e['slug']} | {e['applied_at']} | {e.get('query') or '-'} | {b['position']}→{n['position']} | "
              f"{b['impressions']}→{n['impressions']} | {b['clicks']}→{n['clicks']} |")
    print("\n表示100回未満の記事の順位は日々大きく動く。変化を改善の効果と断定しない。")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "apply", "review"):
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "list":
        cmd_list()
    elif sys.argv[1] == "apply":
        cmd_apply(sys.argv[2:])
    else:
        cmd_review()


if __name__ == "__main__":
    main()
