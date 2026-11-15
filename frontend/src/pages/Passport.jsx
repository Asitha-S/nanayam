// P4 · Credit passport (show only). GET /merchants/{id}/passport.
// Every figure on screen is the backend's *_display string, shown through <Money>. The *_paise integers are used only
// to scale the bars. No score, no limit, no eligibility: a summary the merchant may choose to share.
import '../styles/passport.css'
import { Hourglass, Info, RefreshCw, ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { LoadState, Money, count, monthLabel } from '../components/ui'

function hintFor(error) {
  if (error?.code === 'UNREACHABLE') return 'Start the backend on port 8000, then try again.'
  if (error?.code === 'NO_FIXTURE') return 'Fixtures mode has no passport for this merchant.'
  if (error?.code === 'NOT_FOUND') return 'Check the merchant, then try again.'
  return 'Try again in a moment.'
}

/** One bar of the pair. Length = this month's paise / the largest month's raw collections (drawing only). */
function Bar({ kind, label, paise, max, display }) {
  const share = typeof paise === 'number' && max > 0 ? Math.min(1, Math.max(0, paise / max)) : 0
  return (
    <div className={`pp-bar pp-${kind}`}>
      <svg className="pp-svg" width="100%" height="28" aria-hidden="true" focusable="false">
        {share > 0 && <rect x="0.75" y="1" width={`${(share * 100).toFixed(2)}%`} height="26" rx="6" />}
      </svg>
      <span className="pp-val"><span className="visually-hidden">{label}: </span><Money amount={display} /></span>
    </div>
  )
}

function MonthChart({ months }) {
  const max = Math.max(0, ...months.map((m) => m.raw_collections_paise).filter((v) => typeof v === 'number'))
  return (
    <div className="pp-chart">
      {months.map((m) => (
        <div className="pp-month" key={m.month} role="group" aria-label={monthLabel(m.month)}>
          <div className="pp-month-name">
            <b>{monthLabel(m.month)}</b>
            {m.unresolved_count > 0 && <span className="chip pending">{count(m.unresolved_count)} waiting</span>}
          </div>
          <div className="pp-pair">
            <Bar kind="raw" label="Raw collections" paise={m.raw_collections_paise} max={max} display={m.raw_collections_display} />
            <Bar kind="rec" label="Recorded business income" paise={m.recorded_income_paise} max={max} display={m.recorded_income_display} />
          </div>
        </div>
      ))}
    </div>
  )
}

function Breakdown({ months }) {
  return (
    <section className="pp-table-wrap" aria-labelledby="pp-table-h">
      <h2 id="pp-table-h">Month by month</h2>
      <div className="dtable pp-table" role="table" aria-label="Passport months">
        <div className="tr th" role="row">
          <span role="columnheader">Month</span>
          <span role="columnheader" className="num">Raw collections</span>
          <span role="columnheader" className="num">Family transfers</span>
          <span role="columnheader" className="num">Refunds and reversals</span>
          <span role="columnheader" className="num">Business sales</span>
          <span role="columnheader" className="num">Expenses</span>
          <span role="columnheader" className="num is-rec">Recorded business income</span>
          <span role="columnheader" className="num">Unresolved</span>
        </div>
        {months.map((m) => (
          <div className="tr" role="row" key={m.month}>
            <span role="cell">{monthLabel(m.month)}</span>
            <span role="cell" className="num"><Money amount={m.raw_collections_display} /></span>
            <span role="cell" className="num"><Money amount={m.family_transfers_display} /></span>
            <span role="cell" className="num"><Money amount={m.refunds_reversals_display} /></span>
            <span role="cell" className="num"><Money amount={m.business_sales_display} /></span>
            <span role="cell" className="num"><Money amount={m.expenses_display} /></span>
            <span role="cell" className="num is-rec"><Money amount={m.recorded_income_display} /></span>
            <span role="cell" className="num">
              {m.unresolved_count > 0
                ? <span className="chip pending">{count(m.unresolved_count)} waiting</span>
                : <span className="chip muted">none</span>}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

function Unresolved({ months, owner }) {
  const waiting = months.filter((m) => m.unresolved_count > 0)
  const total = waiting.reduce((n, m) => n + m.unresolved_count, 0) // a count of payments, not money
  if (!total) {
    return <p className="note">No unresolved payments: every payment in these months is sorted into sale or family.</p>
  }
  const who = owner || 'the merchant'
  return (
    <section className="panel signal pp-unresolved" aria-label="Unresolved payments">
      <Hourglass aria-hidden="true" />
      <div>
        <p>
          <b>{count(total)} {total === 1 ? 'payment is' : 'payments are'} still waiting for {who}'s answer</b>{' '}
          ({waiting.map((m) => `${monthLabel(m.month)}: ${count(m.unresolved_count)}`).join(', ')}).
        </p>
        <p>
          Naanayam wasn't sure whether these were sales or family money, so it asked instead of guessing. Until {who} answers,
          they are in raw collections but not in recorded business income. <a href="#/questions">Answer them on Questions</a>
        </p>
      </div>
    </section>
  )
}

export default function Passport() {
  const { merchantId, merchant } = useMerchant()
  const passport = useApi(`/merchants/${merchantId}/passport`)
  const p = passport.data
  const months = p?.months || []
  const period = months.length > 1
    ? `${monthLabel(months[0].month)} – ${monthLabel(months[months.length - 1].month)}`
    : monthLabel(months[0]?.month)
  const owner = merchant?.owner_name
  const valid = p?.ledger_verify_status === 'VALID'
  const share = p?.share_of_collections_that_were_business_sales

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">09 · {merchant?.display_name || merchantId}</span>
          <h1>Credit passport.</h1>
          <p className="lede">
            What a lender would see if {owner || 'the merchant'} chooses to share it: everything that came in by UPI, next to the
            part that was business income, month by month, from the same ledger.
          </p>
        </div>
      </header>

      <p className="plain-bar pp-banner" role="note">
        <Info aria-hidden="true" />
        <span><b>Shown only.</b> Not a credit score or a loan decision.</span>
      </p>

      {!p && passport.error && (
        <div className="error-banner pp-error" role="alert">
          <TriangleAlert aria-hidden="true" />
          <span>Couldn't load the passport: {passport.error.message.replace(/\.$/, '')}. {hintFor(passport.error)}</span>
          <button type="button" className="btn" onClick={passport.reload}><RefreshCw aria-hidden="true" /> Try again</button>
        </div>
      )}
      {!p && !passport.error && <LoadState state={passport} what="the passport" />}

      {p && !months.length && (
        <section className="empty">
          <h2>No complete months yet.</h2>
          <p>The passport uses complete calendar months before today. Come back after the first full month of payments.</p>
        </section>
      )}

      {p && months.length > 0 && (
        <>
          <div className="pp-split">
            <section className="panel pp-chart-panel" aria-labelledby="pp-chart-h">
              <h2 id="pp-chart-h">Came in vs business income</h2>
              <p className="pp-lede">Each month: all UPI collections, and the part the ledger records as business income.</p>
              <ul className="pp-legend">
                <li><i className="pp-swatch raw" aria-hidden="true" />Raw collections (everything that came in)</li>
                <li><i className="pp-swatch rec" aria-hidden="true" />Recorded business income (business sales)</li>
              </ul>
              <MonthChart months={months} />
              <p className="pp-gap-note">
                <Info aria-hidden="true" />
                <span>The gap is family money, refunds and reversals, and payments still waiting for an answer. None of it counts as business income.</span>
              </p>
            </section>

            <div className="pp-side">
              <section className="panel lime">
                <span className="label">Recorded business income · {period}</span>
                <Money amount={p.totals?.recorded_business_income} className="pp-total" />
                <small>Business sales only, as recorded in the ledger.</small>
              </section>
              <section className="panel sky">
                <span className="label">Raw collections · {period}</span>
                <Money amount={p.totals?.raw_collections} className="pp-total" />
                <small>All UPI payments, before sorting.</small>
              </section>
              <section className="panel pp-facts">
                {typeof share === 'number' && (
                  <div>
                    <span className="pp-share">{(share * 100).toFixed(1)}%</span>
                    <p className="note">of collections were business sales</p>
                  </div>
                )}
                <p className={`pp-verify ${valid ? 'is-valid' : 'is-bad'}`}>
                  {valid ? <ShieldCheck aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
                  <span>
                    Ledger check: <b>{p.ledger_verify_status || 'unknown'}</b>.{' '}
                    {valid ? 'Every entry behind these figures is hash-chained.' : <>Don't share this passport. <a href="#/ledger">Open the ledger</a></>}
                  </span>
                </p>
                <div className="pp-fine">
                  <p>{p.label}</p>
                  <p>{p.consent_note}</p>
                  <p>UPI payments only: cash sales are not in Naanayam.</p>
                </div>
              </section>
            </div>
          </div>

          <Unresolved months={months} owner={owner} />
          <Breakdown months={months} />
        </>
      )}
    </>
  )
}
