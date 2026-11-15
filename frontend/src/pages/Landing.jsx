// Landing page (#/): the front door. One action: enter the app (#/home).
// Payment chips are Murugan's real recent payments (today, else the last day with payments); nothing is typed or computed.
import { ArrowRight } from 'lucide-react'
import { useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { clockTime } from '../components/ui'
import { Mark } from '../components/Shell'
import '../styles/front.css'

const HOME = '#/home'
const ACTION = { SALE: 'sorted as a sale', FAMILY: 'family money', PENDING: 'asked in Tamil' }
const SLOTS = ['p1', 'p2', 'p3', 'p4', 'p5']

/** Five chips: the newest payment that was asked about (if any), then sales spread across the day. */
function pick(items) {
  const sorted = [...items].sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
  const asked = [...sorted].reverse().find((p) => p.current_classification !== 'SALE')
  const sales = sorted.filter((p) => p !== asked)
  const step = Math.max(1, Math.floor(sales.length / 4))
  const chosen = [0, 1, 2, 3].map((i) => sales[i * step]).filter(Boolean)
  return asked ? [...chosen.slice(0, 3), asked, ...chosen.slice(3)] : chosen
}

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
      {items && pick(items).map((it, i) => {
        const pos = SLOTS[i]
        const ask = it.current_classification === 'PENDING'
        return (
          <span key={it.transaction_id} className={`front-chip ${pos} ${ask ? 'is-ask' : ''}`}>
            <b>{clockTime(it.timestamp)}</b> {it.payer_name}
            <strong>{it.amount_display}</strong>
            <em>{ACTION[it.current_classification] || it.current_classification}</em>
          </span>
        )
      })}
    </div>
  )
}

export default function Landing() {
  const { demoDate } = useMerchant()
  const yesterday = demoDate && new Date(new Date(`${demoDate}T12:00:00Z`).getTime() - 864e5).toISOString().slice(0, 10)
  const today = useApi(demoDate ? `/merchants/M001/payments?start_date=${demoDate}&end_date=${demoDate}&limit=500` : null)
  const before = useApi(yesterday && today.data && today.data.items.length < 5
    ? `/merchants/M001/payments?start_date=${yesterday}&end_date=${yesterday}&limit=500` : null)
  const items = today.data && today.data.items.length >= 5 ? today.data.items : before.data?.items
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
        <Coin items={items} />
      </main>

      <footer className="front-foot">
        <span>Paytm Build for India AI Hackathon, Chennai 2026 · Track 1 · Team Aether</span>
        <span>Synthetic demo data. No real Paytm, bank or GST portal connection.</span>
      </footer>
    </div>
  )
}
