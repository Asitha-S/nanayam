// P1 · Soundbox: the shop's payment speaker, live.
// Every payment that reaches the shop today is announced once, in order, whoever made it (live mode, a phone on
// #/pay, another screen): GET /merchants/{id}/payments is polled, and each transaction_id not seen before gets
// GET /payments/{txn}/announcement, spoken through app/speech.js (the payment, then its question when one is open).
// Live mode: POST /demo/live-payment every 10-20 s (Fast 3-6 s), only after "Start live mode" is pressed on this
// screen (it starts paused every time the screen opens) and never during the judge tour. The voice speaks only while
// this screen is open: leaving it clears the queue.
// The judge tour sends its demo-day payments through this screen (TOUR_EVENT 'send' -> POST /demo/next-payment).
// Also: GET /merchants/{id}/summary (counter), GET /payments/{txn} (what Naanayam did), GET /demo/network (QR code).
// An ASK opens the question card for exactly the announced question_id (VOICE_AND_NOTICE 4.1a), never "the first one".
// Udhari (flag UDHARI, contract section 13): an announcement may carry `tab_offer` (the payer has an open tab). It is
// spoken after the payment and its question, and shown as a second card: Yes -> POST /tabs/{payer_id}/settle.
import '../styles/soundbox.css'
import '../styles/udhari.css'
import qrcode from 'qrcode-generator'
import { Check, CircleHelp, HandCoins, Laptop, Pause, Play, Send, Smartphone, TriangleAlert, Volume2, VolumeX, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { CHANGED, SAME_ORIGIN, USING_FIXTURES, get, post, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { clearSpeech, setMuted, speak, unlockSound, useSpeech } from '../app/speech'
import { stringsFor, useStrings } from '../app/strings'
import { settleFinal, settleHint } from '../app/udhari'
import { uuid } from '../app/uuid'
import PayForm from '../components/PayForm'
import QuestionCard from '../components/QuestionCard'
import { TOUR_EVENT, useTour } from '../tour/Tour'
import { Badge, LoadState, Money, clockTime, confidenceText, count } from '../components/ui'

/** A backend message as one sentence: a full stop is added only when it has none. */
const sentence = (m) => (/[.!?]$/.test(m || '') ? m : `${m}.`)

const CLASS_WORDS = { SALE: 'Sale', FAMILY: 'Family', PENDING: 'Waiting' }
const VOICE_WORDS = { SARVAM: 'Sarvam voice', DEVICE: 'Device voice', TEXT: 'Text only' }
const POLL_MS = 2500
const PAGE = 1000 // the list endpoint's largest page
const SPEEDS = { normal: [10000, 20000], fast: [3000, 6000] }
const SHOWN = 50 // newest records on screen; the Ledger has all of them
const sleep = (ms) => new Promise((r) => { setTimeout(r, ms) })
function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  const d = { promise, done: false }
  d.resolve = () => { d.done = true; resolve() }
  return d
}

/** useApi keeps the previous path's data when a new fetch fails; never show another merchant's data. */
function forMerchant(state, merchantId) {
  return state.data && state.data.merchant_id && state.data.merchant_id !== merchantId ? { ...state, data: null } : state
}

/** The open question for this question_id: today's list first, then all open, then answered (a replay). */
async function findQuestion(merchantId, demoDate, questionId) {
  const paths = [
    demoDate && `/merchants/${merchantId}/questions?status=OPEN&date=${demoDate}`,
    `/merchants/${merchantId}/questions?status=OPEN`,
    `/merchants/${merchantId}/questions?status=ANSWERED${demoDate ? `&date=${demoDate}` : ''}`,
  ].filter(Boolean)
  let firstError = null
  for (const p of paths) {
    try {
      const hit = (await get(p)).items?.find((q) => q.question_id === questionId)
      if (hit) return hit
    } catch (e) {
      firstError = firstError || e
    }
  }
  if (firstError) throw firstError
  return null
}

/**
 * Today's payments, polled every 2.5 s and after every write in this tab. onNew(items) gets the payments that
 * appeared since the screen opened (the ones already there at the first load are the baseline), oldest first.
 * `ready.current.promise` resolves once that baseline is known: this screen's own sends wait for it, so a payment
 * sent right after the screen opens is never mistaken for one that was already there.
 */
function useTodayPayments(merchantId, onNew) {
  const [state, setState] = useState({ merchantId, data: null, error: null })
  const onNewRef = useRef(onNew)
  onNewRef.current = onNew
  const ready = useRef(null)
  if (!ready.current) ready.current = deferred()
  useEffect(() => {
    if (ready.current.done) ready.current = deferred()
    const gate = ready.current
    let alive = true
    let busy = false
    let again = false
    let seen = null // Set of transaction_ids; null until the first load
    let sig = ''
    setState({ merchantId, data: null, error: null })
    async function load() {
      if (busy) { again = true; return }
      busy = true
      try {
        const items = []
        let total = 0
        for (let offset = 0; ; offset += PAGE) {
          const page = await get(`/merchants/${merchantId}/payments?limit=${PAGE}&offset=${offset}`)
          if (!alive) return
          total = page.count
          items.push(...(page.items || []))
          if (!page.items?.length || items.length >= total) break
        }
        const ids = new Set(items.map((p) => p.transaction_id))
        if (seen === null) {
          seen = ids
          gate.resolve()
        } else {
          for (const id of seen) if (!ids.has(id)) seen.delete(id) // gone: the demo was reset, so it can be new again
          const fresh = items.filter((p) => !seen.has(p.transaction_id))
          fresh.forEach((p) => seen.add(p.transaction_id))
          if (fresh.length) onNewRef.current?.(fresh)
        }
        const next = `${total}|${items.map((p) => `${p.transaction_id}:${p.current_classification}:${p.classification_source}`).join(',')}`
        if (next !== sig) {
          sig = next
          setState({ merchantId, data: { merchant_id: merchantId, count: total, items, sig }, error: null })
        } else {
          setState((s) => (s.error ? { ...s, error: null } : s))
        }
      } catch (e) {
        if (alive && e.name !== 'AbortError') setState((s) => ({ ...s, error: e }))
      } finally {
        busy = false
        if (alive && again) { again = false; load() }
      }
    }
    load()
    const timer = setInterval(load, POLL_MS)
    window.addEventListener(CHANGED, load)
    return () => {
      alive = false
      clearInterval(timer)
      window.removeEventListener(CHANGED, load)
    }
  }, [merchantId])
  const out = state.merchantId === merchantId ? state : { data: null, error: null }
  return { ...out, ready }
}

/** "in 12 s", ticking. */
function Countdown({ at }) {
  const [, setTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [at])
  const s = Math.max(0, Math.ceil((at - Date.now()) / 1000))
  return <span className="mono">{s > 0 ? `in ${s} s` : 'now'}</span>
}

/** A QR code as crisp SVG modules (qrcode-generator), ink on card. */
function QrCode({ text }) {
  const { d, n } = useMemo(() => {
    const qr = qrcode(0, 'M')
    qr.addData(text)
    qr.make()
    const size = qr.getModuleCount()
    let path = ''
    for (let r = 0; r < size; r += 1) {
      for (let c = 0; c < size; c += 1) if (qr.isDark(r, c)) path += `M${c} ${r}h1v1h-1z`
    }
    return { d: path, n: size }
  }, [text])
  return (
    <svg className="sb-qr" viewBox={`-3 -3 ${n + 6} ${n + 6}`} shapeRendering="crispEdges" role="img" aria-label={`QR code for ${text}`}>
      <rect x="-3" y="-3" width={n + 6} height={n + 6} className="sb-qr-bg" />
      <path d={d} className="sb-qr-fg" />
    </svg>
  )
}

/** The simulated speaker: an object in CSS, no image, no brand. */
function Device({ state, speaking, amount, sources, line, top }) {
  return (
    <figure className={`sb-device ${speaking ? 'is-speaking' : ''}`} data-state={state} aria-label={`Simulated Soundbox: ${line}`}>
      <div className="sb-device-top">
        <span className="sb-led" aria-hidden="true" />
        <span className="sb-plate">Soundbox · simulated</span>
        <svg className="sb-bars" viewBox="0 0 22 14" aria-hidden="true">
          <rect x="0" y="9" width="4" height="5" rx="1" /><rect x="6" y="6" width="4" height="8" rx="1" />
          <rect x="12" y="3" width="4" height="11" rx="1" /><rect x="18" y="0" width="4" height="14" rx="1" />
        </svg>
      </div>
      <div className="sb-lcd" aria-live="polite">
        <span className="sb-lcd-top"><span>UPI</span><span>{top}</span></span>
        {amount ? <Money amount={amount} sources={sources} className="sb-lcd-amt" key={`${amount}-${top}`} /> : <strong className="sb-lcd-amt is-idle">- - -</strong>}
        <span className="sb-lcd-line">{line}</span>
      </div>
      <div className="sb-grille" aria-hidden="true" />
      <div className="sb-keys" aria-hidden="true"><i /><i /><i /></div>
    </figure>
  )
}

/** Sound on the device: the unlock button until a tap allowed sound, then mute and the voice actually used. */
function SoundControls({ speech }) {
  const label = speech.muted || !speech.unlocked ? 'TEXT' : speech.lastVoice
  return (
    <div className="sb-sound">
      {!speech.unlocked ? (
        <button type="button" className="btn lime sb-unlock" onClick={unlockSound}>
          <Volume2 aria-hidden="true" /> Turn on Soundbox sound
        </button>
      ) : (
        <button type="button" className="btn sb-mute" onClick={() => setMuted(!speech.muted)} aria-pressed={speech.muted}>
          {speech.muted ? <VolumeX aria-hidden="true" /> : <Volume2 aria-hidden="true" />} {speech.muted ? 'Muted' : 'Sound on'}
        </button>
      )}
      <span className={`sb-voice-tag is-${(label || 'none').toLowerCase()}`} role="status" data-voice={label || ''}>
        {label ? VOICE_WORDS[label] : 'Voice: not used yet'}
      </span>
    </div>
  )
}

function sourceText(p) {
  if (p.current_classification === 'PENDING') return 'Waiting for an answer'
  if (p.classification_source === 'MERCHANT_CONFIRMED') return 'Your answer'
  if (p.classification_source === 'MERCHANT_CONFIG') return 'Your instruction'
  if (typeof p.confidence !== 'number') return 'Your instruction'
  return `${confidenceText(p.confidence)} sure${p.classification_source === 'PAYER_MEMORY' ? ', from past answers' : ''}`
}

/** Newest first: by time, then by arrival on this screen. */
function newestFirst(items, order) {
  return [...items].sort((a, b) => (a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1
    : (order.get(b.transaction_id) || 0) - (order.get(a.transaction_id) || 0)))
}

function RecordsPanel({ payments, sorted, arrived }) {
  const items = sorted.slice(0, SHOWN)
  return (
    <section className="panel sb-payments" aria-labelledby="sb-pay-h" data-tour="soundbox-payments">
      <div className="panel-head">
        <h2 id="sb-pay-h" className="sb-h">Today&apos;s records</h2>
        {payments.data && <span className="label">{count(payments.data.count)} · newest first</span>}
      </div>
      {!payments.data && !payments.error && <p className="load-state">Loading today&apos;s payments…</p>}
      {!payments.data && payments.error && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          <span>Couldn&apos;t load today&apos;s payments: {sentence(payments.error.message)} Check the backend; this screen tries again every few seconds.</span></p>
      )}
      {payments.data && !items.length && <p className="note">No payments yet today. Live mode brings one soon, or pay from a phone.</p>}
      {items.length > 0 && (
        <ul className="sb-paylist">
          {items.map((p) => {
            const c = (p.current_classification || '').toLowerCase()
            return (
              <li key={p.transaction_id} className={arrived.has(p.transaction_id) ? 'is-new' : ''}>
                <span className="sb-t">{clockTime(p.timestamp)}</span>
                <span className="sb-who"><b>{p.payer_name}</b><small>{sourceText(p)}{c === 'pending' && <> · <a href="#/questions">Answer</a></>}</small></span>
                <span className={`chip ${['sale', 'family', 'pending'].includes(c) ? c : 'muted'}`}>{CLASS_WORDS[p.current_classification] || p.current_classification}</span>
                <Money amount={p.amount_display} className="sb-amt" />
              </li>
            )
          })}
        </ul>
      )}
      {sorted.length > SHOWN && <p className="note sb-more">Showing the newest {count(SHOWN)} of {count(sorted.length)}. Every one is in the <a href="#/ledger">Ledger</a>.</p>}
    </section>
  )
}

