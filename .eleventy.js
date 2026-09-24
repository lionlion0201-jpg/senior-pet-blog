const { DateTime } = require("luxon");
const { isPublished } = require("./lib/publishing");

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
