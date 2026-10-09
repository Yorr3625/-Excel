const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = require('node:fs').readFileSync(require('node:path').join(__dirname, '../assets/workspace-bootstrap.js'), 'utf8');

function app(path, mounted = false) {
  const scripts = [], timers = [], events = {};
  let observer, root = mounted ? {firstElementChild: null, textContent: '', setAttribute(name, value) {this[name] = value;}} : null;
  let renders = 0;
  const window = {
    location: {pathname: path},
    addEventListener(name, handler) {events[name] = handler;},
    setTimeout(handler) {timers.push(handler);},
    render() {renders++; root.firstElementChild = {};},
  };
  const sandbox = {
    window,
    document: {
      readyState: 'loading', documentElement: {},
      body: {appendChild(script) {scripts.push(script);}},
      getElementById() {return root;}, createElement() {return {};},
    },
    MutationObserver: class {constructor(callback) {observer = callback;} observe() {}},
  };
  vm.runInNewContext(source, sandbox);
  function runTimers() {
    for (let attempt = 0; timers.length && attempt < 20; attempt++) timers.shift()();
    assert.equal(timers.length, 0, 'mounting should settle');
  }
  return {
    scripts, events, window, sandbox, runTimers,
    get root() {return root;}, get renders() {return renders;},
    showRoot() {root = {firstElementChild: null, textContent: '', setAttribute(name, value) {this[name] = value;}}; observer?.();},
    replaceRoot() {root = {firstElementChild: null, textContent: '', setAttribute(name, value) {this[name] = value;}}; observer?.();},
    notifyMutation() {observer?.();},
  };
}

test('driver and loader mount only after the page loads, once per cabinet', () => {
  for (const [route, src] of [['/driver/', '/driver-app.js'], ['/loader/', '/loader-app.js']]) {
    const a = app(route, true);
    assert.equal(a.scripts.length, 0);
    a.events.load(); a.runTimers();
    assert.equal(a.scripts.length, 1);
    assert.equal(a.scripts[0].src, src);
    vm.runInNewContext(source, a.sandbox); // Reflex can include the head script twice.
    a.notifyMutation(); a.runTimers();
    assert.equal(a.scripts.length, 1);
  }
});

test('late Reflex hydration restores an empty root without reloading the script', () => {
  const a = app('/driver');
  a.events.load(); a.runTimers();
  assert.equal(a.scripts.length, 0);
  a.showRoot(); a.runTimers();
  assert.equal(a.scripts.length, 1);
  a.scripts[0].onload(); a.runTimers();
  assert.equal(a.renders, 1);
  a.replaceRoot(); a.runTimers();
  assert.equal(a.renders, 2);
  assert.equal(a.scripts.length, 1);
});

test('administrative pages do not load cabinet scripts', () => {
  const a = app('/', true);
  assert.equal(a.events.load, undefined);
  assert.equal(a.scripts.length, 0);
});

test('failed script load exposes a readable alert', () => {
  const a = app('/driver', true);
  a.events.load(); a.runTimers();
  a.scripts[0].onerror();
  assert.equal(a.root.role, 'alert');
  assert.ok(a.root.textContent);
});
