// Editor preview must survive user-code exceptions and resume after Run.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const site = path.resolve(process.env.EBM_SMOKE_DIR || 'dist/site');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.wasm': 'application/wasm' };
const server = createServer(async (req, res) => {
  try {
    const file = path.resolve(site, '.' + new URL(req.url, 'http://localhost').pathname);
    if (!file.startsWith(site + path.sep)) throw new Error('invalid path');
    const body = await readFile(file);
    res.writeHead(200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404); res.end('not found');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(`http://127.0.0.1:${server.address().port}/editor.html`);
  await page.waitForFunction(() => document.getElementById('status')?.textContent.includes('Running'), null, { timeout: 120000 });
  async function run(source) {
    await page.click('.cm-content');
    await page.keyboard.press('Control+Home');
    await page.keyboard.press('Control+a');
    await page.keyboard.insertText(source);
    await page.keyboard.press('Control+Enter');
  }
  const source = (build, update) => `from ebm import TileBase
from ebm import editor_preview
class RecoveryTile(TileBase):
    author = "Recovery test"
    def build(self, b):
        ${build}
    ${update}
`;
  const good = marker => source('self.reported = False', `def update(self, b, dt):
        if editor_preview._preview.balls and not self.reported:
            self.reported = True
            print("${marker}")`);
  for (const [bad, marker, error] of [
    [source('pass', 'def update(): pass'), 'RECOVERED_SIGNATURE_WITH_BALLS', 'TypeError'],
    [source('raise ValueError("broken build")', 'def update(self, b, dt): pass'), 'RECOVERED_BUILD_WITH_BALLS', 'ValueError'],
    [source('pass', 'def update(self, b, dt): raise RuntimeError("broken update")'), 'RECOVERED_UPDATE_WITH_BALLS', 'RuntimeError'],
  ]) {
    await run(bad);
    await page.waitForFunction(error => {
      const el = document.getElementById('status');
      return !el.textContent.includes('Running') && document.body.textContent.includes(error);
    }, error, { timeout: 10000 });
    await run(good(marker));
    await page.waitForFunction(marker => document.getElementById('console-output')?.textContent.includes(marker), marker, { timeout: 15000 });
    assert.ok((await page.locator('#status').textContent()).includes('Running'));
  }
  assert.deepEqual(errors, []);
  console.log('PASS: malformed update, build exception and update exception recover with live ball spawning after Run, without reload');
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
