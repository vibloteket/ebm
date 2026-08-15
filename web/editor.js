import {initializeApiReference} from "./api-reference.js?v=0.68";

const PYMUNK_WHEEL="./vendor/pymunk-7.3.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl";
const PY_FILES=["__init__.py","ball_physics.py","ports.py","random_utils.py","tile_base.py","tile_api.py","tile_catalog.py","editor_console.py","tiles/__init__.py","tiles/builtin/__init__.py","tiles/builtin/powered_channel.py","tiles/builtin/reference_router.py","tiles/contributed/__init__.py","tiles/contributed/segment_switchback.py","tiles/contributed/teleport_collector.py","validator.py","debug_demo.py","editor_runtime.py","editor_preview.py"];
const NEW_ID="__new__";
const NEW_SOURCE=`from ebm import TileBase, TileBuilder


class MyTile(TileBase):
    author = "Your name"

    def build(self, b: TileBuilder):
        # Add physical and visual components with b.
        # Coordinates are local to this 400 × 400 tile.
        pass

`;
const ids=["tile-select","status","validation-results","draft-state","cursor-position","preview","loading","console-output","console-count"];
const els=Object.fromEntries(ids.map(id=>[id.replaceAll("-","_"),document.getElementById(id)]));
let pyodide,manifest,currentTile,originalSource="",mode="single",view="simulation",paused=false,saveTimer,consoleTimer,consoleLines=[],codeEditor;
const getSource=()=>codeEditor.getValue();
const setSource=value=>codeEditor.setValue(value);
const draftKey=id=>`ebm.editor.simple.draft.${id}`;
const escapeHtml=s=>String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
const setStatus=(text,type="pending",detail="")=>{els.status.className=`status ${type}`;els.status.innerHTML=`<strong>${escapeHtml(text)}</strong>${detail?`<pre>${escapeHtml(detail)}</pre>`:""}`};
function renderConsole(){els.console_count.textContent=consoleLines.length;els.console_output.innerHTML=consoleLines.length?consoleLines.map(entry=>`<div class="console-line ${entry.stream}"><span class="console-phase">[${escapeHtml(entry.phase)}]</span><span class="console-stream">${escapeHtml(entry.stream)}</span><span class="console-text">${escapeHtml(entry.text)}</span></div>`).join(""):'<div class="console-empty">Output from print() will appear here.</div>';els.console_output.scrollTop=els.console_output.scrollHeight}
function drainConsole(){if(!pyodide)return;const entries=JSON.parse(pyodide.globals.get("drain_editor_console")());if(entries.length){consoleLines.push(...entries);if(consoleLines.length>500)consoleLines=consoleLines.slice(-500);renderConsole()}}
async function fetchText(url){const r=await fetch(url,{cache:"no-store"});if(!r.ok)throw new Error(`${url}: HTTP ${r.status}`);return r.text()}
async function writePackage(){for(const dir of ["/ebm","/ebm/tiles","/ebm/tiles/builtin","/ebm/tiles/contributed"])try{pyodide.FS.mkdir(dir)}catch{}for(const file of PY_FILES)pyodide.FS.writeFile(`/ebm/${file}`,await fetchText(`./ebm/${file}`));pyodide.runPython("import sys\nif '/' not in sys.path: sys.path.insert(0, '/')")}
function classNameFromSource(source){return source.match(/^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*TileBase\s*\)/m)?.[1]||"Tile"}
function filenameFromClass(name){return name.replace(/([a-z0-9])([A-Z])/g,"$1_$2").replace(/([A-Za-z])([0-9])/g,"$1_$2").toLowerCase()+".py"}
async function loadTile(id){saveDraft();if(id===NEW_ID){currentTile={id:NEW_ID,title:"My Tile",author:""};originalSource=NEW_SOURCE}else{currentTile=manifest.tiles.find(tile=>tile.id===id);originalSource=await fetchText(`./${currentTile.source}`)}const draft=localStorage.getItem(draftKey(id));setSource(draft??originalSource);els.draft_state.textContent=draft===null?(id===NEW_ID?"New skeleton":"Original"):"Modified locally";await runSource()}
async function runSource(){setStatus("Building tile…");els.validation_results.innerHTML="";codeEditor.setErrorLine(null);try{const result=JSON.parse(pyodide.globals.get("compile_source")(getSource()));if(!result.ok){codeEditor.setErrorLine(result.line);setStatus(`${result.type||"Build error"}${result.line?` at line ${result.line}`:""}`,"fail",result.message);return}pyodide.globals.get("refresh_preview")(mode);setStatus(`Running ${result.displayName}`,"ok",`by ${result.author}`)}catch(error){setStatus("Runtime error","fail",error.stack||String(error))}finally{drainConsole()}}
function syncPreviewSize(){
  const canvas=els.preview,width=Math.max(300,Math.round(canvas.clientWidth)),height=Math.max(260,Math.round(canvas.clientHeight));
  if(canvas.width!==width)canvas.width=width;if(canvas.height!==height)canvas.height=height;
}
new ResizeObserver(syncPreviewSize).observe(els.preview);
function setView(nextView){
  view=nextView==="validation"?"validation":"simulation";
  document.querySelectorAll("[data-view]").forEach(button=>button.classList.toggle("active",button.dataset.view===view));
  document.querySelectorAll(".simulation-control").forEach(control=>control.hidden=view!=="simulation");
  els.validation_results.hidden=view!=="validation";
  pyodide?.globals.get("set_preview_view")?.(view);
  if(view==="simulation")pyodide?.globals.get("refresh_preview")?.(mode);
}
function renderValidation(r){
  const failures=r.details.filter(detail=>detail.status==="invalid"||detail.status==="lost");
  const groups=new Map();
  for(const detail of failures){
    const key=`${detail.entry}|${detail.exit}`;
    const group=groups.get(key)||{entry:detail.entry,reason:detail.exit,count:0,examples:[]};
    group.count+=1;if(group.examples.length<3)group.examples.push(detail);groups.set(key,group);
  }
  const summary=`<table class="validation-table"><thead><tr><th>Result</th><th>Entered</th><th>Exited</th><th>Active</th><th>Peak</th><th>B0</th><th>R0</th><th>Invalid/lost</th></tr></thead><tbody><tr><td class="${r.ok?"pass":"fail-text"}">${r.ok?"PASS":"FAIL"}</td><td>${r.balls_spawned}</td><td>${r.exited}</td><td>${r.active}/${r.max_active_allowed}</td><td>${r.peak_active}/${r.max_active_allowed}</td><td>${r.output_counts.B0}</td><td>${r.output_counts.R0}</td><td>${r.invalid+r.lost}</td></tr></tbody></table>`;
  if(!failures.length)return summary;
  const diagnostics=[...groups.values()].map(group=>`<section class="failure-group"><h3>${group.count} × ${escapeHtml(group.entry)} → ${escapeHtml(group.reason)}</h3><p>${escapeHtml(group.examples[0].message||"Outside the flow contract")}</p>${group.examples.map(detail=>`<div class="failure-example"><code>#${detail.id} · pos (${detail.position.join(", ")}) · vel (${detail.velocity.join(", ")})</code><button type="button" class="replay-failure" data-failure-id="${detail.id}">Replay</button></div>`).join("")}</section>`).join("");
  return `${summary}<div class="failure-diagnostics"><h2>Why it failed</h2><p>Grouped by input and failure reason. Replay shows the red ball's validator path in the preview.</p>${diagnostics}</div>`;
}
async function validate(){
  setView("validation");pyodide.globals.get("refresh_preview")("single");
  setStatus("Validating 120-ball concurrent flow…");els.validation_results.innerHTML="";await new Promise(r=>setTimeout(r,20));
  try{
    const result=JSON.parse(pyodide.globals.get("validate_source")());if(!result.result){setStatus("Validation failed","fail",result.message);return}
    const r=result.result;setStatus(result.ok?"Flow validation passed":"Flow validation failed",result.ok?"ok":"fail");els.validation_results.innerHTML=renderValidation(r);
    const failures=new Map(r.details.filter(detail=>detail.status==="invalid"||detail.status==="lost").map(detail=>[String(detail.id),detail]));
    els.validation_results.querySelectorAll(".replay-failure").forEach(button=>button.addEventListener("click",()=>{const detail=failures.get(button.dataset.failureId);if(detail){setView("validation");pyodide.globals.get("refresh_preview")("single");pyodide.globals.get("set_preview_view")("validation");pyodide.globals.get("replay_validation_failure")(JSON.stringify(detail));els.validation_results.querySelectorAll(".replay-failure").forEach(item=>item.textContent="Replay");button.textContent="Replaying…"}}));
  }catch(error){setStatus("Validation error","fail",error.stack||String(error))}finally{drainConsole()}
}
function saveDraft(){if(!currentTile)return;const source=getSource(),changed=source!==originalSource;if(changed)localStorage.setItem(draftKey(currentTile.id),source);else localStorage.removeItem(draftKey(currentTile.id));els.draft_state.textContent=changed?"Modified locally":(currentTile.id===NEW_ID?"New skeleton":"Original")}
function sourceChanged(_source){clearTimeout(saveTimer);saveTimer=setTimeout(saveDraft,250)}
codeEditor=window.createEbmCodeEditor(document.getElementById("source-editor"),{doc:NEW_SOURCE,onChange:sourceChanged,onRun:()=>runSource(),onCursor:(line,col)=>els.cursor_position.textContent=`Ln ${line}, Col ${col}`});
document.querySelectorAll("[data-view]").forEach(button=>button.onclick=()=>setView(button.dataset.view));
document.getElementById("console-clear").onclick=()=>{consoleLines=[];pyodide?.globals.get("clear_editor_console")?.();renderConsole()};document.getElementById("console-copy").onclick=async event=>{const text=consoleLines.map(entry=>`[${entry.phase}] ${entry.stream}: ${entry.text}`).join("\n");try{await navigator.clipboard.writeText(text);event.currentTarget.textContent="Copied";setTimeout(()=>event.currentTarget.textContent="Copy",1200)}catch{event.currentTarget.textContent="Copy failed"}};document.getElementById("console-expand").onclick=event=>{const pane=document.querySelector(".code-pane"),expanded=pane.classList.toggle("console-expanded");pane.classList.remove("console-collapsed");document.getElementById("console-panel").classList.remove("collapsed");document.getElementById("console-toggle").setAttribute("aria-expanded","true");event.currentTarget.setAttribute("aria-pressed",String(expanded));event.currentTarget.textContent=expanded?"Shrink":"Expand"};document.getElementById("console-toggle").onclick=event=>{const panel=document.getElementById("console-panel"),pane=document.querySelector(".code-pane"),collapsed=panel.classList.toggle("collapsed");pane.classList.toggle("console-collapsed",collapsed);pane.classList.remove("console-expanded");document.getElementById("console-expand").textContent="Expand";document.getElementById("console-expand").setAttribute("aria-pressed","false");event.currentTarget.setAttribute("aria-expanded",String(!collapsed))};document.getElementById("run-button").onclick=runSource;document.getElementById("validate-button").onclick=validate;document.getElementById("pause-button").onclick=event=>{paused=!paused;pyodide.globals.get("set_preview_paused")(paused);event.currentTarget.textContent=paused?"Resume simulation":"Pause simulation";event.currentTarget.setAttribute("aria-pressed",String(paused))};document.querySelectorAll("[data-mode]").forEach(button=>button.onclick=()=>{mode=button.dataset.mode;document.querySelectorAll("[data-mode]").forEach(b=>b.classList.toggle("active",b===button));pyodide.globals.get("refresh_preview")(mode)});els.tile_select.onchange=()=>loadTile(els.tile_select.value);document.getElementById("reset-button").onclick=()=>{if(confirm("Discard the local draft and restore the skeleton/original source?")){setSource(originalSource);saveDraft();runSource()}};document.getElementById("download-button").onclick=()=>{const source=getSource(),blob=new Blob([source],{type:"text/x-python"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=filenameFromClass(classNameFromSource(source));a.click();URL.revokeObjectURL(a.href)};document.getElementById("import-button").onclick=()=>document.getElementById("import-file").click();document.getElementById("import-file").onchange=async e=>{const file=e.target.files[0];if(file){setSource(await file.text());saveDraft();runSource()}e.target.value=""};
async function main(){try{manifest=await (await fetch("./tiles/manifest.json",{cache:"no-store"})).json();els.tile_select.innerHTML="";els.tile_select.add(new Option("＋ New tile (skeleton)",NEW_ID));manifest.tiles.forEach(tile=>els.tile_select.add(new Option(tile.title,tile.id)));setStatus("Loading Pyodide…");pyodide=await loadPyodide();await pyodide.loadPackage("cffi");await pyodide.loadPackage(new URL(PYMUNK_WHEEL,location.href).href);await writePackage();pyodide.runPython("from ebm.editor_console import install_console, drain_console as drain_editor_console, clear_console as clear_editor_console\ninstall_console()\nfrom ebm.editor_runtime import compile_source, validate_source\nfrom ebm.editor_preview import start, refresh as refresh_preview, set_paused as set_preview_paused, set_view as set_preview_view, replay_failure as replay_validation_failure");consoleTimer=setInterval(drainConsole,200);const initialResult=JSON.parse(pyodide.globals.get("compile_source")(NEW_SOURCE));if(!initialResult.ok)throw new Error(initialResult.message);pyodide.globals.get("start")(els.preview);await loadTile(NEW_ID);els.loading.classList.add("hidden")}catch(error){els.loading.innerHTML=`<div><h2>Editor failed to start</h2><pre>${escapeHtml(error.stack||error)}</pre></div>`}}
initializeApiReference();
main();
