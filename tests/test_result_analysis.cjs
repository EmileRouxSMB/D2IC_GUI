const test = require('node:test');
const assert = require('node:assert/strict');
const {mapMeshPoint, sectionParameters} = require('../static/result_analysis.js');

test('section click maps deformed pixels back to material coordinates', () => {
  const reference = {nodes_xy: [[0, 0], [4, 0], [4, 3], [0, 3]], elements: [[0, 1, 2, 3]]};
  const current = {...reference, nodes_xy: reference.nodes_xy.map(([x, y]) => [2*x + y + 7, 3*y - 2])};
  for (const point of [[1, 1], [3, 2], [0, 0], [4, 3]]) {
    const deformed = mapMeshPoint(point, reference, current);
    const recovered = mapMeshPoint(deformed, current, reference);
    assert.ok(Math.hypot(recovered[0] - point[0], recovered[1] - point[1]) < 1e-10);
  }
  assert.equal(mapMeshPoint([50, 50], current, reference), null);
});

test('degenerate triangles are skipped without hiding subsequent valid cells', () => {
  const mesh = {nodes_xy: [[0, 0], [1, 0], [2, 0], [0, 2]], elements: [[0, 1, 2], [0, 2, 3]]};
  assert.deepEqual(mapMeshPoint([0.5, 0.5], mesh, mesh), [0.5, 0.5]);
  assert.equal(mapMeshPoint([3, 3], mesh, mesh), null);
});

test('section parameters retain reference endpoints and validate sampling', () => {
  const inputs = {points: [[1, 2], [4, 6]], samples: '5', field: 'u1', frame: '2'};
  const params = sectionParameters({...inputs, scope: 'sequence'});
  assert.equal(params.get('scope'), 'sequence');
  assert.equal(params.get('frame'), '2');
  assert.equal(params.get('x0'), '1');
  assert.equal(params.get('y1'), '6');
  assert.equal(params.get('samples'), '5');
  assert.equal(sectionParameters(inputs).get('scope'), 'image');
  assert.throws(() => sectionParameters({...inputs, points: []}), /extrémités/);
  assert.throws(() => sectionParameters({...inputs, samples: '1.5'}), /échantillons/);
  assert.throws(() => sectionParameters({...inputs, points: [[1, 2], [1, 2]]}), /distinctes/);
});
