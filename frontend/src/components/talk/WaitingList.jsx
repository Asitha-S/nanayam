// Side column of Talk: today's payments waiting for an answer (opened by question_id), and how each line was heard.
import { MessageCircleQuestion } from 'lucide-react'
import { Badge, LoadState, Money, clockTime } from '../ui'
import { words } from './strings'

const MODE_TEXT = {
  cache_only: 'Speech runs from saved results only. A new recording can\'t be transcribed; type it instead.',
  cache_first: 'Saved results first; new speech goes to Sarvam live.',
  live: 'Every recording goes to Sarvam live.',
}

export default function WaitingList({ questions, active, onOpen, health }) {
  const items = questions.data?.items || []
  return (
    <aside className="talk-side">
      <section className={`panel talk-waiting ${items.length ? 'signal' : ''}`} aria-labelledby="talk-waiting-h">
        <span className="label" id="talk-waiting-h">Waiting for an answer today</span>
        {!questions.data && <LoadState state={questions} what="open questions" />}
        {questions.data && !items.length && <p className="note">No payment is waiting for an answer.</p>}
        {items.length > 0 && (
          <ul>
            {items.map((q) => {
              const open = active?.q.question_id === q.question_id
              return (
                <li key={q.question_id}>
                  <div>
                    <b>{q.payer_name}</b>
                    <small>{clockTime(q.timestamp)} · suggested {words(q.suggested_classification)}</small>
                  </div>
                  <Money amount={q} />
                  <button type="button" className="btn" onClick={() => onOpen(q)} disabled={open} aria-pressed={open}>
                    <MessageCircleQuestion aria-hidden="true" /> {open ? 'Open below' : 'Answer here'}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>
      <section className="panel talk-heard" aria-labelledby="talk-heard-h">
        <span className="label" id="talk-heard-h">How each line was heard</span>
        <dl>
          <dt>Typed</dt><dd>Written in the box. No speech involved.</dd>
          <dt>Heard live</dt><dd>Your voice, transcribed by Sarvam now.</dd>
          <dt>Heard live (cached)</dt><dd>The same recording was transcribed before.</dd>
          <dt><Badge kind="clip" /></dt><dd>A clip we recorded. Never shown as live.</dd>
        </dl>
        {health?.demo_mode && <p className="note"><b>Speech mode: {words(health.demo_mode)}.</b> {MODE_TEXT[health.demo_mode]}</p>}
      </section>
    </aside>
  )
}
