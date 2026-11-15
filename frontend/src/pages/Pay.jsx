// #/pay?m=M001 · The customer's phone: pay the shop (simulated). Standalone: no app chrome, no login, no tour.
// GET /demo/pay-options for the shop's name; the form itself is components/PayForm.jsx (variant 'phone').
import '../styles/pay.css'
import { Smartphone } from 'lucide-react'
import { useApi } from '../api'
import PayForm from '../components/PayForm'

export default function Pay({ params }) {
  const merchantId = (params?.m || 'M001').trim() || 'M001'
  const opts = useApi(`/demo/pay-options?merchant_id=${encodeURIComponent(merchantId)}`)
  const shop = opts.data?.merchant_id === merchantId ? opts.data.display_name : null

  return (
    <main className="pay-page">
      <header className="pay-top">
        <span className="pay-brand">Naanayam</span>
        <span className="pay-tag"><Smartphone aria-hidden="true" /> Simulated UPI</span>
      </header>
      <section className="pay-card" aria-labelledby="pay-h">
        <h1 id="pay-h" className="pay-h">
          <span>You are paying</span>
          <b>{shop || (opts.error ? merchantId : '…')}</b>
        </h1>
        <PayForm merchantId={merchantId} variant="phone" />
      </section>
      <p className="pay-foot">A practice payment for the Naanayam demo. Nothing is charged and no bank is involved.</p>
    </main>
  )
}
