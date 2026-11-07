(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.D2ICROIShapes = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  function imagePoint(x, y, box, width, height) {
    if (!box || !width || !height) return null;
    return [Math.max(0, Math.min(width - 1, (x - box.left) * width / box.width)),
            Math.max(0, Math.min(height - 1, (y - box.top) * height / box.height))];
  }

  function makeShape(kind, operation, first, last) {
    if (!first || !last) return null;
    if (Math.abs(last[0] - first[0]) < 1 || Math.abs(last[1] - first[1]) < 1) return null;
    return { kind, operation, x0: Math.min(first[0], last[0]), y0: Math.min(first[1], last[1]),
             x1: Math.max(first[0], last[0]), y1: Math.max(first[1], last[1]) };
  }

  function attach(frame, image, canvas, { geometry, draft, changed }) {
    const ctx = canvas.getContext('2d');
    let tool = null, operation = 'add', drag = null;
    function point(event) {
      const rect = frame.getBoundingClientRect();
      return imagePoint(event.clientX - rect.left - frame.clientLeft,
                        event.clientY - rect.top - frame.clientTop,
                        geometry(frame, image), image.naturalWidth, image.naturalHeight);
    }
    function draw() {
      const ratio = frame.ownerDocument.defaultView.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(frame.clientWidth * ratio));
      canvas.height = Math.max(1, Math.round(frame.clientHeight * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const box = geometry(frame, image);
      if (!box || !draft.active || !drag) return;
      const shape = makeShape(tool, operation, drag.first, drag.last);
      if (!shape) return;
      const x = box.left + shape.x0 * box.width / image.naturalWidth;
      const y = box.top + shape.y0 * box.height / image.naturalHeight;
      const w = (shape.x1 - shape.x0) * box.width / image.naturalWidth;
      const h = (shape.y1 - shape.y0) * box.height / image.naturalHeight;
      ctx.strokeStyle = operation === 'subtract' ? '#d95440' : '#f7a735';
      ctx.fillStyle = operation === 'subtract' ? '#d9544022' : '#f7a73522';
      ctx.lineWidth = 2;
      ctx.beginPath();
      if (tool === 'ellipse') ctx.ellipse(x + w/2, y + h/2, w/2, h/2, 0, 0, Math.PI * 2);
      else ctx.rect(x, y, w, h);
      ctx.fill(); ctx.stroke();
    }
    function down(event) {
      if (!tool || !draft.active || event.button !== 0 || event.ctrlKey || event.metaKey ||
          frame.classList.contains('image-zoom-mode')) return;
      const box = geometry(frame, image), r = frame.getBoundingClientRect();
      const x = event.clientX - r.left - frame.clientLeft, y = event.clientY - r.top - frame.clientTop;
      if (!box || x < box.left || x > box.left + box.width || y < box.top || y > box.top + box.height) return;
      const first = point(event); if (!first) return;
      drag = { first, last: first, pointer: event.pointerId };
      canvas.setPointerCapture(event.pointerId);
      event.preventDefault(); draw();
    }
    function move(event) {
      if (!drag || drag.pointer !== event.pointerId) return;
      drag.last = point(event);
      event.preventDefault(); draw();
    }
    function finish(event) {
      if (!drag || drag.pointer !== event.pointerId) return;
      const current = drag;
      drag = null;
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      if (event.type !== 'pointercancel') {
        const shape = makeShape(tool, operation, current.first, point(event));
        if (shape) { draft.shapes.push(shape); changed(); }
      }
      draw();
    }
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
    frame.addEventListener('imageviewchange', draw);
    image.addEventListener('load', draw);
    const observer = new ResizeObserver(draw);
    observer.observe(frame);
    draw();
    return {
      setTool(kind, mode = operation) { tool = kind; operation = mode; drag = null; canvas.style.pointerEvents = kind ? 'auto' : 'none'; draw(); },
      undo() { draft.shapes.pop(); changed(); draw(); },
      clear() { draft.shapes.length = 0; changed(); draw(); },
      destroy() {
        observer.disconnect();
        canvas.removeEventListener('pointerdown', down); canvas.removeEventListener('pointermove', move);
        canvas.removeEventListener('pointerup', finish); canvas.removeEventListener('pointercancel', finish);
        frame.removeEventListener('imageviewchange', draw); image.removeEventListener('load', draw);
      }
    };
  }
  return { attach, imagePoint, makeShape };
});
