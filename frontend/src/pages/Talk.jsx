// P1 · Talk: say or type an expense, ask today's profit, answer an open payment question.
// (audio -> POST /voice/transcribe) -> POST /voice/interpret -> POST /expenses | POST /voice/answer |
// POST /payments/{txn}/confirm (contract sections 4-6). Card binding follows VOICE_AND_NOTICE 4.1a: one active card;
// an utterance carries the id of the question card on screen; a late answer for a closed card is dropped; switching
// merchant clears everything. Nothing is saved without the merchant's tap (or spoken answer to a question card).
import '../styles/talk.css'
import { TOUR_EVENT } from '../tour/Tour'
import { RotateCcw } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, USING_FIXTURES, apiUrl, get, post, useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { useStrings } from '../app/strings'
import { ExpenseCard, PendingCard, ProfitCard, QuestionCard, Said, SayCard, StartCard } from '../components/talk/cards'
import { demoClips } from '../components/talk/clips'
import Composer from '../components/talk/Composer'
import { fileNameFor, micSupported, startRecording } from '../components/talk/mic'
import { EXPENSE_CATEGORIES, talkWords } from '../components/talk/strings'
import WaitingList from '../components/talk/WaitingList'

// Fixtures mode: api.js maps every POST /voice/interpret to one fixture. Pick it by the same rule as the backend stub
// (backend/app/routers/voice.py) so the profit and question flows can be tried without a backend.
const INTERPRET_FIXTURES = import.meta.glob('../../../contract/fixtures/voice_interpret_*.json', { import: 'default' })
const PROFIT_WORDS = ['லாபம்', 'மீதம்', 'labham', 'laabam', 'meedham', 'లాభం', 'profit']

function interpret(body, opts) {
  if (!USING_FIXTURES) return post('/voice/interpret', body, opts)
  const text = body.text.toLowerCase()
  const name = body.open_question_id ? 'confirm' : PROFIT_WORDS.some((w) => text.includes(w)) ? 'profit' : 'expense'
  return INTERPRET_FIXTURES[`../../../contract/fixtures/voice_interpret_${name}.json`]()
}

/** UUID v4 for a card draft (client_request_id). crypto.randomUUID needs a secure context, so fall back. */
function uuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  const b = window.crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

/** A request whose answer no longer matters (merchant switched, screen left). */
class StaleError extends Error {}

const SPEECH_FAILURES = ['CACHE_MISS', 'SARVAM_UNAVAILABLE', 'TIMEOUT', 'UNREACHABLE']
// Cards that can still be acted on; opening another card closes them (4.1a rule 2).
const LIVE = ['open', 'edit', 'failed']

