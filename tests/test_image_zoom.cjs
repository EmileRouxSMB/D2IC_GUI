const test = require('node:test');
const assert = require('node:assert/strict');
const { attach, _math, geometry } = require('../src/D2IC_GUI/static/image_zoom.js');

test('rectangle zoom fits selection and preserves aspect ratio', () => {
  const state = { zoom: 1, tx: 0, ty: 0 };
  assert.equal(_math.fitSelection(state, { left: 100, top: 50, right: 300, bottom: 150 }, 800, 400), true);
  assert.equal(state.zoom, 4);
  assert.equal(state.tx, -400);
  assert.equal(state.ty, -200);
});

test('small rectangle is ignored', () => {
  const state = { zoom: 1, tx: 0, ty: 0 };
  assert.equal(_math.fitSelection(state, { left: 1, top: 2, right: 6, bottom: 20 }, 800, 400), false);
  assert.deepEqual(state, { zoom: 1, tx: 0, ty: 0 });
});

test('pointer centered factor-two zoom out keeps the pointed image location fixed', () => {
  const state = { zoom: 4, tx: -180, ty: -90 };
  const point = { x: 200, y: 100 };
  const before = { x: (point.x - state.tx) / state.zoom, y: (point.y - state.ty) / state.zoom };
  _math.zoomAt(state, 0.5, point.x, point.y);
  assert.equal(state.zoom, 2);
  assert.equal((point.x - state.tx) / state.zoom, before.x);
  assert.equal((point.y - state.ty) / state.zoom, before.y);
});

test('reset restores the original view and zoom stays within limits', () => {
  const state = { zoom: 64, tx: 1000, ty: -500 };
  _math.zoomAt(state, 2, 10, 10);
  assert.equal(state.zoom, 64);
  _math.zoomAt(state, 0.001, 10, 10);
  assert.equal(state.zoom, 1);
  assert.deepEqual(_math.resetState(state), { zoom: 1, tx: 0, ty: 0 });
});

test('object-fit contain centers the rendered image without changing its aspect ratio', () => {
  assert.deepEqual(_math.containBox(400, 200, 100, 100), { left: 100, top: 0, width: 200, height: 200 });
  assert.equal(_math.containBox(0, 200, 100, 100), null);
});

test('resize preserves the same center point in image coordinates when aspect ratio changes', () => {
  const state = { zoom: 2, tx: -100, ty: -40 };
  _math.preserveCenterOnResize(state, 400, 200, 200, 400, 400, 200);
  const nextBox = _math.containBox(200, 400, 400, 200);
  const imageCenterX = ((100 - state.tx) / state.zoom - nextBox.left) / nextBox.width;
  const imageCenterY = ((200 - state.ty) / state.zoom - nextBox.top) / nextBox.height;
  assert.ok(Math.abs(imageCenterX - 0.375) < 1e-12);
  assert.ok(Math.abs(imageCenterY - 0.35) < 1e-12);
});

test('zoom cursor follows Ctrl/Cmd, and drag/Ctrl-click consume image-tool clicks', () => {
  class Element {
    constructor(doc) { this.ownerDocument = doc; this.style = {}; this.listeners = {}; this.children = []; this.clientWidth = 400; this.clientHeight = 200; this.clientLeft = this.clientTop = 0; this.classes = new Set(); this.classList = { toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name), remove: (...names) => names.forEach(name => this.classes.delete(name)) }; }
    appendChild(child) { this.children.push(child); child.parent = this; }
    append(...children) { children.forEach(child => this.appendChild(child)); }
    remove() { this.parent.children = this.parent.children.filter(item => item !== this); }
    contains(target) { return target === this || this.children.some(child => child.contains(target)); }
    addEventListener(name, fn, capture) { (this.listeners[name] ||= []).push({ fn, capture }); }
    removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(item => item.fn !== fn); }
    setAttribute() {}
    querySelectorAll() { return []; }
    querySelector() { return null; }
    getBoundingClientRect() { return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight }; }
    dispatch(name, event) { for (const { fn } of this.listeners[name] || []) fn(event); }
    dispatchEvent() { return true; }
  }
  const doc = { addEventListener() {}, removeEventListener() {}, createElement() { return new Element(doc); }, defaultView: { addEventListener() {}, removeEventListener() {}, Event: class { constructor(type) { this.type = type; } }, getComputedStyle() { return { position: 'absolute' }; } } };
  for (const target of [doc, doc.defaultView]) {
    target.listeners = {};
    target.addEventListener = Element.prototype.addEventListener;
    target.removeEventListener = Element.prototype.removeEventListener;
    target.dispatch = Element.prototype.dispatch;
  }
  const frame = new Element(doc); frame.ownerDocument = doc;
  let consumed = 0;
  const event = (x, y, extra = {}) => ({ clientX: x, clientY: y, button: 0, pointerId: 1, target: frame, preventDefault() {}, stopImmediatePropagation() { consumed++; }, ...extra });
  const controller = attach(frame);
  const isZoomOut = () => frame.classes.has('image-zoom-out');
  assert.equal(isZoomOut(), false);
  doc.dispatch('keydown', { ctrlKey: true });
  assert.equal(isZoomOut(), true); // no pointer movement required
  doc.dispatch('keyup', { ctrlKey: false });
  assert.equal(isZoomOut(), false);
  doc.dispatch('keydown', { metaKey: true });
  assert.equal(isZoomOut(), true);
  doc.dispatch('keyup', { ctrlKey: true, metaKey: false });
  assert.equal(isZoomOut(), true); // Ctrl still held after Cmd release
  doc.defaultView.dispatch('blur', {});
  assert.equal(isZoomOut(), false);
  controller.setInteractive(false);
  frame.dispatch('pointerenter', { ctrlKey: true });
  assert.equal(isZoomOut(), true); // catches a modifier held on window entry
  frame.dispatch('pointermove', { ctrlKey: false });
  assert.equal(isZoomOut(), false);
  controller.setInteractive(true);
  frame.dispatch('pointerdown', event(50, 50));
  frame.dispatch('pointerup', event(50, 50));
  assert.equal(frame.__d2icZoomState.zoom, 2); // tap zooms ×2 at the pointer
  frame.dispatch('click', event(50, 50));
  frame.dispatch('pointerdown', event(20, 20));
  frame.dispatch('pointerup', event(100, 100));
  const click = event(100, 100);
  frame.dispatch('click', click);
  assert.equal(consumed, 6);
  frame.dispatch('pointerdown', event(100, 100, { ctrlKey: true }));
  frame.dispatch('click', event(100, 100));
  assert.equal(consumed, 8);
  assert.equal(frame.__d2icZoomState.zoom, 2.5);
  assert.equal(isZoomOut(), true);
  controller.destroy();
  assert.equal(isZoomOut(), false);
  assert.equal(doc.listeners.keydown.length, 0);
  assert.equal(doc.listeners.keyup.length, 0);
  assert.equal(doc.defaultView.listeners.blur.length, 0);
  assert.equal(frame.listeners.pointerenter.length, 0);
});

