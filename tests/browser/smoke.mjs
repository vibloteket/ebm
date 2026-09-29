/* Browser smoke test: verify the machine actually renders, in pixels.
 *
 * Counters and event logs cannot catch "renders nothing" regressions (the
 * 2026-09-29 launch bug: stats looked fine while the static layer painted
 * only paper). This test serves dist/site itself, loads the page in headless
 * Chromium, and asserts on canvas pixel histograms.
 *
 * Usage:  bunx playwright install --only-shell chromium
 *         node tests/browser/smoke.mjs
 * Env:    EBM_SMOKE_DIR  site root to serve (default: dist/site)
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join, extname, resolve, sep } from "node:path";
import { chromium } from "playwright";

const root = resolve(process.env.EBM_SMOKE_DIR || "dist/site");
const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".txt": "text/plain",
  ".whl": "application/octet-stream",
};

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", "http://localhost");
    const path = join(root, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
    if (!path.startsWith(root + sep) && path !== join(root, "index.html")) throw new Error("path escape");
    const body = await readFile(path);
    res.writeHead(200, { "content-type": MIME[extname(path)] ?? "application/octet-stream", "cache-control": "no-store" });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
});
await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
const port = server.address().port;

let failed = false;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
  if (!ok) failed = true;
};

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });

  await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#loading.hidden", { timeout: 180_000 });
  check("startup completes", true);
  await page.waitForTimeout(6000);

  const scene = await page.evaluate(() => window.EbmScene.debug());
  check("scene store populated", scene.tiles > 10 && scene.segs > 100 && scene.balls > 0, JSON.stringify(scene));

  const pixels = await page.evaluate(() => {
    const scan = (id) => {
      const canvas = document.getElementById(id);
      const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      let transparent = 0, railBlue = 0, saturated = 0, opaque = 0;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
        if (a === 0) { transparent++; continue; }
        opaque++;
        if (Math.abs(r - 49) < 25 && Math.abs(g - 90) < 25 && Math.abs(b - 168) < 30) railBlue++;
        else if (Math.max(r, g, b) - Math.min(r, g, b) > 60) saturated++;
      }
      return { transparent, railBlue, saturated, opaque };
    };
    return { static: scan("static-machine"), dynamic: scan("dynamic-machine") };
  });
  check("static layer paints rails", pixels.static.railBlue > 10_000, `railBlue=${pixels.static.railBlue}`);
  check("static layer paints bumpers/decorations", pixels.static.saturated > 2_000, `saturated=${pixels.static.saturated}`);
  check("static layer leaves no transparent holes", pixels.static.transparent === 0, `transparent=${pixels.static.transparent}`);
  check("dynamic layer paints balls", pixels.dynamic.opaque > 1_000, `opaque=${pixels.dynamic.opaque}`);

  const bitmapHash = () => page.evaluate(() => {
    const canvas = document.getElementById("static-machine");
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let hash = 0;
    for (let i = 0; i < data.length; i += 401) hash = (hash * 31 + data[i]) >>> 0;
    return hash;
  });
  const before = await bitmapHash();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(600);
  const after = await bitmapHash();
  check("static layer follows panning", before !== after, `${before} -> ${after}`);

  check("no console or page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
} finally {
  await browser.close();
  server.close();
}
process.exit(failed ? 1 : 0);
