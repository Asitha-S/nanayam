// API access. The contract (contract/API_CONTRACT.md) is the only source of names and shapes.
// VITE_API_BASE=fixtures serves contract/fixtures instead of the backend.
import { useCallback, useEffect, useState } from 'react'

// VITE_API_BASE: a full URL, "fixtures", or unset. Unset means "the API on this same host, port 8000": the laptop
// reaches localhost, and a phone that opened http://<laptop-LAN-IP>:5173 reaches http://<laptop-LAN-IP>:8000.
const RAW_BASE = import.meta.env.VITE_API_BASE
const API_PORT = import.meta.env.VITE_API_PORT || '8000'
function deriveBase() {
  if (RAW_BASE === 'fixtures') return 'fixtures'
  if (RAW_BASE && /^https?:\/\//.test(RAW_BASE)) return RAW_BASE.replace(/\/$/, '')
  const host = window.location.hostname || 'localhost'
  const path = RAW_BASE && RAW_BASE.startsWith('/') ? RAW_BASE.replace(/\/$/, '') : '/api'
  return `${window.location.protocol}//${host}:${API_PORT}${path}`
}
export const API_BASE = deriveBase()
export const USING_FIXTURES = API_BASE === 'fixtures'

const fixtureFiles = import.meta.glob('../../contract/fixtures/*.json', { import: 'default' })

// GET path (with query) -> fixture name, fixtures mode only. Paths not listed fail with NO_FIXTURE.
const GET_FIXTURES = {
  '/health': 'health',
  '/merchants': 'merchants',
  '/merchants/M001': 'merchant_M001',
  '/merchants/M001/summary?include_sources=true': 'summary_M001_after_confirm',
  '/demo/script?merchant_id=M001': 'demo_script_M001',
  '/evaluation': 'evaluation',
  '/merchants/M001/ledger/verify': 'ledger_verify_valid',
  '/merchants/M001/passport': 'passport_M001',
  '/merchants/M001/learning': 'learning_M001',
  '/merchants/M001/tax-summary': 'tax_summary_M001',
  '/merchants/M001/questions?status=OPEN&date=2026-11-15': 'questions_M001_open_2026-11-15',
  '/merchants/M001/questions?status=OPEN': 'questions_M001_open_all',
  '/merchants/M001/payments': 'payments_list_M001_2026-11-15',
  '/merchants/M001/expenses': 'expenses_list_M001_2026-11-15',
  '/merchants/M001/ledger': 'ledger_M001_2026-11-15',
}
// [method, path regex, fixture name] for writes in fixtures mode
const WRITE_FIXTURES = [
  ['GET', /^\/ledger\/LE-/, 'ledger_entry_detail'],
  ['GET', /^\/payments\/TXN-/, 'payment_get_015'],
  ['POST', /^\/demo\/next-payment$/, 'demo_next_payment_015'],
  ['POST', /^\/demo\/reset$/, 'demo_reset'],
  ['POST', /^\/payments\/[^/]+\/confirm$/, 'confirm_015'],
  ['POST', /^\/expenses$/, 'expenses_post'],
  ['POST', /^\/expenses\/[^/]+\/void$/, 'expense_void'],
  ['POST', /^\/voice\/answer$/, 'voice_answer_profit'],
  ['POST', /^\/voice\/interpret$/, 'voice_interpret_expense'],
  ['POST', /^\/voice\/transcribe$/, 'voice_transcribe_recorded'],
  ['POST', /^\/voice\/speak$/, 'voice_speak'],
  ['POST', /^\/classify\/preview$/, 'classify_preview_remembered'],
  ['POST', /^\/notices\/analyse$/, 'notice_analyse'],
  ['GET', /^\/merchants\/M001\/notices\/[^/]+\/evidence$/, 'notice_evidence'],
  // no fixture file: the contract's documented response, inline
  ['POST', /^\/demo\/tamper$/, { tampered: true }],
]

// Fixtures mode has no Udhari (flag UDHARI off; /health there has no `features`): answer like the backend with the
// flag off, 404 NOT_FOUND (contract section 13).
const FLAG_OFF_IN_FIXTURES = [/^\/merchants\/[^/]+\/tabs$/, /^\/tabs\/[^/]+\/(add|settle)$/]

export class ApiError extends Error {
  constructor(status, error) {
    super(error?.message || `Request failed (${status})`)
    this.status = status
    this.code = error?.code
    this.details = error?.details
  }
}

// POSTs that change nothing on screen (previews, speech, interpretation): no refetch after them.
const READ_ONLY_POSTS = [/^\/classify\/preview$/, /^\/voice\/(interpret|transcribe|speak|answer)$/]
const changesData = (method, path) => method !== 'GET' && !READ_ONLY_POSTS.some((re) => re.test(path.split('?')[0]))

/** Fired after every successful write, so screens refetch what they show. */
export const CHANGED = 'naanayam:changed'
export function notifyChanged() {
  window.dispatchEvent(new Event(CHANGED))
}

async function fromFixture(method, path) {
  if (FLAG_OFF_IN_FIXTURES.some((re) => re.test(path.split('?')[0]))) {
    throw new ApiError(404, { code: 'NOT_FOUND', message: 'Not found (Udhari is off in fixtures mode)' })
  }
  const name = (method === 'GET' && (GET_FIXTURES[path] || GET_FIXTURES[path.split('?')[0]]))
    || WRITE_FIXTURES.find(([m, re]) => m === method && re.test(path.split('?')[0]))?.[2]
  if (name && typeof name === 'object') return structuredClone(name)
  const load = name && fixtureFiles[`../../contract/fixtures/${name}.json`]
  if (!load) throw new ApiError(404, { code: 'NO_FIXTURE', message: `No fixture for ${method} ${path}` })
  return load()
}

/**
 * One request. body: plain object (sent as JSON) or FormData (multipart). Throws ApiError with the contract's
 * { error: { code, message, details } } on non-2xx.
 */
export async function request(method, path, { body, signal, headers } = {}) {
  if (USING_FIXTURES) {
    const data = await fromFixture(method, path)
    if (changesData(method, path)) notifyChanged()
    return data
  }
  const init = { method, signal, headers: { ...(headers || {}) } }
  if (body instanceof FormData) init.body = body
  else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers['Content-Type'] = 'application/json'
  }
  let res
  try {
    res = await fetch(API_BASE + path, init)
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(0, { code: 'UNREACHABLE', message: `Backend not reachable at ${API_BASE}` })
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.error)
  if (changesData(method, path)) notifyChanged()
  return data
}

