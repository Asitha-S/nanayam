// GST threshold watch: this financial year's business sales against the ₹40 lakh GST registration threshold for goods.
// GET /merchants/{id}/threshold-watch. Every figure, the percent and the months left come from the backend; the bar only
// draws the backend's percent. Business sales, never total UPI collections (shown below it, labelled). Not tax advice.
import '../styles/threshold.css'
import { useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { Badge, LoadState, longDate } from './ui'

export default function ThresholdWatch({ compact = false }) {
  const { merchantId, merchant } = useMerchant()
  const state = useApi(`/merchants/${merchantId}/threshold-watch`)
  const w = state.data?.merchant_id === merchantId ? state.data : null
  const lang = merchant?.preferred_language === 'te' ? 'te' : 'ta'
  const headId = compact ? 'tw-h-compact' : 'tw-h'

  if (!w) {
    return (
      <section className={`panel tw ${compact ? 'is-compact' : ''}`} aria-labelledby={headId}>
        <span className="label" id={headId}>GST threshold watch</span>
        <LoadState state={state} what="the GST threshold watch" />
      </section>
    )
  }
  const local = w.note?.[lang]
  const bar = Math.min(100, Math.max(0, w.used_percent))
  return (
    <section className={`panel tw ${compact ? 'is-compact' : ''} ${w.crossed ? 'is-crossed' : ''}`} aria-labelledby={headId}
      data-testid="threshold-watch">
      <div className="panel-head">
        <span className="label" id={headId}>GST threshold watch</span>
        <span className="label">FY {w.financial_year} · 1 Apr to {longDate(w.end_date)}</span>
      </div>
      <div className="tw-main">
        <div className="tw-fig">
          <small>{w.business_sales.label}</small>
          <b className="money tw-big">{w.business_sales.amount_display}</b>
        </div>
        <div className="tw-of">
          <small>{w.threshold.label}</small>
          <b className="money">{w.threshold.amount_display}</b>
        </div>
      </div>
      <div className="tw-bar" role="progressbar" aria-label="Share of the GST threshold used" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={w.used_percent} aria-valuetext={`${w.used_percent_display} of ${w.threshold.amount_display}`}>
        <span style={{ width: `${bar}%` }} />
      </div>
      <p className="tw-stats">
        <span><b>{w.used_percent_display}</b> used</span>
        <span><b>{w.remaining.amount_display}</b> to go</span>
        <span><b>{w.months_remaining_display}</b> left in this financial year</span>
      </p>
      <p className="tw-collections">
        <small>{w.total_collections.label}</small>
        <span className="money">{w.total_collections.amount_display}</span>
      </p>
      {w.note?.en && (
        <div className="tw-note">
          {local && <p className="tw-local" lang={lang}>{local}</p>}
          <p>{w.note.en}</p>
        </div>
      )}
      {w.pending_note && <p className="note">{w.pending_note}</p>}
      {!compact && <p className="tw-foot"><Badge kind="ledger" /><span>From your ledger. Not tax advice: talk to a CA.</span></p>}
    </section>
  )
}
