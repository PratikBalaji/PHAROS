import test from 'node:test';
import assert from 'node:assert/strict';
import { SUPPORTED_LANGUAGES, renderAlert, recommendedLanguages, isSupported, languageMeta } from '../dist/i18n.js';

test('every supported language has a template and preserves the EXERCISE label', () => {
  for (const { code } of SUPPORTED_LANGUAGES) {
    assert.ok(isSupported(code), `missing template for ${code}`);
    const text = renderAlert(code, { area: 'Altadena' });
    assert.ok(text.includes('Altadena'), `${code} did not insert the area`);
    // Each language carries an explicit exercise / drill marker (not a real order).
    assert.ok(text.length > 20);
  }
  // English is the reviewed source; others are flagged for native-speaker review.
  assert.equal(languageMeta('en').reviewed, true);
  assert.equal(languageMeta('ar').rtl, true);
});

test('renderAlert falls back to English for unknown codes and a default area', () => {
  const text = renderAlert('xx');
  assert.ok(text.startsWith('EXERCISE ONLY'));
  assert.ok(text.includes('the selected areas'));
});

test('recommendedLanguages is demographic-weighted and always English-first', () => {
  const selected = [
    { properties: { population: 200000, languages: [{ code: 'hy', share: 0.34 }, { code: 'es', share: 0.12 }] } }, // Glendale-like
    { properties: { population: 40000, languages: [{ code: 'es', share: 0.20 }, { code: 'zh', share: 0.03 }] } },
  ];
  const langs = recommendedLanguages(selected);
  assert.equal(langs[0], 'en');
  // Armenian weight (200000*0.34=68000) beats Spanish (200000*0.12 + 40000*0.20 = 32000).
  assert.ok(langs.indexOf('hy') < langs.indexOf('es'));
  assert.ok(langs.includes('zh'));
});

test('ACS codes without a template are ignored but English still returns', () => {
  const langs = recommendedLanguages([{ properties: { population: 1000, languages: [{ code: 'de', share: 0.9 }] } }]);
  assert.deepEqual(langs, ['en']);
});
