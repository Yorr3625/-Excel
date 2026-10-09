const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function environment() {
  const listeners = {};
  const classes = new Set();
  const target = {
    classList: {add: value => classes.add(value), remove: value => classes.delete(value)},
    contains: () => false,
  };
  const context = {
    window: {},
    document: {
      addEventListener: (name, fn) => { listeners[name] = fn; },
      querySelectorAll: () => [target],
    },
  };
  const code = fs.readFileSync(path.join(__dirname, '../assets/route-template-dnd.js'), 'utf8');
  vm.runInNewContext(code, context);
  return {listeners, classes, target, context, code};
}

test('drag handle carries the exact source and name, drop clears visual state', () => {
  const env = environment();
  let payload;
  const transfer = {setData: (type, value) => { assert.equal(type, 'text/plain'); payload = value; }};
  const handle = {dataset: {source: '2', name: 'Магазин «А»'}};
  env.listeners.dragstart({target: {closest: () => handle}, dataTransfer: transfer});
  assert.deepEqual(JSON.parse(payload), {source: 2, name: 'Магазин «А»'});
  assert.equal(transfer.effectAllowed, 'move');
  let prevented = 0;
  const event = {target: {closest: () => env.target}, dataTransfer: transfer, preventDefault: () => prevented++};
  env.listeners.dragover(event);
  assert.equal(prevented, 1);
  assert.equal(transfer.dropEffect, 'move');
  assert.ok(env.classes.has('is-drop-target'));
  env.listeners.drop(event);
  assert.equal(prevented, 2);
  assert.ok(!env.classes.has('is-drop-target'));
});

test('unrelated drags are not captured and bootstrap is idempotent', () => {
  const env = environment();
  let prevented = false;
  env.listeners.dragover({target: {closest: () => env.target}, preventDefault: () => { prevented = true; }});
  assert.equal(prevented, false);
  const before = {...env.listeners};
  vm.runInNewContext(env.code, env.context);
  assert.deepEqual(env.listeners, before);
});

test('cancelled drag clears target highlights', () => {
  const env = environment();
  env.classes.add('is-drop-target');
  env.listeners.dragend();
  assert.equal(env.classes.size, 0);
});
