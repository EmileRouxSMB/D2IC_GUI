(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.D2ICResultAnalysis = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  // Transport through the same affine T3 / split-Q4 triangles as the viewer.
  function mapMeshPoint(point, source, target) {
    for (const cell of source.elements || []) {
      const triangles = cell.length === 3 ? [cell] : [
        [cell[0], cell[1], cell[2]], [cell[0], cell[2], cell[3]]
      ];
      for (const ids of triangles) {
        const [a, b, c] = ids.map(index => source.nodes_xy[index]);
        const det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
        if (Math.abs(det) < 1e-14) continue;
        const u = ((b[1] - c[1]) * (point[0] - c[0]) + (c[0] - b[0]) * (point[1] - c[1])) / det;
        const v = ((c[1] - a[1]) * (point[0] - c[0]) + (a[0] - c[0]) * (point[1] - c[1])) / det;
        const w = 1 - u - v;
        if (Math.min(u, v, w) >= -1e-9) {
          return [0, 1].map(axis =>
            u * target.nodes_xy[ids[0]][axis] +
            v * target.nodes_xy[ids[1]][axis] +
            w * target.nodes_xy[ids[2]][axis]);
        }
      }
    }
    return null;
  }

  // Inputs are explicit: this module has no DOM, study state or local storage.
  function sectionParameters({points = [], samples, field, frame, scope = 'image'}) {
    samples = Number(samples);
    if (points.length !== 2) {
      throw new Error('Placez les deux extrémités sur le maillage.');
    }
    if (Math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1]) < 1e-9) {
      throw new Error('Les extrémités doivent être distinctes.');
    }
    if (!Number.isInteger(samples) || samples < 2 || samples > 2000) {
      throw new Error('Choisissez entre 2 et 2000 échantillons.');
    }
    return new URLSearchParams({
      field, frame, x0: points[0][0], y0: points[0][1],
      x1: points[1][0], y1: points[1][1], samples, scope
    });
  }

  return {mapMeshPoint, sectionParameters};
});
