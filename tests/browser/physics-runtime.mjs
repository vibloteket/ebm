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

const assert = (await import("node:assert/strict")).default;
const browser = await chromium.launch({ headless: true });
try {
  for (const [query, version, auto] of [
    ["", "7.4.0", false],
    ["?solver=auto", "7.4.0", true],
    ["?pymunk=7.3.1", "7.3.1", false],
    ["?pymunk=7.3.1&solver=auto", "7.3.1", false],
  ]) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    page.on("pageerror", error => errors.push(String(error)));
    page.on("requestfailed", req => console.log("NETWORK", req.url(), req.failure()));
    const wheels = [];
    page.on("request", request => { if (request.url().includes(".whl")) wheels.push(request.url()); });
    await page.goto(`http://127.0.0.1:${port}/${query}#stats`);
    await page.waitForSelector("#loading.hidden", { timeout: 180_000 });
    await page.waitForFunction(v => document.querySelector("#performance-stats")?.textContent.includes(`Pymunk ${v}`), version);
    assert(wheels.some(url => url.includes(`pymunk-${version}-`)));
    assert(!wheels.some(url => url.includes(`pymunk-${version === "7.4.0" ? "7.3.1" : "7.4.0"}-`)));
    const toggle = page.locator(".solver-toggle");
    assert.equal(await toggle.isChecked(), auto);
    const scene = await page.evaluate(() => window.EbmScene.debug());
    assert(scene.tiles > 10 && scene.balls > 0, JSON.stringify(scene));
    if (version === "7.4.0") {
      const timeOrigin = await page.evaluate(() => performance.timeOrigin);
      for (const target of [!auto, auto]) {
        await toggle.setChecked(target);
        await page.waitForTimeout(1300);
        assert.equal(await toggle.isChecked(), target);
        assert.equal(new URL(page.url()).searchParams.get("solver"), target ? "auto" : "baseline");
        assert.equal(await page.evaluate(() => performance.timeOrigin), timeOrigin, "no reload on toggle");
        assert((await page.evaluate(() => window.EbmScene.debug())).balls > 0);
        await page.locator(".copy-performance-report").click();
        await page.waitForFunction(async expected =>
          (await navigator.clipboard.readText()).includes(expected),
          `Pymunk: ${version}; solver: ${target ? "auto" : "baseline"}`);
      }
      // URL is sufficient to reproduce the chosen solver on reload.
      await page.reload();
      await page.waitForSelector("#loading.hidden", { timeout: 180_000 });
      await page.waitForSelector(".solver-toggle");
      assert.equal(await toggle.isChecked(), auto);
    } else {
      assert(await toggle.isDisabled());
      assert.match(await page.locator("#performance-stats").textContent(), /Baseline only/);
    }
    await page.evaluate(() => { location.hash = ""; });
    await page.waitForFunction(() => document.querySelector("#performance-stats").hidden);
    await page.evaluate(() => { location.hash = "stats"; });
    await page.waitForSelector(".solver-toggle");
    assert.equal(await toggle.isChecked(), auto);
    assert.deepEqual(errors, []);
    console.log(`PASS runtime ${version} ${query || "default"}: wheel, solver, rendering, live toggle/reload`);
    await page.close();
  }
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${port}/?pymunk=invalid`);
  await page.waitForFunction(() => document.querySelector("#loading")?.textContent.includes("Unsupported pymunk version"));
  console.log("PASS invalid configuration shows startup error");
} finally {
  await browser.close();
  server.close();
}
