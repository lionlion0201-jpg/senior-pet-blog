#!/usr/bin/env python3
"""
X(旧Twitter)の自動投稿用アクセストークンを、指定したアカウントで発行し直して
GitHub Secrets に登録する。

なぜ必要か
----------
2026-10-10 の点検で、JP(シニアペット)の投稿が US(QuietRecover)と同じアカウント
(@95wDCuNebX41439)から出ていたことが分かった。9/10 に JP 用のトークンを作ったとき、
US のアカウントでログインしたまま発行したとみられる。X の開発者画面でトークンを
作ると、そのときログインしているアカウントの投稿権限になるため、取り違えやすい。

このスクリプトは、ブラウザで「どのアカウントで許可するか」を選ぶ方式(PIN方式)で
トークンを作り、最後に「どのアカウントのトークンか」を表示してから登録する。
違うアカウントだったら登録せずに止まる。

やること:
  1. 開発者アプリの API Key / API Key Secret を入力してもらう(Secret は画面に表示しない)
  2. 認可URLを表示 → ブラウザで JP のアカウントにログインして「許可」→ 表示された番号(PIN)を入力
  3. 発行されたトークンで「誰のトークンか」を確認し、@ユーザー名を表示する
  4. 想定のアカウントだと確認できたら、GitHub Secrets の X_API_KEY / X_API_SECRET /
     X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET を上書きする
     (gh CLI に標準入力で渡すので、値は画面にもファイルにも残らない)

注意: 開発者アプリの権限が "Read and write" になっていないと投稿できない。
      アプリの権限を変えた場合は、変えた後に発行したトークンでないと反映されない。

Usage(自分のターミナルで):
  python3 scripts/setup_x_oauth.py
"""
import getpass
import os
import subprocess
import sys

import tweepy

REPO = "lionlion0201-jpg/senior-pet-blog"
GH = os.path.expanduser("~/.local/bin/gh")
# 取り違えの元になったアカウント。これで許可してしまったら登録しない
WRONG_ACCOUNT = "95wDCuNebX41439"


def set_secret(name, value):
    subprocess.run([GH, "secret", "set", name, "-R", REPO], input=value.encode(), check=True)


def main():
    print("X の開発者アプリ(https://console.x.com)の Keys and tokens にある値を入力してください。")
    api_key = input("API Key: ").strip()
    api_secret = getpass.getpass("API Key Secret(入力しても表示されません): ").strip()
    if not api_key or not api_secret:
        sys.exit("API Key と API Key Secret の両方が必要です。")

    auth = tweepy.OAuth1UserHandler(api_key, api_secret, callback="oob")
    try:
        url = auth.get_authorization_url()
    except tweepy.TweepyException as e:
        sys.exit(f"認可URLを作れませんでした。API Key / Secret を確認してください({e})")

    print()
    print("1. いま X にログインしているアカウントを、ブラウザで一度ログアウトしてください")
    print("   (または別のブラウザ/シークレットウィンドウを使う)")
    print("2. 下のURLを開き、**シニアペット用(JP)のアカウント**でログインして「連携アプリを認証」を押す")
    print("3. 表示された番号(PIN)を、ここに入力する")
    print()
    print(url)
    print()
    pin = input("PIN: ").strip()

    try:
        token, token_secret = auth.get_access_token(pin)
    except tweepy.TweepyException as e:
        sys.exit(f"PIN からトークンを作れませんでした。もう一度最初からやり直してください({e})")

    client = tweepy.Client(consumer_key=api_key, consumer_secret=api_secret,
                           access_token=token, access_token_secret=token_secret)
    try:
        me = client.get_me(user_auth=True).data
    except tweepy.TweepyException as e:
        sys.exit(f"トークンの持ち主を確認できませんでした({e})")

    print()
    print(f"このトークンのアカウント: @{me.username}({me.name})")
    if me.username.lower() == WRONG_ACCOUNT.lower():
        sys.exit("これは US と共用になっていたアカウントです。登録せずに終了します。"
                 "JP のアカウントでログインし直して、もう一度実行してください。")

    answer = input(f"@{me.username} を JP サイトの投稿用として登録しますか? [y/N]: ").strip().lower()
    if answer != "y":
        sys.exit("登録しませんでした。")

    for name, value in [("X_API_KEY", api_key), ("X_API_SECRET", api_secret),
                        ("X_ACCESS_TOKEN", token), ("X_ACCESS_TOKEN_SECRET", token_secret)]:
        set_secret(name, value)
    print(f"{REPO} の Secrets に登録しました。次の投稿から @{me.username} で投稿されます。")
    print(f"アカウントID(メモ用): {me.id}")


if __name__ == "__main__":
    main()
