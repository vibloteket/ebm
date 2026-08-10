const escapeHtml=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");

function propertyTable(properties){return `<table class="api-table"><thead><tr><th>Name</th><th>Type</th><th>Description</th></tr></thead><tbody>${properties.map(p=>`<tr><td><code>${escapeHtml(p.name)}</code>${p.required?'<br><span class="api-required">required</span>':""}</td><td><code>${escapeHtml(p.type)}</code></td><td>${escapeHtml(p.description)}</td></tr>`).join("")}</tbody></table>`}
function methods(items){return items.map(item=>`<article class="api-card"><h4><code>${escapeHtml(item.name)}</code></h4><code class="api-signature">${escapeHtml(item.name+item.signature)}</code><p>${escapeHtml(item.description)}</p></article>`).join("")}
function section(id,title,body){return `<section class="api-section" id="api-${id}" data-api-search="${escapeHtml((title+" "+body).replaceAll(/<[^>]*>/g," "))}"><h3>${escapeHtml(title)}</h3>${body}</section>`}
function list(items){return `<ul>${items.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>`}
function coordinateMap(reference){return `<div class="coordinate-map" aria-label="${reference.tileSize} by ${reference.tileSize} local tile coordinates">${reference.ports.map(port=>{const [x,y]=port.point;return `<span class="port ${port.kind}" style="left:${x/reference.tileSize*100}%;top:${y/reference.tileSize*100}%">${escapeHtml(port.name)}</span>`}).join("")}<span class="axis" style="left:5px;top:5px">(0, 0)</span><span class="axis" style="right:5px;bottom:5px">(${reference.tileSize}, ${reference.tileSize})</span></div>`}
function portRange(port,aperture){const [x,y]=port.point,half=aperture/2,side=port.name.startsWith("L")||port.name.startsWith("R");return side?`y = ${y-half}–${y+half}`:`x = ${x-half}–${x+half}`}
function centerRange(port,range){const [x,y]=port.point,side=port.name.startsWith("L")||port.name.startsWith("R");return side?`y = ${y-range}–${y+range}`:`x = ${x-range}–${x+range}`}
function render(reference){
  const rules=reference.portRules;
  const validation=reference.validation;
  const flow=reference.flow;
  const skeleton=`<pre><code>class MyTile(TileBase):
    id = "local.my-tile"
    title = "My Tile"
    author = "Your name"
    api_version = ${reference.apiVersion}

    def build(self, builder):
        pass

    def update(self, builder, dt):
        pass

TILE_CLASS = MyTile</code></pre>`;
  const sections=[
    ["start","Getting started",`<p>A tile is a self-contained ${reference.tileSize} × ${reference.tileSize} mechanism running on Python 3.14. Define its metadata, create geometry in <code>build()</code>, and optionally animate it in <code>update()</code>.</p>${skeleton}<p>Press <strong>Run</strong> to preview changes, then <strong>Validate flow</strong> to check the tile contract.</p><h4>Common types</h4>${propertyTable(reference.commonTypes)}`],
    ["ports","Ports & coordinates",`${coordinateMap(reference)}<p>Coordinates are local to the tile. <code>(0, 0)</code> is the upper-left corner; x increases to the right and y increases downward. Green ports are inputs and red ports are outputs.</p><h4>Port positions and openings</h4><table class="api-table"><thead><tr><th>Port</th><th>Kind</th><th>Center</th><th>Full opening</th><th>Ball-center range</th></tr></thead><tbody>${reference.ports.map(port=>`<tr><td><code>${port.name}</code></td><td>${port.kind}</td><td><code>(${port.point[0]}, ${port.point[1]})</code></td><td><code>${portRange(port,rules.aperture)}</code></td><td><code>${centerRange(port,rules.centerRange)}</code></td></tr>`).join("")}</tbody></table><p>The full opening includes the whole ${rules.aperture}-unit gap. Since a ball has radius ${rules.ballRadius}, its center uses the narrower range shown in the last column.</p><h4>Ball size and arrival</h4>${list([
      `Every ball has radius ${rules.ballRadius} and diameter ${rules.ballDiameter} tile units.`,
      `Balls can arrive at any speed from nearly stationary up to the global cap of ${flow.maxBallSpeed} units per second; validation samples ${flow.entryTestSpeeds.join(", ")} units per second.`,
      `The current validator introduces one ball every ${flow.spawnInterval} seconds overall. Inputs rotate between T0, L0, and R0, so the nominal interval at each individual input is ${flow.perInputInterval} seconds.`,
      "Do not rely on a fixed interval: balls from neighboring tiles can be delayed, grouped, or arrive independently.",
    ])}<h4>Flow rules</h4>${list([
      "A ball may enter through T0, L0, or R0 and leave through any valid output: B0, L1, or R1. There are no fixed input-to-output routes.",
      `Every port opening is ${rules.aperture} units wide. A ball has radius ${rules.ballRadius}, so its center may be at most ${rules.centerRange} units from the port center.`,
      "Balls may arrive off-center and with different speeds and angles. Do not rely on centered, synchronized input.",
      "A valid exit passes the complete ball through an output opening while moving outward within 30° of the edge normal.",
      "Leaving through the top edge, outside an output opening, or at an invalid angle fails validation.",
      `Build points and segment radii may extend at most ${rules.buildMargin} units beyond the tile, allowing smooth transitions at edges and ports.`,
    ])}`],
    ["validation","Validation rules",`<p><strong>Validate flow</strong> runs the current strict, concurrent flow test:</p>${list([
      `${validation.balls} balls enter as one continuous, unsynchronized stream distributed across all three inputs.`,
      "Entry position, speed, and angle vary across the supported input contract.",
      `At most ${validation.maxActive} balls may be active inside the tile at once. This includes stored balls and balls still travelling through it.`,
      "Balls must not disappear, be removed, acquire non-finite physics state, or leave through an invalid boundary.",
      "All three outputs must receive at least one ball.",
      "There is no drain phase after the final ball enters; balls physically present at that point count as active inventory.",
    ])}<p class="api-note">These values describe the current validator. The durable contract is to accept varied input, conserve every ball, produce valid exits, and keep retention bounded.</p>`],
    ["class","Tile class",`<p>${escapeHtml(reference.tileBase.description)}</p><h4>Properties</h4>${propertyTable(reference.tileBase.properties)}<h4>Lifecycle</h4>${methods(reference.tileBase.methods)}`],
    ["builder","TileBuilder",`<p>${escapeHtml(reference.tileBuilder.description)}</p>${methods(reference.tileBuilder.methods)}`],
    ["events","Handles & events",`<p>Builder methods return ownership-checked handles. Change an existing object through its handle; resources are cleaned up automatically when the tile instance is destroyed.</p>${(reference.handles||[]).map(handle=>`<h4>${escapeHtml(handle.name)}</h4><p>${escapeHtml(handle.description)}</p>${methods(handle.methods)}`).join("")}<h4>ContactEvent</h4>${propertyTable(reference.contactEvent.properties)}`],
    ["recipes","Recipes",reference.recipes.map(recipe=>`<article class="api-card"><h4>${escapeHtml(recipe.title)}</h4><p>${escapeHtml(recipe.description)}</p><pre><code>${escapeHtml(recipe.code)}</code></pre></article>`).join("")],
    ["scope",`API v${reference.apiVersion} capabilities`,`<h4>Available</h4>${list(reference.capabilities.available)}<h4>Not available yet</h4>${list(reference.capabilities.unavailable)}<p>Tile code uses ownership-checked handles so one tile cannot accidentally modify another tile or the shared machine simulation.</p>`],
  ];
  document.getElementById("api-version").textContent=`Tile API v${reference.apiVersion}`;
  document.getElementById("api-nav").innerHTML=sections.map(([id,title])=>`<button type="button" data-api-target="api-${id}">${escapeHtml(title)}</button>`).join("");
  document.getElementById("api-content").innerHTML=sections.map(args=>section(...args)).join("")+`<p class="api-empty" hidden>No matching help entries.</p>`;
  document.querySelectorAll("[data-api-target]").forEach(button=>button.onclick=()=>document.getElementById(button.dataset.apiTarget)?.scrollIntoView());
}

