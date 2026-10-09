const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '../assets/service-worker.js'), 'utf8');

function worker(offline = false) {
  const handlers = {};
  const writes = [];
  const waits = [];
  const installed = [];
  const sandbox = {
    URL,
    self: {location: {origin: 'https://driver.test'}, addEventListener: (name, handler) => {handlers[name] = handler;}, skipWaiting() {}},
    fetch: async () => {
      if (offline) throw new Error('Offline');
      return new Response('fresh');
    },
    caches: {
      match: async request => request?.url?.endsWith('/driver') ? null : new Response('cached'),
      open: async () => ({
        addAll: async assets => installed.push(...assets),
        put: async (request, response) => writes.push([request.url, await response.text()]),
      }),
    },
  };
  vm.runInNewContext(source, sandbox);
  return {
    writes,
    installed,
    async install() {
      handlers.install({waitUntil: promise => waits.push(promise)});
      await Promise.all(waits);
    },
    async get(url, destination = 'document') {
      let response;
      handlers.fetch({
        request: {url: `https://driver.test${url}`, method: 'GET', destination},
        respondWith: promise => {response = promise;},
        waitUntil: promise => waits.push(promise),
      });
      if (!response) return null;
      const text = await (await response).text();
      await Promise.all(waits);
      return text;
    },
  };
}

test('install preloads the canonical HTTPS driver path instead of a redirect', async () => {
  const w = worker();
  await w.install();
  assert.ok(w.installed.includes('/driver/'));
  assert.ok(!w.installed.includes('/driver'));
  assert.ok(w.installed.includes('/workspace-bootstrap.js'));
});

test('online driver shell and bootstrap scripts prefer the network over stale cache', async () => {
  const w = worker();
  assert.equal(await w.get('/driver'), 'fresh');
  assert.equal(await w.get('/app/entry.client.js', 'script'), 'fresh');
  assert.equal(w.writes.length, 2);
});

test('offline driver shell and assets use the installed cache', async () => {
  const w = worker(true);
  assert.equal(await w.get('/driver'), 'cached');
  assert.equal(await w.get('/driver-app.js', 'script'), 'cached');
  assert.equal(w.writes.length, 0);
});

test('authenticated API and administrative navigation are never intercepted or cached', async () => {
  const w = worker();
  assert.equal(await w.get('/api/driver/returns'), null);
  assert.equal(await w.get('/api/dashboard/login'), null);
  assert.equal(await w.get('/'), null);
  assert.equal(await w.get('/loading'), null);
  assert.equal(w.writes.length, 0);
});

test('backend port configuration is refreshed online instead of pinned to an old port', async () => {
  const w = worker();
  assert.equal(await w.get('/env.json', ''), 'fresh');
  assert.equal(await w.get('/env.json?import', 'script'), 'fresh');
});
