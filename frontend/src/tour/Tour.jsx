// Judge tour: a small step engine. One highlighted element at a time, a short caption, Back / Next.
// Steps live in steps.jsx; screens mark what can be highlighted with data-tour="name". Step actions run only when
// moving forward (Back never re-sends payments); a screen-owned action (sending payments) goes through TOUR_EVENT
// so the screen behaves exactly as it does for a presenter.
import { ArrowLeft, ArrowRight, Play, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react'
import demoDay from '../../../data/demo/M001_demo_day.json'
import { get, post } from '../api'
import { useMerchant } from '../app/merchant'
import { go as goTo } from '../app/route'
import { talkWords } from '../components/talk/strings'
import '../styles/tour.css'
import { STEPS } from './steps'

export const TOUR_EVENT = 'naanayam:tour'
const TourContext = createContext(null)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function findTarget(target) {
  for (const name of [].concat(target || [])) {
    const el = document.querySelector(`[data-tour="${name}"]`)
    if (el) return el
  }
  return null
}

async function waitFor(fn, timeoutMs, everyMs = 120) {
  const end = Date.now() + timeoutMs
  for (;;) {
    const v = fn()
    if (v) return v
    if (Date.now() > end) return null
    await sleep(everyMs)
  }
}

/** Ask the open screen to do something (e.g. { action: 'send', count: 13 }); resolves when it reports done. */
function askScreen(detail, { ackMs = 2500, doneMs = 120000 } = {}) {
  return new Promise((resolve, reject) => {
    let acked = false
    const ackTimer = setTimeout(() => { if (!acked) reject(new Error('That screen is not open, so it could not run this step')) }, ackMs)
    const doneTimer = setTimeout(() => reject(new Error('The screen took too long')), doneMs)
    window.dispatchEvent(new CustomEvent(TOUR_EVENT, {
      detail: {
        ...detail,
        ack: () => { acked = true; clearTimeout(ackTimer) },
        done: (v) => { clearTimeout(doneTimer); resolve(v) },
        fail: (e) => { clearTimeout(doneTimer); reject(e) },
      },
    }))
  })
}

function lastNoticeId() {
  try {
    const ids = Object.keys(window.sessionStorage).filter((k) => k.startsWith('naanayam.notice.')).map((k) => k.slice(16))
    return ids[ids.length - 1] || null
  } catch {
    return null
  }
}

/** Highlight box + caption card. */
function Overlay({ step, index, total, busy, error, onNext, onBack, onExit, onRetry }) {
  const [rect, setRect] = useState(null)
  const [missing, setMissing] = useState(false)
  const [cardPos, setCardPos] = useState(null)
  const cardRef = useRef(null)
  const nextRef = useRef(null)

  // find the target (it may appear only after data loads), bring it into view, then follow it as the page moves
  useEffect(() => {
    setRect(null)
    setMissing(false)
    if (!step.target || busy) return undefined
    let alive = true
    let el = null
    let timer = null
    ;(async () => {
      el = await waitFor(() => findTarget(step.target), 15000)
      if (!alive) return
      if (!el) { setMissing(true); return }
      const top = el.getBoundingClientRect().top + window.scrollY - 150
      window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
      const measure = () => {
        const cur = findTarget(step.target) || el
        const r = cur.getBoundingClientRect()
        setRect((p) => (p && p.top === r.top && p.left === r.left && p.width === r.width && p.height === r.height ? p
          : { top: r.top, left: r.left, width: r.width, height: r.height }))
      }
      measure()
      timer = setInterval(measure, 100)
    })()
    return () => { alive = false; if (timer) clearInterval(timer) }
  }, [step, busy])

  // place the card next to the highlight: below, else above, else in the corner
  useLayoutEffect(() => {
    const card = cardRef.current
    if (!card) return
    const vw = window.innerWidth
    const vh = window.innerHeight
    const w = card.offsetWidth
    const h = card.offsetHeight
    if (!rect) { setCardPos(null); return }
    const pad = 14
    const left = Math.min(Math.max(16, rect.left), vw - w - 16)
    if (rect.top + rect.height + pad + h < vh - 16) setCardPos({ top: rect.top + rect.height + pad, left })
    else if (rect.top - pad - h > 16) setCardPos({ top: rect.top - pad - h, left })
    else setCardPos({ top: vh - h - 20, left: vw - w - 20 })
  }, [rect, step, busy, error])

  useEffect(() => { if (!busy) nextRef.current?.focus({ preventScroll: true }) }, [index, busy])

  const pad = 8
  const last = index === total - 1
  return (
    <>
      {rect && !busy ? (
        <div className="tour-hole" aria-hidden="true"
          style={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }} />
      ) : <div className="tour-dim" aria-hidden="true" />}
      <section ref={cardRef} className={`tour-card ${cardPos ? '' : 'is-centered'}`} role="dialog" aria-modal="false"
        aria-labelledby="tour-title" style={cardPos ? { top: cardPos.top, left: cardPos.left } : undefined}>
        <div className="tour-head">
          <span className="label">Judge tour · {index === 0 ? 'start' : last ? 'end' : `${index} of ${total - 2}`}</span>
          <button type="button" className="tour-x" onClick={onExit} aria-label="Close the tour"><X aria-hidden="true" /></button>
        </div>
        <h2 id="tour-title">{step.title}</h2>
        <p className="tour-text">{step.text}</p>
        {busy && <p className="tour-busy" role="status"><i /><i /><i /> Working on it…</p>}
        {missing && !busy && <p className="tour-note">This part isn&apos;t on screen right now. Press Next to go on.</p>}
        {error && !busy && (
          <p className="tour-error" role="alert">{error.message}. <button type="button" className="linkish" onClick={onRetry}>Try again</button></p>
        )}
        <div className="tour-actions">
          <button type="button" className="btn" onClick={onBack} disabled={busy || index === 0}><ArrowLeft aria-hidden="true" /> Back</button>
          <button type="button" className="btn ink" ref={nextRef} onClick={onNext} disabled={busy}>
            {step.next || (last ? 'Finish' : 'Next')} {!last && <ArrowRight aria-hidden="true" />}
          </button>
        </div>
      </section>
    </>
  )
}

