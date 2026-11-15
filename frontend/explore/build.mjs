// Direction boards for the Today screen (exploration only; not the app). node frontend/explore/build.mjs
// Every amount and Tamil question comes from contract/fixtures (backend-formatted amount_display): nothing is
// computed or typed by hand here. Tamil UI labels are drafts from docs/VOICE_AND_NOTICE.md section 7 (to review).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const fx = (name) => JSON.parse(readFileSync(join(here, "../../contract/fixtures", `${name}.json`), "utf8"));
const before = fx("summary_M001_before_confirm");
const after = fx("summary_M001_after_confirm");
const question = fx("questions_M001_open_2026-11-15").items[0];
const merchant = fx("merchant_M001");
const expense = fx("expenses_list_M001_2026-11-15").items[0];
const script = JSON.parse(readFileSync(join(here, "../../data/demo/M001_demo_day.json"), "utf8"));
const time = (iso) => iso.slice(11, 16);

const T = {  // Tamil drafts (VOICE_AND_NOTICE 7) + English for the judges
  today: ["இன்னைக்கு", "Today, 15 Nov"],
  profit: ["மீதம்", "Recorded profit"],
  sales: ["கடை வியாபாரம்", "Shop sales"],
  expenses: ["செலவு", "Expenses"],
  family: ["வீட்டு பணம்", "Family money"],
  pending: ["இன்னும் சொல்லல", "Waiting for your answer"],
  notCounted: ["கடை கணக்குல சேர்க்கல", "Not in profit"],
  askSale: ["கடை வியாபாரம்", "Shop sale"],
  askFamily: ["வீட்டு பணம்", "Family money"],
  scopeTa: "UPI பணம் மட்டும். கையில வாங்கின காசு இதுல இல்ல.",
  newPayment: ["புது பணம்", "New payment"],
  records: ["இன்னைக்கு பதிவு", "Today's records"],
  nextFamily: ["இனிமே வீட்டு பணம்", "Next payments: family"],
};
const pair = ([ta, en], cls = "") => `<span class="ta ${cls}">${ta}</span><span class="en">${en}</span>`;
const money = (amount, extra = "") => `<a class="money ${extra}" href="#ledger" aria-label="${amount}, open ledger entries">${amount}</a>`;

function figures(s, state) {
  const pendingRow = s.pending.count
    ? `<div class="row pending"><div class="label">${pair(T.pending)}<span class="count">${s.pending.count} payment</span></div>${money(s.pending.amount_display)}</div>`
    : "";
  return `
  <section class="figures" aria-label="Today's figures">
    <div class="profit"><div class="label">${pair(T.profit, "big")}</div>${money(s.profit.amount_display, "hero")}</div>
    <div class="eq">
      <div class="row"><div class="label">${pair(T.sales)}</div>${money(s.business_sales.amount_display)}</div>
      <div class="row minus"><div class="label">${pair(T.expenses)}</div>${money(s.expenses.amount_display)}</div>
    </div>
    ${pendingRow}
    <div class="row family"><div class="label">${pair(T.family)}<span class="kept">${T.notCounted[1]}</span></div>${money(s.family_transfers.amount_display)}</div>
  </section>`;
}

function phone(state) {
  const s = state === "ask" ? before : after;
  const top = `
  <header class="top"><div class="shop">${merchant.display_name}</div><div class="day">${pair(T.today)}</div></header>`;
  const ask = `
  <section class="ask" aria-label="Question">
    <div class="ask-meta"><span class="kicker">${T.newPayment[1]} · ${time(question.timestamp)}</span><span class="ask-amt">${question.amount_display}</span><span class="who">${question.payer_name}</span></div>
    <p class="ta question">${question.question_text}</p>
    <p class="en">${question.question_text_en}</p>
    <div class="answers"><button class="answer">${pair(T.askSale)}</button><button class="answer">${pair(T.askFamily)}</button></div>
  </section>`;
  const records = `
  <section class="records" aria-label="${T.records[1]}">
    <div class="rec"><div class="rec-main"><span class="rec-name">${question.payer_name}</span>${pair(T.nextFamily)}</div><span class="badge">Your instruction</span></div>
    <div class="rec"><div class="rec-main"><span class="rec-name">${expense.description} · ${time(expense.timestamp)}</span><span class="en">“${script.expense.utterance_text}”</span></div><span class="badge">Recorded demo clip</span></div>
  </section>`;
  const scope = `<footer class="scope"><span class="ta">${T.scopeTa}</span><span class="en">${s.scope_note}</span></footer>`;
  return `<article class="phone state-${state}" aria-label="${state === "ask" ? "19:42, question open" : "After the answer"}">${top}${state === "ask" ? ask : ""}${figures(s, state)}${state === "ask" ? "" : records}${scope}</article>`;
}

