/**
 * 期間限定セール(Amazonプライム感謝祭・プライムデー・ブラックフライデーなど)の
 * 告知ブロックを、期間が終わったら自動で消すための仕組み。
 *
 * なぜ必要か(規約上の要請):
 * Amazonアソシエイト・プログラム運営規約は
 * 「期間限定のプロモーションへのリンクおよび関連する記述は、
 *   そのプロモーションが終了したらただちにサイトから削除すること」
 * を求めている(Amazon Associates Program Operating Agreement / Policies,
 *  "You must remove from your Site any links and related references to
 *   limited time promotions as soon as that promotion ... ends.")。
 *
 * 手で消す運用にすると必ず消し忘れる。記事側には
 *
 *   {% if campaign.phase %} ...告知... {% endif %}
 *
 * と書いておき、期間の判定はここ1か所だけで行う。
 * deploy.yml が毎日09:00 JSTに再ビルドするので、終了翌朝には自動で消える。
 *
 * 記事本文そのものは「セールのとき何を買うか」という通年で読める内容にしておき、
 * 日付や開催名に依存する部分だけをこのブロックに閉じ込めること。
 * そうすれば終了後も記事は404にならず、資産として残る。
 */

const CAMPAIGNS = [
  {
    id: "prime-thanks-2026",
    name: "Amazonプライム感謝祭",
    // 2026-09-29時点でAmazonが告知している日程
    earlyStart: "2026-10-13T00:00:00+09:00", // 先行セール
    start: "2026-10-16T00:00:00+09:00", // 本セール
    end: "2026-10-19T23:59:59+09:00",
    // 告知を出し始める日。これより前は何も表示しない
    teaseFrom: "2026-10-01T00:00:00+09:00",
    window: "10月13日(先行セール)〜10月19日",
    // 日程の出典を明示するための「いつ時点の情報か」
    asOf: "2026年9月29日",
  },
];

module.exports = function () {
  const now = new Date();

  for (const c of CAMPAIGNS) {
    const tease = new Date(c.teaseFrom);
    const early = new Date(c.earlyStart);
    const end = new Date(c.end);

    if (now > end) continue; // 終了済み。何も出さない
    if (now < tease) continue; // まだ告知期間に入っていない

    return {
      ...c,
      // "upcoming" = 開催前 / "active" = 開催中
      phase: now >= early ? "active" : "upcoming",
    };
  }

  return { phase: null };
};
