// UI sweep: `npm run ui-check` (from frontend/).
//
// Starts its own backend (port 8320, throwaway database in a temp folder) and its own build of the frontend
// (vite preview, port 4320), never the dev servers on 8000 / 5173. Opens every screen in the installed Chrome at
// 1920x1080 and 1366x768 (and #/pay at 390x844), in two states: "empty" (right after POST /demo/reset) and "full"
// (the judge tour's end state, made through the API). For each page it collects console and page errors, failed
// requests, horizontal page overflow, clipped text, overlapping controls, controls stuck outside the viewport,
// broken images, Tamil/Telugu font rendering and axe violations, saves a full-page screenshot to
// shots/<width>/<route>-<state>.png and writes shots/report.json. Never makes sound: Chrome runs with --mute-audio
// and speechSynthesis.speak is stubbed on every page. Everything it starts is stopped, even when it fails.
//
// Options: --only=soundbox,ledger-detail (route names)  --state=empty|full  --size=1920,1366,390
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const REPO = path.resolve(FRONTEND, '..')
const BACKEND_DIR = path.join(REPO, 'backend')
const PYTHON = process.platform === 'win32'
  ? path.join(REPO, '.venv', 'Scripts', 'python.exe')
  : path.join(REPO, '.venv', 'bin', 'python')
const API_PORT = 8320
const WEB_PORT = 4320
const API = `http://127.0.0.1:${API_PORT}/api`
const WEB = `http://127.0.0.1:${WEB_PORT}/`
const SHOTS = path.join(FRONTEND, 'shots')
const DEMO_DAY = JSON.parse(fs.readFileSync(path.join(REPO, 'data', 'demo', 'M001_demo_day.json'), 'utf8'))
const NOTICE_PNG = path.join(REPO, 'assets', 'notice', 'sample_notice.png')

// What the full state must show (GET /merchants/M001/summary, GET /merchants/M001/tabs).
const EXPECT_SUMMARY = { business_sales: '₹4,820', expenses: '₹3,100', family_transfers: '₹2,000', profit: '₹1,720', pending: '₹0' }
const EXPECT_TABS = { total_due_display: '₹4,810', open_count: 4 }

const SIZES = {
  1920: { width: 1920, height: 1080 },
  1366: { width: 1366, height: 768 },
  390: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
}

// The customer /pay page is also checked on a phone. `full` overrides the hash in the full state. `merchant` picks the
// merchant switch (M002 = Venkatesh, Telugu). `keepScroll`: the screen scrolls itself (Talk pins the newest card), so
// the checks run where it left the page and a viewport screenshot is saved too (<name>-<state>-viewport.png).
const ROUTES = [
  { name: 'landing', hash: '#/' },
  { name: 'home', hash: '#/home' },
  { name: 'soundbox', hash: '#/soundbox' },
  { name: 'questions', hash: '#/questions' },
  { name: 'questions-te', hash: '#/questions', merchant: 'M002' },
  { name: 'talk', hash: '#/talk' },
  // the judge tour's two Talk steps: the expense card (typed, never confirmed: nothing is saved) and the profit answer
  { name: 'talk-expense', hash: '#/talk', action: typedExpense, keepScroll: true },
  { name: 'talk-profit', hash: '#/talk?ask=profit', action: profitAnswer, keepScroll: true },
  { name: 'talk-te', hash: '#/talk', merchant: 'M002' },
  { name: 'today', hash: '#/today' },
  { name: 'ledger', hash: '#/ledger' },
  { name: 'ledger-detail', hash: '#/ledger', action: openLedgerEntry },
  { name: 'learning', hash: '#/learning' },
  { name: 'notice', hash: '#/notice', full: (setup) => `#/notice?id=${encodeURIComponent(setup.notice.notice_id)}` },
  { name: 'passport', hash: '#/passport' },
  { name: 'udhari', hash: '#/udhari' },
  { name: 'demo', hash: '#/demo' },
  { name: 'pay', hash: '#/pay?m=M001', sizes: [1920, 1366, 390] },
]

