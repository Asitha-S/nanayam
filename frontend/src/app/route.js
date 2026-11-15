// Hash routing: "#/ledger?ids=LE-1,LE-2" -> route "/ledger", params { ids: "LE-1,LE-2" }.
import { useEffect, useState } from 'react'

function parse() {
  const h = window.location.hash
  if (!h.startsWith('#/')) return { route: '/', params: {} }
  const [path, query = ''] = h.slice(1).split('?')
  return { route: path || '/', params: Object.fromEntries(new URLSearchParams(query)) }
}

export function useHashRoute() {
  const [state, setState] = useState(parse)
  useEffect(() => {
    const on = () => setState(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return state
}

/** Navigate inside the app. */
export function go(path) {
  window.location.hash = path.startsWith('#') ? path : `#${path}`
}
