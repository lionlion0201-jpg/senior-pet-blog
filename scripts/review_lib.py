#!/usr/bin/env python3
"""
週末レビューの共通ロジック。build_review.py と apply_review.py が使う。

設計の背景
----------
従来の週末レビューは `docs/weekly_publish_review.md` のチェックリストを見ながら、
フロントマターを手で書き換える運用だった。2026-09-19の実作業で以下が判明した:

- 見落としが起きる。実際におむつ記事の「動物病院へ相談を」セクション欠落を
  人間もディレクターも素通りしていた
- 2026-09-19に未公開記事のページ出力を止めた結果、「リンク先がまだ公開されて
  いない記事」へのリンクが公開時に404になるという新しい制約が生まれた。
  これは目視では追えない
- 季節性と公開枠のミスマッチが2件発生した(除湿=旬を逃しかけ、熱中症=旬を過ぎ)

そこで、毎回必ず見るべき項目を機械的に計算してレビュー画面に出す。
人間は「機械が拾えない判断」(事実誤認・商品の実在・文章の質)に集中する。

サイト固有の設定は scripts/review_config.json に外出ししてあり、
このファイル自体はJP/USで共通。
"""
import json
import os
import re
from datetime import date, datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(SCRIPT_DIR, "..")
POSTS_DIR = os.path.join(ROOT, "src", "posts")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "review_config.json")

DRAFT_KEYS = ("published", "permalink", "eleventyExcludeFromCollections")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def split_front_matter(text):
    """(front_matter_dict, front_matter_raw, body) を返す簡易パーサ。

    フルのYAMLパーサは使わない。この運用で扱うフロントマターは
    `key: value` の1行形式だけで、ネストもリストも出てこない。
    依存を増やさないほうが、GitHub Actions側でも動かしやすい。
    """
    if not text.startswith("---"):
        return {}, "", text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, "", text
    raw = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    data = {}
    for line in raw.split("\n"):
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$', line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith('"') and val.endswith('"') and len(val) >= 2:
                val = val[1:-1]
            data[key] = val
    return data, raw, body


def is_draft(fm):
    return fm.get("published") == "false"


def publish_date(fm):
    """その記事が公開される日(YYYY-MM-DD)。下書きなら None。"""
    if is_draft(fm):
        return None
    pa = fm.get("publishAt")
    if pa:
        return pa[:10]
    # publishAt が無い記事は初期に書かれたもので、すでに公開済み扱い
    return "0000-00-00"


def load_posts():
    """src/posts/*.md を全部読んで {slug: {...}} を返す。"""
    posts = {}
    for name in sorted(os.listdir(POSTS_DIR)):
        if not name.endswith(".md"):
            continue
        slug = name[:-3]
        path = os.path.join(POSTS_DIR, name)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        fm, raw, body = split_front_matter(text)
        posts[slug] = {
            "slug": slug,
            "path": path,
            "front_matter": fm,
            "front_matter_raw": raw,
            "body": body,
            "text": text,
            "is_draft": is_draft(fm),
            "publish_date": publish_date(fm),
        }
    return posts


def internal_links(body):
    """本文中の内部リンク先スラッグ一覧。"""
    return sorted(set(re.findall(r"/posts/([a-z0-9-]+)/", body)))


def next_free_slots(posts, count, start_from=None):
    """publishAt が埋まっていない日を count 日分提案する。

    途中に空き日があればそちらを先に埋め、無くなったら最終日の翌日から続ける
    (2026-09-29変更。以前は最終日の翌日からしか提案しなかったため、
     季節ものやセール前など「この日に出したい」記事を差し込んだあとに
     できた穴が埋まらず、公開が途切れる日ができていた)。

    start_from を指定しない場合は翌日から探す。今日はビルド済みなので使わない。
    """
    used = set()
    for p in posts.values():
        d = p["publish_date"]
        if d and d != "0000-00-00":
            used.add(d)

    start = (date.fromisoformat(start_from) if start_from
             else date.today() + timedelta(days=1))
    slots = []

    # 1) 既存の予約のあいだに空いている日を先に埋める
    if used:
        cursor = start
        latest = date.fromisoformat(max(used))
        while cursor <= latest and len(slots) < count:
            s = cursor.isoformat()
            if s not in used:
                slots.append(s)
            cursor += timedelta(days=1)
        # 既存の予約がすべて過去なら、過去日を提案しないよう start から続ける
        cursor = max(latest + timedelta(days=1), start)
    else:
        cursor = start

    # 2) 足りない分は最終日の翌日から続ける
    while len(slots) < count:
        s = cursor.isoformat()
        if s not in used and s not in slots:
            slots.append(s)
        cursor += timedelta(days=1)

    return slots


