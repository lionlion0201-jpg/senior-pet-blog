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

module.exports = { isPublished };
