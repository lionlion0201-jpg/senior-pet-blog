#!/usr/bin/env python3
"""週末レビューで書き出した decisions.json を、取り込み → 反映 → commit → push まで一度に行う。

使い方:
  python3 scripts/apply_decisions.py                          # ダウンロードフォルダから自動で探す
  python3 scripts/apply_decisions.py ~/Downloads/decisions.json  # ファイルを指定する

ファイルを指定しないときは ~/Downloads/decisions*.json のうち、site が JP で、
中の decided_at(書き出した日時)が最も新しいものを使う。ファイル名の (1)(2) や
US の書き出しが混ざっていても、中身で判断する。前回反映した decided_at は
docs/review/applied.json に残し、それより古い・同じものは反映済みとして使わない。

反映済みの JP のファイルは ~/Downloads/レビュー決定/JP/decisions_JP_YYMMDD.json に
移す(日付は書き出した日の日本時間。同じ日に2つあれば _2 を付ける)。US のファイルは
US 側の反映がまだかもしれないので、このスクリプトでは動かさない。

やること(途中で失敗したらそこで止まり、push はしない):
  1. ダウンロードフォルダに残っている反映済みの JP のファイルを片付ける
  2. ファイルが JP のレビュー画面の書き出しで、まだ反映していないものか確かめる
  3. git pull --rebase --autostash でリモートに追いつく
  4. docs/review/decisions.json にコピーする
  5. apply_review.py --dry-run → apply_review.py(error があれば apply_review.py 側で中断)
  6. src/posts と docs を commit して push する(push が競合したら1回だけ取り込み直す)
  7. 使ったファイルを JP の保管フォルダに移す
"""
from datetime import datetime, timedelta, timezone
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEST = os.path.join(ROOT, "docs", "review", "decisions.json")
APPLIED = os.path.join(ROOT, "docs", "review", "applied.json")
DOWNLOADS = os.path.expanduser("~/Downloads")
ARCHIVE = os.path.join(DOWNLOADS, "レビュー決定", "JP")
SITE = "シニアペットのくらし (JP)"
JST = timezone(timedelta(hours=9))
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def run(*cmd, check=True):
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    if check and r.returncode != 0:
        sys.exit(f"中断: {' '.join(cmd)} が失敗しました(終了コード {r.returncode})")
    return r.returncode


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def last_applied():
    return (load(APPLIED) or {}).get("decided_at", "")


def jp_files_in_downloads():
    """ダウンロードフォルダ直下の JP の書き出しを (decided_at, path) の古い順で返す。"""
    found = []
    for path in glob.glob(os.path.join(DOWNLOADS, "decisions*.json")):
        data = load(path)
        if data and data.get("site") == SITE and data.get("decided_at"):
            found.append((data["decided_at"], path))
    return sorted(found)


def archive_name(decided_at):
    """decisions_JP_YYMMDD.json(日本時間の書き出し日)。同じ名前があれば _2, _3 … を付ける。"""
    try:
        day = datetime.fromisoformat(decided_at.replace("Z", "+00:00")).astimezone(JST)
        stem = f"decisions_JP_{day:%y%m%d}"
    except ValueError:
        stem = "decisions_JP_unknown"
    name, n = f"{stem}.json", 1
    while os.path.exists(os.path.join(ARCHIVE, name)):
        n += 1
        name = f"{stem}_{n}.json"
    return name


def archive(path, decided_at):
    if os.path.dirname(os.path.abspath(path)) != DOWNLOADS:
        return path  # 保管フォルダなど、ダウンロード直下以外のファイルは動かさない
    os.makedirs(ARCHIVE, exist_ok=True)
    dest = os.path.join(ARCHIVE, archive_name(decided_at))
    shutil.move(path, dest)
    print(f"移動: {os.path.basename(path)} → レビュー決定/JP/{os.path.basename(dest)}")
    return dest


def tidy_downloads():
    """反映済み(applied.json の日時以前)の JP のファイルを保管フォルダへ移す。"""
    done = last_applied()
    for decided_at, path in jp_files_in_downloads():
        if decided_at <= done:
            archive(path, decided_at)


def find_latest():
    """ダウンロードフォルダから、JP の書き出しで decided_at が最も新しいものを返す。"""
    found = jp_files_in_downloads()
    if not found:
        sys.exit("新しい決定ファイルはありません(ダウンロードフォルダに未反映の JP の decisions*.json が無い)。")
    return found[-1][1]


def main():
    if len(sys.argv) > 2:
        sys.exit("使い方: python3 scripts/apply_decisions.py [decisions.json のパス]")
    tidy_downloads()
    src = os.path.expanduser(sys.argv[1]) if len(sys.argv) == 2 else find_latest()
    data = load(src)
    if data is None:
        sys.exit(f"中断: {src} を読めません")
    if data.get("site") != SITE:
        sys.exit(f"中断: 別サイトの決定ファイルです(site={data.get('site')!r})")
    decided_at = data.get("decided_at", "")
    print(f"使うファイル: {src}(書き出し {decided_at})")
    if decided_at and decided_at <= last_applied():
        sys.exit(f"中断: このファイルは反映済みです(前回反映した書き出し {last_applied()})。"
                 "新しい決定はまだダウンロードされていないようです。")
    decisions = data.get("decisions") or []
    approved = [d for d in decisions if d.get("decision") == "approve"]
    if not approved:
        sys.exit("承認された記事がありません。何もしません。")

    run("git", "pull", "--rebase", "--autostash")
    shutil.copyfile(src, DEST)
    run("python3", "scripts/apply_review.py", "--dry-run")
    run("python3", "scripts/apply_review.py")

    with open(APPLIED, "w", encoding="utf-8") as f:
        json.dump({"decided_at": decided_at, "file": f"レビュー決定/JP/{archive_name(decided_at)}",
                   "approved": [d["slug"] for d in approved]}, f, ensure_ascii=False, indent=2)
        f.write("\n")
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
    archive(src, decided_at)
    print(f"完了: {len(approved)}本を反映して push しました。")


if __name__ == "__main__":
    main()
