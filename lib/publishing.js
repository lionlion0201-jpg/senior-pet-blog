/**
 * 記事を公開してよいかを判定する、唯一の実装。
 *
 * 背景(2026-09-19):
 * 以前は .eleventy.js の collections.posts でのみ publishAt を見ていたため、
 * 予約公開待ちの記事が「一覧とサイトマップには出ないが、URLを直接開くと読める」
 * 状態で公開されてしまっていた(国内サイトで28本)。
 * 一覧への表示可否とページ生成可否が別々に書かれていたことが原因なので、
 * 判定をこのファイルに集約し、両方から必ずこれを呼ぶこと。
 *
 * - published: false    → 下書き。常に非公開。
 * - publishAt が未来     → 予約公開待ち。その時刻を過ぎたビルドから公開。
 */
function isPublished(data, now = new Date()) {
  if (data.published === false) return false;
  if (data.publishAt && new Date(data.publishAt) > now) return false;
  return true;
}

/**
 * src/posts/<slug>.md が、このビルドの時点で公開済みかを返す。
 *
 * 記事本文の {% whenPublished "slug" %}...{% endwhenPublished %} から使う。
 * 予約公開の記事へのリンクを先に書いておき、リンク先が公開された日の
 * 再ビルド(deploy.yml の毎朝09:00)から自動で表示させるため。
 * フロントマターは `key: value` の1行形式だけなので、簡易的に読む。
 */
function isSlugPublished(slug, now = new Date()) {
  const fs = require("fs");
  const path = require("path");
  const file = path.join(__dirname, "..", "src", "posts", `${slug}.md`);
  if (!fs.existsSync(file)) return false;
  const text = fs.readFileSync(file, "utf8");
  const m = text.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return false;
  const data = {};
  for (const line of m[1].split("\n")) {
    const kv = line.match(/^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$/);
    if (!kv) continue;
    let val = kv[2].trim().replace(/^"(.*)"$/, "$1");
    if (val === "false") val = false;
    data[kv[1]] = val;
  }
  return isPublished(data, now);
}

module.exports = { isPublished, isSlugPublished };
