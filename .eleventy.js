const { DateTime } = require("luxon");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { isPublished, isSlugPublished } = require("./lib/publishing");
const { addRakutenButtons } = require("./lib/rakuten");

module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/assets");
  eleventyConfig.addGlobalData("currentYear", () => new Date().getFullYear());

  // 記事ごとの OG 画像(scripts/generate_og_images.py が og-images/<slug>.png に生成)。
  // ・公開済みの記事の画像だけを /assets/og/ にコピーする。予約公開待ちの記事の
  //   画像(タイトル入り)が記事より先に公開されないようにするため。
  // ・画像が無い記事(生成に失敗した場合など)は ogImage が空を返し、テンプレートは
  //   og:image も画像タグも出さない。画像が無くてもビルドは止まらない。
  // ・URL の ?v= は画像の中身のハッシュ。タイトルを直したとき SNS 側の古い画像の
  //   キャッシュを避けるため。
  const ogImages = {};
  const ogDir = path.join(__dirname, "og-images");
  if (fs.existsSync(ogDir)) {
    for (const file of fs.readdirSync(ogDir)) {
      if (!file.endsWith(".png")) continue;
      const slug = file.slice(0, -4);
      if (!isSlugPublished(slug)) continue;
      const hash = crypto
        .createHash("md5")
        .update(fs.readFileSync(path.join(ogDir, file)))
        .digest("hex")
        .slice(0, 8);
      ogImages[slug] = `/assets/og/${file}?v=${hash}`;
      eleventyConfig.addPassthroughCopy({ [`og-images/${file}`]: `assets/og/${file}` });
    }
  }
  eleventyConfig.addFilter("ogImage", (slug) => ogImages[slug] || "");

  eleventyConfig.addCollection("posts", function (collectionApi) {
    const now = new Date();
    // 判定は lib/publishing.js に集約している。
    // src/posts/posts.11tydata.js のページ生成可否と必ず同じ結果になるようにするため、
    // ここに条件を直接書き足さないこと。
    return collectionApi
      .getFilteredByGlob("src/posts/*.md")
      .filter((item) => isPublished(item.data, now))
      .sort((a, b) => b.date - a.date);
  });

  // 予約公開の記事へのリンクを、リンク先が公開されたビルドから表示する。
  //   {% whenPublished "slug" %}...[記事]({{ '/posts/slug/' | url }})...{% endwhenPublished %}
  // リンク先が未公開の間は中身を丸ごと出さない(404のリンクを作らない)。
  eleventyConfig.addPairedShortcode("whenPublished", (content, slug) =>
    isSlugPublished(slug) ? content : ""
  );

  // Amazon の検索ボタンの隣に楽天市場ボタンを足す(lib/rakuten.js)
  eleventyConfig.addTransform("rakuten-buttons", function (content, outputPath) {
    return addRakutenButtons(content, (this.page && this.page.outputPath) || outputPath);
  });

  eleventyConfig.addFilter("readableDate", (dateObj) => {
    return DateTime.fromJSDate(dateObj, { zone: "utc" }).setLocale("ja").toFormat("yyyy年LL月dd日");
  });

  eleventyConfig.addFilter("isoDate", (dateObj) => {
    return DateTime.fromJSDate(dateObj, { zone: "utc" }).toFormat("yyyy-LL-dd");
  });

  return {
    pathPrefix: "/",
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
    },
  };
};
