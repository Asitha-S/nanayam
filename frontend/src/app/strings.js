// UI words that follow the merchant's language (Murugan: Tamil, Venkatesh: Telugu).
// Tamil: docs/VOICE_AND_NOTICE.md (sections 4.2–4.4). Telugu answer words: the Telugu question in
// backend/app/questions_text.py ("ఇది షాప్ అమ్మకమా, ఇంటి డబ్బా?") and the te profit templates in the same doc.
// Keys listed in TELUGU_DRAFTS have no Telugu in the spec yet: drafts for the Telugu owner (templates/te.json) to confirm.
import { useMerchant } from './merchant'

export const STRINGS = {
  ta: {
    languageName: 'Tamil',
    sale: 'கடை வியாபாரம்',
    family: 'வீட்டு பணம்',
    rememberAlways: 'ஆமா, எப்பவும்',
    rememberOnce: 'இந்த தடவை மட்டும்',
    addExpense: 'செலவு சேர்',
    todaysProfit: 'இன்னைக்கு லாபம்',
  },
  te: {
    languageName: 'Telugu',
    sale: 'షాప్ అమ్మకం',
    family: 'ఇంటి డబ్బు',
    rememberAlways: 'అవును, ఎప్పుడూ',
    rememberOnce: 'ఈ ఒక్కసారి మాత్రమే',
    addExpense: 'ఖర్చు చేర్చు',
    todaysProfit: 'ఈరోజు లాభం',
  },
}

export const TELUGU_DRAFTS = ['rememberAlways', 'rememberOnce', 'addExpense', 'todaysProfit']

/** Strings for a language code ('ta' | 'te'), plus `lang` for the lang attribute. */
export function stringsFor(lang) {
  const code = STRINGS[lang] ? lang : 'ta'
  return { ...STRINGS[code], lang: code }
}

/** Strings for the selected merchant's language (inside the app only). */
export function useStrings() {
  const { language } = useMerchant()
  return stringsFor(language)
}