const FONTS = "https://fonts.googleapis.com/css2?family=Noto+Sans+Tamil:wght@400;500;600;700&family=Noto+Sans:wght@400;500;600&";
const BASE = `
*{box-sizing:border-box;margin:0}
body{background:var(--board);color:var(--ink);font:400 18px/1.35 var(--sans)}
.board{width:1440px;min-height:1040px;padding:36px 64px;display:grid;grid-template-columns:1fr 412px 412px 1fr;gap:0 56px;align-content:start}
.board>h1{grid-column:1/-1;font:500 15px/1.4 var(--mono);letter-spacing:.02em;color:var(--muted);margin-bottom:24px}
.board>h1 b{color:var(--ink);font-weight:500}
.phone{grid-column:auto;background:var(--bg);min-height:900px;border:1px solid var(--line);border-radius:28px;padding:22px 20px 18px;display:flex;flex-direction:column;gap:18px;overflow:hidden}
.phone.state-ask{grid-column:2}.phone.state-done{grid-column:3}
.ta{font-family:"Noto Sans Tamil",var(--sans);font-size:22px;line-height:1.45;display:block}
.en{font-size:15px;line-height:1.35;color:var(--muted);display:block}
.top{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}
.shop{font:600 20px/1.2 var(--display);letter-spacing:-.01em;max-width:200px}
.day{text-align:right}.day .ta{font-size:22px}
.money{color:inherit;text-decoration:none;font:600 32px/1.1 var(--display);font-family:var(--display),"Noto Sans",sans-serif;white-space:nowrap}
.money.hero{font-size:60px;letter-spacing:-.02em;line-height:1}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0}
.count,.kept{font:500 13px/1.3 var(--mono);color:var(--muted);display:block;margin-top:2px}
.answers{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.answer{min-height:76px;font:inherit;color:var(--ink);background:var(--bg);border:2px solid var(--ink);border-radius:var(--r);cursor:pointer;padding:8px;text-align:center}
.answer .ta{font-weight:600;font-size:22px}.answer .en{font-size:14px}
.answer:hover{background:var(--surface)}.answer:active{transform:translateY(1px)}
.badge{font:500 13px/1 var(--mono);letter-spacing:.02em;color:var(--badge-ink);border:1px solid var(--badge-line);border-radius:999px;padding:6px 9px;white-space:nowrap}
.records{display:flex;flex-direction:column}
.rec{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 0;border-top:1px solid var(--line)}
.rec-name{font:600 17px/1.3 var(--sans);display:block}.rec .ta{font-size:22px}
.scope{margin-top:auto;padding-top:14px;border-top:1px solid var(--line)}.scope .ta{font-size:22px}.scope .en{font-size:14px}
.ask{animation:card-in 200ms ease-out both}
@keyframes card-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.ask{animation:none}}
`;

