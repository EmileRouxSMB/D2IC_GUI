(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.D2ICImageZoom = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));

  function zoomAt(state, factor, px, py) {
    const next = clamp(state.zoom * factor, 1, 64);
    const ratio = next / state.zoom;
    state.tx = px - (px - state.tx) * ratio;
    state.ty = py - (py - state.ty) * ratio;
    state.zoom = next;
    if (next === 1) state.tx = state.ty = 0;
    return state;
  }

  function fitSelection(state, rect, frameWidth, frameHeight) {
    const width = rect.right - rect.left, height = rect.bottom - rect.top;
    if (width < 6 || height < 6 || !frameWidth || !frameHeight) return false;
    const factor = clamp(Math.min(frameWidth / width, frameHeight / height), 1, 64 / state.zoom);
    const cx = (rect.left + rect.right) / 2, cy = (rect.top + rect.bottom) / 2;
    state.tx = frameWidth / 2 - (cx - state.tx) * factor;
    state.ty = frameHeight / 2 - (cy - state.ty) * factor;
    state.zoom *= factor;
    return true;
  }

  function resetState(state) { state.zoom = 1; state.tx = state.ty = 0; return state; }

  function preserveCenterOnResize(state, oldWidth, oldHeight, width, height, imageWidth, imageHeight, contentTop = 0) {
    if (!oldWidth || !oldHeight || !width || !height) return state;
    const oldBox = containBox(oldWidth, oldHeight - contentTop, imageWidth, imageHeight);
    const newBox = containBox(width, height - contentTop, imageWidth, imageHeight);
    if (oldBox) oldBox.top += contentTop;
    if (newBox) newBox.top += contentTop;
    if (!oldBox || !newBox) {
      state.tx *= width / oldWidth; state.ty *= height / oldHeight;
      return state;
    }
    const centerX = (oldWidth / 2 - state.tx) / state.zoom;
    const centerY = ((oldHeight + contentTop) / 2 - state.ty) / state.zoom;
    const imageX = (centerX - oldBox.left) / oldBox.width;
    const imageY = (centerY - oldBox.top) / oldBox.height;
    state.tx = width / 2 - state.zoom * (newBox.left + imageX * newBox.width);
    state.ty = (height + contentTop) / 2 - state.zoom * (newBox.top + imageY * newBox.height);
    return state;
  }

  function containBox(frameWidth, frameHeight, imageWidth, imageHeight) {
    if (!(frameWidth > 0 && frameHeight > 0 && imageWidth > 0 && imageHeight > 0)) return null;
    const scale = Math.min(frameWidth / imageWidth, frameHeight / imageHeight);
    const width = imageWidth * scale, height = imageHeight * scale;
    return { left: (frameWidth - width) / 2, top: (frameHeight - height) / 2, width, height };
  }

  function geometry(frame, image) {
    if (!frame || !image) return null;
    const fw = frame.clientWidth, fh = frame.clientHeight;
    const frameRect = frame.getBoundingClientRect(), imageRect = image.getBoundingClientRect();
    const state = frame.__d2icZoomState || { zoom: 1, tx: 0, ty: 0 };
    // Undo the CSS transform to recover the image element's layout box. Then
    // account for object-fit: contain inside that box (often full-frame).
    const elementLeft = state.zoom ? (imageRect.left - frameRect.left - frame.clientLeft - state.tx) / state.zoom : 0;
    const elementTop = state.zoom ? (imageRect.top - frameRect.top - frame.clientTop - state.ty) / state.zoom : 0;
    const elementWidth = state.zoom ? imageRect.width / state.zoom : 0;
    const elementHeight = state.zoom ? imageRect.height / state.zoom : 0;
    const inner = containBox(elementWidth, elementHeight, image.naturalWidth || image.width, image.naturalHeight || image.height);
    const box = inner && { left: elementLeft + inner.left, top: elementTop + inner.top, width: inner.width, height: inner.height };
    if (!box) return null;
    return {
      left: state.tx + box.left * state.zoom,
      top: state.ty + box.top * state.zoom,
      width: box.width * state.zoom,
      height: box.height * state.zoom,
      right: state.tx + (box.left + box.width) * state.zoom,
      bottom: state.ty + (box.top + box.height) * state.zoom,
      zoom: state.zoom,
    };
  }

  function attach(frame, options) {
    options = options || {};
    if (frame.__d2icZoomController) return frame.__d2icZoomController;
    const doc = frame.ownerDocument;
    const state = frame.__d2icZoomState || (frame.__d2icZoomState = { zoom: 1, tx: 0, ty: 0 });
    const images = Array.from(frame.querySelectorAll('img'));
    const layers = options.layers || images;
    const loadTargets = [...new Set([...images, ...layers])];
    const toolbar = doc.createElement('div');
    toolbar.className = 'd2ic-image-zoom-toolbar';
    toolbar.style.cssText = 'position:absolute;z-index:20;top:8px;right:8px;display:flex;gap:4px;transform:none';
    const toggle = doc.createElement('button'), resetButton = doc.createElement('button');
    const zoomLabel = doc.createElement('span');
    toggle.type = resetButton.type = 'button'; toggle.textContent = 'Zoom'; resetButton.textContent = 'Réinitialiser la vue';
    toggle.title = 'Glisser sur l’image pour zoomer par rectangle';
    toolbar.title = 'Ctrl/Cmd + clic sur l’image pour dézoomer';
    resetButton.title = 'Afficher l’image entière, ajustée à la zone disponible';
    toggle.setAttribute('aria-pressed', options.interactive ? 'false' : 'true');
    zoomLabel.className = 'd2ic-image-zoom-level';
    zoomLabel.style.cssText = 'align-self:center;font-size:11px;padding:0 5px;white-space:nowrap';
    toolbar.append(toggle, zoomLabel, resetButton); frame.appendChild(toolbar);
    const rect = doc.createElement('div');
    rect.className = 'd2ic-image-zoom-selection';
    rect.style.cssText = 'position:absolute;z-index:19;display:none;border:1px solid #4aa3ff;background:#4aa3ff33;pointer-events:none;transform:none';
    frame.appendChild(rect);
    frame.style.overflow = 'hidden';
    if (doc.defaultView.getComputedStyle(frame).position === 'static') frame.style.position = 'relative';
    let active = !options.interactive, dragging = null, destroyed = false, suppressClick = false;
    let previousSize = { width: frame.clientWidth, height: frame.clientHeight };

    function render() {
      const fw = frame.clientWidth, fh = frame.clientHeight;
      for (const img of layers) {
        if (!img || !img.style) continue;
        // Layers are direct children of the positioned frame (or the ROI stack).
        // Read offsets on every render because image dimensions may arrive later.
        const left = img.offsetLeft || 0, top = img.offsetTop || 0;
        img.style.transformOrigin = `${-left}px ${-top}px`;
        img.style.transform = `translate(${state.tx}px, ${state.ty}px) scale(${state.zoom})`;
      }
      toggle.setAttribute('aria-pressed', String(active));
      toggle.classList.toggle('active', active);
      frame.classList.toggle('image-zoom-mode', active);
      zoomLabel.textContent = `Zoom ×${Number(state.zoom.toFixed(2))}`;
      if (options.onChange) options.onChange({ zoom: state.zoom, tx: state.tx, ty: state.ty });
      frame.dispatchEvent(new doc.defaultView.Event('imageviewchange'));
    }
    function updateCursor(event) {
      frame.classList.toggle('image-zoom-out', !!(event.ctrlKey || event.metaKey));
    }
    function clearModifier() { updateCursor({}); }
    function local(event) { const r = frame.getBoundingClientRect(); return { x: event.clientX - r.left - frame.clientLeft, y: event.clientY - r.top - frame.clientTop }; }
    function onDown(event) {
      updateCursor(event);
      if (toolbar.contains(event.target)) { suppressClick = false; return; }
      suppressClick = false;
      if (event.button !== 0) return;
      const raw = local(event), p = { x: clamp(raw.x, 0, frame.clientWidth), y: clamp(raw.y, 0, frame.clientHeight) };
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault(); event.stopImmediatePropagation(); suppressClick = true; zoomAt(state, .5, p.x, p.y); render(); return;
      }
      if (!active) return;
      event.preventDefault(); event.stopImmediatePropagation();
      suppressClick = true;
      dragging = { x: p.x, y: p.y };
      rect.style.display = 'block'; rect.style.left = `${p.x}px`; rect.style.top = `${p.y}px`; rect.style.width = '0'; rect.style.height = '0';
      frame.setPointerCapture?.(event.pointerId);
    }
    function onMove(event) {
      updateCursor(event);
      if (!dragging) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const raw = local(event), p = { x: clamp(raw.x, 0, frame.clientWidth), y: clamp(raw.y, 0, frame.clientHeight) };
      const x = Math.min(p.x, dragging.x), y = Math.min(p.y, dragging.y);
      rect.style.left = `${x}px`; rect.style.top = `${y}px`;
      rect.style.width = `${Math.abs(p.x - dragging.x)}px`; rect.style.height = `${Math.abs(p.y - dragging.y)}px`;
    }
    function onUp(event) {
      if (!dragging) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const raw = local(event), p = { x: clamp(raw.x, 0, frame.clientWidth), y: clamp(raw.y, 0, frame.clientHeight) };
      const start = dragging; dragging = null; rect.style.display = 'none';
      if (frame.hasPointerCapture?.(event.pointerId)) frame.releasePointerCapture(event.pointerId);
      if (event.type === 'pointercancel') { suppressClick = false; return; }
      if (Math.abs(p.x - start.x) < 6 && Math.abs(p.y - start.y) < 6) {
        zoomAt(state, 2, p.x, p.y); render(); return;
      }
      if (fitSelection(state, { left: Math.min(start.x, p.x), right: Math.max(start.x, p.x), top: Math.min(start.y, p.y), bottom: Math.max(start.y, p.y) }, frame.clientWidth, frame.clientHeight)) render();
    }
    function onToggle() { active = !active; render(); }
    function onClick(event) {
      if (toolbar.contains(event.target)) return;
      if (suppressClick) {
        event.preventDefault(); event.stopImmediatePropagation(); suppressClick = false;
      }
    }
    function onLoad() { render(); }
    function onResize() {
      const width = frame.clientWidth, height = frame.clientHeight;
      if (state.zoom === 1) {
        resetState(state);
      } else if (previousSize.width && previousSize.height) {
        const image = layers.find(layer => layer?.naturalWidth) || frame.querySelector('img');
        if (image && image.naturalWidth && image.naturalHeight) {
          preserveCenterOnResize(state, previousSize.width, previousSize.height, width, height, image.naturalWidth, image.naturalHeight, layers[0]?.offsetTop || 0);
        } else { state.tx *= width / previousSize.width; state.ty *= height / previousSize.height; }
      }
      previousSize = { width, height }; render();
    }
    function reset() { resetState(state); render(); }
    // Keyboard events update the cursor even when the pointer stays still.
    doc.addEventListener('keydown', updateCursor, true);
    doc.addEventListener('keyup', updateCursor, true);
    doc.defaultView.addEventListener('blur', clearModifier);
    frame.addEventListener('pointerenter', updateCursor);
    frame.addEventListener('pointerdown', onDown, true);
    frame.addEventListener('pointermove', onMove, true);
    frame.addEventListener('pointerup', onUp, true);
    frame.addEventListener('pointercancel', onUp, true);
    frame.addEventListener('click', onClick, true);
    toggle.addEventListener('click', onToggle); resetButton.addEventListener('click', reset);
    toolbar.addEventListener('click', event => event.stopPropagation());
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(onResize) : null;
    observer?.observe(frame);
    for (const target of loadTargets) target.addEventListener('load', onLoad);
    const controller = { reset, setInteractive(value) { active = !!value; render(); }, destroy() {
      if (destroyed) return; destroyed = true; observer?.disconnect();
      frame.removeEventListener('pointerdown', onDown, true); frame.removeEventListener('pointermove', onMove, true);
      frame.removeEventListener('pointerup', onUp, true); frame.removeEventListener('pointercancel', onUp, true);
      frame.removeEventListener('click', onClick, true);
      frame.removeEventListener('pointerenter', updateCursor);
      doc.removeEventListener('keydown', updateCursor, true);
      doc.removeEventListener('keyup', updateCursor, true);
      doc.defaultView.removeEventListener('blur', clearModifier);
      for (const target of loadTargets) target.removeEventListener('load', onLoad);
      toolbar.remove(); rect.remove(); delete frame.__d2icZoomController;
      frame.classList.remove('image-zoom-mode', 'image-zoom-out');
    } };
    controller.cleanup = controller.destroy;
    frame.__d2icZoomController = controller;
    render();
    return controller;
  }

  return { attach, geometry, _math: { zoomAt, fitSelection, containBox, resetState, preserveCenterOnResize } };
});