test('late image load refreshes dynamic transform origin; normal and toolbar clicks pass through', () => {
  class Element {
    constructor(doc) { this.ownerDocument = doc; this.style = {}; this.listeners = {}; this.children = []; this.clientWidth = 300; this.clientHeight = 200; this.offsetLeft = 0; this.offsetTop = 0; this.classList = { toggle() {}, remove() {} }; }
    appendChild(child) { this.children.push(child); child.parent = this; }
    append(...items) { items.forEach(item => this.appendChild(item)); }
    remove() { this.parent.children = this.parent.children.filter(item => item !== this); }
    contains(target) { return target === this || this.children.some(child => child.contains(target)); }
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
    removeEventListener() {}
    setAttribute() {}
    querySelectorAll() { return []; }
    querySelector() { return null; }
    getBoundingClientRect() { return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight }; }
    dispatch(name, event) { for (const fn of this.listeners[name] || []) fn(event); }
    dispatchEvent() { return true; }
  }
  const doc = { addEventListener() {}, removeEventListener() {}, createElement() { return new Element(doc); }, defaultView: { addEventListener() {}, removeEventListener() {}, Event: class { constructor(type) { this.type = type; } }, getComputedStyle() { return { position: 'relative' }; } } };
  const frame = new Element(doc);
  const image = new Element(doc); image.naturalWidth = 0; image.naturalHeight = 0;
  let consumed = 0;
  const clickEvent = target => ({ target, preventDefault() {}, stopImmediatePropagation() { consumed++; } });
  const controller = attach(frame, { layers: [image], interactive: true });
  assert.equal(image.style.transformOrigin, '0px 0px');
  image.offsetLeft = 12; image.offsetTop = 8; image.naturalWidth = 600; image.naturalHeight = 400;
  image.dispatch('load', {});
  assert.equal(image.style.transformOrigin, '-12px -8px');
  frame.dispatch('click', clickEvent(frame));
  const toolbar = frame.children.find(child => child.className === 'd2ic-image-zoom-toolbar');
  frame.dispatch('click', clickEvent(toolbar.children[0]));
  assert.equal(consumed, 0);
  assert.match(toolbar.children[1].textContent, /Zoom/);
  controller.destroy();
});

test('geometry returns the transformed contain box relative to the frame client area', () => {
  const frame = {
    clientWidth: 400, clientHeight: 200, clientLeft: 2, clientTop: 3,
    __d2icZoomState: { zoom: 2, tx: -100, ty: -40 },
    getBoundingClientRect() { return { left: 10, top: 20 }; },
  };
  const image = {
    naturalWidth: 100, naturalHeight: 50,
    getBoundingClientRect() { return { left: -88, top: -17, width: 800, height: 400 }; },
  };
  const box = geometry(frame, image);
  assert.deepEqual(box, { left: -100, top: -40, width: 800, height: 400, right: 700, bottom: 360, zoom: 2 });
});

test('resize preserves the source point at the viewport center below the shared toolbar', () => {
  const state = {zoom: 2, tx: -100, ty: -40};
  const top = 42;
  const oldBox = _math.containBox(400, 242 - top, 400, 200);
  const expectedX = ((400 / 2 - state.tx) / state.zoom - oldBox.left) / oldBox.width;
  const expectedY = (((242 + top) / 2 - state.ty) / state.zoom - top - oldBox.top) / oldBox.height;
  _math.preserveCenterOnResize(state, 400, 242, 200, 442, 400, 200, top);
  const nextBox = _math.containBox(200, 442 - top, 400, 200);
  const actualX = ((200 / 2 - state.tx) / state.zoom - nextBox.left) / nextBox.width;
  const actualY = (((442 + top) / 2 - state.ty) / state.zoom - top - nextBox.top) / nextBox.height;
  assert.ok(Math.abs(actualX - expectedX) < 1e-12);
  assert.ok(Math.abs(actualY - expectedY) < 1e-12);
});
