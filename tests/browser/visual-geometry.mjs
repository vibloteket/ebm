// End-to-end visual geometry editing and generated API help.
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
  await page.keyboard.insertText(`from ebm import TileBase, Vec2d

class VisualGeometrySmoke(TileBase):
    author = "Geometry smoke"

    def build(self, b):
        self.visuals = []
        self.frames = 0
        for dynamic in (False, True):
            for foreground in (False, True):
                circle = b.visual_circle((100, 100), 10, dynamic=dynamic, foreground=foreground)
                segment = b.visual_segment((100, 150), (200, 150), 2, dynamic=dynamic, foreground=foreground)
                polygon = b.visual_polygon(((100, 200), (200, 200), (150, 250)), radius=2, dynamic=dynamic, foreground=foreground)
                box = b.visual_box(100, 270, 200, 300, dynamic=dynamic, foreground=foreground)
                self.visuals.append((circle, segment, polygon, box))

    def update(self, b, dt):
        if self.frames >= 20:
            return
        shift = Vec2d(1, 0)
        for circle, segment, polygon, box in self.visuals:
            old = circle.center
            circle.set_center(old + shift)
            assert circle.center == old + shift
            a, c = segment.segment_points
            segment.set_segment_points(a + shift, c + shift)
            assert segment.segment_points == (a + shift, c + shift)
            for visual in (polygon, box):
                old = visual.points
                visual.set_points(tuple(point + shift for point in old))
                assert visual.points == tuple(point + shift for point in old)
        self.frames += 1
        if self.frames == 20:
            print("VISUAL_GEOMETRY_BROWSER_COMPLETE")
`);
  await page.keyboard.press('Control+Enter');
  await page.waitForFunction(() => document.getElementById('console-output')?.textContent.includes('VISUAL_GEOMETRY_BROWSER_COMPLETE'), null, { timeout: 30000 });
  assert.ok((await page.locator('#status').textContent()).includes('Running'));
  await page.keyboard.press('F1');
  await page.waitForSelector('#api-events');
  const help = await page.locator('#api-events').textContent();
  for (const name of ['center', 'set_center', 'segment_points', 'set_segment_points', 'points', 'set_points']) {
    assert.ok(help.includes(name), `API help missing ${name}`);
  }
  assert.deepEqual(errors, []);
  console.log('PASS: visual geometry getters/setters animate circles, segments, polygons and boxes in Pyodide; static/dynamic, both bands, API help');
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
