/**
 * 記事のテーマ(カテゴリ)を決める、唯一の実装。
 *
 * テーマの定義と「記事スラッグ → テーマ」の対応は src/_data/categories.json に置く。
 * 記事ファイル(src/posts/*.md)を書き換えずにテーマ分けを変えられるようにするため。
 *
 * 決め方(上から順に):
 *   1. categories.json の posts に記事のスラッグが登録されていれば、そのテーマ
 *   2. 記事のフロントマターに category があり、テーマの slug・表示名・aliases(旧カテゴリ名)の
 *      どれかと一致すれば、そのテーマ(大文字小文字は区別しない)
 *   3. どちらも無ければ「テーマなし」(null)。どのまとめページにも出ず、
 *      パンくずは「ホーム > 記事」、関連記事は新しい順の記事で補う。ビルドは止めない。
 *      公開済みでテーマなしの記事があると、ビルド時に警告を出す(.eleventy.js)。
 *
 * 関連記事・まとめページは、公開判定(lib/publishing.js)を通った collections.posts
 * だけを材料にすること。未公開記事へのリンクは 404 になる。
 */
function resolveCategory(categoriesData, fileSlug, frontCategory) {
  if (!categoriesData) return null;
  const list = categoriesData.categories || [];
  const map = categoriesData.posts || {};
  let slug = map[fileSlug];
  if (!slug && frontCategory) {
    const key = String(frontCategory).trim().toLowerCase();
    const hit = list.find((c) =>
      [c.slug, c.name, ...(c.aliases || [])].some(
        (v) => String(v).toLowerCase() === key
      )
    );
    if (hit) slug = hit.slug;
  }
  if (!slug) return null;
  return list.find((c) => c.slug === slug) || null;
}

/**
 * 関連記事を選ぶ。
 *   - 同じテーマの公開済み記事を、新しい順に最大 max 本
 *   - 同じテーマが min 本に満たなければ、他テーマの新しい記事で min 本まで補う
 * posts には公開判定済みの collections.posts を渡すこと。
 */
function pickRelated(posts, currentUrl, categorySlug, max = 6, min = 4) {
  const others = (posts || []).filter((p) => p.url !== currentUrl);
  const same = categorySlug
    ? others.filter((p) => p.data.categorySlug === categorySlug).slice(0, max)
    : [];
  if (same.length >= min) return same;
  const fill = others
    .filter((p) => !same.includes(p))
    .slice(0, min - same.length);
  return same.concat(fill);
}

module.exports = { resolveCategory, pickRelated };
