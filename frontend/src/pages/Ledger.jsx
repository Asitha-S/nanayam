// P1 · Ledger: entries, detail, verify. GET /merchants/{id}/ledger, GET /ledger/{entry_id}, GET .../ledger/verify.
// Opened from an amount (#/ledger?ids=LE-1,LE-2) it shows exactly the entries behind that amount.
// Correcting a payment (contract section 4): POST /payments/{txn}/confirm with question_id = the payment's open
// question (GET /merchants/{id}/questions) or null. It writes a new RECLASSIFICATION entry; the old one stays.
import { Check, ChevronLeft, ChevronRight, Info, RefreshCw, ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { get, post, put, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { go } from '../app/route'
import { useStrings } from '../app/strings'
import { LoadState, clockTime, confidenceText, count, longDate } from '../components/ui'
import { shiftDay } from './Today'

const FILTERS = [
  ['all', 'All'],
  ['sale', 'Sales'],
  ['family', 'Family'],
  ['pending', 'Waiting'],
  ['expense', 'Expenses'],
]

/** sale | family | pending | expense | other: what the entry is, for colour and filtering (never for money). */
function kindOf(e) {
  if (e.source_type === 'EXPENSE') return 'expense'
  const c = (e.classification || '').toLowerCase()
  return ['sale', 'family', 'pending'].includes(c) ? c : 'other'
}

function words(s) {
  return (s || '').toLowerCase().replaceAll('_', ' ')
}

function shortHash(h) {
  return h ? `${h.slice(0, 6)}…${h.slice(-4)}` : '—'
}

function KindChip({ entry }) {
  const k = kindOf(entry)
  const text = k === 'expense' ? 'Expense' : k === 'other' ? words(entry.classification || entry.entry_type) : k === 'pending' ? 'Waiting' : k
  return <span className={`chip ${k === 'other' ? 'muted' : k}`}>{text}</span>
}

/** Fetch a list of entries by id (an amount's sources). */
function useEntries(ids) {
  const key = ids?.join(',') || ''
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(key) })
  useEffect(() => {
    if (!key) return undefined
    let live = true
    setState({ data: null, error: null, loading: true })
    Promise.all(key.split(',').map((id) => get(`/ledger/${encodeURIComponent(id)}`)))
      .then((items) => live && setState({ data: items, error: null, loading: false }))
      .catch((error) => live && setState({ data: null, error, loading: false }))
    return () => { live = false }
  }, [key])
  return state
}

function Verify({ merchantId }) {
  const v = useApi(`/merchants/${merchantId}/ledger/verify`)
  const ok = v.data?.status === 'VALID'
  return (
    <section className={`panel verify-strip ${v.data ? (ok ? 'is-valid' : 'is-bad') : ''}`} aria-live="polite" data-tour="verify">
      {ok ? <ShieldCheck aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
      <div>
        <span className="label">Hash-chain check</span>
        {v.data ? (
          <p><strong className="figure">{v.data.status}</strong> {v.data.message}
            {v.data.first_invalid_entry_id && <> First bad entry: <button type="button" className="linkish" onClick={() => go(`/ledger?ids=${v.data.first_invalid_entry_id}`)}>{v.data.first_invalid_entry_id}</button>.</>}
          </p>
        ) : <LoadState state={v} what="the check" />}
      </div>
      <button type="button" className="btn" onClick={v.reload}><RefreshCw aria-hidden="true" /> Check again</button>
    </section>
  )
}

function SourceDetails({ source }) {
  if (!source || typeof source !== 'object') return null
  const rows = Object.entries(source).filter(([, v]) => v !== null && typeof v !== 'object')
  return (
    <>
      <h3 className="detail-sub">Source record</h3>
      <dl className="kv">
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <dt>{words(k)}</dt>
            <dd className={/paise|_id|hash/.test(k) ? 'mono' : ''}>{String(v)}</dd>
          </div>
        ))}
      </dl>
    </>
  )
}

