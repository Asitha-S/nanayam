// Udhari · the credit book (contract section 13, flag UDHARI; App.jsx shows this route only when the flag is on).
// GET /merchants/{id}/tabs: who owes what (open tabs oldest first, then paid-off ones), each tab's entries with their
// source, and today's payments that could come off a tab. POST /tabs/{payer_id}/settle takes one off; the backend
// decides the amount. A book beside the ledger: nothing here changes a payment, a ledger entry, sales or profit.
// Every amount is the backend's display string; the frontend never adds, subtracts or compares money.
import '../styles/udhari.css'
import { Check, ChevronDown, Database, Info, Mic, PenLine, Receipt, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { post, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { useStrings } from '../app/strings'
import { settleHint } from '../app/udhari'
import { uuid } from '../app/uuid'
import { LoadState, clockTime, count, ledgerHref, longDate } from '../components/ui'

const KIND = {
  ADD: ['Given on credit', 'ud-add'],
  SETTLE: ['Paid back', 'ud-settle'],
  ADJUST: ['Adjusted', 'muted'],
}

function When({ iso }) {
  return (
    <span className="ud-when">
      <b>{longDate(iso)}</b>
      <small>{clockTime(iso)} IST</small>
    </span>
  )
}

/** Where a tab entry came from: said on Talk, a UPI payment (its ledger entry), typed, or seeded demo data. */
function Source({ s, lang }) {
  if (!s) return <span className="note">No source</span>
  if (s.type === 'VOICE') {
    return (
      <span className="ud-src">
        <span className="ud-src-k"><Mic aria-hidden="true" /> Said on Talk</span>
        {s.utterance_text && <q lang={lang}>{s.utterance_text}</q>}
        {s.voice_log_id && <small className="mono">{s.voice_log_id}</small>}
      </span>
    )
  }
  if (s.type === 'PAYMENT') {
    return (
      <span className="ud-src">
        <span className="ud-src-k"><Receipt aria-hidden="true" /> UPI payment</span>
        {s.ledger_entry_id && (
          <a className="mono" href={ledgerHref([s.ledger_entry_id])} title="Open the payment's ledger entry">{s.ledger_entry_id}</a>
        )}
        {s.transaction_id && <small className="mono">{s.transaction_id}</small>}
      </span>
    )
  }
  if (s.type === 'SEED') {
    return (
      <span className="ud-src">
        <span className="badge"><Database aria-hidden="true" /> Demo data</span>
        <small>Seeded with the demo day, not said or typed</small>
      </span>
    )
  }
  if (s.type === 'MANUAL') {
    return (
      <span className="ud-src">
        <span className="ud-src-k"><PenLine aria-hidden="true" /> Typed</span>
      </span>
    )
  }
  return <span className="ud-src"><span className="ud-src-k">{s.type}</span></span>
}

function Entries({ tab, lang }) {
  return (
    <div className="dtable ud-entries" role="table" aria-label={`${tab.payer_name}'s tab`} id={`ud-e-${tab.payer_id}`}>
      <div className="tr th" role="row">
        <span>When</span><span>What</span><span className="num">Amount</span><span className="num">Due after</span><span>Source</span>
      </div>
      {!tab.entries?.length && <div className="tr"><span className="note">No entries.</span></div>}
      {(tab.entries || []).map((e) => {
        const [text, cls] = KIND[e.kind] || [e.kind, 'muted']
        return (
          <div className="tr" role="row" key={e.tab_entry_id}>
            <When iso={e.created_at} />
            <span className="ud-what">
              <span className={`chip ${cls}`}>{text}</span>
              {e.note && <small>{e.note}</small>}
              <small className="mono">{e.tab_entry_id}</small>
            </span>
            <span className="num">{e.amount_display}</span>
            <span className="num">{e.balance_after_display}</span>
            <Source s={e.source} lang={lang} />
          </div>
        )
      })}
    </div>
  )
}

function Tab({ tab, n, open, onToggle, lang }) {
  const paidOff = !(tab.due_paise > 0)
  const entries = tab.entries?.length || 0
  return (
    <li className={`ud-tab ${open ? 'is-open' : ''} ${paidOff ? 'is-settled' : ''}`}>
      <button type="button" className="ud-tab-row" aria-expanded={open} aria-controls={`ud-e-${tab.payer_id}`} onClick={onToggle}>
        <span className="n">{String(n).padStart(2, '0')}</span>
        <span className="ud-who">
          <b>{tab.payer_name}</b>
          <small>
            {paidOff ? 'Paid off' : tab.opened_at ? `Owing since ${longDate(tab.opened_at)}` : 'Owing'}
            {' · '}{count(entries)} {entries === 1 ? 'entry' : 'entries'}
          </small>
        </span>
        <span className="ud-due figure">{tab.due_display}</span>
        <ChevronDown className="ud-chev" aria-hidden="true" />
      </button>
      {open && <Entries tab={tab} lang={lang} />}
    </li>
  )
}

/** One payment that could come off a tab. Yes -> POST /tabs/{payer_id}/settle with a fresh client_request_id. */
function Offer({ offer, merchantId, onDone, onStale }) {
  const [crid] = useState(uuid) // one id per card: a retry re-sends the same request
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  async function take() {
    setBusy(true)
    setError(null)
    try {
      const res = await post(`/tabs/${encodeURIComponent(offer.payer_id)}/settle`, {
        client_request_id: crid,
        merchant_id: merchantId,
        transaction_id: offer.transaction_id,
      })
      onDone(res)
    } catch (e) {
      setError(e)
      if (['INVALID_STATE', 'NOT_FOUND'].includes(e?.code)) onStale()
    } finally {
      setBusy(false)
    }
  }
  return (
    <li className="ud-offer">
      <div className="ud-offer-top">
        <span>
          <b>{offer.payer_name}</b>
          <small> · {clockTime(offer.timestamp)} IST</small>
        </span>
        <a className="money figure" href={ledgerHref([offer.ledger_entry_id])} title="Open the payment's ledger entry">{offer.amount_display}</a>
      </div>
      <dl className="kv">
        <dt>Due now</dt><dd className="figure">{offer.due_display}</dd>
        <dt>Comes off</dt><dd className="figure">{offer.settle_display}</dd>
        <dt>Payment</dt><dd className="mono">{offer.transaction_id}</dd>
      </dl>
      <button type="button" className="btn ink" onClick={take} disabled={busy} aria-busy={busy}>
        {busy ? 'Taking it off…' : 'Take it off the tab'}
      </button>
      {error && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          <span><b>{error.message}.</b> {settleHint(error)}</span></p>
      )}
    </li>
  )
}

function Done({ r }) {
  return (
    <div className="ud-done" role="status">
      <p>
        <Check aria-hidden="true" />
        <span>
          <b>Took <span className="figure">{r.amount_display}</span> off {r.payer_name}&apos;s tab.</b>{' '}
          Due was <span className="figure">{r.due_before_display}</span>, now <span className="figure">{r.due_display}</span>.
        </span>
      </p>
      {r.idempotent_replay && <small>This was already done, so nothing new was written.</small>}
      <small>
        Payment {r.payment_amount_display && <span className="figure">{r.payment_amount_display}</span>}{' '}
        <span className="mono">{r.transaction_id}</span>: its ledger entry is unchanged. Tab entry <span className="mono">{r.tab_entry_id}</span>.
      </small>
    </div>
  )
}

export default function Udhari() {
  const { merchantId, merchant } = useMerchant()
  const t = useStrings()
  const tabs = useApi(`/merchants/${merchantId}/tabs`)
  const d = tabs.data
  const [open, setOpen] = useState(() => new Set())
  const [taken, setTaken] = useState([]) // settle results made on this screen, newest first

  useEffect(() => {
    setOpen(new Set())
    setTaken([])
  }, [merchantId])

  const toggle = (id) => setOpen((s) => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const items = d?.items || []
  const owing = items.filter((x) => x.due_paise > 0)
  const paidOff = items.filter((x) => !(x.due_paise > 0))
  const offers = d?.offers || []

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">10 · {merchant?.display_name || merchantId}</span>
          <h1>Udhari.</h1>
          <p className="lede">
            Goods given on credit to customers {merchant?.owner_name || 'the owner'} knows, and what they paid back. A book
            beside the ledger: it never changes a payment, sales or profit.
          </p>
        </div>
        {d && items.length > 0 && (
          <div className="page-actions">
            <button type="button" className="btn" onClick={() => setOpen(new Set(open.size ? [] : items.map((x) => x.payer_id)))}>
              {open.size ? 'Close all' : 'Open all'}
            </button>
          </div>
        )}
      </header>

      {!d && <LoadState state={tabs} what="the credit book" />}

      {d && (
        <div className="split ud-split">
          <section className="panel ud-book" aria-labelledby="ud-book-h">
            <div className="panel-head">
              <h2 id="ud-book-h">Who owes what</h2>
              <span className="label">Oldest first</span>
            </div>
            {!items.length && <p className="note">No one has anything on a tab yet. Say it on Talk: a customer’s name and the amount given on credit.</p>}
            {owing.length > 0 && (
              <ol className="ud-tabs" aria-label="Open tabs">
                {owing.map((tab, i) => (
                  <Tab key={tab.payer_id} tab={tab} n={i + 1} open={open.has(tab.payer_id)} onToggle={() => toggle(tab.payer_id)} lang={t.lang} />
                ))}
              </ol>
            )}
            {paidOff.length > 0 && (
              <>
                <span className="label ud-group">Paid off</span>
                <ol className="ud-tabs" aria-label="Paid-off tabs">
                  {paidOff.map((tab, i) => (
                    <Tab key={tab.payer_id} tab={tab} n={owing.length + i + 1} open={open.has(tab.payer_id)} onToggle={() => toggle(tab.payer_id)} lang={t.lang} />
                  ))}
                </ol>
              </>
            )}
          </section>

          <div className="ud-side">
            <section className="panel sky ud-total" aria-labelledby="ud-total-h">
              <div className="panel-head" style={{ marginBottom: 0 }}>
                <span className="label" id="ud-total-h">Owed to the shop</span>
                <span className="label">as of {clockTime(d.as_of)} IST</span>
              </div>
              <strong className="ud-total-fig figure">{d.total_due_display}</strong>
              <small>{count(d.open_count)} {d.open_count === 1 ? 'customer owes' : 'customers owe'}</small>
            </section>

            <section className={`panel ud-offers ${offers.length ? 'signal' : ''}`} aria-labelledby="ud-offers-h">
              <span className="label" id="ud-offers-h">Paid today, not yet taken off the tab</span>
              {taken.map((r) => <Done key={r.tab_entry_id} r={r} />)}
              {offers.length ? (
                <ul>
                  {offers.map((o) => (
                    <Offer key={o.transaction_id} offer={o} merchantId={merchantId}
                      onDone={(r) => setTaken((list) => [r, ...list.filter((x) => x.tab_entry_id !== r.tab_entry_id)])}
                      onStale={tabs.reload} />
                  ))}
                </ul>
              ) : (
                <p className="note">No payment from a customer with a tab is waiting today. When one pays, the Soundbox asks too.</p>
              )}
            </section>

            <section className="panel ud-scope">
              <Info aria-hidden="true" />
              <p>
                Taking a payment off a tab writes only in this book. The payment stays where the ledger put it (normally a
                sale), and nothing in the ledger is edited.
              </p>
            </section>
          </div>
        </div>
      )}
    </>
  )
}