// HTTP errors a page asks for on purpose: [url regex, status, why]. They are listed in the report, not counted.
const EXPECTED_HTTP = []

// ---------------------------------------------------------------- options

const argv = Object.fromEntries(process.argv.slice(2).map((a) => {
  const [k, v = 'true'] = a.replace(/^--/, '').split('=')
  return [k, v]
}))
const ONLY = argv.only ? argv.only.split(',') : null
const STATES = argv.state ? argv.state.split(',') : ['empty', 'full']
const ONLY_SIZES = argv.size ? argv.size.split(',').map(Number) : null

// ---------------------------------------------------------------- start and stop

const started = { backend: null, preview: null, browser: null, tmp: null }
let cleaning = null

async function portInUse(port) {
  return new Promise((resolve) => {
    const s = net.connect({ port, host: '127.0.0.1' })
    s.once('connect', () => { s.destroy(); resolve(true) })
    s.once('error', () => resolve(false))
    s.setTimeout(1500, () => { s.destroy(); resolve(false) })
  })
}

function killTree(child) {
  if (!child || child.exitCode !== null || child.killed) return
  if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
  else child.kill('SIGTERM')
}

async function cleanup() {
  if (cleaning) return cleaning
  cleaning = (async () => {
    try { if (started.browser) await started.browser.close() } catch { /* already gone */ }
    try { if (started.preview) await started.preview.close() } catch { /* already gone */ }
    const be = started.backend
    if (be && be.exitCode === null) {
      const exited = new Promise((r) => be.once('exit', r))
      killTree(be)
      await Promise.race([exited, new Promise((r) => setTimeout(r, 5000))])
    }
    if (started.tmp) {
      try { fs.rmSync(started.tmp, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 }) } catch { /* locked: left in temp */ }
    }
  })()
  return cleaning
}

process.on('SIGINT', () => { cleanup().finally(() => process.exit(130)) })
process.on('SIGTERM', () => { cleanup().finally(() => process.exit(143)) })
process.on('exit', () => { killTree(started.backend) }) // last resort, synchronous

async function startBackend() {
  const logPath = path.join(started.tmp, 'backend.log')
  const log = fs.openSync(logPath, 'w')
  const env = {
    ...process.env,
    DB_PATH: path.join(started.tmp, 'ui.db'),
    LOGS_DIR: path.join(started.tmp, 'logs'),
    ENABLE_DEMO_TOOLS: 'true',
    DEMO_MODE: 'cache_only',
    DEMO_DATE: DEMO_DAY.demo_date,
    DEMO_TIME: '21:30',
    UDHARI: 'true',
    PYTHONIOENCODING: 'utf-8',
  }
  const child = spawn(PYTHON, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(API_PORT)], {
    cwd: BACKEND_DIR, env, stdio: ['ignore', log, log], windowsHide: true,
  })
  started.backend = child
  const end = Date.now() + 90000
  while (Date.now() < end) {
    if (child.exitCode !== null) break
    try {
      const r = await fetch(`${API}/health`)
      if (r.ok) return
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 400))
  }
  const tail = fs.readFileSync(logPath, 'utf8').split('\n').slice(-20).join('\n')
  throw new Error(`backend did not start on ${API_PORT}:\n${tail}`)
}

async function buildAndServe() {
  const outDir = path.join(started.tmp, 'dist')
  process.env.VITE_API_BASE = API // wins over frontend/.env
  const { build, preview } = await import('vite')
  const configFile = path.join(FRONTEND, 'vite.config.js')
  await build({ root: FRONTEND, configFile, logLevel: 'warn', build: { outDir, emptyOutDir: true } })
  started.preview = await preview({
    root: FRONTEND, configFile, logLevel: 'warn', build: { outDir },
    preview: { host: '127.0.0.1', port: WEB_PORT, strictPort: true, open: false },
  })
}

// ---------------------------------------------------------------- API (states)

