const { DateTime } = require("luxon");
const { isPublished, isSlugPublished } = require("./lib/publishing");
const { addRakutenButtons } = require("./lib/rakuten");
const { resolveCategory, pickRelated } = require("./lib/categories");

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

  // テーマ(カテゴリ)別のまとめページ用。/category/<slug>/ を1テーマ1ページで作る。
  // 材料は公開判定済みの記事だけ(未公開記事は一覧にもリンクにも出さない)。
  // 公開済みの記事が1本も無いテーマは、ページを作らない。
  eleventyConfig.addCollection("categoryHubs", function (collectionApi) {
    const now = new Date();
    // 編集中に categories.json を書き換えても反映されるよう、毎回読み直す
    delete require.cache[require.resolve("./src/_data/categories.json")];
    const categoriesData = require("./src/_data/categories.json");
    const posts = collectionApi
      .getFilteredByGlob("src/posts/*.md")
      .filter((item) => isPublished(item.data, now))
      .sort((a, b) => b.date - a.date);
    const unassigned = posts.filter(
      (item) => !resolveCategory(categoriesData, item.fileSlug, item.data.category)
    );
    if (unassigned.length) {
      console.warn(
        "[categories] テーマ未登録の公開記事があります(src/_data/categories.json の posts に追加してください): " +
          unassigned.map((i) => i.fileSlug).join(", ")
      );
    }
    return categoriesData.categories
      .map((c) => ({
        ...c,
        posts: posts.filter(
          (item) =>
            (resolveCategory(categoriesData, item.fileSlug, item.data.category) || {}).slug === c.slug
        ),
      }))
      .filter((c) => c.posts.length > 0);
  });

  // 関連記事: 同じテーマの公開済み記事を最大6本。同テーマが4本未満なら新しい記事で4本まで補う。
  eleventyConfig.addFilter("relatedPosts", (posts, currentUrl, categorySlug) =>
    pickRelated(posts, currentUrl, categorySlug, 6, 4)
  );

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