/**
 * The payment's second card when its payer has an open tab (announcement `tab_offer`). Every figure is the backend's
 * display string; the backend decides how much comes off. No just closes the card.
 */
function TabOffer({ item, onYes, onNo }) {
  const o = item.offer
  const t = stringsFor(item.lang)
  const busy = item.state === 'saving'
  const r = item.result
  const final = item.error && settleFinal(item.error)
  return (
    <section className="panel sky sb-tab" aria-label={`${o.payer_name}'s tab`}>
      <div className="sb-tab-copy">
        <h2 className="sb-h">On {o.payer_name}&apos;s tab.</h2>
        <p>{o.payer_name} has goods on credit. Take this payment off the tab? Only the credit book changes: the payment stays where the ledger put it.</p>
        <a className="note" href="#/udhari"><HandCoins aria-hidden="true" /> Open Udhari</a>
      </div>
      <article className="qcard qc sb-tab-card" aria-busy={busy}>
        <div className="qc-head">
          <span className="qcard-avatar" aria-hidden="true">{o.payer_name?.[0]}</span>
          <span className="qc-who">
            <b>{o.payer_name}</b>
            <small>{o.due_display} due on the tab</small>
          </span>
          <span className="figure">{o.payment_display}</span>
        </div>
        <div className="qc-q">
          <p className="qc-text" lang={t.lang}>{o.text}</p>
          <p className="sb-tab-en">
            {o.payer_name} paid <span className="figure">{o.payment_display}</span>. Take it off the tab? (<span className="figure">{o.due_display}</span> due)
          </p>
          {o.settle_display !== o.payment_display && (
            <p className="qcard-en">Only <span className="figure">{o.settle_display}</span> comes off: that is all that is due.</p>
          )}
        </div>
        {item.state !== 'done' && !final && (
          <div className="qcard-answers qc-answers sb-tab-answers" role="group" aria-label="Take it off the tab?">
            <button type="button" onClick={onYes} disabled={busy}>
              <span lang={t.lang}>{t.tabYes}</span><small>{busy ? 'Taking it off…' : 'Take it off the tab'}</small>
            </button>
            <button type="button" onClick={onNo} disabled={busy}>
              <span lang={t.lang}>{t.tabNo}</span><small>No, keep the tab</small>
            </button>
          </div>
        )}
        {item.error && (
          <div className="qc-error">
            <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
              <span><b>{sentence(item.error.message)}</b> {settleHint(item.error)}</span></p>
            {final && <div className="qc-row"><button type="button" className="btn" onClick={onNo}>Close</button></div>}
          </div>
        )}
        {item.state === 'done' && r && (
          <div className="sb-tab-done" role="status">
            <p>
              <Check aria-hidden="true" />
              <span>
                <b>Took <span className="figure">{r.amount_display}</span> off {r.payer_name}&apos;s tab.</b>{' '}
                Due was <span className="figure">{r.due_before_display}</span>, now <b className="figure">{r.due_display}</b>.
              </span>
            </p>
            {r.idempotent_replay && <small>This was already done, so nothing new was written.</small>}
            <small>The payment&apos;s ledger entry is unchanged. Tab entry <span className="mono">{r.tab_entry_id}</span>.</small>
            <button type="button" className="btn" onClick={onNo}>Done</button>
          </div>
        )}
      </article>
    </section>
  )
}

