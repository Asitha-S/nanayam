// P1 · Questions. GET /merchants/{id}/questions?status=OPEN&date={demoDate} for today, and status=OPEN without a date
// for the older open questions the seed keeps on purpose. Every card is bound to its own question_id; nothing is
// opened by list position. #/questions?q=Q-... (from the Soundbox) highlights or opens that one.
import '../styles/soundbox.css'
import { ChevronDown, ChevronUp, Radio, RotateCcw, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { useStrings } from '../app/strings'
import QuestionCard from '../components/QuestionCard'
import { LoadState, Money, clockTime, confidenceText, count, longDate } from '../components/ui'

/** useApi keeps the previous path's data when a new fetch fails; never show another merchant's questions. */
function forMerchant(state, merchantId) {
  return state.data && state.data.merchant_id && state.data.merchant_id !== merchantId ? { ...state, data: null } : state
}

const byNewest = (a, b) => (a.timestamp === b.timestamp ? (a.question_id < b.question_id ? 1 : -1) : a.timestamp < b.timestamp ? 1 : -1)

/** Open items plus the ones answered on this screen (kept so their result stays visible after the list refetches). */
function withAnswered(items, answered, keep) {
  const ids = new Set(items.map((q) => q.question_id))
  return [...items, ...Object.values(answered).filter((q) => !ids.has(q.question_id) && keep(q))].sort(byNewest)
}

function ErrorBanner({ state, what }) {
  return (
    <div className="qs-error">
      <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
        <span>Couldn't load {what}: {state.error.message}. Check that the backend is running, then reload.</span></p>
      <button type="button" className="btn" onClick={state.reload}><RotateCcw aria-hidden="true" /> Reload</button>
    </div>
  )
}

export default function Questions({ params }) {
  const { merchantId, merchant, language, demoDate } = useMerchant()
  const t = useStrings()
  const today = forMerchant(useApi(demoDate ? `/merchants/${merchantId}/questions?status=OPEN&date=${demoDate}` : null, { pollMs: 8000 }), merchantId)
  const all = forMerchant(useApi(`/merchants/${merchantId}/questions?status=OPEN`, { pollMs: 15000 }), merchantId)
  const [answered, setAnswered] = useState({}) // question_id -> question, answered here
  const [openOld, setOpenOld] = useState(params.q || null)
  const targetRef = useRef(null)
  const owner = merchant?.owner_name || merchantId

  // switching merchant closes every card (VOICE_AND_NOTICE 4.1a rule 4)
  useEffect(() => {
    setAnswered({})
    setOpenOld(null)
  }, [merchantId])
  useEffect(() => { if (params.q) setOpenOld(params.q) }, [params.q])

  const isToday = (q) => q.timestamp?.slice(0, 10) === demoDate
  const todayItems = withAnswered(today.data?.items || [], answered, isToday)
  const todayIds = new Set(todayItems.map((q) => q.question_id))
  const olderItems = withAnswered((all.data?.items || []).filter((q) => !isToday(q) && !todayIds.has(q.question_id)), answered, (q) => !isToday(q))
  const openCount = (today.data?.items?.length || 0) + (all.data ? all.data.items.filter((q) => !isToday(q)).length : 0)

  useEffect(() => {
    if (params.q && targetRef.current) targetRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [params.q, today.data, all.data])

  const onAnswered = (q) => setAnswered((a) => ({ ...a, [q.question_id]: q }))
  const reloadBoth = () => { today.reload(); all.reload() }
  const cardProps = { merchantId, language, demoDate, onAnswered, onReload: reloadBoth }

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">03 · {merchant?.display_name || merchantId}</span>
          <h1>Open questions.</h1>
          <p className="lede">Payments Naanayam wasn't sure about. Each one waits, out of sales and family, until {owner} answers in {t.languageName}. An answer is a new ledger entry; nothing is edited.</p>
        </div>
        {(today.data || all.data) && (
          <div className="page-actions">
            <span className="label">{count(openCount)} open</span>
          </div>
        )}
      </header>

      <div className="split qs-split">
        <section className="qs-group" aria-labelledby="qs-today-h">
          <div className="qs-group-head">
            <h2 id="qs-today-h">Today</h2>
            {demoDate && <span className="label">{longDate(demoDate)}</span>}
          </div>
          {!today.data && !today.error && <LoadState state={{ ...today, loading: true }} what="today's questions" />}
          {today.error && !today.data && <ErrorBanner state={today} what="today's questions" />}
          {today.data && !todayItems.length && (
            <div className="panel qs-empty">
              <h3>Nothing waiting today.</h3>
              <p>Confident payments were sorted silently. When one isn't clear, its question appears here and on the Soundbox.</p>
              <a className="btn" href="#/soundbox"><Radio aria-hidden="true" /> Open the Soundbox</a>
            </div>
          )}
          <div className="qs-cards">
            {todayItems.map((q) => (
              <div key={q.question_id} ref={params.q === q.question_id ? targetRef : undefined}
                className={params.q === q.question_id ? 'qs-target' : undefined}>
                <QuestionCard question={q} {...cardProps} />
              </div>
            ))}
          </div>
        </section>

        <aside className="panel sky qs-help" aria-labelledby="qs-help-h">
          <h2 id="qs-help-h" className="sb-h">What an answer does</h2>
          <dl className="qs-help-list">
            <dt><span className="chip sale">Sale</span> <span lang={t.lang}>{t.sale}</span></dt>
            <dd>Counts in today's sales and recorded profit.</dd>
            <dt><span className="chip family">Family</span> <span lang={t.lang}>{t.family}</span></dt>
            <dd>Kept out of sales. Shown on its own as family money.</dd>
            <dt><span lang={t.lang}>{t.rememberAlways}</span></dt>
            <dd>Naanayam remembers the person: their future payments follow your instruction. Past entries never change.</dd>
            <dt><span lang={t.lang}>{t.rememberOnce}</span></dt>
            <dd>Only this payment. The answer still helps the next guess for this person.</dd>
          </dl>
          <p className="note">Tap a wrong answer by mistake? Change it: the correction is another new entry.</p>
        </aside>
      </div>

      <section className="qs-group qs-older" aria-labelledby="qs-older-h">
        <div className="qs-group-head">
          <h2 id="qs-older-h">Older open questions</h2>
          {all.data && <span className="label">{count(olderItems.length)} from before today</span>}
        </div>
        <p className="note">Still waiting from earlier days. They stay open until {owner} answers; Naanayam never answers on its own.</p>
        {!all.data && !all.error && <LoadState state={all} what="older questions" />}
        {all.error && !all.data && <ErrorBanner state={all} what="older questions" />}
        {all.data && !olderItems.length && <p className="note">No older questions are open.</p>}
        {olderItems.length > 0 && (
          <ul className="qs-old">
            {olderItems.map((q) => {
              const open = openOld === q.question_id
              return (
                <li key={q.question_id} className={open ? 'is-open' : ''} ref={params.q === q.question_id ? targetRef : undefined}>
                  <div className="qs-old-row">
                    <span className="qs-old-date"><b>{longDate(q.timestamp)}</b><small>{clockTime(q.timestamp)} IST</small></span>
                    <span className="qs-old-who"><b>{q.payer_name}</b><small className="mono">{q.question_id}</small></span>
                    <span className="qs-old-guess">
                      <span className={`chip ${q.suggested_classification === 'FAMILY' ? 'family' : 'sale'}`}>{q.suggested_classification === 'FAMILY' ? 'Family?' : 'Sale?'}</span>
                      <small>{typeof q.confidence === 'number' ? `${confidenceText(q.confidence)} sure` : 'Your instruction'}</small>
                    </span>
                    <Money amount={q.amount_display} className="qs-old-amt" />
                    <button type="button" className="btn" aria-expanded={open} aria-controls={`qs-card-${q.question_id}`}
                      onClick={() => setOpenOld(open ? null : q.question_id)}>
                      {open ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />} {open ? 'Close' : answered[q.question_id] ? 'Result' : 'Answer'}
                    </button>
                  </div>
                  {open && (
                    <div className="qs-old-card" id={`qs-card-${q.question_id}`}>
                      <QuestionCard question={q} {...cardProps} />
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </>
  )
}
