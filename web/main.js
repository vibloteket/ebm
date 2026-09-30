import {loadPythonPackage} from "./python-package.js?v=1";
const APP_VERSION = "prototype-0.70-tile-400";
const PYMUNK_WHEEL = "./vendor/pymunk-7.3.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl";

const diagnostics = [];
let loading;

function logStep(message, data = undefined) {
  const line = data === undefined ? message : `${message}: ${JSON.stringify(data)}`;
  diagnostics.push(`[${new Date().toISOString()}] ${line}`);
  console.log(`[EBM] ${line}`);
  const log = document.getElementById("diagnostic-log");
  if (log) log.textContent = diagnostics.join("\n");
}

function setStatus(text) {
  loading ??= document.getElementById("loading");
  const p = loading?.querySelector("p");
  if (p) p.textContent = text;
  logStep(text);
}

function formatError(error) {
  if (!error) return "Unknown error";
  if (error.stack) return error.stack;
  if (error.message) return error.message;
  try { return JSON.stringify(error, null, 2); } catch (_) { return String(error); }
}

function showError(error, context = "startup") {
  console.error(error);
  loading ??= document.getElementById("loading");
  const detail = formatError(error);
  const environment = [
    `App version: ${APP_VERSION}`,
    `Context: ${context}`,
    `URL: ${location.href}`,
    `User agent: ${navigator.userAgent}`,
    `Online: ${navigator.onLine}`,
    `Viewport: ${innerWidth}×${innerHeight}`,
  ].join("\n");

  loading.classList.add("error");
  loading.classList.remove("hidden");
  loading.innerHTML = `
    <section class="error-card">
      <h1>Endless Ball Machine failed to start</h1>
      <p class="error-summary">${escapeHtml(error?.message || String(error || "Unknown error"))}</p>
      <div class="error-actions">
        <button id="copy-error" type="button">Copy error</button>
        <button id="reload-page" type="button">Reload</button>
      </div>
      <details open>
        <summary>Error details</summary>
        <pre>${escapeHtml(detail)}</pre>
      </details>
      <details>
        <summary>Environment</summary>
        <pre>${escapeHtml(environment)}</pre>
      </details>
      <details open>
        <summary>Startup log</summary>
        <pre id="diagnostic-log">${escapeHtml(diagnostics.join("\n"))}</pre>
      </details>
    </section>`;

  document.getElementById("copy-error")?.addEventListener("click", async () => {
    const text = `${detail}\n\n${environment}\n\n${diagnostics.join("\n")}`;
    try {
      await navigator.clipboard.writeText(text);
      document.getElementById("copy-error").textContent = "Copied";
    } catch (_) {
      document.getElementById("copy-error").textContent = "Copy failed";
    }
  });
  document.getElementById("reload-page")?.addEventListener("click", () => location.reload());
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function fetchText(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch ${path}: HTTP ${response.status}`);
  const text = await response.text();
  logStep(`Fetched ${path}`, { bytes: text.length });
  return text;
}

async function checkResource(path) {
  const response = await fetch(path, { method: "GET", cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch ${path}: HTTP ${response.status}`);
  const blob = await response.blob();
  logStep(`Fetched ${path}`, { bytes: blob.size, type: blob.type || "unknown" });
  return blob.size;
}

async function writePackage(pyodide) {
  await loadPythonPackage(pyodide);
}

