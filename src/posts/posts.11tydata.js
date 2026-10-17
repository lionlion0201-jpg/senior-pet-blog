const {
  isPublished,
  publishedDateString,
  modifiedDateString,
  shownUpdatedString,
} = require("../../lib/publishing");

// 未公開の記事はページ自体を出力しない(permalink: false)。
// 一覧から外すだけだと、URLを直接開けば読めてしまうため。
module.exports = {
  eleventyComputed: {
    permalink: (data) =>
      isPublished(data) ? `posts/${data.page.fileSlug}/index.html` : false,
    // 記事ページの日付表示と JSON-LD 用("YYYY-MM-DD")。
    // 予約公開の記事は publishAt の日付が公開日。`updated:` があれば更新日。
    publishedDateStr: (data) => publishedDateString(data),
    modifiedDateStr: (data) => modifiedDateString(data),
    updatedShownStr: (data) => shownUpdatedString(data),
  },
};
