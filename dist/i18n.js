// Multilingual EXERCISE alert templates + demographic-driven language recommendation.
// Templates are the "safe floor": fixed, human-authored strings with one {area} slot.
// Non-English translations are best-effort and need native-speaker review before any real
// use (reviewed:false) — matching the deck's validation posture. English is the source.

export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English', native: 'English', reviewed: true },
  { code: 'es', label: 'Spanish', native: 'Español', reviewed: false },
  { code: 'zh', label: 'Chinese', native: '中文', reviewed: false },
  { code: 'ko', label: 'Korean', native: '한국어', reviewed: false },
  { code: 'tl', label: 'Tagalog', native: 'Tagalog', reviewed: false },
  { code: 'vi', label: 'Vietnamese', native: 'Tiếng Việt', reviewed: false },
  { code: 'hy', label: 'Armenian', native: 'Հայերեն', reviewed: false },
  { code: 'ar', label: 'Arabic', native: 'العربية', rtl: true, reviewed: false },
  { code: 'ru', label: 'Russian', native: 'Русский', reviewed: false },
];

const TEMPLATES = {
  en: 'EXERCISE ONLY — not a real emergency. {area}: a wildfire evacuation exercise is in progress. In a real event, follow the official instructions from your local emergency authority. This is a drill and not an evacuation order.',
  es: 'SIMULACRO SOLAMENTE — no es una emergencia real. {area}: hay un simulacro de evacuación por incendio forestal en curso. En un evento real, siga las instrucciones oficiales de su autoridad local de emergencias. Esto es un simulacro y no una orden de evacuación.',
  zh: '仅为演习 — 并非真实紧急情况。{area}：正在进行野火疏散演习。如遇真实事件，请遵循当地应急管理部门的官方指示。这是演习，并非疏散命令。',
  ko: '훈련 전용 — 실제 긴급 상황이 아닙니다. {area}: 산불 대피 훈련이 진행 중입니다. 실제 상황에서는 지역 긴급 당국의 공식 지시를 따르십시오. 이것은 훈련이며 대피 명령이 아닙니다.',
  tl: 'PAGSASANAY LAMANG — hindi tunay na emerhensiya. {area}: may isinasagawang pagsasanay sa paglikas dahil sa wildfire. Sa totoong pangyayari, sundin ang opisyal na tagubilin mula sa inyong lokal na awtoridad sa emerhensiya. Ito ay pagsasanay at hindi utos na lumikas.',
  vi: 'CHỈ LÀ DIỄN TẬP — không phải tình huống khẩn cấp thật. {area}: đang diễn ra cuộc diễn tập sơ tán vì cháy rừng. Trong sự kiện thật, hãy làm theo hướng dẫn chính thức từ cơ quan khẩn cấp địa phương của bạn. Đây là diễn tập, không phải lệnh sơ tán.',
  hy: 'ՄԻԱՅՆ ՎԱՐԺԱՆՔ — սա իրական արտակարգ իրավիճակ չէ: {area}: ընթանում է անտառային հրդեհի տարհանման վարժանք: Իրական դեպքում հետևեք ձեր տեղական արտակարգ իրավիճակների մարմնի պաշտոնական ցուցումներին: Սա վարժանք է, ոչ թե տարհանման հրաման:',
  ar: 'تدريب فقط — ليست حالة طوارئ حقيقية. {area}: يجري حالياً تدريب على الإخلاء بسبب حريق هائل. في حالة حقيقية، اتبع التعليمات الرسمية من سلطة الطوارئ المحلية لديك. هذا تدريب وليس أمراً بالإخلاء.',
  ru: 'ТОЛЬКО УЧЕНИЯ — это не настоящая чрезвычайная ситуация. {area}: проводятся учения по эвакуации при лесном пожаре. В реальной ситуации следуйте официальным указаниям местных экстренных служб. Это учения, а не приказ об эвакуации.',
};

// ACS table C16001 groups several languages together; map each ACS code that has a
// template to that template. Codes without a specific template (other Asian, German,
// French, unspecified) are left out of the recommendation but still shown in the split.
const ACS_TO_TEMPLATE = { en: 'en', es: 'es', zh: 'zh', ko: 'ko', tl: 'tl', vi: 'vi', hy: 'hy', ar: 'ar', ru: 'ru' };

export function isSupported(code) {
  return Object.prototype.hasOwnProperty.call(TEMPLATES, code);
}

export function languageMeta(code) {
  return SUPPORTED_LANGUAGES.find(l => l.code === code) || SUPPORTED_LANGUAGES[0];
}

export function renderAlert(code, slots = {}) {
  const area = slots.area || 'the selected areas';
  const template = TEMPLATES[code] || TEMPLATES.en;
  return template.replace('{area}', area);
}

// Given selected district features (or their properties), return language codes ordered
// by population-weighted presence. English is always included and placed first.
export function recommendedLanguages(selected) {
  const weight = {};
  for (const item of selected || []) {
    const props = item.properties || item;
    const pop = Number(props.population) || 0;
    for (const lang of props.languages || []) {
      const code = ACS_TO_TEMPLATE[lang.code];
      if (!code || code === 'en') continue;
      weight[code] = (weight[code] || 0) + pop * (Number(lang.share) || 0);
    }
  }
  const ranked = Object.keys(weight).sort((a, b) => weight[b] - weight[a]);
  return ['en', ...ranked];
}
