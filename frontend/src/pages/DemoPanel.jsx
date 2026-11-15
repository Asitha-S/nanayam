// Hidden · Demo controls for the presenter (#/demo, not in the rail).
// GET /health, POST /demo/reset, GET /demo/script, POST /demo/tamper; reads today's payments, ledger and verify.
// Device voices: this browser's speechSynthesis voices (no backend call).
// The scripted 15-payment day appears only here and in the judge tour.
import '../styles/demopanel.css'
import {
  ArrowRight, Check, CircleDashed, Construction, Radio, RefreshCw, RotateCcw, ShieldAlert, ShieldCheck,
  Smartphone, TriangleAlert, X,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { API_BASE, USING_FIXTURES, post, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { LoadState, Money, clockTime, count, longDate } from '../components/ui'

const MODE_TEXT = {
  cache_only: 'Never calls Sarvam: every scripted call comes from the committed cache.',
  cache_first: 'Uses the cache; calls Sarvam only on a miss.',
  live: 'Calls Sarvam every time.',
}
const ACTION_TEXT = { AUTO_CLASSIFY: 'sorted silently', ASK_MERCHANT: 'asked' }
const CLASS_TEXT = { SALE: 'Sale', FAMILY: 'Family', PENDING: 'Waiting' }

function words(s) {
  return (s || '').toLowerCase().replaceAll('_', ' ')
}

function shortHash(h) {
  return h ? `${h.slice(0, 6)}…${h.slice(-4)}` : '—'
}

/** A 404/403 from a /demo route itself (not "unknown merchant/entry"): the tools are switched off. */
function toolsOffError(e) {
  if (!e || e.code === 'NO_FIXTURE') return false
  if (e.status === 403) return true
  return e.status === 404 && !e.details?.merchant_id && !e.details?.ledger_entry_id
}

function writeHint(e) {
  if (toolsOffError(e)) return 'Demo tools are off on this backend (ENABLE_DEMO_TOOLS=false).'
  if (e.code === 'INVALID_STATE' && e.details?.reason === 'NO_SEED') return 'Seed the demo database first, then reset again.'
  if (e.code === 'NO_FIXTURE') return 'Fixtures mode has no response for this write; run it against the backend.'
  if (e.code === 'UNREACHABLE') return 'Start the backend on port 8000, then try again.'
  return 'Try again. If it keeps failing, check the backend log.'
}

function ErrorBanner({ error, hint }) {
  if (!error) return null
  return (
    <p className="error-banner" role="alert">
      <TriangleAlert aria-hidden="true" />
      <span><b>{error.message}</b> {hint}</span>
    </p>
  )
}

/** Two-step button: the first press asks, the second does it. */
function Confirm({ step, setStep, ask, label, yes, onYes, disabled }) {
  if (step === 'idle') {
    return (
      <button type="button" className="btn dp-arm" disabled={disabled} onClick={() => setStep('confirm')}>
        {label}
      </button>
    )
  }
  return (
    <div className="dp-confirm" role="group" aria-label="Confirm">
      <p>{ask}</p>
      <div className="dp-confirm-btns">
        <button type="button" className="btn dp-go" onClick={onYes} disabled={step === 'busy'} aria-busy={step === 'busy'}
          autoFocus>
          {step === 'busy' ? 'Working…' : yes}
        </button>
        <button type="button" className="btn" onClick={() => setStep('idle')} disabled={step === 'busy'}>
          <X aria-hidden="true" /> Cancel
        </button>
      </div>
    </div>
  )
}

/* ---------- health ---------- */

function Health({ health }) {
  const h = health.data
  return (
    <section className="panel ink dp-health" aria-labelledby="dp-health-h">
      <div className="panel-head">
        <span className="label" id="dp-health-h">Backend health · GET /health</span>
        <button type="button" className="btn dp-small" onClick={health.reload}><RefreshCw aria-hidden="true" /> Check</button>
      </div>
      {!h && <LoadState state={health} what="the backend health" />}
      {h && (
        <dl className="dp-kv">
          <dt>Status</dt><dd className={h.status === 'ok' ? 'is-ok' : 'is-bad'}>{h.status}</dd>
          <dt>Database</dt><dd className={h.db === 'ok' ? 'is-ok' : 'is-bad'}>{h.db}</dd>
          <dt>Demo mode</dt><dd><b className="mono">{h.demo_mode}</b><small>{MODE_TEXT[h.demo_mode]}</small></dd>
          <dt>Demo date</dt><dd><b>{longDate(h.demo_date)}</b><small className="mono">{h.demo_date} · the backend's “today”</small></dd>
          <dt>Model</dt><dd><b className="mono">{h.model_version}</b></dd>
          <dt>Threshold</dt><dd><b className="mono">{String(h.threshold)}</b><small>A model call at or above this is sorted silently; below it, the merchant is asked.</small></dd>
          <dt>Demo tools</dt><dd className={h.demo_tools ? 'is-ok' : 'is-warn'}>{h.demo_tools ? 'On' : 'Off'}</dd>
          <dt>Tampered</dt><dd className={h.tampered ? 'is-bad' : 'is-ok'}>{h.tampered ? 'Yes · reset the demo to undo it' : 'No'}</dd>
          <dt>Data</dt><dd className="mono">{USING_FIXTURES ? 'Fixtures (contract/fixtures)' : API_BASE}</dd>
        </dl>
      )}
    </section>
  )
}

/* ---------- reset ---------- */

function Reset({ toolsOff }) {
  const [step, setStep] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function run() {
    setStep('busy')
    setError(null)
    try {
      setResult(await post('/demo/reset', {}))
    } catch (e) {
      setError(e)
    } finally {
      setStep('idle')
    }
  }

  const pending = Object.entries(result?.pending_demo_payments || {})
  return (
    <section className="panel dp-action" aria-labelledby="dp-reset-h">
      <span className="label">Reset · POST /demo/reset</span>
      <h3 id="dp-reset-h">Start the demo day again.</h3>
      <p>Restores the committed seed: all history before the demo day, nothing on it. Today's payments, answers, expenses, read notices and any tamper are gone, and the script starts again at payment 1.</p>
      <Confirm step={step} setStep={setStep} disabled={toolsOff}
        label={<><RotateCcw aria-hidden="true" /> Reset the demo…</>}
        ask="Reset the shared demo database now? Every open screen changes."
        yes={<><RotateCcw aria-hidden="true" /> Yes, reset now</>} onYes={run} />
      <ErrorBanner error={error} hint={error && writeHint(error)} />
      {result && (
        <div className="dp-done" role="status">
          <Check aria-hidden="true" />
          <p>
            <b>Reset done.</b> Merchants {(result.merchants || []).join(', ')}; demo date {longDate(result.demo_date)}.
            {pending.length > 0 && <> Payments still to send: {pending.map(([m, n]) => `${m} ${count(n)}`).join(' · ')}.</>}
          </p>
        </div>
      )}
    </section>
  )
}

/* ---------- script ---------- */

function Outcome({ item, payment, isNext }) {
  if (!payment) {
    return isNext
      ? <span className="chip dp-next">Next</span>
      : <span className="dp-notyet"><CircleDashed aria-hidden="true" /> Not sent</span>
  }
  const now = payment.current_classification
  const matches = now === item.expected_classification
  const waiting = now === 'PENDING' && item.expected_action === 'ASK_MERCHANT'
  return (
    <span className="dp-now">
      <span className={`chip ${(now || '').toLowerCase()}`}>{CLASS_TEXT[now] || now}</span>
      {matches && <span className="dp-ok"><Check aria-hidden="true" /> as expected</span>}
      {waiting && <span className="dp-wait">asked, no answer yet</span>}
      {!matches && !waiting && <span className="dp-diff"><TriangleAlert aria-hidden="true" /> differs</span>}
    </span>
  )
}

function Script({ merchantId, toolsOff }) {
  const script = useApi(`/demo/script?merchant_id=${encodeURIComponent(merchantId)}`)
  const pays = useApi(`/merchants/${merchantId}/payments?limit=200`)
  const items = script.data?.merchant_id === merchantId ? script.data.items || [] : null
  const byId = new Map((pays.data?.items || []).map((p) => [p.transaction_id, p]))
  const sent = (i) => byId.has(i.transaction_id) || (!pays.data && i.injected)
  const done = items ? items.filter(sent).length : 0
  const next = items?.find((i) => !sent(i))

  return (
    <section className="panel dp-script" aria-labelledby="dp-script-h">
      <div className="panel-head">
        <div>
          <span className="label">Scripted demo day (used by the judge tour)</span>
          <h3 id="dp-script-h">{items ? `${count(done)} of ${count(items.length)} sent.` : 'The scripted day.'}</h3>
        </div>
        <a className="btn" href="#/soundbox"><Radio aria-hidden="true" /> Open the Soundbox</a>
      </div>
      <p className="note">
        {merchantId} · GET /demo/script. The judge tour sends these payments one by one. “Sent” means the payment is in
        today's payments list for {merchantId}. “Now” is its classification at this moment.
      </p>
      {!items && !script.error && <LoadState state={script} what="the demo script" />}
      {script.error && (
        <p className="dp-off-note">
          {toolsOff || toolsOffError(script.error)
            ? 'The demo script is not available: demo tools are off on this backend.'
            : `${script.error.message}. Only the scripted merchants (Murugan, Venkatesh) have a demo day.`}
        </p>
      )}
      {items && (
        <div className="dtable dp-table" role="table" aria-label="Demo script">
          <div className="tr th" role="row">
            <span>#</span><span>Time</span><span>Payer</span><span className="num">Amount</span><span>Expected</span><span>Now</span>
          </div>
          {items.map((i) => {
            const p = byId.get(i.transaction_id)
            const isNext = next?.transaction_id === i.transaction_id
            return (
              <div key={i.transaction_id} role="row" className={`tr ${isNext ? 'is-next' : ''} ${p ? 'is-sent' : ''}`}>
                <span className="mono">{i.demo_index}</span>
                <span className="mono">{i.time}</span>
                <span className="dp-payer"><b>{i.payer_name}</b><small className="mono">{i.transaction_id}</small></span>
                <span className="num"><Money amount={i.amount_display} /></span>
                <span className="dp-exp">
                  <span className={`chip ${(i.expected_classification || '').toLowerCase()}`}>{CLASS_TEXT[i.expected_classification] || i.expected_classification}</span>
                  <small>{ACTION_TEXT[i.expected_action] || words(i.expected_action)}</small>
                </span>
                <span><Outcome item={i} payment={p} isNext={isNext} /></span>
              </div>
            )
          })}
        </div>
      )}
      {pays.error && items && <p className="note">Couldn't load today's payments ({pays.error.message}); “sent” falls back to the script's own flag.</p>}
    </section>
  )
}

/* ---------- tamper ---------- */

function Tamper({ merchantId, demoDate, toolsOff, tampered }) {
  const ledger = useApi(demoDate ? `/merchants/${merchantId}/ledger?start_date=${demoDate}&end_date=${demoDate}&limit=200` : null)
  const verify = useApi(`/merchants/${merchantId}/ledger/verify`)
  const [entryId, setEntryId] = useState('')
  const [step, setStep] = useState('idle')
  const [done, setDone] = useState(null)
  const [error, setError] = useState(null)
  const items = ledger.data?.merchant_id === merchantId ? ledger.data.items || [] : null
  const entry = items?.find((e) => e.ledger_entry_id === entryId)
  const v = verify.data?.merchant_id === merchantId ? verify.data : null

  async function run() {
    setStep('busy')
    setError(null)
    try {
      await post('/demo/tamper', { merchant_id: merchantId, ledger_entry_id: entryId })
      setDone(entryId)
    } catch (e) {
      setError(e)
    } finally {
      setStep('idle')
    }
  }

  return (
    <section className="panel dp-action dp-tamper" aria-labelledby="dp-tamper-h">
      <span className="label">Tamper test · POST /demo/tamper</span>
      <h3 id="dp-tamper-h">Break the hash chain on purpose.</h3>
      <p>Changes one entry's amount straight in the database, skipping the ledger code and without updating its hash. The hash check then fails at that entry and every screen shows TAMPERED. Resetting the demo undoes it.</p>

      {!items && <LoadState state={ledger} what="today's ledger" />}
      {items && !items.length && <p className="dp-off-note">No ledger entries on {longDate(demoDate)} yet. Send a payment from the Soundbox first.</p>}
      {items && items.length > 0 && (
        <label className="field">
          <span>Entry from today's ledger</span>
          <select value={entryId} onChange={(e) => { setEntryId(e.target.value); setStep('idle'); setDone(null) }}>
            <option value="">Pick an entry…</option>
            {items.map((e) => (
              <option key={e.ledger_entry_id} value={e.ledger_entry_id}>
                {`seq ${e.seq} · ${clockTime(e.effective_at)} · ${words(e.entry_type)} · ${e.amount_display} · ${e.ledger_entry_id}`}
              </option>
            ))}
          </select>
        </label>
      )}
      {entry && (
        <dl className="kv dp-entry">
          <dt>Entry</dt><dd className="mono">{entry.ledger_entry_id} · seq {entry.seq}</dd>
          <dt>Source</dt><dd className="mono">{entry.source_type} {entry.source_id}</dd>
          <dt>Amount</dt><dd><Money amount={entry} sources={[entry.ledger_entry_id]} /></dd>
          <dt>Hash</dt><dd className="hash">{shortHash(entry.hash)}</dd>
        </dl>
      )}

      <Confirm step={step} setStep={setStep} disabled={toolsOff || !entry}
        label={<><ShieldAlert aria-hidden="true" /> Tamper with this entry…</>}
        ask={`Edit ${entryId} directly in the database? The ledger shows TAMPERED until the demo is reset.`}
        yes={<><ShieldAlert aria-hidden="true" /> Yes, tamper</>} onYes={run} />
      <ErrorBanner error={error} hint={error && writeHint(error)} />
      {done && (
        <div className="dp-done is-tampered" role="status">
          <ShieldAlert aria-hidden="true" />
          <p><b>{done} was changed in the database.</b> <a href="#/ledger">See TAMPERED on the ledger <ArrowRight aria-hidden="true" /></a></p>
        </div>
      )}

      <div className={`dp-verify ${v ? (v.status === 'VALID' ? 'is-valid' : 'is-bad') : ''}`} aria-live="polite">
        {v?.status === 'VALID' ? <ShieldCheck aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
        <p>
          <span className="label">Hash check now</span>
          {v ? <><b className="mono">{v.status}</b> {v.message}</> : <LoadState state={verify} what="the hash check" />}
        </p>
        <a className="btn dp-small" href="#/ledger">Ledger <ArrowRight aria-hidden="true" /></a>
      </div>
      {tampered && <p className="note">The ledger is tampered right now. Reset the demo (above) to undo it.</p>}
    </section>
  )
}

/* ---------- device voices (speechSynthesis) ---------- */

const isTamil = (v) => /^ta([-_]|$)/i.test(v.lang || '')
const isTelugu = (v) => /^te([-_]|$)/i.test(v.lang || '')
/** lang for a voice name written in Tamil or Telugu script (the 22px rule) */
const scriptLang = (s) => (/[஀-௿]/.test(s) ? 'ta' : /[ఀ-౿]/.test(s) ? 'te' : undefined)

/** This browser's voices. Chrome fills the list late, so wait for 'voiceschanged' (and give up waiting after 3 s). */
function useVoices() {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : undefined
  const [voices, setVoices] = useState(() => (synth ? synth.getVoices() : []))
  const [settled, setSettled] = useState(false)
  const [round, setRound] = useState(0)
  const refresh = useCallback(() => setRound((r) => r + 1), [])

  useEffect(() => {
    if (!synth) return undefined
    setSettled(false)
    const read = () => setVoices(synth.getVoices())
    const changed = () => { read(); setSettled(true) }
    read()
    if (synth.addEventListener) synth.addEventListener('voiceschanged', changed)
    else synth.onvoiceschanged = changed
    const timer = setTimeout(changed, 3000)
    return () => {
      clearTimeout(timer)
      if (synth.removeEventListener) synth.removeEventListener('voiceschanged', changed)
      else synth.onvoiceschanged = null
    }
  }, [synth, round])

  // the verdict waits for the event (or the timeout): network voices can arrive after the first list
  return { supported: Boolean(synth), voices, settled, refresh }
}

function Verdict({ name, found, settled }) {
  if (!settled) return <li className="is-wait"><CircleDashed aria-hidden="true" /><span><b>{name}:</b> checking…</span></li>
  return (
    <li className={found.length ? 'is-yes' : 'is-no'}>
      {found.length ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}
      <span>
        <b>{name}: {found.length ? 'installed.' : 'no voice installed.'}</b>{' '}
        {found.length
          ? found.map((v) => `${v.name} (${v.lang}, ${v.localService ? 'on this device' : 'network'})`).join('; ')
          : `This device can't speak ${name} by itself.`}
      </span>
    </li>
  )
}

function Voices() {
  const { supported, voices, settled, refresh } = useVoices()
  const ta = voices.filter(isTamil)
  const te = voices.filter(isTelugu)
  const rest = voices.filter((v) => !isTamil(v) && !isTelugu(v))
  const ordered = [...ta, ...te, ...rest]

  return (
    <section className="panel dp-voices" aria-labelledby="dp-voices-h">
      <div className="panel-head">
        <div>
          <span className="label">Device voices · speechSynthesis</span>
          <h3 id="dp-voices-h">Can this device speak Tamil and Telugu?</h3>
        </div>
        <button type="button" className="btn dp-small" onClick={refresh} disabled={!supported}><RefreshCw aria-hidden="true" /> Check again</button>
      </div>
      <p className="note">The voices this browser on this device offers. Another laptop or phone can list different ones.</p>
      {!supported && <p className="dp-off-note">This browser has no speech synthesis (window.speechSynthesis is missing), so it lists no voices.</p>}
      {supported && (
        <ul className="dp-verdict" aria-live="polite">
          <Verdict name="Tamil" found={ta} settled={settled} />
          <Verdict name="Telugu" found={te} settled={settled} />
        </ul>
      )}
      {supported && settled && !voices.length && <p className="dp-off-note">This browser lists no voices at all.</p>}
      {voices.length > 0 && (
        <div className="dtable dp-vtable" role="table" aria-label="Device voices">
          <div className="tr th" role="row">
            <span role="columnheader">Name</span><span role="columnheader">Language</span>
            <span role="columnheader">Local or network</span><span role="columnheader">Default</span>
          </div>
          {ordered.map((v, i) => {
            const mark = isTamil(v) ? 'Tamil' : isTelugu(v) ? 'Telugu' : null
            return (
              <div key={`${v.voiceURI || v.name}-${i}`} role="row" className={`tr ${mark ? 'is-mark' : ''}`}>
                <span role="cell" className="dp-vname" lang={scriptLang(v.name)}>{v.name}</span>
                <span role="cell" className="dp-vlang">
                  <span className="mono">{v.lang || '—'}</span>
                  {mark && <span className="chip dp-vchip">{mark}</span>}
                </span>
                <span role="cell">{v.localService ? 'On this device' : 'Network'}</span>
                <span role="cell">{v.default ? <span className="chip">Default</span> : <span className="dp-notyet">—</span>}</span>
              </div>
            )
          })}
        </div>
      )}
      {voices.length > 0 && <p className="note">{count(voices.length)} voices · {count(voices.filter((v) => v.localService).length)} on this device.</p>}
    </section>
  )
}

/* ---------- page ---------- */

export default function DemoPanel() {
  const { merchantId, merchant, demoDate } = useMerchant()
  const health = useApi('/health')
  const h = health.data
  const toolsOff = h?.demo_tools === false

  return (
    <div className="dp">
      <div className={`dp-tape ${toolsOff ? 'is-off' : ''}`} role="note">
        <Construction aria-hidden="true" />
        <p><b>Demo controls.</b> For the presenter, not part of the merchant's app. Reset and tamper change the shared demo database behind every screen.</p>
        <span className="dp-state">{h ? (toolsOff ? 'Demo tools off' : 'Demo tools on') : '…'}</span>
      </div>

      <header className="page-head">
        <div>
          <span className="label">Demo · {merchant?.display_name || merchantId}</span>
          <h1>Demo controls.</h1>
          <p className="lede">Health, reset, the tamper test, this device's voices and the scripted day. Hidden from the rail; open it at #/demo.</p>
        </div>
      </header>

      <p className="dp-live" role="note">
        <Smartphone aria-hidden="true" />
        <span>
          <b>Live mode.</b> Payments now also arrive on their own on the <a href="#/soundbox">Soundbox</a> screen, and
          from phones on <a href="#/pay">#/pay</a>.
        </span>
      </p>

      {toolsOff && (
        <p className="error-banner dp-off" role="alert">
          <TriangleAlert aria-hidden="true" />
          <span><b>Demo tools are off on this backend.</b> Reset, script and tamper return 404. Set ENABLE_DEMO_TOOLS=true in the backend .env and restart it.</span>
        </p>
      )}

      <div className="dp-top">
        <div className="dp-stack dp-left">
          <Health health={health} />
          <Voices />
        </div>
        <div className="dp-stack">
          <Reset toolsOff={toolsOff} />
          <Tamper key={`t-${merchantId}`} merchantId={merchantId} demoDate={demoDate} toolsOff={toolsOff} tampered={Boolean(h?.tampered)} />
        </div>
      </div>

      <Script key={`s-${merchantId}`} merchantId={merchantId} toolsOff={toolsOff} />
    </div>
  )
}
