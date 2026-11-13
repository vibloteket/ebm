import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(process.env.EBM_SMOKE_DIR||'dist/site');
const mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.py':'text/plain','.whl':'application/zip'};
const server=http.createServer((req,res)=>{const file=path.join(root,decodeURIComponent(new URL(req.url,'http://localhost').pathname));try{res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file))}catch{res.statusCode=404;res.end()}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',error=>errors.push(String(error)));
const source=`from ebm import TileBase
class FeedbackTile(TileBase):
    author = "Browser tests"
    def build(self, b):
        self.reported = False
        sensor = b.sensor_box(0, 0, 400, 400)
        def divert(event):
            event.ball.set_position((380, 300))
            event.ball.set_velocity((300, 220))
        b.on_ball_contact(sensor, begin=divert)
    def update(self, b, dt):
        from ebm import editor_preview
        preview = editor_preview._preview
        if preview and preview.exit_monitor.markers and not self.reported:
            self.reported = True
            marker = preview.exit_monitor.markers[-1]
            print("LIVE_EXIT_FAILURE", marker["text"], len(preview.exit_monitor.failed))
`;
async function runSource(text){
  await page.locator('.cm-content').click();
  await page.keyboard.press('Control+a');await page.keyboard.insertText(text);await page.keyboard.press('Control+Enter');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Running'),null,{timeout:30000});
}
try{
  await page.goto(`http://127.0.0.1:${server.address().port}/editor.html`,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#status')?.textContent.includes('Running'),null,{timeout:120000});
  assert(await page.locator('#stop-on-first-failure').isChecked());
  await runSource(source);
  await page.locator('#preview').click();
  await page.waitForFunction(()=>document.querySelector('#console-output').textContent.includes('LIVE_EXIT_FAILURE R0:'),null,{timeout:15000});
  const redPixels=await page.locator('#preview').evaluate(canvas=>{
    const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
    let count=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]>140&&pixels[i+1]<70&&pixels[i+2]<70)count++;return count;
  });
  assert(redPixels>20,`expected red failure overlay, got ${redPixels} pixels`);
  await page.locator('#validate-button').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Stopped early'),null,{timeout:60000});
  assert.match(await page.locator('#validation-results').innerText(),/Skipped: stop on first failure/);
  assert.match(await page.locator('#validation-results').innerText(),/Stopped early/);
  await page.locator('.replay-failure').first().click();
  assert.equal(await page.locator('.replay-failure').first().innerText(),'Replaying…');
  await page.locator('#stop-on-first-failure').uncheck();
  assert.equal(await page.evaluate(()=>localStorage.getItem('ebm-stop-on-first-failure')),'false');
  await page.locator('#validate-button').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Flow validation failed'),null,{timeout:120000});
  const full=await page.locator('#validation-results').innerText();
  assert.match(full,/120\/120/);assert.doesNotMatch(full,/Skipped:/);assert.match(full,/3 × 3 repeat/);
  await page.locator('[data-view="simulation"]').click();
  await runSource('from ebm import TileBase\nclass CleanTile(TileBase):\n    author = "Tests"\n    def build(self, b): self.reported = False\n    def update(self, b, dt):\n        from ebm import editor_preview\n        if not self.reported:\n            self.reported = True\n            print("CLEAN_MARKERS", len(editor_preview._preview.exit_monitor.markers))\n');
  await page.waitForFunction(()=>document.querySelector('#console-output').textContent.includes('CLEAN_MARKERS 0'),null,{timeout:10000});
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#status')?.textContent.includes('Running'),null,{timeout:120000});
  assert.equal(await page.locator('#stop-on-first-failure').isChecked(),false);
  assert.deepEqual(errors,[]);
  console.log('PASS: live red failure overlays, default-on fail-fast, retained replay, full-report toggle and persisted preference');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
