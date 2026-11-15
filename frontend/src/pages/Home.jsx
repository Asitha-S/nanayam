// Home: the overview board inside the app (#/home). Every figure comes from the API; nothing is computed or typed here.
import { useState } from 'react'
import { ArrowUpRight, CircleHelp, Download, Link2, RotateCcw } from 'lucide-react'
import { apiUrl, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import QuestionCard from '../components/QuestionCard'
import { useStrings } from '../app/strings'
import { Badge, LoadState, Money, clockTime, confidenceText, count, longDate, monthLabel } from '../components/ui'

const DEMO_HREF = '#/soundbox'

// ---------- 01 Overview ----------

const DAY_START = 6 * 60
const DAY_END = 20 * 60

function minutes(iso) {
  const [h, m] = clockTime(iso).split(':').map(Number)
  return h * 60 + m
}

const KIND = { SALE: 'sale', FAMILY: 'family', PENDING: 'ask' }

/** The day's real payments on a 06:00-20:00 line, coloured by their current classification. */
function DayStrip({ items }) {
  const t = useStrings()
  if (!items) return null
  if (!items.length) {
    return <p className="daystrip-empty note">No payments yet today. They appear here as they arrive on the Soundbox.</p>
  }
  const hours = [6, 8, 10, 12, 14, 16, 18, 20]
  const sorted = [...items].sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
  const labelled = sorted.length <= 18 // amounts only when they fit
  const lastAsk = [...sorted].reverse().find((p) => p.current_classification === 'PENDING')
  const pos = (p) => Math.min(100, Math.max(0, ((minutes(p.timestamp) - DAY_START) / (DAY_END - DAY_START)) * 100))
  const words = { sale: 'sorted as a sale', family: 'family money, kept out of sales', ask: `waiting for an answer in ${t.languageName}` }
  return (
    <figure className="daystrip">
      <figcaption className="visually-hidden">{sorted.length} UPI payments between {clockTime(sorted[0].timestamp)} and {clockTime(sorted[sorted.length - 1].timestamp)}.</figcaption>
      <div className="daystrip-track">
        {hours.map((h) => (
          <span key={h} className="daystrip-hour" style={{ left: `${((h * 60 - DAY_START) / (DAY_END - DAY_START)) * 100}%` }}>
            {String(h).padStart(2, '0')}:00
          </span>
        ))}
        {sorted.map((p, i) => {
          const kind = KIND[p.current_classification] || 'sale'
          return (
            <span key={p.transaction_id} className={`dot is-${kind} ${i % 2 ? 'below' : 'above'}`}
              style={{ left: `${pos(p)}%` }} tabIndex={0}
              aria-label={`${clockTime(p.timestamp)} ${p.payer_name} ${p.amount_display}, ${words[kind]}`}>
              {p === lastAsk ? (
                <span className="dot-card">
                  <b>{clockTime(p.timestamp)} · {p.payer_name}</b>
                  <span className="figure">{p.amount_display}</span>
                  <em>asked in {t.languageName}</em>
                </span>
              ) : labelled && <span className="dot-amt">{p.amount_display}</span>}
            </span>
          )
        })}
      </div>
      <div className="daystrip-legend">
        <span><i className="sw sale" /> Sorted as a sale, silently</span>
        <span><i className="sw family" /> Family money</span>
        <span><i className="sw ask" /> Waiting for an answer in {t.languageName}</span>
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

function Overview({ payments, summary, dayWord, shownDate, merchantName }) {
  const t = useStrings()
  const s = summary.data
  return (
    <section id="overview" className="overview" aria-labelledby="overview-h">
      <div className="panel hero-panel">
        <div className="panel-head">
          <span className="label">{merchantName}</span>
          <Badge kind="synthetic">Synthetic data</Badge>
        </div>
        <h1 id="overview-h">The day,<br />payment by payment.</h1>
        <p className="lede">
          Every UPI payment is sorted as it arrives. Sure calls stay silent; the one Naanayam isn't sure about becomes
          a question in {t.languageName}. Every amount opens the ledger entries behind it.
        </p>
        {payments.data ? <DayStrip items={payments.data.items} /> : <LoadState state={payments} what="the day's payments" />}
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

function Question({ questions, evaluation }) {
  const t = useStrings()
  const { merchantId, merchant, language, demoDate } = useMerchant()
  const owner = merchant?.owner_name || 'the merchant'
  const open = questions.data?.items || []
  const q = open[0] || null // newest first (contract); opened by its own question_id
  const tau = evaluation.data?.threshold
  return (
    <section id="question" className="panel question" aria-labelledby="question-h">
      <div className="question-copy">
        <span className="label">{q ? 'Waiting for an answer' : 'Questions'}</span>
        <h2 id="question-h">When it isn&apos;t sure, it asks.</h2>
        <p>
          Below the confidence threshold{typeof tau === 'number' ? ` (${tau})` : ''}, a payment waits as pending
          until {owner} answers. Two big buttons, in {t.languageName}, on the Soundbox and the phone.
        </p>
        {open.length > 1 && <p className="question-note"><a href="#/questions">{open.length - 1} more waiting today</a></p>}
      </div>
      {q ? (
        <QuestionCard key={q.question_id} question={q} merchantId={merchantId} language={language} demoDate={demoDate} />
      ) : (
        <div className="qcard question-none">
          <p className="qcard-en">No question right now. Naanayam has been sure about every payment so far today; when it isn&apos;t,
            the question appears here, on the Soundbox and on the Questions screen.</p>
          <a className="btn" href="#/soundbox">Open the Soundbox</a>
        </div>
      )}
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
  const shown = todayEmpty ? prev : day
  const payments = useApi(shown ? `/merchants/${MERCHANT}/payments?start_date=${shown}&end_date=${shown}&limit=500` : null, { pollMs: 5000 })
  const questions = useApi(day ? `/merchants/${MERCHANT}/questions?status=OPEN&date=${day}` : null)
  const owner = merchant?.owner_name || 'The merchant'

  return (
    <div className="home">
        <Overview payments={payments} summary={summary} dayWord={dayWord} shownDate={todayEmpty ? prev : day}
          merchantName={merchant?.display_name || MERCHANT} />
        <How />
        <Question questions={questions} evaluation={evaluation} />
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
