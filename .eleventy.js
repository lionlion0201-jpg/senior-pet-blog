const { DateTime } = require("luxon");

module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/assets");
  eleventyConfig.addPassthroughCopy("src/robots.txt");
  eleventyConfig.addGlobalData("currentYear", () => new Date().getFullYear());

  eleventyConfig.addCollection("posts", function (collectionApi) {
    const now = new Date();
    return collectionApi
      .getFilteredByGlob("src/posts/*.md")
      .filter((item) => item.data.published !== false)
      // 予約公開: publishAtが設定されていて、まだ到来していない場合のみ非表示にする。
      // publishAtが無い記事(既存記事など)は従来通り常に表示する。
      .filter((item) => !item.data.publishAt || new Date(item.data.publishAt) <= now)
      .sort((a, b) => b.date - a.date);
  });

  eleventyConfig.addFilter("readableDate", (dateObj) => {
    return DateTime.fromJSDate(dateObj, { zone: "utc" }).setLocale("ja").toFormat("yyyy年LL月dd日");
  });

  eleventyConfig.addFilter("isoDate", (dateObj) => {
    return DateTime.fromJSDate(dateObj, { zone: "utc" }).toFormat("yyyy-LL-dd");
  });

  return {
    pathPrefix: "/senior-pet-blog/",
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
    },
  };
};