// Performance stats overlay toggled by the URL hash (#stats). Changing the
// hash never reloads the page, so the overlay can be switched on/off live via
// the hashchange event. Sampling (rAF loop) only runs while enabled, and the
// consume-style counters on both the Python and JS scene side are discarded
// on enable so the first sample is a fresh window.
function setupPerformanceStats(getPerformanceStats, getZoom, setTileProfiling) {
  const stats = document.getElementById("performance-stats");
  if (!stats) return;

  let enabled = false;
  let browserFrames = 0, last = performance.now(), latestReport = "Waiting for the first profiling sample…";

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-performance-report";
  copyButton.textContent = "Copy report";
  copyButton.hidden = true;
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(latestReport);
      copyButton.textContent = "Copied";
    } catch (_) {
      const textarea = document.createElement("textarea");
      textarea.value = latestReport;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
      copyButton.textContent = "Copied";
    }
    setTimeout(() => { copyButton.textContent = "Copy report"; }, 1400);
  });
  stats.after(copyButton);

  const avg = (entry) => entry?.calls ? entry.total_ms / entry.calls : 0;
  const ms = (value) => Number(value || 0).toFixed(2);
  const sample = (now) => {
    if (!enabled) return;
    browserFrames++;
    if (now - last >= 1000) {
      const seconds = (now-last)/1000;
      const data = JSON.parse(String(getPerformanceStats?.() || "{}"));
      const scene = window.EbmScene?.consumeStats?.() || {};
      const engine = data.engine || {};
      const dynamicFrames = scene.dynamicFrames || 0;
      const renderedFps = dynamicFrames / seconds;
      const browserFps = browserFrames / seconds;
      const exportCalls = data.export_calls || 0;
      const frameCount = Math.max(1, engine.engine_total?.calls || 0);
      const perTile = Object.entries(data.per_tile || {})
        .map(([name, bucket]) => ({ name, total: bucket.total_ms || 0, calls: bucket.calls || 0, max: bucket.max_ms || 0 }))
        .sort((a, b) => b.total - a.total);
      const tileRows = perTile.slice(0, 3)
        .map((t) => `<span class="tile-detail">↳ ${t.name} ×${Math.round(t.calls / frameCount)} · ${(t.total / frameCount).toFixed(2)} ms/f</span>`)
        .join("");
      const metrics = {
        renderedFps: renderedFps.toFixed(1), browserFps: browserFps.toFixed(1),
        engine: ms(avg(engine.engine_total)), tileUpdates: ms(avg(engine.tile_update)),
        physics: ms(avg(engine.physics)), physicsSteps: Math.round(engine.physics?.units || 0),
        reconcile: ms(avg(engine.tile_reconcile)), ballUpkeep: ms(avg(engine.ball_maintenance)),
        exportMs: ms((data.export_total_ms||0)/Math.max(1,exportCalls)), exportMax: ms(data.export_max_ms),
        dynamic: ms((scene.dynamicTotalMs||0)/Math.max(1,dynamicFrames)), dynamicMax: ms(scene.dynamicMaxMs),
        staticDraw: ms((scene.staticTotalMs||0)/Math.max(1,scene.staticFrames||0)), staticRedraws: scene.staticFrames||0,
      };
      stats.innerHTML = `
        <strong>${metrics.renderedFps} rendered FPS</strong>
        <span>${metrics.browserFps} browser FPS · target 30</span>
        <hr>
        <span>Engine total <b>${metrics.engine} ms/frame</b></span>
        <span>Tile updates <b>${metrics.tileUpdates} ms</b></span>
        ${tileRows}
        <span>Physics <b>${metrics.physics} ms</b> · ${metrics.physicsSteps} steps</span>
        <span>Reconcile <b>${metrics.reconcile} ms</b></span>
        <span>Ball upkeep <b>${metrics.ballUpkeep} ms</b></span>
        <hr>
        <span>Export <b>${metrics.exportMs} ms/frame</b> · max ${metrics.exportMax} ms</span>
        <span>Dynamic draw <b>${metrics.dynamic} ms</b> · max ${metrics.dynamicMax} ms</span>
        <span>Static draw <b>${metrics.staticDraw} ms</b> · ${metrics.staticRedraws} redraws</span>
        <span>Scene events <b>${data.sync_events||0}</b> · JS ${scene.eventCount||0}</span>
        <hr>
        <span>${data.visible_tiles||0} visible · ${data.tiles||0} active tiles · ${data.balls||0} balls</span>
        <span>${data.boundary_inputs||0} open inputs · ${data.shapes||0} shapes · ${data.bodies||0} bodies</span>
        <span>${innerWidth}×${innerHeight} · zoom ${Number(getZoom()).toFixed(2)}×</span>`;
      latestReport = [
        "Endless Ball Machine performance report",
        `Timestamp: ${new Date().toISOString()}`,
        `App: ${APP_VERSION}`,
        `URL: ${location.href}`,
        `Browser: ${navigator.userAgent}`,
        `Rendered FPS: ${metrics.renderedFps} (target 30)`,
        `Browser FPS: ${metrics.browserFps}`,
        `Engine total: ${metrics.engine} ms/frame`,
        `Tile updates: ${metrics.tileUpdates} ms/frame`,
        ...(perTile.length
          ? ["Tile update breakdown:", ...perTile.map((t) =>
            `  ${t.name}: ${Math.round(t.calls / frameCount)} instances, ${(t.total / frameCount).toFixed(3)} ms/frame avg, ${t.max.toFixed(2)} ms max, ${(100 * t.total / Math.max(1e-9, engine.tile_update?.total_ms || 0)).toFixed(0)}% of tile updates`)]
          : []),
        `Physics: ${metrics.physics} ms/frame (${metrics.physicsSteps} steps in sample)`,
        `Tile reconcile: ${metrics.reconcile} ms/frame`,
        `Ball upkeep: ${metrics.ballUpkeep} ms/frame`,
        `Export: ${metrics.exportMs} ms/frame (max ${metrics.exportMax} ms), ${data.sync_events||0} scene events`,
        `Dynamic draw: ${metrics.dynamic} ms/frame (max ${metrics.dynamicMax} ms)`,
        `Static draw: ${metrics.staticDraw} ms/redraw (${metrics.staticRedraws} redraws)`,
        `World: ${data.visible_tiles||0} visible tiles, ${data.tiles||0} active buffered tiles, ${data.balls||0} balls, ${data.boundary_inputs||0} open boundary inputs, ${data.shapes||0} shapes, ${data.bodies||0} bodies, ${data.constraints||0} constraints`,
        `Viewport: ${innerWidth}x${innerHeight}`,
        `Zoom: ${Number(getZoom()).toFixed(2)}x`,
        `Renderer: js-scene basic`,
      ].join("\n");
      browserFrames = 0; last = now;
    }
    requestAnimationFrame(sample);
  };

  const applyHash = () => {
    const want = location.hash === "#stats";
    if (want === enabled) return;
    enabled = want;
    stats.hidden = !enabled;
    copyButton.hidden = !enabled;
    try { setTileProfiling?.(enabled); } catch (_) { /* profiling is optional */ }
    if (enabled) {
      // Discard counters accumulated while the overlay was off; both
      // performance_stats() and EbmScene.consumeStats() reset on read.
      try { getPerformanceStats?.(); } catch (_) { /* ignore */ }
      window.EbmScene?.consumeStats?.();
      browserFrames = 0;
      last = performance.now();
      requestAnimationFrame(sample);
    }
  };
  window.addEventListener("hashchange", applyHash);
  applyHash();
}

