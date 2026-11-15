// Talk screen turns: what the merchant said, and Naanayam's card in reply. Every amount is the backend's display
// string through <Money>; the merchant's own words are shown with lang set.
import {
  CircleHelp, Loader2, Pause, ShieldCheck, TriangleAlert, Volume2,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { USING_FIXTURES, apiUrl } from '../../api'
import { Badge, Money, clockTime, confidenceText, count, ledgerHref, longDate } from '../ui'
import { EXPENSE_CATEGORIES, words } from './strings'

const LARGE_PAISE = 5000000 // VOICE_AND_NOTICE 4.2: above ₹50,000 the card warns and needs a tap

const HEARD = { LIVE: 'Heard live', CACHED_LIVE: 'Heard live (cached)' }

/** The merchant's side of a turn. */
export function Said({ u, lang }) {
  let meta
  if (u.source === 'clip' || u.recognition_mode === 'RECORDED_DEMO') meta = <Badge kind="clip" />
  else if (u.source === 'mic') meta = <span className="said-src">{HEARD[u.recognition_mode] || 'Your voice'}</span>
  else meta = <span className="said-src">{{ typed: 'Typed', example: 'Example sentence', tap: 'Tapped' }[u.source]}</span>

  let body
  if (u.status === 'listening') body = <p className="said-wait">Listening…</p>
  else if (u.status === 'transcribing') body = <p className="said-wait">{u.clipText ? <span lang={lang}>{u.clipText}</span> : 'Writing down what was said…'}</p>
  else if (u.status === 'failed' && !u.text) body = <p className="said-wait">Not transcribed</p>
  else if (u.text === '') body = <p className="said-wait">Nothing heard</p>
  else body = <p lang={lang}>{u.text}</p>

  return (
    <div className="said">
      <span className="visually-hidden">{u.source === 'tap' ? 'You tapped:' : 'You said:'}</span>
      {meta}
      {body}
    </div>
  )
}

function Head({ tone, label, children }) {
  return (
    <div className={`tcard-head ${tone}`}>
      <span className="label">{label}</span>
      {children}
    </div>
  )
}

/** Big tap answers, the merchant's word on top and English under it. */
export function BigTaps({ items, label }) {
  return (
    <div className={`bigtaps n${items.length}`} role="group" aria-label={label}>
      {items.map((it) => (
        <button key={it.key} type="button" className={`bigtap ${it.tone || ''}`} onClick={it.onClick} disabled={it.disabled}>
          <span lang={it.lang}>{it.text}</span>
          <small>{it.en}</small>
        </button>
      ))}
    </div>
  )
}

function StartTaps({ t, onExpense, onProfit }) {
  return (
    <BigTaps label="Tap instead of speaking" items={[
      { key: 'expense', text: t.addExpense, lang: t.lang, en: 'Add an expense', tone: 'sun', onClick: onExpense },
      { key: 'profit', text: t.todaysProfit, lang: t.lang, en: "Today's profit", tone: 'lime', onClick: onProfit },
    ]} />
  )
}

function ErrorLine({ error, hint }) {
  if (!error) return null
  return (
    <p className="error-banner" role="alert">
      <TriangleAlert aria-hidden="true" />
      <span>{error.message}{error.code ? ` (${error.code})` : ''}.{hint ? ` ${hint}` : ''}</span>
    </p>
  )
}

/** Play a backend audio file. url null: says why there is no sound. */
export function SpokenAudio({ url, auto = false, label, unavailable }) {
  const ref = useRef(null)
  const [state, setState] = useState('idle')
  useEffect(() => {
    if (auto && url && ref.current) ref.current.play().catch(() => setState('blocked'))
  }, [auto, url])
  if (!url) return unavailable ? <p className="note spoken-none">{unavailable}</p> : null
  const toggle = () => {
    const a = ref.current
    if (!a) return
    if (state === 'playing') a.pause()
    else {
      a.currentTime = 0
      a.play().catch(() => setState('error'))
    }
  }
  return (
    <div className="spoken">
      <audio ref={ref} src={url} preload="auto" onPlay={() => setState('playing')} onPause={() => setState('idle')}
        onEnded={() => setState('idle')} onError={() => setState('error')} />
      <button type="button" className="btn" onClick={toggle} aria-pressed={state === 'playing'}>
        {state === 'playing' ? <Pause aria-hidden="true" /> : <Volume2 aria-hidden="true" />}
        {state === 'playing' ? 'Pause' : label}
      </button>
      {state === 'error' && <span className="note">The audio didn't play. The text is the answer.</span>}
      {state === 'blocked' && <span className="note">Tap to hear it.</span>}
    </div>
  )
}

export function PendingCard({ stage }) {
  return (
    <div className="tcard is-pending" role="status">
      <Loader2 className="spin" aria-hidden="true" />
      <span>{stage === 'listening' ? 'Listening…' : 'Understanding…'}</span>
    </div>
  )
}

export function StartCard({ W, t, onExpense, onProfit }) {
  return (
    <div className="reply">
      <div className="tcard">
        <Head tone="sky" label="Start here" />
        <p className="tcard-say" lang={t.lang}>{W.start}</p>
        <p className="tcard-en">
          Say or type what you spent, or ask how much the shop made today. Or tap:
        </p>
        <StartTaps t={t} onExpense={onExpense} onProfit={onProfit} />
      </div>
    </div>
  )
}

/** Clarify / not understood / failure. */
export function SayCard({ r, t, onExpense, onProfit }) {
  const head = {
    clarify: ['sky', r.title || 'Say it again'],
    not_understood: ['sky', r.title || "Didn't catch that"],
    failure: ['signal', r.title || "Couldn't do that"],
  }[r.tone] || ['sky', r.title || 'Naanayam']
  return (
    <div className="tcard">
      <Head tone={head[0]} label={head[1]} />
      {r.text && <p className="tcard-say" lang={t.lang}>{r.text}</p>}
      {r.tone === 'not_understood' && <p className="tcard-en">Not understood. Say an expense, or ask today's profit.</p>}
      {r.error && <ErrorLine error={r.error} />}
      {r.detail && <p className="tcard-en">{r.detail}</p>}
      {r.taps && onExpense && <StartTaps t={t} onExpense={onExpense} onProfit={onProfit} />}
    </div>
  )
}

function CategoryWord({ W, lang, category }) {
  return (
    <span className="catword">
      <span lang={lang}>{W.categories[category] || words(category)}</span>
      <small>{words(category)}</small>
    </span>
  )
}

function CategoryChips({ W, t, value, onPick, disabled }) {
  return (
    <div className="catchips" role="radiogroup" aria-label="Category">
      {EXPENSE_CATEGORIES.map((c) => (
        <button key={c} type="button" role="radio" aria-checked={value === c} disabled={disabled}
          className="catchip" onClick={() => onPick(c)}>
          <span lang={t.lang}>{W.categories[c]}</span>
          <small>{words(c)}</small>
        </button>
      ))}
    </div>
  )
}

/** Expense confirmation card (VOICE_AND_NOTICE 4.2). Saved only on the merchant's tap. */
export function ExpenseCard({ r, W, t, demoDate, act }) {
  const d = r.draft
  const notToday = d.date && demoDate && d.date !== demoDate
  const busy = r.status === 'saving'
  const statusText = {
    open: 'Check, then tap to save', edit: 'Change and save', saving: 'Saving…', saved: 'Saved',
    failed: 'Not saved yet', cancelled: 'Cancelled', closed: 'Closed',
  }[r.status]

  if (r.status === 'saved') return <SavedExpense r={r} W={W} t={t} act={act} />

  return (
    <div className={`tcard expense ${r.status === 'closed' || r.status === 'cancelled' ? 'is-done' : ''}`}>
      <Head tone="sun" label={`Expense · ${statusText}`}>
        <span className={`tcard-date ${notToday ? 'is-other' : ''}`}>{notToday ? 'Not today: ' : ''}{longDate(d.date)}</span>
      </Head>

      {r.note && <p className="tcard-say" lang={t.lang}>{r.note}</p>}

      {r.status !== 'edit' && (
        <>
          <div className="exp-main">
            {d.amount_display
              ? <Money amount={d.amount_display} className="tcard-amount" />
              : <span className="tcard-amount typed">{d.typed} <small>rupees, as typed</small></span>}
            <div className="exp-what">
              <CategoryWord W={W} lang={t.lang} category={d.category} />
              {d.description && <span className="exp-desc">{d.description}</span>}
            </div>
          </div>
          {r.confirmationText && !d.edited && (
            <div className="exp-confirm">
              <p className="tcard-say" lang={t.lang}>{r.confirmationText}</p>
              {r.status === 'open' && (
                r.speech?.url
                  ? <SpokenAudio url={r.speech.url} auto label="Hear it again" />
                  : (
                    <button type="button" className="btn small-btn" onClick={() => act('speak')} disabled={r.speech?.state === 'loading'}>
                      <Volume2 aria-hidden="true" /> {r.speech?.state === 'loading' ? 'Getting speech…' : 'Hear it'}
                    </button>
                  )
              )}
              {r.speech?.state === 'error' && <p className="note">{r.speech.message}</p>}
            </div>
          )}
          {d.amount_paise > LARGE_PAISE && r.status === 'open' && (
            <p className="exp-large" lang={t.lang}>{W.expense_large_warning}</p>
          )}
          {d.categoryUnclear && r.status === 'open' && (
            <div className="exp-cats">
              <p className="tcard-en">Category not clear, so it is set to other. Tap the right one:</p>
              <CategoryChips W={W} t={t} value={d.category} onPick={(c) => act('category', c)} />
            </div>
          )}
        </>
      )}

      {r.status === 'edit' && <ExpenseForm r={r} W={W} t={t} act={act} />}

      {r.status === 'failed' && <ErrorLine error={r.error} hint="Retry sends the same card again, so it can't be saved twice." />}

      {(r.status === 'open' || r.status === 'saving') && (
        <BigTaps label="Save this expense?" items={[
          { key: 'yes', text: W.yes, lang: t.lang, en: busy ? 'Saving…' : 'Save', tone: 'ink', onClick: () => act('save'), disabled: busy },
          { key: 'change', text: W.change, lang: t.lang, en: 'Change', onClick: () => act('edit'), disabled: busy },
          { key: 'cancel', text: W.cancel, lang: t.lang, en: 'Cancel', tone: 'muted', onClick: () => act('cancel'), disabled: busy },
        ]} />
      )}
      {r.status === 'failed' && (
        <div className="tcard-actions">
          <button type="button" className="btn ink" onClick={() => act('retry')}>Retry</button>
          <button type="button" className="btn" onClick={() => act('edit')}>Change</button>
          <button type="button" className="btn" onClick={() => act('cancel')}>Cancel</button>
        </div>
      )}
      {r.status === 'cancelled' && <p className="tcard-en">Cancelled. Nothing was saved.</p>}
      {r.status === 'closed' && (
        <p className="tcard-en">
          {r.error
            ? "Closed when another card opened. The last save didn't confirm, so check the ledger before adding it again."
            : 'Closed when another card opened. Nothing was saved from this card.'}
        </p>
      )}
    </div>
  )
}

function ExpenseForm({ r, W, t, act }) {
  const d = r.draft
  const f = r.form
  const busy = r.status === 'saving'
  return (
    <form className="exp-form" onSubmit={(e) => { e.preventDefault(); act('submit') }}>
      <label className="field">
        <span>Amount in rupees</span>
        <input inputMode="numeric" autoComplete="off" value={f.rupees} disabled={busy}
          placeholder={d.amount_display ? 'Leave empty to keep it' : 'For example 3100'}
          onChange={(e) => act('form', { rupees: e.target.value })} aria-describedby="exp-amount-hint" />
        <small id="exp-amount-hint" className="note">
          {d.amount_display ? <>Now: <Money amount={d.amount_display} />. The backend checks the amount again.</> : 'From 1 to 5,00,000. The backend checks it again.'}
        </small>
      </label>
      <div className="field">
        <span>Category</span>
        <CategoryChips W={W} t={t} value={f.category} onPick={(c) => act('form', { category: c })} disabled={busy} />
      </div>
      <label className="field">
        <span>What it was for (optional)</span>
        <input value={f.description} disabled={busy} onChange={(e) => act('form', { description: e.target.value })} />
      </label>
      {f.error && <p className="error-banner" role="alert"><TriangleAlert aria-hidden="true" /> {f.error}</p>}
      <div className="bigtaps n2">
        <button type="submit" className="bigtap ink" disabled={busy}>
          <span lang={t.lang}>{W.yes}</span><small>{busy ? 'Saving…' : 'Save'}</small>
        </button>
        <button type="button" className="bigtap muted" onClick={() => act('cancel')} disabled={busy}>
          <span lang={t.lang}>{W.cancel}</span><small>Cancel</small>
        </button>
      </div>
    </form>
  )
}

function SavedExpense({ r, W, t, act }) {
  const s = r.result
  return (
    <div className="tcard expense is-saved">
      <Head tone="sun" label={r.voidState === 'voided' ? 'Expense · Voided' : 'Expense · Saved'}>
        <Badge kind="ledger" />
      </Head>
      <p className="tcard-say" lang={t.lang}>
        <Money amount={s} sources={[s.ledger_entry_id]} /> {W.expense_saved}
      </p>
      {s.idempotent_replay && <p className="tcard-en">This card was already saved, so nothing new was written.</p>}
      <dl className="kv">
        <dt>Category</dt><dd><CategoryWord W={W} lang={t.lang} category={s.category} /></dd>
        <dt>Ledger entry</dt><dd><a className="mono" href={ledgerHref([s.ledger_entry_id])}>{s.ledger_entry_id}</a></dd>
        <dt>Expense</dt><dd className="mono">{s.expense_id} · {words(s.status)}</dd>
      </dl>
      {r.voidState === 'voided' ? (
        <>
          <p className="tcard-en">
            Voided. The ledger keeps the expense and adds <a className="mono" href={ledgerHref([r.voidResult.void_ledger_entry_id])}>{r.voidResult.void_ledger_entry_id}</a> to cancel it.
          </p>
          <div className="tcard-actions"><a className="btn" href="#/today">Open Today</a></div>
        </>
      ) : r.voidState === 'ask' || r.voidState === 'voiding' ? (
        <div className="void-ask">
          <p className="tcard-en">Void this expense? It stays in the ledger with a second entry that cancels it.</p>
          <div className="tcard-actions">
            <button type="button" className="btn ink" onClick={() => act('void-confirm')} disabled={r.voidState === 'voiding'}>
              {r.voidState === 'voiding' ? 'Voiding…' : 'Void it'}
            </button>
            <button type="button" className="btn" onClick={() => act('void-keep')} disabled={r.voidState === 'voiding'}>Keep it</button>
          </div>
        </div>
      ) : (
        <div className="tcard-actions">
          <a className="btn ink" href="#/today">Open Today</a>
          <button type="button" className="btn" onClick={() => act('void')}>Wrong? Void it</button>
        </div>
      )}
      {r.voidState === 'failed' && <ErrorLine error={r.voidError} hint="The expense is still recorded." />}
    </div>
  )
}

/** Daily profit, spoken from the fixed template (VOICE_AND_NOTICE 4.3, 6). */
export function ProfitCard({ r, t }) {
  if (r.status === 'loading') return <PendingCard stage="understanding" />
  const label = r.date ? `Profit · ${longDate(r.date)}` : 'Profit'
  if (r.status === 'error') {
    const e = r.error
    const hint = e.status === 500
      ? 'The number check failed, so Naanayam will not speak these numbers.'
      : e.status === 422 ? `No spoken answer for this yet in ${t.languageName}.` : 'Try again, or open Today.'
    const s = r.fallback
    const src = s?.sources || {}
    return (
      <div className="tcard profit">
        <Head tone="lime" label={label} />
        <ErrorLine error={e} hint={hint} />
        {s && (
          <>
            <p className="tcard-en">The ledger's numbers for today, shown without speech:</p>
            <dl className="facts">
              <div><dt>Business sales</dt><dd><Money amount={s.business_sales} sources={src.business_sales} /></dd></div>
              <div><dt>Expenses</dt><dd><Money amount={s.expenses} sources={src.expenses} /></dd></div>
              <div className="is-key"><dt>{s.profit?.label || 'Profit'}</dt><dd><Money amount={s.profit} sources={[...(src.business_sales || []), ...(src.expenses || [])]} /></dd></div>
              <div><dt>Family money, kept out</dt><dd><Money amount={s.family_transfers} sources={src.family_transfers} /></dd></div>
            </dl>
            {s.scope_note && <p className="scope"><CircleHelp aria-hidden="true" /> {s.scope_note}</p>}
          </>
        )}
        <div className="tcard-actions"><a className="btn" href="#/today">Open Today</a></div>
      </div>
    )
  }
  const a = r.data
  const f = a.facts || {}
  const slots = Object.keys(a.number_check?.slots || {})
  const loss = slots.includes('loss')
  const url = a.audio_id ? apiUrl(`/audio/${encodeURIComponent(a.audio_id)}`) : null
  const unavailable = a.audio_error
    ? `No speech this time (${a.audio_error}): the text is shown without speech.`
    : !a.audio_id ? 'No audio came back: the text is shown without speech.'
      : USING_FIXTURES ? 'Speech plays with the live backend (fixtures mode has no audio).' : null
  return (
    <div className="tcard profit">
      <Head tone="lime" label={label}>
        <Badge kind="ledger" />
      </Head>
      <p className="tcard-say" lang={a.language}>{a.text}</p>
      <SpokenAudio url={url} auto label="Play the answer" unavailable={unavailable} />
      <dl className="facts">
        <div><dt>Business sales</dt><dd><Money amount={f.business_sales} /></dd></div>
        <div><dt>Expenses</dt><dd><Money amount={f.expenses} /></dd></div>
        <div className="is-key"><dt>{loss ? 'Loss so far' : 'Profit'}</dt><dd><Money amount={f.profit} /></dd></div>
        <div><dt>Family money, kept out</dt><dd><Money amount={f.family_transfers} /></dd></div>
        {f.pending_count > 0 && <div><dt>Still to answer</dt><dd className="figure">{count(f.pending_count)} {f.pending_count === 1 ? 'payment' : 'payments'}</dd></div>}
      </dl>
      <p className={`numcheck ${a.number_check?.passed ? 'is-ok' : 'is-bad'}`}>
        {a.number_check?.passed ? <ShieldCheck aria-hidden="true" /> : <TriangleAlert aria-hidden="true" />}
        <span>
          {a.number_check?.passed ? 'Number check passed: ' : 'Number check failed: '}
          the spoken numbers are these figures, each in its own place ({slots.map(words).join(', ')}).
        </span>
      </p>
      {a.scope_note && <p className="scope"><CircleHelp aria-hidden="true" /> {a.scope_note}</p>}
      <div className="tcard-actions"><a className="btn" href="#/today">Open Today</a></div>
    </div>
  )
}

const CONFIRM_ERRORS = {
  REVERSED: 'This payment was reversed, so there is nothing to confirm.',
  QUESTION_MISMATCH: 'This answer did not match the open question, so nothing was saved.',
}

/** A payment question on Talk (VOICE_AND_NOTICE 4.4). Spoken answers go to the card on screen only. */
export function QuestionCard({ r, W, t, act }) {
  const q = r.q
  const live = r.status === 'open'
  const busy = r.status === 'saving'
  if (r.status === 'moved') {
    return (
      <div className="tcard tq is-done">
        <Head tone="signal" label="Payment question" />
        <p className="tcard-en"><b>{q.payer_name}</b> · <Money amount={q} /> · continued below.</p>
      </div>
    )
  }
  if (r.status === 'saved') return <AnsweredQuestion r={r} W={W} t={t} />
  const reason = r.error?.details?.reason
  return (
    <div className={`tcard tq ${r.status === 'closed' ? 'is-done' : ''}`}>
      <Head tone="signal" label={r.stage === 'remember' ? 'Remember this payer?' : 'Waiting for an answer'}>
        <span className="tcard-date">{clockTime(q.timestamp)} IST</span>
      </Head>
      <div className="q-who">
        <span className="q-avatar" aria-hidden="true">{q.payer_name?.[0]}</span>
        <div>
          <b>{q.payer_name}</b>
          <small>Suggested: {words(q.suggested_classification)}{typeof q.confidence === 'number' ? `, ${confidenceText(q.confidence)} sure` : ''}</small>
        </div>
        <Money amount={q} className="q-amt" />
      </div>
      {r.note && <p className="q-note" lang={t.lang}>{r.note}</p>}
      {r.stage === 'ask' ? (
        <>
          <p className="tcard-say" lang={t.lang}>{q.question_text}</p>
          {q.question_text_en && <p className="tcard-en">{q.question_text_en}</p>}
          {live && <SpokenAudio url={q.question_audio_id ? apiUrl(`/audio/${encodeURIComponent(q.question_audio_id)}`) : null} label="Play the question" />}
          {(live || busy) && (
            <BigTaps label="Shop sale or family money?" items={[
              { key: 'sale', text: t.sale, lang: t.lang, en: 'Shop sale', tone: 'lime', onClick: () => act('SALE'), disabled: !live },
              { key: 'family', text: t.family, lang: t.lang, en: 'Family money', tone: 'violet', onClick: () => act('FAMILY'), disabled: !live },
            ]} />
          )}
        </>
      ) : (
        <>
          <p className="tcard-say" lang={t.lang}>{W.remember_question(q.payer_name)}</p>
          <p className="tcard-en">Family money. From now on, is everything {q.payer_name} sends family money?</p>
          {(live || busy) && (
            <BigTaps label="Remember this payer as family?" items={[
              { key: 'always', text: t.rememberAlways, lang: t.lang, en: 'Yes, always', tone: 'violet', onClick: () => act('always'), disabled: !live },
              { key: 'once', text: t.rememberOnce, lang: t.lang, en: 'Only this time', onClick: () => act('once'), disabled: !live },
            ]} />
          )}
        </>
      )}
      {busy && <p className="tcard-en" role="status">Saving the answer…</p>}
      {r.status === 'failed' && (
        <>
          {reason === 'REVERSED' && <p className="tcard-say" lang={t.lang}>{W.reversed}</p>}
          <ErrorLine error={r.error} hint={CONFIRM_ERRORS[reason]} />
          {!CONFIRM_ERRORS[reason] && (
            <div className="tcard-actions"><button type="button" className="btn ink" onClick={() => act('retry')}>Retry</button></div>
          )}
        </>
      )}
      {live && (
        <div className="q-foot">
          <span className="note">Your next words answer this payment.</span>
          <button type="button" className="linkish" onClick={() => act('close')}>Not now</button>
        </div>
      )}
      {r.status === 'closed' && <p className="tcard-en">Closed. The payment is still waiting; answer it from the list any time.</p>}
    </div>
  )
}

function AnsweredQuestion({ r, W, t }) {
  const q = r.q
  const s = r.result
  const fam = s.confirmed_category === 'FAMILY'
  const remembered = fam && s.payer_memory?.family_payer_configured && r.answer?.remember
  const said = fam ? (remembered ? W.confirm_family_remembered(q.payer_name) : W.confirm_family) : W.confirm_sale
  return (
    <div className="tcard tq is-saved">
      <Head tone={fam ? 'violet' : 'lime'} label="Answer saved">
        <Badge kind="ledger" />
      </Head>
      <p className="tcard-say" lang={t.lang}>{said}</p>
      {s.idempotent_replay && <p className="tcard-en">It was already recorded this way, so nothing new was written.</p>}
      <dl className="kv">
        <dt>Payment</dt><dd><b>{q.payer_name}</b> · <Money amount={q} sources={[s.ledger_entry_id]} /> · <span className={`chip ${fam ? 'family' : 'sale'}`}>{fam ? 'family' : 'sale'}</span></dd>
        <dt>Ledger entry</dt><dd><a className="mono" href={ledgerHref([s.ledger_entry_id])}>{s.ledger_entry_id}</a> (a new entry; the original stays)</dd>
        <dt>Answered by</dt><dd>{r.answer?.channel === 'VOICE' ? 'Words' : 'Tap'}{r.answer?.utterance_text ? <> · <span lang={t.lang}>{r.answer.utterance_text}</span></> : ''}</dd>
        {remembered && (<><dt>Next time</dt><dd>{q.payer_name}'s payments go to family money without asking.</dd></>)}
        {s.moved_from && (<><dt>Moved</dt><dd>{q.payer_name} was remembered as {words(s.moved_from)} before.</dd></>)}
      </dl>
      <div className="tcard-actions"><a className="btn" href="#/today">Open Today</a></div>
    </div>
  )
}
