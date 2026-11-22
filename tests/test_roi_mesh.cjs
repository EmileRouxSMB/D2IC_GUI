const test = require('node:test');
const assert = require('node:assert/strict');
const { transform } = require('../src/D2IC_GUI/static/roi_mesh.js');
const { _math } = require('../src/D2IC_GUI/static/image_zoom.js');

test('native mesh edges map to the VIS contain box at every zoom', () => {
  for (const [fw, fh, iw, ih] of [[800, 600, 1920, 1200], [390, 600, 900, 1600]]) {
    const fit = _math.containBox(fw, fh, iw, ih);
    for (const zoom of [1, 2, 16, 64]) {
      const box = { left: -30 + fit.left * zoom, top: -20 + fit.top * zoom,
        width: fit.width * zoom, height: fit.height * zoom };
      const values = transform(box, iw, ih).match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/g).map(Number);
      const [tx, ty, sx, sy] = values;
      assert.ok(Math.abs(sx - sy) < 1e-12);
      assert.ok(Math.abs(tx + iw * sx - (box.left + box.width)) < 1e-9);
      assert.ok(Math.abs(ty + ih * sy - (box.top + box.height)) < 1e-9);
    }
  }
});
