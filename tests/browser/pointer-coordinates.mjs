// End-to-end coordinate inspector and unchanged click spawning.
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
  await page.keyboard.insertText(`from ebm import TileBase
from ebm import editor_preview
from js import window
class PointerSmoke(TileBase):
    author = "Pointer smoke"
    def build(self, b):
        pass
    def update(self, b, dt):
        for boundary in editor_preview._preview.spawn_clocks:
            editor_preview._preview.spawn_clocks[boundary] = 1000000
        window.coordinateTestBalls = len(editor_preview._preview.balls)
`);
  await page.keyboard.press('Control+Enter');
  await page.waitForFunction(() => window.coordinateTestBalls === 0);
  async function target(row, col, x, y, size) {
    return page.locator('#preview').evaluate((canvas, {row,col,x,y,size}) => {
      const rect = canvas.getBoundingClientRect();
      const ww = size * 400, wh = ww + (size > 1 ? 200 : 0);
      const scale = Math.max(.01, Math.min((canvas.width-36)/ww, (canvas.height-44)/wh));
      const left = (canvas.width-ww*scale)/2, top = (canvas.height-wh*scale)/2;
      return {x:rect.left + (left + (col*400+x)*scale)*rect.width/canvas.width,
              y:rect.top + (top + (row*400+(col%2)*200+y)*scale)*rect.height/canvas.height};
    }, {row,col,x,y,size});
  }
  let p = await target(0,0,123.4,234.5,1);
  await page.mouse.move(p.x,p.y);
  await page.waitForFunction(() => document.getElementById('pointer-live').textContent === '(123.4, 234.5)');
  await page.keyboard.down('Shift');
  await page.mouse.click(p.x,p.y);
  await page.keyboard.up('Shift');
  assert.equal(await page.locator('#pointer-pinned').textContent(), '(123.4, 234.5)');
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(() => window.coordinateTestBalls), 0, 'shift-click must not spawn');
  await page.mouse.move(0,0);
  assert.equal(await page.locator('#pointer-live').textContent(), '—');
  assert.equal(await page.locator('#pointer-pinned').textContent(), '(123.4, 234.5)');
  await page.context().grantPermissions(['clipboard-read','clipboard-write']);
  await page.click('#pointer-copy');
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), '(123.4, 234.5)');
  await page.click('#pointer-clear');
  assert.equal(await page.locator('#pointer-pinned').textContent(), '—');
  assert.ok(await page.locator('#pointer-copy').isDisabled());
  await page.mouse.click(p.x,p.y);
  await page.waitForFunction(() => window.coordinateTestBalls === 2);
  await page.click('[data-mode="repeat"]');
  p = await target(1,1,135.2,246.8,3);
  await page.mouse.move(p.x,p.y);
  await page.waitForFunction(() => document.getElementById('pointer-live').textContent === '(135.2, 246.8) · row 2, col 2');
  await page.click('#pause-button');
  p = await target(0,2,210.3,110.4,3);
  await page.mouse.move(p.x,p.y);
  await page.waitForFunction(() => document.getElementById('pointer-live').textContent === '(210.3, 110.4) · row 1, col 3');
  await page.keyboard.down('Shift');
  await page.mouse.click(p.x,p.y);
  await page.keyboard.up('Shift');
  assert.equal(await page.locator('#pointer-pinned').textContent(), '(210.3, 110.4) · row 1, col 3');
  await page.click('#pause-button');
  // Empty region above staggered middle column must not look like a tile.
  p = await target(0,1,100,-100,3);
  await page.mouse.move(p.x,p.y);
  assert.equal(await page.locator('#pointer-live').textContent(), '—');
  // Exercise CSS-scaled backing pixels and narrow repeat-preview layout.
  await page.setViewportSize({width:390,height:900});
  await page.locator('#preview').scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await page.locator('#preview').evaluate(canvas => {canvas.style.transform='scale(.8)';});
  await page.waitForTimeout(300);
  p = await target(2,2,100.1,200.2,3);
  await page.mouse.move(p.x,p.y);
  await page.waitForFunction(() => document.getElementById('pointer-live').textContent === '(100.1, 200.2) · row 3, col 3');
  await page.keyboard.down('Shift');
  await page.mouse.click(p.x,p.y);
  await page.keyboard.up('Shift');
  assert.equal(await page.locator('#pointer-pinned').textContent(), '(100.1, 200.2) · row 3, col 3');
  assert.deepEqual(errors, []);
  console.log('PASS: live tile-local coordinates, pin/copy/clear, normal spawn vs shift-click, staggered repeat gaps, resized/CSS-scaled mobile preview');
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
