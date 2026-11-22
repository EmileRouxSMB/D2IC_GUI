const test = require('node:test');
const assert = require('node:assert/strict');
const {imagePoint, makeShape} = require('../src/D2IC_GUI/static/roi_shapes.js');

test('drawing coordinates stay in original image pixels after a zoom and translation', () => {
  const box = {left: -100, top: -50, width: 800, height: 400};
  assert.deepEqual(imagePoint(250, 150, box, 400, 200), [175, 100]);
  assert.deepEqual(imagePoint(100, 50, {left: 0, top: 0, width: 400, height: 200}, 400, 200), [100, 50]);
});

test('coordinates are clamped to image pixel centers at the native boundaries', () => {
  const box = {left: 10, top: 20, width: 100, height: 80};
  assert.deepEqual(imagePoint(-10, -10, box, 100, 80), [0, 0]);
  assert.deepEqual(imagePoint(200, 200, box, 100, 80), [99, 79]);
});

test('backward drags normalize bounds and preserve shape and subtraction mode', () => {
  assert.deepEqual(makeShape('ellipse', 'subtract', [60, 70], [20, 30]),
    {kind: 'ellipse', operation: 'subtract', x0: 20, y0: 30, x1: 60, y1: 70});
});

test('clicks and missing image geometry do not create zero area shapes', () => {
  assert.equal(imagePoint(0, 0, null, 100, 80), null);
  assert.equal(makeShape('rectangle', 'add', [10, 10], [10, 50]), null);
  assert.equal(makeShape('rectangle', 'add', [10, 10], null), null);
});
