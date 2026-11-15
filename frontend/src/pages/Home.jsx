// Home: the overview board inside the app (#/home). Every figure comes from the API; nothing is computed or typed here.
import { useState } from 'react'
import { ArrowUpRight, CircleHelp, Download, Link2, RotateCcw } from 'lucide-react'
import { apiUrl, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { useStrings } from '../app/strings'
import { Badge, LoadState, Money, clockTime, confidenceText, count, longDate, monthLabel } from '../components/ui'

const DEMO_HREF = '#/soundbox'

// ---------- 01 Overview ----------

const DAY_START = 6 * 60
const DAY_END = 20 * 60

function minutes(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function DayStrip({ items }) {
  const t = useStrings()
  if (!items?.length) return null
  const hours = [6, 8, 10, 12, 14, 16, 18, 20]
  return (
    <figure className="daystrip">
      <figcaption className="visually-hidden">The demo day: {items.length} UPI payments between {items[0].time} and {items[items.length - 1].time}.</figcaption>
      <div className="daystrip-track">
        {hours.map((h) => (
          <span key={h} className="daystrip-hour" style={{ left: `${((h * 60 - DAY_START) / (DAY_END - DAY_START)) * 100}%` }}>
            {String(h).padStart(2, '0')}:00
          </span>
        ))}
        {items.map((it, i) => {
          const ask = it.expected_action === 'ASK_MERCHANT'
          const left = ((minutes(it.time) - DAY_START) / (DAY_END - DAY_START)) * 100
          const what = ask ? `asked in ${t.languageName}` : `sorted as ${it.expected_classification.toLowerCase()}`
          return (
            <span key={it.transaction_id} className={`dot ${ask ? 'is-ask' : 'is-sale'} ${i % 2 ? 'below' : 'above'}`}
              style={{ left: `${left}%` }} tabIndex={0} aria-label={`${it.time} ${it.payer_name} ${it.amount_display}, ${what}`}>
              {ask ? (
                <span className="dot-card">
                  <b>{it.time} · {it.payer_name}</b>
                  <span className="figure">{it.amount_display}</span>
                  <em>asked in {t.languageName}</em>
                </span>
              ) : (
                <span className="dot-amt">{it.amount_display}</span>
              )}
            </span>
          )
        })}
      </div>
      <div className="daystrip-legend">
        <span><i className="sw sale" /> Sorted as a sale, silently</span>
        <span><i className="sw ask" /> Not sure, so asked in {t.languageName}</span>
      </div>
    </figure>
  )
}

function TodayList({ summary }) {
  const s = summary.data
  if (!s) return <LoadState state={summary} what="today's summary" />
  const src = s.sources || {}
  const rows = [
    { key: 'sales', name: 'Business sales', note: plural(src.business_sales?.length, 'payment'), amount: s.business_sales, ids: src.business_sales },
    { key: 'expenses', name: 'Expenses', note: plural(src.expenses?.length, 'entry', 'entries'), amount: s.expenses, ids: src.expenses },
    { key: 'family', name: 'Family money', note: 'kept out of sales', amount: s.family_transfers, ids: src.family_transfers, tone: 'family' },
  ]
  if (s.pending?.count) {
    rows.push({ key: 'pending', name: 'Waiting for an answer', note: `${plural(s.pending.count, 'payment')}, not counted yet`, amount: s.pending, ids: src.pending, tone: 'pending' })
  }
  return (
    <>
      <ol className="today-list">
        {rows.map((r, i) => (
          <li key={r.key} className={r.tone ? `tone-${r.tone}` : ''}>
            <span className="today-n figure">{String(i + 1).padStart(2, '0')}</span>
            <span className="today-name"><b>{r.name}</b><small>{r.note}</small></span>
            <Money amount={r.amount} sources={r.ids} className="today-amt" />
          </li>
        ))}
      </ol>
      <div className="today-profit">
        <span className="label">{s.profit?.label || 'Recorded profit'}</span>
        <Money amount={s.profit} sources={[...(src.business_sales || []), ...(src.expenses || [])]} className="today-profit-amt" />
        <Badge kind="ledger" />
      </div>
    </>
  )
}

function Overview({ script, summary, dayWord, shownDate, merchantName }) {
  const t = useStrings()
  const s = summary.data
  return (
    <section id="overview" className="overview" aria-labelledby="overview-h">
      <div className="panel hero-panel">
        <div className="panel-head">
          <span className="label">{merchantName}</span>
          <Badge kind="synthetic">Synthetic demo day</Badge>
        </div>
        <h1 id="overview-h">The day,<br />payment by payment.</h1>
        <p className="lede">
          Every UPI payment is sorted as it arrives. Sure calls stay silent; the one Naanayam isn't sure about becomes
          a question in {t.languageName}. Every amount opens the ledger entries behind it.
        </p>
        {script.data ? <DayStrip items={script.data.items} /> : <LoadState state={script} what="the demo day" />}
      </div>

      <div className="panel today-panel">
        <div className="panel-head">
          <span className="label">{dayWord} at the stall</span>
          {s && (dayWord === 'Today'
            ? <span className="label live"><i aria-hidden="true" /> as of {clockTime(s.as_of)} IST</span>
            : <span className="label">{longDate(shownDate)}</span>)}
        </div>
        <h2>What the shop really earned.</h2>
        <TodayList summary={summary} />
      </div>

      {s && (
        <p className="plain">
          <CircleHelp aria-hidden="true" />
          <span><b>In plain language:</b> {s.scope_note}</span>
        </p>
      )}
    </section>
  )
}

// ---------- 02 How it works ----------

const STEPS = [
  { t: 'A payment arrives', d: 'The Soundbox announces it; Naanayam sees the same UPI credit.' },
  { t: 'Sorted when sure', d: 'A calibrated model separates sales from family money. Confident calls stay silent.' },
  { t: 'Asked when not', d: (lang) => `One question in ${lang}, two big answers. Uncertain means ask, never guess.` },
  { t: 'Remembered', d: (lang, owner) => `${owner}'s answers shape how that payer's next payments are handled.` },
  { t: 'Written to the ledger', d: 'Append-only and hash-chained, so a changed entry is caught.' },
]

function How() {
  const t = useStrings()
  const owner = useMerchant().merchant?.owner_name || 'The merchant'
  return (
    <section id="how" className="how" aria-labelledby="how-h">
      <div className="section-head">
        <h2 id="how-h">From a payment to proof.</h2>
        <p>The backend calculates every rupee. Voice only speaks numbers the ledger already holds.</p>
      </div>
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s.t}>
            <span className="step-n figure">{i + 1}</span>
            <b>{s.t}</b>
            <span>{typeof s.d === 'function' ? s.d(t.languageName, owner) : s.d}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

// ---------- 03 The question ----------

function QuestionCard({ question, askItem }) {
  const t = useStrings()
  const [answer, setAnswer] = useState(null)
  const payer = question?.payer_name || askItem?.payer_name
  const amount = question?.amount_display || askItem?.amount_display
  return (
    <div className={`qcard ${answer ? 'is-answered' : ''}`}>
      <div className="qcard-head">
        <span className="qcard-avatar" aria-hidden="true">{payer?.[0]}</span>
        <span>
          <b>{payer}</b>
          <small className="figure">{amount}{question && ` · ${clockTime(question.timestamp)}`}</small>
        </span>
        {question && (
          <span className="qcard-conf label">
            {confidenceText(question.confidence)} sure it's {question.suggested_classification === 'FAMILY' ? 'family' : 'a sale'}
          </span>
        )}
      </div>
      {question ? (
        <>
          <p className="qcard-ta" lang="ta">{question.question_text}</p>
          <p className="qcard-en">{question.question_text_en}</p>
        </>
      ) : (
        <p className="qcard-en">This question appears in the live demo when {payer}'s payment arrives.</p>
      )}
      <div className="qcard-answers">
        <button type="button" onClick={() => setAnswer('SALE')} disabled={Boolean(answer)}>
          <span lang={t.lang}>{t.sale}</span><small>Shop sale</small>
        </button>
        <button type="button" onClick={() => setAnswer('FAMILY')} disabled={Boolean(answer)}>
          <span lang={t.lang}>{t.family}</span><small>Family money</small>
        </button>
      </div>
      {answer && (
        <div className="qcard-stamp" role="status">
          <span className="stamp" lang={t.lang}>{answer === 'FAMILY' ? t.family : t.sale}</span>
          <p>
            Preview only: nothing was saved. In the live demo this answer goes to the ledger
            {answer === 'FAMILY' ? ', stays out of sales,' : ''} and Naanayam asks whether to remember {payer}.
          </p>
          <button type="button" className="btn" onClick={() => setAnswer(null)}><RotateCcw aria-hidden="true" /> Try again</button>
        </div>
      )}
    </div>
  )
}

function Question({ script, questions, evaluation }) {
  const t = useStrings()
  const owner = useMerchant().merchant?.owner_name || 'the merchant'
  const askItem = script.data?.items.find((it) => it.expected_action === 'ASK_MERCHANT')
  // open by transaction, never by list position (the seed keeps older open questions)
  const question = askItem && questions.data?.items.find((q) => q.transaction_id === askItem.transaction_id)
  const tau = evaluation.data?.threshold
  return (
    <section id="question" className="panel question" aria-labelledby="question-h">
      <div className="question-copy">
        <span className="label">The one question of the day</span>
        <h2 id="question-h">When it isn't sure, it asks.</h2>
        <p>
          {askItem ? `${askItem.payer_name}'s ${askItem.amount_display} could be a sale or family money. ` : ''}
          Below the confidence threshold{typeof tau === 'number' ? ` (${tau})` : ''}, a payment waits as pending
          until {owner} answers. Two big buttons, in {t.languageName}, on the Soundbox and the phone.
        </p>
        <p className="question-note">Try it here. This card is a preview; the live demo saves the answer.</p>
      </div>
      {askItem ? <QuestionCard question={question} askItem={askItem} /> : <LoadState state={script} what="the question" />}
    </section>
  )
}

// ---------- 04 Proofs ----------

function Proofs({ summary, passport, health, dayWord, merchantId }) {
  const t = useStrings()
  const owner = useMerchant().merchant?.owner_name || 'the merchant'
  const s = summary.data
  const src = s?.sources || {}
  const months = passport.data?.months || []
  const last = months[months.length - 1]
  const day = health.data?.demo_date
  const pdf = day && apiUrl(`/merchants/${merchantId}/export/pdf?start_date=${day}&end_date=${day}`)
  const csv = day && apiUrl(`/merchants/${merchantId}/export/csv?start_date=${day}&end_date=${day}`)
  return (
    <section id="proofs" className="proofs" aria-labelledby="proofs-h">
      <div className="section-head">
        <h2 id="proofs-h">One ledger, three proofs.</h2>
        <p>The same entries answer the merchant, the taxman and the lender.</p>
      </div>
      <div className="proof-grid">
        <article className="panel proof proof-profit">
          <span className="label">For {owner}</span>
          <h3>Proof of profit</h3>
          <p>Ask "how much did I make today?" and hear it back in {t.languageName}, from fixed templates checked against the ledger.</p>
          <div className="proof-fig">
            {s ? <Money amount={s.profit} sources={[...(src.business_sales || []), ...(src.expenses || [])]} /> : '…'}
            <small>{s?.profit?.label || 'Recorded profit'}, {dayWord.toLowerCase()}</small>
          </div>
          <Badge kind="ledger" />
        </article>

        <article className="panel proof proof-tax">
          <span className="label">For the CA</span>
          <h3>Proof for the taxman</h3>
          <p>A sample GST notice becomes an evidence summary: what the ledger shows for the notice period, for a CA to review.</p>
          <div className="proof-links">
            {pdf ? (
              <>
                <a className="btn" href={pdf} target="_blank" rel="noreferrer"><Download aria-hidden="true" /> CA pack PDF</a>
                <a className="btn" href={csv} target="_blank" rel="noreferrer"><Download aria-hidden="true" /> CSV</a>
              </>
            ) : <small>Exports need the live backend.</small>}
          </div>
          <span className="proof-foot">Not legal advice. No filing, no automatic replies.</span>
          <Badge kind="notice" />
        </article>

        <article className="panel proof proof-lender">
          <span className="label">For the lender</span>
          <h3>Proof for the lender</h3>
          <p>A credit passport: what came in, and what was really business, month by month.</p>
          {last ? (
            <dl className="proof-pair">
              <div><dt>Raw collections, {monthLabel(last.month)}</dt><dd><Money amount={last.raw_collections_display} /></dd></div>
              <div><dt>Recorded business income</dt><dd><Money amount={last.recorded_income_display} /></dd></div>
            </dl>
          ) : <LoadState state={passport} what="the passport" />}
          <span className="proof-foot">Shown only. Not a credit score or a loan decision.</span>
        </article>
      </div>
    </section>
  )
}

// ---------- 05 Evaluation ----------

function Evaluation({ evaluation }) {
  const e = evaluation.data
  const h = e?.headline
  return (
    <section id="evaluation" className="panel evaluation" aria-labelledby="eval-h">
      <div className="panel-head">
        <span className="label">Held-out evaluation</span>
        {e && <Badge kind="synthetic">{e.data_label}</Badge>}
      </div>
      <h2 id="eval-h">Does it find the family money?</h2>
      {!e && <LoadState state={evaluation} what="the evaluation" />}
      {e && !h && (
        <p className="eval-missing">
          This evaluation file has no headline block, so there are no results to show. Run <code>python -m ml.evaluate</code> and
          serve <code>data/eval/latest.json</code>.
        </p>
      )}
      {h && (
        <div className="eval-grid">
          <div className="eval-main">
            <span className="label">Family money found, with learning</span>
            <strong className="figure">
              {count(h.with_feedback.family_money_found.count)}<span> of {count(h.with_feedback.family_money_found.of)}</span>
            </strong>
            <p>
              Before learning: {count(h.baseline.family_money_found.count)} of {count(h.baseline.family_money_found.of)}.
              Counting every payment as a sale finds {count(h.always_sale.family_money_found.count)}.
            </p>
          </div>
          <dl className="eval-side">
            <div>
              <dt>Income wrongly removed</dt>
              <dd className="figure">{count(h.with_feedback.income_wrongly_removed.count)} of {count(h.with_feedback.income_wrongly_removed.of)}</dd>
              <span>{count(h.with_feedback.income_wrongly_removed.silent)} silent, {count(h.with_feedback.income_wrongly_removed.merchant_answer_errors)} from simulated answer mistakes</span>
            </div>
            <div>
              <dt>Questions per merchant per day</dt>
              <dd className="figure">{h.with_feedback.questions_per_merchant_per_day}</dd>
              <span>{h.baseline.questions_per_merchant_per_day} before learning</span>
            </div>
          </dl>
        </div>
      )}
      {e && (
        <p className="eval-foot label">
          Run {e.run_id} · {count(e.split?.test_merchants)} test merchants · {count(e.split?.test_transactions)} test payments · {e.split?.test_period}
        </p>
      )}
    </section>
  )
}

// ---------- 06 Ledger ----------

function Ledger({ verify }) {
  const v = verify.data
  return (
    <section id="ledger" className="ledger" aria-labelledby="ledger-h">
      <div className="panel ledger-panel">
        <div className="ledger-copy">
          <span className="label">Tamper-evident ledger</span>
          <h2 id="ledger-h">Nothing is edited. Everything is checked.</h2>
          <p>Corrections are new entries. Each entry carries the hash of the one before it, so any change breaks the chain where it happened.</p>
        </div>
        <div className="ledger-proof">
          <div className="chain" aria-hidden="true">
            {Array.from({ length: 7 }, (_, i) => <span key={i}><Link2 /></span>)}
          </div>
          <div className={`verify ${v?.status === 'VALID' ? 'is-valid' : v ? 'is-bad' : ''}`}>
            {v ? (
              <>
                <strong className="figure">{v.status}</strong>
                <span>{v.message}</span>
              </>
            ) : <LoadState state={verify} what="the ledger check" />}
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------- page ----------

function plural(n, one, many = `${one}s`) {
  return `${count(n ?? 0)} ${n === 1 ? one : many}`
}

/** No collections, no expenses, nothing pending: the day has not started. Reads amounts, computes none. */
function isEmptyDay(s) {
  return s.total_collections?.amount_paise === 0 && s.expenses?.amount_paise === 0 && !s.pending?.count
}

/** "2026-11-15" -> "2026-11-14" (calendar arithmetic on the IST date the backend sent) */
function previousDay(iso) {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() - 1)
  return d.toISOString().slice(0, 10)
}

export default function Home() {
  const { merchantId: MERCHANT, merchant } = useMerchant()
  const health = useApi('/health')
  const verify = useApi(`/merchants/${MERCHANT}/ledger/verify`)
  const script = useApi(`/demo/script?merchant_id=${MERCHANT}`)
  const today = useApi(`/merchants/${MERCHANT}/summary?include_sources=true`)
  const evaluation = useApi('/evaluation')
  const passport = useApi(`/merchants/${MERCHANT}/passport`)
  const day = health.data?.demo_date
  // Before the live demo starts, today is empty: show yesterday's ledger day instead of a row of zeros.
  const todayEmpty = today.data && isEmptyDay(today.data)
  const prev = day && previousDay(day)
  const yesterday = useApi(todayEmpty && prev
    ? `/merchants/${MERCHANT}/summary?start_date=${prev}&end_date=${prev}&include_sources=true` : null)
  const summary = todayEmpty ? yesterday : today
  const dayWord = todayEmpty ? 'Yesterday' : 'Today'
  const questions = useApi(day ? `/merchants/${MERCHANT}/questions?status=OPEN&date=${day}` : null)
  const owner = merchant?.owner_name || 'The merchant'

  return (
    <div className="home">
        <Overview script={script} summary={summary} dayWord={dayWord} shownDate={todayEmpty ? prev : day}
          merchantName={merchant?.display_name || MERCHANT} />
        <How />
        <Question script={script} questions={questions} evaluation={evaluation} />
        <Proofs summary={summary} passport={passport} health={health} dayWord={dayWord} merchantId={MERCHANT} />
        <Evaluation evaluation={evaluation} />
        <Ledger verify={verify} />
        <section className="panel close" aria-labelledby="close-h">
          <h2 id="close-h">{owner}'s day is ready to run.</h2>
          <p>Send the payments, answer the question, log the day's expense by voice, and ask for today's profit.</p>
          <a className="btn ink big" href={DEMO_HREF}>Open the live demo <ArrowUpRight aria-hidden="true" /></a>
        </section>
        <footer className="foot">
          <span>Naanayam · Team Aether · Paytm Build for India AI Hackathon, Chennai, 2026 · Track 1</span>
          <span>All payments are synthetic. No real Paytm, bank or GST portal connection.</span>
        </footer>
    </div>
  )
}
