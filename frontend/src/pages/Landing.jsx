// Landing page (#/): the front door. One action: enter the app (#/home).
// Payment chips come from GET /demo/script (synthetic demo day); nothing is typed or computed here.
import { ArrowRight } from 'lucide-react'
import { useApi } from '../api'
import { Mark } from '../components/Shell'
import '../styles/front.css'

const HOME = '#/home'
const ACTION = { AUTO_CLASSIFY: 'sorted as a sale', ASK_MERCHANT: 'asked in Tamil' }
// which scripted payments float around the coin, and where (index into the script, position class)
const PICKS = [[0, 'p1'], [11, 'p2'], [7, 'p3'], [14, 'p4'], [4, 'p5']]

function Coin({ items }) {
  return (
    <div className="front-coin" aria-hidden="true">
      <svg viewBox="0 0 520 520" className="front-coin-art">
        <circle cx="260" cy="260" r="250" fill="var(--lime)" stroke="var(--ink)" strokeWidth="4" />
        <circle cx="260" cy="260" r="196" fill="none" stroke="var(--ink)" strokeWidth="3" strokeDasharray="5 9" className="spin" />
        <circle cx="260" cy="260" r="136" fill="var(--sky)" stroke="var(--ink)" strokeWidth="3" />
        <circle cx="260" cy="260" r="78" fill="var(--ink)" />
        <text x="260" y="262" textAnchor="middle" dominantBaseline="middle" className="front-coin-ta">நா</text>
      </svg>
      {items && PICKS.map(([i, pos]) => {
        const it = items[i]
        if (!it) return null
        const ask = it.expected_action === 'ASK_MERCHANT'
        return (
          <span key={it.transaction_id} className={`front-chip ${pos} ${ask ? 'is-ask' : ''}`}>
            <b>{it.time}</b> {it.payer_name}
            <strong>{it.amount_display}</strong>
            <em>{ACTION[it.expected_action] || it.expected_action}</em>
          </span>
        )
      })}
    </div>
  )
}

export default function Landing() {
  const script = useApi('/demo/script?merchant_id=M001')
  return (
    <div className="front">
      <header className="front-head">
        <span className="brand">
          <Mark />
          <span className="brand-name">Naanayam</span>
          <span className="brand-ta" lang="ta">நாணயம்</span>
        </span>
        <a className="front-skip" href={HOME}>Open the app <ArrowRight aria-hidden="true" /></a>
      </header>

      <main className="front-main">
        <div className="front-copy">
          <h1>Every rupee,<br />proven.</h1>
          <p className="front-lede">
            Naanayam turns a small shop's UPI payments into a ledger that knows sales from family money, asks in Tamil
            when it isn't sure, and proves what the shop really earned.
          </p>
          <a className="btn ink front-cta" href={HOME}>Enter Naanayam <ArrowRight aria-hidden="true" /></a>
          <ol className="front-points">
            <li><b>Sales apart from family money</b><span>Every UPI credit is sorted; confident calls stay silent.</span></li>
            <li><b>One question, in Tamil</b><span>When it isn't sure, it asks with two big answers.</span></li>
            <li><b>Three proofs, one ledger</b><span>For the merchant, the taxman and the lender.</span></li>
          </ol>
        </div>
        <Coin items={script.data?.items} />
      </main>

      <footer className="front-foot">
        <span>Paytm Build for India AI Hackathon, Chennai 2026 · Track 1 · Team Aether</span>
        <span>Synthetic demo data. No real Paytm, bank or GST portal connection.</span>
      </footer>
    </div>
  )
}
