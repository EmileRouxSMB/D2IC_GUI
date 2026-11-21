// Exercise the launch boundary with asynchronous reports and API calls.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const launch = source.slice(source.indexOf('  async function prepareRun('), source.indexOf('  function renderRunSummary'));
function harness(report) {
  const calls = [], nodes = {'#run-status': {}, '#config-message': {textContent: 'Invalid settings'}};
  const context = {
    launching: false, preparingRun: false, readiness: report, state: {dirty: true, config: {}},
    $: selector => nodes[selector],
    applyReadiness: () => {},
    save: async () => { calls.push(['save']); return true; },
    api: async (path, options) => { calls.push(['post', path, options]); return {id: 'run-1'}; },
    rememberRun: id => calls.push(['selected', id]), populateRuns: () => {},
    notify: (...args) => calls.push(['notice', ...args])
  };
  vm.createContext(context); vm.runInContext(launch, context);
  return {context, calls};
}
test('preparation creates a job even when mandatory prerequisites are missing', async () => {
  const {context, calls} = harness({ready: false, required: [{view: 'ROI'}], optional: []});
  await context.prepareRun();
  assert.deepEqual(calls.map(c => c[0]), ['save', 'post', 'selected']);
  assert.equal(calls[1][1], '/api/runs/prepare');
  assert.equal(context.preparingRun, false);
});
test('launch uses the individual start route', async () => {
  const {context, calls} = harness({ready: true, required: [], optional: []});
  await context.launchRun('run-1');
  assert.deepEqual(calls.map(c => c[0]), ['post', 'selected']);
  assert.equal(calls[0][1], '/api/runs/run-1/start');
});
test('a failed save prevents preparation', async () => {
  const {context, calls} = harness(null);
  context.save = async () => false;
  await context.prepareRun();
  assert.equal(calls.some(c => c[1] === '/api/runs/prepare'), false);
});
test('a double click during preparation creates one job', async () => {
  const report = {ready: false, required: []};
  const {context, calls} = harness(report);
  let complete;
  context.api = path => { calls.push(['post', path]); return new Promise(resolve => { complete = resolve; }); };
  const first = context.prepareRun();
  await context.prepareRun();
  complete({id:'run-1'}); await first;
  assert.equal(calls.filter(c => c[1] === '/api/runs/prepare').length, 1);
});
test('server refusal leaves the prepared job unlaunched', async () => {
  const {context, calls} = harness({ready: true, optional: []});
  context.api = async () => { throw new Error('Maillage périmé'); };
  await context.launchRun('run-1');
  assert.equal(calls.some(c => c[1] === '/api/runs/run-1/start'), false);
  assert.equal(context.launching, false);
});

test('Job Manager renders escaped required and optional messages and gates start on can_start', () => {
  assert.match(source, /data-run-start \$\{run\.can_start\?'':'disabled'\}/);
  assert.match(source, /id="prepare-run">Préparer le job/);
  assert.match(source, /\/api\/runs\/prepare/);
  assert.match(source, /\/start/);
  const renderSource = source.slice(source.indexOf('  function renderRunPreparation('), source.indexOf('  async function populateRuns('));
  const context = {htmlEscape: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')};
  vm.createContext(context); vm.runInContext(renderSource, context);
  const html = context.renderRunPreparation({preparation: {
    required: [{view:'ROI', message:'<mask>'}], optional: [{view:'Échelle', message:'incertain'}]
  }, error:'<mask>'});
  assert.match(html, /Erreur · ROI : &lt;mask&gt;/);
  assert.match(html, /Avertissement · Échelle : incertain/);
  assert.equal((html.match(/&lt;mask&gt;/g)||[]).length, 1);
  assert.match(context.renderRunPreparation({error:'<runtime>'}), /&lt;runtime&gt;/);
});

test('readiness no longer disables job preparation', () => {
  const nodes = {'#prepare-run': {}};
  const context = {
    readiness: null, launching: false,
    document: {querySelectorAll: () => []},
    $: selector => nodes[selector]
  };
  vm.createContext(context);
  vm.runInContext('let preparingRun = false;\n' + source.slice(source.indexOf('  function applyReadiness('), source.indexOf('  function scheduleReadiness(')), context);
  context.applyReadiness({ready: false, required: [{view: 'ROI', message: 'Binning modifié ; cliquer sur Mailler'}]});
  assert.equal(nodes['#prepare-run'].disabled, false);
  vm.runInContext('preparingRun = true; applyReadiness({ready: true, required: []});', context);
  assert.equal(nodes['#prepare-run'].disabled, true);
});
