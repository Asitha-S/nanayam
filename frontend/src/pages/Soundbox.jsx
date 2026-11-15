// P1 · Soundbox simulator. POST /demo/next-payment { merchant_id } injects the next scripted payment through the same
// code path as POST /payments. AUTO → a classification chip; ASK → the question card for exactly the returned
// question_id (the seed keeps older open questions, so never "the first open one").
// Also: GET /demo/script (progress), GET /merchants/{id}/payments (today, newest first), GET /audio/{id} (voice).
import '../styles/soundbox.css'
import { Check, CircleHelp, Radio, RotateCcw, Send, TriangleAlert, Volume2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { apiUrl, get, post, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { useStrings } from '../app/strings'
import QuestionCard from '../components/QuestionCard'
import { Badge, LoadState, Money, clockTime, confidenceText, count } from '../components/ui'

const CLASS_WORDS = { SALE: 'Sale', FAMILY: 'Family', PENDING: 'Waiting' }

/** useApi keeps the previous path's data when a new fetch fails; never show another merchant's data. */
function forMerchant(state, merchantId) {
  return state.data && state.data.merchant_id && state.data.merchant_id !== merchantId ? { ...state, data: null } : state
}

/** The open question for this question_id: today's list first, then all open, then answered (a replay). */
async function findQuestion(merchantId, demoDate, questionId) {
  const paths = [
    demoDate && `/merchants/${merchantId}/questions?status=OPEN&date=${demoDate}`,
    `/merchants/${merchantId}/questions?status=OPEN`,
    `/merchants/${merchantId}/questions?status=ANSWERED${demoDate ? `&date=${demoDate}` : ''}`,
  ].filter(Boolean)
  let firstError = null
  for (const p of paths) {
    try {
      const hit = (await get(p)).items?.find((q) => q.question_id === questionId)
      if (hit) return hit
    } catch (e) {
      firstError = firstError || e
    }
  }
  if (firstError) throw firstError
  return null
}

/**
 * What the Soundbox says. `payment_announce` is not in contract v1.1; it is read only if a backend sends it.
 * Otherwise an ASK payment speaks its question (question_text + question_audio_id) and an AUTO one has no voice.
 */
function announcementOf(res, question, lang) {
  const a = res?.payment_announce
  if (a && typeof a.text === 'string') {
    return {
      text: a.text,
      lang: a.language || lang,
      audioId: a.audio_id || null,
      recorded: a.recognition_mode === 'RECORDED_DEMO' || a.from_cache === true || a.recorded === true,
    }
  }
  if (question) return { text: question.question_text, textEn: question.question_text_en, lang, audioId: question.question_audio_id, recorded: false, isQuestion: true }
  return { text: null, audioId: null, recorded: false }
}

/** Plays /audio/{id} once per payment (after the click), with replay. Reports its status for the device lights. */
function Voice({ audioId, playKey, recorded, onStatus }) {
  const src = audioId ? apiUrl(`/audio/${encodeURIComponent(audioId)}`) : null
  const ref = useRef(null)
  const [status, setStatus] = useState('idle')
  const set = (s) => { setStatus(s); onStatus?.(s) }
  const play = () => {
    const el = ref.current
    if (!el) return
    el.currentTime = 0
    set('loading')
    el.play().catch((e) => set(e?.name === 'NotAllowedError' ? 'blocked' : 'failed'))
  }
  useEffect(() => {
    if (src) play()
    else set('none')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, playKey])

  let note = null
  if (!audioId) note = 'Text only: no audio came with this payment.'
  else if (!src) note = 'Text only here: the voice plays from the live backend.'
  else if (status === 'failed') note = "Audio couldn't play. Showing the text only."
  else if (status === 'blocked') note = 'The browser held the audio back. Press Replay.'
  return (
    <div className="sb-voice">
      {src && <audio ref={ref} src={src} preload="auto" onPlaying={() => set('playing')} onEnded={() => set('ended')} onError={() => set('failed')} />}
      {src && (
        <button type="button" className="btn" onClick={play} disabled={status === 'playing' || status === 'loading'}>
          {status === 'playing' ? <Volume2 aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
          {status === 'playing' ? 'Playing…' : 'Replay'}
        </button>
      )}
      {src && recorded && <Badge kind="clip" />}
      {note && <span className="sb-voice-note" role="status">{note}</span>}
    </div>
  )
}

/** The simulated speaker: an object in CSS, no image, no brand. */
function Device({ state, speaking, amount, sources, line, top }) {
  return (
    <figure className={`sb-device ${speaking ? 'is-speaking' : ''}`} data-state={state} aria-label={`Simulated Soundbox: ${line}`}>
      <div className="sb-device-top">
        <span className="sb-led" aria-hidden="true" />
        <span className="sb-plate">Soundbox · demo</span>
        <svg className="sb-bars" viewBox="0 0 22 14" aria-hidden="true">
          <rect x="0" y="9" width="4" height="5" rx="1" /><rect x="6" y="6" width="4" height="8" rx="1" />
          <rect x="12" y="3" width="4" height="11" rx="1" /><rect x="18" y="0" width="4" height="14" rx="1" />
        </svg>
      </div>
      <div className="sb-lcd" aria-live="polite">
        <span className="sb-lcd-top"><span>UPI</span><span>{top}</span></span>
        {amount ? <Money amount={amount} sources={sources} className="sb-lcd-amt" key={`${amount}-${top}`} /> : <strong className="sb-lcd-amt is-idle">- - -</strong>}
        <span className="sb-lcd-line">{line}</span>
      </div>
      <div className="sb-grille" aria-hidden="true" />
      <div className="sb-keys" aria-hidden="true"><i /><i /><i /></div>
    </figure>
  )
}

function ScriptPanel({ script, nextItem, sentCount, total, finished, merchantName }) {
  const items = script.data?.items || []
  const missing = script.error && (script.error.code === 'NOT_FOUND' || script.error.code === 'NO_FIXTURE')
  return (
    <section className="panel sb-script" aria-labelledby="sb-script-h">
      <div className="panel-head">
        <h2 id="sb-script-h" className="sb-h">Demo day script</h2>
        {total > 0 && <span className="label">{count(sentCount)} of {count(total)} sent</span>}
      </div>
      {!script.data && !script.error && <LoadState state={script} what="the script" />}
      {missing && <p className="note">No demo script for {merchantName}. Payments can still arrive through the API.</p>}
      {script.error && !missing && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          <span>Couldn't load the script: {script.error.message}. Check the backend, then reload the page.</span></p>
      )}
      {script.data && !items.length && <p className="note">The script for {merchantName} is empty.</p>}
      {items.length > 0 && (
        <>
          <div className="sb-progress" role="progressbar" aria-label="Script progress" aria-valuemin={0} aria-valuemax={total} aria-valuenow={sentCount}>
            {items.map((it) => (
              <i key={it.transaction_id} className={`${it.injected ? 'is-done' : ''} ${it.expected_action === 'ASK_MERCHANT' ? 'is-ask' : ''} ${nextItem?.transaction_id === it.transaction_id ? 'is-next' : ''}`} />
            ))}
          </div>
          {finished && <p className="sb-done"><Check aria-hidden="true" /> All {count(total)} payments sent. The scripted day is finished.</p>}
          <ol className="sb-steps">
            {items.map((it) => {
              const isNext = nextItem?.transaction_id === it.transaction_id
              return (
                <li key={it.transaction_id} className={it.injected ? 'is-done' : isNext ? 'is-next' : ''} aria-current={isNext ? 'step' : undefined}>
                  <span className="sb-n">{String(it.demo_index).padStart(2, '0')}</span>
                  <span className="sb-t">{it.time}</span>
                  <span className="sb-who">{it.payer_name}{it.expected_action === 'ASK_MERCHANT' && <small>asks</small>}</span>
                  <Money amount={it.amount_display} className="sb-amt" />
                  <span className="sb-state">
                    {it.injected ? <Check aria-label="Sent" /> : isNext ? <b>Next</b> : <span className="visually-hidden">Not sent</span>}
                  </span>
                </li>
              )
            })}
          </ol>
        </>
      )}
    </section>
  )
}

function sourceText(p) {
  if (p.current_classification === 'PENDING') return 'Waiting for an answer'
  if (p.classification_source === 'MERCHANT_CONFIRMED') return 'Your answer'
  if (p.classification_source === 'MERCHANT_CONFIG') return 'Your instruction'
  if (typeof p.confidence !== 'number') return 'Your instruction'
  return `${confidenceText(p.confidence)} sure${p.classification_source === 'PAYER_MEMORY' ? ', from past answers' : ''}`
}

function PaymentsPanel({ payments }) {
  const items = [...(payments.data?.items || [])].sort((a, b) => (a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0))
  return (
    <section className="panel sb-payments" aria-labelledby="sb-pay-h">
      <div className="panel-head">
        <h2 id="sb-pay-h" className="sb-h">Today's payments</h2>
        {payments.data && <span className="label">{count(payments.data.count)} · newest first</span>}
      </div>
      {!payments.data && <LoadState state={payments} what="today's payments" />}
      {payments.data && !items.length && <p className="note">No payments yet today. Press Send next payment.</p>}
      {items.length > 0 && (
        <ul className="sb-paylist">
          {items.map((p) => {
            const c = (p.current_classification || '').toLowerCase()
            return (
              <li key={p.transaction_id}>
                <span className="sb-t">{clockTime(p.timestamp)}</span>
                <span className="sb-who"><b>{p.payer_name}</b><small>{sourceText(p)}{c === 'pending' && <> · <a href="#/questions">Answer</a></>}</small></span>
                <span className={`chip ${['sale', 'family', 'pending'].includes(c) ? c : 'muted'}`}>{CLASS_WORDS[p.current_classification] || p.current_classification}</span>
                <Money amount={p.amount_display} className="sb-amt" />
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

export default function Soundbox() {
  const { merchantId, merchant, language, demoDate, health } = useMerchant()
  const t = useStrings()
  const script = forMerchant(useApi(`/demo/script?merchant_id=${merchantId}`, { pollMs: 10000 }), merchantId)
  const payments = forMerchant(useApi(`/merchants/${merchantId}/payments`, { pollMs: 5000 }), merchantId)
  const [sent, setSent] = useState(null) // { res, question, questionError, key, answer }
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [voice, setVoice] = useState('idle')
  const reqId = useRef(0)
  const askRef = useRef(null)

  // switching merchant clears the card and drops in-flight responses (VOICE_AND_NOTICE 4.1a rule 4)
  useEffect(() => {
    reqId.current += 1
    setSent(null)
    setError(null)
    setSending(false)
    setVoice('idle')
  }, [merchantId])

  const items = script.data?.items || []
  const total = items.length
  const sentCount = items.filter((i) => i.injected).length
  const nextItem = items.find((i) => !i.injected) || null
  const finished = total > 0 && !nextItem
  const toolsOff = health?.demo_tools === false
  const owner = merchant?.owner_name || merchantId

  async function send() {
    const id = ++reqId.current
    setSending(true)
    setError(null)
    setVoice('idle')
    try {
      const res = await post('/demo/next-payment', { merchant_id: merchantId })
      if (id !== reqId.current) return
      let question = null
      let questionError = null
      if (res.action === 'ASK_MERCHANT' && res.question_id) {
        try {
          question = await findQuestion(merchantId, demoDate, res.question_id)
        } catch (e) {
          questionError = e
        }
        if (id !== reqId.current) return
      }
      const item = items.find((i) => i.transaction_id === res.transaction_id) || null
      setSent({ res, question, questionError, item, key: id, answer: null })
    } catch (e) {
      if (id === reqId.current) setError(e)
    } finally {
      if (id === reqId.current) setSending(false)
    }
  }

  useEffect(() => {
    if (sent?.question && askRef.current) askRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [sent?.key, sent?.question])

  const res = sent?.res
  const isAsk = res?.action === 'ASK_MERCHANT'
  const ann = res ? announcementOf(res, sent.question, language) : null
  const latest = [...(payments.data?.items || [])].sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))[0]

  // device display
  let devState = 'idle'
  let devLine = 'Ready'
  let devTop = 'Ready'
  let devAmount = null
  let devSources = undefined
  if (sending) { devState = 'busy'; devLine = 'Receiving…'; devTop = '' }
  else if (error) { devState = 'error'; devLine = 'Not sent'; devTop = 'Error' }
  else if (res) {
    devAmount = res.amount_display
    devSources = [res.ledger_entry_id]
    devTop = sent.item?.time || 'Now'
    const cat = sent.answer || (isAsk ? null : res.classification)
    devState = cat ? cat.toLowerCase() : 'ask'
    devLine = sent.answer ? `Answered · ${CLASS_WORDS[sent.answer]}` : isAsk ? 'Received · asking' : `Received · ${CLASS_WORDS[res.classification] || res.classification}`
  } else if (finished) { devState = 'done'; devLine = 'Day finished'; devTop = 'Done' }
  else if (latest) {
    devAmount = latest.amount_display
    devTop = `Last ${clockTime(latest.timestamp)}`
    devLine = `Received · ${CLASS_WORDS[latest.current_classification] || latest.current_classification}`
  }

  const counts = payments.data?.items || []
  const nSorted = counts.filter((p) => p.current_classification !== 'PENDING' && p.classification_source !== 'MERCHANT_CONFIRMED').length
  const nAnswered = counts.filter((p) => p.classification_source === 'MERCHANT_CONFIRMED').length
  const nWaiting = counts.filter((p) => p.current_classification === 'PENDING').length

  let errorHint = null
  if (error) {
    if (error.code === 'INVALID_STATE') errorHint = <>The script is finished for {owner}. Reset the demo from the <a href="#/demo">demo panel</a> to run the day again.</>
    else if (error.code === 'NOT_FOUND' && toolsOff) errorHint = <>Demo tools are off on this backend (ENABLE_DEMO_TOOLS=false). Turn them on and restart it.</>
    else if (error.code === 'NOT_FOUND') errorHint = <>There is no demo script for {owner}, or demo tools are off on this backend.</>
    else if (error.code === 'UNREACHABLE') errorHint = <>Start the backend, then press Send again. A payment is never counted twice.</>
    else errorHint = <>Press Send again. The same scripted payment is never counted twice.</>
  }

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">02 · {merchant?.display_name || merchantId}</span>
          <h1>Soundbox.</h1>
          <p className="lede">A simulated payment speaker for {owner}'s shop. Each press sends the next scripted payment through the same path as a real one: Naanayam sorts it silently, or asks one question in {t.languageName}.</p>
        </div>
      </header>

      {toolsOff && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          <span>Demo tools are off on this backend (ENABLE_DEMO_TOOLS=false), so the simulator can't send payments. Turn them on and restart the backend.</span></p>
      )}

      <div className="sb-layout">
        <div className="sb-main">
          <section className="panel sb-stage" aria-label="Soundbox simulator">
            <div className="sb-device-col">
              <Device state={devState} speaking={voice === 'playing' || sending} amount={devAmount} sources={devSources} line={devLine} top={devTop} />
              {counts.length > 0 && (
                <p className="sb-tally">
                  <span><b>{count(nSorted)}</b> sorted silently</span>
                  <span><b>{count(nAnswered)}</b> answered</span>
                  {nWaiting > 0 && <span className="is-waiting"><b>{count(nWaiting)}</b> waiting</span>}
                </p>
              )}
            </div>

            <div className="sb-console">
              <div className="sb-sendrow">
                <button type="button" className="btn ink big sb-send" onClick={send} disabled={sending || toolsOff || finished} aria-busy={sending}>
                  <Send aria-hidden="true" /> {sending ? 'Sending…' : finished ? 'Script finished' : 'Send next payment'}
                </button>
                {nextItem && !finished && (
                  <p className="sb-next">Next: <span className="mono">{nextItem.time}</span> · {nextItem.payer_name} · <Money amount={nextItem.amount_display} /> <small>({count(nextItem.demo_index)} of {count(total)})</small></p>
                )}
                {finished && <p className="sb-next">All scripted payments are in. Reset from the <a href="#/demo">demo panel</a> to replay the day.</p>}
              </div>

              {error && (
                <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
                  <span><b>{error.message}.</b> {errorHint}</span></p>
              )}

              {!res && !error && (
                <div className="sb-idle">
                  <Radio aria-hidden="true" />
                  {finished ? (
                    <p>The scripted day is finished.{nWaiting > 0 && <> {count(nWaiting)} {nWaiting === 1 ? 'payment is' : 'payments are'} waiting for {owner}'s answer on the <a href="#/questions">Questions screen</a>.</>}</p>
                  ) : (
                    <p>Press <b>Send next payment</b>. The Soundbox announces it; Naanayam decides whether it's a shop sale or family money, and asks {owner} only when it isn't sure.</p>
                  )}
                </div>
              )}

              {res && (
                <div className="sb-said" aria-live="polite">
                  <span className="label">{isAsk ? 'The Soundbox asks' : 'The Soundbox says'}</span>
                  {ann.text && !ann.isQuestion
                    ? <p className="sb-said-text" lang={ann.lang}>{ann.text}</p>
                    : <p className="sb-said-amt"><Money amount={res.amount_display} sources={[res.ledger_entry_id]} /> received{sent.item ? ` from ${sent.item.payer_name}` : ''}.</p>}
                  {ann.isQuestion && <p className="note">Then it reads the question on the card below, in {t.languageName}.</p>}
                  {isAsk && !sent.question && !ann.text && <p className="note">The question couldn't be loaded, so there is nothing to read out.</p>}
                  <Voice audioId={ann.audioId} playKey={sent.key} recorded={ann.recorded} onStatus={setVoice} />
                </div>
              )}

              {res && (
                <div className={`sb-verdict ${isAsk ? 'is-ask' : ''}`}>
                  <span className="label">What Naanayam did</span>
                  <p className="sb-verdict-line">
                    {isAsk
                      ? <><span className="chip pending">Asked</span> It asks {owner} before deciding. The payment waits, out of sales, until {owner} answers.</>
                      : <><span className={`chip ${res.classification === 'FAMILY' ? 'family' : 'sale'}`}>{CLASS_WORDS[res.classification] || res.classification}</span> Sorted silently.</>}
                    {typeof res.confidence === 'number'
                      ? <b className="sb-conf">{confidenceText(res.confidence)} sure{isAsk && res.suggested_classification ? ` it's ${res.suggested_classification === 'FAMILY' ? 'family' : 'a sale'}` : ''}</b>
                      : <Badge kind="instruction" />}
                  </p>
                  {res.reasons?.length > 0 && (
                    <ul className="sb-reasons" aria-label="Why">
                      {res.reasons.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  )}
                  <p className="note">
                    Ledger entry <a className="mono" href={`#/ledger?ids=${encodeURIComponent(res.ledger_entry_id)}`}>{res.ledger_entry_id}</a>
                    {res.idempotent_replay ? ' (already recorded; nothing new written)' : ''}
                    {typeof res.demo_remaining === 'number' && ` · ${count(res.demo_remaining)} scripted ${res.demo_remaining === 1 ? 'payment' : 'payments'} left`}
                  </p>
                </div>
              )}
            </div>
          </section>

          {res && isAsk && (
            <section className="panel signal sb-ask" ref={askRef} aria-label="The question">
              <div className="sb-ask-copy">
                <h2 className="sb-h">One question for {owner}.</h2>
                <p>On {owner}'s phone and the Soundbox, in {t.languageName}. Two big answers; nothing is guessed.</p>
                <a className="note sb-ask-link" href={`#/questions?q=${encodeURIComponent(res.question_id)}`}>
                  <CircleHelp aria-hidden="true" /> Also on the Questions screen
                </a>
              </div>
              {sent.question ? (
                <QuestionCard key={sent.question.question_id} question={sent.question} merchantId={merchantId} language={language}
                  demoDate={demoDate} hideAudio onAnswered={(_, r) => setSent((s) => (s && s.key === sent.key ? { ...s, answer: r.confirmed_category } : s))} />
              ) : (
                <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
                  <span>
                    {sent.questionError ? `Couldn't load question ${res.question_id}: ${sent.questionError.message}.` : `Question ${res.question_id} isn't in the question list.`}{' '}
                    Open it from the <a href={`#/questions?q=${encodeURIComponent(res.question_id)}`}>Questions screen</a>.
                  </span>
                </p>
              )}
            </section>
          )}

          <PaymentsPanel payments={payments} />
        </div>

        <aside className="sb-side">
          <ScriptPanel script={script} nextItem={nextItem} sentCount={sentCount} total={total} finished={finished} merchantName={owner} />
        </aside>
      </div>
    </>
  )
}
