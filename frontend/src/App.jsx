// Routes. "#/" is the standalone landing page; "#/home" and every other route is an app screen inside AppShell.
import { MerchantProvider, useMerchant } from './app/merchant'
import { useHashRoute } from './app/route'
import { TourProvider } from './tour/Tour'
import AppShell from './components/AppShell'
import DemoPanel from './pages/DemoPanel'
import Home from './pages/Home'
import Landing from './pages/Landing'
import Learning from './pages/Learning'
import Ledger from './pages/Ledger'
import Notice from './pages/Notice'
import Passport from './pages/Passport'
import Pay from './pages/Pay'
import Questions from './pages/Questions'
import Soundbox from './pages/Soundbox'
import Talk from './pages/Talk'
import Today from './pages/Today'
import Udhari from './pages/Udhari'

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
// Screens behind a backend feature flag: with the flag off (or unknown) the route does not exist.
const FLAGGED = {
  '/udhari': ['udhari', Udhari, 'udhari'],
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

/** The app screen for a route, inside the chrome. A flagged route waits for /health before saying "no screen". */
function Screen({ route, params }) {
  const merchant = useMerchant()
  const flagged = FLAGGED[route]
  const [active, Page] = SCREENS[route] || (flagged && merchant[flagged[2]] ? flagged : [null, null])
  return (
    <AppShell active={active}>
      {Page ? <Page params={params} />
        : flagged && !merchant.health ? <p className="load-state">Loading…</p>
          : <NotFound route={route} />}
    </AppShell>
  )
}

export default function App() {
  const { route, params } = useHashRoute()
  // the customer's phone page: standalone, no app chrome, no judge tour
  if (route === '/pay') {
    return (
      <MerchantProvider>
        <Pay params={params} />
      </MerchantProvider>
    )
  }
  return (
    <MerchantProvider>
      <TourProvider>
        {route === '/' ? <Landing /> : <Screen route={route} params={params} />}
      </TourProvider>
    </MerchantProvider>
  )
}
