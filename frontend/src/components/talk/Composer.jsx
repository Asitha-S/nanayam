// The Talk input, fixed below the conversation: a big text box in the merchant's language first, the mic second,
// then example sentences and (when registered) recorded demo clips, always labelled as recorded.
import { MessageCircleQuestion, Mic, MicOff, SendHorizontal, Square } from 'lucide-react'
import { Badge, Money } from '../ui'
import { MAX_SECONDS } from './mic'

export default function Composer({
  W, t, value, onChange, onSubmit, textRef, busy, listening, seconds, micBlocked, onMic,
  examples, onExample, clips, onClip, bound,
}) {
  const submit = (e) => {
    e.preventDefault()
    if (!busy && value.trim()) onSubmit()
  }
  return (
    <form className={`talk-composer ${bound ? 'is-bound' : ''}`} onSubmit={submit}>
      {bound && (
        <p className="talk-bound" role="status">
          <MessageCircleQuestion aria-hidden="true" />
          <span>Answering <b>{bound.q.payer_name}</b>'s <Money amount={bound.q} /> payment{bound.stage === 'remember' ? ' (always family?)' : ''}.</span>
        </p>
      )}
      <div className="talk-inputrow">
        <label className="visually-hidden" htmlFor="talk-text">Type in {t.languageName}</label>
        <textarea
          id="talk-text" ref={textRef} lang={t.lang} rows={2} value={value} placeholder={bound ? W.typeHere : W.placeholder}
          disabled={listening} onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) submit(e)
          }}
        />
        <button type="submit" className="btn big ink talk-send" disabled={busy || listening || !value.trim()}>
          <SendHorizontal aria-hidden="true" /> Send
        </button>
        <button type="button" className={`talk-mic ${listening ? 'is-on' : ''}`} onClick={onMic}
          aria-pressed={listening} disabled={busy && !listening}
          aria-label={listening ? 'Stop recording' : 'Speak'}>
          {listening ? <Square aria-hidden="true" /> : micBlocked ? <MicOff aria-hidden="true" /> : <Mic aria-hidden="true" />}
          <span>{listening ? `Stop · ${seconds}s` : 'Speak'}</span>
        </button>
      </div>
      <div className="talk-tries">
        <span className="label">{listening ? `Listening, up to ${MAX_SECONDS} s. It stops when you pause.` : 'Try'}</span>
        {!listening && examples.map((ex) => (
          <button key={ex} type="button" className="try" onClick={() => onExample(ex)} disabled={busy}>
            <span lang={t.lang}>{ex}</span>
          </button>
        ))}
        {!listening && clips.map((c) => (
          <button key={c.demoKey} type="button" className="try clip" onClick={() => onClip(c)} disabled={busy}>
            <Badge kind="clip" />
            <span lang={c.lang}>{c.text}</span>
          </button>
        ))}
      </div>
    </form>
  )
}