async function api(method, p, body) {
  const init = { method, headers: {} }
  if (body instanceof FormData) init.body = body
  else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(API + p, init)
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new Error(`${method} ${p} -> ${res.status} ${JSON.stringify(data)}`)
  return data
}

async function makeEmpty() {
  await api('POST', '/demo/reset', {})
  return { state: 'empty' }
}

async function makeFull() {
  await api('POST', '/demo/reset', {})
  await api('POST', '/expenses', DEMO_DAY.expense)
  let last = null
  for (let i = 0; i < 15; i += 1) last = await api('POST', '/demo/next-payment', { merchant_id: 'M001' })
  if (last.action !== 'ASK_MERCHANT' || !last.question_id) throw new Error(`the 15th payment did not ask: ${JSON.stringify(last)}`)
  await api('POST', `/payments/${encodeURIComponent(last.transaction_id)}/confirm`, {
    merchant_id: 'M001', question_id: last.question_id, confirmed_category: 'FAMILY',
    channel: 'VOICE', utterance_text: null, remember_payer: true,
  })
  const form = new FormData()
  form.append('file', new Blob([fs.readFileSync(NOTICE_PNG)], { type: 'image/png' }), 'sample_notice.png')
  form.append('merchant_id', 'M001')
  form.append('demo_key', 'sample_notice_v1')
  const notice = await api('POST', '/notices/analyse', form)

  const s = await api('GET', '/merchants/M001/summary')
  const got = Object.fromEntries(Object.keys(EXPECT_SUMMARY).map((k) => [k, s[k]?.amount_display]))
  const tabs = await api('GET', '/merchants/M001/tabs')
  const checks = [
    ...Object.entries(EXPECT_SUMMARY).map(([k, v]) => ({ check: `summary.${k}`, expected: v, got: got[k], ok: got[k] === v })),
    { check: 'summary.pending.count', expected: 0, got: s.pending?.count, ok: s.pending?.count === 0 },
    ...Object.entries(EXPECT_TABS).map(([k, v]) => ({ check: `tabs.${k}`, expected: v, got: tabs[k], ok: tabs[k] === v })),
  ]
  const bad = checks.filter((c) => !c.ok)
  if (bad.length) throw new Error(`full state is wrong: ${JSON.stringify(bad)}`)
  return { state: 'full', notice, checks }
}

// ---------------------------------------------------------------- page actions

async function settle(page) {
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await page.waitForFunction(() => ![...document.querySelectorAll('.load-state')].some((e) => /Loading/.test(e.textContent)),
    null, { timeout: 10000 }).catch(() => {})
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(700)
}

/** Open one entry the way a person does: tap its row (the newest correction when there is one). */
async function openLedgerEntry(page) {
  const rows = page.locator('.ledger-table button.tr[data-entry]')
  await rows.first().waitFor({ timeout: 6000 }).catch(() => {})
  let note = null
  if (await rows.count() === 0) {
    note = 'no entries today: opened the previous day'
    await page.getByRole('button', { name: 'Previous day' }).click()
    await rows.first().waitFor({ timeout: 10000 })
  }
  const corrections = rows.filter({ hasText: 'reclassification' })
  const target = (await corrections.count()) ? corrections.last() : rows.first()
  const id = await target.getAttribute('data-entry')
  await target.click()
  await page.locator('.detail .detail-amt').waitFor({ timeout: 10000 })
  await settle(page)
  return note ? `${note}; entry ${id}` : `entry ${id}`
}

/** Talk: tap the Koyambedu example (the tour plays the recorded clip of the same sentence). Never confirmed. */
async function typedExpense(page) {
  await page.locator('.talk-tries button.try', { hasText: 'Koyambedu' }).first().click()
  await page.locator('[data-tour="expense-card"]').waitFor({ timeout: 15000 })
  await settle(page)
  await page.waitForTimeout(1500) // Talk pins the newest card again at 450 ms and 1.3 s
  return 'typed the Koyambedu example; expense card shown, not confirmed'
}

