const { DateTime } = require("luxon");
const { isPublished, isSlugPublished } = require("./lib/publishing");
const { addRakutenButtons } = require("./lib/rakuten");

module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/assets");
  eleventyConfig.addGlobalData("currentYear", () => new Date().getFullYear());

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

  // "YYYY-MM-DD" の文字列を「2026年9月22日」にする(記事ページの公開日・更新日用)
  eleventyConfig.addFilter("jpDateStr", (s) => {
    const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[1]}年${Number(m[2])}月${Number(m[3])}日` : "";
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