function PhonePanel({ merchantId, onPayHere, payOpen }) {
  // Hosted (SAME_ORIGIN): this page's own public address works from any phone, so no LAN lookup.
  const net = useApi(USING_FIXTURES || SAME_ORIGIN ? null : '/demo/network')
  const ip = net.data?.lan_ips?.[0]
  const pay = `/#/pay?m=${encodeURIComponent(merchantId)}`
  const url = SAME_ORIGIN ? `${window.location.origin}${pay}` : ip ? `http://${ip}:${window.location.port || 5173}${pay}` : null
  return (
    <section className="panel sb-phone" aria-labelledby="sb-phone-h">
      <div className="panel-head">
        <h2 id="sb-phone-h" className="sb-h">Pay from a phone</h2>
        <Smartphone aria-hidden="true" className="sb-phone-icon" />
      </div>
      {url ? (
        <>
          <p className="sb-phone-lede">{SAME_ORIGIN
            ? 'Scan with any phone. The payment lands here and the Soundbox announces it.'
            : 'Scan with any phone on the same Wi-Fi or hotspot as this laptop. The payment lands here and the Soundbox announces it.'}</p>
          <QrCode text={url} />
          <p className="sb-url"><span className="label">Or type</span><span className="mono">{url}</span></p>
        </>
      ) : net.error ? (
        <p className="note">Couldn&apos;t get this laptop&apos;s network address ({net.error.message}). Use Pay from this screen instead.</p>
      ) : net.data || USING_FIXTURES ? (
        <p className="sb-phone-off">Phones can&apos;t reach this laptop right now: it isn&apos;t on a Wi-Fi or hotspot network. Connect it, then reload this page.</p>
      ) : <LoadState state={net} what="this laptop's address" />}
      <button type="button" className="btn sb-payhere" onClick={onPayHere} aria-expanded={payOpen} aria-controls="sb-drawer">
        <Laptop aria-hidden="true" /> Pay from this screen
      </button>
    </section>
  )
}