export async function initializeApiReference(){
  const drawer=document.getElementById("api-reference"),backdrop=document.getElementById("api-backdrop"),search=document.getElementById("api-search");
  const setOpen=open=>{drawer.classList.toggle("open",open);backdrop.classList.toggle("open",open);drawer.setAttribute("aria-hidden",String(!open));document.getElementById("api-button").setAttribute("aria-expanded",String(open));if(open)setTimeout(()=>search.focus(),210)};
  document.getElementById("api-button").onclick=()=>setOpen(true);document.getElementById("api-close").onclick=()=>setOpen(false);backdrop.onclick=()=>setOpen(false);document.addEventListener("keydown",event=>{if(event.key==="Escape")setOpen(false)});
  try{const response=await fetch("./api-reference.json",{cache:"no-store"});if(!response.ok)throw new Error(`HTTP ${response.status}`);render(await response.json())}catch(error){document.getElementById("api-content").innerHTML=`<p class="api-empty">Could not load tile help: ${escapeHtml(error.message)}</p>`}
  search.oninput=()=>{const query=search.value.trim().toLowerCase();let visible=0;document.querySelectorAll(".api-section").forEach(section=>{const show=!query||section.dataset.apiSearch.toLowerCase().includes(query);section.hidden=!show;if(show)visible++});document.querySelector(".api-empty").hidden=visible!==0};
}