// ---------- correct a payment ----------

const EN = { SALE: 'Shop sale', FAMILY: 'Family money' }
const NOW_WORDS = { SALE: 'a shop sale', FAMILY: 'family money', PENDING: 'waiting for an answer' }

/** What to say when a correction fails, by the contract's error codes. The server's message is shown too. */
function confirmHint(e) {
  const reason = e?.details?.reason
  if (e?.code === 'INVALID_STATE' && reason === 'REVERSED') return 'The bank reversed this payment, so it stays as it is. Nothing was saved.'
  if (e?.code === 'INVALID_STATE' && reason === 'QUESTION_MISMATCH') return 'The open question changed. Pick the entry again and retry. Nothing was saved.'
  if (e?.code === 'INVALID_STATE') return 'Not allowed for this payment right now. Pick the entry again to see where it stands.'
  if (e?.code === 'VALIDATION_ERROR' && e?.details?.field === 'remember_payer') {
    return 'Untick “Remember”, or choose family money. Nothing was saved.'
  }
  if (e?.code === 'NOT_FOUND') return 'This payment is gone (was the demo reset?). Reload the ledger.'
  if (e?.code === 'UNREACHABLE') return 'Check that the backend is running, then try again.'
  return 'Try again. A repeated answer is never counted twice.'
}

/** The payment's current entry is the last PAYMENT_IN / RECLASSIFICATION in its history. */
function latestEntryId(payment) {
  const h = payment?.classification_history
  return h && h.length ? h[h.length - 1].ledger_entry_id : null
}

