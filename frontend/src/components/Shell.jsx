// Page chrome shared by the landing page and the app screens: ticker, top bar, numbered rail.
import { ArrowUpRight, Play } from 'lucide-react'
import { USING_FIXTURES } from '../api'
import { longDate } from './ui'

export function Mark({ size = 44 }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 44 44" aria-hidden="true">
      <circle cx="22" cy="22" r="20.5" fill="var(--lime)" stroke="var(--ink)" strokeWidth="2.5" />
      <circle cx="22" cy="22" r="13" fill="none" stroke="var(--ink)" strokeWidth="2.5" strokeDasharray="2.6 3.2" />
      <circle cx="22" cy="22" r="5.5" fill="var(--ink)" />
    </svg>
  )
}

/**
 * Top bar. `children` sits between the brand and the status (e.g. the merchant switch);
 * `action` is the pill on the right (defaults to the live-demo link).
 */
export function TopBar({ health, verify, demoHref, action, children }) {
  return (
    <header className="topbar">
      <a className="brand" href="#/home" aria-label="Naanayam home">
        <Mark />
        <span className="brand-name">Naanayam</span>
        <span className="brand-ta" lang="ta">நாணயம்</span>
        <span className="brand-sub label">Merchant ledger<br />for small shops</span>
      </a>
      {children}
      <div className="status">
        <div>
          <span className="label">Demo day</span>
          <strong className="figure">{health ? longDate(health.demo_date) : '…'}</strong>
        </div>
        <div>
          <span className="label">Ledger</span>
          <strong className={`figure ${verify?.status === 'VALID' ? 'is-valid' : verify ? 'is-bad' : ''}`}>
            {verify ? verify.status : '…'}
          </strong>
        </div>
        <div>
          <span className="label">Data</span>
          <strong className="figure">{USING_FIXTURES ? 'Fixtures' : 'Live backend'}</strong>
        </div>
      </div>
      {action ?? (
        <a className="btn primary" href={demoHref}>
          Open the live demo <ArrowUpRight aria-hidden="true" />
        </a>
      )}
    </header>
  )
}

/**
 * Numbered rail. items: [{ id, n, label, Icon, href? }]. With href the item is a route link;
 * without, it scrolls to the section with that id. active: id
 */
export function Rail({ items, active, demoHref, demoLabel = 'Live demo' }) {
  return (
    <nav className="rail" aria-label="Sections">
      <ol>
        {items.map(({ id, n, label, Icon, href }) => (
          <li key={id}>
            <a href={href || `#${id}`} className={active === id ? 'is-active' : ''} aria-current={active === id ? 'page' : undefined}
              onClick={href ? undefined : (e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }}>
              <span className="rail-n">{n}</span>
              <Icon aria-hidden="true" />
              <span className="rail-label">{label}</span>
            </a>
          </li>
        ))}
      </ol>
      {demoHref && (
        <a className="rail-demo" href={demoHref}>
          <Play aria-hidden="true" />
          <span>{demoLabel}</span>
        </a>
      )}
    </nav>
  )
}
