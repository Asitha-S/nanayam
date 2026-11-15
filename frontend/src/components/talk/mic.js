// Microphone recording for Talk (VOICE_AND_NOTICE 4.1): max 15 s, stops by itself after 1.5 s of silence once
// speech was heard. The bytes go to POST /voice/transcribe as they are; nothing is transcribed in the browser.

const MAX_MS = 15000
const SILENCE_MS = 1500
const LOUD_RMS = 0.02
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
    let heard = false
    let lastLoud = Date.now()
    poll = setInterval(() => {
      analyser.getFloatTimeDomainData(buf)
      let sum = 0
      for (let i = 0; i < buf.length; i += 1) sum += buf[i] * buf[i]
      const rms = Math.sqrt(sum / buf.length)
      onLevel?.(Math.min(1, rms * 8))
      if (rms > LOUD_RMS) {
        heard = true
        lastLoud = Date.now()
      } else if (heard && Date.now() - lastLoud > SILENCE_MS) {
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
