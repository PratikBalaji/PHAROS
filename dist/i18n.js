// Multilingual EXERCISE alert templates + demographic-driven language recommendation.
// Templates are the "safe floor": fixed, human-authored strings with one {area} slot.
// Non-English translations are best-effort and need native-speaker review before any real
// use (reviewed:false) — matching the deck's validation posture. English is the source.

import catalogue from './data/alert-templates.json' with {type:'json'};
export const SUPPORTED_LANGUAGES=catalogue.languages;
export const TEMPLATES=catalogue.templates;

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
      if (!code || code === 'en' || !(Number(lang.share)>0)) continue;
      weight[code] = (weight[code] || 0) + pop * (Number(lang.share) || 0);
    }
  }
  const ranked = Object.keys(weight).sort((a, b) => weight[b] - weight[a]);
  return ['en', ...ranked];
}

// Sending scope is derived from selected areas, never from the preview tab.
export function buildLanguagePlan(selected,mode='auto') {
  if(!['auto','all'].includes(mode))throw new Error('Unknown language strategy');
  const seen=new Set();const areas=[];
  for(const item of selected||[]){const p=item.properties||item;if(seen.has(p.GEOID))continue;seen.add(p.GEOID);
    const codes=mode==='all'?SUPPORTED_LANGUAGES.map(l=>l.code):recommendedLanguages([p]);
    const gaps=(p.languages||[]).filter(l=>Number(l.share)>0&&(!isSupported(l.code)||/other|unspecified|slavic|indo-european/i.test(l.label||''))).map(l=>l.label||l.code);
    areas.push({geoid:p.GEOID,name:p.name,demographics_source:p.demographics_source||'unknown',gaps,messages:codes.map(code=>({code,text:renderAlert(code,{area:p.name}),reviewed:languageMeta(code).reviewed,rtl:!!languageMeta(code).rtl}))});
  }
  return {mode,areas,languages:[...new Set(areas.flatMap(a=>a.messages.map(m=>m.code)))],message_count:areas.reduce((n,a)=>n+a.messages.length,0),requires_language_review:areas.some(a=>a.messages.some(m=>!m.reviewed)),has_illustrative_data:areas.some(a=>!a.demographics_source.startsWith('ACS')),has_coverage_gaps:areas.some(a=>a.gaps.length>0)};
}
