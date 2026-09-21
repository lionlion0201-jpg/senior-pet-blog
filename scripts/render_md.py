#!/usr/bin/env python3
"""
記事Markdownを、レビュー画面で読むためのHTMLに変換する。

汎用のMarkdownライブラリは使わない。理由は2つ:

1. 依存を増やしたくない(GitHub Actions側でも動かせる状態を保ちたい)
2. この運用の記事が使う記法は限られている。見出し・段落・箇条書き・表・強調・
   リンク、そしてCTAボックスの生HTML。それだけ扱えればよい

特有の事情として、内部リンクは `[文言]({{ '/posts/slug/' | url }})` という
Eleventyのテンプレート記法で書かれている。これをそのまま出すと読めないので、
リンク先のスラッグと公開日を添えて表示する。
"""
import html
import re


def _inline(text, posts=None):
    """段落内の記法を処理する。入力は生テキスト(未エスケープ)。"""
    out = html.escape(text)

    def internal(m):
        label, slug = m.group(1), m.group(2)
        if posts is None:
            meta = ""
        elif slug not in posts:
            meta = '<span class="lk-bad">存在しない</span>'
        else:
            d = posts[slug]["publish_date"]
            if d is None:
                meta = '<span class="lk-bad">まだ下書き</span>'
            elif d == "0000-00-00":
                meta = '<span class="lk-ok">公開済</span>'
            else:
                meta = f'<span class="lk-ok">{d} 公開</span>'
        return f'<span class="ilink">{label}{meta}</span>'

    # 内部リンク: [文言]({{ '/posts/slug/' | url }})
    # html.escape 後は ' が &#x27; になっているので、引用符には依存せず
    # /posts/<slug>/ の部分だけを手掛かりにする。
    out = re.sub(r"\[([^\]]+)\]\(\{\{[^)]*?/posts/([a-z0-9-]+)/[^)]*?\}\}\)",
                 internal, out)

    # 外部リンク
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                 lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>',
                 out)

    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out


def md_to_html(body, posts=None):
    lines = body.split("\n")
    out = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 生HTMLのブロック(CTAボックスなど)はそのまま通す。
        # <div> の開閉を数えて、閉じるまでを1ブロックとして扱う。
        if stripped.startswith("<"):
            block = []
            depth = 0
            while i < n:
                cur = lines[i]
                depth += cur.count("<div") - cur.count("</div>")
                block.append(cur)
                i += 1
                if depth <= 0:
                    break
            out.append("\n".join(block))
            continue

        # 表
        if stripped.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            # 2行目が区切り(---)なら1行目がヘッダ
            has_head = len(cells) > 1 and all(set(c) <= set("-: ") for c in cells[1])
            out.append("<table>")
            if has_head:
                out.append("<thead><tr>" + "".join(
                    f"<th>{_inline(c, posts)}</th>" for c in cells[0]) + "</tr></thead>")
                body_rows = cells[2:]
            else:
                body_rows = cells
            out.append("<tbody>")
            for r in body_rows:
                out.append("<tr>" + "".join(
                    f"<td>{_inline(c, posts)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue

        # 箇条書き
        if re.match(r"^\s*[-*]\s+", line):
            out.append("<ul>")
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                item = re.sub(r"^\s*[-*]\s+", "", lines[i])
                out.append(f"<li>{_inline(item, posts)}</li>")
                i += 1
            out.append("</ul>")
            continue

        # 見出し
        m = re.match(r"^(#{2,4})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            tag = {2: "h3", 3: "h4", 4: "h5"}[level]
            out.append(f'<{tag} class="md-h{level}">{_inline(m.group(2), posts)}</{tag}>')
            i += 1
            continue

        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        # 段落(空行まで)
        para = []
        while i < n and lines[i].strip() and not lines[i].strip().startswith(("#", "|", "<")) \
                and not re.match(r"^\s*[-*]\s+", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{_inline(' '.join(para), posts)}</p>")

    return "\n".join(out)


def outline(body):
    """見出しの一覧。記事の骨格をひと目で見るため。"""
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.*)$", body, re.M)]
