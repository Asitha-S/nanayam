// Hash routing: "#/ledger?ids=LE-1,LE-2" -> route "/ledger", params { ids: "LE-1,LE-2" }.
// Moving to another screen cross-fades (View Transitions API, where the browser has it and motion is allowed),
// and the new screen starts at its top inside the transition, so nothing jumps.
import { useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'

function parse() {
  const h = window.location.hash
  if (!h.startsWith('#/')) return { route: '/', params: {} }
  const [path, query = ''] = h.slice(1).split('?')
  return { route: path || '/', params: Object.fromEntries(new URLSearchParams(query)) }
}

function reducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export function useHashRoute() {
  const [state, setState] = useState(parse)
  const current = useRef(state.route)
  useEffect(() => {
    const on = () => {
      const next = parse()
      const newScreen = next.route !== current.current
      current.current = next.route
      if (!newScreen) return setState(next)
      const swap = () => {
        flushSync(() => setState(next))
        window.scrollTo(0, 0)
      }
      if (document.startViewTransition && !reducedMotion()) document.startViewTransition(swap)
      else swap()
      return undefined
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return state
}

/** Navigate inside the app. */
export function go(path) {
  window.location.hash = path.startsWith('#') ? path : `#${path}`
}