/** Talk opened the way the tour's profit step opens it (#/talk?ask=profit). */
async function profitAnswer(page) {
  await page.locator('[data-tour="profit-answer"]').waitFor({ timeout: 20000 })
  await settle(page)
  await page.waitForTimeout(1500)
  return 'profit answer shown'
}

// ---------------------------------------------------------------- in-page checks

/* Runs in the page. Plain function: no closures over module scope. */
function collectChecks() {
  const de = document.documentElement
  const vw = de.clientWidth
  const vh = window.innerHeight
  const cssPath = (el) => {
    const parts = []
    for (let e = el, i = 0; e && e.nodeType === 1 && e !== document.body && i < 4; e = e.parentElement, i += 1) {
      let s = e.tagName.toLowerCase()
      if (e.id) s += `#${e.id}`
      const cls = [...e.classList].filter((c) => !c.startsWith('is-')).slice(0, 2)
      if (cls.length) s += `.${cls.join('.')}`
      parts.unshift(s)
    }
    return parts.join(' > ')
  }
  const text = (el, n = 60) => (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, n)
  const shown = (el) => el.checkVisibility({ opacityProperty: true, visibilityProperty: true })
  const fixedRoot = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) if (getComputedStyle(e).position === 'fixed') return e
    return null
  }
  const rnd = (r) => ({ x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) })

  // horizontal page overflow, with the elements that stick out (the outermost ones)
  const overflow = { scrollWidth: de.scrollWidth, clientWidth: vw, innerWidth: window.innerWidth, overflowing: de.scrollWidth > vw, culprits: [] }
  if (overflow.overflowing) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect()
      if (r.width === 0 || r.right <= vw + 1 || !shown(el)) continue
      const p = el.parentElement
      if (p && p !== document.body && p.getBoundingClientRect().right > vw + 1) continue
      overflow.culprits.push({ el: cssPath(el), right: Math.round(r.right), text: text(el, 40) })
      if (overflow.culprits.length >= 8) break
    }
  }

  // clipped text: a box with overflow hidden/clip whose text runs outside it (not ellipsis, not the ticker)
  const IGNORE = '.ticker, .visually-hidden, [data-ui-check-ignore]'
  const clips = (v) => v === 'hidden' || v === 'clip'
  const scrolls = (v) => v === 'auto' || v === 'scroll'
  const textClip = []
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest(IGNORE) || el instanceof SVGElement) continue
    const s = getComputedStyle(el)
    const cx = clips(s.overflowX) && el.scrollWidth > el.clientWidth + 1
    const cy = clips(s.overflowY) && el.scrollHeight > el.clientHeight + 1
    if ((!cx && !cy) || !shown(el)) continue
    const r = el.getBoundingClientRect()
    const box = { l: r.left + el.clientLeft, t: r.top + el.clientTop }
    box.r = box.l + el.clientWidth
    box.b = box.t + el.clientHeight
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    let hit = null
    while (!hit && walker.nextNode()) {
      const t = walker.currentNode
      if (!t.textContent.trim()) continue
      const pe = t.parentElement
      if (!pe || !shown(pe) || pe.closest(IGNORE)) continue
      // ellipsis is intentional; text inside its own scroller (or a fixed layer) is not clipped by this box
      let skip = false
      for (let e = pe; e && e !== el; e = e.parentElement) {
        const es = getComputedStyle(e)
        if (es.textOverflow === 'ellipsis' || scrolls(es.overflowX) || scrolls(es.overflowY) || es.position === 'fixed') { skip = true; break }
      }
      if (skip || s.textOverflow === 'ellipsis') continue
      const range = document.createRange()
      range.selectNodeContents(t)
      for (const rr of range.getClientRects()) {
        if (rr.width < 1 || rr.height < 1) continue
        const outX = cx && (rr.right > box.r + 2 || rr.left < box.l - 2)
        const outY = cy && (rr.bottom > box.b + 2 || rr.top < box.t - 2)
        if (outX || outY) {
          hit = { axis: outX ? 'x' : 'y', text: t.textContent.replace(/\s+/g, ' ').trim().slice(0, 60), by: Math.round(outX ? Math.max(rr.right - box.r, box.l - rr.left) : Math.max(rr.bottom - box.b, box.t - rr.top)) }
          break
        }
      }
    }
    if (hit) textClip.push({ el: cssPath(el), node: el, ...hit, box: rnd(r) })
  }
  // keep the innermost clipping box only
  const innermost = textClip.filter((a) => !textClip.some((b) => b !== a && a.node.contains(b.node)))
  innermost.forEach((x) => { delete x.node })

  // overlapping controls
  const Q = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=link], [role=checkbox], [role=radio]'
  const ctrls = [...document.querySelectorAll(Q)].filter((el) => {
    if (!shown(el)) return false
    const r = el.getBoundingClientRect()
    return r.width > 2 && r.height > 2
  }).map((el) => ({ el, r: el.getBoundingClientRect(), fixed: fixedRoot(el) }))
  const overlaps = []
  const tourOverlaps = []
  for (let i = 0; i < ctrls.length; i += 1) {
    for (let j = i + 1; j < ctrls.length; j += 1) {
      const a = ctrls[i]
      const b = ctrls[j]
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue
      const iw = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left)
      const ih = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top)
      if (iw <= 4 || ih <= 4) continue
      // a label wrapping an input is one control
      const lab = (x) => x.el.closest('label')
      if (lab(a) && lab(a) === lab(b)) continue
      const item = {
        a: cssPath(a.el), aText: text(a.el, 30), b: cssPath(b.el), bText: text(b.el, 30),
        overlap: `${Math.round(iw)}x${Math.round(ih)}`,
        fixed: a.fixed || b.fixed ? (a.fixed && b.fixed ? (a.fixed === b.fixed ? 'same fixed layer' : 'two fixed layers') : 'fixed over content') : null,
      }
      // once the page is scrolled, content passing under the fixed bars is how scrolling works
      if (item.fixed === 'fixed over content' && window.scrollY > 0) continue
      if (a.el.closest('.tour-start') || b.el.closest('.tour-start')) tourOverlaps.push(item)
      else overlaps.push(item)
    }
  }

  // controls in fixed chrome that sit (partly) outside the viewport: nobody can scroll to them
  const offscreenFixed = ctrls.filter((c) => c.fixed && (c.r.bottom > vh + 1 || c.r.right > vw + 1 || c.r.top < -1))
    .map((c) => ({ el: cssPath(c.el), text: text(c.el, 30), box: rnd(c.r), viewport: `${vw}x${vh}` }))

  // images
  const images = [...document.images].filter((i) => i.complete && i.naturalWidth === 0 && i.getAttribute('src'))
    .map((i) => ({ src: i.currentSrc || i.src, el: cssPath(i) }))

  // Tamil / Telugu: which elements carry the text, at what size; mark a few for the font probe (CDP)
  const SCRIPTS = { ta: /[஀-௿]/, te: /[ఀ-౿]/ }
  const indic = { ta: { count: 0, small: [] }, te: { count: 0, small: [] } }
  const seen = new Set()
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  while (tw.nextNode()) {
    const t = tw.currentNode
    const pe = t.parentElement
    if (!pe || seen.has(pe) || pe.closest('script, style, .visually-hidden')) continue
    for (const [k, re] of Object.entries(SCRIPTS)) {
      if (!re.test(t.textContent)) continue
      if (!shown(pe) || !pe.getClientRects().length) continue
      seen.add(pe)
      const cs = getComputedStyle(pe)
      const size = parseFloat(cs.fontSize)
      if (indic[k].count < 8) pe.setAttribute('data-uicheck-font', `${k}-${indic[k].count}`)
      indic[k].count += 1
      if (size < 22 && !(pe instanceof SVGElement)) indic[k].small.push({ el: cssPath(pe), size, text: t.textContent.trim().slice(0, 40) })
    }
  }
  const faces = [...document.fonts].filter((f) => /Noto Sans (Tamil|Telugu)/.test(f.family))
    .map((f) => ({ family: f.family, status: f.status, weight: f.weight }))

  return { overflow, textClip: innermost, overlaps, tourOverlaps, offscreenFixed, images, indic, faces }
}