export default function Soundbox() {
  const { merchantId, merchant, language, demoDate, health } = useMerchant()
  const t = useStrings()
  const tour = useTour()
  const speech = useSpeech()
  const lang = language === 'te' ? 'te' : 'ta'
  const owner = merchant?.owner_name || merchantId
  const toolsOff = health?.demo_tools === false

  const gen = useRef(0) // bumps on merchant switch: late answers for the old merchant are dropped
  const ctx = useRef({})
  ctx.current = { merchantId, demoDate, lang }
  const chain = useRef(Promise.resolve())
  const responses = useRef(new Map()) // txn -> POST response made on this screen (reasons live only there)
  const anns = useRef(new Map()) // txn -> announcement + who/how much
  const arrived = useRef(new Map()) // txn -> arrival order on this screen
  const askRef = useRef(null)
  const voiced = useRef(0) // announcements queued or being spoken
  const [latestTxn, setLatestTxn] = useState(null)
  const [saidTxn, setSaidTxn] = useState(null)
  const [backlog, setBacklog] = useState(0)
  const [annError, setAnnError] = useState(null)
  const [ask, setAsk] = useState(null) // { txn, questionId, question, error, loaded }
  const [detail, setDetail] = useState(null) // GET /payments/{latest}
  const [payOpen, setPayOpen] = useState(false)
  const [tabOffers, setTabOffers] = useState([]) // [{ txn, offer, lang, crid, state, result, error }] (udhari)

  const patchTab = (txn, patch) => setTabOffers((list) => list.map((x) => (x.txn === txn ? { ...x, ...patch } : x)))
  const dropTab = (txn) => setTabOffers((list) => list.filter((x) => x.txn !== txn))
  function offerTab(txn, offer, l) {
    setTabOffers((list) => (list.some((x) => x.txn === txn) ? list : [...list, { txn, offer, lang: l, crid: uuid(), state: 'ask' }]))
  }
  /** Yes on a tab offer: the backend takes min(payment, due) off the tab; the same card re-sends the same request. */
  async function settleTab(item) {
    const g = gen.current
    patchTab(item.txn, { state: 'saving', error: null })
    try {
      const res = await post(`/tabs/${encodeURIComponent(item.offer.payer_id)}/settle`, {
        client_request_id: item.crid,
        merchant_id: ctx.current.merchantId,
        transaction_id: item.txn,
      })
      if (g === gen.current) patchTab(item.txn, { state: 'done', result: res })
    } catch (e) {
      if (g === gen.current) patchTab(item.txn, { state: 'error', error: e })
    }
  }

  async function openQuestion(txn, questionId, g) {
    if (askRef.current?.questionId === questionId) return
    const entry = { txn, questionId, question: null, error: null, loaded: false }
    askRef.current = entry
    setAsk(entry)
    let question = null
    let error = null
    try {
      question = await findQuestion(ctx.current.merchantId, ctx.current.demoDate, questionId)
    } catch (e) {
      error = e
    }
    if (g !== gen.current || askRef.current?.questionId !== questionId) return
    const next = { ...askRef.current, question, error, loaded: true }
    askRef.current = next
    setAsk(next)
  }

  async function announce(p, g) {
    const { merchantId: m, lang: l } = ctx.current
    let a = null
    for (let attempt = 0; attempt < 2 && !a; attempt += 1) {
      try {
        a = await get(`/payments/${encodeURIComponent(p.transaction_id)}/announcement?language=${l}`)
      } catch (e) {
        if (attempt === 1) {
          if (g === gen.current) setAnnError({ txn: p.transaction_id, name: p.payer_name, error: e })
          return
        }
        await sleep(700)
      }
    }
    if (g !== gen.current) return
    anns.current.set(p.transaction_id, { ...a, payer_name: p.payer_name, amount_display: p.amount_display, lang: l })
    setSaidTxn(p.transaction_id)
    setAnnError(null)
    if (a.question) openQuestion(p.transaction_id, a.question.question_id, g)
    const items = [{ text: a.text, textEn: a.text_en, lang: l, merchantId: m, txn: p.transaction_id, part: 'payment' }]
    if (a.question) items.push({ text: a.question.text, textEn: a.question.text_en, lang: l, merchantId: m, txn: p.transaction_id, part: 'question' })
    if (a.tab_offer) {
      offerTab(p.transaction_id, a.tab_offer, l)
      items.push({ text: a.tab_offer.text, textEn: a.tab_offer.text_en, lang: l, merchantId: m, txn: p.transaction_id, part: 'tab' })
    }
    // a burst (the tour's thirteen payments): every payment shows on screen, but the voice never falls more than one
    // behind; a payment that asks a question is always spoken
    if (!a.question && voiced.current >= 2) return
    voiced.current += 1
    setBacklog((n) => n + 1)
    speak(items).finally(() => {
      voiced.current = Math.max(0, voiced.current - 1)
      if (g === gen.current) setBacklog((n) => Math.max(0, n - 1))
    })
  }

  const payments = useTodayPayments(merchantId, (fresh) => {
    const g = gen.current
    fresh.forEach((p) => arrived.current.set(p.transaction_id, arrived.current.size + 1))
    setLatestTxn(fresh[fresh.length - 1].transaction_id)
    for (const p of fresh) chain.current = chain.current.then(() => announce(p, g)).catch(() => {})
  })
  const summary = forMerchant(useApi(`/merchants/${merchantId}/summary?include_sources=true`), merchantId)
  const sig = payments.data?.sig
  const reloadSummary = summary.reload
  useEffect(() => { if (sig) reloadSummary() }, [sig, reloadSummary])

  // switching merchant clears the cards, the voice queue and in-flight answers (VOICE_AND_NOTICE 4.1a rule 4)
  useEffect(() => {
    gen.current += 1
    clearSpeech()
    chain.current = Promise.resolve()
    responses.current = new Map()
    anns.current = new Map()
    arrived.current = new Map()
    askRef.current = null
    setLatestTxn(null); setSaidTxn(null); setBacklog(0); setAnnError(null); setAsk(null); setDetail(null)
    setPayOpen(false)
    setTabOffers([])
  }, [merchantId])
  useEffect(() => () => { gen.current += 1; clearSpeech() }, []) // leaving the screen: nothing more is said

  // ---------- live mode ----------
  const [liveOn, setLiveOn] = useState(false) // starts paused every time the screen opens
  const [speed, setSpeed] = useState('normal')
  const [kick, setKick] = useState(0)
  const [nextAt, setNextAt] = useState(null)
  const [liveBusy, setLiveBusy] = useState(false)
  const [liveError, setLiveError] = useState(null)
  const liveBlocked = toolsOff || USING_FIXTURES
  const tourOn = Boolean(tour?.active)
  const running = liveOn && !tourOn && !liveBlocked

  /** Wait (a few seconds at most) until the screen knows which payments were already there. */
  const baseline = () => Promise.race([payments.ready.current.promise, sleep(4000)])

  async function sendLive() {
    const g = gen.current
    setLiveBusy(true)
    try {
      await baseline()
      const res = await post('/demo/live-payment', { merchant_id: ctx.current.merchantId })
      if (g !== gen.current) return null
      responses.current.set(res.transaction_id, res)
      setLiveError(null)
      return res
    } catch (e) {
      if (g === gen.current) {
        setLiveError(e)
        if (e.code === 'NOT_FOUND') setLiveOn(false)
      }
      return null
    } finally {
      if (g === gen.current) setLiveBusy(false)
    }
  }
  const sendLiveRef = useRef(sendLive)
  sendLiveRef.current = sendLive

  useEffect(() => {
    if (!running) { setNextAt(null); return undefined }
    let alive = true
    let timer = null
    const plan = () => {
      const [lo, hi] = SPEEDS[speed]
      const ms = Math.round(lo + Math.random() * (hi - lo))
      setNextAt(Date.now() + ms)
      timer = setTimeout(async () => {
        if (!alive) return
        setNextAt(null)
        await sendLiveRef.current()
        if (alive) plan()
      }, ms)
    }
    plan()
    return () => { alive = false; clearTimeout(timer) }
  }, [running, speed, merchantId, kick])

  async function sendNow() {
    await sendLive()
    setKick((k) => k + 1) // the next live payment comes a full interval after this one
  }

  // ---------- the judge tour's demo-day payments ----------
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const reqId = useRef(0)
  useEffect(() => { reqId.current += 1; setError(null); setSending(false) }, [merchantId])

  async function send() {
    const id = ++reqId.current
    setSending(true)
    setError(null)
    try {
      await baseline()
      const res = await post('/demo/next-payment', { merchant_id: merchantId })
      if (id !== reqId.current) return
      responses.current.set(res.transaction_id, res)
      if (res.action === 'ASK_MERCHANT' && res.question_id) await openQuestion(res.transaction_id, res.question_id, gen.current)
      return res
    } catch (e) {
      if (id === reqId.current) setError(e)
      return null
    } finally {
      if (id === reqId.current) setSending(false)
    }
  }

  // Judge tour: "send N payments" presses this screen's own Send, so the device, the announcement and the
  // question card behave exactly as they do for a presenter.
  const sendRef = useRef(send)
  sendRef.current = send
  useEffect(() => {
    const on = async (e) => {
      if (e.detail?.action !== 'send') return
      e.detail.ack?.()
      for (let i = 0; i < (e.detail.count || 1); i += 1) {
        const res = await sendRef.current()
        if (!res) return e.detail.fail?.(new Error('A payment could not be sent (see the Soundbox screen)'))
      }
      return e.detail.done?.()
    }
    window.addEventListener(TOUR_EVENT, on)
    return () => window.removeEventListener(TOUR_EVENT, on)
  }, [])

  // ---------- what the screen shows ----------
  const items = payments.data?.items || []
  const sorted = useMemo(() => newestFirst(items, arrived.current), [items])
  const latest = (latestTxn && items.find((p) => p.transaction_id === latestTxn)) || null
  const shown = latest || sorted[0] || null

  // what Naanayam did with the latest payment (GET /payments/{txn}; reasons only for payments sent from here)
  const latestSig = latest ? `${latest.transaction_id}:${latest.current_classification}:${latest.classification_source}` : ''
  useEffect(() => {
    if (!latest) return undefined
    let alive = true
    const g = gen.current
    get(`/payments/${encodeURIComponent(latest.transaction_id)}`)
      .then((d) => { if (alive && g === gen.current) setDetail(d) })
      .catch(() => { /* the verdict falls back to the list item */ })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestSig])

  let devState = 'idle'
  let devLine = 'Ready'
  let devTop = 'Ready'
  let devSources
  if (shown) {
    const c = shown.current_classification
    devState = c === 'PENDING' ? 'ask' : (c || '').toLowerCase()
    devTop = latest ? clockTime(shown.timestamp) : `Last ${clockTime(shown.timestamp)}`
    devLine = c === 'PENDING' ? 'Received · asking'
      : `${shown.classification_source === 'MERCHANT_CONFIRMED' ? 'Answered' : 'Received'} · ${CLASS_WORDS[c] || c}`
    const d = detail?.transaction_id === shown.transaction_id ? detail : null
    devSources = d?.classification_history?.map((h) => h.ledger_entry_id) || (responses.current.get(shown.transaction_id)?.ledger_entry_id ? [responses.current.get(shown.transaction_id).ledger_entry_id] : undefined)
  }
  if (backlog > 1) devLine = `${devLine} · ${count(backlog - 1)} more to say`

  // the words: the item being spoken, else the newest announcement
  const cur = speech.current
  const sayTxn = cur?.txn && anns.current.has(cur.txn) ? cur.txn : saidTxn
  const said = sayTxn ? anns.current.get(sayTxn) : null
  const part = cur?.txn === sayTxn ? cur.part : null

  const s = summary.data
  const waiting = s?.pending?.count

  let verdict = null
  if (latest) {
    const res = responses.current.get(latest.transaction_id)
    const d = detail?.transaction_id === latest.transaction_id ? detail : null
    const ip = d?.initial_prediction
    const action = res?.action || ip?.action
    const conf = res ? res.confidence : ip ? ip.confidence : latest.confidence
    const suggested = res?.suggested_classification || ip?.suggested_classification
    const c = latest.current_classification
    const ledgerId = d?.classification_history?.[d.classification_history.length - 1]?.ledger_entry_id || res?.ledger_entry_id
    verdict = { res, action, conf, suggested, c, ledgerId, asked: action === 'ASK_MERCHANT', answered: latest.classification_source === 'MERCHANT_CONFIRMED' }
  }

  let errorHint = null
  if (error) {
    if (error.code === 'INVALID_STATE') errorHint = <>All of the demo day&apos;s payments have been sent for {owner}. Reset the demo from the <a href="#/demo">demo panel</a> to run the day again.</>
    else if (error.code === 'NOT_FOUND' && toolsOff) errorHint = <>Demo tools are off on this backend (ENABLE_DEMO_TOOLS=false). Turn them on and restart it.</>
    else if (error.code === 'NOT_FOUND') errorHint = <>There is no demo day for {owner}, or demo tools are off on this backend.</>
    else if (error.code === 'UNREACHABLE') errorHint = <>Start the backend, then try again. A payment is never counted twice.</>
    else errorHint = <>Try again. The same payment is never counted twice.</>
  }
  const errorWords = error && ['INVALID_STATE', 'NOT_FOUND'].includes(error.code) ? null : error?.message

  let liveStatus
  if (liveBlocked) liveStatus = USING_FIXTURES ? 'Live mode needs the live backend.' : 'Live mode needs demo tools on the backend.'
  else if (tourOn) liveStatus = 'Paused while the judge tour runs.'
  else if (!liveOn) liveStatus = 'Live mode is off. Payments from phones still arrive and are announced.'
  else if (liveBusy || !nextAt) liveStatus = 'A payment is arriving…'
  else liveStatus = <>Next payment <Countdown at={nextAt} />.</>

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">02 · {merchant?.display_name || merchantId}</span>
          <h1>Soundbox.</h1>
          <p className="lede">{owner}&apos;s payment speaker. Every UPI payment to the shop is announced as it arrives, from a customer&apos;s phone or from live mode. Naanayam sorts it silently, or asks {owner} one question in {t.languageName}.</p>
        </div>
      </header>

      {toolsOff && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          <span>Demo tools are off on this backend (ENABLE_DEMO_TOOLS=false), so live mode and phone payments can&apos;t run. Turn them on and restart the backend.</span></p>
      )}

      <div className="sb-layout">
        <div className="sb-main">
          <section className="panel sb-stage" aria-label="Soundbox" data-tour="soundbox-stage">
            <div className="sb-device-col">
              <Device state={devState} speaking={speech.speaking} amount={shown?.amount_display} sources={devSources} line={devLine} top={devTop} />
              <SoundControls speech={speech} />
            </div>

            <div className="sb-console">
              <div className={`sb-live ${running ? 'is-on' : ''}`}>
                <div className="sb-live-row">
                  <span className="sb-live-pill" aria-hidden="true"><i />{running ? 'Live' : 'Paused'}</span>
                  <p className="sb-live-status">{liveStatus}</p>
                </div>
                <div className="sb-live-row sb-live-actions">
                  {liveOn ? (
                    <button type="button" className="btn" onClick={() => setLiveOn(false)} disabled={liveBlocked || tourOn}>
                      <Pause aria-hidden="true" /> Pause
                    </button>
                  ) : (
                    <button type="button" className="btn lime sb-start" onClick={() => setLiveOn(true)} disabled={liveBlocked || tourOn}>
                      <Play aria-hidden="true" /> Start live mode · a payment every {speed === 'fast' ? '3–6' : '10–20'} s
                    </button>
                  )}
                  <div className="seg" role="group" aria-label="Live mode speed">
                    <button type="button" aria-pressed={speed === 'normal'} onClick={() => setSpeed('normal')}>Normal</button>
                    <button type="button" aria-pressed={speed === 'fast'} onClick={() => setSpeed('fast')}>Fast</button>
                  </div>
                  <button type="button" className="btn ink" onClick={sendNow} disabled={liveBlocked || tourOn || liveBusy} aria-busy={liveBusy}>
                    <Send aria-hidden="true" /> Send a payment now
                  </button>
                </div>
                <p className="note">Live mode sends {speed === 'fast' ? 'a payment every 3 to 6 seconds' : 'a payment every 10 to 20 seconds'} from {owner}&apos;s own customers, through the same path as any payment. It stops when you leave this screen.</p>
                {liveError && (
                  <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
                    <span><b>{sentence(liveError.message)}</b> {liveError.code === 'UNREACHABLE' ? 'Start the backend; live mode keeps trying.' : liveError.code === 'NOT_FOUND' ? 'Live mode is paused: demo tools are off on this backend.' : 'Live mode tries again with the next payment.'}</span></p>
                )}
              </div>

              <dl className="sb-count" aria-label="Today so far">
                <div><dt>Payments today</dt><dd className="figure">{payments.data ? count(payments.data.count) : '…'}</dd></div>
                <div><dt>Business sales</dt><dd>{s ? <Money amount={s.business_sales} sources={s.sources?.business_sales} /> : '…'}</dd></div>
                <div className={waiting > 0 ? 'is-waiting' : ''}>
                  <dt>Waiting for an answer</dt>
                  <dd><span className="figure">{typeof waiting === 'number' ? count(waiting) : '…'}</span>{waiting > 0 && <a className="sb-count-link" href="#/questions">Answer</a>}</dd>
                </div>
              </dl>
              {summary.error && !s && <p className="note">Couldn&apos;t load today&apos;s totals: {sentence(summary.error.message)}</p>}

              {error && (
                <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
                  <span>{errorWords && <b>{sentence(errorWords)} </b>}{errorHint}</span></p>
              )}
              {sending && <p className="note" role="status">Sending the demo day&apos;s next payment…</p>}

              {said ? (
                <div className={`sb-said ${speech.speaking && cur?.txn === sayTxn ? 'is-live' : ''}`}>
                  <span className="label">{cur?.txn === sayTxn ? 'The Soundbox is saying' : 'The Soundbox said'} · {said.payer_name}</span>
                  <p className={`sb-said-text ${part === 'payment' ? 'is-now' : ''}`} lang={said.lang}>{said.text}</p>
                  <p className="sb-said-en">{said.text_en}</p>
                  {said.question && (
                    <>
                      <p className={`sb-said-text sb-said-q ${part === 'question' ? 'is-now' : ''}`} lang={said.lang}>{said.question.text}</p>
                      <p className="sb-said-en">{said.question.text_en}</p>
                    </>
                  )}
                  {said.tab_offer && (
                    <>
                      <p className={`sb-said-text sb-said-q ${part === 'tab' ? 'is-now' : ''}`} lang={said.lang}>{said.tab_offer.text}</p>
                      <p className="sb-said-en">{said.tab_offer.text_en}</p>
                    </>
                  )}
                </div>
              ) : (
                <div className="sb-idle">
                  <Volume2 aria-hidden="true" />
                  <p>Waiting for the next payment. The Soundbox says each one out loud in {t.languageName}{speech.unlocked ? '' : ' once its sound is turned on'}; until then the words appear here.</p>
                </div>
              )}
              {annError && (
                <p className="note" role="status">Couldn&apos;t load what to say for {annError.name}&apos;s payment ({annError.error.message}). It is still in today&apos;s records.</p>
              )}

              {verdict && (
                <div className={`sb-verdict ${verdict.asked && verdict.c === 'PENDING' ? 'is-ask' : ''}`}>
                  <span className="label">What Naanayam did · {latest.payer_name}</span>
                  <p className="sb-verdict-line">
                    {verdict.asked && verdict.c === 'PENDING' ? (
                      <><span className="chip pending">Asked</span> It asks {owner} before deciding. The payment waits, out of sales, until {owner} answers.</>
                    ) : verdict.answered ? (
                      <><span className={`chip ${verdict.c === 'FAMILY' ? 'family' : 'sale'}`}>{CLASS_WORDS[verdict.c] || verdict.c}</span> {owner} answered.</>
                    ) : (
                      <><span className={`chip ${verdict.c === 'FAMILY' ? 'family' : 'sale'}`}>{CLASS_WORDS[verdict.c] || verdict.c}</span> Sorted silently.</>
                    )}
                    {typeof verdict.conf === 'number'
                      ? <b className="sb-conf">{confidenceText(verdict.conf)} sure{verdict.asked && verdict.suggested ? ` it's ${verdict.suggested === 'FAMILY' ? 'family' : 'a sale'}` : ''}</b>
                      : verdict.conf === null ? <Badge kind="instruction" /> : null}
                  </p>
                  {verdict.res?.reasons?.length > 0 && (
                    <ul className="sb-reasons" aria-label="Why">
                      {verdict.res.reasons.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  )}
                  {verdict.ledgerId && (
                    <p className="note">Ledger entry <a className="mono" href={`#/ledger?ids=${encodeURIComponent(verdict.ledgerId)}`}>{verdict.ledgerId}</a></p>
                  )}
                </div>
              )}
            </div>
          </section>

          {ask && (
            <section className="panel signal sb-ask" aria-label="The question" data-tour="soundbox-question">
              <div className="sb-ask-copy">
                <h2 className="sb-h">One question for {owner}.</h2>
                <p>On {owner}&apos;s phone and the Soundbox, in {t.languageName}. Two big answers; nothing is guessed.</p>
                <a className="note sb-ask-link" href={`#/questions?q=${encodeURIComponent(ask.questionId)}`}>
                  <CircleHelp aria-hidden="true" /> Also on the Questions screen
                </a>
              </div>
              {ask.question ? (
                <QuestionCard key={ask.question.question_id} question={ask.question} merchantId={merchantId} language={language}
                  demoDate={demoDate} hideAudio />
              ) : ask.loaded ? (
                <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
                  <span>
                    {ask.error ? `Couldn't load question ${ask.questionId}: ${sentence(ask.error.message)}` : `Question ${ask.questionId} isn't in the question list.`}{' '}
                    Open it from the <a href={`#/questions?q=${encodeURIComponent(ask.questionId)}`}>Questions screen</a>.
                  </span>
                </p>
              ) : <p className="load-state">Loading the question…</p>}
            </section>
          )}

          {[...tabOffers].reverse().map((item) => (
            <TabOffer key={item.txn} item={item} onYes={() => settleTab(item)} onNo={() => dropTab(item.txn)} />
          ))}

          <RecordsPanel payments={payments} sorted={sorted} arrived={arrived.current} />
        </div>

        <aside className="sb-side">
          <PhonePanel merchantId={merchantId} payOpen={payOpen} onPayHere={() => setPayOpen(true)} />
        </aside>
      </div>

      {payOpen && <PayDrawer merchantId={merchantId} shop={merchant?.display_name || merchantId}
        onClose={() => setPayOpen(false)} onPaid={(res) => responses.current.set(res.transaction_id, res)} />}
    </>
  )
}