async function main() {
  loading = document.getElementById("loading");
  const canvas = document.getElementById("dynamic-machine");

  const pymunkWheelUrl = new URL(PYMUNK_WHEEL, location.href).href;

  setStatus("Checking static files…");
  await checkResource(pymunkWheelUrl);

  setStatus("Loading Pyodide…");
  const pyodide = await loadPyodide();
  logStep("Pyodide loaded", {
    pyodideVersion: pyodide.version,
    python: pyodide.runPython("import sys; sys.version"),
  });

  setStatus("Loading Pyodide package: cffi…");
  await pyodide.loadPackage("cffi");
  logStep("cffi loaded");

  setStatus("Loading pymunk wheel…");
  // The pymunk WASM wheel is hosted with the site. It is a Pyodide/emscripten
  // binary wheel, not a pure Python PyPI wheel. Use pyodide.loadPackage for
  // the custom wheel URL; cffi is loaded above because custom URL wheels do
  // not get dependency resolution.
  await pyodide.loadPackage(pymunkWheelUrl);
  logStep("pymunk loaded", pyodide.runPython("import pymunk; pymunk.version"));

  setStatus("Loading EBM Python modules…");
  await writePackage(pyodide);

  setStatus("Starting simulation…");
  await pyodide.runPythonAsync(`
from ebm.web_demo import start, zoom_at, set_zoom, zoom_value, performance_stats, set_tile_profiling
from js import window, document
start(document.getElementById('static-machine'), document.getElementById('dynamic-machine'))
`);

  // Expose zoom for pinch-to-zoom, touchpads without wheel events, and
  // explicit controls that work consistently in Firefox/Linux.
  const engine = pyodide.globals.get("zoom_at");
  const setZoom = pyodide.globals.get("set_zoom");
  const getZoom = pyodide.globals.get("zoom_value");
  const updateZoomLabel = () => {
    const value = Number(getZoom?.() ?? 0.5);
    document.getElementById("zoom-reset").textContent = `${value.toFixed(2).replace(/0$/, "")}×`;
  };
  document.getElementById("zoom-out")?.addEventListener("click", () => { setZoom(Math.max(.2, Number(getZoom()) / 1.25)); updateZoomLabel(); });
  document.getElementById("zoom-in")?.addEventListener("click", () => { setZoom(Math.min(4, Number(getZoom()) * 1.25)); updateZoomLabel(); });
  document.getElementById("zoom-reset")?.addEventListener("click", () => { setZoom(.5); updateZoomLabel(); });
  window.addEventListener("keydown", (e) => { if (["+", "=", "-", "_", "0"].includes(e.key)) requestAnimationFrame(updateZoomLabel); });
  updateZoomLabel();

  if (engine) {
    const canvas = document.getElementById("dynamic-machine");
    let pinchDist = 0;
    let pinchCx = 0;
    let pinchCy = 0;

    canvas.addEventListener("touchstart", (e) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        const t0 = e.touches[0];
        const t1 = e.touches[1];
        pinchCx = (t0.clientX + t1.clientX) / 2;
        pinchCy = (t0.clientY + t1.clientY) / 2;
        const dx = t0.clientX - t1.clientX;
        const dy = t0.clientY - t1.clientY;
        pinchDist = Math.sqrt(dx * dx + dy * dy);
      }
    }, { passive: false });

    canvas.addEventListener("touchmove", (e) => {
      if (e.touches.length === 2 && pinchDist > 0) {
        e.preventDefault();
        const t0 = e.touches[0];
        const t1 = e.touches[1];
        const dx = t0.clientX - t1.clientX;
        const dy = t0.clientY - t1.clientY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const factor = dist / pinchDist;
        pinchDist = dist;
        const cx = (t0.clientX + t1.clientX) / 2;
        const cy = (t0.clientY + t1.clientY) / 2;
        const rect = canvas.getBoundingClientRect();
        engine(cx - rect.left, cy - rect.top, factor);
      }
    }, { passive: false });

    canvas.addEventListener("touchend", () => {
      pinchDist = 0;
    });
  }

  loading.classList.add("hidden");

  setupPerformanceStats(pyodide.globals.get("performance_stats"), getZoom, pyodide.globals.get("set_tile_profiling"));
}

window.addEventListener("error", (event) => {
  showError(event.error || event.message, "window.error");
});

window.addEventListener("unhandledrejection", (event) => {
  showError(event.reason, "unhandledrejection");
});

main().catch((error) => showError(error, "main"));