def check_article(post, posts, config, planned_date=None):
    """記事1本に対する機械チェック。問題のリストを返す。

    severity: "error" = 公開すると実害が出る / "warn" = 人間の判断が要る
    """
    issues = []
    body = post["body"]
    fm = post["front_matter"]

    # 1. 内部リンク先の公開日順序。リンク先がまだ公開されていないと404になる。
    #    2026-09-19にページ出力を止めた副作用で生まれた制約。目視では追えない。
    for slug in internal_links(body):
        target = posts.get(slug)
        if target is None:
            issues.append(("error", f"リンク先の記事が存在しない: {slug}"))
            continue
        tdate = target["publish_date"]
        if tdate is None:
            issues.append(("error", f"リンク先がまだ下書き: {slug}(公開日を決めるか、リンクを外す)"))
        elif planned_date and tdate > planned_date:
            issues.append(("error",
                           f"リンク先の公開が後になる: {slug} は {tdate} 公開。"
                           f"この記事を {planned_date} に出すと404になる"))

    # 2. 必須セクション(JPは動物病院への相談導線、USは医療免責)
    for heading in config.get("required_sections", []):
        if heading not in body:
            issues.append(("error", f"必須セクションが無い: 「{heading.lstrip('# ')}」"))

    # 2b. 必須の言い回し(USの医療免責のように、見出しではなく本文中の文言で
    #     担保しているもの。いずれか1つ含まれていればよい)
    phrases = config.get("required_phrases_any", [])
    if phrases and not any(ph.lower() in body.lower() for ph in phrases):
        issues.append(("error",
                       "医療免責の文言が見当たらない(いずれか必要: "
                       + " / ".join(phrases) + ")"))

    # 3. アフィリエイトリンクの体裁
    tag = config.get("amazon_tag")
    links = re.findall(r'<a[^>]+href="(https://www\.amazon\.[^"]+)"[^>]*>', body)
    for href in links:
        if tag and f"tag={tag}" not in href:
            issues.append(("error", f"Amazonタグが付いていないリンク: {href[:70]}"))
    for m in re.finditer(r'<a[^>]+href="https://(?:www\.amazon\.|af\.moshimo\.com)[^"]*"([^>]*)>', body):
        if "sponsored" not in m.group(1):
            issues.append(("error", 'rel="nofollow sponsored" が付いていないアフィリエイトリンクがある'))
            break
    if not links:
        issues.append(("warn", "Amazonリンクが1本も無い"))

    # 3b. CTAで商品名を単品で名指ししていないか(JPの方針。2026-09-21決定)
    #     このサイトの読者は「何があるのか知らない」段階で来るため、
    #     単品ではなくカテゴリの入り口を示す。詳細は共通ルールの「CTAの出し方」。
    #     CTAボックス内の <strong> がラベル(末尾がコロン)になっているかで判定する。
    if config.get("cta_strong_must_be_label"):
        for m in re.finditer(r'<div class="cta-box">(.*?)</div>', body, re.S):
            sm = re.search(r"<strong>(.*?)</strong>", m.group(1), re.S)
            if sm:
                t = sm.group(1).strip()
                if t and not re.search(r"[:：]$", t):
                    issues.append(("warn",
                                   f"CTAで商品名を名指ししている可能性: 「{t[:40]}」。"
                                   "このサイトはカテゴリで示す方針"))

    # 4. 断定表現
    # 英語サイトでは大文字小文字が混在するので、常に大小を無視して探す
    for pat in config.get("ng_patterns", []):
        for m in re.finditer(pat, body, re.I):
            issues.append(("warn", f"断定的な表現の疑い: 「{m.group(0)}」"))

    # 5. タイトル重複
    title = fm.get("title", "")
    for other in posts.values():
        if other["slug"] == post["slug"]:
            continue
        if other["front_matter"].get("title") == title and title:
            issues.append(("error", f"タイトルが既存記事と重複: {other['slug']}"))

    # 6. 季節性と公開予定日の整合
    if planned_date:
        month = int(planned_date[5:7])
        for kw, months in config.get("seasonal_keywords", {}).items():
            if kw.lower() in title.lower() and month not in months:
                issues.append(("warn",
                               f"季節性のずれ: 「{kw}」を含むが {month}月公開の予定。"
                               f"旬は {'/'.join(str(m) for m in months)}月"))

    # 7. 分量
    if len(body) < 2000:
        issues.append(("warn", f"本文が短い({len(body)}文字)。他記事は4000〜6000文字程度"))

    # 8. Amazonアソシエイト規約まわり(2026-09-29追加)
    issues.extend(check_amazon_policy(body, config))

    return issues