export function TourProvider({ children }) {
  const { setMerchantId, demoDate } = useMerchant()
  const [index, setIndex] = useState(-1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const routes = useRef({})
  const counter = useRef(0)
  const dateRef = useRef(demoDate)
  dateRef.current = demoDate

  const helpers = useRef({
    get,
    post,
    nonce: () => `${Date.now().toString(36)}${(counter.current += 1)}`,
    lastNotice: lastNoticeId,
    async go(path) {
      goTo(path)
      await sleep(250)
    },
    /** Send n scripted payments through the open Soundbox screen. */
    async send(n) {
      await waitFor(() => findTarget('soundbox-stage'), 8000)
      await sleep(150)
      await askScreen({ action: 'send', count: n })
    },
    /** Say the expense on the Talk screen: the recorded clip if registered, else typed into the box. Waits for the card. */
    async sayExpense(clipKey, text) {
      await waitFor(() => document.getElementById('talk-text'), 8000)
      await sleep(150)
      await askScreen({ action: 'expense-utterance', clipKey, text })
      const card = await waitFor(() => document.querySelector('[data-tour="expense-card"][data-status="open"]'), 30000)
      if (!card) throw new Error('The confirmation card did not appear on the Talk screen')
    },
    /** Tap the yes button on the open expense card and wait until it is saved (nothing to do if already saved). */
    async confirmExpense() {
      if (document.querySelector('[data-tour="expense-card"][data-status="saved"]')) return
      const yes = talkWords('ta').yes
      const btn = [...document.querySelectorAll('[data-tour="expense-card"][data-status="open"] button')]
        .find((b) => b.textContent.includes(yes))
      if (!btn) throw new Error('There is no expense card waiting for a yes')
      btn.click()
      const saved = await waitFor(() => document.querySelector('[data-tour="expense-card"][data-status="saved"]'), 20000)
      if (!saved) throw new Error('The expense was not saved')
    },
    /** If the scripted question is still open, answer it the way the script does (family, remember). Returns the payer id. */
    async answerAskedPayment() {
      const script = await get(`/demo/script?merchant_id=${demoDay.merchant_id}`)
      const asked = script.items.find((i) => i.expected_action === 'ASK_MERCHANT')
      const date = dateRef.current || demoDay.demo_date
      const open = await get(`/merchants/${demoDay.merchant_id}/questions?status=OPEN&date=${date}`)
      const q = open.items.find((x) => x.transaction_id === asked.transaction_id)
      if (q) {
        await post(`/payments/${asked.transaction_id}/confirm`, {
          merchant_id: demoDay.merchant_id, question_id: q.question_id, confirmed_category: demoDay.answer.confirmed_category,
          channel: 'TAP', utterance_text: null, remember_payer: demoDay.answer.remember_payer,
        })
      }
      return (await get(`/payments/${asked.transaction_id}`)).payer_id
    },
  })

  const show = useCallback(async (i, forward) => {
    const step = STEPS[i]
    setIndex(i)
    setError(null)
    if (forward && step.enter) {
      setBusy(true)
      try {
        await step.enter(helpers.current)
        routes.current[i] = window.location.hash
      } catch (e) {
        setError(e)
      } finally {
        setBusy(false)
      }
    } else if (routes.current[i] && window.location.hash !== routes.current[i]) {
      window.location.hash = routes.current[i]
    }
  }, [])

  const start = useCallback(() => {
    routes.current = {}
    setMerchantId('M001')
    show(0, false)
  }, [setMerchantId, show])
  const exit = useCallback(() => { setIndex(-1); setBusy(false); setError(null) }, [])
  const next = useCallback(async () => {
    const step = STEPS[index]
    if (step?.leave) { // forward-only: what this step finishes before the tour moves on
      setBusy(true)
      setError(null)
      try {
        await step.leave(helpers.current)
      } catch (e) {
        e.phase = 'leave'
        setError(e)
        return
      } finally {
        setBusy(false)
      }
    }
    if (index >= STEPS.length - 1) exit()
    else show(index + 1, true)
  }, [index, show, exit])
  const back = useCallback(() => index > 0 && show(index - 1, false), [index, show])
  const retry = useCallback(() => (error?.phase === 'leave' ? next() : show(index, true)), [error, index, next, show])

  // keyboard: Esc closes; arrows move when focus is not in a text field
  useEffect(() => {
    if (index < 0) return undefined
    const on = (e) => {
      if (e.key === 'Escape') exit()
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '')
      if (busy || typing) return
      if (e.key === 'ArrowRight') next()
      if (e.key === 'ArrowLeft') back()
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [index, busy, next, back, exit])

  return (
    <TourContext.Provider value={{ active: index >= 0, start }}>
      {children}
      {index < 0 ? (
        <button type="button" className="tour-start" onClick={start}>
          <Play aria-hidden="true" />
          <span>Judge tour</span>
        </button>
      ) : (
        <Overlay step={STEPS[index]} index={index} total={STEPS.length} busy={busy} error={error}
          onNext={next} onBack={back} onExit={exit} onRetry={retry} />
      )}
    </TourContext.Provider>
  )
}

export function useTour() {
  return useContext(TourContext)
}
