#!/usr/bin/env node
// PHAROS Photon iMessage sidecar. Runs on a Mac that is signed into Messages.
//
// Safety rules (all enforced here, not trusted from the caller):
//   - the recipient is fixed by PHOTON_SIDECAR_TO; the request can never choose one
//   - every request needs the bearer token PHOTON_SIDECAR_TOKEN
//   - the text must begin with one of PHAROS's exercise markers (dist/data/alert-templates.json)
//   - one send per idempotency key; an ambiguous result blocks automatic resend
//   - binds to 127.0.0.1 unless PHOTON_SIDECAR_HOST is set
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAX_BODY = 8 * 1024, MAX_TEXT = 1000, KEY_RE = /^[A-Za-z0-9_-]{8,96}$/;

export function loadMarkers(file = path.join(HERE, '../../dist/data/alert-templates.json')) {
  const cat = JSON.parse(fs.readFileSync(file, 'utf8'));
  return Object.values(cat.templates).map(t => t.split('{area}')[0].trim());
}

export function createSidecar({ sdk, token, to, markers, statePath, gapMs = 1500, log = () => {} }) {
  if (!token || token.length < 16) throw new Error('PHOTON_SIDECAR_TOKEN must be at least 16 characters');
  if (!to) throw new Error('PHOTON_SIDECAR_TO (the one test recipient) is required');
  const state = statePath && fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath, 'utf8')) : {};
  const save = () => { if (statePath) fs.writeFileSync(statePath, JSON.stringify(state, null, 2)); };
  let chain = Promise.resolve(); // sends are serialized so iMessage order matches request order
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const authOk = req => {
    const given = Buffer.from((req.headers.authorization || '').replace(/^Bearer /, ''));
    const want = Buffer.from(token);
    return given.length === want.length && crypto.timingSafeEqual(given, want);
  };
  const reply = (res, code, body) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };

  async function deliver(key, text) {
    const prior = state[key];
    if (prior) return { code: 200, body: { key, state: prior.state, duplicate: true, at: prior.at } };
    state[key] = { state: 'sending', at: new Date().toISOString() }; save(); // written before dispatch, so a crash blocks resend
    try {
      await sdk.send({ to, text });
      state[key] = { state: 'sent', at: new Date().toISOString() }; save();
      log(`sent ${key}`);
      return { code: 200, body: { key, state: 'sent', duplicate: false, note: 'Accepted by Messages.app; delivery is not confirmed by the kit' } };
    } catch (e) {
      const timedOut = /time/i.test(String(e?.message || e));
      if (timedOut) { state[key] = { state: 'uncertain', at: new Date().toISOString() }; save(); return { code: 502, body: { key, state: 'uncertain', error: 'Send timed out; it may have gone out. Check Messages before retrying.' } }; }
      delete state[key]; save(); // plain failure: safe to retry with the same key
      return { code: 502, body: { key, state: 'rejected', error: 'Messages.app refused the send: ' + String(e?.message || e).slice(0, 200) } };
    }
  }

  return http.createServer((req, res) => {
    if (req.method === 'GET' && req.url === '/health') return reply(res, 200, { ok: true, recipient: to.slice(0, 2) + '…' + to.slice(-2), markers: markers.length });
    if (req.method !== 'POST' || req.url !== '/send') return reply(res, 404, { error: 'not found' });
    if (!authOk(req)) return reply(res, 401, { error: 'bad token' });
    let raw = '';
    req.on('data', c => { raw += c; if (raw.length > MAX_BODY) { reply(res, 413, { error: 'too large' }); req.destroy(); } });
    req.on('end', () => {
      let b; try { b = JSON.parse(raw); } catch { return reply(res, 400, { error: 'invalid JSON' }); }
      const { key, text } = b || {};
      if (typeof key !== 'string' || !KEY_RE.test(key)) return reply(res, 400, { error: 'key must be 8-96 chars of A-Z a-z 0-9 _ -' });
      if (typeof text !== 'string' || text.length < 20 || text.length > MAX_TEXT) return reply(res, 400, { error: 'text length must be 20-1000' });
      if (!markers.some(m => text.startsWith(m))) return reply(res, 400, { error: 'text must start with an exercise marker' });
      chain = chain.then(async () => { const r = await deliver(key, text); await wait(r.body.duplicate ? 0 : gapMs); return r; });
      chain.then(r => reply(res, r.code, r.body));
    });
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { IMessageSDK } = await import('@photon-ai/imessage-kit');
  const server = createSidecar({
    sdk: new IMessageSDK(), token: process.env.PHOTON_SIDECAR_TOKEN, to: process.env.PHOTON_SIDECAR_TO,
    markers: loadMarkers(), statePath: path.join(HERE, '.sidecar-state.json'), log: m => console.log(new Date().toISOString(), m),
  });
  const port = Number(process.env.PHOTON_SIDECAR_PORT || 8787), host = process.env.PHOTON_SIDECAR_HOST || '127.0.0.1';
  server.listen(port, host, () => console.log(`PHAROS Photon sidecar on http://${host}:${port} (recipient fixed, exercise markers enforced)`));
}
