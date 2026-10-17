#!/usr/bin/env python3
"""
記事ごとの見出し画像(OG 画像、1200x630)を自動生成する。

背景(2026-10-17):
  記事に画像が1枚も無く og:image も無かったため、Google 画像検索・Discover・
  SNS 共有で画像が出なかった。Amazon の商品画像は規約上加工・再アップロード
  できないので使わず、「記事タイトル+サイト名」だけのシンプルな画像を作る。
  画像に入れる文言はタイトルとサイト名だけ(価格・効能などは入れない)。

仕組み:
  - src/posts/*.md のフロントマターから title を読み、og-images/<slug>.png に出力する。
  - og-images/ はリポジトリにコミットしない(.gitignore)。deploy.yml のビルド前に
    GitHub Actions 上で毎回作り直す。
  - サイトへのコピーは .eleventy.js 側で「公開済みの記事の分だけ」行う。
    予約公開待ちの記事の画像(タイトル入り)が先に公開されないようにするため、
    出力先を src/assets/ の外にしている。
  - 1件失敗しても他の記事は続行し、終了コードは常に 0。画像が無い記事は
    テンプレート側で画像タグを出さないので、ビルドと配信は止まらない。

フォントは scripts/fonts/ に同梱(SIL Open Font License。ライセンス文も同じ場所)。
GitHub Actions の ubuntu-latest には日本語フォントが無く、ネットワーク取得は
失敗しうるため、同梱して手元と Actions で同じ見た目にしている。

使い方:
  python3 scripts/generate_og_images.py            # 全記事
  python3 scripts/generate_og_images.py --out DIR  # 出力先を変える(検証用)
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
POSTS_DIR = os.path.join(ROOT, "src", "posts")
SITE_JSON = os.path.join(ROOT, "src", "_data", "site.json")
DEFAULT_OUT = os.path.join(ROOT, "og-images")
FONT_DIR = os.path.join(ROOT, "scripts", "fonts")

WIDTH, HEIGHT = 1200, 630

# --- サイトごとの見た目(src/assets/style.css の CSS 変数に合わせる) -------------
STYLE = {
    "bg": "#faf7f2",           # --bg
    "card": "#ffffff",         # --card
    "border": "#e6ddd2",       # --border
    "text": "#2b2420",         # --text
    "accent": "#b5622a",       # --accent
    "accent_soft": "#f2e2d2",  # --accent-soft
    "title_font": os.path.join(FONT_DIR, "NotoSansJP-Bold.otf"),
    "title_variation": None,   # 可変フォントの軸の値(使わない場合は None)
    "name_font": os.path.join(FONT_DIR, "NotoSansJP-Bold.otf"),
    "name_variation": None,
    "max_lines": 4,
    "title_sizes": range(72, 39, -2),   # 大きい順に試し、収まった最初のサイズを使う
    "line_spacing": 1.35,
    "cjk": True,               # 日本語の折り返し(1文字単位+禁則)
}
# -----------------------------------------------------------------------------

MARGIN = 48                       # 画像の端からカードまで
CARD_PAD_X, CARD_PAD_TOP = 72, 64
FOOTER_H = 110                    # カード下部のサイト名の帯
ACCENT_BAR_W = 12

# 行頭に来てはいけない文字 / 行末に来てはいけない文字(簡易禁則)
NO_LINE_START = set("、。，．・：；？！ー―‐～…）」』】〕〉》｝]）,.:;?!%」ゃゅょぁぃぅぇぉっャュョァィゥェォッ")
NO_LINE_END = set("（「『【〔〈《｛[(")


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def read_title(path):
    """フロントマターの title を読む。このリポジトリの記事は title: "..." の1行形式。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return None
    for line in m.group(1).splitlines():
        kv = re.match(r"^title:\s*(.*)$", line)
        if not kv:
            continue
        val = kv.group(1).strip()
        if len(val) >= 2 and val[0] == val[-1] == '"':
            val = re.sub(r'\\(.)', r"\1", val[1:-1])
        elif len(val) >= 2 and val[0] == val[-1] == "'":
            val = val[1:-1].replace("''", "'")
        return val.strip() or None
    return None


