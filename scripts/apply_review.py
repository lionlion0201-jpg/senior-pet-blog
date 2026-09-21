#!/usr/bin/env python3
"""
レビュー画面が書き出した decisions.json を実ファイルに反映する。

  python3 scripts/build_review.py          # レビュー画面を生成
  (ブラウザで判断して decisions.json をダウンロード → docs/review/ に置く)
  python3 scripts/apply_review.py --dry-run  # 何が起きるか確認
  python3 scripts/apply_review.py            # 実際に反映

やること
--------
承認された記事について:
  1. フロントマターから published/permalink/eleventyExcludeFromCollections を削除し、
     date と publishAt を追加する
  2. 選ばれたSNS投稿案を tweet_schedule.json に追加する(記事の公開日と同じ日付)
  3. Pinterest用のマニフェストがあれば、保留場所から本来の場所へ移す(USサイト用)

見送られた記事は何もしない(下書きのまま残る)。

適用前に必ず再チェックする
--------------------------
レビュー画面を開いてから決定するまでの間に、他の記事の公開日が変わっている
可能性がある。特に内部リンクの公開日順序は、片方を動かすともう片方が壊れる。
error が1件でも残っていれば中断する(--force で無視できるが、原則使わない)。
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from review_lib import (  # noqa: E402
    ROOT, DRAFT_KEYS, load_config, load_posts, check_article,
)

DECISIONS_PATH = os.path.join(ROOT, "docs", "review", "decisions.json")


def rewrite_front_matter(post, publish_date, config):
    """下書き用の3行を外し、date と publishAt を入れる。"""
    raw = post["front_matter_raw"]
    lines = [ln for ln in raw.split("\n")
             if not any(re.match(rf"^{k}:", ln) for k in DRAFT_KEYS)]

    stamp = f'{publish_date}T{config["publish_hour"]}{config["timezone_offset"]}'
    lines = [ln for ln in lines if not re.match(r"^(date|publishAt):", ln)]

    out = []
    for ln in lines:
        out.append(ln)
        if ln.startswith("description:"):
            out.append(f"date: {publish_date}")
    if not any(ln.startswith("date:") for ln in out):
        out.append(f"date: {publish_date}")

    final = []
    for ln in out:
        final.append(ln)
        if ln.startswith("tags:"):
            final.append(f'publishAt: "{stamp}"')
    if not any(ln.startswith("publishAt:") for ln in final):
        final.append(f'publishAt: "{stamp}"')

    return "---\n" + "\n".join(final) + "\n---\n\n" + post["body"]


def append_tweet(queue_path, slug, date_str, sns_type, text):
    queue = []
    if os.path.exists(queue_path):
        with open(queue_path, encoding="utf-8") as f:
            queue = json.load(f)
    entry_id = f"{date_str}-{slug}-{sns_type}"
    if any(e.get("id") == entry_id for e in queue):
        return False
    queue.append({
        "id": entry_id,
        "date": date_str,
        "article": slug,
        "type": sns_type,
        "text": text,
        "posted": False,
        "posted_at": None,
    })
    queue.sort(key=lambda e: (e.get("date", ""), e.get("type", "")))
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    return True


def release_pending_manifest(slug):
    """USサイト用。保留中のマニフェストを本来の場所へ移す。

    docs/cycles/pending/ に置いてある間はワークフローのパス指定
    (docs/cycles/cycle_manifest_*.json)に一致しないので投稿が走らない。
    承認したときに初めて移動し、pushで投稿処理が動く。
    """
    pending_dir = os.path.join(ROOT, "docs", "cycles", "pending")
    if not os.path.isdir(pending_dir):
        return None
    for name in os.listdir(pending_dir):
        if slug in name and name.endswith(".json"):
            src = os.path.join(pending_dir, name)
            dst = os.path.join(ROOT, "docs", "cycles", name)
            shutil.move(src, dst)
            return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="再チェックでerrorが出ても強行する(原則使わない)")
    ap.add_argument("--decisions", default=DECISIONS_PATH)
    args = ap.parse_args()

    if not os.path.exists(args.decisions):
        raise SystemExit(f"{args.decisions} がありません。"
                         "レビュー画面で「決定を書き出す」を押して、"
                         "ダウンロードされた decisions.json をここに置いてください。")

    with open(args.decisions, encoding="utf-8") as f:
        decisions = json.load(f)

    config = load_config()
    posts = load_posts()
    approved = [d for d in decisions["decisions"] if d.get("decision") == "approve"]
    skipped = [d for d in decisions["decisions"] if d.get("decision") == "skip"]
    undecided = [d for d in decisions["decisions"] if not d.get("decision")]

    print(f"承認 {len(approved)}本 / 見送り {len(skipped)}本 / 未判断 {len(undecided)}本")
    if undecided:
        for d in undecided:
            print(f"  未判断のまま: {d['slug']}")

    # --- 適用前の再チェック ---
    planned = {d["slug"]: d["publish_date"] for d in approved}
    problems = []

    dates = [d["publish_date"] for d in approved]
    for dup in {x for x in dates if dates.count(x) > 1}:
        problems.append(f"公開日が重複している: {dup}")
    for p in posts.values():
        if p["slug"] in planned:
            continue
        if p["publish_date"] in dates and p["publish_date"] not in (None, "0000-00-00"):
            problems.append(f"既存記事と公開日が衝突: {p['slug']} が {p['publish_date']}")

    # 承認分を「その日付で公開される」ものとして仮に反映してから相互チェックする。
    # そうしないと、同時に承認した記事どうしのリンク順序を判定できない。
    simulated = {k: dict(v) for k, v in posts.items()}
    for slug, d in planned.items():
        if slug in simulated:
            simulated[slug]["publish_date"] = d
            simulated[slug]["is_draft"] = False

    for d in approved:
        post = posts.get(d["slug"])
        if post is None:
            problems.append(f"記事が見つからない: {d['slug']}")
            continue
        for sev, msg in check_article(post, simulated, config, planned_date=d["publish_date"]):
            if sev == "error":
                problems.append(f"{d['slug']}: {msg}")

    if problems:
        print("\n適用前チェックで問題が見つかりました:")
        for p in problems:
            print(f"  [error] {p}")
        if not args.force:
            raise SystemExit("\n中断しました。修正してからやり直してください"
                             "(どうしても強行する場合は --force)。")
        print("\n--force が指定されたため続行します。")

    # --- 適用 ---
    queue_path = os.path.join(ROOT, config["tweet_queue"]) if config.get("tweet_queue") else None
    for d in approved:
        post = posts[d["slug"]]
        new_text = rewrite_front_matter(post, d["publish_date"], config)
        print(f"\n[{d['slug']}] 公開日 {d['publish_date']}")
        if args.dry_run:
            print("  " + "\n  ".join(new_text.split("\n---")[0].split("\n")[1:]))
        else:
            with open(post["path"], "w", encoding="utf-8") as f:
                f.write(new_text)
            print("  フロントマターを更新")

        if d.get("sns_type") and d.get("sns_text") and queue_path:
            if args.dry_run:
                print(f"  SNS[{d['sns_type']}]を {d['publish_date']} に登録予定")
            else:
                added = append_tweet(queue_path, d["slug"], d["publish_date"],
                                     d["sns_type"], d["sns_text"])
                print(f"  SNS[{d['sns_type']}]を登録" if added else "  SNSは登録済みのためスキップ")

        if config.get("has_pins"):
            if args.dry_run:
                print("  保留中のマニフェストがあれば公開位置へ移動予定")
            else:
                moved = release_pending_manifest(d["slug"])
                print(f"  マニフェストを公開位置へ移動: {moved}" if moved
                      else "  対応するマニフェストは見つかりませんでした")

    if args.dry_run:
        print("\n(dry-run のため何も書き換えていません)")
    else:
        print("\n反映しました。内容を確認してから commit・push してください。")
        print("  git add -A src/posts docs && git commit && git push")


if __name__ == "__main__":
    main()
