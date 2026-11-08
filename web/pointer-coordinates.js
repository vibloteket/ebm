// Coordinate conversion stays in Python, sharing the preview's draw transform.
export function setupPointerCoordinates(canvas, lookup) {
  const liveOutput = document.getElementById('pointer-live');
  let live = null;
  function render() {
    liveOutput.textContent = live ? `(${live.x.toFixed(1)}, ${live.y.toFixed(1)})` : '—';
  }
  function locate(event) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return lookup((event.clientX - rect.left) * canvas.width / rect.width,
                  (event.clientY - rect.top) * canvas.height / rect.height);
  }
  canvas.addEventListener('pointermove', event => {
    live = locate(event);
    render();
  });
  canvas.addEventListener('pointerleave', () => {
    live = null;
    render();
  });
  // Avoid retaining a live position calculated for an obsolete canvas size/grid.
  const resetLive = () => { live = null; render(); };
  new ResizeObserver(resetLive).observe(canvas);
  document.querySelectorAll('[data-mode], [data-view]').forEach(button => button.addEventListener('click', resetLive));
  render();
}
