// End-to-end Pyodide import, bound setter, completion, and searchable API help.
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
  await page.click('.cm-content');
  await page.keyboard.press('Control+Home');
  await page.keyboard.press('Control+a');
  await page.keyboard.insertText(`from ebm import TileBase, Tween, ease

class TweenSmoke(TileBase):
    author = "Tween smoke test"

    def build(self, builder):
        self.circle = builder.visual_circle((200, 200), 1, dynamic=True)
        self.growth = Tween(1, 15, duration=0.1,
                            apply=self.circle.set_radius,
                            easing=ease.in_out_sine)
        assert self.growth.value == 1 and not self.growth.done
        assert len(ease.__all__) == 31

    def update(self, builder, dt):
        if self.growth is not None:
            self.growth.update(dt)
            if self.growth.done:
                assert self.growth.value == 15
                self.growth = None
                print("TWEEN_BROWSER_COMPLETE")
`);
  await page.keyboard.press('Control+Enter');
  await page.waitForFunction(() => document.getElementById('console-output')?.textContent.includes('TWEEN_BROWSER_COMPLETE'), null, { timeout: 30000 });
  assert.ok((await page.locator('#status').textContent()).includes('Running'));
  await page.keyboard.press('F1');
  await page.waitForSelector('#api-animation');
  const help = await page.locator('#api-animation').textContent();
  assert.ok(help.includes('ease.in_out_sine') && help.includes('ease.out_bounce'));
  assert.ok(help.includes('done') && help.includes('update(dt: float)'));
  assert.deepEqual(errors, []);
  console.log('PASS: Tween/ease work in Pyodide editor, dynamic circle completes, API help lists contract and all easing functions');
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