function Correct({ entry, onCorrected, onStale }) {
  const t = useStrings()
  const pay = entry.source
  const merchantId = pay.merchant_id
  const day = (pay.timestamp || '').slice(0, 10)
  const questions = useApi(`/merchants/${encodeURIComponent(merchantId)}/questions?status=OPEN&date=${day}`)
  const open = questions.data?.items?.find((q) => q.transaction_id === pay.transaction_id) || null
  const [remember, setRemember] = useState(false)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const now = pay.current_classification
  const waiting = questions.loading && !questions.data

  async function send(category) {
    setBusy(category)
    setError(null)
    try {
      const res = await post(`/payments/${encodeURIComponent(pay.transaction_id)}/confirm`, {
        merchant_id: merchantId,
        question_id: open ? open.question_id : null,
        confirmed_category: category,
        channel: 'TAP',
        utterance_text: null,
        remember_payer: remember,
      })
      onCorrected({ res, from: entry.ledger_entry_id, payerId: pay.payer_id, payerName: pay.payer_name, merchantId, remember })
    } catch (e) {
      setError(e)
      // the screen was out of date (reversed, question changed): show where the payment stands now
      if (e?.code === 'INVALID_STATE') {
        onStale?.()
        questions.reload()
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="lg-fix" aria-labelledby={`fix-${entry.ledger_entry_id}`}>
      <h3 className="lg-fix-h" id={`fix-${entry.ledger_entry_id}`}>Correct this payment</h3>
      <p className="lg-fix-now">
        Now <span className={`chip ${(now || '').toLowerCase()}`}>{now === 'PENDING' ? 'Waiting' : words(now)}</span>
        <span>{pay.payer_name} · {pay.payment_type}</span>
      </p>
      {pay.reversed ? (
        <p className="lg-fix-note"><Info aria-hidden="true" /> The bank reversed this payment, so it can't be corrected.</p>
      ) : (
        <>
          <p className="note">
            A correction is a new entry; this one stays in the ledger.
            {open && <> It also answers the open question <span className="mono">{open.question_id}</span>.</>}
          </p>
          <div className="lg-fix-answers" role="group" aria-label={`What is ${pay.payer_name}'s ${pay.amount_display}?`}>
            {['SALE', 'FAMILY'].map((cat) => (
              <button key={cat} type="button" className={cat === 'SALE' ? 'is-sale' : 'is-family'} onClick={() => send(cat)}
                disabled={Boolean(busy) || waiting} aria-busy={busy === cat}>
                <span lang={t.lang}>{cat === 'SALE' ? t.sale : t.family}</span>
                <small>{busy === cat ? 'Saving…' : EN[cat]}{now === cat && <b className="lg-now">Now</b>}</small>
              </button>
            ))}
          </div>
          <label className="lg-remember">
            <input type="checkbox" checked={remember} onChange={(ev) => { setRemember(ev.target.checked); setError(null) }} disabled={Boolean(busy)} />
            <span>Remember this for {pay.payer_name}</span>
          </label>
          {remember && pay.payment_type !== 'P2P' && (
            <p className="note">This is a shop-QR (P2M) payment: only family money can be remembered. “Always a customer” needs a payment to the UPI number (P2P).</p>
          )}
          {questions.error && <p className="note">Couldn't check for an open question ({questions.error.message}); the correction is sent without one.</p>}
        </>
      )}
      {error && (
        <p className="error-banner" role="alert">
          <TriangleAlert aria-hidden="true" />
          <span><b>{error.message}.</b> {confirmHint(error)}</span>
        </p>
      )}
    </section>
  )
}

/** "Stop treating {name} as always family?" (contract: suggest_unconfigure). PUT /merchants/{id} without them. */
function Unconfigure({ fix }) {
  const [state, setState] = useState('idle')
  const [error, setError] = useState(null)
  async function stop() {
    setState('saving')
    setError(null)
    try {
      const m = await get(`/merchants/${encodeURIComponent(fix.merchantId)}`)
      await put(`/merchants/${encodeURIComponent(fix.merchantId)}`, {
        family_payer_ids: (m.family_payers || []).map((p) => p.payer_id).filter((id) => id !== fix.payerId),
      })
      setState('done')
    } catch (e) {
      setError(e)
      setState('idle')
    }
  }
  if (state === 'done') return <p>Removed {fix.payerName} from the family list. Future payments are judged on their own again.</p>
  return (
    <div className="lg-unconf">
      <p>{fix.payerName} is still on the family list, so future payments stay family. Stop treating {fix.payerName} as always family?</p>
      <button type="button" className="btn" onClick={stop} disabled={state === 'saving'}>
        {state === 'saving' ? 'Saving…' : 'Stop treating as family'}
      </button>
      {error && <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" /><span>{error.message}. Try again in a moment.</span></p>}
    </div>
  )
}

function FixResult({ fix, inList }) {
  const r = fix.res
  const cat = r.confirmed_category
  const pm = r.payer_memory || {}
  if (r.idempotent_replay) {
    return (
      <div className="lg-fix-done is-same" role="status">
        <p><Info aria-hidden="true" /><span><b>Nothing changed.</b> This payment is already {NOW_WORDS[cat]}, as you said before. No new entry was written.</span></p>
      </div>
    )
  }
  const moved = r.moved_from === 'CUSTOMER' ? ' Moved off the customer list.' : r.moved_from === 'FAMILY' ? ' Moved off the family list.' : ''
  let memory = null
  if (fix.remember && cat === 'FAMILY' && pm.family_payer_configured) memory = `Remembered: ${fix.payerName}'s future payments are family money, by your instruction.${moved}`
  else if (fix.remember && cat === 'SALE' && pm.customer_payer_configured) memory = `Remembered: ${fix.payerName}'s future payments count as shop sales, by your instruction.${moved}`
  return (
    <div className={`lg-fix-done ${cat === 'FAMILY' ? 'is-family' : ''}`} role="status">
      <p>
        <Check aria-hidden="true" />
        <span>
          <b>Saved as {NOW_WORDS[cat]}</b> (was {NOW_WORDS[r.previous_classification] || words(r.previous_classification)}). This new
          entry replaces <span className="mono">{fix.from}</span>, which stays in the ledger.
          {!inList && ' It is not in the list you opened, so it is shown here.'}
        </span>
      </p>
      {r.question_status === 'ANSWERED' && r.question_id && <small>Question <span className="mono">{r.question_id}</span> is answered.</small>}
      {memory && <small>{memory}</small>}
      {r.suggest_unconfigure && <Unconfigure fix={fix} />}
    </div>
  )
}

function Detail({ id, onPick, fix, inList, onCorrected }) {
  const d = useApi(id ? `/ledger/${encodeURIComponent(id)}` : null)
  if (!id) {
    return (
      <aside className="panel detail is-empty">
        <span className="label">Entry detail</span>
        <p>Pick an entry to see its source, what it replaced, and the two hashes that chain it to the entry before.</p>
      </aside>
    )
  }
  const e = d.data
  const isPayment = e?.source_type === 'PAYMENT' && e.source && typeof e.source === 'object'
  const latest = isPayment ? latestEntryId(e.source) : null
  return (
    <aside className="panel detail" aria-live="polite">
      <div className="panel-head"><span className="label">Entry detail</span>{e && <KindChip entry={e} />}</div>
      {!e && <LoadState state={d} what="the entry" />}
      {e && (
        <>
          <p className="detail-amt figure">{e.amount_display}</p>
          {fix && fix.res.ledger_entry_id === e.ledger_entry_id && <FixResult fix={fix} inList={inList} />}
          {isPayment && latest === e.ledger_entry_id && <Correct key={e.ledger_entry_id} entry={e} onCorrected={onCorrected} onStale={d.reload} />}
          {isPayment && latest && latest !== e.ledger_entry_id && (
            <p className="lg-fix-note">
              <Info aria-hidden="true" />
              <span>A later entry replaced this one: <button type="button" className="linkish mono" onClick={() => onPick(latest)}>{latest}</button>. Corrections go on the latest entry.</span>
            </p>
          )}
          <dl className="kv">
            <dt>Entry</dt><dd className="mono">{e.ledger_entry_id} · seq {e.seq}</dd>
            <dt>Type</dt><dd>{words(e.entry_type)}</dd>
            <dt>Source</dt><dd className="mono">{e.source_type} {e.source_id}</dd>
            {e.supersedes_entry_id && (<><dt>Replaces</dt><dd><button type="button" className="linkish mono" onClick={() => onPick(e.supersedes_entry_id)}>{e.supersedes_entry_id}</button> (corrections are new entries)</dd></>)}
            <dt>Decided by</dt><dd>{words(e.classification_source) || '—'}{typeof e.confidence === 'number' ? ` · ${confidenceText(e.confidence)} confidence` : ''}</dd>
            <dt>Happened</dt><dd className="mono">{e.effective_at}</dd>
            <dt>Recorded</dt><dd className="mono">{e.created_at}</dd>
            <dt>Prev hash</dt><dd className="hash">{e.prev_hash}</dd>
            <dt>Hash</dt><dd className="hash">{e.hash}</dd>
          </dl>
          <SourceDetails source={e.source} />
        </>
      )}
    </aside>
  )
}

export default function Ledger({ params }) {
  const { merchantId, merchant, demoDate } = useMerchant()
  const ids = useMemo(() => (params.ids ? params.ids.split(',').filter(Boolean) : null), [params.ids])
  const [picked, setPicked] = useState(null)
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [fix, setFix] = useState(null)
  const scrollTo = useRef(null)
  const day = picked || demoDate
  const isToday = day && day === demoDate
  const dayLedger = useApi(!ids && day ? `/merchants/${merchantId}/ledger?start_date=${day}&end_date=${day}&limit=200` : null)
  const byIds = useEntries(ids)
  const source = ids ? byIds : dayLedger
  const items = ids ? byIds.data : dayLedger.data?.items
  const shown = (items || []).filter((e) => filter === 'all' || kindOf(e) === filter)

  useEffect(() => {
    setSelected(ids?.length === 1 ? ids[0] : null)
    setFix(null)
  }, [ids])

  const pick = (id) => {
    setSelected(id)
    setFix(null)
  }
  // a correction: select the new RECLASSIFICATION entry (a replay keeps the current one) and show what happened
  const onCorrected = (f) => {
    setFix(f)
    setSelected(f.res.ledger_entry_id)
    scrollTo.current = f.res.idempotent_replay ? null : f.res.ledger_entry_id
  }
  // once the refetched day includes the new entry, bring its row into view
  useEffect(() => {
    const id = scrollTo.current
    if (!id || !items?.some((e) => e.ledger_entry_id === id)) return
    scrollTo.current = null
    const calm = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    document.querySelector(`[data-entry="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: calm ? 'auto' : 'smooth' })
  }, [items])

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">06 · {merchant?.display_name || merchantId}</span>
          <h1>The ledger.</h1>
          <p className="lede">Append-only: nothing is edited, corrections are new entries. Each entry carries the hash of the one before it.</p>
        </div>
        {!ids && (
          <div className="page-actions">
            <div className="daystep" aria-label="Day">
              <button type="button" onClick={() => setPicked(shiftDay(day, -1))} disabled={!day} aria-label="Previous day"><ChevronLeft /></button>
              <strong>{day ? longDate(day) : '…'}</strong>
              <button type="button" onClick={() => setPicked(shiftDay(day, 1))} disabled={!day || isToday} aria-label="Next day"><ChevronRight /></button>
            </div>
          </div>
        )}
      </header>

      <Verify merchantId={merchantId} />

      <div className="ledger-bar">
        {ids ? (
          <p><b>{count(ids.length)} {ids.length === 1 ? 'entry' : 'entries'}</b> behind the amount you opened. <a href="#/ledger">Show the whole day</a></p>
        ) : (
          <div className="seg" role="group" aria-label="Filter">
            {FILTERS.map(([k, label]) => (
              <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>
            ))}
          </div>
        )}
        {items && <span className="label">{count(shown.length)} shown</span>}
      </div>

      <div className="split ledger-split">
        <div className="dtable ledger-table" role="table" aria-label="Ledger entries" data-tour="ledger-table">
          <div className="tr th" role="row">
            <span>Seq</span><span>Time</span><span>Entry</span><span>Source</span><span>Kind</span><span className="num">Amount</span><span>Hash</span>
          </div>
          {!items && <div className="tr"><LoadState state={source} what="ledger entries" /></div>}
          {items && !shown.length && <div className="tr"><span className="note">No entries {filter === 'all' ? 'on this day' : 'of this kind'}.</span></div>}
          {shown.map((e) => (
            <button key={e.ledger_entry_id} type="button" role="row" className={`tr ${selected === e.ledger_entry_id ? 'is-selected' : ''}`}
              onClick={() => pick(e.ledger_entry_id)} aria-pressed={selected === e.ledger_entry_id} data-entry={e.ledger_entry_id}>
              <span className="mono">{e.seq}</span>
              <span className="mono">{clockTime(e.effective_at)}</span>
              <span>{words(e.entry_type)}{e.supersedes_entry_id && <small className="note"> · replaces {e.supersedes_entry_id.split('-').pop()}</small>}</span>
              <span className="mono">{e.source_id}</span>
              <span><KindChip entry={e} /></span>
              <span className="num">{e.amount_display}</span>
              <span className="hash">{shortHash(e.hash)}</span>
            </button>
          ))}
        </div>
        <Detail id={selected} onPick={pick} fix={fix} onCorrected={onCorrected}
          inList={!ids || !fix || ids.includes(fix.res.ledger_entry_id)} />
      </div>
    </>
  )
}