# --- Amazonアソシエイト規約に関するチェック -------------------------------
#
# 根拠(2026-09-29に一次情報を確認):
#  JP「商品の紹介で注意すべきことは何ですか?」
#    https://affiliate.amazon.co.jp/help/node/topic/GKT6X2R3NGW5V23K
#    - 価格や在庫を書く場合は「いつの時点の情報か」を明記すること
#    - 配送料無料の表記は決められた言い回しのいずれかを使うこと
#    - Amazonの商品画像の加工・再アップロード・画面キャプチャは不可
#  JP「クーポンのコードを自分のWebサイトに掲載してもよいですか?」
#    https://affiliate.amazon.co.jp/help/node/topic/GUPDNS3EVD952D97
#    - 掲載不可。違反するとアカウント閉鎖や紹介料差し押さえの可能性
#  US Operating Agreement / Policies
#    https://affiliate-program.amazon.com/help/operating/policies
#    - 価格・在庫の表示は Amazon が配信するリンク、または PA-API / Creators API
#      経由で取得した場合に限られる(手書きの価格は不可。JPより厳しい)
#    - 期間限定プロモーションへのリンクおよび関連する記述は、
#      プロモーション終了と同時にサイトから削除すること
#
# 運用方針: 価格は書かない。セール告知は campaign.js の時限ブロックに閉じ込める。
# 詳しくは共通ルールの「セール記事の書き方」を参照。

# 配送料無料として使ってよい言い回し(JPヘルプに列挙されているもの)
SHIPPING_OK_PHRASES = [
    "配送料無料(一部除く)",
    "配送料無料（一部除く）",
    "通常配送無料(一部除く)",
    "通常配送無料（一部除く）",
    "Amazon.co.jpが発送する商品は、配送料無料(条件あり)",
    "Amazon.co.jpが発送する商品は、配送料無料（条件あり）",
]

# 「いつ時点の情報か」を示していると見なす手がかり
AS_OF_HINTS = ["時点", "as of", "現在の価格", "確認した"]

# 期間限定プロモーションを指す語。時限ブロックの外に出ていたら警告する
PROMO_WORDS = [
    "プライム感謝祭", "プライムデー", "ブラックフライデー", "サイバーマンデー",
    "初売り", "タイムセール祭り", "Prime Day", "Black Friday", "Cyber Monday",
]


def _strip_campaign_blocks(body):
    """{% if campaign... %} ... {% endif %} の中身を取り除いた本文を返す。

    時限ブロックの中に書かれたセール告知は、終了後に自動で消えるので
    規約上の「終了したら削除」を満たしている。外にあるものだけを問題にする。
    """
    return re.sub(r"\{%-?\s*if\s+campaign.*?\{%-?\s*endif\s*-?%\}", "", body, flags=re.S)


