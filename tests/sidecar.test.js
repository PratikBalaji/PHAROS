import test from 'node:test';
import assert from 'node:assert/strict';
import { createSidecar, loadMarkers } from '../sidecar/photon/server.mjs';

const TOKEN = 'test-token-0123456789';
const MARKER = loadMarkers().find(m => m.startsWith('EXERCISE ONLY'));
const GOOD = `${MARKER} Glendale city: a wildfire evacuation exercise is in progress. This is a drill.`;

async function boot(sdk, extra = {}) {
  const server = createSidecar({ sdk, token: TOKEN, to: '+15555550123', markers: loadMarkers(), gapMs: 0, ...extra });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const post = (body, token = TOKEN) => fetch(base + '/send', { method: 'POST', headers: { authorization: 'Bearer ' + token, 'content-type': 'application/json' }, body: JSON.stringify(body) });
  return { server, base, post };
}

test('markers cover every language and the English one is present', () => {
  const m = loadMarkers();
  assert.equal(m.length, 9);
  assert.ok(m.every(x => x.length > 5));
  assert.ok(MARKER);
});

test('rejects missing or wrong token, bad key, short text, and text without an exercise marker', async () => {
  const sent = [];
  const { server, post } = await boot({ send: async r => sent.push(r) });
  assert.equal((await post({ key: 'abcdefgh1', text: GOOD }, 'wrong-token-0123456789')).status, 401);
  assert.equal((await post({ key: 'x', text: GOOD })).status, 400);
  assert.equal((await post({ key: 'abcdefgh1', text: 'too short' })).status, 400);
  assert.equal((await post({ key: 'abcdefgh1', text: 'Evacuate the whole district immediately, no drill here.' })).status, 400);
  assert.equal(sent.length, 0);
  server.close();
});

test('the recipient is always the fixed one, even if the caller supplies another', async () => {
  const sent = [];
  const { server, post } = await boot({ send: async r => sent.push(r) });
  const r = await post({ key: 'recipient-1', text: GOOD, to: '+19999999999' });
  assert.equal(r.status, 200);
  assert.deepEqual(sent, [{ to: '+15555550123', text: GOOD }]);
  server.close();
});

test('one send per key: a repeat is a duplicate and does not call the SDK again', async () => {
  let n = 0;
  const { server, post } = await boot({ send: async () => { n++; } });
  const a = await (await post({ key: 'idem-key-1', text: GOOD })).json();
  const b = await (await post({ key: 'idem-key-1', text: GOOD })).json();
  assert.equal(n, 1);
  assert.equal(a.duplicate, false);
  assert.equal(b.duplicate, true);
  server.close();
});

test('a plain failure may be retried; a timeout blocks resend as uncertain', async () => {
  let calls = 0;
  const { server, post } = await boot({ send: async () => { calls++; if (calls === 1) throw new Error('osascript failed'); } });
  assert.equal((await post({ key: 'retry-key-1', text: GOOD })).status, 502);
  assert.equal((await post({ key: 'retry-key-1', text: GOOD })).status, 200);
  server.close();
  let t = 0;
  const b = await boot({ send: async () => { t++; throw new Error('send timeout'); } });
  const first = await b.post({ key: 'timeout-key-1', text: GOOD });
  assert.equal((await first.json()).state, 'uncertain');
  const again = await (await b.post({ key: 'timeout-key-1', text: GOOD })).json();
  assert.equal(again.duplicate, true);
  assert.equal(t, 1);
  b.server.close();
});

test('sends keep request order even when fired together', async () => {
  const order = [];
  const { server, post } = await boot({ send: async r => { await new Promise(x => setTimeout(x, r.text.includes('slow') ? 30 : 1)); order.push(r.text.includes('slow') ? 'slow' : 'fast'); } });
  const slow = post({ key: 'order-slow-1', text: GOOD + ' slow' });
  await new Promise(x => setTimeout(x, 5));
  const fast = post({ key: 'order-fast-1', text: GOOD + ' fast' });
  await Promise.all([slow, fast]);
  assert.deepEqual(order, ['slow', 'fast']);
  server.close();
});

test('refuses to start with a weak token or no recipient', () => {
  assert.throws(() => createSidecar({ sdk: {}, token: 'short', to: '+1', markers: [] }));
  assert.throws(() => createSidecar({ sdk: {}, token: TOKEN, to: '', markers: [] }));
});
