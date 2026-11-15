// P1 · Today: proof of profit. GET /merchants/{id}/summary?include_sources=true. All amounts are the backend's.
import { ChevronLeft, ChevronRight, CircleHelp, Download, Mic, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { apiUrl, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { Badge, LoadState, Money, clockTime, count, longDate } from '../components/ui'

/** Calendar step on an IST date string ("2026-11-15", -1) -> "2026-11-14". */
export function shiftDay(iso, n) {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

function plural(n, one, many = `${one}s`) {
  return `${count(n ?? 0)} ${n === 1 ? one : many}`
}

export default function Today() {
  const { merchantId, merchant, demoDate } = useMerchant()
  const [picked, setPicked] = useState(null)
  const day = picked || demoDate
  const isToday = day && day === demoDate
  const path = !day ? null : isToday
    ? `/merchants/${merchantId}/summary?include_sources=true`
    : `/merchants/${merchantId}/summary?start_date=${day}&end_date=${day}&include_sources=true`
  const summary = useApi(path)
  const s = summary.data
  const src = s?.sources || {}
  const pdf = day && apiUrl(`/merchants/${merchantId}/export/pdf?start_date=${day}&end_date=${day}`)
  const csv = day && apiUrl(`/merchants/${merchantId}/export/csv?start_date=${day}&end_date=${day}`)

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">05 · {merchant?.display_name || merchantId}</span>
          <h1>{isToday ? "Today's money." : `Money on ${longDate(day)}.`}</h1>
          <p className="lede">What the shop earned, with family money kept out. Every figure opens the ledger entries it came from.</p>
        </div>
        <div className="page-actions">
          <div className="daystep" aria-label="Day">
            <button type="button" onClick={() => setPicked(shiftDay(day, -1))} disabled={!day} aria-label="Previous day"><ChevronLeft /></button>
            <strong>{day ? longDate(day) : '…'}</strong>
            <button type="button" onClick={() => setPicked(shiftDay(day, 1))} disabled={!day || isToday} aria-label="Next day"><ChevronRight /></button>
          </div>
          {!isToday && <button type="button" className="btn" onClick={() => setPicked(null)}>Back to today</button>}
        </div>
      </header>

      {!s && <LoadState state={summary} what="the day's summary" />}
      {s && s.reconciliation_ok === false && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          The day's figures don't add up (reconciliation failed). This is a bug: don't use these numbers.</p>
      )}

      {s && (
        <div className="split">
          <section className="panel lime today-hero" aria-labelledby="profit-h">
            <div className="panel-head">
              <span className="label" id="profit-h">{s.profit.label}</span>
              {isToday && <span className="label">as of {clockTime(s.as_of)} IST</span>}
            </div>
            <Money amount={s.profit} sources={[...(src.business_sales || []), ...(src.expenses || [])]} className="today-big" />
            <p className="equation">
              <span data-tour="sales-figure"><small>Business sales</small><Money amount={s.business_sales} sources={src.business_sales} /></span>
              <i aria-hidden="true">−</i>
              <span><small>Expenses</small><Money amount={s.expenses} sources={src.expenses} /></span>
              <i aria-hidden="true">=</i>
              <span><small>{s.profit.label}</small><Money amount={s.profit} sources={[...(src.business_sales || []), ...(src.expenses || [])]} /></span>
            </p>
            <div className="today-hero-foot">
              <Badge kind="ledger" />
              <a className="btn" href="#/talk"><Mic aria-hidden="true" /> Hear it in {merchant?.preferred_language === 'te' ? 'Telugu' : 'Tamil'}</a>
            </div>
          </section>

          <div className="today-side">
            <section className="panel violet">
              <span className="label">Family money, kept out of sales</span>
              <Money amount={s.family_transfers} sources={src.family_transfers} className="side-fig" />
              <small>{plural(src.family_transfers?.length, 'payment')}</small>
            </section>
            {s.pending?.count > 0 && (
              <section className="panel signal">
                <span className="label">Waiting for an answer</span>
                <Money amount={s.pending} sources={src.pending} className="side-fig" />
                <small>{plural(s.pending.count, 'payment')}, not counted in sales or family yet. <a href="#/questions">Answer now</a></small>
              </section>
            )}
            <section className="panel sky">
              <span className="label">Everything that came in</span>
              <Money amount={s.total_collections} className="side-fig" />
              <small>All UPI payments, before sorting</small>
            </section>
            <section className="panel">
              <dl className="kv">
                <dt>Refunds</dt><dd><Money amount={s.refunds} sources={src.refunds} /></dd>
                <dt>Reversals</dt><dd><Money amount={s.reversals} sources={src.reversals} /></dd>
              </dl>
            </section>
          </div>
        </div>
      )}

      {s && (
        <>
          <p className="plain-bar"><CircleHelp aria-hidden="true" /><span><b>In plain language:</b> {s.scope_note}</span></p>
          <p className="note">{s.attribution_note}</p>
          <div className="page-actions" style={{ justifyContent: 'start' }}>
            {pdf ? (
              <>
                <a className="btn" href={pdf} target="_blank" rel="noreferrer"><Download aria-hidden="true" /> CA pack PDF</a>
                <a className="btn" href={csv} target="_blank" rel="noreferrer"><Download aria-hidden="true" /> CSV for this day</a>
              </>
            ) : <span className="note">Exports need the live backend.</span>}
          </div>
        </>
      )}
    </>
  )
}
