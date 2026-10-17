#!/usr/bin/env python3
"""週末レビューで書き出した decisions.json を、取り込み → 反映 → commit → push まで一度に行う。

使い方:
  python3 scripts/apply_decisions.py ~/Downloads/decisions.json

やること(途中で失敗したらそこで止まり、push はしない):
  1. ファイルが JP のレビュー画面の書き出しか確かめる
  2. git pull --rebase --autostash でリモートに追いつく
  3. docs/review/decisions.json にコピーする
  4. apply_review.py --dry-run → apply_review.py(error があれば apply_review.py 側で中断)
  5. src/posts と docs を commit して push する(push が競合したら1回だけ取り込み直す)
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEST = os.path.join(ROOT, "docs", "review", "decisions.json")
SITE = "シニアペットのくらし (JP)"
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def run(*cmd, check=True):
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    if check and r.returncode != 0:
        sys.exit(f"中断: {' '.join(cmd)} が失敗しました(終了コード {r.returncode})")
    return r.returncode


def main():
    if len(sys.argv) != 2:
        sys.exit("使い方: python3 scripts/apply_decisions.py <decisions.json のパス>")
    src = os.path.expanduser(sys.argv[1])
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("site") != SITE:
        sys.exit(f"中断: 別サイトの決定ファイルです(site={data.get('site')!r})")
    decisions = data.get("decisions") or []
    approved = [d for d in decisions if d.get("decision") == "approve"]
    if not approved:
        sys.exit("承認された記事がありません。何もしません。")

    run("git", "pull", "--rebase", "--autostash")
    shutil.copyfile(src, DEST)
    run("python3", "scripts/apply_review.py", "--dry-run")
    run("python3", "scripts/apply_review.py")

    run("git", "add", "-A", "src/posts", "docs")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        sys.exit("反映による変更がありません(すでに反映済みの可能性)。commit・push はしません。")
    lines = [f"- {d['publish_date']} {d['slug']}" for d in sorted(approved, key=lambda d: d["publish_date"])]
    msg = (f"週末レビューで承認した{len(approved)}本を予約公開に設定\n\n"
           "レビュー画面の決定(decisions.json)を apply_review.py で反映した。\n"
           + "\n".join(lines) + f"\n\n{TRAILER}\n")
    run("git", "commit", "-q", "-m", msg)
    if run("git", "push", check=False) != 0:
        run("git", "pull", "--rebase", "--autostash")
        run("git", "push")
    print(f"完了: {len(approved)}本を反映して push しました。")


if __name__ == "__main__":
    main()
