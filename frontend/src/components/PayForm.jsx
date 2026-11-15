// A customer's UPI payment to the shop, simulated: the phone page (#/pay, variant 'phone') and the laptop's
// "Pay from this screen" side panel (variant 'panel').
// GET /demo/pay-options (who can pay; no classification hints), GET /health (`now`, used as the payment's time),
// POST /payments with X-Naanayam-Client: pay-page (one payment per 2 s per device, else 429 RATE_LIMITED).
// Only the panel shows each payer's status, from GET /merchants/{id}/learning; the phone never does.
import { Check, RotateCcw, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { get, post, useApi } from '../api'
import { LoadState, Money, clockTime } from './ui'

/** A backend message as one sentence: a full stop is added only when it has none. */
const sentence = (m) => (/[.!?]$/.test(m || '') ? m : `${m}.`)

const NEW = 'NEW'
const MAX_RUPEES = 50000
const GAP_MS = 2000
const METHODS = [
  { type: 'P2M', title: 'Shop QR', sub: 'P2M' },
  { type: 'P2P', title: 'UPI number', sub: 'P2P' },
]
const METHOD_WORDS = { P2M: 'Shop QR (P2M)', P2P: 'UPI number (P2P)' }
const GROUP_WORDS = { CUSTOMER: 'Regular customers', BUSINESS: 'Businesses', PERSON: 'People' }

function hex(bytes) {
  const b = new Uint8Array(bytes)
  window.crypto.getRandomValues(b)
  return [...b].map((x) => x.toString(16).padStart(2, '0')).join('')
}
const newTxnId = (merchantId) => `PAY-${merchantId}-${Date.now()}-${hex(2)}`
const newPayerId = () => `PNEW${String(parseInt(hex(3), 16) % 1000000).padStart(6, '0')}`

/** Whole rupees, 1 to 50,000. Returns { rupees } or { error }. */
function readRupees(raw) {
  const t = raw.replace(/[,\s]/g, '')
  if (!t) return { error: 'Enter the amount in rupees.' }
  if (!/^\d+$/.test(t)) return { error: 'Whole rupees only: digits, no paise.' }
  const n = Number(t)
  if (n < 1 || n > MAX_RUPEES) return { error: 'From 1 to 50,000 rupees.' }
  return { rupees: n }
}

/** A payer's status in plain words (panel only), from GET /merchants/{id}/learning `payers`. */
function statusHint(lp, isNew) {
  if (isNew) return 'New payer: the model decides, and asks when unsure'
  if (!lp) return 'No instruction: the model decides, and asks when unsure'
  const how = lp.source === 'SETUP' ? 'set at setup' : lp.source === 'CONFIRMATION' ? 'from an answer' : 'from answers'
  if (lp.kind === 'FAMILY_INSTRUCTION') return `Always family money: your instruction, ${how}`
  if (lp.kind === 'CUSTOMER_INSTRUCTION') return `Always a shop sale: your instruction, ${how}`
  if (lp.kind === 'MIXED') return `Mixed answers (${lp.confirmed_family} family, ${lp.confirmed_sale} sale): always asked`
  if (lp.kind === 'MEMORY') return `Past answers: ${lp.confirmed_family} family, ${lp.confirmed_sale} sale. The model uses them`
  return 'No instruction: the model decides, and asks when unsure'
}

function optionsError(e, merchantId) {
  if (e.code === 'NOT_FOUND') return `There is no shop with code ${merchantId} here, or demo tools are off on the laptop's backend.`
  if (e.code === 'UNREACHABLE') return "Can't reach the shop's laptop. Check that this device is on the same Wi-Fi or hotspot as the laptop, then reload."
  return 'Reload the page to try again.'
}

function payError(e) {
  if (e.code === 'RATE_LIMITED') return null // the backend's own message says it all
  if (e.code === 'UNREACHABLE') return "Can't reach the shop's laptop. Press Pay again: the same payment is sent again and is never counted twice."
  if (e.code === 'VALIDATION_ERROR') return 'Check the amount and the name, then press Pay again.'
  if (e.code === 'DUPLICATE_CONFLICT') return 'Press Pay again to send it as a new payment.'
  return 'Press Pay again.'
}

/** props: merchantId, variant: 'phone' | 'panel', onPaid(response, request) */
export default function PayForm({ merchantId, variant = 'phone', onPaid }) {
  const panel = variant === 'panel'
  const opts = useApi(`/demo/pay-options?merchant_id=${encodeURIComponent(merchantId)}`)
  const learning = useApi(panel ? `/merchants/${encodeURIComponent(merchantId)}/learning` : null)
  const [payerId, setPayerId] = useState(null)
  const [newName, setNewName] = useState('')
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState(null) // null: the payer's usual way
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(null) // { res, body }
  const [coolUntil, setCoolUntil] = useState(0)
  const [, setTick] = useState(0)
  const newPayer = useRef(null) // { name, id }: one id per new customer's name
  const pending = useRef(null) // { key, body }: re-sent unchanged after a network failure (idempotent)
  const doneRef = useRef(null)
  const payRef = useRef(null)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  // a new shop: start over
  useEffect(() => {
    setPayerId(null); setMethod(null); setDone(null); setError(null); setTried(false)
    pending.current = null
  }, [merchantId])

  // re-render when the 2 s gap is over
  useEffect(() => {
    const ms = coolUntil - Date.now()
    if (ms <= 0) return undefined
    const t = setTimeout(() => setTick((n) => n + 1), ms + 30)
    return () => clearTimeout(t)
  }, [coolUntil])
  const cooling = coolUntil > Date.now()

  const data = opts.data && opts.data.merchant_id === merchantId ? opts.data : null
  const payers = data?.payers || []
  const shop = data?.display_name || merchantId
  const memory = useMemo(() => new Map((learning.data?.payers || []).map((p) => [p.payer_id, p])), [learning.data])

  const isNew = payerId === NEW
  const picked = isNew ? null : payers.find((p) => p.payer_id === payerId) || null
  const type = method || picked?.usual_payment_type || 'P2M'
  const amt = readRupees(amount)
  const name = newName.trim()
  const problems = {
    payer: !payerId || (!isNew && !picked) ? 'Choose who is paying.' : null,
    name: isNew && !name ? "Enter the new customer's name." : isNew && name.length > 40 ? 'Keep the name under 40 letters.' : null,
    amount: amt.error || null,
  }
  const invalid = Object.values(problems).some(Boolean)

  function choosePayer(id) {
    setPayerId(id)
    setMethod(null)
    setError(null)
  }

  function payerFields() {
    if (!isNew) return { payer_id: picked.payer_id, payer_name: picked.payer_name, payer_vpa_kind: picked.payer_vpa_kind }
    if (!newPayer.current || newPayer.current.name !== name) newPayer.current = { name, id: newPayerId() }
    return { payer_id: newPayer.current.id, payer_name: name, payer_vpa_kind: 'PERSONAL' }
  }

  async function pay(e) {
    e.preventDefault()
    setTried(true)
    if (invalid || busy || cooling) return
    setBusy(true)
    setError(null)
    try {
      const who = payerFields()
      const key = JSON.stringify([merchantId, who, amt.rupees, type])
      let body = pending.current?.key === key ? pending.current.body : null
      if (!body) {
        const health = await get('/health') // the backend's current IST time is the payment's time
        if (!health?.now) throw Object.assign(new Error("The laptop's backend didn't send the time"), { code: 'NO_TIME' })
        body = {
          transaction_id: newTxnId(merchantId),
          merchant_id: merchantId,
          ...who,
          amount_paise: amt.rupees * 100, // the typed whole rupees in paise (a unit conversion, not a calculation)
          payment_type: type,
          timestamp: health.now,
          description: null,
        }
        pending.current = { key, body }
      }
      const res = await post('/payments', body, { headers: { 'X-Naanayam-Client': 'pay-page' } })
      pending.current = null
      if (!alive.current) return
      setCoolUntil(Date.now() + GAP_MS)
      setDone({ res, body })
      onPaid?.(res, body)
    } catch (err) {
      if (!alive.current) return
      if (err.code === 'RATE_LIMITED') {
        pending.current = null // nothing was recorded: the next try is a new payment with a fresh time
        setCoolUntil(Date.now() + Math.max(500, (Number(err.details?.retry_after_s) || 2) * 1000))
      } else if (err.code !== 'UNREACHABLE') {
        pending.current = null
      }
      setError(err)
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  useEffect(() => {
    if (done) doneRef.current?.focus()
  }, [done])

  function again() {
    setDone(null)
    setError(null)
    setTried(false)
    requestAnimationFrame(() => payRef.current?.focus())
  }

  if (!data) {
    return (
      <div className={`pf pf-${variant}`}>
        {opts.error ? (
          <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
            <span><b>{sentence(opts.error.message)}</b> {optionsError(opts.error, merchantId)}</span></p>
        ) : <LoadState state={opts} what="who can pay" />}
      </div>
    )
  }

  if (done) {
    const { res, body } = done
    return (
      <div className={`pf pf-${variant} pf-done`}>
        <div className="pf-done-head" tabIndex={-1} ref={doneRef} role="status">
          <span className="pf-tick" aria-hidden="true"><Check /></span>
          <h2 className="pf-h">{res.idempotent_replay ? 'Already paid' : 'Paid'}</h2>
        </div>
        <Money amount={res.amount_display} sources={res.ledger_entry_id ? [res.ledger_entry_id] : undefined} className="pf-done-amt" />
        <dl className="kv pf-kv">
          <dt>To</dt><dd>{shop}</dd>
          <dt>From</dt><dd>{body.payer_name}</dd>
          <dt>Time</dt><dd>{clockTime(body.timestamp)} IST</dd>
          <dt>How</dt><dd>{METHOD_WORDS[body.payment_type]}</dd>
          <dt>Transaction</dt><dd className="mono">{res.transaction_id}</dd>
        </dl>
        {res.idempotent_replay && <p className="note">This payment had already reached the shop. Nothing was counted twice.</p>}
        <p className="pf-sim"><b>Simulated payment.</b> No real money moves.</p>
        <button type="button" className="btn big pf-again" onClick={again}>
          <RotateCcw aria-hidden="true" /> Pay again
        </button>
      </div>
    )
  }

  const show = (k) => tried && problems[k]
  const groups = panel ? ['CUSTOMER', 'BUSINESS', 'PERSON'] : [null]
  return (
    <form className={`pf pf-${variant}`} onSubmit={pay} noValidate aria-busy={busy}>
      <fieldset className="pf-set">
        <legend className="pf-legend">Who is paying?</legend>
        {groups.map((role) => {
          const list = role ? payers.filter((p) => p.role === role) : payers
          if (!list.length) return null
          return (
            <div key={role || 'all'} className="pf-group">
              {role && <span className="pf-group-h">{GROUP_WORDS[role]}</span>}
              <div className="pf-payers">
                {list.map((p) => (
                  <label key={p.payer_id} className={`pf-payer ${payerId === p.payer_id ? 'is-on' : ''}`}>
                    <input type="radio" name={`payer-${variant}`} value={p.payer_id} checked={payerId === p.payer_id}
                      onChange={() => choosePayer(p.payer_id)} />
                    <span className="pf-avatar" aria-hidden="true">{p.payer_name?.[0]}</span>
                    <span className="pf-payer-text">
                      <b>{p.payer_name}</b>
                      {panel && <small>{statusHint(memory.get(p.payer_id), false)}</small>}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )
        })}
        <div className="pf-payers">
          <label className={`pf-payer pf-payer-new ${isNew ? 'is-on' : ''}`}>
            <input type="radio" name={`payer-${variant}`} value={NEW} checked={isNew} onChange={() => choosePayer(NEW)} />
            <span className="pf-avatar" aria-hidden="true">+</span>
            <span className="pf-payer-text">
              <b>New customer</b>
              {panel && <small>{statusHint(null, true)}</small>}
            </span>
          </label>
        </div>
        {show('payer') && <p className="pf-err" role="alert">{problems.payer}</p>}
      </fieldset>

      {isNew && (
        <label className="field pf-field">
          <span>Customer's name</span>
          <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} autoComplete="off" maxLength={60}
            placeholder="For example Meena" aria-invalid={Boolean(show('name'))} />
          {show('name') && <small className="pf-err" role="alert">{problems.name}</small>}
        </label>
      )}

      <label className="field pf-field">
        <span>Amount, whole rupees</span>
        <span className="pf-amount">
          <span className="pf-rupee" aria-hidden="true">₹</span>
          <input type="text" inputMode="numeric" pattern="[0-9]*" value={amount} onChange={(e) => setAmount(e.target.value)}
            autoComplete="off" placeholder="0" aria-invalid={Boolean(show('amount'))} aria-describedby={`pf-amt-help-${variant}`} />
        </span>
        <small className={show('amount') ? 'pf-err' : 'pf-help'} id={`pf-amt-help-${variant}`} role={show('amount') ? 'alert' : undefined}>
          {show('amount') || 'From 1 to 50,000 rupees.'}
        </small>
      </label>

      <fieldset className="pf-set">
        <legend className="pf-legend">How?</legend>
        <div className="pf-methods">
          {METHODS.map((m) => (
            <label key={m.type} className={`pf-method ${type === m.type ? 'is-on' : ''}`}>
              <input type="radio" name={`method-${variant}`} value={m.type} checked={type === m.type} onChange={() => setMethod(m.type)} />
              <b>{m.title}</b><small>{m.sub}</small>
            </label>
          ))}
        </div>
        {picked && !method && <small className="pf-help">{picked.payer_name}&apos;s usual way.</small>}
      </fieldset>

      <p className="pf-sim"><b>Simulated payment.</b> No real money moves.</p>

      {error && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          <span><b>{sentence(error.message)}</b> {payError(error)}</span></p>
      )}

      <button type="submit" ref={payRef} className="btn ink big pf-pay" disabled={busy || cooling} aria-describedby={cooling ? `pf-wait-${variant}` : undefined}>
        {busy ? 'Paying…' : cooling ? 'Wait a moment…' : 'Pay'}
      </button>
      {cooling && !busy && <small className="pf-help" id={`pf-wait-${variant}`}>One payment every 2 seconds.</small>}
    </form>
  )
}
