"""保留中の下書き(docs/drafts_on_hold/)のうち、戻す日を過ぎたものを src/posts/ に戻す。

フロントマターの `holdUntil: "YYYY-MM-DD"` が今日(JST)以前の記事が対象。
戻すときは holdUntil の行だけ外し、非公開の3行はそのまま残す
(戻した記事は下書きとして次の週末レビューに出る)。

週次の記事生成タスクが毎回最初に実行する。git の操作はしない
(移動はローカルだけ。週末レビュー後の commit にまとめて入る)。

  python3 scripts/restore_held_drafts.py            # 戻す
  python3 scripts/restore_held_drafts.py --dry-run  # 何が戻るかだけ表示
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from review_lib import split_front_matter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOLD_DIR = os.path.join(ROOT, "docs", "drafts_on_hold")
POSTS_DIR = os.path.join(ROOT, "src", "posts")


def main():
    dry_run = "--dry-run" in sys.argv
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    restored, waiting = [], []

    for name in sorted(os.listdir(HOLD_DIR)) if os.path.isdir(HOLD_DIR) else []:
        if not name.endswith(".md") or name == "README.md":
            continue
        path = os.path.join(HOLD_DIR, name)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        fm, _, _ = split_front_matter(text)
        until = fm.get("holdUntil", "")
        if not until or until > today:
            waiting.append(f"{name}(戻す日: {until or '未設定'})")
            continue
        dest = os.path.join(POSTS_DIR, name)
        if os.path.exists(dest):
            print(f"スキップ: {name} は src/posts/ に同名のファイルがある")
            continue
        restored.append(f"{name}(戻す日: {until})")
        if dry_run:
            continue
        text = re.sub(r"^holdUntil:.*\n", "", text, count=1, flags=re.M)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
        os.remove(path)

    label = "戻す予定" if dry_run else "戻した"
    print(f"{label}: {', '.join(restored) if restored else 'なし'}")
    print(f"保留のまま: {', '.join(waiting) if waiting else 'なし'}")


if __name__ == "__main__":
    main()
