// Shared question card (Soundbox and Questions screens). One card = one question: it is bound to its question_id,
// transaction_id and merchant_id when shown and sends exactly those (VOICE_AND_NOTICE 4.1a), never "the first open
// question". Taps go to POST /payments/{txn}/confirm (contract section 4).
// The remember prompt comes BEFORE the confirm call when it applies: a second confirm with the same category is an
// idempotent replay that writes nothing, so "remember" can only travel with the answer itself.
import { ArrowLeft, Check, RotateCcw, TriangleAlert, Volume2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { apiUrl, post, put, useApi } from '../api'
import { stringsFor } from '../app/strings'
import { Badge, Money, clockTime, confidenceText, count, ledgerHref, longDate } from './ui'

// Spoken-style sentences from the templates in docs/VOICE_AND_NOTICE.md section 7 (remember_question, confirm_*)
// and section 8 (reversed). Button words come from app/strings.js.
const SENTENCES = {
  ta: {
    rememberFamily: (n) => `இனிமே ${n} அனுப்புறது எல்லாம் வீட்டு பணமா?`,
    savedFamily: 'சரி, இதை வீட்டு பணமா வச்சுட்டேன். கடை கணக்குல சேர்க்கல.',
    savedFamilyRemembered: (n) => `சரி. இனிமே ${n} பணம் வீட்டு பணமா எடுத்துக்கறேன். கடை கணக்குல சேர்க்க மாட்டேன்.`,
    savedSale: 'சரி, இதை கடை வியாபாரமா சேர்த்துட்டேன்.',
    reversed: 'இந்த பணம் திரும்ப போயிடுச்சு',
  },
  te: {
    rememberFamily: (n) => `ఇకపై ${n} పంపేది అంతా ఇంటి డబ్బేనా?`,
    savedFamily: 'సరే, ఇది ఇంటి డబ్బుగా పెట్టాను. షాప్ లెక్కలో కలపలేదు.',
    savedFamilyRemembered: (n) => `సరే. ఇకపై ${n} డబ్బు ఇంటి డబ్బుగా తీసుకుంటాను. షాప్ లెక్కలో కలపను.`,
    savedSale: 'సరే, ఇది షాప్ అమ్మకంగా కలిపాను.',
  },
}
const EN = { SALE: 'Shop sale', FAMILY: 'Family money' }
const CLASS_WORDS = { PENDING: 'waiting', SALE: 'shop sale', FAMILY: 'family money' }

/** What to tell the merchant when a confirm fails, by the contract's error codes. */
function hintFor(e) {
  const reason = e?.details?.reason
  if (e?.code === 'INVALID_STATE' && reason === 'QUESTION_MISMATCH') {
    return { text: 'This answer belonged to a different question, so nothing was saved. Reload the questions and answer the card on screen.', reload: true }
  }
  if (e?.code === 'INVALID_STATE' && reason === 'REVERSED') {
    return { text: 'The bank reversed this payment, so it cannot be sorted. Nothing was saved.', reversed: true }
  }
  if (e?.code === 'INVALID_STATE') return { text: 'Not allowed for this payment right now. Reload to see where it stands.', reload: true }
  if (e?.code === 'DUPLICATE_CONFLICT') return { text: 'A different answer for this payment is already saved. Reload to see the current answer.', reload: true }
  if (e?.code === 'VALIDATION_ERROR' && e?.details?.field === 'remember_payer') {
    return { text: '"Remember as customer" is only for person-to-person payments. Answer again without remembering.', withoutRemember: true }
  }
  if (e?.code === 'NOT_FOUND') return { text: 'This payment or question no longer exists (was the demo reset?). Reload the questions.', reload: true }
  if (e?.code === 'UNREACHABLE') return { text: 'Check that the backend is running, then try again. The same answer is sent again and is never counted twice.', retry: true }
  return { text: 'Try again. A repeated answer is never counted twice.', retry: true }
}

/** Payer memory after the answer, in plain words. */
function memoryText(res, name, remembered) {
  const pm = res.payer_memory || {}
  const moved = res.moved_from === 'CUSTOMER' ? ' Moved off your customer list.' : res.moved_from === 'FAMILY' ? ' Moved off your family list.' : ''
  if (res.confirmed_category === 'FAMILY' && pm.family_payer_configured) {
    return `${remembered ? `Remembered: ${name}'s future payments are family money automatically, by your instruction.` : `${name} is on your family list, so future payments stay family.`}${moved} You can change this later.`
  }
  if (res.confirmed_category === 'SALE' && pm.customer_payer_configured) {
    return `${remembered ? `Remembered as a customer: ${name}'s future payments count as shop sales, by your instruction.` : `${name} is on your customer list.`}${moved}`
  }
  return `Not remembered. Naanayam keeps the answer (${name} so far: ${count(pm.confirmed_family)} family, ${count(pm.confirmed_sale)} sale) and uses it next time, but may still ask.`
}

/** Question audio from GET /audio/{id}; the text on the card stays the source of truth. */
function QuestionAudio({ audioId }) {
  const src = audioId ? apiUrl(`/audio/${encodeURIComponent(audioId)}`) : null
  const ref = useRef(null)
  const [status, setStatus] = useState('idle')
  if (!audioId) return <p className="qc-audio-note">Text only: no audio for this question yet.</p>
  if (!src) return <p className="qc-audio-note">Text only here: question audio plays from the live backend.</p>
  const play = () => {
    const el = ref.current
    if (!el) return
    el.currentTime = 0
    el.play().catch(() => setStatus('failed'))
  }
  return (
    <div className="qc-audio">
      <audio ref={ref} src={src} preload="none" onPlaying={() => setStatus('playing')} onEnded={() => setStatus('idle')} onError={() => setStatus('failed')} />
      <button type="button" className="btn" onClick={play} disabled={status === 'playing'}>
        <Volume2 aria-hidden="true" /> {status === 'playing' ? 'Playing…' : 'Hear the question'}
      </button>
      {status === 'failed' && <span className="qc-audio-note" role="status">Audio couldn't play. Read the question above.</span>}
    </div>
  )
}

/**
 * props: question (an item of GET /merchants/{id}/questions), merchantId, language ('ta'|'te'), demoDate,
 * hideAudio (the Soundbox plays the voice itself), onAnswered(question, response), onReload (refetch the list).
 */
export default function QuestionCard({ question: q, merchantId, language, demoDate, hideAudio = false, onAnswered, onReload }) {
  const t = stringsFor(language)
  const lang = t.lang
  const say = SENTENCES[lang]
  const payment = useApi(`/payments/${encodeURIComponent(q.transaction_id)}`)
  const merchant = useApi(`/merchants/${merchantId}`)
  const [step, setStep] = useState('ask') // ask | remember | done
  const [busy, setBusy] = useState(false)
  const [choice, setChoice] = useState(null) // { category, remember }
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [unconf, setUnconf] = useState({ state: 'idle', error: null })
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false } // a late response for a closed card is dropped
  }, [])

  const pay = payment.data
  const payerId = pay?.payer_id
  const m = merchant.data
  const onFamilyList = Boolean(payerId && m?.family_payers?.some((p) => p.payer_id === payerId))
  const onCustomerList = Boolean(payerId && m?.customer_payers?.some((p) => p.payer_id === payerId))
  const entryIds = (pay?.classification_history || []).map((h) => h.ledger_entry_id)
  const name = q.payer_name
  const day = q.timestamp?.slice(0, 10)
  const reversed = pay?.reversed === true
  const native = { SALE: t.sale, FAMILY: t.family }

  // FAMILY: ask unless the payer is already on the family list. SALE: only on a P2P payment (the backend answers 422
  // otherwise) and only when the payer isn't already a remembered customer.
  function offersRemember(category) {
    if (category === 'FAMILY') return !onFamilyList
    return pay?.payment_type === 'P2P' && !onCustomerList
  }

  async function send(category, remember) {
    const body = {
      merchant_id: merchantId,
      question_id: q.question_id,
      confirmed_category: category,
      channel: 'TAP',
      utterance_text: null,
      remember_payer: remember,
    }
    setChoice({ category, remember })
    setBusy(true)
    setError(null)
    try {
      const res = await post(`/payments/${encodeURIComponent(q.transaction_id)}/confirm`, body)
      if (!alive.current) return
      setResult(res)
      setStep('done')
      onAnswered?.(q, res)
    } catch (e) {
      if (alive.current) setError(e)
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  function choose(category) {
    if (offersRemember(category)) {
      setChoice({ category, remember: null })
      setError(null)
      setStep('remember')
    } else {
      send(category, false)
    }
  }

  function restart() {
    setStep('ask')
    setChoice(null)
    setError(null)
    setUnconf({ state: 'idle', error: null })
  }

  // contract section 4: "Stop treating {name} as always family?" after a SALE answer from a configured family payer
  async function stopFamily() {
    if (!m || !payerId) return
    setUnconf({ state: 'saving', error: null })
    try {
      await put(`/merchants/${merchantId}`, { family_payer_ids: m.family_payers.map((p) => p.payer_id).filter((id) => id !== payerId) })
      if (alive.current) setUnconf({ state: 'done', error: null })
    } catch (e) {
      if (alive.current) setUnconf({ state: 'idle', error: e })
    }
  }

  const hint = error && hintFor(error)
  const doneCat = result?.confirmed_category
  const reversedWords = say?.reversed && <><span lang={lang}>{say.reversed}</span>. </>

  return (
    <article className={`qcard qc is-${step}`} aria-label={`Question about ${name}'s payment`} aria-busy={busy}>
      <div className="qc-top">
        <span className={`chip ${step === 'done' ? (doneCat === 'FAMILY' ? 'family' : 'sale') : 'pending'}`}>
          {step === 'done' ? CLASS_WORDS[doneCat] || doneCat : q.status === 'ANSWERED' ? 'Answered earlier' : 'Waiting for you'}
        </span>
        <span className="qc-id" title="This card answers only this question">{q.question_id}</span>
      </div>

      <div className="qc-head">
        <span className="qcard-avatar" aria-hidden="true">{name?.[0]}</span>
        <span className="qc-who">
          <b>{name}</b>
          <small>
            {clockTime(q.timestamp)} IST{day && day !== demoDate ? ` · ${longDate(day)}` : ''}
            {pay?.payment_type && ` · ${pay.payment_type === 'P2P' ? 'sent to your UPI ID' : 'paid to your QR'}`}
          </small>
        </span>
        <Money amount={q.amount_display} sources={entryIds} className="qc-amt" />
      </div>

      <p className="qc-guess">
        <span>Naanayam's guess</span>
        <span className={`chip ${q.suggested_classification === 'FAMILY' ? 'family' : 'sale'}`}>
          {CLASS_WORDS[q.suggested_classification] || q.suggested_classification}
        </span>
        {typeof q.confidence === 'number'
          ? <span><b>{confidenceText(q.confidence)} sure.</b> Your answer decides.</span>
          : <Badge kind="instruction" />}
      </p>

      <div className="qc-q">
        <p className="qc-text" lang={lang}>{q.question_text}</p>
        <p className="qcard-en">{q.question_text_en}</p>
        {!hideAudio && <QuestionAudio audioId={q.question_audio_id} />}
      </div>

      {reversed && step !== 'done' && (
        <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
          <span>{reversedWords}The bank reversed this payment, so it cannot be sorted.</span>
        </p>
      )}

      {step === 'ask' && (
        <div className="qcard-answers qc-answers" role="group" aria-label="Your answer">
          {['SALE', 'FAMILY'].map((cat) => (
            <button key={cat} type="button" className={`is-${cat.toLowerCase()}`} onClick={() => choose(cat)} disabled={busy || reversed}>
              <span lang={lang}>{native[cat]}</span><small>{EN[cat]}</small>
            </button>
          ))}
        </div>
      )}

      {step === 'remember' && choice && (
        <div className={`qc-remember is-${choice.category.toLowerCase()}`} role="group" aria-labelledby={`rq-${q.question_id}`}>
          <p className="qc-said-you">You said <span lang={lang}>{native[choice.category]}</span> <small>({EN[choice.category].toLowerCase()})</small></p>
          {choice.category === 'FAMILY' ? (
            <>
              <p className="qc-remember-q" id={`rq-${q.question_id}`} lang={lang}>{say.rememberFamily(name)}</p>
              <p className="qcard-en">From now on, is everything {name} sends family money?</p>
            </>
          ) : (
            <p className="qc-remember-q qc-remember-en" id={`rq-${q.question_id}`}>
              Remember {name} as a customer? Future payments from {name} would count as shop sales.
            </p>
          )}
          <div className="qc-choices">
            <button type="button" className="is-always" onClick={() => send(choice.category, true)} disabled={busy}>
              <span lang={lang}>{t.rememberAlways}</span>
              <small>{choice.category === 'FAMILY' ? 'Always family' : 'Remember as customer'}</small>
            </button>
            <button type="button" className="is-once" onClick={() => send(choice.category, false)} disabled={busy}>
              <span lang={lang}>{t.rememberOnce}</span>
              <small>Just this time</small>
            </button>
          </div>
          <div className="qc-row">
            <button type="button" className="linkish qc-back" onClick={restart} disabled={busy}><ArrowLeft aria-hidden="true" /> Change answer</button>
            <span className="note">Only future payments change. Past entries are never rewritten.</span>
          </div>
        </div>
      )}

      {busy && <p className="qc-status" role="status">Saving your answer…</p>}

      {error && hint && !busy && (
        <div className="qc-error">
          <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" />
            <span><b>{error.message}.</b> {hint.reversed && reversedWords}{hint.text}</span>
          </p>
          <div className="qc-row">
            {hint.retry && choice && (
              <button type="button" className="btn" onClick={() => send(choice.category, choice.remember)}><RotateCcw aria-hidden="true" /> Try again</button>
            )}
            {hint.withoutRemember && choice && (
              <button type="button" className="btn" onClick={() => send(choice.category, false)}>Answer without remembering</button>
            )}
            {hint.reload && (onReload
              ? <button type="button" className="btn" onClick={onReload}><RotateCcw aria-hidden="true" /> Reload questions</button>
              : <a className="btn" href="#/questions">Open questions</a>)}
          </div>
        </div>
      )}

      {step === 'done' && result && (
        <div className="qcard-stamp qc-result" role="status">
          <span className={`qc-stamp is-${doneCat === 'FAMILY' ? 'family' : 'sale'}`} lang={native[doneCat] ? lang : undefined}>
            <Check aria-hidden="true" />{native[doneCat] || doneCat}
          </span>
          <p className="qc-said" lang={lang}>
            {doneCat === 'SALE'
              ? say.savedSale
              : choice?.remember && result.payer_memory?.family_payer_configured ? say.savedFamilyRemembered(name) : say.savedFamily}
          </p>
          <p className="qc-plain">
            {result.idempotent_replay
              ? 'Already saved with this answer. Nothing new was written.'
              : doneCat === 'FAMILY'
                ? 'Saved as family money: kept out of sales and profit.'
                : 'Saved as a shop sale: it counts in sales and profit.'}
          </p>
          <dl className="kv qc-kv">
            <dt>Was</dt>
            <dd>{CLASS_WORDS[result.previous_classification] || result.previous_classification} → <b>{CLASS_WORDS[doneCat] || doneCat}</b></dd>
            {result.ledger_entry_id && (
              <>
                <dt>Ledger</dt>
                <dd>
                  <Money amount={q.amount_display} sources={[result.ledger_entry_id]} />{' '}
                  <a className="mono" href={ledgerHref([result.ledger_entry_id])}>{result.ledger_entry_id}</a>
                  {result.idempotent_replay ? ' (the current entry)' : ', a new entry. The original stays in the ledger.'}
                </dd>
              </>
            )}
            <dt>Memory</dt>
            <dd>{memoryText(result, name, Boolean(choice?.remember))}</dd>
          </dl>
          {result.suggest_unconfigure && (
            <div className="qc-unconf">
              {unconf.state === 'done' ? (
                <p>Removed {name} from your family list. Future payments are judged on their own again.</p>
              ) : (
                <>
                  <p>{name} is still on your family list, so future payments stay family. Stop treating {name} as always family?</p>
                  <button type="button" className="btn" onClick={stopFamily} disabled={unconf.state === 'saving' || !m}>
                    {unconf.state === 'saving' ? 'Saving…' : 'Stop treating as family'}
                  </button>
                  {unconf.error && (
                    <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" /><span>{unconf.error.message}. Try again in a moment.</span></p>
                  )}
                </>
              )}
            </div>
          )}
          <button type="button" className="btn qc-change" onClick={restart}><RotateCcw aria-hidden="true" /> Change answer</button>
        </div>
      )}
    </article>
  )
}
