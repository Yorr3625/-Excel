const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {randomUUID} = require('node:crypto');

const source = readFileSync(path.join(__dirname, '../assets/driver-app.js'), 'utf8');

function app() {
  const element = {innerHTML: '', textContent: '', className: '', addEventListener() {}, setAttribute() {}, querySelector() { return this; }, querySelectorAll() { return []; }};
  const sandbox = {
    console, URL, structuredClone, crypto: {randomUUID},
    navigator: {onLine: true}, localStorage: {getItem() {return null;}, setItem() {}},
    window: {location: {origin: 'https://driver.test'}, confirm: () => true},
    document: {getElementById: () => element}, fetch: async () => ({ok: false}),
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(source.slice(0, source.indexOf('window.addEventListener("online"')), context);
  vm.runInContext(`
    globalThis.stores = new Map();
    globalThis.calls = [];
    dbPut = async (store, key, value) => {
      if (!stores.has(store)) stores.set(store, new Map());
      stores.get(store).set(key, structuredClone(value));
    };
    dbGet = async (store, key) => structuredClone(stores.get(store)?.get(key));
    dbAll = async (store) => [...(stores.get(store)?.values() || [])].map(value => structuredClone(value));
    dbDelete = async (store, key) => stores.get(store)?.delete(key);
    driverId = 'driver-a'; csrfToken = 'csrf'; online = true; mileage = {required: false};
    globalThis.contextFixture = {
      assignment_id: 'route-a', route_label: 'Route A', loading_ready: true, eligible: true, complete: true,
      facts_token: 'fresh-token', reasons: ['Повреждение', 'Другое'], document: null,
      lines: [{loading_line_id: 'load-1', name: 'Product', planned_kg: '15', loaded_net_kg: '10', shipped_net_kg: '4', available_net_kg: '6'}]
    };
    globalThis.lineFixture = {selected: true, box_count: '2', tare_weight_per_box_kg: '0.5', gross_weight_kg: '7', reason: 'Повреждение', comment: ''};
    globalThis.queueFixture = () => ({driver_id: driverId, assignment_id: 'route-a', expected_facts: returnFacts(contextFixture), created_at: '2026-01-01', payload: {operation_id: 'op-1', base_revision: 0, facts_token: '', lines: {'load-1': {...lineFixture}}}});
  `, context);
  return {run: text => vm.runInContext(text, context), element};
}

test('validates positive net bounded by loaded minus shipped, integer boxes, reason, Other comment', () => {
  const t = app();
  assert.equal(t.run(`validateReturnDraft({lines: {'load-1': lineFixture}}, contextFixture)['load-1'].gross_weight_kg`), '7');
  for (const patch of ["gross_weight_kg: '7.01'", "gross_weight_kg: '1'", "box_count: '1.2'", "tare_weight_per_box_kg: '-1'", "gross_weight_kg: ''", "reason: ''", "reason: 'Другое', comment: ' '"]) {
    assert.throws(() => t.run(`validateReturnDraft({lines: {'load-1': {...lineFixture, ${patch}}}}, contextFixture)`));
  }
  assert.throws(() => t.run(`validateReturnDraft({lines: {}}, contextFixture)`));
  assert.equal(t.run(`validateReturnDraft({lines: {'load-1': {...lineFixture, reason: 'Другое', comment: '  Detail  '}}}, contextFixture)['load-1'].comment`), 'Detail');
});

test('facts compare loading and shipping, not only available net', () => {
  const t = app();
  assert.equal(t.run(`sameReturnFacts(returnFacts(contextFixture), contextFixture)`), true);
  assert.equal(t.run(`sameReturnFacts(returnFacts(contextFixture), {...contextFixture, lines: [{...contextFixture.lines[0], loaded_net_kg: '11', shipped_net_kg: '5'}]})`), false);
  assert.equal(t.run(`sameReturnFacts({}, contextFixture)`), false);
});

test('offline completion derives shipped weights by loading identity, never by product name', () => {
  const t = app();
  t.run(`globalThis.local = {return_context: {...contextFixture, eligible: false, complete: false}, stores: [
    {status: 'completed', lines: [{name: 'same', loading_line_id: 'load-1', actual_qty: '2'}]},
    {status: 'completed', lines: [{name: 'different', loading_line_id: 'load-1', shipment_measurement: {net_weight_kg: '3'}}]}
  ]};`);
  assert.equal(t.run(`localReturnContext(local).lines[0].available_net_kg`), '5');
  assert.equal(t.run(`editableReturn(localReturnContext(local))`), true);
  assert.equal(t.run(`localReturnContext({...local, stores: [{status: 'pending'}]}).complete`), false);
  assert.equal(t.run(`localReturnContext({...local, stores: [{status: 'completed', lines: [{loading_line_id: 'wrong', actual_qty: '1'}]}]}).complete`), false);
});

test('submitted and accepted documents are read-only, rejected drafts use document revision', () => {
  const t = app();
  for (const status of ['submitted', 'accepted']) assert.equal(t.run(`editableReturn({...contextFixture, document: {status: '${status}'}})`), false);
  assert.equal(t.run(`draftFromContext({...contextFixture, document: {status: 'rejected', revision: 3, lines: []}}).base_revision`), 3);
  assert.equal(t.run(`editableReturn({...contextFixture, document: {status: 'rejected'}})`), true);
});

test('draft autosave uses driver plus assignment and isolates another driver', async () => {
  const t = app();
  await t.run(`returnDraft = draftFromContext(contextFixture); returnDraft.lines['load-1'] = {...lineFixture}; saveReturnDraft();`);
  assert.equal(await t.run(`dbGet(RETURN_DRAFT_STORE, 'driver-b:route-a')`), undefined);
  assert.equal(await t.run(`dbGet(RETURN_DRAFT_STORE, 'driver-a:route-a').then(d => d.lines['load-1'].gross_weight_kg)`), '7');
});

test('unsent return checks server facts before adopting token, preserves mismatch', async () => {
  const t = app();
  await t.run(`dbPut(RETURN_QUEUE_STORE, returnKey('route-a'), queueFixture())`);
  t.run(`api = async (url, options = {}) => { calls.push({url, options}); return {context: {...contextFixture, lines: [{...contextFixture.lines[0], shipped_net_kg: '5'}]}}; };`);
  await assert.rejects(t.run(`flushReturnQueue()`));
  assert.equal(t.run(`calls.length`), 1);
  assert.equal(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a')).then(op => Boolean(op && !op.sent_body))`), true);
});

test('lost response retries exact persisted bytes without refreshing facts or token', async () => {
  const t = app();
  await t.run(`dbPut(RETURN_QUEUE_STORE, returnKey('route-a'), queueFixture())`);
  t.run(`api = async (url, options = {}) => {
    calls.push({url, options});
    if (!options.method) return {context: contextFixture};
    const saved = await dbGet(RETURN_QUEUE_STORE, returnKey('route-a'));
    if (saved.sent_body !== options.body) throw new Error('Not durable before POST');
    throw new Error('Response lost');
  };`);
  await assert.rejects(t.run(`flushReturnQueue()`), /Response lost/);
  const body = t.run(`calls[1].options.body`);
  assert.equal(JSON.parse(body).facts_token, 'fresh-token');
  t.run(`api = async (url, options = {}) => { calls.push({url, options}); return {ok: true, document: {assignment_id: 'route-a', status: 'submitted', revision: 1}}; };`);
  await t.run(`flushReturnQueue()`);
  assert.equal(t.run(`calls.length`), 3);
  assert.equal(t.run(`calls[2].options.body`), body);
  assert.equal(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a'))`), undefined);
});

test('return 409 retains exact operation and error for retry', async () => {
  const t = app();
  await t.run(`dbPut(RETURN_QUEUE_STORE, returnKey('route-a'), queueFixture())`);
  t.run(`api = async (url, options = {}) => { if (!options.method) return {context: contextFixture}; throw Object.assign(new Error('Conflict'), {status: 409}); };`);
  await assert.rejects(t.run(`flushReturnQueue()`), /Conflict/);
  assert.equal(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a')).then(op => Boolean(op.sent_body && op.error === 'Conflict'))`), true);
});

test('legacy unbound shipment queue is never silently retargeted or deleted', async () => {
  const t = app();
  await t.run(`dbPut(QUEUE_STORE, 'old', {driver_id: driverId, store_id: 'store', payload: {operation_id: 'old'}})`);
  t.run(`api = async () => { calls.push('unexpected'); };`);
  assert.equal(await t.run(`flushQueue()`), false);
  assert.equal(t.run(`calls.length`), 0);
  assert.equal(await t.run(`dbAll(QUEUE_STORE).then(entries => entries.length)`), 1);
});

test('shipment conflict stops following operations and returns without deleting either', async () => {
  const t = app();
  await t.run(`Promise.all([1, 2].map(n => dbPut(QUEUE_STORE, 'op-' + n, {driver_id: driverId, assignment_id: 'route-a', store_id: 'store-' + n, payload: {assignment_id: 'route-a', operation_id: 'op-' + n, base_revision: n}})))`);
  t.run(`api = async () => { calls.push('post'); throw Object.assign(new Error('Route changed'), {status: 409}); };`);
  assert.equal(await t.run(`flushQueue()`), false);
  assert.equal(t.run(`calls.length`), 1);
  assert.equal(await t.run(`dbAll(QUEUE_STORE).then(entries => entries.length)`), 2);
  await assert.rejects(t.run(`flushReturnQueue()`));
});

test('historical return bypasses current mileage gate but never queued shipments', async () => {
  const t = app();
  t.run(`mileage = {required: true}; view = 'returns'; render = () => {};
    flushMileageQueue = async () => {calls.push('mileage'); return false;};
    flushQueue = async () => {calls.push('stores'); return true;};
    flushReturnQueue = async () => {calls.push('returns');}; loadReturnIndex = async () => {};`);
  await t.run(`syncOrder()`);
  assert.equal(t.run(`calls.join(',')`), 'mileage,returns');
  await t.run(`dbPut(QUEUE_STORE, 'pending', {driver_id: driverId})`);
  t.run(`calls.length = 0`);
  await t.run(`syncOrder()`);
  assert.equal(t.run(`calls.join(',')`), 'mileage');
});

test('synchronization order is mileage, store completions, then returns', async () => {
  const t = app();
  await t.run(`dbPut(QUEUE_STORE, 'pending', {driver_id: driverId})`);
  t.run(`render = () => {}; view = 'order';
    flushMileageQueue = async () => {calls.push('mileage'); return true;};
    flushQueue = async () => {calls.push('stores'); return true;};
    flushReturnQueue = async () => {calls.push('returns');};
    api = async () => ({assignment: null});`);
  await t.run(`syncOrder()`);
  assert.equal(t.run(`calls.join(',')`), 'mileage,stores,returns');
});

test('older assignment cache cannot overwrite an accepted return document', async () => {
  const t = app();
  await t.run(`cacheReturnContext({...contextFixture, document: {assignment_id: 'route-a', status: 'accepted', revision: 2}})`);
  await t.run(`cacheReturnContext(contextFixture)`);
  assert.equal(await t.run(`dbGet(RETURN_CACHE_STORE, returnKey('route-a')).then(item => item.context.document.status)`), 'accepted');
});

test('history retains local drafts when navigator reports online but server fails', async () => {
  const t = app();
  await t.run(`cacheReturnContext(contextFixture)`);
  await t.run(`dbPut(RETURN_DRAFT_STORE, returnKey('route-a'), draftFromContext(contextFixture))`);
  t.run(`api = async () => {throw new Error('offline');}`);
  await assert.rejects(t.run(`loadReturnIndex()`), /offline/);
  assert.equal(t.run(`returnIndex.assignments.length`), 1);
  assert.equal(t.run(`returnIndex.drafts.length`), 1);
});

test('rejected documents reopen as a new revision without reusing an operation id', async () => {
  const t = app();
  await t.run(`dbPut(RETURN_DRAFT_STORE, returnKey('route-a'), {...draftFromContext(contextFixture), base_revision: 0})`);
  t.run(`api = async () => ({context: {...contextFixture, document: {status: 'rejected', revision: 2, lines: [{loading_line_id: 'load-1', measurement: lineFixture, reason: 'Другое', comment: 'Revise me'}]}}});`);
  await t.run(`loadReturn('route-a')`);
  assert.equal(t.run(`returnDraft.base_revision`), 2);
  assert.equal(t.run(`returnDraft.lines['load-1'].comment`), 'Revise me');
  assert.equal(t.run(`returnOperation`), null);
  assert.equal(t.run(`returnDraft.operation_id`), undefined);
});

test('server incomplete prevents sending even when a local draft was queued', async () => {
  const t = app();
  await t.run(`dbPut(RETURN_QUEUE_STORE, returnKey('route-a'), queueFixture())`);
  t.run(`api = async (url, options = {}) => {calls.push(options.method || 'GET'); return {context: {...contextFixture, complete: false, eligible: false}};};`);
  await assert.rejects(t.run(`flushReturnQueue()`));
  assert.equal(t.run(`calls.join(',')`), 'GET');
  assert.equal(await t.run(`dbAll(RETURN_QUEUE_STORE).then(items => items.length)`), 1);
});

test('history actor objects display escaped names and fall back to IDs', () => {
  const t = app();
  t.run(`returnContext = {...contextFixture, document: {status: 'accepted', lines: [], history: [
    {kind: 'accepted', actor: {kind: 'admin', id: 'admin-1', name: '<b>Reviewer</b>'}},
    {kind: 'submitted', actor: {kind: 'driver', id: 'driver-77'}}
  ]}}; renderReturn();`);
  assert.ok(t.element.innerHTML.includes('&lt;b&gt;Reviewer&lt;/b&gt;'));
  assert.ok(t.element.innerHTML.includes('driver-77'));
  assert.ok(!t.element.innerHTML.includes('[object Object]'));
});

test('definite 400/409 keeps rejected bytes and draft until explicit rebase creates a new operation', async () => {
  for (const status of [400, 409]) {
    const t = app();
    await t.run(`returnContext = contextFixture; returnDraft = draftFromContext(contextFixture); returnDraft.lines['load-1'] = {...lineFixture}; saveReturnDraft();`);
    await t.run(`dbPut(RETURN_QUEUE_STORE, returnKey('route-a'), queueFixture())`);
    t.run(`api = async (url, options = {}) => { calls.push(options.method || 'GET'); if (!options.method) return {context: contextFixture}; throw Object.assign(new Error('Rejected'), {status: ${status}}); };`);
    await assert.rejects(t.run(`flushReturnQueue()`), /Rejected/);
    assert.equal(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a')).then(op => op.server_rejected)`), status);
    assert.ok(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a')).then(op => op.sent_body)`));
    assert.equal(await t.run(`dbGet(RETURN_DRAFT_STORE, returnKey('route-a')).then(draft => draft.lines['load-1'].gross_weight_kg)`), '7');
    const count = t.run(`calls.length`);
    await assert.rejects(t.run(`flushReturnQueue()`), /Rejected/);
    assert.equal(t.run(`calls.length`), count);
    await t.run(`rebaseReturnDraft()`);
    assert.equal(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a'))`), undefined);
    await t.run(`online = false; submitReturn({preventDefault() {}})`);
    assert.notEqual(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a')).then(op => op.payload.operation_id)`), 'op-1');
  }
});

test('5xx response keeps sent bytes immutable and cannot be rebased', async () => {
  const t = app();
  await t.run(`returnContext = contextFixture; returnDraft = draftFromContext(contextFixture); dbPut(RETURN_QUEUE_STORE, returnKey('route-a'), queueFixture())`);
  t.run(`api = async (url, options = {}) => { calls.push(options); if (!options.method) return {context: contextFixture}; throw Object.assign(new Error('Unavailable'), {status: 503}); };`);
  await assert.rejects(t.run(`flushReturnQueue()`), /Unavailable/);
  const bytes = await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a')).then(op => op.sent_body)`);
  assert.equal(t.run(`returnOperation.server_rejected`), undefined);
  await t.run(`rebaseReturnDraft()`);
  assert.equal(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a')).then(op => op.sent_body)`), bytes);
  await assert.rejects(t.run(`flushReturnQueue()`), /Unavailable/);
  assert.equal(t.run(`calls[2].body`), bytes);
});

test('conflicting canonical submitted/accepted document stays read-only and is never removed by rebase', async () => {
  for (const status of ['submitted', 'accepted']) {
    const t = app();
    await t.run(`returnContext = contextFixture; returnDraft = draftFromContext(contextFixture); returnDraft.lines['load-1'] = {...lineFixture}; saveReturnDraft();`);
    await t.run(`dbPut(RETURN_QUEUE_STORE, returnKey('route-a'), queueFixture())`);
    t.run(`globalThis.posted = false; api = async (url, options = {}) => {
      if (options.method) {posted = true; throw Object.assign(new Error('Conflict'), {status: 409});}
      return {context: posted ? {...contextFixture, eligible: false, document: {status: '${status}', revision: 5, lines: []}} : contextFixture};
    };`);
    await assert.rejects(t.run(`flushReturnQueue()`), /Conflict/);
    assert.equal(t.run(`returnContext.document.status`), status);
    t.run(`renderReturn()`);
    assert.ok(!t.element.innerHTML.includes('data-return-rebase'));
    await t.run(`rebaseReturnDraft()`);
    assert.equal(t.run(`returnContext.document.status`), status);
    assert.ok(await t.run(`dbGet(RETURN_QUEUE_STORE, returnKey('route-a'))`));
    assert.ok(await t.run(`dbGet(RETURN_DRAFT_STORE, returnKey('route-a'))`));
  }
});

test('return history and server errors are escaped and accessible through mileage gate', () => {
  const t = app();
  t.run(`mileage = {required: true}; view = 'return'; returnContext = {...contextFixture, route_label: '<img src=x onerror=alert(1)>', document: {status: 'accepted', total_net_kg: '1', lines: [], history: [{kind: 'accepted', at: 'now', actor: '<script>x</script>', comment: '<img onerror=x>'}]}}; returnOperation = {error: '<script>bad</script>'}; render();`);
  assert.ok(t.element.innerHTML.includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert.ok(t.element.innerHTML.includes('&lt;img'));
  assert.ok(!t.element.innerHTML.includes('<script>'));
  assert.ok(!t.element.innerHTML.includes('data-mileage-form'));
});
