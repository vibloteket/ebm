// Pixel regression for every dynamic primitive, including radius animation.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.setContent('<canvas id="static" width="400" height="400"></canvas><canvas id="dynamic" width="400" height="400"></canvas>');
  await page.addScriptTag({ content: fs.readFileSync('web/scene.js', 'utf8') });
  const result = await page.evaluate(async () => {
    const scene = window.EbmScene;
    const canvas = document.getElementById('dynamic');
    scene.attach(document.getElementById('static'), canvas);
    const red = [255, 0, 0, 255], blue = [0, 0, 255, 255], none = [0, 0, 0, 0];
    // Circle, polygon/box and segment, each in background and foreground.
    const shapes = (r) => [
      [1, 40, 40, r, red, none, 0],
      [2, 0, red, none, [90, 20, 130, 20, 130, 60, 90, 60], 0],
      [0, 160, 40, 200, 40, 5, red, none, 0],
      [1, 40, 140, r, blue, none, 1],
      [2, 0, blue, none, [90, 120, 130, 120, 130, 160, 90, 160], 1],
      [0, 160, 140, 200, 140, 5, blue, none, 1],
    ];
    async function frame(events) {
      await new Promise(resolve => setTimeout(resolve, 40));
      scene.frame(events, 0, 0, 1, new Uint32Array(), new Float64Array(), 1);
    }
    const pixel = (x, y) => Array.from(canvas.getContext('2d').getImageData(x, y, 1, 1).data);
    await frame([['tile_add', 1, 0, 0, [], shapes(1), []]]);
    const first = [[40, 40], [110, 40], [180, 40], [40, 140], [110, 140], [180, 140]].map(([x, y]) => pixel(x, y));
    const beforeGrowth = pixel(50, 40);
    scene.consumeStats();
    await frame([['tile_dynvisuals', 1, shapes(20)]]);
    const afterGrowth = pixel(50, 40), fgGrowth = pixel(50, 140);
    const stats = scene.consumeStats();
    await frame([['tile_dynvisuals', 1, []]]);
    return { first, beforeGrowth, afterGrowth, fgGrowth, stats, removed: pixel(40, 40) };
  });
  assert.deepEqual(result.first.slice(1, 3), [[255, 0, 0, 255], [255, 0, 0, 255]]);
  assert.deepEqual(result.first.slice(4), [[0, 0, 255, 255], [0, 0, 255, 255]]);
  assert.ok(result.first[0][0] > 0 && result.first[3][2] > 0, 'small circles render in both bands');
  assert.equal(result.beforeGrowth[3], 0);
  assert.deepEqual(result.afterGrowth, [255, 0, 0, 255]);
  assert.deepEqual(result.fgGrowth, [0, 0, 255, 255]);
  assert.equal(result.stats.staticFrames, 0, 'radius update must not rebuild static canvas');
  assert.ok(result.stats.dynamicFrames > 0);
  assert.equal(result.removed[3], 0);
  console.log('PASS: dynamic circles, polygons/boxes, segments, both bands, growth and removal; no static rebuild');
} finally {
  await browser.close();
}
