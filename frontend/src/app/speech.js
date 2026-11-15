// The Soundbox voice. One queue for the whole app: items are spoken strictly one after another, never overlapping,
// across calls too. Per item: (a) Sarvam speech from POST /voice/speak (3 s budget), played from GET /audio/{id};
// (b) on 503, an error or a timeout, the browser's own voice for the language (ta-IN / te-IN), or the English
// sentence with an English voice when the browser has no such voice; (c) otherwise text only.
// Nothing is spoken until sound is turned on by a tap on "Turn on Soundbox sound" (unlockSound; browsers block audio
// before a tap), or while muted. Sound is never turned on by itself: after a reload it is off until pressed again.
// Both voices play at the same level: Sarvam audio is peak-normalised to LEVEL, the device voice gets volume LEVEL.
import { useSyncExternalStore } from 'react'
import { USING_FIXTURES, apiUrl, post } from '../api'

const MUTE_KEY = 'naanayam.sound.muted'
const SPEAK_BUDGET_MS = 3000 // POST /voice/speak: a live Sarvam call takes about 1-2 s (cache_first, unsaved line)
const AUDIO_BUDGET_MS = 3000 // fetching and decoding the audio file
const START_BUDGET_MS = 2500 // a device voice that hasn't started by then never will
const LEVEL = 0.85 // one output level for both voices
const TARGET_PEAK = 0.95 // Sarvam audio is scaled so its loudest sample sits here, then multiplied by LEVEL

function readSession(key) {
  try {
    return window.sessionStorage.getItem(key)
  } catch {
    return null
  }
}
function writeSession(key, value) {
  try {
    if (value === null) window.sessionStorage.removeItem(key)
    else window.sessionStorage.setItem(key, value)
  } catch {
    /* private mode: the choice just isn't remembered */
  }
}

// ---- store (read by useSpeech) ----
let state = { unlocked: false, muted: readSession(MUTE_KEY) === '1', speaking: false, lastVoice: null, current: null }
const listeners = new Set()
function set(patch) {
  state = { ...state, ...patch }
  listeners.forEach((l) => l())
}
const subscribe = (l) => {
  listeners.add(l)
  return () => listeners.delete(l)
}
const snapshot = () => state

// ---- unlocking ----
let ctx = null
function audioContext() {
  if (ctx) return ctx
  const AC = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)
  if (!AC) return null
  try {
    ctx = new AC()
  } catch {
    ctx = null
  }
  return ctx
}

/** True once sound was turned on by a tap in this page (and the browser hasn't blocked it since). */
export function soundUnlocked() {
  return state.unlocked
}

/** Call inside a user gesture (a click or a key press): unlocks audio playback and speechSynthesis. */
export function unlockSound() {
  try {
    const c = audioContext()
    if (c) {
      c.resume?.()
      const src = c.createBufferSource()
      src.buffer = c.createBuffer(1, 1, 22050)
      src.connect(c.destination)
      src.start(0)
    }
  } catch {
    /* no Web Audio: the <audio> element path is used */
  }
  try {
    const synth = window.speechSynthesis
    if (synth && typeof window.SpeechSynthesisUtterance !== 'undefined') {
      const u = new window.SpeechSynthesisUtterance(' ')
      u.volume = 0
      synth.resume?.()
      synth.speak(u)
      synth.getVoices()
    }
  } catch {
    /* no device voice */
  }
  set({ unlocked: true })
}

/** The browser refused to play without a fresh tap: show the "Turn on Soundbox sound" button again. */
function relock() {
  if (state.unlocked) set({ unlocked: false })
}

export function isMuted() {
  return state.muted
}

export function setMuted(muted) {
  const m = Boolean(muted)
  writeSession(MUTE_KEY, m ? '1' : null)
  set({ muted: m })
  if (m) stopCurrent?.()
}

const canSound = () => state.unlocked && !state.muted

// ---- the queue ----
let tail = Promise.resolve()
let gen = 0 // clearSpeech() bumps it: queued items of an older generation are shown as text only
let stopCurrent = null