export const get = (path, opts) => request('GET', path, opts)
export const post = (path, body, opts) => request('POST', path, { ...opts, body })
export const put = (path, body, opts) => request('PUT', path, { ...opts, body })

/** Absolute URL for things the browser loads itself (exports, audio); null in fixtures mode. */
export function apiUrl(path) {
  return USING_FIXTURES ? null : API_BASE + path
}

/**
 * { data, error, loading, reload } for a GET. Refetches when path changes, after any write (CHANGED),
 * and every pollMs when given. path = null skips the request.
 */
export function useApi(path, { pollMs } = {}) {
  // `path` is kept with the data so a screen never shows one request's data under another (e.g. after a merchant switch)
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path), path })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    window.addEventListener(CHANGED, reload)
    const id = pollMs ? setInterval(reload, pollMs) : null
    return () => {
      window.removeEventListener(CHANGED, reload)
      if (id) clearInterval(id)
    }
  }, [reload, pollMs])

  useEffect(() => {
    if (!path) {
      setState({ data: null, error: null, loading: false, path })
      return undefined
    }
    const ctrl = new AbortController()
    // same path (refetch): keep showing the data while it reloads; new path: start empty
    setState((s) => (s.path === path ? { ...s, loading: s.data === null, error: null }
      : { data: null, error: null, loading: true, path }))
    get(path, { signal: ctrl.signal })
      .then((data) => setState({ data, error: null, loading: false, path }))
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setState((s) => ({ data: s.path === path ? s.data : null, error, loading: false, path }))
        }
      })
    return () => ctrl.abort()
  }, [path, tick])

  // never hand out data that belongs to a different path, even for the render before the effect runs
  const fresh = state.path === path
  return { data: fresh ? state.data : null, error: fresh ? state.error : null, loading: fresh ? state.loading : Boolean(path), reload }
}
