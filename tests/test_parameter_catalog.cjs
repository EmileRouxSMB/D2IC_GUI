const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/D2IC_GUI/static/app.js'), 'utf8');
const controls = source.slice(source.indexOf('  function controlFor('), source.indexOf('  let seriesRequestId'));
const context = { state: {config: {project: {mode: 'dic'}}}, htmlEscape: x => String(x ?? '') };
vm.createContext(context);
vm.runInContext(controls, context);

test('new catalogue fields choose controls by explicit type', () => {
  const control = (type, extra = {}, value = '') => context.controlFor('custom.added', {type, ...extra}, value);
  assert.match(control('integer', {}, 2), /step="1"/);
  assert.match(control('float', {minimum: 0}, 0.5), /step="any"/);
  assert.match(control('boolean', {}, true), /type="checkbox".*checked/);
  assert.match(control('directory', {}, '/tmp'), /type="text"/);
  assert.match(control('string', {choices: ['a', 'b']}, 'b'), /value="b" selected/);
  assert.match(control('array', {choices: ['VIS', 'TH']}, ['TH']), /multiple.*value="TH" selected/);
  assert.match(control('boolean', {readonly: true}, true), /disabled/);
});

test('catalogue controls location including newly added ROI fields', () => {
  assert.equal(context.fieldView('custom.added', {view: 'ROI'}), 'ROI');
  assert.equal(context.fieldView('custom.added', {view: 'Export', hidden: true}), null);
  const cadence = {view: 'Synchro', view_dic: 'Réglages DIC'};
  assert.equal(context.fieldView('time.visible_fps', cadence), 'Réglages DIC');
  context.state.config.project.mode = 'dic_thermal';
  assert.equal(context.fieldView('time.visible_fps', cadence), 'Synchro');
});

test('form values preserve numbers, booleans and multiple choices', () => {
  assert.equal(context.readControl({value: '0.25'}, {type: 'float'}), 0.25);
  assert.equal(context.readControl({checked: false}, {type: 'boolean'}), false);
  assert.equal(JSON.stringify(context.readControl({value: '[[1,2],[3,4]]'}, {type: 'array'})), '[[1,2],[3,4]]');
  assert.equal(JSON.stringify(context.readControl({multiple: true, selectedOptions: [{value: 'VIS'}, {value: 'TH'}]}, {type: 'array'})), '["VIS","TH"]');
});
