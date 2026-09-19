const { isPublished } = require("../../lib/publishing");

// 未公開の記事はページ自体を出力しない(permalink: false)。
// 一覧から外すだけだと、URLを直接開けば読めてしまうため。
module.exports = {
  eleventyComputed: {
    permalink: (data) =>
      isPublished(data) ? `posts/${data.page.fileSlug}/index.html` : false,
  },
};
