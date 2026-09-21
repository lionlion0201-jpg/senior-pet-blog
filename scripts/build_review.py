#!/usr/bin/env python3
"""
週末レビュー用のHTMLを生成する。

使い方:
  python3 scripts/build_review.py
  → docs/review/review.html が生成されるので、ブラウザで開く

画面上で承認/見送り・公開日・SNS投稿の型を選び、「決定を書き出す」を押すと
decisions.json がダウンロードされる。それを docs/review/ に置いて
  python3 scripts/apply_review.py
を実行すると、フロントマターの書き換えとSNSキューへの登録が行われる。

画面の作り
----------
左に記事本文、右に判断パネル(機械チェック・承認/見送り・公開日・SNS)を置く。
記事は生のMarkdownではなく、実際のサイトに近い見た目に整形して出す。
レビューで一番時間を使うのは本文を読むことなので、そこを読みやすくしないと
道具として意味がない。

なぜオフラインHTMLなのか
------------------------
Pinterestの背景写真レビュー(photo_review.html)が同じ方式で実運用に耐えたため
踏襲した。サーバーを立てる必要がなく、ファイルを開くだけで使える。
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from review_lib import (  # noqa: E402
    ROOT, load_config, load_posts, check_article, next_free_slots,
    parse_sns_drafts, internal_links,
)
from render_md import md_to_html, outline  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "review")
OUT_PATH = os.path.join(OUT_DIR, "review.html")


def latest_cycle_log():
    d = os.path.join(ROOT, "docs", "cycles")
    if not os.path.isdir(d):
        return None
    logs = sorted(f for f in os.listdir(d)
                  if f.endswith(".md") and f[0].isdigit())
    return os.path.join(d, logs[-1]) if logs else None


def match_drafts_to_posts(drafts, drafts_posts):
    """サイクルログの「### 記事N: 見出し」と実ファイルを対応づける。

    見出しは内容の要約なのでスラッグとは一致しない。見出しの語がタイトルに
    含まれていればそれを優先し、なければ生成順に割り当てる。
    """
    result = {}
    used = set()
    for i, block in enumerate(drafts):
        head = block["heading"]
        key = head.split(":", 1)[-1].strip() if ":" in head else head
        hit = None
        for p in drafts_posts:
            if p["slug"] in used:
                continue
            title = p["front_matter"].get("title", "")
            if key and (key in title or any(w in title for w in key.split() if len(w) > 2)):
                hit = p
                break
        if hit is None and i < len(drafts_posts):
            for p in drafts_posts:
                if p["slug"] not in used:
                    hit = p
                    break
        if hit:
            used.add(hit["slug"])
            result[hit["slug"]] = block["drafts"]
    return result


def build():
    config = load_config()
    posts = load_posts()
    drafts_posts = [p for p in posts.values() if p["is_draft"]]
    drafts_posts.sort(key=lambda p: p["slug"])

    if not drafts_posts:
        print("下書きの記事がありません(published: false の記事が0本)。")
        return

    slots = next_free_slots(posts, len(drafts_posts))
    sns = match_drafts_to_posts(parse_sns_drafts(latest_cycle_log()), drafts_posts)

    items = []
    for i, p in enumerate(drafts_posts):
        planned = slots[i]
        issues = check_article(p, posts, config, planned_date=planned)
        items.append({
            "slug": p["slug"],
            "title": p["front_matter"].get("title", ""),
            "description": p["front_matter"].get("description", ""),
            "body_html": md_to_html(p["body"], posts),
            "outline": outline(p["body"]),
            "chars": len(p["body"]),
            "cta_count": p["body"].count('class="cta-box"'),
            "links": internal_links(p["body"]),
            "suggested_date": planned,
            "issues": [{"severity": s, "message": m} for s, m in issues],
            "sns": sns.get(p["slug"], {}),
        })

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {
        "site": config["site_label"],
        "generated_at": date.today().isoformat(),
        "publish_hour": config["publish_hour"],
        "tz": config["timezone_offset"],
        "items": items,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(render(payload))

    n_err = sum(1 for it in items for x in it["issues"] if x["severity"] == "error")
    n_warn = sum(1 for it in items for x in it["issues"] if x["severity"] == "warn")
    print(f"{OUT_PATH} を生成しました。")
    print(f"  対象: {len(items)}本 / 要修正(error) {n_err}件 / 要確認(warn) {n_warn}件")
    print(f"  公開日の候補: {slots[0]} 〜 {slots[-1]}")


def render(payload):
    # 記事本文にはCTAボックスの生HTMLが含まれる。"</script>" という並びが
    # 入ると、その時点で <script> が閉じて画面が壊れる。
    # JSONのエスケープでは "/" は処理されないので、ここで潰しておく。
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data)


TEMPLATE = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>週末レビュー</title>
<style>
:root{--err:#c0392b;--warn:#b7791f;--ok:#2f855a;--line:#e2e8f0;--muted:#718096;
      --ink:#1a202c;--accent:#2b6cb0}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;
  color:var(--ink);background:#eef2f7;line-height:1.8;font-size:15px}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);
  padding:10px 20px;display:flex;align-items:center;gap:14px;z-index:20;flex-wrap:wrap}
h1{font-size:15px;margin:0}
.counts{font-size:13px;color:var(--muted)}
.hint{font-size:12px;color:var(--muted)}
button{font:inherit;padding:7px 14px;border-radius:6px;border:1px solid var(--line);
  background:#fff;cursor:pointer}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button.mini{padding:3px 9px;font-size:12px}
main{max-width:1280px;margin:0 auto;padding:20px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;margin-bottom:22px;
  overflow:hidden}
.card.approved{box-shadow:0 0 0 2px var(--ok)}
.card.skipped{opacity:.5}
.card.current{box-shadow:0 0 0 3px #90cdf4}
.card-head{padding:14px 18px;background:#fafcff;border-bottom:1px solid var(--line)}
.card-head h2{font-size:17px;margin:0 0 6px;line-height:1.5}
.meta{font:12px ui-monospace,monospace;color:var(--muted)}
.desc{font-size:13px;color:#4a5568;margin-top:6px}
.chips{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:12px;background:#edf2f7;color:#4a5568;padding:2px 9px;border-radius:12px}
.body{display:grid;grid-template-columns:minmax(0,1fr) 330px}
@media(max-width:980px){.body{grid-template-columns:1fr}}
.doc{padding:18px 24px;max-height:70vh;overflow:auto;border-right:1px solid var(--line)}
.doc.full{max-height:none}
.doc p{margin:0 0 1em}
.doc h3{font-size:16px;margin:1.6em 0 .6em;padding-left:10px;
  border-left:4px solid var(--accent)}
.doc h4{font-size:14px;margin:1.3em 0 .5em}
.doc ul{margin:0 0 1em;padding-left:1.3em}
.doc li{margin-bottom:.3em}
.doc table{border-collapse:collapse;width:100%;margin:1em 0;font-size:13px}
.doc th,.doc td{border:1px solid var(--line);padding:7px 10px;text-align:left;
  vertical-align:top}
.doc th{background:#f7fafc}
.doc hr{border:none;border-top:1px solid var(--line);margin:1.5em 0}
.doc code{background:#edf2f7;padding:1px 5px;border-radius:3px;font-size:13px}
.cta-box{border:1px solid #cbd5e0;background:#fffdf6;border-left:4px solid #dd8b3a;
  padding:12px 14px;margin:1.2em 0;border-radius:4px;font-size:14px}
.cta-box .button{display:inline-block;margin-top:8px;color:var(--accent);
  text-decoration:none;font-weight:600}
.cta-box .button:hover{text-decoration:underline}
.ilink{background:#ebf8ff;border-bottom:1px dashed #63b3ed;padding:0 2px}
.lk-ok{font-size:11px;color:var(--ok);margin-left:5px;white-space:nowrap}
.lk-bad{font-size:11px;color:var(--err);margin-left:5px;font-weight:600;white-space:nowrap}
.panel{padding:16px;background:#fafcff}
.panel-sticky{position:sticky;top:58px}
.label{font-size:11px;font-weight:700;color:var(--muted);margin:16px 0 7px;
  letter-spacing:.04em}
.label:first-child{margin-top:0}
.issue{font-size:12.5px;padding:7px 10px;border-radius:4px;margin-bottom:6px;line-height:1.6}
.issue.error{background:#fff5f5;color:var(--err);border-left:3px solid var(--err)}
.issue.warn{background:#fffaf0;color:var(--warn);border-left:3px solid var(--warn)}
.clean{font-size:13px;color:var(--ok)}
.seg{display:flex;gap:6px}
.seg button{flex:1}
.seg button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.seg button.on.skip{background:#718096;border-color:#718096}
input[type=date]{font:inherit;padding:6px 10px;border:1px solid var(--line);
  border-radius:4px;width:100%}
.sns label{display:block;font-size:12.5px;padding:8px 10px;border:1px solid var(--line);
  border-radius:6px;margin-bottom:6px;cursor:pointer;line-height:1.6;background:#fff}
.sns label:hover{border-color:#90cdf4}
.sns input{margin-right:7px}
.type{display:inline-block;font:10px ui-monospace,monospace;background:#edf2f7;
  padding:1px 6px;border-radius:3px;margin-right:6px;color:#4a5568;vertical-align:1px}
.human{font-size:12px;color:var(--muted);background:#fff;border:1px dashed var(--line);
  border-radius:6px;padding:10px 12px;margin-top:14px;line-height:1.7}
</style></head><body>
<header>
  <h1>週末レビュー</h1>
  <span class="counts" id="counts"></span>
  <span class="hint">j/k 移動 · a 承認 · s 見送り · f 本文を全部表示</span>
  <button class="primary" id="export" style="margin-left:auto">決定を書き出す</button>
</header>
<main id="list"></main>
<script>
const DATA = __DATA__;
const state = {};
DATA.items.forEach(it => state[it.slug] = {
  decision: it.issues.some(x=>x.severity==='error') ? null : 'approve',
  date: it.suggested_date,
  sns: Object.keys(it.sns)[0] || null,
  full: false
});
let cur = 0;

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

function render(){
  document.getElementById('list').innerHTML = DATA.items.map((it,i) => {
    const st = state[it.slug];
    const cls = ['card',
      st.decision==='approve'?'approved':(st.decision==='skip'?'skipped':''),
      i===cur?'current':''].join(' ');
    const snsKeys = Object.keys(it.sns);
    return `<div class="${cls}" id="card-${i}">
      <div class="card-head">
        <h2>${esc(it.title)}</h2>
        <div class="meta">${esc(it.slug)} · ${it.chars}文字 · CTA ${it.cta_count}箇所</div>
        <div class="desc">${esc(it.description)}</div>
        <div class="chips">${it.outline.map(h=>`<span class="chip">${esc(h)}</span>`).join('')}</div>
      </div>
      <div class="body">
        <div class="doc ${st.full?'full':''}" id="doc-${i}">
          ${it.body_html}
          <div style="margin-top:14px">
            <button class="mini" onclick="toggleFull('${it.slug}')">
              ${st.full?'高さを戻す':'全文を展開'}</button>
          </div>
        </div>
        <div class="panel"><div class="panel-sticky">
          <div class="label">自動チェック</div>
          ${it.issues.length===0 ? '<div class="clean">問題なし</div>' :
            it.issues.map(x=>`<div class="issue ${x.severity}">${esc(x.message)}</div>`).join('')}

          <div class="label">判断</div>
          <div class="seg">
            <button class="${st.decision==='approve'?'on':''}"
              onclick="setDecision('${it.slug}','approve')">承認</button>
            <button class="${st.decision==='skip'?'on skip':''}"
              onclick="setDecision('${it.slug}','skip')">見送り</button>
          </div>

          <div class="label">公開日</div>
          <input type="date" value="${st.date}" onchange="setDate('${it.slug}',this.value)">

          <div class="label">SNS投稿</div>
          <div class="sns">
          ${snsKeys.length===0 ? '<div class="clean" style="color:var(--muted)">サイクルログに投稿案が見つかりませんでした</div>' :
            snsKeys.map(type=>`
            <label><input type="radio" name="s-${i}" ${st.sns===type?'checked':''}
              onchange="setSns('${it.slug}','${type}')">
              <span class="type">${type}</span>${esc(it.sns[type])}</label>`).join('') +
            `<label><input type="radio" name="s-${i}" ${st.sns===null?'checked':''}
              onchange="setSns('${it.slug}',null)">投稿しない</label>`}
          </div>

          <div class="human">機械が見ていないのは、商品が実在するか・数字が正しいか・
          結論が根拠から導けているか・文章として読めるか。<b>ここに時間を使う。</b></div>
        </div></div>
      </div>
    </div>`;
  }).join('');
  const ap = Object.values(state).filter(s=>s.decision==='approve').length;
  const sk = Object.values(state).filter(s=>s.decision==='skip').length;
  document.getElementById('counts').textContent =
    `${DATA.items.length}本中 承認${ap} / 見送り${sk} / 未判断${DATA.items.length-ap-sk}`;
}
function setDecision(slug,v){state[slug].decision=v;render()}
function setDate(slug,v){state[slug].date=v}
function setSns(slug,v){state[slug].sns=v}
function toggleFull(slug){state[slug].full=!state[slug].full;render()}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  const n = DATA.items.length;
  const go = () => {render(); document.getElementById('card-'+cur).scrollIntoView({block:'start'})};
  if (e.key==='j'){cur=Math.min(cur+1,n-1);go()}
  if (e.key==='k'){cur=Math.max(cur-1,0);go()}
  if (e.key==='a'){setDecision(DATA.items[cur].slug,'approve')}
  if (e.key==='s'){setDecision(DATA.items[cur].slug,'skip')}
  if (e.key==='f'){toggleFull(DATA.items[cur].slug)}
});

document.getElementById('export').onclick = () => {
  const out = {
    site: DATA.site,
    decided_at: new Date().toISOString(),
    publish_hour: DATA.publish_hour,
    tz: DATA.tz,
    decisions: DATA.items.map(it => ({
      slug: it.slug,
      decision: state[it.slug].decision,
      publish_date: state[it.slug].date,
      sns_type: state[it.slug].sns,
      sns_text: state[it.slug].sns ? it.sns[state[it.slug].sns] : null
    }))
  };
  const blob = new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'decisions.json';
  a.click();
};
render();
</script></body></html>
"""


if __name__ == "__main__":
    build()
