// Microphone recording for Talk (VOICE_AND_NOTICE 4.1): max 15 s. Stop ends it at once; otherwise it stops by itself
// after 2.5 s of silence once speech was heard, never in the first 3 s, so a pause to think doesn't cut the sentence.
// "Silence" is measured against this room: the quietest level heard so far (the mic's noise floor) times three,
// so a soft voice still counts as speech and a fan doesn't. In a loud hall it may not hear silence: Stop, or 15 s.
// The bytes go to POST /voice/transcribe as they are; nothing is transcribed in the browser.

const MAX_MS = 15000
const SILENCE_MS = 2500
const MIN_MS = 3000 // never stops by itself before this
const SPEECH_MS = 400 // this much sound above the floor counts as having heard speech (a click doesn't)
const LOUD_MIN = 0.006 // the speech threshold never drops below this (a silent mic)...
const LOUD_MAX = 0.03 // ...or rises above this (a noisy room)
const TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg']

export function micSupported() {
  return Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder)
}

/** File name with an extension the contract accepts (webm/ogg/wav/mp3). */
export function fileNameFor(blob) {
  const t = blob.type || ''
  if (t.includes('ogg')) return 'speech.ogg'
  if (t.includes('wav')) return 'speech.wav'
  if (t.includes('mpeg') || t.includes('mp3')) return 'speech.mp3'
  return 'speech.webm'
}

/**
 * Start recording. Resolves to { stop, cancel } once the mic is open; rejects with the getUserMedia error
 * (NotAllowedError when permission is denied). onDone(blob) runs after stop() or the automatic stop.
 */
export async function startRecording({ onDone, onLevel }) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mimeType = TYPES.find((t) => window.MediaRecorder.isTypeSupported?.(t))
  const rec = new window.MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  const chunks = []
  let cancelled = false
  let ctx = null
  let poll = null
  let maxTimer = null

  const cleanup = () => {
    clearTimeout(maxTimer)
    clearInterval(poll)
    stream.getTracks().forEach((t) => t.stop())
    ctx?.close().catch(() => {})
  }
  const stop = () => {
    if (rec.state !== 'inactive') rec.stop()
  }
  rec.ondataavailable = (e) => {
    if (e.data?.size) chunks.push(e.data)
  }
  rec.onstop = () => {
    cleanup()
    if (!cancelled) onDone(new Blob(chunks, { type: rec.mimeType || mimeType || 'audio/webm' }))
  }

  // Silence detection. If the browser has no AudioContext the 15 s limit (or the Stop button) still ends it.
  try {
    ctx = new (window.AudioContext || window.webkitAudioContext)()
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 2048
    ctx.createMediaStreamSource(stream).connect(analyser)
    const buf = new Float32Array(analyser.fftSize)
    const started = Date.now()
    let floor = Infinity // quietest level so far
    let loudFor = 0 // ms of sound above the threshold, in total
    let lastLoud = Date.now()
    poll = setInterval(() => {
      analyser.getFloatTimeDomainData(buf)
      let sum = 0
      for (let i = 0; i < buf.length; i += 1) sum += buf[i] * buf[i]
      const rms = Math.sqrt(sum / buf.length)
      onLevel?.(Math.min(1, rms * 8))
      if (rms > 0) floor = Math.min(floor, rms)
      const threshold = Math.min(LOUD_MAX, Math.max(LOUD_MIN, (Number.isFinite(floor) ? floor : 0) * 3))
      const now = Date.now()
      if (rms > threshold) {
        loudFor += 100
        lastLoud = now
      } else if (loudFor >= SPEECH_MS && now - started > MIN_MS && now - lastLoud > SILENCE_MS) {
        stop()
      }
    }, 100)
  } catch {
    ctx = null
  }

  maxTimer = setTimeout(stop, MAX_MS)
  rec.start()
  return {
    stop,
    cancel() {
      cancelled = true
      stop()
      cleanup()
    },
  }
}

export const MAX_SECONDS = MAX_MS / 1000
