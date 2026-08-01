const APP_VERSION = "debug-0.51-basic-default-routes";
const PYMUNK_WHEEL = "./vendor/pymunk-7.2.0-cp312-cp312-pyodide_2024_0_wasm32.whl";
const PY_FILES = [
  "__init__.py",
  "ports.py",
  "random_utils.py",
  "tile_base.py",
  "tile_api.py",
  "tile_catalog.py",
  "tiles/__init__.py",
  "tiles/builtin/__init__.py",
  "tiles/builtin/powered_channel.py",
  "tiles/builtin/reference_router.py",
  "tiles/contributed/__init__.py",
  "sketch.py",
  "pigment.py",
  "routes.py",
  "engine.py",
  "web_demo.py",
  "validator.py",
  "debug_demo.py",
];

const diagnostics = [];
let loading;

function logStep(message, data = undefined) {
  const line = data === undefined ? message : `${message}: ${JSON.stringify(data)}`;
  diagnostics.push(`[${new Date().toISOString()}] ${line}`);
  console.log(`[EBM debug] ${line}`);
  const log = document.getElementById("diagnostic-log");
  if (log) log.textContent = diagnostics.join("\n");
}

function setStatus(text) {
  loading ??= document.getElementById("loading");
  const p = loading?.querySelector("p");
  if (p) p.textContent = text;
  logStep(text);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatError(error) {
  if (!error) return "Unknown error";
  if (error.stack) return error.stack;
  if (error.message) return error.message;
  try { return JSON.stringify(error, null, 2); } catch (_) { return String(error); }
}

function showError(error, context = "debug startup") {
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
      <h1>Tile Debug failed to start</h1>
      <p class="error-summary">${escapeHtml(error?.message || String(error || "Unknown error"))}</p>
      <div class="error-actions">
        <button id="copy-error" type="button">Copy error</button>
        <button id="reload-page" type="button">Reload</button>
      </div>
      <details open><summary>Error details</summary><pre>${escapeHtml(detail)}</pre></details>
      <details><summary>Environment</summary><pre>${escapeHtml(environment)}</pre></details>
      <details open><summary>Startup log</summary><pre id="diagnostic-log">${escapeHtml(diagnostics.join("\n"))}</pre></details>
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
}

async function writePackage(pyodide) {
  for (const directory of ["/ebm", "/ebm/tiles", "/ebm/tiles/builtin", "/ebm/tiles/contributed"]) {
    try { pyodide.FS.mkdir(directory); } catch (_) {}
  }
  for (const file of PY_FILES) {
    pyodide.FS.writeFile(`/ebm/${file}`, await fetchText(`./ebm/${file}`));
  }
  pyodide.runPython(`
import sys
if '/' not in sys.path:
    sys.path.insert(0, '/')
`);
}

async function main() {
  loading = document.getElementById("loading");
  const canvas = document.getElementById("machine");
  const select = document.getElementById("tile-select");
  const title = document.getElementById("contract-title");
  const pymunkWheelUrl = new URL(PYMUNK_WHEEL, location.href).href;

  setStatus("Checking static files…");
  await checkResource(pymunkWheelUrl);

  setStatus("Loading Pyodide…");
  const pyodide = await loadPyodide();
  logStep("Pyodide loaded", {
    pyodideVersion: pyodide.version,
    python: pyodide.runPython("import sys; sys.version"),
  });

  setStatus("Loading cffi…");
  await pyodide.loadPackage("cffi");

  setStatus("Loading pymunk wheel…");
  await pyodide.loadPackage(pymunkWheelUrl);
  logStep("pymunk loaded", pyodide.runPython("import pymunk; pymunk.version"));

  setStatus("Loading EBM debug modules…");
  await writePackage(pyodide);

  setStatus("Starting debug simulator…");
  await pyodide.runPythonAsync(`
from ebm.debug_demo import start
from js import document
start(
    document.getElementById('machine'),
    document.getElementById('tile-select'),
    document.getElementById('contract-title'),
    document.getElementById('validation-report'),
)
`);

  loading.classList.add("hidden");
}

window.addEventListener("error", (event) => showError(event.error || event.message, "window.error"));
window.addEventListener("unhandledrejection", (event) => showError(event.reason, "unhandledrejection"));
main().catch((error) => showError(error, "main"));