const DIRECTIONS = {
  a: {
    title: "A · Sheet and biro", deal: "palette white-link-blue (deal 1, first) · type Funnel (deal 1, first)",
    font: "family=Funnel+Display:wght@400..700&family=Funnel+Sans:wght@400..600&family=DM+Mono:wght@400;500&display=swap",
    css: `:root{--bg:#ffffff;--surface:#f4f4f4;--ink:#111111;--muted:#555555;--accent:#1a4be0;--line:#d9d9d9;--board:#ececec;
      --badge-ink:#1a4be0;--badge-line:#1a4be0;--r:6px;--display:"Funnel Display";--sans:"Funnel Sans","Noto Sans",sans-serif;--mono:"DM Mono",monospace}
      .money{color:var(--accent);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:6px}
      .profit{padding:6px 0 14px;border-bottom:3px double var(--ink)}
      .profit .money.hero{color:var(--ink);text-decoration-color:var(--accent)}
      .eq .row{border-bottom:1px solid var(--line)}
      .minus .money::before{content:"− ";color:var(--muted)}
      .ask{background:var(--surface);border-radius:var(--r);padding:16px}
      .ask-meta{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.kicker{font:500 13px var(--mono);color:var(--muted);width:100%}
      .ask-amt{font:600 34px/1 var(--display)}.who{font-size:18px;color:var(--ink)}
      .question{font-size:24px;font-weight:500;margin-top:10px}
      .family{border-top:1px dashed var(--muted);margin-top:4px}.family .money{color:var(--ink)}`,
  },
  b: {
    title: "B · Frost and slate", deal: "palette cool-white-slate (deal 2, first) · type Host Grotesk (deal 2, first)",
    font: "family=Host+Grotesk:wght@400..700&family=JetBrains+Mono:wght@400..500&display=swap",
    css: `:root{--bg:#f7f9fa;--surface:#ecf0f2;--ink:#1f3038;--muted:#4f6670;--accent:#0d7480;--line:#d3dde1;--board:#e3e9ec;
      --badge-ink:#0d7480;--badge-line:#0d7480;--r:10px;--display:"Host Grotesk";--sans:"Host Grotesk","Noto Sans",sans-serif;--mono:"JetBrains Mono",monospace}
      .figures{display:flex;flex-direction:column}
      .profit{order:3;background:var(--accent);color:#ffffff;border-radius:var(--r);padding:16px 18px;display:flex;justify-content:space-between;align-items:flex-end}
      .profit .en,.profit .ta{color:#ffffff}.profit .money.hero{font-size:52px}
      .profit .money::before{content:"= ";font-weight:400;opacity:.8}
      .eq{order:1}.pending{order:4}.family{order:5}
      .eq .row{padding:10px 2px}.minus{border-bottom:2px solid var(--ink)}
      .minus .money::before{content:"− ";color:var(--muted)}
      .family{margin-top:12px;background:var(--surface);border-radius:var(--r);padding:14px 16px;border-left:6px solid var(--muted)}
      .pending{padding:14px 2px}
      .ask{background:#ffffff;border:1px solid var(--line);border-top:5px solid var(--accent);border-radius:var(--r);padding:16px}
      .ask-meta{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.kicker{font:500 13px var(--mono);color:var(--accent);width:100%}
      .ask-amt{font:600 34px/1 var(--display)}.who{font-size:18px}
      .question{font-size:24px;font-weight:500;margin-top:10px}
      .answer{background:var(--surface);border:0}.answer:hover{background:var(--line)}
      .money{text-decoration:underline;text-decoration-style:dotted;text-decoration-thickness:2px;text-underline-offset:7px;text-decoration-color:var(--muted)}
      .profit .money{text-decoration-color:#ffffff99}`,
  },
  c: {
    title: "C · Paper and brass", deal: "palette warm-black-gold (deal 1, second) turned light for the brief · type Schibsted Grotesk (picked)",
    font: "family=Schibsted+Grotesk:wght@400..700&family=JetBrains+Mono:wght@400..500&display=swap",
    css: `:root{--bg:#f6f1e6;--surface:#ece4d3;--ink:#1a1612;--muted:#5d5244;--accent:#8a6420;--gold:#c9a45a;--line:#d8cdb6;--board:#e6dfcf;
      --badge-ink:#5b4210;--badge-line:#c9a45a;--r:2px;--display:"Schibsted Grotesk";--sans:"Schibsted Grotesk","Noto Sans",sans-serif;--mono:"JetBrains Mono",monospace}
      .top{border-bottom:2px solid var(--ink);padding-bottom:12px}
      .profit{border:2px solid var(--gold);padding:14px 16px;display:flex;justify-content:space-between;align-items:flex-end;background:#fbf8f1}
      .profit .money.hero{font-size:54px}
      .eq .row{border-bottom:1px solid var(--line)}
      .minus .money::before{content:"− ";color:var(--muted)}
      .money{text-decoration:none;border-bottom:2px solid var(--gold);padding-bottom:2px}
      .ask{border-left:6px solid var(--accent);background:#fbf8f1;padding:14px 16px}
      .ask-meta{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.kicker{font:500 13px var(--mono);color:var(--accent);width:100%;text-transform:uppercase;letter-spacing:.06em}
      .ask-amt{font:700 34px/1 var(--display)}.who{font-size:18px}
      .question{font-size:24px;font-weight:500;margin-top:10px}
      .answer{background:var(--ink);color:var(--bg);border-color:var(--ink)}.answer .en{color:#d8cdb6}.answer:hover{background:#000}
      .family{border-top:2px solid var(--ink);margin-top:6px}
      .badge{background:#fbf8f1}`,
  },
};

for (const [key, d] of Object.entries(DIRECTIONS)) {
  const html = `<!doctype html><html lang="ta"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Naanayam Today: direction ${d.title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}${d.font}">
<style>${BASE}${d.css}</style></head>
<body><main class="board"><h1><b>${d.title}</b> · ${d.deal} · data: contract/fixtures (M001, 15 Nov)</h1>
${phone("ask")}
${phone("done")}
</main></body></html>`;
  writeFileSync(join(here, `${key}.html`), html, "utf8");
  console.log(`wrote ${key}.html`);
}
