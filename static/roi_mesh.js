/* Native SVG mesh in screen coordinates, sharing the VIS image geometry. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.D2ICROIMesh = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  function transform(box, width, height) {
    return `translate(${box.left} ${box.top}) scale(${box.width / width} ${box.height / height})`;
  }

  function attach(frame, image, svg) {
    const ns = 'http://www.w3.org/2000/svg';
    const group = svg.ownerDocument.createElementNS(ns, 'g');
    svg.replaceChildren(group);
    let revision = 0;
    function render() {
      const box = window.D2ICImageZoom.geometry(frame, image);
      if (box) group.setAttribute('transform', transform(box, image.naturalWidth, image.naturalHeight));
    }
    frame.addEventListener('imageviewchange', render);
    image.addEventListener('load', render);
    return {
      async load(url) {
        const current = ++revision;
        const response = await fetch(url, { cache: 'no-cache' });
        if (!response.ok) throw new Error('Maillage absent ou périmé');
        const source = new DOMParser().parseFromString(await response.text(), 'image/svg+xml');
        if (current !== revision || !svg.isConnected) return;
        const paths = source.querySelectorAll('svg > path');
        if (!paths.length || source.querySelector('parsererror')) throw new Error('Calque maillage SVG invalide');
        // Only copy edge geometry; never insert markup from the response into the page.
        group.replaceChildren(...Array.from(paths, sourcePath => {
          const path = svg.ownerDocument.createElementNS(ns, 'path');
          path.setAttribute('d', sourcePath.getAttribute('d'));
          path.setAttribute('fill', 'none');
          path.setAttribute('stroke', '#ffb02a');
          path.setAttribute('stroke-width', '1');
          path.setAttribute('vector-effect', 'non-scaling-stroke');
          path.setAttribute('stroke-linejoin', 'round');
          path.setAttribute('stroke-linecap', 'round');
          return path;
        }));
        render();
        svg.dispatchEvent(new Event('load'));
      },
      destroy() {
        ++revision;
        frame.removeEventListener('imageviewchange', render);
        image.removeEventListener('load', render);
      }
    };
  }
  return { attach, transform };
});
