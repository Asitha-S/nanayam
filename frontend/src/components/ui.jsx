// Shared atoms. Money is always the backend's display string; the frontend never computes it.
import { BadgeCheck, FileText, Mic, PenLine, ShieldCheck } from 'lucide-react'

/** Link to the ledger entries an amount came from. */
export function ledgerHref(ids) {
  return ids && ids.length ? `#/ledger?ids=${encodeURIComponent(ids.join(','))}` : '#/ledger'
}

/**
 * An amount from the backend. `amount` is { amount_display } or a display string; `sources` are ledger entry ids.
 * Always rendered as a link to its entries.
 */
export function Money({ amount, sources, className = '' }) {
  const shown = typeof amount === 'string' ? amount : amount?.amount_display
  if (!shown) return <span className={`money ${className}`}>—</span>
  return (
    <a className={`money ${className}`} href={ledgerHref(sources)} title="Open the ledger entries for this amount">
      {shown}
    </a>
  )
}

const BADGES = {
  clip: { text: 'Recorded demo clip', Icon: Mic },
  instruction: { text: 'Your instruction', Icon: PenLine },
  notice: { text: 'From notice', Icon: FileText },
  ledger: { text: 'From your ledger', Icon: BadgeCheck },
  synthetic: { text: 'Synthetic data', Icon: ShieldCheck },
}

/** Small honest source badge. */
export function Badge({ kind, children }) {
  const b = BADGES[kind]
  return (
    <span className={`badge badge-${kind}`}>
      {b && <b.Icon aria-hidden="true" />}
      {children || b?.text}
    </span>
  )
}

/**
 * Confidence as shown to people (contract section 0): ≥ 0.995 reads ">99%", never "100%";
 * null means the merchant's own instruction decided it, not the model.
 */
export function confidenceText(p) {
  if (p === null) return 'Your instruction'
  if (typeof p !== 'number') return '—'
  if (p >= 0.995) return '>99%'
  return `${Math.round(p * 100)}%`
}

/** Counts (not money) in Indian grouping. */
export function count(n) {
  return typeof n === 'number' ? n.toLocaleString('en-IN') : '—'
}

/** "2026-11-15" -> "15 Nov 2026" */
export function longDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]
  return `${d} ${month} ${y}`
}

/** "2026-10" -> "Oct 2026" */
export function monthLabel(ym) {
  if (!ym) return ''
  const [y, m] = ym.split('-').map(Number)
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} ${y}`
}

/** "2026-11-15T19:43:05+05:30" -> "19:43" (IST as sent by the backend) */
export function clockTime(iso) {
  return iso ? iso.slice(11, 16) : ''
}

export function LoadState({ state, what }) {
  if (state.loading) return <p className="load-state">Loading {what}…</p>
  if (state.error) {
    return (
      <p className="load-state is-error">
        Couldn't load {what}: {state.error.message}.
      </p>
    )
  }
  return null
}
