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

なぜオフラインHTMLなのか
------------------------
Pinterestの背景写真レビュー(fetch_pin_photo_candidates.py が生成する
photo_review.html)が同じ方式で、実運用で使いやすかったため踏襲した。
サーバーを立てる必要がなく、ファイルをダブルクリックするだけで開ける。
"""
import html
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from review_lib import (  # noqa: E402
    ROOT, load_config, load_posts, check_article, next_free_slots,
    parse_sns_drafts, internal_links,
)

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

    見出しは日本語の要約なのでスラッグと直接は一致しない。
    順番が生成順と一致する前提で並び順マッチを基本にしつつ、
    見出しの語がタイトルに含まれていればそれを優先する。
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
            "body": p["body"],
            "chars": len(p["body"]),
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
    # 記事本文にはHTMLのCTAボックスが含まれる。仮に "</script>" という文字列が
    # 入ると、その時点で <script> タグが閉じてしまい画面が壊れる。
    # JSONのエスケープでは "/" は処理されないので、ここで潰しておく。
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<title>週末レビュー</title>
<style>
:root{--err:#c0392b;--warn:#b7791f;--ok:#2f855a;--line:#e2e8f0;--muted:#718096}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;
  color:#1a202c;background:#f7fafc;line-height:1.7}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);
  padding:12px 20px;display:flex;align-items:center;gap:16px;z-index:10}
h1{font-size:16px;margin:0}
.counts{font-size:13px;color:var(--muted)}
button{font:inherit;padding:8px 16px;border-radius:6px;border:1px solid var(--line);
  background:#fff;cursor:pointer}
button.primary{background:#2b6cb0;color:#fff;border-color:#2b6cb0}
main{max-width:960px;margin:0 auto;padding:20px}
.card{background:#fff;border:1px solid var(--line);border-radius:8px;margin-bottom:20px;
  overflow:hidden}
.card.approved{border-color:var(--ok);box-shadow:0 0 0 1px var(--ok)}
.card.skipped{opacity:.55}
.card.current{box-shadow:0 0 0 3px #bee3f8}
.card-head{padding:14px 18px;border-bottom:1px solid var(--line)}
.card-head h2{font-size:15px;margin:0 0 4px}
.slug{font:12px ui-monospace,monospace;color:var(--muted)}
.desc{font-size:13px;color:#4a5568;margin-top:6px}
.section{padding:14px 18px;border-bottom:1px solid var(--line)}
.section:last-child{border-bottom:none}
.label{font-size:12px;font-weight:600;color:var(--muted);margin-bottom:8px}
.issue{font-size:13px;padding:6px 10px;border-radius:4px;margin-bottom:6px}
.issue.error{background:#fff5f5;color:var(--err);border-left:3px solid var(--err)}
.issue.warn{background:#fffaf0;color:var(--warn);border-left:3px solid var(--warn)}
.clean{font-size:13px;color:var(--ok)}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
input[type=date]{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:4px}
.sns label{display:block;font-size:13px;padding:8px 10px;border:1px solid var(--line);
  border-radius:6px;margin-bottom:6px;cursor:pointer}
.sns label:hover{background:#f7fafc}
.sns input{margin-right:8px}
.type{display:inline-block;font:11px ui-monospace,monospace;background:#edf2f7;
  padding:1px 6px;border-radius:3px;margin-right:6px;color:#4a5568}
details pre{white-space:pre-wrap;font-size:12px;background:#f7fafc;padding:12px;
  border-radius:6px;max-height:420px;overflow:auto}
.hint{font-size:12px;color:var(--muted);margin-left:auto}
</style></head><body>
<header>
  <h1>週末レビュー</h1>
  <span class="counts" id="counts"></span>
  <span class="hint">j/k 移動 · a 承認 · s 見送り</span>
  <button class="primary" id="export">決定を書き出す</button>
</header>
<main id="list"></main>
<script>
const DATA = __DATA__;
const state = {};
DATA.items.forEach(it => state[it.slug] = {
  decision: it.issues.some(x=>x.severity==='error') ? null : 'approve',
  date: it.suggested_date,
  sns: Object.keys(it.sns)[0] || null
});
let cur = 0;

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

function render(){
  const list = document.getElementById('list');
  list.innerHTML = DATA.items.map((it,i) => {
    const st = state[it.slug];
    const errs = it.issues.filter(x=>x.severity==='error');
    const cls = [ 'card', st.decision==='approve'?'approved':(st.decision==='skip'?'skipped':''), i===cur?'current':'' ].join(' ');
    return `<div class="${cls}" id="card-${i}">
      <div class="card-head">
        <h2>${esc(it.title)}</h2>
        <div class="slug">${esc(it.slug)} · ${it.chars}文字</div>
        <div class="desc">${esc(it.description)}</div>
      </div>
      <div class="section">
        <div class="label">自動チェック</div>
        ${it.issues.length === 0 ? '<div class="clean">問題なし</div>' :
          it.issues.map(x=>`<div class="issue ${x.severity}">${esc(x.message)}</div>`).join('')}
        ${errs.length ? '<div class="issue error"><b>要修正があるため、初期状態では承認にしていません</b></div>' : ''}
      </div>
      <div class="section">
        <div class="label">判断</div>
        <div class="row">
          <label><input type="radio" name="d-${i}" ${st.decision==='approve'?'checked':''}
            onchange="setDecision('${it.slug}','approve')"> 承認</label>
          <label><input type="radio" name="d-${i}" ${st.decision==='skip'?'checked':''}
            onchange="setDecision('${it.slug}','skip')"> 見送り</label>
          <span style="margin-left:12px">公開日</span>
          <input type="date" value="${st.date}" onchange="setDate('${it.slug}',this.value)">
        </div>
      </div>
      <div class="section sns">
        <div class="label">SNS投稿(1つ選ぶ / 選ばないことも可)</div>
        ${Object.keys(it.sns).length === 0 ? '<div class="clean" style="color:var(--muted)">サイクルログに投稿案が見つかりませんでした</div>' :
          Object.entries(it.sns).map(([type,text]) => `
          <label><input type="radio" name="s-${i}" ${st.sns===type?'checked':''}
            onchange="setSns('${it.slug}','${type}')">
            <span class="type">${type}</span>${esc(text)}</label>`).join('') +
          `<label><input type="radio" name="s-${i}" ${st.sns===null?'checked':''}
            onchange="setSns('${it.slug}',null)">投稿しない</label>`}
      </div>
      <div class="section">
        <details><summary style="cursor:pointer;font-size:13px">本文を読む</summary>
        <pre>${esc(it.body)}</pre></details>
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

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  const n = DATA.items.length;
  if (e.key==='j'){cur=Math.min(cur+1,n-1);render();document.getElementById('card-'+cur).scrollIntoView({block:'center'})}
  if (e.key==='k'){cur=Math.max(cur-1,0);render();document.getElementById('card-'+cur).scrollIntoView({block:'center'})}
  if (e.key==='a'){setDecision(DATA.items[cur].slug,'approve')}
  if (e.key==='s'){setDecision(DATA.items[cur].slug,'skip')}
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
""".replace("__DATA__", data)


if __name__ == "__main__":
    build()
