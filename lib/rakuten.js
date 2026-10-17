/**
 * Amazon の検索ボタンの隣に、同じ検索語の楽天市場ボタンを自動で足す(2026-10-17 追加)。
 *
 * 背景:
 * 記事のアフィリエイトリンクは Amazon の検索結果ページへのボタン(217本)だけで、
 * 楽天で買う人を取りこぼしていた。73本の記事を1本ずつ書き換えるのではなく、
 * ビルド時に HTML を変換して、全記事・今後の記事にまとめて楽天ボタンを付ける。
 * 記事の Markdown には何も書かなくてよい。
 *
 * リンクはもしもアフィリエイトの「どこでもリンク」(楽天市場: p_id=54)。
 * a_id はもしもの会員ID(サイトに公開される値で、秘密情報ではない)。
 *
 * 対象: class="button" の Amazon 検索リンク(https://www.amazon.co.jp/s?k=...)のみ。
 * ENABLED_SLUGS に記事スラッグを並べると、その記事だけで有効になる(試験導入用)。
 * null にすると全記事で有効。
 */
const MOSHIMO_RAKUTEN = "https://af.moshimo.com/af/c/click?a_id=5717340&p_id=54&pc_id=54&pl_id=616&url=";

const ENABLED_SLUGS = [
  "rougan-rouneko-ninchisho-taisaku",
  "rougan-rouneko-ochitsukanai-anshin-care",
  "senior-pet-sale-kaimono-handan",
];

const AMAZON_BUTTON = /<a class="button" href="https:\/\/www\.amazon\.co\.jp\/s\?k=([^"&]+)[^"]*"[^>]*>[\s\S]*?<\/a>/g;

function rakutenUrl(amazonKeyword) {
  let kw;
  try {
    kw = decodeURIComponent(amazonKeyword.replace(/\+/g, " "));
  } catch (e) {
    kw = amazonKeyword.replace(/\+/g, " ");
  }
  const words = kw.trim().split(/\s+/).map(encodeURIComponent).join("+");
  const search = `https://search.rakuten.co.jp/search/mall/${words}/`;
  return MOSHIMO_RAKUTEN + encodeURIComponent(search);
}

function isEnabled(outputPath) {
  if (!outputPath || !outputPath.endsWith(".html")) return false;
  const m = outputPath.match(/posts[\\/]([^\\/]+)[\\/]index\.html$/);
  if (!m) return false;
  return ENABLED_SLUGS === null || ENABLED_SLUGS.includes(m[1]);
}

function addRakutenButtons(content, outputPath) {
  if (!isEnabled(outputPath)) return content;
  return content.replace(AMAZON_BUTTON, (amazonLink, keyword) =>
    `${amazonLink} <a class="button button-rakuten" href="${rakutenUrl(keyword)}" rel="nofollow sponsored">楽天市場で探す →</a>`
  );
}

module.exports = { addRakutenButtons, rakutenUrl };