def check_amazon_policy(body, config):
    issues = []
    lang = config.get("lang", "ja")
    outside = _strip_campaign_blocks(body)

    # 8a. 価格の記載
    if lang == "ja":
        price_hits = re.findall(r"[0-9０-９][0-9０-９,，]*\s*円", body)
    else:
        price_hits = re.findall(r"\$\s?[0-9][0-9,]*(?:\.[0-9]{2})?", body)
    if price_hits:
        dated = any(h in body for h in AS_OF_HINTS)
        if lang == "ja" and dated:
            issues.append(("warn",
                           f"価格らしい記載がある: {', '.join(price_hits[:3])}。"
                           "「いつ時点か」は書かれているようだが、"
                           "古くなると規約違反になる。原則は価格を書かない運用"))
        elif lang == "ja":
            issues.append(("error",
                           f"価格を書いている: {', '.join(price_hits[:3])}。"
                           "JPは「いつ時点の情報か」の明記が必須。"
                           "このサイトは価格を書かない方針なので削除する"))
        else:
            issues.append(("error",
                           f"Price written by hand: {', '.join(price_hits[:3])}. "
                           "US policy allows prices only from Amazon-served links "
                           "or PA-API / Creators API. Remove it."))

    # 8b. 割引率・値引き幅の記載(いつ時点かに関わらず、終了後に残ると違反)
    off_hits = re.findall(r"[0-9０-９]+\s*(?:%|％)\s*(?:オフ|OFF|off|引き|割引)", body)
    off_hits += re.findall(r"(?:半額|最大[0-9０-９]+\s*(?:%|％))", body)
    if off_hits:
        issues.append(("error",
                       f"値引き率を書いている: {', '.join(off_hits[:3])}。"
                       "対象も率も変動し、終了後に残ると規約違反になる"))

    # 8c. 配送料無料の表記ゆれ
    if re.search(r"(送料|配送料)\s*(が)?\s*(無料|0円|タダ)|free shipping", body, re.I):
        if not any(p in body for p in SHIPPING_OK_PHRASES):
            issues.append(("error",
                           "配送料無料の書き方が規約の指定表現と一致していない。"
                           "「配送料無料(一部除く)」「通常配送無料(一部除く)」"
                           "「Amazon.co.jpが発送する商品は、配送料無料(条件あり)」"
                           "のいずれかを使うこと"))

    # 8d. クーポンコード(掲載自体が禁止)
    if re.search(r"クーポンコード|プロモーションコード|coupon code|promo code", body, re.I):
        issues.append(("error",
                       "クーポンコードの掲載は禁止されている"
                       "(アカウント閉鎖・紹介料差し押さえの対象)"))

    # 8e. 期間限定プロモーションの言及が時限ブロックの外に出ていないか
    for w in PROMO_WORDS:
        if w in outside:
            issues.append(("error",
                           f"「{w}」が時限ブロックの外にある。"
                           "期間限定プロモーションへの言及は終了と同時に"
                           "削除する必要がある。"
                           "{% if campaign.phase %} ... {% endif %} の中に入れること"))
            break

    # 8f. Amazonの商品画像を直接使っていないか
    if re.search(r"(images-amazon|media-amazon|ssl-images-amazon)", body):
        issues.append(("error",
                       "Amazonの画像URLを直接埋め込んでいる。"
                       "商品画像の利用はAmazonが提供するリンク経由に限られる"))

    return issues


def parse_sns_drafts(cycle_log_path):
    """サイクルログからプロモーターのSNS投稿案を抜き出す。

    形式:
      ### 記事N: <見出し>
      - [hook] 本文
      - [list] 本文
    戻り値: [{"heading": ..., "drafts": {"hook": "...", ...}}, ...]
    """
    if not os.path.exists(cycle_log_path):
        return []
    with open(cycle_log_path, encoding="utf-8") as f:
        text = f.read()
    section = re.search(r"^## [^\n]*プロモーター出力[^\n]*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not section:
        return []
    blocks = []
    for m in re.finditer(r"^### (.+?)$(.*?)(?=^### |\Z)", section.group(1), re.M | re.S):
        drafts = {}
        for dm in re.finditer(r"^- \[(\w+)\]\s*(.+?)$", m.group(2), re.M):
            drafts[dm.group(1)] = dm.group(2).strip()
        if drafts:
            blocks.append({"heading": m.group(1).strip(), "drafts": drafts})
    return blocks
