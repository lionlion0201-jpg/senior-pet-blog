const { isPublished } = require("../../lib/publishing");
const { resolveCategory } = require("../../lib/categories");

// 未公開の記事はページ自体を出力しない(permalink: false)。
// 一覧から外すだけだと、URLを直接開けば読めてしまうため。
module.exports = {
  eleventyComputed: {
    permalink: (data) =>
      isPublished(data) ? `posts/${data.page.fileSlug}/index.html` : false,
    // テーマ(カテゴリ)。src/_data/categories.json で決める(lib/categories.js)。
    // テーマ未登録の記事は null になり、まとめページには出ない。
    categorySlug: (data) => {
      const c = resolveCategory(data.categories, data.page.fileSlug, data.category);
      return c ? c.slug : null;
    },
    categoryName: (data) => {
      const c = resolveCategory(data.categories, data.page.fileSlug, data.category);
      return c ? c.name : null;
    },
  },
};
