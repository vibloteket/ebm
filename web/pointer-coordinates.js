// Coordinate conversion stays in Python, sharing the preview's draw transform.
export function setupPointerCoordinates(canvas, lookup) {
  const liveOutput = document.getElementById('pointer-live');
  const pinnedOutput = document.getElementById('pointer-pinned');
  const copy = document.getElementById('pointer-copy');
  const clear = document.getElementById('pointer-clear');
  let live = null;
  let pinned = null;
  const tuple = point => `(${point.x.toFixed(1)}, ${point.y.toFixed(1)})`;
  const label = point => `${tuple(point)}${point.gridSize > 1 ? ` · row ${point.row + 1}, col ${point.col + 1}` : ''}`;
  function render() {
    liveOutput.textContent = live ? label(live) : '—';
    pinnedOutput.textContent = pinned ? label(pinned) : '—';
    copy.disabled = !pinned;
    copy.textContent = 'Copy pinned';
    clear.disabled = !pinned;
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
  // PointerEvent preserves subpixel coordinates; legacy click events may round.
  canvas.addEventListener('pointerdown', event => {
    if (!event.shiftKey || event.button !== 0) return;
    live = locate(event);
    if (live) pinned = { ...live };
    render();
  });
  clear.addEventListener('click', () => {
    pinned = null;
    render();
  });
  copy.addEventListener('click', async () => {
    const point = pinned;
    if (!point) return;
    try {
      await navigator.clipboard.writeText(tuple(point));
      copy.textContent = 'Copied';
    } catch {
      copy.textContent = 'Copy unavailable';
    }
  });
  // Avoid retaining a live position calculated for an obsolete canvas size/grid.
  const resetLive = () => { live = null; render(); };
  new ResizeObserver(resetLive).observe(canvas);
  document.querySelectorAll('[data-mode], [data-view]').forEach(button => button.addEventListener('click', resetLive));
  render();
}
