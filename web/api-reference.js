const escapeHtml=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
const slug=value=>value.toLowerCase().replaceAll(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");

function propertyTable(properties){return `<table class="api-table"><thead><tr><th>Name</th><th>Type</th><th>Description</th></tr></thead><tbody>${properties.map(p=>`<tr><td><code>${escapeHtml(p.name)}</code>${p.required?'<br><span class="api-required">required</span>':""}</td><td><code>${escapeHtml(p.type)}</code></td><td>${escapeHtml(p.description)}</td></tr>`).join("")}</tbody></table>`}
function methods(items){return items.map(item=>`<article class="api-card"><h4><code>${escapeHtml(item.name)}</code></h4><code class="api-signature">${escapeHtml(item.name+item.signature)}</code><p>${escapeHtml(item.description)}</p></article>`).join("")}
function section(id,title,body){return `<section class="api-section" id="api-${id}" data-api-search="${escapeHtml((title+" "+body).replaceAll(/<[^>]*>/g," "))}"><h3>${escapeHtml(title)}</h3>${body}</section>`}
function coordinateMap(reference){return `<div class="coordinate-map" aria-label="200 by 200 local tile coordinates">${reference.ports.map(port=>{const [x,y]=port.point;return `<span class="port ${port.kind}" style="left:${x/reference.tileSize*100}%;top:${y/reference.tileSize*100}%">${escapeHtml(port.name)}</span>`}).join("")}<span class="axis" style="left:5px;top:5px">(0, 0)</span><span class="axis" style="right:5px;bottom:5px">(${reference.tileSize}, ${reference.tileSize})</span></div><p>Coordinates are local to each ${reference.tileSize} × ${reference.tileSize} tile. Green ports are inputs; red ports are outputs. Physical build points may extend at most 10 units beyond the edge.</p>`}
function render(reference){
  const skeleton=`<pre><code>class MyTile(TileBase):
    id = "local.my-tile"
    title = "My Tile"
    author = "Your name"
    api_version = 1
    routes = DEFAULT_ROUTES

    def __init__(self, route):
        self.route = route

    def build(self, tile):
        # tile is a TileBuilder
        pass

    def update(self, tile, dt):
        pass

TILE_CLASS = MyTile</code></pre>`;
  const sections=[
    ["class","Tile class",`<p>${escapeHtml(reference.tileBase.description)}</p>${skeleton}<h4>Properties</h4>${propertyTable(reference.tileBase.properties)}<h4>Lifecycle</h4>${methods(reference.tileBase.methods)}`],
    ["builder","TileBuilder",`<p>${escapeHtml(reference.tileBuilder.description)}</p>${methods(reference.tileBuilder.methods)}`],
    ["routes","Routes & coordinates",`${coordinateMap(reference)}<p>A <code>RoutePermutation</code> maps T0, L0, and R0 bijectively to B0, L1, and R1. Use <code>route.exit_for(entry)</code> to inspect the selected mapping.</p>`],
    ["events","Handles & events",`<p>Builder methods return ownership-checked handles. A tile can only inspect or remove its own resources. Resources are cleaned up automatically when the instance is destroyed.</p><h4>ContactEvent</h4>${propertyTable(reference.contactEvent.properties)}`],
    ["recipes","Recipes",reference.recipes.map(recipe=>`<article class="api-card"><h4>${escapeHtml(recipe.title)}</h4><p>${escapeHtml(recipe.description)}</p><pre><code>${escapeHtml(recipe.code)}</code></pre></article>`).join("")],
    ["scope","What API v1 can build",`<ul>${reference.limitations.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>`],
  ];
  document.getElementById("api-version").textContent=`API v${reference.apiVersion}`;
  document.getElementById("api-nav").innerHTML=sections.map(([id,title])=>`<button type="button" data-api-target="api-${id}">${escapeHtml(title)}</button>`).join("");
  document.getElementById("api-content").innerHTML=sections.map(args=>section(...args)).join("")+`<p class="api-empty" hidden>No matching API entries.</p>`;
  document.querySelectorAll("[data-api-target]").forEach(button=>button.onclick=()=>document.getElementById(button.dataset.apiTarget)?.scrollIntoView());
}

export async function initializeApiReference(){
  const drawer=document.getElementById("api-reference"),backdrop=document.getElementById("api-backdrop"),search=document.getElementById("api-search");
  const setOpen=open=>{drawer.classList.toggle("open",open);backdrop.classList.toggle("open",open);drawer.setAttribute("aria-hidden",String(!open));document.getElementById("api-button").setAttribute("aria-expanded",String(open));if(open)setTimeout(()=>search.focus(),210)};
  document.getElementById("api-button").onclick=()=>setOpen(true);document.getElementById("api-close").onclick=()=>setOpen(false);backdrop.onclick=()=>setOpen(false);document.addEventListener("keydown",event=>{if(event.key==="Escape")setOpen(false)});
  try{const response=await fetch("./api-reference.json",{cache:"no-store"});if(!response.ok)throw new Error(`HTTP ${response.status}`);render(await response.json())}catch(error){document.getElementById("api-content").innerHTML=`<p class="api-empty">Could not load API reference: ${escapeHtml(error.message)}</p>`}
  search.oninput=()=>{const query=search.value.trim().toLowerCase();let visible=0;document.querySelectorAll(".api-section").forEach(section=>{const show=!query||section.dataset.apiSearch.toLowerCase().includes(query);section.hidden=!show;if(show)visible++});document.querySelector(".api-empty").hidden=visible!==0};
}
