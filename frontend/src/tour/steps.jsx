// Judge tour steps, in the order of BUILD_PLAN section 7. Captions are English; Tamil content stays Tamil.
// No rupee figure is typed here: the highlighted screen shows the backend's own numbers.
// target: the data-tour name to highlight (or a list, first one on screen wins). enter(h): runs only when moving
// forward, and does everything the step needs (demo endpoints, navigation). h is built in Tour.jsx.
import { STRINGS } from '../app/strings'

const ta = STRINGS.ta
const M = 'M001'

export const STEPS = [
  {
    id: 'intro',
    title: 'Judge tour',
    text: <>Murugan&apos;s day, step by step: payments arrive, one question in Tamil, the profit spoken back, and the proof behind every number. Starting resets the demo day.</>,
    next: 'Reset and start',
  },
  {
    id: 'arrive',
    target: 'soundbox-stage',
    title: 'A payment arrives',
    text: <>A customer pays by UPI. The Soundbox announces it, and Naanayam counts it as a shop sale without asking anyone: it is sure enough. The morning&apos;s Koyambedu stock purchase is already logged by voice.</>,
    enter: async (h) => {
      await h.post('/demo/reset', {})
      await h.logExpense()
      await h.go('/soundbox')
      await h.send(1)
    },
  },
  {
    id: 'sales',
    target: 'soundbox-payments',
    title: 'Thirteen more, sorted silently',
    text: <>The next customers pay. Every call is confident, so every payment is counted as a sale and Murugan is never interrupted.</>,
    enter: async (h) => {
      await h.go('/soundbox')
      await h.send(13)
    },
  },
  {
    id: 'question',
    target: 'soundbox-question',
    title: 'Not sure? It asks',
    text: <>Lakshmi R sends money. It could be family money, so instead of guessing, Naanayam asks Murugan one question in Tamil. Tap <span lang="ta">{ta.family}</span>, then <span lang="ta">{ta.rememberAlways}</span> to remember her. If nobody taps, Next answers for him.</>,
    enter: async (h) => {
      await h.go('/soundbox')
      await h.send(1)
    },
  },
  {
    id: 'instruction',
    target: 'preview',
    title: 'Next time: his instruction',
    text: <>A future payment from Lakshmi R is no longer a guess. Naanayam follows Murugan&apos;s own instruction and shows it as &ldquo;Your instruction&rdquo;, not as a model percentage.</>,
    enter: async (h) => {
      const payer = await h.answerAskedPayment()
      await h.go(`/learning?payer=${encodeURIComponent(payer)}&run=${h.nonce()}`)
    },
  },
  {
    id: 'profit',
    target: 'profit-answer',
    title: 'Profit, spoken back',
    text: <>Murugan asks how much he made today. The answer is a fixed Tamil template filled with the ledger&apos;s own numbers, and checked before it is spoken. UPI payments and the expenses he logged, nothing else.</>,
    enter: (h) => h.go(`/talk?ask=profit&n=${h.nonce()}`),
  },
  {
    id: 'tap',
    target: 'sales-figure',
    title: 'Every number is a link',
    text: <>Business sales on the Today screen. Tap it, or press Next: every amount in Naanayam opens the ledger entries behind it.</>,
    enter: (h) => h.go('/today'),
  },
  {
    id: 'entries',
    target: 'ledger-table',
    title: 'The entries behind it',
    text: <>Each sale is its own ledger entry, with the payment it came from and the hash that chains it to the entry before.</>,
    enter: async (h) => {
      const s = await h.get(`/merchants/${M}/summary?include_sources=true`)
      await h.go(`/ledger?ids=${encodeURIComponent((s.sources?.business_sales || []).join(','))}`)
    },
  },
  {
    id: 'evaluation',
    target: 'eval-headline',
    title: 'Does it find the family money?',
    text: <>Measured on held-out merchants the model never saw, next to calling everything a sale. Read the label: this is synthetic data from our generator, not real merchants.</>,
    enter: (h) => h.go('/learning'),
  },
  {
    id: 'verify',
    target: 'verify',
    title: 'Nothing edited, everything checked',
    text: <>The ledger is append-only and hash-chained. This check recomputes every hash: VALID means no entry changed after it was written.</>,
    enter: (h) => h.go('/ledger'),
  },
  {
    id: 'notice',
    target: ['notice-evidence', 'notice-read'],
    title: 'Proof for the taxman',
    text: <>One sample GST notice, read and set beside the ledger for the same period, for a CA to check. Naanayam explains and organises; it never files or replies. If no notice has been read yet, pick the sample here.</>,
    enter: (h) => h.go(h.lastNotice() ? `/notice?id=${encodeURIComponent(h.lastNotice())}` : '/notice'),
  },
  {
    id: 'done',
    title: 'That was Murugan’s day',
    text: <>Every rupee on these screens came from the ledger, and every number opens its entries. Explore any screen, or start the tour again.</>,
    next: 'Finish',
  },
]