/** Which fonts Chrome actually used for the marked Tamil/Telugu elements (CSS.getPlatformFontsForNode). */
async function probeFonts(page, indic, faces) {
  const out = {}
  const cdp = await page.context().newCDPSession(page)
  try {
    await cdp.send('DOM.enable')
    await cdp.send('CSS.enable')
    const { root } = await cdp.send('DOM.getDocument', { depth: -1 })
    for (const k of ['ta', 'te']) {
      if (!indic[k].count) continue
      const want = k === 'ta' ? /Noto Sans Tamil/ : /Noto Sans Telugu/
      const { nodeIds } = await cdp.send('DOM.querySelectorAll', { nodeId: root.nodeId, selector: `[data-uicheck-font^="${k}-"]` })
      const used = {}
      let withNoto = 0
      for (const nodeId of nodeIds) {
        const { fonts } = await cdp.send('CSS.getPlatformFontsForNode', { nodeId })
        for (const f of fonts) {
          const key = `${f.familyName}${f.isCustomFont ? ' (web font)' : ' (system)'}`
          used[key] = (used[key] || 0) + f.glyphCount
        }
        // the @fontsource face, not a system copy that happens to share the name
        if (fonts.some((f) => want.test(f.familyName) && f.isCustomFont && f.glyphCount > 0)) withNoto += 1
      }
      const loaded = faces.filter((f) => want.test(f.family) && f.status === 'loaded').length
      out[k] = {
        elements: indic[k].count, probed: nodeIds.length, renderedWithNoto: withNoto, facesLoaded: loaded, used,
        ok: nodeIds.length > 0 && withNoto === nodeIds.length && loaded > 0,
        small: indic[k].small,
      }
    }
  } finally {
    await cdp.detach().catch(() => {})
  }
  return out
}

