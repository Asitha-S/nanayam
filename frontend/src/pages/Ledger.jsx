// P1 · Ledger: entries, detail, verify. GET /merchants/{id}/ledger, GET /ledger/{entry_id}, GET .../ledger/verify.
// Opened from an amount (#/ledger?ids=LE-1,LE-2) it shows exactly the entries behind that amount.
import { ChevronLeft, ChevronRight, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { get, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { go } from '../app/route'
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

function Detail({ id, onPick }) {
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
  return (
    <aside className="panel detail" aria-live="polite">
      <div className="panel-head"><span className="label">Entry detail</span>{e && <KindChip entry={e} />}</div>
      {!e && <LoadState state={d} what="the entry" />}
      {e && (
        <>
          <p className="detail-amt figure">{e.amount_display}</p>
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
  const day = picked || demoDate
  const isToday = day && day === demoDate
  const dayLedger = useApi(!ids && day ? `/merchants/${merchantId}/ledger?start_date=${day}&end_date=${day}&limit=200` : null)
  const byIds = useEntries(ids)
  const source = ids ? byIds : dayLedger
  const items = ids ? byIds.data : dayLedger.data?.items
  const shown = (items || []).filter((e) => filter === 'all' || kindOf(e) === filter)

  useEffect(() => { setSelected(ids?.length === 1 ? ids[0] : null) }, [ids])

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
              onClick={() => setSelected(e.ledger_entry_id)} aria-pressed={selected === e.ledger_entry_id}>
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
        <Detail id={selected} onPick={setSelected} />
      </div>
    </>
  )
}
