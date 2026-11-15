// Talk screen words in the merchant's language. Sentences are the templates in docs/VOICE_AND_NOTICE.md section 7
// (Tamil and Telugu columns). Shared answer words (sale, family, remember, add expense, today's profit) come from
// src/app/strings.js. Keys in TELUGU_DRAFTS / TAMIL_DRAFTS are not in the spec yet: drafts for the language owners.

const TA = {
  not_understood: 'புரியல. செலவு சொல்லுங்க, இல்லன்னா இன்னைக்கு லாபம் கேளுங்க.',
  start: 'செலவு சொல்லுங்க, இல்லன்னா இன்னைக்கு லாபம் கேளுங்க.',
  no_speech: 'கேக்கல. இன்னொரு தடவை சொல்லுங்க.',
  offline: 'இப்போ இணைப்பு இல்ல. திரையில தட்டி சேர்க்கலாம்.',
  clarify_amount: 'எவ்வளவு ரூபாய்னு இன்னொரு தடவை சொல்லுங்க.',
  clarify_category: 'கடை வியாபாரமா, வீட்டு பணமா? கீழ தட்டுங்க.',
  remember_question: (name) => `இனிமே ${name} அனுப்புறது எல்லாம் வீட்டு பணமா?`,
  confirm_family: 'சரி, இதை வீட்டு பணமா வச்சுட்டேன். கடை கணக்குல சேர்க்கல.',
  confirm_family_remembered: (name) => `சரி. இனிமே ${name} பணம் வீட்டு பணமா எடுத்துக்கறேன். கடை கணக்குல சேர்க்க மாட்டேன்.`,
  confirm_sale: 'சரி, இதை கடை வியாபாரமா சேர்த்துட்டேன்.',
  expense_saved: 'செலவு சேமிச்சுட்டேன்.', // follows the saved amount
  expense_large_warning: 'பெரிய தொகை. திரையில சரி-ன்னு தட்டுங்க.',
  reversed: 'இந்த பணம் திரும்ப போயிடுச்சு.',
  yes: 'சரி',
  change: 'மாற்று',
  cancel: 'ரத்து',
  placeholder: 'இங்க எழுதுங்க, இல்லன்னா பேசுங்க', // the example sentence is the Try chip below the box
  typeHere: 'இங்க எழுதுங்க',
  categories: {
    STOCK_PURCHASE: 'சரக்கு', TRANSPORT: 'வண்டி', PACKAGING: 'கவர்', RENT: 'வாடகை', WAGES: 'கூலி',
    UTILITIES: 'கரண்ட்/தண்ணி', OTHER: 'மற்ற',
  },
  // Example sentences: the demo audio lines in section 10, so typed and spoken demos say the same thing.
  examples: ['Koyambedu-la 3,100 rupees-ku kaaikari vaanginen', 'இன்னைக்கு எவ்வளவு லாபம்?'],
  answerExamples: ['வீட்டு பணம், அக்கா அனுப்பினாங்க', 'கடை வியாபாரம்'],
  rememberExamples: ['ஆமா, எப்பவும்'],
  // Udhari (flag UDHARI only): the credit book, contract section 13
  credit_saved: 'கடன் கணக்குல எழுதிட்டேன்.', // follows the amount written on the tab
  credit_pick: 'யார் கணக்குல எழுதணும்? கீழ தட்டுங்க.',
  clarify_credit: 'யாருக்கு, எவ்வளவு ரூபாய்னு இன்னொரு தடவை சொல்லுங்க.',
  udhariExamples: ['ரமேஷ் 300 கடன்', 'யாரெல்லாம் பணம் தரணும்?'],
}

const TE = {
  not_understood: 'అర్థం కాలేదు. ఖర్చు చెప్పండి, లేదా ఈరోజు లాభం అడగండి.',
  start: 'ఖర్చు చెప్పండి, లేదా ఈరోజు లాభం అడగండి.',
  no_speech: 'వినిపించలేదు. మళ్ళీ చెప్పండి.',
  offline: 'ఇప్పుడు నెట్ లేదు. స్క్రీన్ మీద నొక్కి చేర్చవచ్చు.',
  clarify_amount: 'ఎంత రూపాయలో మళ్ళీ ఒకసారి చెప్పండి.',
  clarify_category: 'షాప్ అమ్మకమా, ఇంటి డబ్బా? కింద నొక్కండి.',
  remember_question: (name) => `ఇకపై ${name} పంపేది అంతా ఇంటి డబ్బేనా?`,
  confirm_family: 'సరే, ఇది ఇంటి డబ్బుగా పెట్టాను. షాప్ లెక్కలో కలపలేదు.',
  confirm_family_remembered: (name) => `సరే. ఇకపై ${name} డబ్బు ఇంటి డబ్బుగా తీసుకుంటాను. షాప్ లెక్కలో కలపను.`,
  confirm_sale: 'సరే, ఇది షాప్ అమ్మకంగా కలిపాను.',
  expense_saved: 'ఖర్చు సేవ్ చేశాను.',
  expense_large_warning: 'పెద్ద మొత్తం. స్క్రీన్ మీద సరే నొక్కండి.',
  reversed: 'ఈ డబ్బు తిరిగి వెళ్ళిపోయింది.',
  yes: 'సరే',
  change: 'మార్చు',
  cancel: 'రద్దు',
  placeholder: 'ఇక్కడ రాయండి, లేదా మాట్లాడండి', // the example sentence is the Try chip below the box
  typeHere: 'ఇక్కడ రాయండి',
  categories: {
    STOCK_PURCHASE: 'సరుకు', TRANSPORT: 'బండి', PACKAGING: 'కవర్', RENT: 'అద్దె', WAGES: 'కూలి',
    UTILITIES: 'కరెంట్/నీళ్లు', OTHER: 'ఇతర',
  },
  examples: ['Koyambedu lo 4,200 rupayalaku pandlu konnanu', 'ఈరోజు లాభం ఎంత?'],
  answerExamples: ['ఇంటి డబ్బు, తమ్ముడు పంపాడు', 'షాప్ అమ్మకం'],
  rememberExamples: ['అవును, ఎప్పుడూ'],
  // Udhari (flag UDHARI only)
  credit_saved: 'అప్పు లెక్కలో రాశాను.',
  credit_pick: 'ఎవరి లెక్కలో రాయాలి? కింద నొక్కండి.',
  clarify_credit: 'ఎవరికి, ఎంత రూపాయలో మళ్ళీ ఒకసారి చెప్పండి.',
  udhariExamples: [],
}

export const TAMIL_DRAFTS = ['placeholder', 'typeHere', 'start', 'credit_saved', 'credit_pick', 'clarify_credit']
export const TELUGU_DRAFTS = ['reversed', 'yes', 'change', 'cancel', 'placeholder', 'typeHere', 'start', 'credit_saved', 'credit_pick', 'clarify_credit']

export const EXPENSE_CATEGORIES = ['STOCK_PURCHASE', 'TRANSPORT', 'PACKAGING', 'RENT', 'WAGES', 'UTILITIES', 'OTHER']

/** Talk words for 'ta' | 'te' (Tamil when unknown). */
export function talkWords(lang) {
  return lang === 'te' ? TE : TA
}

/** "STOCK_PURCHASE" -> "stock purchase" (English caption under the merchant's word). */
export function words(s) {
  return (s || '').toLowerCase().replaceAll('_', ' ')
}