def load_font(path, size, variation):
    from PIL import ImageFont
    font = ImageFont.truetype(path, size)
    if variation:
        font.set_variation_by_axes(variation)
    return font


def tokenize(text, cjk):
    """折り返しの単位に分ける。英数字・カタカナの連なりは1単位、それ以外の日本語は1文字ずつ。"""
    if not cjk:
        return [t for t in re.split(r"(\s+)", text) if t]
    return re.findall(r"[A-Za-z0-9%&'.\-]+|[ァ-ヶー]+|\s+|.", text)


def wrap(draw, text, font, max_width, cjk):
    tokens = []
    for tok in tokenize(text, cjk):
        # 1単位だけで1行に収まらない語(長いカタカナ語など)は1文字ずつに分ける
        if cjk and len(tok) > 1 and draw.textlength(tok, font=font) > max_width:
            tokens.extend(tok)
        else:
            tokens.append(tok)
    lines, cur = [], ""
    for tok in tokens:
        if not cur and tok.isspace():
            continue
        test = cur + tok
        if draw.textlength(test.rstrip(), font=font) <= max_width or not cur.strip():
            cur = test
            continue
        # 収まらないので改行する。禁則を簡易的に処理する。
        nxt = tok
        if cjk:
            if tok[0] in NO_LINE_START and len(cur) > 1:
                nxt = cur[-1] + tok          # 前の1文字を次の行へ送る
                cur = cur[:-1]
            elif cur and cur[-1] in NO_LINE_END and len(cur) > 1:
                nxt = cur[-1] + tok
                cur = cur[:-1]
        lines.append(cur.rstrip())
        cur = nxt.lstrip()
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def _fit(draw, segments, max_width, max_height, avoid_orphan):
    """segments(それぞれ新しい行から始める)が収まる最大のフォントを探す。無ければ None。"""
    for size in STYLE["title_sizes"]:
        font = load_font(STYLE["title_font"], size, STYLE["title_variation"])
        line_h = int(size * STYLE["line_spacing"])
        lines, orphan = [], False
        for seg in segments:
            seg_lines = wrap(draw, seg, font, max_width, STYLE["cjk"])
            # 最終行が1〜2文字だけになる「泣き別れ」
            if len(seg_lines) > 1 and len(seg_lines[-1].replace(" ", "")) <= STYLE.get("orphan_len", 2):
                orphan = True
            lines.extend(seg_lines)
        too_wide = any(draw.textlength(l, font=font) > max_width for l in lines)
        if (len(lines) <= STYLE["max_lines"] and line_h * len(lines) <= max_height
                and not too_wide and not (avoid_orphan and orphan)):
            return font, lines, line_h
    return None


def layout_title(draw, title, max_width, max_height):
    """タイトルが枠に収まる最大のフォントサイズと改行位置を決める。

    - 泣き別れ(最終行が1〜2文字)の無い配置を優先する。
    - 区切り記号「｜」「|」があれば、そこで改行した配置も試し、文字の大きさが
      あまり変わらない(8px以内)ならそちらを採用する(区切り記号自体は改行に置き換わる)。
    """
    parts = [p.strip() for p in re.split(r"\s*[｜|]\s*", title) if p.strip()]
    for avoid_orphan in (True, False):
        whole = _fit(draw, [title], max_width, max_height, avoid_orphan)
        split = _fit(draw, parts, max_width, max_height, avoid_orphan) if len(parts) > 1 else None
        if split and (not whole or split[0].size >= whole[0].size - 8):
            return split
        if whole:
            return whole
    # 最小サイズでも収まらない場合: 最小サイズで行数を打ち切り、末尾を「…」にする
    size = list(STYLE["title_sizes"])[-1]
    font = load_font(STYLE["title_font"], size, STYLE["title_variation"])
    line_h = int(size * STYLE["line_spacing"])
    lines = wrap(draw, title, font, max_width, STYLE["cjk"])[:STYLE["max_lines"]]
    last = lines[-1]
    while last and draw.textlength(last + "…", font=font) > max_width:
        last = last[:-1]
    lines[-1] = last.rstrip() + "…"
    return font, lines, line_h


