// P2 · Learning (for judges). Two sources, never mixed:
//   GET /merchants/{id}/learning  this merchant's questions, answers and payer memory (counts only, no precision)
//   GET /evaluation               the held-out run file. Every metric on screen comes from it, next to its data_label.
// POST /classify/preview runs the full decision for a payment that hasn't happened. It writes nothing.
import '../styles/learning.css'
import { ArrowRight, Info, Play, RefreshCw, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { post, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { Badge, LoadState, clockTime, confidenceText, count, longDate } from '../components/ui'

// ---------- shared bits ----------

function words(s) {
  return (s || '').toLowerCase().replaceAll('_', ' ')
}

function hintFor(error) {
  if (error?.code === 'UNREACHABLE') return 'Start the backend on port 8000, then try again.'
  if (error?.code === 'NO_FIXTURE') return 'Fixtures mode has no file for this request.'
  if (error?.code === 'NOT_FOUND') return 'Check the merchant, then try again.'
  if (error?.code === 'VALIDATION_ERROR') return 'Check the payer and the amount, then try again.'
  return 'Try again in a moment.'
}

function ErrorBanner({ error, hint, onRetry }) {
  return (
    <div className="error-banner lr-error" role="alert">
      <TriangleAlert aria-hidden="true" />
      <span>{(error?.message || 'Something went wrong').replace(/\.$/, '')}. {hint ?? hintFor(error)}</span>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}><RefreshCw aria-hidden="true" /> Try again</button>
      )}
    </div>
  )
}

/** Loading line or error banner for a useApi state; nothing once data is in. */
function Status({ state, what, hint }) {
  if (state.error && !state.data) {
    return <ErrorBanner error={{ ...state.error, message: `Couldn't load ${what}: ${state.error.message}` }} hint={hint} onRetry={state.reload} />
  }
  if (!state.data) return <LoadState state={state} what={what} />
  return null
}

// ---------- evaluation helpers (format what the file says; never derive a metric) ----------

/** Condition A-E. The run file keys them "A".."E"; older files used "A_always_sale" etc. */
function cond(e, letter) {
  const c = e?.conditions || {}
  const key = Object.keys(c).find((k) => k === letter || k.startsWith(`${letter}_`))
  return key ? c[key] : null
}

const isCount = (m) => m && typeof m === 'object' && typeof m.count === 'number' && typeof m.of === 'number'
const ofText = (m) => (isCount(m) ? `${count(m.count)} of ${count(m.of)}` : '—')

/** A rate from the file as a percentage. Never "100%": rates are rounded in the file. */
function pct(x) {
  if (typeof x !== 'number') return '—'
  if (x === 0) return '0%'
  if (x >= 0.9995) return '>99.9%'
  return `${(x * 100).toFixed(1)}%`
}

const num = (x) => (typeof x === 'number' ? String(x) : '—')

/** "9 of 512" cell; a zero denominator means the source was not used. */
function OfCell({ m, sub }) {
  if (!isCount(m)) return <span className="lr-dim">—</span>
  if (m.of === 0) return <span className="lr-dim">not used</span>
  return (
    <>
      <span className="lr-of"><b>{count(m.count)}</b> of {count(m.of)}</span>
      {sub && <small>{sub}</small>}
    </>
  )
}

function removedSub(m) {
  if (!m || typeof m.silent !== 'number') return null
  return `${count(m.silent)} silent · ${count(m.merchant_answer_errors)} answer mistakes`
}

// ---------- 1. headline ----------

const HEAD_COLS = [
  { key: 'always_sale', letter: 'A', name: 'Always sale', sub: 'Every payment counted as a sale' },
  { key: 'baseline', letter: 'C', name: 'Before learning', sub: 'Model only, answers not kept' },
  { key: 'with_feedback', letter: 'E', name: 'With learning', sub: 'Payer memory and “remember”' },
]