/**
 * Queue items [{ text, textEn, lang: 'ta'|'te', merchantId, ...anything the screen wants back in `current` }].
 * Resolves with the voice used per item: 'SARVAM' | 'DEVICE' | 'TEXT'.
 */
export function speak(items) {
  const list = [].concat(items || []).filter((i) => i && (i.text || i.textEn))
  const myGen = gen
  const job = tail.then(async () => {
    const used = []
    for (const item of list) used.push(myGen === gen ? await playOne(item, myGen) : 'TEXT')
    return used
  })
  tail = job.catch(() => {})
  return job
}

/** Drop everything queued and stop what is playing (switching merchant, leaving the screen). */
export function clearSpeech() {
  gen += 1
  stopCurrent?.()
  if (state.current || state.speaking) set({ current: null, speaking: false })
}

async function playOne(item, myGen) {
  set({ current: item, speaking: false })
  let voice = 'TEXT'
  try {
    if (canSound()) voice = (await viaSarvam(item, myGen)) || (myGen === gen && canSound() && (await viaDevice(item, myGen))) || 'TEXT'
  } catch {
    voice = 'TEXT'
  }
  stopCurrent = null
  set({ current: null, speaking: false, lastVoice: voice })
  return voice
}

// (a) Sarvam
async function viaSarvam(item, myGen) {
  if (USING_FIXTURES || !item.text || !item.merchantId || !['ta', 'te'].includes(item.lang)) return null
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), SPEAK_BUDGET_MS)
  let res
  try {
    res = await post('/voice/speak', { merchant_id: item.merchantId, language: item.lang, text: item.text }, { signal: ctrl.signal })
  } catch {
    return null // 503 SARVAM_UNAVAILABLE / CACHE_MISS, an error or the budget ran out
  } finally {
    clearTimeout(timer)
  }
  const url = res?.audio_id ? apiUrl(`/audio/${encodeURIComponent(res.audio_id)}`) : null
  if (!url || myGen !== gen || !canSound()) return null
  return (await playUrl(url, myGen)) ? 'SARVAM' : null
}

function peakGain(buf) {
  let peak = 0
  for (let c = 0; c < buf.numberOfChannels; c += 1) {
    const d = buf.getChannelData(c)
    for (let i = 0; i < d.length; i += 1) {
      const v = d[i] < 0 ? -d[i] : d[i]
      if (v > peak) peak = v
    }
  }
  return peak > 0.01 ? Math.min(4, TARGET_PEAK / peak) : 1
}

async function playUrl(url, myGen) {
  const c = audioContext()
  if (c && c.state !== 'closed') {
    let buf = null
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), AUDIO_BUDGET_MS)
    try {
      // without a fresh tap resume() may never settle: give it a moment, then check the state below
      if (c.state === 'suspended') await Promise.race([c.resume(), new Promise((r) => { setTimeout(r, 300) })])
      const r = await fetch(url, { signal: ctrl.signal })
      if (!r.ok) return false
      buf = await c.decodeAudioData(await r.arrayBuffer())
    } catch (e) {
      if (e?.name === 'AbortError') return false
      buf = null // CORS or decoding: try the <audio> element below
    } finally {
      clearTimeout(timer)
    }
    if (buf) {
      if (myGen !== gen || !canSound()) return false
      if (c.state !== 'running') {
        relock()
        return false
      }
      return new Promise((resolve) => {
        const src = c.createBufferSource()
        const gain = c.createGain()
        src.buffer = buf
        gain.gain.value = LEVEL * peakGain(buf)
        src.connect(gain).connect(c.destination)
        let settled = false
        const finish = () => {
          if (settled) return
          settled = true
          clearTimeout(cap)
          resolve(true)
        }
        const cap = setTimeout(() => { try { src.stop() } catch { /* already stopped */ } finish() }, buf.duration * 1000 + 1500)
        src.onended = finish
        stopCurrent = () => { try { src.stop() } catch { /* already stopped */ } finish() }
        set({ speaking: true, lastVoice: 'SARVAM' })
        src.start()
      })
    }
  }
  return playElement(url)
}

