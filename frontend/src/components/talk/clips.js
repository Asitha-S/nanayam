// Recorded demo clips (VOICE_AND_NOTICE 3 and 10). A clip is offered only when its demo_key is registered in
// cache/sarvam_demo/demo_clips.json AND its WAV exists at assets/demo_audio/{demo_key}.wav. Both are read at build
// time, so the list is empty until clips are recorded and registered. On screen a clip is always "Recorded demo clip".

const REGISTRY = import.meta.glob('../../../../cache/sarvam_demo/demo_clips.json', { eager: true, import: 'default' })
const FILES = import.meta.glob('../../../../assets/demo_audio/*/*.wav', { eager: true, query: '?url', import: 'default' })

// What each scripted clip says (section 10), shown on its button.
const CLIP_TEXT = {
  'ta/expense_koyambedu': 'Koyambedu-la 3,100 rupees-ku kaaikari vaanginen',
  'ta/confirm_yes': 'சரி',
  'ta/answer_family': 'வீட்டு பணம், அக்கா அனுப்பினாங்க',
  'ta/remember_yes': 'ஆமா, எப்பவும்',
  'ta/ask_profit': 'இன்னைக்கு எவ்வளவு லாபம்?',
  'te/expense_koyambedu': 'Koyambedu lo 4,200 rupayalaku pandlu konnanu',
  'te/answer_family': 'ఇంటి డబ్బు, తమ్ముడు పంపాడు',
  'te/ask_profit': 'ఈరోజు లాభం ఎంత?',
}
// Clips that answer an open question; they are offered only while a question card is open.
const ANSWER_CLIPS = ['answer_family', 'remember_yes', 'confirm_yes']

const registered = Object.values(REGISTRY)[0] || {}

/** [{ demoKey, url, text, lang, answers }] for one language ('ta' | 'te'). */
export function demoClips(lang) {
  return Object.keys(registered)
    .filter((key) => key.startsWith(`${lang}/`))
    .map((key) => ({
      demoKey: key,
      url: FILES[`../../../../assets/demo_audio/${key}.wav`],
      text: CLIP_TEXT[key] || key.split('/')[1].replaceAll('_', ' '),
      lang,
      answers: ANSWER_CLIPS.includes(key.split('/')[1]),
    }))
    .filter((c) => c.url)
}
