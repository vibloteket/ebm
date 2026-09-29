// Browser check for the help drawer's ctrl-f-style search on editor.html.
// Serves dist/site (or EBM_SMOKE_DIR) and verifies: no filtering (all sections
// stay visible), match highlighting, hit counter, Enter/Shift+Enter navigation.
// Usage: bunx playwright install --only-shell chromium && node tests/browser/help-search.mjs
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const SITE = process.env.EBM_SMOKE_DIR || path.join(ROOT, 'dist', 'site');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.py': 'text/plain' };

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const rel = url.pathname === '/' ? '/editor.html' : url.pathname;
  const file = path.join(SITE, decodeURIComponent(rel));
  if (!file.startsWith(SITE) || !existsSync(file)) { res.writeHead(404); res.end('not found'); return; }
  res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream' });
  res.end(await readFile(file));
});
await new Promise(resolve => server.listen(0, resolve));
const port = server.address().port;

const fail = message => { console.error(`FAIL: ${message}`); process.exitCode = 1; };

let browser;
try {
  browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(`http://localhost:${port}/editor.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#api-content .api-section', { timeout: 30000 });

  const sectionsBefore = await page.locator('#api-content .api-section:visible').count();
  await page.click('#api-button');
  await page.fill('#api-search', 'sensor');
  await page.waitForSelector('#api-content mark.api-hit');

  const sectionsAfter = await page.locator('#api-content .api-section:visible').count();
  const hitCount = await page.locator('#api-content mark.api-hit').count();
  const label = await page.locator('#api-hits').textContent();
  const currentText = await page.locator('#api-content mark.api-hit.current').first().textContent();

  if (sectionsAfter !== sectionsBefore) fail(`search hid sections: ${sectionsBefore} -> ${sectionsAfter}`);
  if (hitCount < 10) fail(`expected many 'sensor' highlights, got ${hitCount}`);
  if (label.trim() !== `1 / ${hitCount}`) fail(`hit counter shows '${label}', expected '1 / ${hitCount}'`);
  if (currentText.toLowerCase() !== 'sensor') fail(`current hit text is '${currentText}'`);

  const scrollBefore = await page.locator('#api-content').evaluate(el => el.scrollTop);
  await page.press('#api-search', 'Enter');
  const label2 = await page.locator('#api-hits').textContent();
  if (label2.trim() !== `2 / ${hitCount}`) fail(`after Enter counter shows '${label2}'`);
  const currentCount = await page.locator('#api-content mark.api-hit.current').count();
  if (currentCount !== 1) fail(`expected exactly one current hit, got ${currentCount}`);

  await page.press('#api-search', 'Shift+Enter');
  const label3 = await page.locator('#api-hits').textContent();
  if (label3.trim() !== `1 / ${hitCount}`) fail(`after Shift+Enter counter shows '${label3}'`);

  await page.fill('#api-search', 'xyzzy-no-such-word');
  await page.waitForFunction(() => document.querySelector('#api-hits').textContent === 'No matches');
  const leftover = await page.locator('#api-content mark.api-hit').count();
  if (leftover !== 0) fail(`${leftover} stale highlights after no-match search`);

  await page.fill('#api-search', '');
  await page.waitForFunction(() => document.querySelector('#api-hits').textContent === '');
  const cleared = await page.locator('#api-content mark.api-hit').count();
  if (cleared !== 0) fail(`${cleared} stale highlights after clearing search`);

  if (!process.exitCode) console.log(`PASS: help search keeps ${sectionsAfter} sections visible, ${hitCount} 'sensor' hits highlighted, Enter/Shift+Enter navigation and counter work.`);
} catch (error) {
  fail(error.message);
} finally {
  if (browser) await browser.close();
  server.close();
}
process.exit(process.exitCode || 0);
