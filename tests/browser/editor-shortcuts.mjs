// Browser check for editor keyboard behavior on editor.html.
// Serves dist/site (or EBM_SMOKE_DIR) and verifies:
//   Tab / Shift+Tab indent and dedent without moving focus out of the editor,
//   F1 toggles the help drawer (from the editor and from the page),
//   Ctrl+Enter triggers a run both inside and outside the editor.
// Usage: bash scripts/build-static-site.sh && node tests/browser/editor-shortcuts.mjs
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
  await page.waitForSelector('.cm-content', { timeout: 30000 });

  const editorFocus = () => page.evaluate(() => document.activeElement?.closest?.('.cm-editor') !== null || document.activeElement?.classList.contains('cm-content'));
  const firstLineIndent = () => page.evaluate(() => {
    const text = document.querySelector('.cm-content').textContent;
    return text.match(/^\s*/)[0].length;
  });
  const drawerOpen = () => page.evaluate(() => document.getElementById('api-reference').classList.contains('open'));

  // Tab indents and keeps focus inside the editor.
  await page.click('.cm-content');
  await page.keyboard.press('Control+Home');
  const before = await firstLineIndent();
  await page.keyboard.press('Tab');
  const afterTab = await firstLineIndent();
  if (afterTab !== before + 4) fail(`Tab should indent by 4 columns, went ${before} -> ${afterTab}`);
  if (!(await editorFocus())) fail('Tab moved focus out of the editor');

  // Shift+Tab dedents back, still focused.
  await page.keyboard.press('Shift+Tab');
  const afterShiftTab = await firstLineIndent();
  if (afterShiftTab !== before) fail(`Shift+Tab should restore indent to ${before}, got ${afterShiftTab}`);
  if (!(await editorFocus())) fail('Shift+Tab moved focus out of the editor');

  // Tab with a multi-line selection indents every selected line.
  await page.keyboard.press('Control+Home');
  await page.keyboard.press('Shift+ArrowDown');
  await page.keyboard.press('Shift+ArrowDown');
  await page.keyboard.press('Tab');
  const selectedIndent = await page.evaluate(() =>
    [...document.querySelectorAll('.cm-content > div')].slice(0, 2).map(line => line.textContent.match(/^\s*/)[0].length));
  if (selectedIndent.some(indent => indent < 4)) fail(`selection Tab should indent both lines, got ${selectedIndent}`);
  await page.keyboard.press('Shift+Tab');

  // F1 from the editor opens help, F1 again closes it.
  await page.keyboard.press('F1');
  if (!(await drawerOpen())) fail('F1 in editor did not open help');
  await page.keyboard.press('F1');
  if (await drawerOpen()) fail('F1 in editor did not close help');

  // F1 from outside the editor toggles help too.
  await page.click('body', { position: { x: 5, y: 5 } });
  await page.keyboard.press('F1');
  if (!(await drawerOpen())) fail('F1 outside editor did not open help');
  await page.keyboard.press('Escape');
  if (await drawerOpen()) fail('Escape did not close help');

  // Ctrl+Enter outside the editor triggers a run. Status text is identical before
  // and after a successful rebuild, so observe the transient "Building tile…" text.
  await page.evaluate(() => {
    window.__buildCount = 0;
    window.__statusObserver = new MutationObserver(() => {
      if (document.getElementById('status').textContent.includes('Building tile')) window.__buildCount++;
    });
    window.__statusObserver.observe(document.getElementById('status'), { childList: true, subtree: true });
  });
  await page.keyboard.press('Control+Enter');
  await page.waitForFunction(() => window.__buildCount >= 1, null, { timeout: 10000 });

  // Ctrl+Enter inside the editor triggers a run and is not double-fired.
  await page.click('.cm-content');
  await page.keyboard.press('Control+Enter');
  await page.waitForFunction(() => window.__buildCount === 2, null, { timeout: 10000 });

  if (!process.exitCode) console.log('PASS: Tab/Shift+Tab indent in place, F1 toggles help, Ctrl+Enter runs from editor and page.');
} catch (error) {
  fail(error.message);
} finally {
  if (browser) await browser.close();
  server.close();
}
process.exit(process.exitCode || 0);
