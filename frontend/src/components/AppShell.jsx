// Chrome for the app screens: live payment ticker, top bar with the merchant switch, numbered rail, tamper banner.
import {
  BookOpenCheck, FileWarning, Gauge, HandCoins, IdCard, LayoutGrid, ListChecks, MessageCircleQuestion, Mic, Radio, ShieldAlert,
} from 'lucide-react'
import { useApi } from '../api'
import { useMerchant } from '../app/merchant'
import { Rail, TopBar } from './Shell'
import { clockTime } from './ui'

// Order is the demo order. `p1` screens first, then the judge-facing ones.
export const APP_ROUTES = [
  { id: 'home', n: '01', label: 'Home', Icon: LayoutGrid, href: '#/home' },
  { id: 'soundbox', n: '02', label: 'Soundbox', Icon: Radio, href: '#/soundbox' },
  { id: 'questions', n: '03', label: 'Questions', Icon: MessageCircleQuestion, href: '#/questions' },
  { id: 'talk', n: '04', label: 'Talk', Icon: Mic, href: '#/talk' },
  { id: 'today', n: '05', label: 'Today', Icon: ListChecks, href: '#/today' },
  { id: 'ledger', n: '06', label: 'Ledger', Icon: BookOpenCheck, href: '#/ledger' },
  { id: 'learning', n: '07', label: 'Learning', Icon: Gauge, href: '#/learning' },
  { id: 'notice', n: '08', label: 'Notice', Icon: FileWarning, href: '#/notice' },
  { id: 'passport', n: '09', label: 'Passport', Icon: IdCard, href: '#/passport' },
]
// Shown only when the backend's UDHARI flag is on (GET /health features.udhari).
export const UDHARI_ROUTE = { id: 'udhari', n: '10', label: 'Udhari', Icon: HandCoins, href: '#/udhari' }

const CLASS_TEXT = { SALE: 'sale', FAMILY: 'family', PENDING: 'waiting' }

/** Live strip of today's payments for the selected merchant (polls). */
function LiveTicker() {
  const { merchantId } = useMerchant()
  const payments = useApi(`/merchants/${merchantId}/payments?limit=40`, { pollMs: 5000 })
  const items = payments.data?.items || []
  const row = items.map((p) => (
    <span className={`tick tick-${(p.current_classification || '').toLowerCase()}`} key={p.transaction_id}>
      <b>{clockTime(p.timestamp)}</b>
      <span>{p.payer_name.toUpperCase()}</span>
      <span className="tick-amt">{p.amount_display}</span>
      <span className="tick-act">{CLASS_TEXT[p.current_classification] || p.current_classification}</span>
      <i aria-hidden="true" />
    </span>
  ))
  return (
    <div className="ticker" aria-hidden="true">
      <span className="ticker-tag">Today's payments</span>
      <div className="ticker-track">
        {items.length ? (
          <div className={`ticker-run ${items.length < 6 ? 'is-still' : ''}`}>{row}{items.length >= 6 && row}</div>
        ) : (
          <span className="tick tick-empty">No payments yet today. Send one from the Soundbox.</span>
        )}
      </div>
    </div>
  )
}

function MerchantSwitch() {
  const { merchantId, setMerchantId, merchants } = useMerchant()
  const shown = merchants.filter((m) => m.merchant_id === 'M001' || m.merchant_id === 'M002')
  if (!shown.length) return null
  return (
    <div className="merchant-switch" role="group" aria-label="Merchant">
      {shown.map((m) => (
        <button key={m.merchant_id} type="button" aria-pressed={merchantId === m.merchant_id}
          onClick={() => setMerchantId(m.merchant_id)}>
          <b>{m.owner_name}</b>
          <small>{m.preferred_language === 'te' ? 'Telugu' : 'Tamil'}</small>
        </button>
      ))}
    </div>
  )
}

/** Wrap an app screen. active: route id from APP_ROUTES. */
export default function AppShell({ active, children }) {
  const { merchantId, health, udhari } = useMerchant()
  const verify = useApi(`/merchants/${merchantId}/ledger/verify`)
  const routes = udhari ? [...APP_ROUTES, UDHARI_ROUTE] : APP_ROUTES
  return (
    <div className="app">
      <LiveTicker />
      <TopBar health={health} verify={verify.data}
        action={<a className="btn primary" href="#/soundbox"><Radio aria-hidden="true" /> Soundbox</a>}>
        <MerchantSwitch />
      </TopBar>
      <Rail items={routes} active={active} />
      <main className="app-main">
        {health?.tampered && (
          <p className="tamper-banner" role="alert">
            <ShieldAlert aria-hidden="true" />
            <span><b>Ledger tampered (demo).</b> An entry was edited directly in the database. Reset the demo to undo it.</span>
          </p>
        )}
        {children}
      </main>
    </div>
  )
}