function HeadlineTable({ h }) {
  const rows = [
    {
      title: 'Family money found',
      sub: 'Family payments that ended up as family',
      cell: (r) => (
        <><b className="figure">{count(r?.family_money_found?.count)}</b><small>of {count(r?.family_money_found?.of)}</small></>
      ),
    },
    {
      title: 'Income wrongly removed',
      sub: 'Sales that ended up as family',
      cell: (r) => (
        <>
          <b className="figure">{count(r?.income_wrongly_removed?.count)}</b>
          <small>of {count(r?.income_wrongly_removed?.of)}</small>
          {removedSub(r?.income_wrongly_removed) && <small className="lr-split">{removedSub(r.income_wrongly_removed)}</small>}
        </>
      ),
    },
    {
      title: 'Questions per merchant per day',
      sub: 'Averaged over the test period',
      cell: (r) => (
        <><b className="figure">{num(r?.questions_per_merchant_per_day)}</b>{r?.questions_per_merchant_per_day === 0 && <small>never asks</small>}</>
      ),
    },
  ]
  return (
    <table className="lr-headline">
      <caption className="visually-hidden">Headline results on held-out data: always sale, before learning, with learning</caption>
      <thead>
        <tr>
          <td />
          {HEAD_COLS.map((c) => (
            <th scope="col" key={c.key} className={c.letter === 'E' ? 'is-e' : ''}>
              <span>{c.name}</span>
              <small>{c.letter} · {c.sub}</small>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.title}>
            <th scope="row"><span>{row.title}</span><small>{row.sub}</small></th>
            {HEAD_COLS.map((c) => (
              <td key={c.key} className={c.letter === 'E' ? 'is-e' : ''}>{row.cell(h[c.key])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function niceScale(max) {
  if (!(max > 0)) return { top: 1, step: 0.25 }
  const raw = (max * 1.1) / 4
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  return { top: Math.ceil((max * 1.1) / step) * step, step }
}
const tick = (v) => String(Number(v.toFixed(4)))

/** Questions per merchant per day by week, before learning (C) vs with learning (E). Hand-drawn SVG. */
function WeeklyChart({ weekly }) {
  const [active, setActive] = useState(null)
  const series = [
    { key: 'baseline', name: 'Before learning', cls: 'c', values: weekly?.baseline || [] },
    { key: 'with_feedback', name: 'With learning', cls: 'e', values: weekly?.with_feedback || [] },
  ]
  const n = Math.max(0, ...series.map((s) => s.values.length))
  if (!n) return <p className="lr-ink-note">This file has no weekly question counts.</p>
  const labels = Array.from({ length: n }, (_, i) => weekly?.labels?.[i] || `Week ${i + 1}`)
  const vals = series.flatMap((s) => s.values).filter((v) => typeof v === 'number')
  const { top, step } = niceScale(Math.max(0, ...vals))
  const W = 640
  const H = 236
  const L = 44
  const R = 20
  const T = 16
  const B = 38
  const inset = 40
  const pw = W - L - R
  const ph = H - T - B
  const x = (i) => (n === 1 ? L + pw / 2 : L + inset + (i * (pw - 2 * inset)) / (n - 1))
  const y = (v) => T + ph - (v / top) * ph
  const ticks = []
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(v)
  const colW = n === 1 ? pw : (pw - 2 * inset) / (n - 1)
  const tipX = active === null ? 0 : x(active) + (active >= n / 2 ? -210 : 14)
  // put the readout in the empty half of the plot so it never covers the lines
  const activeVals = active === null ? [] : series.map((s) => s.values[active]).filter((v) => typeof v === 'number')
  const high = activeVals.length && Math.max(...activeVals) / top > 0.5
  const tipY = high ? T + ph - 80 : T + 4

  return (
    <figure className="lr-week">
      <figcaption>
        <ul className="lr-legend">
          {series.map((s) => <li key={s.key}><i className={`lr-key ${s.cls}`} aria-hidden="true" />{s.name}</li>)}
        </ul>
      </figcaption>
      <svg className="lr-week-svg" viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Questions per merchant per day by week. Focus a week to read both values.">
        {ticks.map((v) => (
          <g key={v}>
            <line className="grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
            <text className="axis" x={L - 10} y={y(v) + 4} textAnchor="end">{tick(v)}</text>
          </g>
        ))}
        {labels.map((lab, i) => (
          <text key={lab + i} className={`axis ${active === i ? 'is-on' : ''}`} x={x(i)} y={H - 12} textAnchor="middle">{lab}</text>
        ))}
        {active !== null && <line className="cross" x1={x(active)} x2={x(active)} y1={T} y2={T + ph} />}
        {series.map((s) => {
          const pts = s.values.map((v, i) => (typeof v === 'number' ? [x(i), y(v)] : null)).filter(Boolean)
          return (
            <g key={s.key} className={`series ${s.cls}`}>
              <polyline points={pts.map((p) => p.join(',')).join(' ')} />
              {pts.map(([px, py], i) => <circle key={i} cx={px} cy={py} r={active === i ? 6 : 4.5} />)}
            </g>
          )
        })}
        {active !== null && (
          <g className="tip" transform={`translate(${tipX}, ${tipY})`} aria-hidden="true">
            <rect width="196" height="72" rx="10" />
            <text x="14" y="22" className="tip-label">{labels[active]}</text>
            {series.map((s, k) => (
              <g key={s.key} transform={`translate(14, ${42 + k * 20})`}>
                <line className={`tip-key ${s.cls}`} x1="0" x2="14" y1="-4" y2="-4" />
                <text x="22" y="0"><tspan className="tip-val">{num(s.values[active])}</tspan> {s.name.toLowerCase()}</text>
              </g>
            ))}
          </g>
        )}
        {labels.map((lab, i) => (
          <rect key={`hit${i}`} className="hit" x={x(i) - colW / 2} y={T} width={colW} height={ph + 24} tabIndex={0}
            aria-label={`${lab}: ${series.map((s) => `${s.name.toLowerCase()} ${num(s.values[i])}`).join(', ')}`}
            onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(i)} onBlur={() => setActive(null)} />
        ))}
      </svg>
      <details className="lr-week-table" open>
        <summary>Show the numbers</summary>
        <table>
          <thead><tr><td />{labels.map((lab, i) => <th scope="col" key={lab + i}>{lab}</th>)}</tr></thead>
          <tbody>
            {series.map((s) => (
              <tr key={s.key}><th scope="row">{s.name}</th>{labels.map((lab, i) => <td key={lab + i}>{num(s.values[i])}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}

function EvalHeadline({ evaluation }) {
  const e = evaluation.data
  const h = e?.headline
  const split = e?.split || {}
  return (
    <section className="panel ink lr-eval" aria-labelledby="lr-eval-h">
      <h2 id="lr-eval-h">Does it find the family money?</h2>
      <Status state={evaluation} what="the evaluation" hint="Run python -m ml.evaluate to write data/eval/latest.json, then try again." />
      {e && (
        <div className="lr-eval-meta">
          <Badge kind="synthetic">{e.data_label}</Badge>
          <p>
            Held-out test: {count(split.test_merchants)} merchants the model never saw, {split.test_period || 'test period not given'},{' '}
            {count(split.test_transactions)} payments.
          </p>
        </div>
      )}
      {e && !h && (
        <p className="lr-missing">
          This evaluation file has no results to show: it has no headline block. Run <code>python -m ml.evaluate</code> and
          serve <code>data/eval/latest.json</code>.
        </p>
      )}
      {h && <HeadlineTable h={h} />}
      {e && (
        <p className="lr-run">
          Run {e.run_id} · model {e.model_version} · threshold {num(e.threshold)} · {count(split.train_merchants)} training
          merchants, {count(split.test_merchants)} test merchants
        </p>
      )}
    </section>
  )
}

function WeeklyPanel({ e }) {
  return (
    <section className="panel ink lr-eval lr-weekly" aria-labelledby="lr-week-h">
      <h2 id="lr-week-h">Questions per merchant per day, week by week</h2>
      <div className="lr-eval-meta">
        <Badge kind="synthetic">{e.data_label}</Badge>
        <p>Before learning (C) vs with learning (E). Test period {e.split?.test_period || 'not given'}.</p>
      </div>
      <WeeklyChart weekly={e.questions_per_day_by_week} />
    </section>
  )
}

// ---------- 2. what would happen? (POST /classify/preview) ----------

const KIND = {
  FAMILY_INSTRUCTION: { chip: 'family', short: 'Always family', long: 'The merchant told Naanayam. Counted as family without asking, no model score.' },
  MIXED: { chip: 'pending', short: 'Mixed: always asked', long: 'Sometimes family, sometimes a sale, so Naanayam always asks.' },
  CUSTOMER_INSTRUCTION: { chip: 'sale', short: 'Always a customer', long: 'The merchant told Naanayam. Counted as a sale without asking, no model score.' },
  MEMORY: { chip: 'muted', short: 'Payer memory', long: "Past answers nudge the model's score for this person." },
}
const KIND_ORDER = ['FAMILY_INSTRUCTION', 'MIXED', 'CUSTOMER_INSTRUCTION', 'MEMORY']
const SOURCE = {
  SETUP: 'Told when the shop was set up',
  CONFIRMATION: 'Said “remember” while answering',
  ANSWERS: 'Learned from answers',
}
const DECIDED_BY = {
  MERCHANT_CONFIG: "The merchant's instruction",
  PAYER_MEMORY: 'The model, adjusted by past answers for this payer',
  MODEL: 'The model alone',
  RULE: 'A safety rule',
  MERCHANT_CONFIRMED: "The merchant's answer",
}
const APPLIED = {
  MERCHANT_CONFIG: 'Yes: a standing instruction. No model score is used.',
  PAYER_MEMORY: "Yes: payer memory moved the model's score.",
  MODEL: 'No: nothing remembered for this payer yet.',
  RULE: 'A safety rule asks instead of deciding silently.',
}
const OTHER = '__other'

function KindChip({ kind }) {
  return <span className={`chip ${KIND[kind]?.chip || 'muted'}`}>{KIND[kind]?.short || words(kind)}</span>
}

function defaultPayer(learning, wanted) {
  const payers = learning?.payers || []
  const recent = learning?.recent_feedback?.[0]?.payer_name
  return payers.find((p) => p.payer_id === wanted)
    || payers.find((p) => p.kind === 'FAMILY_INSTRUCTION' && p.payer_name === recent)
    || payers.find((p) => p.kind === 'FAMILY_INSTRUCTION' && p.source === 'CONFIRMATION')
    || payers.find((p) => p.kind === 'FAMILY_INSTRUCTION')
    || payers[0]
    || null
}

/** A typed payer: an id as the contract takes it, or a name we can map to exactly one id. */
function resolveTyped(text, payers) {
  const t = text.trim()
  if (!t) return { error: 'Type a payer id (like P10001) or the name of a payer in the list.' }
  if (/^P\d+$/i.test(t)) return { id: t.toUpperCase() }
  const hits = payers.filter((p) => p.payer_name.toLowerCase() === t.toLowerCase())
  if (hits.length === 1) return { id: hits[0].payer_id }
  if (hits.length > 1) return { error: `${count(hits.length)} payers are called ${hits[0].payer_name}. Pick one from the list.` }
  return { error: `No payer called “${t}” in this merchant's memory. Type a payer id (like P10001) for anyone else.` }
}

function outcome(r) {
  const cat = r.suggested_classification === 'FAMILY' ? 'family' : 'sale'
  if (r.action === 'AUTO_CLASSIFY' && r.classification_source === 'MERCHANT_CONFIG') {
    return r.suggested_classification === 'FAMILY'
      ? { tone: 'family', head: 'Next time: family, because you told Naanayam to remember (you can change this)' }
      : { tone: 'sale', head: 'Next time: sale, because you told Naanayam this is a customer (you can change this)' }
  }
  if (r.action === 'AUTO_CLASSIFY') return { tone: cat, head: `Next time: ${cat}, decided without asking.` }
  return { tone: 'ask', head: 'Next time: Naanayam asks first.', sub: `Its guess is ${cat}.` }
}

function PreviewResult({ result, payers, owner }) {
  const r = result.res
  const o = outcome(r)
  const onFile = payers.find((p) => p.payer_id === result.payerId)
  const reasons = r.reasons || []
  return (
    <div className={`lr-result is-${o.tone}`}>
      <p className="lr-result-head">{o.head}</p>
      {o.sub && <p className="lr-result-sub">{o.sub} {owner ? `${owner} taps sale or family.` : ''}</p>}
      <dl className="kv">
        <dt>Decision</dt>
        <dd>
          <span className={`chip ${r.action === 'ASK_MERCHANT' ? 'pending' : r.suggested_classification === 'FAMILY' ? 'family' : 'sale'}`}>
            {r.action === 'ASK_MERCHANT' ? 'Asks' : words(r.suggested_classification)}
          </span>{' '}
          {r.action === 'ASK_MERCHANT' ? `guess: ${words(r.suggested_classification)}` : 'without asking'}
        </dd>
        <dt>Confidence</dt>
        <dd>{r.confidence_kind === 'NONE' || r.confidence === null ? <Badge kind="instruction" /> : confidenceText(r.confidence)}</dd>
        <dt>Decided by</dt>
        <dd>{DECIDED_BY[r.classification_source] || words(r.classification_source)}</dd>
        <dt>Memory used</dt>
        <dd>
          {APPLIED[r.classification_source] || '—'}
          {onFile ? ` On file: ${KIND[onFile.kind]?.short || words(onFile.kind)}.` : ' Nothing on file for this payer.'}
        </dd>
        {reasons.length > 0 && (
          <>
            <dt>Why</dt>
            <dd><ul className="lr-reasons">{reasons.map((t) => <li key={t}>{t}</li>)}</ul></dd>
          </>
        )}
      </dl>
      {r.written === false && <p className="lr-result-foot"><Info aria-hidden="true" /> Preview only. Nothing was saved.</p>}
    </div>
  )
}

function WhatIf({ learning, merchantId, demoDate, owner, pickRequest, wanted, panelRef }) {
  const payers = useMemo(() => learning.data?.payers || [], [learning.data])
  const [choice, setChoice] = useState(null)
  const [typed, setTyped] = useState('')
  const [rupees, setRupees] = useState('2000')
  const [ptype, setPtype] = useState('P2P')
  const [time, setTime] = useState('20:30')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const runRef = useRef(null)

  useEffect(() => {
    if (choice !== null) return
    if (learning.data) setChoice(defaultPayer(learning.data, wanted)?.payer_id || OTHER)
    else if (learning.error) setChoice(OTHER) // no list: the id can still be typed
  }, [learning.data, learning.error, choice, wanted])

  useEffect(() => {
    if (!pickRequest) return
    setChoice(pickRequest.id)
    setResult(null)
    setError(null)
    runRef.current?.focus({ preventScroll: true })
  }, [pickRequest])

  const picked = payers.find((p) => p.payer_id === choice)
  const grouped = KIND_ORDER.map((k) => [k, payers.filter((p) => p.kind === k)]).filter(([, list]) => list.length)
  const changed = (fn) => (ev) => { fn(ev.target.value); setResult(null); setError(null) }

  async function run(ev) {
    ev.preventDefault()
    setError(null)
    setResult(null)
    const target = choice === OTHER || choice === null ? resolveTyped(typed, payers) : { id: choice }
    if (target.error) return setError({ message: target.error, local: true })
    const digits = rupees.replaceAll(',', '').trim()
    if (!/^\d+$/.test(digits) || Number(digits) <= 0) return setError({ message: 'Type the amount in whole rupees, like 2000', local: true })
    if (!/^\d{2}:\d{2}$/.test(time)) return setError({ message: 'Pick a time of day', local: true })
    if (!demoDate) return setError({ message: "The backend's date isn't known yet", hint: 'Wait for the backend, then try again.', local: true })
    setBusy(true)
    try {
      const res = await post('/classify/preview', {
        merchant_id: merchantId,
        payer_id: target.id,
        amount_paise: Number(digits) * 100, // whole rupees typed by the user -> paise for the request
        payment_type: ptype,
        timestamp: `${demoDate}T${time}:00+05:30`,
      })
      setResult({ res, payerId: target.id })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel lr-tool" ref={panelRef} aria-labelledby="lr-tool-h">
      <h2 id="lr-tool-h">What would happen?</h2>
      <p className="lr-tool-lede">Pick a payer and an amount. Naanayam runs the same decision it uses for a real payment, and saves nothing.</p>
      {!learning.data && !learning.error && <LoadState state={learning} what="this merchant's payers" />}
      {!learning.data && learning.error && <p className="note">This merchant's payers didn't load, so type a payer id below.</p>}
      <form className="lr-form" onSubmit={run} noValidate>
        <label className="field">
          <span>Payer</span>
          <select value={choice ?? ''} onChange={changed(setChoice)}>
            {choice === null && <option value="">Loading payers…</option>}
            {grouped.map(([k, list]) => (
              <optgroup key={k} label={KIND[k].short}>
                {list.map((p) => <option key={p.payer_id} value={p.payer_id}>{p.payer_name} · {p.payer_id}</option>)}
              </optgroup>
            ))}
            <option value={OTHER}>Someone else: type a name or id</option>
          </select>
        </label>
        {choice === OTHER && (
          <label className="field">
            <span>Payer id or name</span>
            <input type="text" value={typed} onChange={changed(setTyped)} list="lr-payer-names" placeholder="P10001" autoComplete="off" spellCheck="false" />
            <datalist id="lr-payer-names">
              {payers.map((p) => <option key={p.payer_id} value={p.payer_id}>{p.payer_name}</option>)}
            </datalist>
          </label>
        )}
        {picked && (
          <p className="lr-onfile">
            <KindChip kind={picked.kind} />
            <span>{SOURCE[picked.source] || words(picked.source)}{picked.relation_label ? ` · ${picked.relation_label}` : ''}</span>
          </p>
        )}
        {choice === OTHER && <p className="lr-onfile"><span>An id not in the list is treated as a new payer.</span></p>}
        <div className="lr-form-row">
          <label className="field">
            <span>Amount, whole rupees</span>
            <input type="text" inputMode="numeric" maxLength={9} value={rupees} onChange={changed(setRupees)} aria-describedby="lr-amt-note" />
          </label>
          <label className="field">
            <span>Time, IST</span>
            <input type="time" value={time} onChange={changed(setTime)} />
          </label>
        </div>
        <p className="note" id="lr-amt-note">On {demoDate ? longDate(demoDate) : 'the demo day'}. Rupees only, no paise.</p>
        <div className="field">
          <span id="lr-ptype">Paid to</span>
          <div className="seg lr-seg" role="group" aria-labelledby="lr-ptype">
            <button type="button" aria-pressed={ptype === 'P2P'} onClick={() => { setPtype('P2P'); setResult(null) }}>UPI number (P2P)</button>
            <button type="button" aria-pressed={ptype === 'P2M'} onClick={() => { setPtype('P2M'); setResult(null) }}>Shop QR (P2M)</button>
          </div>
        </div>
        <button type="submit" className="btn primary big lr-run-btn" ref={runRef} disabled={busy || choice === null}>
          <Play aria-hidden="true" /> {busy ? 'Working it out…' : 'See what happens'}
        </button>
      </form>
      <div aria-live="polite">
        {error && <ErrorBanner error={error} hint={error.local ? (error.hint || '') : hintFor(error)} />}
        {result && <PreviewResult result={result} payers={payers} owner={owner} />}
      </div>
    </section>
  )
}

// ---------- 3. this merchant (GET /merchants/{id}/learning) ----------

const PAGE = 10

function Payers({ payers, onTry, owner }) {
  const [filter, setFilter] = useState('all')
  const [all, setAll] = useState(false)
  const sorted = useMemo(
    () => [...payers].sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind)),
    [payers],
  )
  const shown = sorted.filter((p) => filter === 'all' || p.kind === filter)
  const visible = all ? shown : shown.slice(0, PAGE)
  const answers = (p) => (p.confirmed_family || p.confirmed_sale
    ? `${count(p.confirmed_family)} family · ${count(p.confirmed_sale)} sale`
    : 'none yet')

  return (
    <div className="lr-payers">
      <div className="lr-payers-bar">
        <h3>Payers</h3>
        <div className="seg lr-seg" role="group" aria-label="Show payers">
          <button type="button" aria-pressed={filter === 'all'} onClick={() => { setFilter('all'); setAll(false) }}>All {count(payers.length)}</button>
          {KIND_ORDER.map((k) => {
            const n = payers.filter((p) => p.kind === k).length
            return n ? (
              <button key={k} type="button" aria-pressed={filter === k} onClick={() => { setFilter(k); setAll(false) }}>
                {KIND[k].short.split(':')[0]} {count(n)}
              </button>
            ) : null
          })}
        </div>
      </div>
      <dl className="lr-kinds">
        {KIND_ORDER.map((k) => (
          <div key={k}><dt><KindChip kind={k} /></dt><dd>{KIND[k].long}</dd></div>
        ))}
      </dl>
      {!payers.length ? (
        <p className="note lr-empty">No answers yet. When {owner || 'the merchant'} answers a question, the payer shows up here.</p>
      ) : (
        <div className="dtable lr-ptable" role="table" aria-label="Payers Naanayam remembers">
          <div className="tr th" role="row">
            <span role="columnheader">Payer</span><span role="columnheader">What Naanayam does</span>
            <span role="columnheader">How it knows</span><span role="columnheader">Answers</span><span role="columnheader"><span className="visually-hidden">Try</span></span>
          </div>
          {visible.map((p) => (
            <div className="tr" role="row" key={p.payer_id}>
              <span role="cell" className="lr-payer">
                <b>{p.payer_name}</b>
                <small><span className="mono">{p.payer_id}</span>{p.relation_label ? ` · ${p.relation_label}` : ''}</small>
              </span>
              <span role="cell"><KindChip kind={p.kind} /></span>
              <span role="cell" className="lr-how">{SOURCE[p.source] || words(p.source)}</span>
              <span role="cell" className="mono">{answers(p)}</span>
              <span role="cell">
                <button type="button" className="btn lr-try" onClick={() => onTry(p.payer_id)} aria-label={`What if ${p.payer_name} pays next?`}>
                  Try <ArrowRight aria-hidden="true" />
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
      {shown.length > PAGE && (
        <button type="button" className="btn lr-more" onClick={() => setAll((v) => !v)} aria-expanded={all}>
          {all ? 'Show fewer' : `Show all ${count(shown.length)}`}
        </button>
      )}
    </div>
  )
}

function MerchantActivity({ learning, owner }) {
  const l = learning.data
  const q = l?.questions_asked || {}
  return (
    <section className="panel lr-merchant" aria-labelledby="lr-merchant-h">
      <h2 id="lr-merchant-h">What {owner ? `${owner}'s` : 'the'} answers taught it</h2>
      <p className="lr-sub-lede">Counts from this merchant's own records. Only his answers count as lessons; Naanayam's own silent decisions never do.</p>
      <Status state={learning} what="this merchant's learning" />
      {l && (
        <div className="lr-stats">
            <div className="lr-stat lr-stat-q">
              <span className="label">Questions asked</span>
              <ol className="lr-qsteps">
                <li><b className="figure">{count(q.first_7_days)}</b><small>first 7 days</small></li>
                <li><b className="figure">{count(q.last_7_days)}</b><small>last 7 days</small></li>
                <li><b className="figure">{count(q.today)}</b><small>today</small></li>
              </ol>
            </div>
            <div className="lr-stat">
              <span className="label">Answers and corrections</span>
              <b className="figure">{count(l.corrections_total)}</b>
            </div>
            <div className="lr-stat">
              <span className="label">Payers with memory</span>
              <b className="figure">{count(l.payers_with_memory)}</b>
              <small>of {count(l.known_payers)} known payers</small>
            </div>
            <div className="lr-stat">
              <span className="label">Standing instructions</span>
              <b className="figure">{count(l.family_payers_configured)}</b>
              <small>always family · {count(l.customer_payers_configured)} always a customer</small>
            </div>
            <div className="lr-stat">
              <span className="label">Decided without asking today</span>
              <b className="figure">{count(l.auto_classified_today)}</b>
            </div>
        </div>
      )}
    </section>
  )
}

function PayerMemory({ learning, owner, onTry }) {
  const l = learning.data
  return (
    <section className="panel lr-memory" aria-labelledby="lr-memory-h">
      <h2 id="lr-memory-h">Who Naanayam remembers</h2>
      <p className="lr-sub-lede">Each payer with an instruction or an answer, what Naanayam does when they pay, and how it knows. Try one to see the next decision.</p>
      <Status state={learning} what="this merchant's payers" />
      {l && (
        <div className="lr-merchant-split">
          <Payers payers={l.payers || []} onTry={onTry} owner={owner} />
          <div className="lr-recent">
            <h3>Latest answers</h3>
            {(l.recent_feedback || []).length ? (
              <ul className="rows">
                {l.recent_feedback.map((f) => (
                  <li key={f.feedback_id}>
                    <span className={`chip ${f.confirmed_category === 'FAMILY' ? 'family' : 'sale'}`}>{words(f.confirmed_category)}</span>
                    <span className="name"><b>{f.payer_name}</b><small>{longDate(f.at)}, {clockTime(f.at)} IST</small></span>
                    <span className="mono lr-fb">{f.feedback_id.split('-').pop()}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="note">No answers yet.</p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

// ---------- 4. behind the headline (secondary, from GET /evaluation) ----------

const SOURCES = [
  ['MODEL', 'By the model'],
  ['PAYER_MEMORY', 'By payer memory'],
  ['MERCHANT_CONFIG', "By the merchant's instruction"],
]
const PREC_COLS = [['A', 'Always sale'], ['C', 'Before learning'], ['E', 'With learning']]

function SourceCell({ by }) {
  if (!by || !by.of) return <span className="lr-dim">not used</span>
  return (
    <>
      <span className="lr-of"><b>{count(by.correct)}</b> of {count(by.of)} right</span>
      <small>{pct(by.precision)}</small>
    </>
  )
}

function byList(c) {
  const f = c?.config_errors_by_list?.FAMILY
  const k = c?.config_errors_by_list?.CUSTOMER
  if (!isCount(f) || !isCount(k) || (!f.of && !k.of)) return null
  return `family list ${ofText(f)} · customer list ${ofText(k)}`
}

function Precision({ e }) {
  const cols = PREC_COLS.map(([L, name]) => [L, name, cond(e, L)]).filter(([, , c]) => c)
  if (!cols.length) return null
  return (
    <section className="panel lr-sec" aria-labelledby="lr-prec-h">
      <h2 id="lr-prec-h">How often the silent decisions are right</h2>
      <p className="lr-sub-lede">
        Split by who decided, with the instruction mistakes next to it. Always sale is here because a system that finds no family
        money can still look precise.
      </p>
      <Badge kind="synthetic">{e.data_label}</Badge>
      <div className="lr-scroll">
        <table className="lr-table">
          <thead>
            <tr><td />{cols.map(([L, name]) => <th scope="col" key={L} className={L === 'E' ? 'is-e' : ''}><span>{name}</span><small>{L}</small></th>)}</tr>
          </thead>
          <tbody>
            <tr className="is-total">
              <th scope="row">All silent decisions<small>precision, every source together</small></th>
              {cols.map(([L, , c]) => <td key={L} className={L === 'E' ? 'is-e' : ''}><span className="lr-of"><b>{pct(c.precision_auto)}</b></span></td>)}
            </tr>
            {SOURCES.map(([src, label]) => (
              <tr key={src}>
                <th scope="row">{label}</th>
                {cols.map(([L, , c]) => <td key={L} className={L === 'E' ? 'is-e' : ''}><SourceCell by={c.precision_auto_by_source?.[src]} /></td>)}
              </tr>
            ))}
            <tr>
              <th scope="row">Instruction mistakes<small>of decisions made by an instruction</small></th>
              {cols.map(([L, , c]) => <td key={L} className={L === 'E' ? 'is-e' : ''}><OfCell m={c.config_errors} sub={byList(c)} /></td>)}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Conditions({ e }) {
  const cols = ['A', 'B', 'C', 'D', 'E'].map((L) => [L, cond(e, L)]).filter(([, c]) => c)
  if (!cols.length) return null
  const a = cond(e, 'A')
  const rows = [
    ['Family money found', 'of all family payments', (c) => <OfCell m={c.family_recall_final} />],
    ['Income wrongly removed', 'of all sales, ended up as family', (c) => <OfCell m={c.income_wrongly_removed} sub={removedSub(c.income_wrongly_removed)} />],
    ['Family money silently counted as a sale', 'of all family payments', (c) => <OfCell m={c.silent_sale_errors} />],
    ['Sales silently removed as family', 'of all sales', (c) => <OfCell m={c.silent_family_errors} />],
    ['Instruction mistakes', 'of decisions made by an instruction', (c) => <OfCell m={c.config_errors} />],
    ['Questions per merchant per day', 'questions asked in the test', (c) => (
      <><span className="lr-of"><b>{num(c.questions_per_merchant_per_day)}</b></span>{typeof c.questions === 'number' && <small>{count(c.questions)} questions</small>}</>
    )],
    ['Decided without asking', 'share of test payments', (c) => (
      <span className="lr-of"><b>{c.questions === 0 ? 'All' : pct(c.coverage)}</b></span>
    )],
    ['Right when it did not ask', 'precision of silent decisions', (c) => <span className="lr-of"><b>{pct(c.precision_auto)}</b></span>],
    ['Correct by count', 'final labels, after simulated answers', (c) => <span className="lr-of"><b>{pct(c.overall_accuracy)}</b></span>],
  ]
  const cls = (L) => [['A', 'C', 'E'].includes(L) ? 'is-head' : '', L === 'E' ? 'is-e' : ''].join(' ').trim()
  return (
    <section className="panel lr-sec" aria-labelledby="lr-cond-h">
      <h2 id="lr-cond-h">Five ways of deciding, same test</h2>
      <p className="lr-sub-lede">
        Same model, same threshold, same simulated answers. The headline uses A, C and E. Family figures are counts with their
        denominators, because family payments are rare.
      </p>
      <Badge kind="synthetic">{e.data_label}</Badge>
      <div className="lr-scroll">
        <table className="lr-table lr-cond">
          <thead>
            <tr>
              <td />
              {cols.map(([L, c]) => <th scope="col" key={L} className={cls(L)}><span>{L}</span><small>{c.name || L}</small></th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(([title, sub, cell]) => (
              <tr key={title}>
                <th scope="row">{title}<small>{sub}</small></th>
                {cols.map(([L, c]) => <td key={L} className={cls(L)}>{cell(c)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {a && isCount(a.family_recall_final) && (
        <p className="plain-bar lr-plain">
          <Info aria-hidden="true" />
          <span>
            <b>Why the headline counts family money:</b> always sale is {pct(a.overall_accuracy)} correct by count and still finds{' '}
            {ofText(a.family_recall_final)} family payments.
          </span>
        </p>
      )}
      {e.notes?.family_metric_denominators && <p className="note lr-notes">{e.notes.family_metric_denominators}</p>}
      {e.threshold_selection?.objective && (
        <p className="note lr-notes">
          Threshold {num(e.threshold)}, chosen on the calibration set ({e.threshold_selection.set || 'calibration split'}) to{' '}
          {e.threshold_selection.objective}.
        </p>
      )}
    </section>
  )
}

// ---------- page ----------

export default function Learning({ params = {} }) {
  const { merchantId, merchant, demoDate } = useMerchant()
  const learning = useApi(`/merchants/${merchantId}/learning`)
  const evaluation = useApi('/evaluation')
  const [pickRequest, setPickRequest] = useState(null)
  const toolRef = useRef(null)
  const owner = merchant?.owner_name || ''
  const e = evaluation.data

  const onTry = (id) => {
    setPickRequest({ id, at: Date.now() })
    const calm = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    toolRef.current?.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' })
  }

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">07 · {merchant?.display_name || merchantId}</span>
          <h1>Learning.</h1>
          <p className="lede">
            How {owner ? `${owner}'s` : 'the merchant\'s'} answers change what Naanayam does next, and how the model does on merchants it
            never saw.
          </p>
        </div>
        <div className="page-actions">
          {e?.data_label && <Badge kind="synthetic">{e.data_label}</Badge>}
        </div>
      </header>

      <div className="lr-top">
        <EvalHeadline evaluation={evaluation} />
        <WhatIf key={merchantId} learning={learning} merchantId={merchantId} demoDate={demoDate} owner={owner}
          pickRequest={pickRequest} wanted={params.payer} panelRef={toolRef} />
      </div>

      <div className={`lr-row2 ${e?.headline ? '' : 'is-single'}`}>
        {e?.headline && <WeeklyPanel e={e} />}
        <MerchantActivity learning={learning} owner={owner} />
      </div>

      <PayerMemory learning={learning} owner={owner} onTry={onTry} />

      {e?.headline && (
        <>
          <Precision e={e} />
          <Conditions e={e} />
        </>
      )}
    </>
  )
}
