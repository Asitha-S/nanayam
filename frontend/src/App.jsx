// Routes. "#/" is the standalone landing page; "#/home" and every other route is an app screen inside AppShell.
import { useEffect } from 'react'
import { MerchantProvider } from './app/merchant'
import { useHashRoute } from './app/route'
import AppShell from './components/AppShell'
import DemoPanel from './pages/DemoPanel'
import Home from './pages/Home'
import Landing from './pages/Landing'
import Learning from './pages/Learning'
import Ledger from './pages/Ledger'
import Notice from './pages/Notice'
import Passport from './pages/Passport'
import Questions from './pages/Questions'
import Soundbox from './pages/Soundbox'
import Talk from './pages/Talk'
import Today from './pages/Today'

const SCREENS = {
  '/home': ['home', Home],
  '/soundbox': ['soundbox', Soundbox],
  '/questions': ['questions', Questions],
  '/talk': ['talk', Talk],
  '/today': ['today', Today],
  '/ledger': ['ledger', Ledger],
  '/learning': ['learning', Learning],
  '/notice': ['notice', Notice],
  '/passport': ['passport', Passport],
  '/demo': ['demo', DemoPanel], // hidden demo control panel, not in the rail
}

function NotFound({ route }) {
  return (
    <section className="empty">
      <span className="label">{route}</span>
      <h1>No screen here.</h1>
      <a className="btn" href="#/home">Back to home</a>
    </section>
  )
}

export default function App() {
  const { route, params } = useHashRoute()
  useEffect(() => { window.scrollTo(0, 0) }, [route])
  if (route === '/') return <Landing />
  const [active, Screen] = SCREENS[route] || [null, null]
  return (
    <MerchantProvider>
      <AppShell active={active}>
        {Screen ? <Screen params={params} /> : <NotFound route={route} />}
      </AppShell>
    </MerchantProvider>
  )
}