// ---------------------------------------------------------------- one page

function expectedHttp(url, status) {
  return EXPECTED_HTTP.find(([re, st]) => re.test(url) && st === status) || null
}

async function visit(browser, route, size, state, setup) {
  const spec = SIZES[size]
  const context = await browser.newContext({
    viewport: { width: spec.width, height: spec.height },
    deviceScaleFactor: spec.deviceScaleFactor || 1,
    isMobile: Boolean(spec.isMobile), hasTouch: Boolean(spec.hasTouch),
    locale: 'en-IN', timezoneId: 'Asia/Kolkata', serviceWorkers: 'block',
  })
  await context.addInitScript(({ notice, merchant }) => {
    // never make sound: Windows speech ignores --mute-audio
    try {
      if (window.speechSynthesis) {
        window.speechSynthesis.speak = () => {}
        if (window.SpeechSynthesis) window.SpeechSynthesis.prototype.speak = function speak() {}
      }
    } catch { /* no speech */ }
    // the full state read the sample notice through the API; the Notice screen keeps that response per tab
    if (notice) {
      try { window.sessionStorage.setItem(`naanayam.notice.${notice.notice_id}`, JSON.stringify(notice)) } catch { /* blocked */ }
    }
    // the top bar's merchant switch remembers its choice here (app/merchant.jsx)
    try { window.localStorage.setItem('naanayam.merchant', merchant) } catch { /* blocked */ }
  }, { notice: state === 'full' ? setup.notice : null, merchant: route.merchant || 'M001' })

  const page = await context.newPage()
  const rec = { console: [], pageErrors: [], http: [], expectedHttp: [], failed: [], aborted: [] }
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const url = m.location()?.url || ''
    rec.console.push({ text: m.text().slice(0, 300), url })
  })
  page.on('pageerror', (e) => rec.pageErrors.push(String(e.stack || e).slice(0, 600)))
  page.on('requestfailed', (r) => {
    const item = { method: r.method(), url: r.url(), error: r.failure()?.errorText }
    if (/ERR_ABORTED/.test(item.error || '')) rec.aborted.push(item)
    else rec.failed.push(item)
  })
  page.on('response', (r) => {
    if (r.status() < 400) return
    const item = { method: r.request().method(), url: r.url(), status: r.status() }
    const why = expectedHttp(item.url, item.status)
    if (why) rec.expectedHttp.push({ ...item, why: why[2] })
    else rec.http.push(item)
  })

  const hash = state === 'full' && route.full ? route.full(setup) : route.hash
  const result = { route: route.name, hash, size, viewport: `${spec.width}x${spec.height}`, state }
  try {
    await page.goto(WEB + hash, { waitUntil: 'load', timeout: 30000 })
    await settle(page)
    if (route.action) result.action = await route.action(page)
    const dir = path.join(SHOTS, String(size))
    fs.mkdirSync(dir, { recursive: true })
    const rel = (f) => path.relative(FRONTEND, f).replaceAll('\\', '/')
    if (route.keepScroll) {
      // where the screen put itself: what a person (or the tour) sees
      result.scrollY = await page.evaluate(() => Math.round(window.scrollY))
      const vfile = path.join(dir, `${safe(route.name)}-${state}-viewport.png`)
      await page.screenshot({ path: vfile, animations: 'disabled', caret: 'hide' })
      result.viewportShot = rel(vfile)
    } else {
      // from the top: an action (tapping a row) may have scrolled the page
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
      await page.waitForTimeout(300)
    }
    const checks = await page.evaluate(collectChecks)
    const fonts = await probeFonts(page, checks.indic, checks.faces)
    delete checks.indic
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
    await page.waitForTimeout(300)
    const file = path.join(dir, `${safe(route.name)}-${state}.png`)
    await page.screenshot({ path: file, fullPage: true, animations: 'disabled', caret: 'hide' })
    result.shot = rel(file)
    const { default: AxeBuilder } = await import('@axe-core/playwright')
    const axe = await new AxeBuilder({ page }).analyze()
    result.axe = axe.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')) }))
    Object.assign(result, checks, { fonts })
  } catch (e) {
    result.error = String(e.stack || e).slice(0, 800)
  }
  // a console "Failed to load resource" for an expected response is part of that response, not a new error
  const expectedUrls = new Set(rec.expectedHttp.map((x) => x.url))
  rec.console = rec.console.filter((c) => !(/Failed to load resource/.test(c.text) && expectedUrls.has(c.url)))
  Object.assign(result, rec)
  await context.close()
  return result
}

