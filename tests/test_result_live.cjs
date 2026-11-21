const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const start = source.indexOf('  async function refreshRunResults(');
const end = source.indexOf('  let runListTimer=', start);
const refresh = source.slice(start, end);

function option(value) { return {value, textContent: ''}; }
function select(value, options = []) {
  return {value, options, replaceChildren(...next) { this.options = next; }};
}

test('live result refresh appends committed frames and thermal fields without losing selections', async () => {
  const fields = select('u1', [option('u1')]);
  const frames = {value: '1', max: '1'};
  const history = select('u1', [option('u1')]);
  const nodes = {'#run-field': fields, '#run-frame': frames, '#history-field': history,
    '#run-fields': {dataset: {}}};
  const cache = new Map([['live-run:4', []]]);
  let rendered, historyRefresh, scheduled, cleared = false;
  const context = {
    state: {view: 'Résultats', selectedRun: 'live-run', projectKey: 'study'},
    resultMetadata: {state: 'running', completed_frames: 1, total_frames: 3,
      times_s: [0, 0.1], fields: ['u1']},
    resultDisplay: {cache: {clear() { cleared = true; }}, historyFields: ['u1']},
    historyCache: cache,
    $: selector => nodes[selector],
    api: async () => ({state: 'running', completed_frames: 2, total_frames: 3,
      times_s: [0, 0.1, 0.2], fields: ['u1', 'Temperature']}),
    fieldLabel: field => field,
    document: {createElement: () => option('')},
    renderResultRunStatus: () => {},
    renderRunField: (id, metadata) => { rendered = [id, metadata]; },
    updateAnalysisGraphs: id => { historyRefresh = [id, history.value]; },
    scheduleResultRefresh: id => { scheduled = id; },
    historyRequest: 0
  };
  vm.createContext(context);
  vm.runInContext(refresh, context);
  await context.refreshRunResults('live-run');

  assert.equal(fields.value, 'u1');
  assert.equal(frames.max, '2');
  assert.equal(frames.value, '1');
  assert.deepEqual(Array.from(history.options, item => item.value), ['u1', 'Temperature']);
  assert.deepEqual(Array.from(context.resultDisplay.historyFields), ['u1', 'Temperature']);
  assert.equal(cache.size, 0);
  assert.equal(cleared, true);
  assert.equal(rendered[0], 'live-run');
  assert.deepEqual(Array.from(rendered[1].times_s), [0, 0.1, 0.2]);
  assert.deepEqual(historyRefresh, ['live-run', 'u1']);
  assert.equal(scheduled, 'live-run');
});
