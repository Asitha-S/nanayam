// P3 · Notice mode: one sample GST notice set beside the ledger for the same period, for a CA.
// GET /merchants/{id}/tax-summary, POST /notices/analyse (multipart), GET /merchants/{id}/notices/{nid}/evidence,
// export links (GET .../export/pdf|csv). Every amount is the backend's display string; nothing is computed here.
import '../styles/notice.css'
import {
  CircleAlert, Download, FileText, FileUp, Info, ListChecks, RotateCcw, Scale, ScanText, TriangleAlert,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import sampleNoticeUrl from '../../../assets/notice/sample_notice.png'
import { USING_FIXTURES, apiUrl, get, post, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { go } from '../app/route'
import { Badge, LoadState, Money, clockTime, confidenceText, count, longDate } from '../components/ui'

const SAMPLE_KEY = 'sample_notice_v1'
const CACHE_PREFIX = 'naanayam.notice.'
const MAX_LINKED = 150 // amounts with more source entries than this open the ledger instead of every entry

const TREATMENT = { EXEMPT_LIKELY: 'Likely exempt', TAXABLE_LIKELY: 'Likely taxable', UNKNOWN: 'Unknown' }

const FIELDS = [
  ['notice_title', 'Title'],
  ['issuing_office', 'Issued by'],
  ['reference_number', 'Reference'],
  ['issue_date', 'Date of issue'],
  ['period_start', 'Period from'],
  ['period_end', 'Period to'],
  ['amount_questioned_paise', 'Amount questioned'],
  ['response_deadline', 'Reply by'],
  ['documents_requested', 'Documents asked for'],
]
const DATE_FIELDS = new Set(['issue_date', 'period_start', 'period_end', 'response_deadline'])

function words(s) {
  const t = (s || '').toLowerCase().replaceAll('_', ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

function plural(n, one, many = `${one}s`) {
  return `${count(n ?? 0)} ${n === 1 ? one : many}`
}

function periodText(p) {
  return p ? `${longDate(p.start_date)} to ${longDate(p.end_date)}` : ''
}

/** The analyse response for a notice, kept for this tab so the fields survive a reload (convenience only). */
function readCached(id) {
  try {
    const raw = window.sessionStorage.getItem(CACHE_PREFIX + id)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}
function writeCached(data) {
  try {
    window.sessionStorage.setItem(CACHE_PREFIX + data.notice_id, JSON.stringify(data))
  } catch {
    /* storage blocked: the fields just won't survive a reload */
  }
}

function ErrorBanner({ error, hint }) {
  if (!error) return null
  return (
    <p className="error-banner" role="alert">
      <TriangleAlert aria-hidden="true" />
      <span><b>{error.message}</b>{hint ? ` ${hint}` : ''}</span>
    </p>
  )
}

function analyseHint(e) {
  if (e.code === 'SARVAM_UNAVAILABLE') return 'Only the sample notice can be read today: tick “This is the sample notice” and try again.'
  if (e.code === 'VALIDATION_ERROR') return 'Pick the committed sample notice image (assets/notice/sample_notice.png) and try again.'
  if (e.code === 'CACHE_MISS') return 'There is no cached reading for this file. Use the sample notice.'
  if (e.code === 'UNREACHABLE') return 'Start the backend on port 8000, then try again.'
  if (e.code === 'NO_FIXTURE') return 'Fixtures mode has no response for this request.'
  return 'Try again. If it keeps failing, check the backend log.'
}

function evidenceHint(e, who) {
  if (e.code === 'VALIDATION_ERROR') return 'No evidence is built without the notice period. Read the notice again.'
  if (e.code === 'NOT_FOUND') return `This notice is not stored for ${who}: it may belong to the other merchant, or the demo was reset. Read the notice again.`
  if (e.code === 'UNREACHABLE') return 'Start the backend on port 8000, then reload.'
  return 'Reload the page. If it keeps failing, check the backend log.'
}

/** Ledger entry ids behind each payment (from GET /payments/{txn}), so its amount opens exactly those entries. */
function usePaymentSources(txnIds) {
  const key = txnIds.join(',')
  const [map, setMap] = useState({})
  useEffect(() => {
    if (!key) {
      setMap({})
      return undefined
    }
    let live = true
    const ids = key.split(',')
    Promise.allSettled(ids.map((id) => get(`/payments/${encodeURIComponent(id)}`))).then((results) => {
      if (!live) return
      const next = {}
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') {
          next[ids[i]] = (r.value?.classification_history || []).map((h) => h.ledger_entry_id).filter(Boolean)
        }
      })
      setMap(next)
    })
    return () => { live = false }
  }, [key])
  return map
}

function linked(ids) {
  return ids && ids.length && ids.length <= MAX_LINKED ? ids : undefined
}

/* ---------- reader ---------- */

function Reader({ merchantId, onRead }) {
  const [file, setFile] = useState(null)
  const [sample, setSample] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loadingSample, setLoadingSample] = useState(false)

  /** The committed sample (assets/notice/sample_notice.png), bundled with the app: no file dialog in the demo. */
  async function pickSample() {
    setLoadingSample(true)
    setError(null)
    try {
      const res = await fetch(sampleNoticeUrl)
      if (!res.ok) throw new Error(`The sample notice image didn't load (HTTP ${res.status})`)
      setFile(new File([await res.blob()], 'sample_notice.png', { type: 'image/png' }))
      setSample(true)
    } catch (err) {
      setError(err)
    } finally {
      setLoadingSample(false)
    }
  }

  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) {
      setPreview(null)
      return undefined
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  async function read(e) {
    e.preventDefault()
    if (!file || busy) return
    const body = new FormData()
    body.append('merchant_id', merchantId)
    body.append('file', file)
    if (sample) body.append('demo_key', SAMPLE_KEY)
    setBusy(true)
    setError(null)
    try {
      const data = await post('/notices/analyse', body)
      onRead(data)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel nt-reader" aria-labelledby="nt-reader-h" data-tour="notice-read">
      <div className="panel-head">
        <span className="label" id="nt-reader-h">The notice</span>
        <span className="label">PNG, JPG or PDF</span>
      </div>
      <h2>Read the sample notice.</h2>
      <form className="nt-form" onSubmit={read}>
        <label className={`nt-drop ${file ? 'has-file' : ''}`}>
          <input type="file" accept="image/png,image/jpeg,application/pdf" className="visually-hidden"
            onChange={(e) => { setFile(e.target.files?.[0] || null); setError(null) }} />
          {preview ? (
            <img src={preview} alt="The notice you picked" />
          ) : (
            <span className="nt-drop-empty">
              {file ? <FileText aria-hidden="true" /> : <FileUp aria-hidden="true" />}
              <b>{file ? file.name : 'Pick the notice image'}</b>
              <small>{file ? 'PDF picked. Read it below.' : 'PNG, JPG or PDF. Or use the sample below.'}</small>
            </span>
          )}
        </label>
        {file && preview && <p className="note nt-file">{file.name} · <span>click the image to pick another</span></p>}
        <button type="button" className="btn nt-sample" onClick={pickSample} disabled={loadingSample || busy}>
          <FileText aria-hidden="true" /> {loadingSample ? 'Loading the sample…' : 'Use the sample notice'}
        </button>

        <label className="nt-check">
          <input type="checkbox" checked={sample} onChange={(e) => setSample(e.target.checked)} />
          <span>This is the sample notice <small className="mono">demo key {SAMPLE_KEY}</small></span>
        </label>

        <div className="nt-form-foot">
          <button type="submit" className="btn primary big" disabled={!file || busy} aria-busy={busy}>
            <ScanText aria-hidden="true" /> {busy ? 'Reading…' : 'Read the notice'}
          </button>
          <p className="note">Only the committed sample can be read today. Any other notice gets “not available yet”.</p>
        </div>
        <ErrorBanner error={error} hint={error && analyseHint(error)} />
      </form>
    </section>
  )
}

/* ---------- GST picture (tax summary) ---------- */

function GstPicture({ merchantId }) {
  const tax = useApi(`/merchants/${merchantId}/tax-summary`)
  const t = tax.data?.merchant_id === merchantId ? tax.data : null
  const flags = t?.flags || []
  const mixed = flags.includes('MIXED_CATEGORY_SPLIT_UNKNOWN') || t?.gst_treatment === 'UNKNOWN'
  const caToConfirm = t && (t.ca_review_required || flags.includes('CA_REVIEW_REQUIRED'))

  return (
    <section className="panel sun nt-gst" aria-labelledby="nt-gst-h">
      <div className="panel-head">
        <span className="label" id="nt-gst-h">GST picture</span>
        {t && <span className="label">{periodText(t.period)}</span>}
      </div>
      {!t && <LoadState state={tax} what="the GST picture" />}
      {tax.error && !t && <p className="note">Check that the backend is running, then reload.</p>}
      {t && (
        <>
          <p className="nt-gst-treat">{TREATMENT[t.gst_treatment] || t.gst_treatment}</p>
          <div className="nt-gst-flags">
            {caToConfirm && <span className="chip nt-ca">CA to confirm</span>}
            {mixed && <span className="chip muted">Split not known</span>}
          </div>
          <dl className="kv">
            <dt>Category</dt><dd>{words(t.business_category)} · <b>Declared by merchant</b></dd>
            <dt>Basis</dt><dd>{t.gst_treatment_basis}</dd>
          </dl>
          {mixed && (
            <p className="nt-gst-mixed"><Info aria-hidden="true" />
              <span>Mixed goods: how much was exempt and how much taxable is not known, so no split is estimated. Not from payments, not from purchases.</span>
            </p>
          )}
          <ul className="nt-figs">
            <li><span>Everything that came in</span><Money amount={t.total_collections} /></li>
            <li><span>Business sales</span><Money amount={t.business_sales} /></li>
            <li><span>Family money</span><Money amount={t.family_transfers} /></li>
            <li><span>Waiting for an answer <small>{plural(t.pending?.count, 'payment')}</small></span><Money amount={t.pending} /></li>
            <li><span>Expenses you entered <small>{plural(t.expenses_recorded?.count, 'entry', 'entries')}</small></span><Money amount={t.expenses_recorded} /></li>
          </ul>
          <div className="nt-gst-foot">
            <Badge kind="ledger" />
            <span className="note">Expenses are purchases. They never stand in for what was sold.</span>
          </div>
        </>
      )}
    </section>
  )
}

/* ---------- what the notice says ---------- */

function FieldValue({ name, field, ev }) {
  const missing = !field || field.origin === 'NOT_FOUND' || field.value === null || field.value === undefined
  if (missing) return <span className="nt-missing">Not found on the notice</span>
  if (name === 'amount_questioned_paise') {
    return ev?.amount_questioned?.amount_display
      ? <Money amount={ev.amount_questioned} />
      : <span className="note">Shown with the ledger figures once they load.</span>
  }
  if (Array.isArray(field.value)) {
    return <ul className="nt-docs">{field.value.map((v) => <li key={v}>{v}</li>)}</ul>
  }
  if (DATE_FIELDS.has(name)) return <span>{longDate(String(field.value))}</span>
  return <span>{String(field.value)}</span>
}

function OriginBadge({ origin }) {
  if (origin === 'EXTRACTED_FROM_NOTICE') return <Badge kind="notice" />
  if (origin === 'DERIVED_FROM_LEDGER') return <Badge kind="ledger" />
  return <Badge kind="missing"><CircleAlert aria-hidden="true" /> Not found</Badge>
}

function Explanation({ explanation, language }) {
  const lang = explanation?.language || language
  const langName = lang === 'te' ? 'Telugu' : 'Tamil'
  const audio = explanation?.audio_id && apiUrl(`/audio/${encodeURIComponent(explanation.audio_id)}`)
  return (
    <div className="nt-explain">
      <span className="label">The notice in {langName}</span>
      {explanation?.text
        ? <p lang={lang}>{explanation.text}</p>
        : <p className="nt-explain-none">The {langName} explanation is not available yet. The fields above are what was read.</p>}
      {explanation?.text && audio && <audio controls preload="none" src={audio} aria-label={`Hear the ${langName} explanation`} />}
    </div>
  )
}

function NoticeFields({ analysis, ev, language }) {
  if (!analysis) {
    return (
      <section className="panel nt-fields is-empty" aria-labelledby="nt-fields-h">
        <span className="label" id="nt-fields-h">What the notice says</span>
        <p>The fields read from the notice are shown right after reading it, in the same browser tab. Read the notice again to see them here.</p>
      </section>
    )
  }
  const fields = analysis.fields || {}
  const known = new Set(FIELDS.map(([k]) => k))
  const rows = [...FIELDS, ...Object.keys(fields).filter((k) => !known.has(k)).map((k) => [k, words(k)])]
  return (
    <section className="panel nt-fields" aria-labelledby="nt-fields-h">
      <div className="panel-head">
        <span className="label" id="nt-fields-h">What the notice says</span>
        <span className="label mono">{analysis.notice_id}</span>
      </div>
      {analysis.from_cache && <p className="note nt-cached">Cached reading of the sample notice, not read live just now.</p>}
      <dl className="nt-fieldlist">
        {rows.map(([name, label]) => {
          const f = fields[name]
          return (
            <div key={name} className="nt-field">
              <dt>{label}</dt>
              <dd>
                <FieldValue name={name} field={f} ev={ev} />
                <span className="nt-field-meta">
                  <OriginBadge origin={f?.origin || 'NOT_FOUND'} />
                  {typeof f?.confidence === 'number' && f.origin !== 'NOT_FOUND' && (
                    <small>{confidenceText(f.confidence)} confidence</small>
                  )}
                </span>
              </dd>
            </div>
          )
        })}
      </dl>
      {analysis.missing_fields?.length > 0 && (
        <p className="note">Not found on the notice: {analysis.missing_fields.map(words).join(', ')}.</p>
      )}
      <Explanation explanation={analysis.explanation} language={language} />
    </section>
  )
}

/* ---------- what the ledger shows ---------- */

const BUCKETS = [
  ['total_collections', 'Everything that came in', null, 'All UPI payments'],
  ['business_sales', 'Business sales', 'business_sales'],
  ['family_transfers', 'Family money', 'family_transfers'],
  ['refunds_and_reversals', 'Refunds and reversals', ['refunds', 'reversals']],
  ['unresolved', 'Waiting for an answer', 'pending'],
  ['expenses_recorded', 'Expenses you entered', 'expenses'],
]

function bucketSources(sources, key) {
  if (!sources || !key) return undefined
  const ids = Array.isArray(key) ? key.flatMap((k) => sources[k] || []) : sources[key]
  return linked(ids)
}

function Evidence({ evidence, ev, sources, who }) {
  if (!ev) {
    return (
      <section className="panel nt-evidence" aria-labelledby="nt-ev-h" data-tour="notice-evidence">
        <span className="label" id="nt-ev-h">What your ledger shows</span>
        {evidence.error
          ? <ErrorBanner error={evidence.error} hint={evidenceHint(evidence.error, who)} />
          : <LoadState state={evidence} what="the ledger evidence" />}
      </section>
    )
  }
  const lv = ev.ledger_view || {}
  const aq = ev.amount_questioned
  const diff = ev.difference_vs_notice
  const tampered = ev.ledger_verify_status && ev.ledger_verify_status !== 'VALID'
  return (
    <section className="panel lime nt-evidence" aria-labelledby="nt-ev-h" data-tour="notice-evidence">
      <div className="panel-head">
        <span className="label" id="nt-ev-h">What your ledger shows · {periodText(ev.period)}</span>
        <Badge kind="ledger" />
      </div>

      <div className="nt-compare">
        <div>
          <small>Amount on the notice</small>
          {aq?.origin === 'NOT_FOUND' || !aq?.amount_display
            ? <span className="nt-missing">Not found on the notice</span>
            : <Money amount={aq} className="nt-big" />}
          <Badge kind={aq?.origin === 'NOT_FOUND' ? 'missing' : 'notice'}>{aq?.origin === 'NOT_FOUND' ? 'Not found' : undefined}</Badge>
        </div>
        <div>
          <small>UPI collections in your ledger</small>
          <Money amount={lv.total_collections} className="nt-big" />
          <Badge kind="ledger" />
        </div>
      </div>

      {diff && (
        <div className="nt-diff">
          {diff.amount_display != null && (
            <span className="nt-diff-fig"><small>Difference</small><Money amount={diff} /></span>
          )}
          <p>{diff.explanation}</p>
        </div>
      )}

      <ul className="nt-buckets" aria-label="Ledger figures for the notice period">
        {BUCKETS.map(([key, label, srcKey, note]) => {
          const b = lv[key]
          if (!b) return null
          const sub = typeof b.entry_count === 'number' ? plural(b.entry_count, 'entry', 'entries') : note
          return (
            <li key={key} className={key === 'unresolved' && b.entry_count > 0 ? 'is-waiting' : ''}>
              <span><b>{label}</b>{sub && <small>{sub}</small>}</span>
              <Money amount={b} sources={bucketSources(sources, srcKey)} />
            </li>
          )
        })}
      </ul>

      <dl className="kv nt-ev-meta">
        <dt>GST treatment</dt><dd>{TREATMENT[ev.gst_treatment] || ev.gst_treatment} · CA to confirm</dd>
        <dt>Hash chain</dt>
        <dd className={tampered ? 'nt-bad' : ''}>{ev.ledger_verify_status}{tampered ? ': the ledger was changed after it was written. Do not use these figures.' : ''}</dd>
        {ev.as_of && (<><dt>As of</dt><dd className="mono">{longDate(ev.as_of)} {clockTime(ev.as_of)} IST</dd></>)}
      </dl>
    </section>
  )
}

function Unresolved({ ev, merchantId }) {
  const p = ev.period
  const list = useApi(`/merchants/${merchantId}/payments?start_date=${p.start_date}&end_date=${p.end_date}&classification=PENDING&limit=200`)
  const items = (list.data?.items || []).filter((x) => x.current_classification === 'PENDING')
  const sources = usePaymentSources(items.map((x) => x.transaction_id))
  const expected = ev.ledger_view?.unresolved?.entry_count ?? 0
  const waiting = expected > 0 || items.length > 0
  return (
    <section className={`panel nt-list ${waiting ? 'signal' : ''}`} aria-labelledby="nt-un-h">
      <span className="label" id="nt-un-h">Still waiting for an answer</span>
      {!list.data && <LoadState state={list} what="the waiting payments" />}
      {list.data && !items.length && (
        <p className="nt-list-empty">
          {expected > 0 ? `${plural(expected, 'payment')} in this period ${expected === 1 ? 'is' : 'are'} unconfirmed; the list could not be shown.` : 'Every payment in this period has an answer.'}
        </p>
      )}
      {items.length > 0 && (
        <ul className="nt-items">
          {items.map((x) => (
            <li key={x.transaction_id}>
              <span><b>{x.payer_name}</b><small>{longDate(x.timestamp)} · {clockTime(x.timestamp)}</small></span>
              <Money amount={x} sources={linked(sources[x.transaction_id])} />
            </li>
          ))}
        </ul>
      )}
      {list.data && typeof list.data.count === 'number' && list.data.count > items.length && items.length > 0 && (
        <p className="note">Showing {count(items.length)} of {count(list.data.count)}.</p>
      )}
      {waiting && <a className="nt-list-link" href="#/questions"><ListChecks aria-hidden="true" /> Answer them on the Questions screen</a>}
    </section>
  )
}

function FamilyExamples({ ev }) {
  const items = ev.family_transfer_examples || []
  const sources = usePaymentSources(items.map((x) => x.transaction_id))
  return (
    <section className="panel violet nt-list" aria-labelledby="nt-fam-h">
      <span className="label" id="nt-fam-h">Family money in this period</span>
      <p className="nt-list-sub">Largest first. Only payments the merchant labelled.</p>
      {!items.length && <p className="nt-list-empty">No family payments labelled by the merchant in this period.</p>}
      {items.length > 0 && (
        <ul className="nt-items">
          {items.map((x) => (
            <li key={x.transaction_id}>
              <span>
                <b>{x.payer_name}</b>
                <small>{longDate(x.date)} · {x.confirmed_by === 'MERCHANT_CONFIG' ? 'Your instruction' : 'Confirmed by the merchant'}</small>
              </span>
              <Money amount={x.amount_display} sources={linked(sources[x.transaction_id])} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Warnings({ ev }) {
  const items = ev.ca_review_warnings || []
  return (
    <section className="panel nt-list nt-warn" aria-labelledby="nt-warn-h">
      <span className="label" id="nt-warn-h">For the CA to check</span>
      {!items.length && <p className="nt-list-empty">No warnings.</p>}
      <ul>
        {items.map((w) => <li key={w}><CircleAlert aria-hidden="true" /><span>{w}</span></li>)}
      </ul>
    </section>
  )
}

function CaPack({ ev, merchantId }) {
  const q = `start_date=${ev.period.start_date}&end_date=${ev.period.end_date}`
  const pdf = apiUrl(`/merchants/${merchantId}/export/pdf?${q}`)
  const csv = apiUrl(`/merchants/${merchantId}/export/csv?${q}`)
  return (
    <section className="panel nt-pack" aria-labelledby="nt-pack-h">
      <div>
        <span className="label" id="nt-pack-h">CA pack · {periodText(ev.period)}</span>
        <p>The figures above as a PDF for the CA, and every ledger entry of the period as a CSV.</p>
      </div>
      <div className="page-actions">
        {pdf ? (
          <>
            <a className="btn ink" href={pdf} target="_blank" rel="noreferrer"><Download aria-hidden="true" /> CA pack PDF</a>
            <a className="btn" href={csv} target="_blank" rel="noreferrer"><Download aria-hidden="true" /> CSV for the period</a>
          </>
        ) : <span className="note">Exports need the live backend (fixtures mode has no files).</span>}
      </div>
    </section>
  )
}

/* ---------- page ---------- */

export default function Notice({ params }) {
  const { merchantId, merchant, language } = useMerchant()
  const noticeId = params.id || null
  const [lastRead, setLastRead] = useState(null)
  const [readerKey, setReaderKey] = useState(0)

  const analysis = useMemo(() => {
    if (!noticeId) return null
    if (lastRead?.notice_id === noticeId) return lastRead
    return readCached(noticeId)
  }, [noticeId, lastRead])

  const evidence = useApi(noticeId ? `/merchants/${merchantId}/notices/${encodeURIComponent(noticeId)}/evidence` : null)
  const ev = !evidence.error && evidence.data?.notice_id === noticeId ? evidence.data : null
  const period = ev?.period
  const summary = useApi(period
    ? `/merchants/${merchantId}/summary?start_date=${period.start_date}&end_date=${period.end_date}&include_sources=true`
    : null)
  const sources = summary.data?.period?.start_date === period?.start_date ? summary.data?.sources : null

  function onRead(data) {
    writeCached(data)
    setLastRead(data)
    go(`/notice?id=${encodeURIComponent(data.notice_id)}`)
  }

  function startOver() {
    setLastRead(null)
    setReaderKey((k) => k + 1)
    go('/notice')
  }

  const who = merchant?.display_name || merchantId

  return (
    <div className="nt">
      <header className="page-head">
        <div>
          <span className="label">08 · {who}</span>
          <h1>Notice mode.</h1>
          <p className="lede">One sample GST notice, read and set beside the ledger for the same period, so a CA can check it. Naanayam explains and organises records. It does not reply.</p>
        </div>
        {noticeId && (
          <div className="page-actions">
            <button type="button" className="btn" onClick={startOver}><RotateCcw aria-hidden="true" /> Read another notice</button>
          </div>
        )}
      </header>

      <div className="nt-top">
        <Reader key={readerKey} merchantId={merchantId} onRead={onRead} />
        <GstPicture merchantId={merchantId} />
      </div>

      {noticeId && (
        <div className="nt-body">
          <NoticeFields analysis={analysis} ev={ev} language={language} />
          <Evidence evidence={evidence} ev={ev} sources={sources} who={who} />
        </div>
      )}

      {ev && (
        <div className="grid-3 nt-lists">
          <Unresolved ev={ev} merchantId={merchantId} />
          <FamilyExamples ev={ev} />
          <Warnings ev={ev} />
        </div>
      )}

      {ev && <CaPack ev={ev} merchantId={merchantId} />}

      <p className="plain-bar nt-disclaimer">
        <Scale aria-hidden="true" />
        <span><b>Not legal advice.</b> No filing, no automatic replies. {analysis?.disclaimer || 'Naanayam explains and organises records. A CA must review.'}</span>
      </p>
      {USING_FIXTURES && <p className="note">Fixtures mode: every notice reads as the sample fixture.</p>}
    </div>
  )
}