/**
 * "Pay from this screen": the payment form in a side panel over the page (a portal on <body>, so no ancestor can
 * move or clip it). Esc, the close button or a click on the backdrop closes it; Tab stays inside while it is open.
 */
function PayDrawer({ merchantId, shop, onClose, onPaid }) {
  const ref = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const opener = document.activeElement
    ref.current?.focus()
    const on = (e) => {
      if (e.key === 'Escape') { closeRef.current(); return }
      if (e.key !== 'Tab' || !ref.current) return
      const f = [...ref.current.querySelectorAll('button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])')]
        .filter((el) => !el.disabled && el.offsetParent !== null)
      if (!f.length) return
      const first = f[0]
      const last = f[f.length - 1]
      if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', on)
    return () => {
      window.removeEventListener('keydown', on)
      if (opener && opener.focus) opener.focus()
    }
  }, [])
  return createPortal(
    <>
      <div className="sb-backdrop" aria-hidden="true" onClick={() => closeRef.current()} />
      <aside className="sb-drawer" id="sb-drawer" role="dialog" aria-modal="true" aria-labelledby="sb-drawer-h" tabIndex={-1} ref={ref}>
        <div className="sb-drawer-head">
          <h2 id="sb-drawer-h" className="sb-h">Pay from this screen</h2>
          <button type="button" className="sb-drawer-x" onClick={() => closeRef.current()} aria-label="Close the payment panel"><X aria-hidden="true" /></button>
        </div>
        <p className="note">Pay {shop} the way a customer would. The Soundbox announces it like any other payment.</p>
        <PayForm merchantId={merchantId} variant="panel" onPaid={onPaid} />
      </aside>
    </>,
    document.body,
  )
}