def render(title, site_name, out_path):
    from PIL import Image, ImageDraw

    bg = hex_to_rgb(STYLE["bg"])
    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)

    # カード(白地・角丸・枠線)と左端のアクセント帯
    card = (MARGIN, MARGIN, WIDTH - MARGIN, HEIGHT - MARGIN)
    draw.rounded_rectangle(card, radius=28, fill=hex_to_rgb(STYLE["accent"]))
    draw.rounded_rectangle((card[0] + ACCENT_BAR_W, card[1], card[2], card[3]), radius=24,
                           fill=hex_to_rgb(STYLE["card"]), outline=hex_to_rgb(STYLE["border"]), width=2)

    # 下部の帯(サイト名)
    footer_top = card[3] - FOOTER_H
    draw.line((card[0] + CARD_PAD_X, footer_top, card[2] - CARD_PAD_X, footer_top),
              fill=hex_to_rgb(STYLE["accent_soft"]), width=3)
    name_font = load_font(STYLE["name_font"], 34, STYLE["name_variation"])
    name_y = footer_top + (FOOTER_H - 34) // 2 - 6
    dot_r = 9
    dot_cx = card[0] + CARD_PAD_X + dot_r
    dot_cy = name_y + 34 // 2 + 6
    draw.ellipse((dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
                 fill=hex_to_rgb(STYLE["accent"]))
    draw.text((dot_cx + dot_r + 18, name_y), site_name, font=name_font,
              fill=hex_to_rgb(STYLE["accent"]))

    # タイトル(枠の中で上下中央)
    left = card[0] + CARD_PAD_X
    max_width = (card[2] - CARD_PAD_X) - left
    area_top = card[1] + CARD_PAD_TOP
    area_bottom = footer_top - 36
    font, lines, line_h = layout_title(draw, title, max_width, area_bottom - area_top)
    block_h = line_h * len(lines)
    y = area_top + max(0, (area_bottom - area_top - block_h) // 2)
    for line in lines:
        # 行の高さの中央に文字が来るよう、上側の余白を均等にする
        draw.text((left, y + (line_h - font.size) // 2 - int(font.size * 0.12)), line,
                  font=font, fill=hex_to_rgb(STYLE["text"]))
        y += line_h

    img.save(out_path, "PNG", optimize=True)
    return lines, font.size


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[og] Pillow が無いため OG 画像の生成をスキップします(サイトは画像なしでビルドされます)")
        return 0
    for key in ("title_font", "name_font"):
        if not os.path.exists(STYLE[key]):
            print("[og] フォントが見つからないためスキップします: %s" % STYLE[key])
            return 0

    with open(SITE_JSON, encoding="utf-8") as f:
        site_name = json.load(f)["name"]

    os.makedirs(args.out, exist_ok=True)
    slugs = []
    ok = failed = 0
    for name in sorted(os.listdir(POSTS_DIR)):
        if not name.endswith(".md"):
            continue
        slug = name[:-3]
        slugs.append(slug)
        try:
            title = read_title(os.path.join(POSTS_DIR, name))
            if not title:
                print("[og] タイトルが読めないためスキップ: %s" % name)
                failed += 1
                continue
            render(title, site_name, os.path.join(args.out, slug + ".png"))
            ok += 1
        except Exception as e:  # 1件の失敗で全体を止めない
            print("[og] 生成に失敗: %s (%s)" % (name, e))
            failed += 1

    # 記事が削除・改名された場合の古い画像を消す
    for name in os.listdir(args.out):
        if name.endswith(".png") and name[:-4] not in slugs:
            os.remove(os.path.join(args.out, name))

    print("[og] 生成 %d 件 / 失敗 %d 件 -> %s" % (ok, failed, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