function safe(name) {
  return name.replace(/^#\/?/, '').replace(/[^a-zA-Z0-9-]+/g, '_').replace(/^_+|_+$/g, '') || 'landing'
}

// ---------------------------------------------------------------- report

function countsOf(p) {
  const fontsBad = Object.values(p.fonts || {}).filter((f) => !f.ok).length
  const small = Object.values(p.fonts || {}).reduce((n, f) => n + f.small.length, 0)
  return {
    console: p.console.length + p.pageErrors.length,
    http: p.http.length + p.failed.length,
    hOverflow: p.overflow?.overflowing ? p.overflow.scrollWidth - p.overflow.clientWidth : 0,
    textClip: p.textClip?.length || 0,
    overlap: (p.overlaps?.length || 0) + (p.tourOverlaps?.length || 0),
    offscreen: p.offscreenFixed?.length || 0,
    images: p.images?.length || 0,
    fonts: fontsBad,
    smallIndic: small,
    axe: (p.axe || []).reduce((n, v) => n + v.nodes, 0),
    error: p.error ? 1 : 0,
  }
}

function printTable(pages) {
  const cols = ['route', 'size', 'state', 'console', 'http', 'hOverflow', 'textClip', 'overlap', 'offscreen', 'images', 'fonts', 'smallIndic', 'axe', 'error']
  const rows = pages.map((p) => ({ route: p.route, size: p.size, state: p.state, ...countsOf(p) }))
  const w = Object.fromEntries(cols.map((c) => [c, Math.max(c.length, ...rows.map((r) => String(r[c]).length))]))
  const line = (r) => cols.map((c) => String(r[c]).padEnd(w[c])).join('  ')
  console.log(`\n${line(Object.fromEntries(cols.map((c) => [c, c])))}`)
  console.log(cols.map((c) => '-'.repeat(w[c])).join('  '))
  for (const r of rows) console.log(line(r))
  const totals = Object.fromEntries(cols.slice(3).map((c) => [c, rows.reduce((n, r) => n + r[c], 0)]))
  const axeRules = {}
  for (const p of pages) for (const v of p.axe || []) axeRules[`${v.id} (${v.impact})`] = (axeRules[`${v.id} (${v.impact})`] || 0) + v.nodes
  console.log(`\npages: ${pages.length}  pages with any finding: ${rows.filter((r) => cols.slice(3).some((c) => r[c])).length}`)
  console.log(`totals: ${Object.entries(totals).map(([k, v]) => `${k} ${v}`).join(' · ')}`)
  if (Object.keys(axeRules).length) console.log(`axe serious/critical by rule (nodes): ${Object.entries(axeRules).map(([k, v]) => `${k} ${v}`).join(' · ')}`)
  return { totals, axeRules }
}

// ---------------------------------------------------------------- main

async function main() {
  const t0 = Date.now()
  for (const port of [API_PORT, WEB_PORT]) {
    if (await portInUse(port)) throw new Error(`port ${port} is already in use; stop whatever is on it and run again`)
  }
  started.tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'naanayam-ui-'))
  console.log(`temp: ${started.tmp}`)
  console.log(`backend: ${API} (UDHARI=true, DEMO_MODE=cache_only, DEMO_TIME=21:30)`)
  await startBackend()
  console.log(`frontend: building with VITE_API_BASE=${API}, serving on ${WEB}`)
  await buildAndServe()
  const { chromium } = await import('playwright')
  started.browser = await chromium.launch({ channel: 'chrome', args: ['--mute-audio'] })

  fs.mkdirSync(SHOTS, { recursive: true })
  const pages = []
  const setups = {}
  for (const state of STATES) {
    const setup = state === 'full' ? await makeFull() : await makeEmpty()
    setups[state] = { checks: setup.checks || null, notice_id: setup.notice?.notice_id || null }
    console.log(`\nstate ${state}${setup.checks ? `: ${setup.checks.map((c) => `${c.check}=${c.got}`).join(', ')}` : ''}`)
    for (const route of ROUTES) {
      if (ONLY && !ONLY.includes(route.name)) continue
      for (const size of route.sizes || [1920, 1366]) {
        if (ONLY_SIZES && !ONLY_SIZES.includes(size)) continue
        const p = await visit(started.browser, route, size, state, setup)
        const c = countsOf(p)
        const found = Object.entries(c).filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join(', ')
        console.log(`  ${route.name.padEnd(14)} ${String(size).padEnd(5)} ${found || 'clean'}`)
        pages.push(p)
      }
    }
  }
  const summary = printTable(pages)
  const report = {
    generated_at: new Date().toISOString(),
    seconds: Math.round((Date.now() - t0) / 1000),
    api: API, web: WEB, states: setups,
    expected_http: EXPECTED_HTTP.map(([re, st, why]) => ({ url: String(re), status: st, why })),
    ...summary, pages,
  }
  fs.writeFileSync(path.join(SHOTS, 'report.json'), JSON.stringify(report, null, 2))
  console.log(`\nreport: ${path.join(SHOTS, 'report.json')}  (${report.seconds} s)`)
}

let code = 0
try {
  await main()
} catch (e) {
  console.error(`\nui-check failed: ${e.stack || e}`)
  code = 1
} finally {
  await cleanup()
}
process.exit(code)