function playElement(url) {
  return new Promise((resolve) => {
    const el = new Audio()
    el.preload = 'auto'
    el.volume = LEVEL
    let started = false
    let settled = false
    let cap = null
    const finish = (ok) => {
      if (settled) return
      settled = true
      clearTimeout(startCap)
      clearTimeout(cap)
      el.pause()
      el.removeAttribute('src')
      resolve(ok)
    }
    const startCap = setTimeout(() => finish(false), AUDIO_BUDGET_MS)
    el.onplaying = () => {
      if (started) return
      started = true
      clearTimeout(startCap)
      set({ speaking: true, lastVoice: 'SARVAM' })
      cap = setTimeout(() => finish(true), ((Number.isFinite(el.duration) ? el.duration : 12) * 1000) + 1500)
    }
    el.onended = () => finish(true)
    el.onerror = () => finish(started)
    stopCurrent = () => finish(started)
    el.src = url
    el.play().catch((e) => {
      if (e?.name === 'NotAllowedError') relock()
      finish(false)
    })
  })
}

// (b) the device's own voice
const norm = (lang) => (lang || '').toLowerCase().replace('_', '-')

function loadVoices(synth) {
  const now = synth.getVoices()
  if (now.length) return Promise.resolve(now)
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(t)
      synth.removeEventListener?.('voiceschanged', done)
      resolve(synth.getVoices())
    }
    const t = setTimeout(done, 1000)
    synth.addEventListener?.('voiceschanged', done)
  })
}

/** Best voice for a language: lang-IN first, voices that work offline first. */
function pickVoice(voices, code) {
  const all = voices.filter((v) => norm(v.lang).startsWith(code))
  const score = (v) => (norm(v.lang) === `${code}-in` ? 2 : 0) + (v.localService ? 1 : 0)
  return all.sort((a, b) => score(b) - score(a))[0] || null
}

/** The browser's voices as [{ name, lang, localService }] (for checks and the report). */
export function deviceVoices() {
  try {
    return (window.speechSynthesis?.getVoices() || []).map((v) => ({ name: v.name, lang: v.lang, localService: v.localService }))
  } catch {
    return []
  }
}

let keep = null // Chrome drops the end event of an utterance that was garbage-collected
async function viaDevice(item, myGen) {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
  if (!synth || typeof window.SpeechSynthesisUtterance === 'undefined') return null
  const voices = await loadVoices(synth)
  let voice = item.text && ['ta', 'te'].includes(item.lang) ? pickVoice(voices, item.lang) : null
  let text = item.text
  let lang = `${item.lang}-IN`
  if (!voice) {
    voice = pickVoice(voices, 'en')
    text = item.textEn
    lang = voice ? voice.lang : 'en-IN'
  }
  if (!voice || !text || !canSound() || myGen !== gen) return null // cleared or muted while the voices loaded
  const ok = await new Promise((resolve) => {
    const u = new window.SpeechSynthesisUtterance(text)
    keep = u
    u.voice = voice
    u.lang = lang
    u.volume = LEVEL
    u.rate = 1
    u.pitch = 1
    let started = false
    let settled = false
    const finish = (spoken) => {
      if (settled) return
      settled = true
      clearTimeout(startCap)
      clearTimeout(cap)
      keep = null
      resolve(spoken)
    }
    const startCap = setTimeout(() => { if (!started) { synth.cancel(); finish(false) } }, START_BUDGET_MS)
    const cap = setTimeout(() => { synth.cancel(); finish(started) }, 4000 + text.length * 120)
    u.onstart = () => {
      started = true
      clearTimeout(startCap)
      set({ speaking: true, lastVoice: 'DEVICE' })
    }
    u.onend = () => finish(true)
    u.onerror = (e) => {
      if (e?.error === 'not-allowed') relock()
      finish(started && e?.error !== 'not-allowed')
    }
    stopCurrent = () => { synth.cancel(); finish(started) }
    synth.resume?.()
    synth.speak(u)
  })
  return ok ? 'DEVICE' : null
}

/** { unlocked, muted, speaking, lastVoice: 'SARVAM'|'DEVICE'|'TEXT'|null, current: the item being spoken or null } */
export function useSpeech() {
  return useSyncExternalStore(subscribe, snapshot)
}