export default function Talk({ params }) {
  const { merchantId, merchant, language, demoDate, health } = useMerchant()
  const t = useStrings()
  const W = talkWords(t.lang)

  const [turns, setTurns] = useState([])
  const [active, setActive] = useState(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [micBlocked, setMicBlocked] = useState(false)

  const activeRef = useRef(null) // { turnId, cardKey, kind, q?, stage?, answer? }: the card on screen
  const genRef = useRef(0)
  const ctrls = useRef(new Set())
  const recRef = useRef(null)
  const nextId = useRef(0)
  const clarifyTries = useRef(0)
  const textRef = useRef(null)
  const endRef = useRef(null)

  const questions = useApi(demoDate ? `/merchants/${merchantId}/questions?status=OPEN&date=${demoDate}` : null)
  const clips = demoClips(t.lang)

  // ---- turns -------------------------------------------------------------------------------------------------
  const addTurn = (turn) => {
    nextId.current += 1
    const id = `turn-${nextId.current}`
    setTurns((ts) => [...ts, { id, ...turn }])
    return id
  }
  const setReply = (id, reply) => setTurns((ts) => ts.map((x) => (x.id === id ? { ...x, reply } : x)))
  const patchReply = (id, patch) => setTurns((ts) => ts.map((x) => (x.id !== id ? x
    : { ...x, reply: typeof patch === 'function' ? patch(x.reply) : { ...x.reply, ...patch } })))
  const patchSaid = (id, patch) => setTurns((ts) => ts.map((x) => (x.id === id ? { ...x, utterance: { ...x.utterance, ...patch } } : x)))
  const removeTurn = (id) => setTurns((ts) => ts.filter((x) => x.id !== id))

  /** Make a card the one on screen. The previous card closes, or is marked "continued below" if it is the same card. */
  const activate = (next) => {
    const prev = activeRef.current
    if (prev && prev.turnId !== next?.turnId) {
      const status = next && prev.cardKey === next.cardKey ? 'moved' : 'closed'
      patchReply(prev.turnId, (r) => (LIVE.includes(r.status) ? { ...r, status } : r))
    }
    activeRef.current = next
    setActive(next)
  }
  /** The card finished (saved, cancelled): nothing is on screen any more. */
  const release = (turnId) => {
    if (activeRef.current?.turnId === turnId) {
      activeRef.current = null
      setActive(null)
    }
  }

  // ---- requests: every one is dropped if the merchant switches or the screen is left (4.1a rule 4) ------------
  const call = useCallback(async (fn, ms) => {
    const gen = genRef.current
    const ctrl = new AbortController()
    ctrls.current.add(ctrl)
    let timedOut = false
    const timer = setTimeout(() => { timedOut = true; ctrl.abort() }, ms)
    try {
      const out = await fn(ctrl.signal)
      if (gen !== genRef.current) throw new StaleError()
      return out
    } catch (e) {
      if (gen !== genRef.current || e instanceof StaleError) throw new StaleError()
      if (e.name === 'AbortError' && timedOut) {
        throw new ApiError(0, { code: 'TIMEOUT', message: `No answer after ${Math.round(ms / 1000)} seconds` })
      }
      throw e
    } finally {
      clearTimeout(timer)
      ctrls.current.delete(ctrl)
    }
  }, [])

  const resetAll = useCallback(() => {
    genRef.current += 1
    ctrls.current.forEach((c) => c.abort())
    ctrls.current.clear()
    recRef.current?.cancel()
    recRef.current = null
    activeRef.current = null
    clarifyTries.current = 0
    setActive(null)
    setTurns([])
    setBusy(false)
    setListening(false)
  }, [])

  const lastMerchant = useRef(merchantId)
  useEffect(() => {
    if (lastMerchant.current === merchantId) return
    lastMerchant.current = merchantId
    resetAll()
  }, [merchantId, resetAll])
  useEffect(() => () => {
    genRef.current += 1
    ctrls.current.forEach((c) => c.abort())
    recRef.current?.cancel()
  }, [])

  // ---- what went wrong, in the merchant's words (VOICE_AND_NOTICE 8) ------------------------------------------
  const failure = (e, step) => {
    if (step === 'transcribe' && e.status === 422 && e.details?.field === 'audio' && /empty/i.test(e.message)) {
      return { kind: 'say', tone: 'clarify', text: W.no_speech }
    }
    if (SPEECH_FAILURES.includes(e.code) || e.status === 503) {
      const why = {
        CACHE_MISS: "Can't reach Sarvam right now: speech runs from saved results only, and this hasn't been heard before.",
        SARVAM_UNAVAILABLE: "Can't reach Sarvam right now.",
        TIMEOUT: "Can't reach Sarvam right now: no answer in time.",
        UNREACHABLE: "Naanayam's backend isn't reachable.",
      }[e.code] || "Can't reach Sarvam right now."
      return { kind: 'say', tone: 'failure', text: W.offline, detail: `${why} Type it in the box, or tap a button.`, error: e, taps: true }
    }
    return { kind: 'say', tone: 'failure', error: e, detail: 'Nothing was saved. Try again, or tap a button.', taps: true }
  }

  // ---- expense card (4.2) ----------------------------------------------------------------------------------------
  const openExpense = (id, { res, utt, manual = false, note = null, hint = {} }) => {
    const ent = res?.entities || {}
    const category = ent.category || hint.category
    const draft = {
      draft_id: uuid(),
      amount_paise: manual ? null : ent.amount_paise,
      amount_display: manual ? null : ent.amount_display,
      typed: null,
      category: EXPENSE_CATEGORIES.includes(category) ? category : 'OTHER',
      categoryUnclear: !manual && (!ent.category || res?.validation?.category_valid === false),
      description: ent.description || hint.description || '',
      date: ent.date || hint.date || demoDate,
      timestamp: null,
      input_source: !manual && (utt?.source === 'mic' || utt?.source === 'clip') ? 'VOICE' : 'MANUAL',
      utterance_text: utt?.text || null,
      voice_log_id: utt?.voice_log_id || null,
      edited: false,
    }
    setReply(id, {
      kind: 'expense',
      status: manual ? 'edit' : 'open',
      draft,
      confirmationText: manual ? null : res?.confirmation_text,
      note,
      form: { rupees: '', category: draft.category, description: draft.description, error: null },
    })
    activate({ turnId: id, cardKey: draft.draft_id, kind: 'expense' })
  }

  /** "now" for the expense timestamp comes from the backend clock (summary.as_of), never the browser. */
  const saveExpense = async (id, draft) => {
    patchReply(id, { status: 'saving', error: null, draft })
    try {
      let d = draft
      if (!d.timestamp) {
        const s = await call((signal) => get(`/merchants/${merchantId}/summary?include_sources=true`, { signal }), 15000)
        // Same draft, same timestamp: a retry re-sends identical content under the same client_request_id.
        d = { ...d, timestamp: `${d.date || s.as_of.slice(0, 10)}${s.as_of.slice(10)}` }
        patchReply(id, { draft: d })
      }
      const res = await call((signal) => post('/expenses', {
        client_request_id: d.draft_id,
        merchant_id: merchantId,
        amount_paise: d.amount_paise,
        category: d.category,
        description: d.description || null,
        timestamp: d.timestamp,
        input_source: d.input_source,
        language,
        utterance_text: d.utterance_text,
        voice_log_id: d.voice_log_id,
      }, { signal }), 20000)
      patchReply(id, { status: 'saved', result: res })
      release(id)
    } catch (e) {
      if (e instanceof StaleError) return
      patchReply(id, { status: 'failed', error: e })
    }
  }

  /** Editing amount, category or description makes a new draft with a new id (4.1a rule 3). */
  const redraft = (id, d, changes) => {
    const next = { ...d, ...changes, draft_id: uuid(), timestamp: d.timestamp, edited: true }
    if (activeRef.current?.turnId === id) activeRef.current = { ...activeRef.current, cardKey: next.draft_id }
    return next
  }

  const submitEdit = (id, r) => {
    const { rupees, category, description } = r.form
    const d = r.draft
    const typed = rupees.trim()
    if (!typed && d.amount_paise == null) return patchReply(id, { form: { ...r.form, error: 'Type the amount in rupees.' } })
    if (typed && (!/^\d+$/.test(typed) || Number(typed) < 1 || Number(typed) > 500000)) {
      return patchReply(id, { form: { ...r.form, error: 'Type a whole number of rupees, from 1 to 5,00,000.' } })
    }
    const changed = typed || category !== d.category || description.trim() !== (d.description || '')
    const next = !changed ? d : redraft(id, d, {
      // The merchant's own typed rupees in the contract's unit (paise); the backend revalidates and formats it.
      ...(typed ? { amount_paise: Number(typed) * 100, amount_display: null, typed, input_source: 'MANUAL' } : {}),
      category,
      categoryUnclear: false,
      description: description.trim(),
    })
    return saveExpense(id, next)
  }

  const voidExpense = async (id, result) => {
    patchReply(id, { voidState: 'voiding', voidError: null })
    try {
      const v = await call((signal) => post(`/expenses/${encodeURIComponent(result.expense_id)}/void`, {
        merchant_id: merchantId, reason: 'Voided by the merchant on the Talk screen',
      }, { signal }), 15000)
      patchReply(id, { voidState: 'voided', voidResult: v })
    } catch (e) {
      if (e instanceof StaleError) return
      patchReply(id, { voidState: 'failed', voidError: e })
    }
  }

  /** Read a backend sentence aloud (POST /voice/speak). Only backend text is ever spoken. */
  const speak = async (id, sentence) => {
    patchReply(id, { speech: { state: 'loading' } })
    try {
      const r = await call((signal) => post('/voice/speak', { merchant_id: merchantId, language, text: sentence }, { signal }), 20000)
      const url = apiUrl(`/audio/${encodeURIComponent(r.audio_id)}`)
      patchReply(id, { speech: url ? { state: 'ready', url } : { state: 'error', message: 'Audio plays only with the live backend.' } })
    } catch (e) {
      if (e instanceof StaleError) return
      patchReply(id, { speech: { state: 'error', message: `No speech (${e.message}). The text above is what it says.` } })
    }
  }

  const onExpense = (id, r, action, value) => {
    const d = r.draft
    if (action === 'save' || action === 'retry') return saveExpense(id, d)
    if (action === 'edit') {
      return patchReply(id, { status: 'edit', error: null, form: { rupees: '', category: d.category, description: d.description || '', error: null } })
    }
    if (action === 'form') return patchReply(id, (x) => ({ ...x, form: { ...x.form, ...value, error: null } }))
    if (action === 'submit') return submitEdit(id, r)
    if (action === 'category') return patchReply(id, { draft: redraft(id, d, { category: value, categoryUnclear: true }) })
    if (action === 'cancel') {
      patchReply(id, { status: 'cancelled' })
      return release(id)
    }
    if (action === 'speak') return speak(id, r.confirmationText)
    if (action === 'void') return patchReply(id, { voidState: 'ask' })
    if (action === 'void-keep') return patchReply(id, { voidState: null })
    if (action === 'void-confirm') return voidExpense(id, r.result)
    return undefined
  }

  // ---- profit answer (4.3) ---------------------------------------------------------------------------------------
  const runProfit = async (id, date) => {
    const day = date || demoDate
    setReply(id, { kind: 'profit', status: 'loading', date: day })
    try {
      const body = { merchant_id: merchantId, language, intent: 'ASK_DAILY_PROFIT', ...(day ? { date: day } : {}) }
      const data = await call((signal) => post('/voice/answer', body, { signal }), 30000)
      patchReply(id, { status: 'done', data })
    } catch (e) {
      if (e instanceof StaleError) return
      patchReply(id, { status: 'error', error: e })
      // No spoken answer (no template for this language, or the number check failed): the ledger's numbers still show.
      if ((e.status === 422 || e.status === 500) && (!day || day === demoDate)) {
        try {
          const s = await call((signal) => get(`/merchants/${merchantId}/summary?include_sources=true`, { signal }), 15000)
          patchReply(id, { fallback: s })
        } catch {
          /* the answer's error is already on screen */
        }
      }
    }
  }

  // ---- payment question (4.4) ------------------------------------------------------------------------------------
  const openQuestion = (q) => {
    const a = activeRef.current
    if (a?.kind === 'question' && a.q.question_id === q.question_id) return
    const cardKey = uuid()
    const id = addTurn({ utterance: null, reply: { kind: 'question', q, stage: 'ask', status: 'open', cardKey } })
    activate({ turnId: id, cardKey, kind: 'question', q, stage: 'ask' })
  }

  /** The same question card continues in a newer turn (newest at the bottom). */
  const moveQuestion = (id, card, { stage, note = null, answer = null }) => {
    setReply(id, { kind: 'question', q: card.q, stage, status: 'open', cardKey: card.cardKey, note, answer })
    activate({ turnId: id, cardKey: card.cardKey, kind: 'question', q: card.q, stage, answer })
  }

  const confirmQuestion = async (id, card, answer) => {
    if (activeRef.current?.turnId !== id) moveQuestion(id, card, { stage: card.stage, answer })
    patchReply(id, { status: 'saving', answer, error: null, note: null })
    release(id)
    const body = {
      merchant_id: merchantId,
      question_id: card.q.question_id,
      confirmed_category: answer.category,
      channel: answer.channel,
      utterance_text: answer.utterance_text || null,
      remember_payer: Boolean(answer.remember),
    }
    try {
      const res = await call((signal) => post(`/payments/${encodeURIComponent(card.q.transaction_id)}/confirm`, body, { signal }), 20000)
      patchReply(id, { status: 'saved', result: res })
    } catch (e) {
      if (e instanceof StaleError) return
      patchReply(id, { status: 'failed', error: e })
      // A reversed payment or a mismatched question can't be answered here: the card stays closed.
      const final = ['REVERSED', 'QUESTION_MISMATCH'].includes(e.details?.reason)
      if (!final && !activeRef.current) {
        activeRef.current = { turnId: id, cardKey: card.cardKey, kind: 'question', q: card.q, stage: card.stage, answer }
        setActive(activeRef.current)
      }
    }
  }

  const onQuestion = (id, r, action) => {
    const card = { cardKey: r.cardKey, q: r.q, stage: r.stage }
    if (action === 'SALE') return confirmQuestion(id, card, { category: 'SALE', channel: 'TAP', utterance_text: null, remember: false })
    if (action === 'FAMILY') {
      const answer = { category: 'FAMILY', channel: 'TAP', utterance_text: null }
      patchReply(id, { stage: 'remember', answer, note: null })
      if (activeRef.current?.turnId === id) {
        activeRef.current = { ...activeRef.current, stage: 'remember', answer }
        setActive(activeRef.current)
      }
      return undefined
    }
    if (action === 'always') return confirmQuestion(id, card, { ...r.answer, remember: true })
    if (action === 'once') return confirmQuestion(id, card, { ...r.answer, remember: false })
    if (action === 'retry') return confirmQuestion(id, card, r.answer)
    if (action === 'close') {
      patchReply(id, { status: 'closed' })
      return release(id)
    }
    return undefined
  }

  /** A spoken or typed answer to the question card that was on screen when it was sent. */
  const answerQuestion = (id, card, res, utt) => {
    const ent = res.entities || {}
    const cat = ent.confirmed_category
    if (res.needs_clarification || !cat) return moveQuestion(id, card, { stage: card.stage, note: res.clarification_text || W.clarify_category })
    const said = [card.answer?.utterance_text, utt.text].filter(Boolean).join('. ')
    const answer = { category: cat, channel: 'VOICE', utterance_text: said }
    if (card.stage === 'remember') {
      if (cat === 'FAMILY' && ent.remember_payer) return confirmQuestion(id, card, { ...answer, remember: true })
      if (cat === 'SALE') return moveQuestion(id, card, { stage: 'ask', note: W.clarify_category })
      return moveQuestion(id, card, { stage: 'remember', answer: card.answer })
    }
    if (cat === 'SALE') return confirmQuestion(id, card, { ...answer, remember: false })
    if (ent.remember_payer) return confirmQuestion(id, card, { ...answer, remember: true })
    return moveQuestion(id, card, { stage: 'remember', answer: { ...answer, utterance_text: utt.text } })
  }

  // ---- one utterance: interpret, then branch on intent -------------------------------------------------------------
  const route = (id, res, utt, card) => {
    const ent = res.entities || {}
    if (card && res.intent === 'CONFIRM_TRANSACTION') return answerQuestion(id, card, res, utt)
    if (card && res.intent === 'UNKNOWN') {
      return moveQuestion(id, card, { stage: card.stage, note: res.clarification_text || W.clarify_category, answer: card.answer })
    }
    if (res.intent === 'LOG_EXPENSE') {
      if (res.needs_clarification || ent.amount_paise == null) {
        clarifyTries.current += 1
        const ask = res.clarification_text || W.clarify_amount
        if (clarifyTries.current >= 2) {
          clarifyTries.current = 0
          return openExpense(id, { utt, manual: true, note: ask, hint: ent })
        }
        return setReply(id, {
          kind: 'say', tone: 'clarify', text: ask,
          detail: "The amount couldn't be checked against what was said, so there is nothing to save yet. Say the amount again.",
        })
      }
      clarifyTries.current = 0
      return openExpense(id, { res, utt })
    }
    if (res.intent === 'ASK_DAILY_PROFIT') return runProfit(id, ent.date)
    // UNKNOWN, or CONFIRM_TRANSACTION with no question card on screen (the backend treats that as UNKNOWN too).
    return setReply(id, { kind: 'say', tone: 'not_understood', text: res.clarification_text || W.not_understood, taps: true })
  }

  /** 4.1a rule 1: the question card on screen when the merchant speaks or sends, never looked up later. */
  const boundCard = () => (activeRef.current?.kind === 'question' ? activeRef.current : null)

  const understand = async (id, utt, card = boundCard()) => {
    setReply(id, { kind: 'pending', stage: 'understanding' })
    setBusy(true)
    const gen = genRef.current
    try {
      const res = await call((signal) => interpret({
        merchant_id: merchantId,
        language,
        text: utt.text,
        voice_log_id: utt.voice_log_id || null,
        open_question_id: card ? card.q.question_id : null,
      }, { signal }), 30000)
      if (card && activeRef.current?.cardKey !== card.cardKey) return setReply(id, { kind: 'discarded', q: card.q })
      return route(id, res, utt, card)
    } catch (e) {
      if (e instanceof StaleError) return undefined
      return setReply(id, failure(e, 'interpret'))
    } finally {
      if (gen === genRef.current) setBusy(false)
    }
  }

  const sendText = (value, source) => {
    const said = value.trim()
    if (!said || busy) return
    const id = addTurn({ utterance: { source, text: said }, reply: { kind: 'pending', stage: 'understanding' } })
    understand(id, { text: said, source, voice_log_id: null })
  }

  const transcribe = async (id, blob, clip, card) => {
    setBusy(true)
    const gen = genRef.current
    patchSaid(id, { status: 'transcribing' })
    setReply(id, { kind: 'pending', stage: 'understanding' })
    try {
      if (!blob.size) {
        patchSaid(id, { status: null, text: '' })
        return setReply(id, { kind: 'say', tone: 'clarify', text: W.no_speech })
      }
      const form = new FormData()
      form.append('audio', blob, clip ? `${clip.demoKey.split('/')[1]}.wav` : fileNameFor(blob))
      form.append('language', language)
      form.append('merchant_id', merchantId)
      if (clip) form.append('demo_key', clip.demoKey)
      const tr = await call((signal) => post('/voice/transcribe', form, { signal }), 30000)
      const heard = (tr.text || '').trim()
      patchSaid(id, { status: null, text: heard, recognition_mode: tr.recognition_mode, voice_log_id: tr.voice_log_id })
      if (!heard) return setReply(id, { kind: 'say', tone: 'clarify', text: W.no_speech })
      if (card && activeRef.current?.cardKey !== card.cardKey) return setReply(id, { kind: 'discarded', q: card.q })
      return await understand(id, { text: heard, source: clip ? 'clip' : 'mic', voice_log_id: tr.voice_log_id }, card)
    } catch (e) {
      if (e instanceof StaleError) return undefined
      patchSaid(id, { status: 'failed' })
      return setReply(id, failure(e, 'transcribe'))
    } finally {
      if (gen === genRef.current) setBusy(false)
    }
  }

  const micProblem = (denied) => {
    setMicBlocked(true)
    addTurn({
      utterance: null,
      reply: {
        kind: 'say', tone: 'failure', title: 'Mic not available', taps: true,
        detail: denied
          ? "The mic isn't allowed in this browser. Type in the box below, or tap a button."
          : "This browser can't record here. Type in the box below, or tap a button.",
      },
    })
    textRef.current?.focus()
  }

  const onMic = async () => {
    if (recRef.current) return recRef.current.stop()
    if (!micSupported()) return micProblem(false)
    const id = addTurn({ utterance: { source: 'mic', text: null, status: 'listening' }, reply: null })
    const gen = genRef.current
    try {
      const rec = await startRecording({
        onDone: (blob) => {
          recRef.current = null
          setListening(false)
          if (gen === genRef.current) transcribe(id, blob, null, boundCard())
        },
      })
      if (gen !== genRef.current) return rec.cancel()
      recRef.current = rec
      setMicBlocked(false)
      setSeconds(0)
      return setListening(true)
    } catch (e) {
      removeTurn(id)
      return micProblem(e?.name === 'NotAllowedError' || e?.name === 'SecurityError')
    }
  }

  const playClip = async (clip) => {
    if (busy) return
    const card = boundCard()
    const id = addTurn({ utterance: { source: 'clip', text: null, status: 'transcribing', clipText: clip.text }, reply: { kind: 'pending', stage: 'understanding' } })
    try {
      new Audio(clip.url).play().catch(() => {})
      const blob = await (await fetch(clip.url)).blob()
      await transcribe(id, blob, clip, card)
    } catch (e) {
      setReply(id, failure(e, 'transcribe'))
    }
  }

  // Judge tour: say the morning expense as Murugan would. The recorded clip if it is registered (its own badge
  // shows "Recorded demo clip"), otherwise the sentence is typed into the text box and sent. Starts a clean
  // conversation so a card from an earlier run is never mistaken for this one.
  const tourRef = useRef(null)
  tourRef.current = { clips, playClip, sendText, setText, resetAll }
  useEffect(() => {
    const on = async (e) => {
      if (e.detail?.action !== 'expense-utterance') return
      e.detail.ack?.()
      tourRef.current.resetAll()
      await new Promise((r) => setTimeout(r, 300))
      const clip = tourRef.current.clips.find((c) => c.demoKey === e.detail.clipKey)
      if (clip) {
        tourRef.current.playClip(clip)
        return e.detail.done?.('clip')
      }
      tourRef.current.setText(e.detail.text)
      await new Promise((r) => setTimeout(r, 900)) // let the words show in the box first
      tourRef.current.sendText(e.detail.text, 'typed')
      tourRef.current.setText('')
      return e.detail.done?.('typed')
    }
    window.addEventListener(TOUR_EVENT, on)
    return () => window.removeEventListener(TOUR_EVENT, on)
  }, [])

  // The two big tap buttons (every voice path has a tap path).
  const tapProfit = () => {
    const id = addTurn({ utterance: { source: 'tap', text: t.todaysProfit }, reply: { kind: 'pending', stage: 'understanding' } })
    runProfit(id, demoDate)
  }
  const tapExpense = () => {
    const id = addTurn({ utterance: { source: 'tap', text: t.addExpense }, reply: { kind: 'pending', stage: 'understanding' } })
    openExpense(id, { manual: true })
  }

  // Elapsed seconds while the mic is on.
  useEffect(() => {
    if (!listening) return undefined
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [listening])

  // #/talk?ask=profit&n=<nonce> (judge tour) asks today's profit once per nonce, through the same tap path.
  const askedFor = useRef(null)
  useEffect(() => {
    if (params?.ask !== 'profit' || !demoDate || askedFor.current === (params.n || 'once')) return
    askedFor.current = params.n || 'once'
    tapProfit()
  })

  // #/talk?question=Q-... opens that question's card (by id, never by position).
  const linked = useRef(null)
  useEffect(() => {
    const wanted = params?.question
    if (!wanted || linked.current === wanted) return
    const q = questions.data?.items?.find((x) => x.question_id === wanted)
    if (q) {
      linked.current = wanted
      openQuestion(q)
    }
  })

  // Keep the newest turn in view, just above the text box.
  const last = turns[turns.length - 1]
  const tail = last ? `${turns.length}:${last.reply?.kind}:${last.reply?.status}:${last.reply?.stage}:${last.utterance?.text}` : ''
  useEffect(() => {
    if (tail) endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [tail])

  const bound = active?.kind === 'question' ? active : null
  const examples = bound ? (bound.stage === 'remember' ? W.rememberExamples : W.answerExamples) : W.examples
  const shownClips = clips.filter((c) => (bound ? c.answers : !c.answers))

  return (
    <>
      <header className="page-head">
        <div>
          <span className="label">04 · {merchant?.display_name || merchantId}</span>
          <h1>Say it or type it.</h1>
          <p className="lede">
            Log an expense or ask today's profit in {t.languageName}. Nothing is saved until you tap to confirm, and every
            rupee shown comes from the ledger.
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn" onClick={resetAll} disabled={!turns.length}>
            <RotateCcw aria-hidden="true" /> Start over
          </button>
        </div>
      </header>

      <div className="talk">
        <div className="talk-main">
          <ol className="talk-thread" aria-label="Conversation" aria-live="polite">
            {!turns.length && (
              <li className="turn">
                <StartCard W={W} t={t} onExpense={tapExpense} onProfit={tapProfit} />
              </li>
            )}
            {turns.map((turn) => (
              <li className="turn" key={turn.id}>
                {turn.utterance && <Said u={turn.utterance} lang={t.lang} />}
                {turn.reply && (
                  <div className="reply">
                    <span className="visually-hidden">Naanayam:</span>
                    <Reply turn={turn} W={W} t={t} demoDate={demoDate}
                      onExpense={onExpense} onQuestion={onQuestion} onExpenseTap={tapExpense} onProfitTap={tapProfit} />
                  </div>
                )}
              </li>
            ))}
          </ol>

          <Composer
            W={W} t={t} value={text} onChange={setText} textRef={textRef}
            onSubmit={() => { sendText(text, 'typed'); setText('') }}
            busy={busy} listening={listening} seconds={seconds} micBlocked={micBlocked} onMic={onMic}
            examples={examples} onExample={(ex) => sendText(ex, 'example')}
            clips={shownClips} onClip={playClip}
            bound={bound}
          />
          <div ref={endRef} className="talk-end" />
        </div>

        <WaitingList questions={questions} active={bound} onOpen={openQuestion} health={health} />
      </div>
    </>
  )
}

function Reply({ turn, W, t, demoDate, onExpense, onQuestion, onExpenseTap, onProfitTap }) {
  const r = turn.reply
  const id = turn.id
  if (!r) return null
  if (r.kind === 'pending') return <PendingCard stage={r.stage} />
  if (r.kind === 'expense') return <ExpenseCard r={r} W={W} t={t} demoDate={demoDate} act={(a, v) => onExpense(id, r, a, v)} />
  if (r.kind === 'profit') return <ProfitCard r={r} t={t} />
  if (r.kind === 'question') return <QuestionCard r={r} W={W} t={t} act={(a) => onQuestion(id, r, a)} />
  if (r.kind === 'discarded') {
    return <SayCard r={{ tone: 'clarify', title: 'Ignored', detail: `This answer arrived after the card for ${r.q.payer_name}'s payment was closed, so nothing was saved.` }} W={W} t={t} />
  }
  return <SayCard r={r} W={W} t={t} onExpense={onExpenseTap} onProfit={onProfitTap} />
}
