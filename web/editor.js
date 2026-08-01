import {initializeApiReference} from "./api-reference.js";

const PYMUNK_WHEEL="./vendor/pymunk-7.2.0-cp312-cp312-pyodide_2024_0_wasm32.whl";
const PY_FILES=["__init__.py","ports.py","random_utils.py","tile_base.py","tile_api.py","tile_catalog.py","tiles/__init__.py","tiles/builtin/__init__.py","tiles/builtin/powered_channel.py","tiles/builtin/reference_router.py","tiles/contributed/__init__.py","routes.py","validator.py","debug_demo.py","editor_runtime.py","editor_preview.py"];
const NEW_ID="__new__";
const NEW_SOURCE=`from ebm import DEFAULT_ROUTES, TileBase


class MyTile(TileBase):
    id = "local.my-tile"
    title = "My Tile"
    author = "Your name"
    api_version = 1
    routes = DEFAULT_ROUTES

    def __init__(self, route):
        if route not in self.routes:
            raise ValueError(f"unsupported route: {route}")
        self.route = route

    def build(self, tile):
        # Add physical and visual components here.
        # Coordinates are local to this 200 × 200 tile.
        pass


TILE_CLASS = MyTile
`;
const ids=["tile-select","route-select","status","validation-results","draft-state","cursor-position","preview","loading","tile-title","tile-id","tile-author","tile-origin"];
const els=Object.fromEntries(ids.map(id=>[id.replaceAll("-","_"),document.getElementById(id)]));
let pyodide,manifest,currentTile,originalSource="",mode="single",saveTimer,codeEditor;
const getSource=()=>codeEditor.getValue();
const setSource=value=>codeEditor.setValue(value);
const draftKey=id=>`ebm.editor.draft.${id}`;
const escapeHtml=s=>String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
const setStatus=(text,type="pending",detail="")=>{els.status.className=`status ${type}`;els.status.innerHTML=`<strong>${escapeHtml(text)}</strong>${detail?`<pre>${escapeHtml(detail)}</pre>`:""}`};
async function fetchText(url){const r=await fetch(url,{cache:"no-store"});if(!r.ok)throw new Error(`${url}: HTTP ${r.status}`);return r.text()}
async function writePackage(){for(const dir of ["/ebm","/ebm/tiles","/ebm/tiles/builtin","/ebm/tiles/contributed"])try{pyodide.FS.mkdir(dir)}catch{}for(const file of PY_FILES)pyodide.FS.writeFile(`/ebm/${file}`,await fetchText(`./ebm/${file}`));pyodide.runPython("import sys\nif '/' not in sys.path: sys.path.insert(0, '/')")}
function metadataFromSource(source){const value=name=>source.match(new RegExp(`^\\s*${name}\\s*=\\s*[\"']([^\"']*)[\"']`,`m`))?.[1]||"";return{title:value("title"),id:value("id"),author:value("author")}}
function replaceMetadata(name,value){const safe=value.replaceAll("\\","\\\\").replaceAll('"','\\"');const pattern=new RegExp(`^(\\s*${name}\\s*=\\s*)[\"'][^\"']*[\"']`,`m`),source=getSource();if(pattern.test(source))setSource(source.replace(pattern,`$1"${safe}"`));saveDraft()}
function updateMetadata(source,origin){const meta=metadataFromSource(source);els.tile_title.value=meta.title;els.tile_id.value=meta.id;els.tile_author.value=meta.author;els.tile_origin.textContent=origin}
async function loadTile(id){saveDraft();if(id===NEW_ID){currentTile={id:NEW_ID,title:"New tile",author:"Local",apiVersion:1};originalSource=NEW_SOURCE}else{currentTile=manifest.tiles.find(tile=>tile.id===id);originalSource=await fetchText(`./${currentTile.source}`)}const draft=localStorage.getItem(draftKey(id));setSource(draft??originalSource);els.draft_state.textContent=draft===null?(id===NEW_ID?"New skeleton":"Original"):"Modified locally";updateMetadata(getSource(),id===NEW_ID?"New local tile":`Based on ${currentTile.title} · API ${currentTile.apiVersion}`);await runSource()}
function updateRoutes(routes){const old=els.route_select.value;els.route_select.innerHTML="";routes.forEach((route,i)=>{const o=document.createElement("option");o.value=i;o.textContent=`T0→${route[0]} · L0→${route[1]} · R0→${route[2]}`;els.route_select.append(o)});if([...els.route_select.options].some(o=>o.value===old))els.route_select.value=old}
async function runSource(){setStatus("Building tile…");els.validation_results.innerHTML="";codeEditor.setErrorLine(null);try{const result=JSON.parse(pyodide.globals.get("compile_source")(getSource()));if(!result.ok){codeEditor.setErrorLine(result.line);setStatus(`${result.type||"Build error"}${result.line?` at line ${result.line}`:""}`,"fail",result.message);return}updateMetadata(getSource(),currentTile.id===NEW_ID?"New local tile":`Based on ${currentTile.title} · API ${currentTile.apiVersion}`);updateRoutes(result.routes);pyodide.globals.get("refresh_preview")(Number(els.route_select.value||0),mode);setStatus(`Running ${result.title}`,"ok",`${result.id} · ${result.routes.length} route${result.routes.length===1?"":"s"}`)}catch(error){setStatus("Runtime error","fail",error.stack||String(error))}}
async function validate(){setStatus("Validating all 243 sampled states per route…");els.validation_results.innerHTML="";await new Promise(r=>setTimeout(r,20));try{const result=JSON.parse(pyodide.globals.get("validate_source")());if(!result.results){setStatus("Validation failed","fail",result.message);return}setStatus(result.ok?"Strict validation passed":"Strict validation failed",result.ok?"ok":"fail");els.validation_results.innerHTML=`<table class="validation-table"><thead><tr><th>Route</th><th>Result</th><th>Exited</th><th>Failures</th></tr></thead><tbody>${result.results.map(r=>`<tr><td>${escapeHtml(r.route.label)}</td><td class="${r.ok?"pass":"fail-text"}">${r.ok?"PASS":"FAIL"}</td><td>${r.exited}/${r.balls_spawned}</td><td>${r.unexpected+r.out_of_bounds+r.stuck+r.active}</td></tr>`).join("")}</tbody></table>`}catch(error){setStatus("Validation error","fail",error.stack||String(error))}}
function saveDraft(){if(!currentTile)return;const source=getSource(),changed=source!==originalSource;if(changed)localStorage.setItem(draftKey(currentTile.id),source);else localStorage.removeItem(draftKey(currentTile.id));els.draft_state.textContent=changed?"Modified locally":(currentTile.id===NEW_ID?"New skeleton":"Original")}
function sourceChanged(source){const meta=metadataFromSource(source);els.tile_title.value=meta.title;els.tile_id.value=meta.id;els.tile_author.value=meta.author;clearTimeout(saveTimer);saveTimer=setTimeout(saveDraft,250)}
codeEditor=window.createEbmCodeEditor(document.getElementById("source-editor"),{doc:NEW_SOURCE,onChange:sourceChanged,onRun:()=>runSource(),onCursor:(line,col)=>els.cursor_position.textContent=`Ln ${line}, Col ${col}`});
[[els.tile_title,"title"],[els.tile_id,"id"],[els.tile_author,"author"]].forEach(([input,name])=>input.addEventListener("change",()=>replaceMetadata(name,input.value)));
document.getElementById("run-button").onclick=runSource;document.getElementById("validate-button").onclick=validate;els.route_select.onchange=()=>pyodide.globals.get("refresh_preview")(Number(els.route_select.value),mode);document.querySelectorAll("[data-mode]").forEach(button=>button.onclick=()=>{mode=button.dataset.mode;document.querySelectorAll("[data-mode]").forEach(b=>b.classList.toggle("active",b===button));pyodide.globals.get("refresh_preview")(Number(els.route_select.value),mode)});els.tile_select.onchange=()=>loadTile(els.tile_select.value);document.getElementById("reset-button").onclick=()=>{if(confirm("Discard the local draft and restore the skeleton/original source?")){setSource(originalSource);saveDraft();updateMetadata(getSource(),currentTile.id===NEW_ID?"New local tile":`Based on ${currentTile.title} · API ${currentTile.apiVersion}`);runSource()}};document.getElementById("download-button").onclick=()=>{const source=getSource(),meta=metadataFromSource(source),blob=new Blob([source],{type:"text/x-python"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`${(meta.id||"my-tile").replaceAll(/[^a-z0-9._-]/gi,"-")}.py`;a.click();URL.revokeObjectURL(a.href)};document.getElementById("import-button").onclick=()=>document.getElementById("import-file").click();document.getElementById("import-file").onchange=async e=>{const file=e.target.files[0];if(file){setSource(await file.text());saveDraft();updateMetadata(getSource(),`Imported from ${file.name}`);runSource()}e.target.value=""};
async function main(){try{manifest=await (await fetch("./tiles/manifest.json",{cache:"no-store"})).json();els.tile_select.innerHTML="";els.tile_select.add(new Option("＋ New tile (skeleton)",NEW_ID));manifest.tiles.forEach(tile=>els.tile_select.add(new Option(tile.title,tile.id)));setStatus("Loading Pyodide…");pyodide=await loadPyodide();await pyodide.loadPackage("cffi");await pyodide.loadPackage(new URL(PYMUNK_WHEEL,location.href).href);await writePackage();pyodide.runPython("from ebm.editor_runtime import compile_source, validate_source\nfrom ebm.editor_preview import start, refresh as refresh_preview");const initialResult=JSON.parse(pyodide.globals.get("compile_source")(NEW_SOURCE));if(!initialResult.ok)throw new Error(initialResult.message);pyodide.globals.get("start")(els.preview);await loadTile(NEW_ID);els.loading.classList.add("hidden")}catch(error){els.loading.innerHTML=`<div><h2>Editor failed to start</h2><pre>${escapeHtml(error.stack||error)}</pre></div>`}}
initializeApiReference();
main();
