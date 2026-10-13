const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../assets/theme-preference.js'), 'utf8');
function load(stored = {}, dark = false, unavailable = false) {
  const listeners = {}, documentListeners = {}, systemListeners = {}, classes = new Set();
  const storage = {...stored}, writes = [], events = [];
  const control = {value: ''};
  const choices = ['light', 'dark'].map(themeChoice => ({dataset: {themeChoice}, setAttribute(name, value) {this[name] = value;}}));
  const html = {dataset: {}, style: {}, classList: {toggle(name, active) { if (active) classes.add(name); else classes.delete(name); }}};
  const meta = {setAttribute: (name, value) => { meta[name] = value; }};
  const media = {matches: dark, addEventListener: (name, fn) => {systemListeners[name] = fn;}};
  const window = {matchMedia: () => media, addEventListener: (name, fn) => {listeners[name] = fn;}, dispatchEvent: event => {events.push(event);}};
  vm.runInNewContext(source, {
    window, document: {documentElement: html, querySelectorAll: selector => selector.includes('meta') ? [meta] : selector === '.radix-themes' ? [html] : selector === '[data-theme-choice]' ? choices : [control], addEventListener: (name, fn) => {documentListeners[name] = fn;}},
    localStorage: {getItem: key => {if (unavailable) throw Error('denied'); return storage[key] ?? null;}, setItem: (key, value) => {if (unavailable) throw Error('denied'); storage[key] = value; writes.push([key,value]);}},
    CustomEvent: class {constructor(name, options) {this.type=name; this.detail=options.detail;}},
    MutationObserver: class {observe() {}},
  });
  return {window, html, control, choices, meta, media, storage, writes, listeners, documentListeners, systemListeners, events};
}
test('system is the default and follows device changes', () => {
  const app=load({}, true);
  assert.equal(app.window.LogisticsTheme.getPreference(),'system');
  assert.equal(app.html.dataset.theme,'dark');
  app.media.matches=false; app.systemListeners.change();
  assert.equal(app.html.dataset.theme,'light');
  assert.equal(app.meta.content,'#ffffff');
});
test('explicit preference persists without touching form or network state', () => {
  const app=load();
  app.documentListeners.change({target:{value:'dark',matches:()=>true}});
  assert.equal(app.html.dataset.theme,'dark');
  assert.equal(app.storage['logistics-theme'],'dark');
  assert.equal(app.control.value,'dark');
  assert.equal(app.html.style.colorScheme,'dark');
  app.media.matches=false; app.systemListeners.change();
  assert.equal(app.html.dataset.theme,'dark');
  app.window.LogisticsTheme.setPreference('invalid');
  assert.equal(app.window.LogisticsTheme.getPreference(),'dark');
});
test('legacy driver preference migrates and new preference takes priority', () => {
  assert.equal(load({'driver-theme':'dark'}).html.dataset.theme,'dark');
  assert.equal(load({'driver-theme':'dark','logistics-theme':'light'}).html.dataset.theme,'light');
});
test('storage restrictions do not prevent switching', () => {
  const app=load({},true,true);
  app.window.LogisticsTheme.setPreference('light');
  assert.equal(app.html.dataset.theme,'light');
});
test('other tabs and preference removal sync the system theme', () => {
  const app=load({'logistics-theme':'dark'});
  app.listeners.storage({key:'logistics-theme',newValue:'light'});
  assert.equal(app.html.dataset.theme,'light');
  app.listeners.storage({key:'logistics-theme',newValue:null});
  assert.equal(app.window.LogisticsTheme.getPreference(),'system');
});

test('theme buttons share persisted preference and expose the effective selection', () => {
  const app = load({}, true);
  assert.equal(app.choices[1]['aria-pressed'], 'true');
  app.documentListeners.click({target: {closest: () => app.choices[0]}});
  assert.equal(app.storage['logistics-theme'], 'light');
  assert.equal(app.control.value, 'light');
  assert.equal(app.choices[0]['aria-pressed'], 'true');
  assert.equal(app.choices[1]['aria-pressed'], 'false');
});
