#!/usr/bin/env node
// Draft and (optionally) send the EXERCISE texts for every fire run through a deployed PHAROS:
// per run, the AI-chosen translated language messages (English plus the top two other languages)
// and one Gemini-polished strategy text built from the planner's own result.
//
//   node scripts/simulate_runs.mjs --json > facts.json          # planner facts (live OSRM)
//   node scripts/send_exercise_sms.mjs --facts facts.json       # DRY RUN: writes drafts, sends nothing
//   node scripts/send_exercise_sms.mjs --facts facts.json --send --reviewer "Your Name" [verdugo ...]
//
// Options: --base URL (default https://www.pharos.casa)  --batch TAG (idempotency tag, default ex1)
//          --sidecar URL  deliver through the Mac iMessage sidecar instead of Photon SMS (token in PHOTON_SIDECAR_TOKEN)
//          --languages N (default 3 total)  --out FILE (drafts markdown)  --gap SECONDS (default 4)
// Every text is marked EXERCISE ONLY by the server. Sends go to the single configured test number.
// Behind a proxy: NODE_USE_ENV_PROXY=1 NODE_EXTRA_CA_CERTS=<bundle>.
import fs from 'node:fs';

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : dflt; };
const BASE = opt('base', 'https://www.pharos.casa').replace(/\/$/, '');
const SEND = args.includes('--send');
const BATCH = opt('batch', 'ex1');
const N_LANG = Number(opt('languages', 3));
const GAP = Number(opt('gap', 4)) * 1000;
const REVIEWER = opt('reviewer', '');
const OUT = opt('out', 'exercise_drafts.md');
const SIDECAR = opt('sidecar', '').replace(/\/$/, '');
const SIDECAR_TOKEN = process.env.PHOTON_SIDECAR_TOKEN || '';
const factsFile = opt('facts');
const valued = new Set(['--sidecar', '--base', '--batch', '--languages', '--gap', '--reviewer', '--out', '--facts']);
const only = args.filter((a, i) => !a.startsWith('--') && !valued.has(args[i - 1]));
if (!factsFile) { console.error('Need --facts <file from simulate_runs.mjs --json>'); process.exit(2); }
if (SEND && SIDECAR && SIDECAR_TOKEN.length < 16) { console.error('--sidecar needs PHOTON_SIDECAR_TOKEN in the environment'); process.exit(2); }
if (SEND && !REVIEWER.trim()) { console.error('--send needs --reviewer "<name of the person who reviewed the drafts>"'); process.exit(2); }

const wait = ms => new Promise(r => setTimeout(r, ms));
async function api(path, body) {
  const res = await fetch(BASE + path, body ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  const text = await res.text();
  let json; try { json = JSON.parse(text); } catch { json = { raw: text.slice(0, 200) }; }
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status} ${JSON.stringify(json).slice(0, 200)}`);
  return json;
}

const all = JSON.parse(fs.readFileSync(factsFile, 'utf8'));
const runs = only.length ? all.filter(f => only.includes(f.run)) : all;
const drafts = [];
for (const f of runs) {
  const plan = await api('/api/console/language-plan', { geoid: f.geoid });
  const codes = plan.languages.slice(0, N_LANG);
  const tr = await api('/api/console/translate', { geoid: f.geoid, languages: codes });
  const texts = Object.fromEntries(codes.map(c => [c, tr.messages[c].text]));
  const facts = f.outcome === 'withheld' ? { run_name: f.runName, outcome: 'withheld' }
    : { run_name: f.runName, outcome: f.outcome, assembly: f.assembly, minutes: f.minutes, km: f.km };
  const strat = await api('/api/console/strategy-plan', { geoid: f.geoid, facts });
  drafts.push({ f, plan, tr, codes, texts, facts, strat });
  console.log(`drafted ${f.run}: ${codes.join(',')} [${plan.engine}] + strategy [${strat.engine}]`);
}

let md = `# Exercise SMS drafts (${new Date().toISOString()})\nTarget: ${BASE}. ${SEND ? 'SENDING' : 'DRY RUN, nothing sent'}.\n`;
for (const d of drafts) {
  md += `\n## ${d.f.runName} — ${d.plan.name} (outcome: ${d.f.outcome})\nLanguage plan: ${d.plan.engine}; ${d.plan.rationale}\n`;
  for (const c of d.codes) md += `\n**${c}** (${d.tr.messages[c].source}${d.tr.messages[c].reviewed ? '' : ', machine translation, review pending'}):\n> ${d.texts[c]}\n`;
  md += `\n**strategy** (${d.strat.source}):\n> ${d.strat.text}\n`;
}
fs.writeFileSync(OUT, md);
console.log(`\nWrote ${OUT}: ${drafts.length} runs, ${drafts.reduce((n, d) => n + d.codes.length + 1, 0)} texts`);
if (!SEND) process.exit(0);

const receipts = [];
async function sidecarSend(key, text) {
  const res = await fetch(SIDECAR + '/send', { method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SIDECAR_TOKEN }, body: JSON.stringify({ key, text }) });
  const j = await res.json().catch(() => ({}));
  if (!res.ok && !j.state) throw new Error(`sidecar HTTP ${res.status} ${JSON.stringify(j).slice(0, 160)}`);
  return j;
}
for (const d of drafts) {
  const rid = `${BATCH}-${d.f.run}`;
  let lang, st;
  if (SIDECAR) {
    lang = { results: [], counts: { submitted: 0 } };
    for (const c of d.codes) { const r = await sidecarSend(`${rid}-${c}`, d.texts[c]); lang.results.push({ code: c, state: r.state, message_id: null, provider_status: r.error || null, duplicate: !!r.duplicate }); if (r.state === 'sent') lang.counts.submitted++; }
    const r = await sidecarSend(`${rid}-strategy`, d.strat.text);
    st = { result: { state: r.state, message_id: null, provider_status: r.error || null, duplicate: !!r.duplicate } };
  } else {
    lang = await api('/api/console/send-sms', { request_id: rid, geoid: d.f.geoid, reviewer: REVIEWER, reviewed: true, texts: d.texts });
    await wait(GAP);
    st = await api('/api/console/strategy-sms', { request_id: rid + '-strategy', geoid: d.f.geoid, reviewer: REVIEWER, reviewed: true, facts: d.facts, text: d.strat.text });
  }
  for (const r of lang.results) receipts.push({ run: d.f.run, kind: r.code, state: r.state, id: r.message_id, status: r.provider_status, dup: r.duplicate });
  receipts.push({ run: d.f.run, kind: 'strategy', state: st.result.state, id: st.result.message_id, status: st.result.provider_status, dup: st.result.duplicate });
  console.log(`sent ${d.f.run}: ${lang.counts.submitted} language + strategy ${st.result.state}`);
  await wait(GAP);
}
const ids = receipts.map(r => r.id).filter(Boolean);
let fresh = {};
if (ids.length) {
  await wait(3000);
  for (let i = 0; i < ids.length; i += 20) {
    const j = await api('/api/console/sms-status?ids=' + ids.slice(i, i + 20).join(','));
    for (const r of j.receipts) fresh[r.message_id] = r.provider_status || 'error: ' + r.error;
  }
}
console.table(receipts.map(r => ({ run: r.run, kind: r.kind, sent: r.state, photon: fresh[r.id] || r.status || '-', id: r.id || '-' })));
fs.writeFileSync(OUT.replace(/\.md$/, '') + '.receipts.json', JSON.stringify(receipts.map(r => ({ ...r, photon: fresh[r.id] })), null, 2));
