const cards = [...document.querySelectorAll(".sample")];
const pigmentControl = document.querySelector("#pigment");
const grainControl = document.querySelector("#grain");
const animateButton = document.querySelector("#animate");
const selection = document.querySelector("#selection");
const shaderStatus = document.querySelector("#shader-status");
const shaderOriginalStatus = document.querySelector("#shader-original-status");
const SIZE = { w: 700, h: 430 };
let animation = true;
let angle = 0;
let ballTime = 0;
let previous = performance.now();

const state = () => ({
  pigment: Number(pigmentControl.value) / 100,
  grain: Number(grainControl.value) / 100,
});

function rng(seed) {
  let n = seed >>> 0;
  return () => ((n = Math.imul(1664525, n) + 1013904223 >>> 0) / 4294967296);
}

function fitCanvas(canvas) {
  const dpr = Math.min(devicePixelRatio || 1, 1.75);
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(1, Math.round(rect.width * dpr));
  const h = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  return { sx: w / SIZE.w, sy: h / SIZE.h, dpr };
}

function paper(ctx, s, grain, seed = 11) {
  ctx.fillStyle = "#f4e8c8";
  ctx.fillRect(0, 0, SIZE.w, SIZE.h);
  const r = rng(seed);
  ctx.fillStyle = `rgba(91,67,35,${0.035 * grain})`;
  for (let i = 0; i < 2800 * grain; i++) {
    const x = r() * SIZE.w, y = r() * SIZE.h;
    ctx.fillRect(x, y, .35 + r() * 1.25, .25 + r() * .65);
  }
  const g = ctx.createRadialGradient(350, 190, 20, 350, 215, 440);
  g.addColorStop(0, "rgba(255,255,255,.10)"); g.addColorStop(1, "rgba(112,76,29,.08)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, SIZE.w, SIZE.h);
}

const rails = [
  [55,72,220,154], [220,154,330,225], [330,225,480,128], [480,128,652,205],
  [48,350,200,294], [200,294,320,355], [390,350,530,294], [530,294,665,340],
];
const bumpers = [[180,100,22], [340,122,27], [530,92,21], [272,285,20], [596,252,23]];
const wheels = [[208,224,54], [486,236,67]];

function wheelGeometry(drawLine, drawCircle, a) {
  for (const [cx, cy, radius] of wheels) {
    drawCircle(cx, cy, radius);
    drawCircle(cx, cy, 13);
    for (let i = 0; i < 8; i++) {
      const q = a + i * Math.PI / 4;
      drawLine(cx + Math.cos(q) * 15, cy + Math.sin(q) * 15, cx + Math.cos(q) * (radius - 8), cy + Math.sin(q) * (radius - 8));
    }
  }
}

function staticScene(drawLine, drawCircle) {
  rails.forEach(v => drawLine(...v));
  bumpers.forEach(v => drawCircle(...v));
}

function scene(drawLine, drawCircle, a) {
  staticScene(drawLine, drawCircle);
  wheelGeometry(drawLine, drawCircle, a);
}

function ballPosition(t) {
  // A repeatable bouncing arc through the scene, shared by every renderer.
  const phase = (t % 4.8) / 4.8;
  const x = -25 + phase * 750;
  const bounce = Math.abs(Math.sin(phase * Math.PI * 3));
  return { x, y: 335 - bounce * 190, r: 15 };
}

function canvasBall(ctx, x, y, radius, dry = false) {
  texturedCircle(ctx, x, y, radius, dry ? "#175db8" : "#176bd0", 982451, dry);
  ctx.beginPath();
  ctx.arc(x - 4, y - 5, 3.2, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(220,240,255,.7)";
  ctx.fill();
} 

function setup2d(canvas) {
  const size = fitCanvas(canvas); const ctx = canvas.getContext("2d");
  ctx.setTransform(size.sx, 0, 0, size.sy, 0, 0); return ctx;
}

function stampLine(ctx, x1,y1,x2,y2, color, width, seed, dry=false) {
  const random = rng(seed), cfg = state();
  const dx=x2-x1, dy=y2-y1, distance=Math.hypot(dx,dy), nx=-dy/distance, ny=dx/distance;

  // A strong, readable pigment body first; texture is variation within it,
  // rather than thousands of almost-transparent dots trying to form the line.
  ctx.save();
  ctx.strokeStyle=color; ctx.lineCap="round"; ctx.lineWidth=width;
  ctx.globalAlpha=(dry ? .50 : .68)*cfg.pigment;
  ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();

  const steps=Math.max(3,Math.ceil(distance/(dry?5.8:4.4)));
  for(let i=0;i<steps;i++) {
    const t=i/(steps-1), spread=(random()-.5)*width*.72;
    if(dry && random()<.18+cfg.grain*.20) continue;
    const x=x1+dx*t+nx*spread, y=y1+dy*t+ny*spread;
    ctx.globalAlpha=(dry?.12+random()*.24:.10+random()*.18)*cfg.pigment;
    ctx.fillStyle=random()<.18?"#183472":color;
    ctx.beginPath();
    ctx.ellipse(x,y,width*(.18+random()*.22),width*(.10+random()*.15),Math.atan2(dy,dx)+(random()-.5)*.5,0,Math.PI*2);
    ctx.fill();
  }
  ctx.restore();
}

function texturedCircle(ctx,x,y,radius,color,seed,dry) {
  const random=rng(seed), cfg=state();
  ctx.save(); ctx.beginPath(); ctx.arc(x,y,radius,0,Math.PI*2); ctx.clip();
  ctx.globalAlpha=(dry?.48:.68)*cfg.pigment; ctx.fillStyle=color; ctx.fillRect(x-radius,y-radius,radius*2,radius*2);
  for(let i=0;i<radius*radius*(dry?.055:.08);i++) {
    if(dry&&random()<.25)continue;
    ctx.globalAlpha=(.10+random()*.28)*cfg.pigment;
    ctx.fillStyle=random()<.2?"#a94a16":color;
    const q=random()*Math.PI*2,rr=Math.sqrt(random())*radius;
    ctx.beginPath();ctx.ellipse(x+Math.cos(q)*rr,y+Math.sin(q)*rr,1+random()*3.8,.5+random()*1.8,random()*Math.PI,0,Math.PI*2);ctx.fill();
  }
  ctx.restore();ctx.globalAlpha=1;ctx.strokeStyle="rgba(92,44,14,.72)";ctx.lineWidth=dry?2.5:1.8;ctx.stroke();
}

const wheelSprites=new Map();
function wheelSprite(radius,dry) {
  const cfg=state(),key=[radius,dry,Math.round(cfg.pigment*100),Math.round(cfg.grain*100)].join(":");
  if(wheelSprites.has(key))return wheelSprites.get(key);
  const scale=2,pad=12,size=(radius+pad)*2,sprite=document.createElement("canvas");
  sprite.width=size*scale;sprite.height=size*scale;
  const ctx=sprite.getContext("2d");ctx.scale(scale,scale);ctx.translate(size/2,size/2);
  const line=(x1,y1,x2,y2)=>stampLine(ctx,x1,y1,x2,y2,dry?"#c55c1d":"#dc7925",dry?9:11,7000+Math.round((x2+radius)*37+(y2+radius)*19),dry);
  texturedCircle(ctx,0,0,radius,dry?"#cf6821":"#df7a24",8800+radius,dry);
  // Cut the centre back to paper transparency before adding a textured hub.
  ctx.save();ctx.globalCompositeOperation="destination-out";ctx.beginPath();ctx.arc(0,0,radius-9,0,Math.PI*2);ctx.fill();ctx.restore();
  for(let i=0;i<8;i++){const q=i*Math.PI/4;line(Math.cos(q)*15,Math.sin(q)*15,Math.cos(q)*(radius-8),Math.sin(q)*(radius-8));}
  texturedCircle(ctx,0,0,13,dry?"#c85e1d":"#df7822",9900+radius,dry);
  const result={image:sprite,size};wheelSprites.set(key,result);return result;
}

function drawCachedWheel(ctx,cx,cy,radius,angle,dry){const sprite=wheelSprite(radius,dry);ctx.save();ctx.translate(cx,cy);ctx.rotate(angle);ctx.drawImage(sprite.image,-sprite.size/2,-sprite.size/2,sprite.size,sprite.size);ctx.restore();}

function renderCanvas(canvas,a,dry) {
  const ctx=setup2d(canvas),cfg=state();paper(ctx,null,cfg.grain,dry?24:17);
  const line=(x1,y1,x2,y2)=>stampLine(ctx,x1,y1,x2,y2,dry?"#263f84":"#264c9d",dry?18:23,Math.round(x1*31+y2*19),dry);
  const circle=(x,y,r)=>texturedCircle(ctx,x,y,r,dry?"#cf6e25":"#dc7925",Math.round(x*17+y*23),dry);
  staticScene(line,circle);
  wheels.forEach(([x,y,r])=>drawCachedWheel(ctx,x,y,r,a,dry));
  const ball=ballPosition(ballTime);canvasBall(ctx,ball.x,ball.y,ball.r,dry);
}

const vertex = `#version 300 es
in vec2 p; out vec2 uv; void main(){uv=p*.5+.5;gl_Position=vec4(p,0.,1.);}`;
const fragment = `#version 300 es
precision highp float;
in vec2 uv; out vec4 outColor;
uniform vec2 resolution; uniform vec2 ball;
uniform float pigment; uniform float grain; uniform float angle;

float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1)),f.x),f.y);}
float sdSeg(vec2 p,vec2 a,vec2 b){vec2 pa=p-a,ba=b-a;float h=clamp(dot(pa,ba)/dot(ba,ba),0.,1.);return length(pa-ba*h);}
vec2 rotateLocal(vec2 p,float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c)*p;}
float wheelShape(vec2 q,float r){float d=min(abs(length(q)-r),abs(length(q)-13.));for(int k=0;k<8;k++){float a=float(k)*.785398;d=min(d,sdSeg(q,vec2(cos(a),sin(a))*15.,vec2(cos(a),sin(a))*(r-8.)));}return d;}
float fbm(vec2 p){
  float value=0.;
  value+=noise(p)*.533;
  p=mat2(1.63,-1.17,1.17,1.63)*p+vec2(7.1,3.7);
  value+=noise(p)*.267;
  p=mat2(1.71,.93,-.93,1.71)*p+vec2(5.3,11.9);
  value+=noise(p)*.133;
  p=mat2(1.47,-1.29,1.29,1.47)*p+vec2(13.7,2.1);
  value+=noise(p)*.067;
  return value;
}
float edgeWarp(vec2 local,float seed){
  float broad=fbm(local*.052+vec2(seed*5.7,-seed*2.1));
  float chips=fbm(local*.145+vec2(-seed*3.3,seed*7.9));
  // Continuous width variation plus hard-edged chips in the silhouette.
  return (broad-.5)*5.2+(step(.54,chips)-.5)*1.8;
}
float crayon(vec2 local,float seed){
  // Rotated octaves form irregular, branching islands instead of round blur.
  float fractal=fbm(local*.035+vec2(seed*3.1,seed*1.7));
  float broken=fbm(local*.087+vec2(seed*7.3,-seed*2.9));
  float fibres=noise(vec2(local.x*.07,local.y*.48)+seed*9.1);
  float grit=hash(floor(local*1.05+seed*41.));

  // Coverage can now reach zero: paper cuts completely through the stroke.
  float body=step(.37,fractal);
  float dense=step(.56,fractal);
  float branches=step(.46,broken);
  float fibreCut=step(.50,fibres);
  float gritCut=step(.48,grit);
  float coverage=body*(.43+.27*dense)+.19*branches+.10*gritCut;
  coverage*=mix(.68,1.,fibreCut);
  coverage-=grain*.15*(1.-fibreCut)*(1.-dense);
  return clamp(coverage,0.,1.);
}
void main(){
  vec2 p=vec2(uv.x*700.,(1.-uv.y)*430.);
  float rail=999.;
  rail=min(rail,sdSeg(p,vec2(55,72),vec2(220,154)));rail=min(rail,sdSeg(p,vec2(220,154),vec2(330,225)));rail=min(rail,sdSeg(p,vec2(330,225),vec2(480,128)));rail=min(rail,sdSeg(p,vec2(480,128),vec2(652,205)));rail=min(rail,sdSeg(p,vec2(48,350),vec2(200,294)));rail=min(rail,sdSeg(p,vec2(200,294),vec2(320,355)));rail=min(rail,sdSeg(p,vec2(390,350),vec2(530,294)));rail=min(rail,sdSeg(p,vec2(530,294),vec2(665,340)));

  vec3 cs[5]=vec3[5](vec3(180,100,22),vec3(340,122,27),vec3(530,92,21),vec3(272,285,20),vec3(596,252,23));
  float bump=999.;for(int i=0;i<5;i++)bump=min(bump,length(p-cs[i].xy)-cs[i].z);
  // Geometry and pigment use the same inverse rotation. The texture is now
  // attached to each wheel instead of remaining fixed in screen space.
  vec2 q1=rotateLocal(p-vec2(208,224),-angle);
  vec2 q2=rotateLocal(p-vec2(486,236),-angle);
  float w1=wheelShape(q1,54.),w2=wheelShape(q2,67.);
  float orange=min(bump,min(w1,w2));
  vec2 orangeLocal=p;
  if(w1<bump&&w1<w2)orangeLocal=q1+vec2(31,17);
  else if(w2<bump)orangeLocal=q2+vec2(83,47);

  float paperNoise=noise(p*.16)+.5*noise(p*.035);
  vec3 paper=vec3(.957,.91,.785)*(1.-grain*.045*paperNoise);

  vec2 railLocal=p+vec2(19,71);
  float railEdge=rail+edgeWarp(railLocal,1.7);
  float railPigment=crayon(railLocal,1.7);
  // A narrower, intermittently broken core preserves readability without
  // recreating two continuous ruler-straight outer lines.
  float railCore=smoothstep(6.2,5.2,rail)*step(.34,fbm(railLocal*.075+vec2(8.1,3.4)))*.22;
  float railMask=smoothstep(10.4,9.5,railEdge)*pigment*clamp(railPigment+railCore,0.,1.);

  float orangeEdge=orange+edgeWarp(orangeLocal,4.2)*.55;
  float orangeMask=smoothstep(2.2,.8,orangeEdge)*pigment*crayon(orangeLocal,4.2);
  vec2 ballLocal=p-ball;
  float ballEdge=length(ballLocal)+edgeWarp(ballLocal,7.9)*.55;
  float ballMask=smoothstep(15.2,14.3,ballEdge)*pigment*crayon(ballLocal,7.9);
  vec3 col=mix(paper,vec3(.075,.19,.49),railMask);
  col=mix(col,vec3(.86,.31,.055),orangeMask);
  col=mix(col,vec3(.025,.27,.76),ballMask);
  outColor=vec4(col,1.);
}`;

const originalFragment = `#version 300 es
precision highp float;
in vec2 uv; out vec4 outColor;
uniform vec2 resolution; uniform vec2 ball;
uniform float pigment; uniform float grain; uniform float angle;
float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float sdSeg(vec2 p,vec2 a,vec2 b){vec2 pa=p-a,ba=b-a;float h=clamp(dot(pa,ba)/dot(ba,ba),0.,1.);return length(pa-ba*h);}
float ring(vec2 p,vec2 c,float r){return abs(length(p-c)-r);}
vec2 rotateLocalOriginal(vec2 p,float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c)*p;}
float originalWheel(vec2 q,float r){float d=min(abs(length(q)-r),abs(length(q)-13.));for(int k=0;k<8;k++){float a=float(k)*.785398;d=min(d,sdSeg(q,vec2(cos(a),sin(a))*15.,vec2(cos(a),sin(a))*(r-8.)));}return d;}
float denseGrain(vec2 local){return hash(floor(local*1.7))+hash(floor(local*.31))*.5;}
void main(){
  vec2 p=vec2(uv.x*700.,(1.-uv.y)*430.);float rail=999.;
  rail=min(rail,sdSeg(p,vec2(55,72),vec2(220,154)));rail=min(rail,sdSeg(p,vec2(220,154),vec2(330,225)));rail=min(rail,sdSeg(p,vec2(330,225),vec2(480,128)));rail=min(rail,sdSeg(p,vec2(480,128),vec2(652,205)));rail=min(rail,sdSeg(p,vec2(48,350),vec2(200,294)));rail=min(rail,sdSeg(p,vec2(200,294),vec2(320,355)));rail=min(rail,sdSeg(p,vec2(390,350),vec2(530,294)));rail=min(rail,sdSeg(p,vec2(530,294),vec2(665,340)));
  float bump=999.;vec3 cs[5]=vec3[5](vec3(180,100,22),vec3(340,122,27),vec3(530,92,21),vec3(272,285,20),vec3(596,252,23));
  for(int i=0;i<5;i++)bump=min(bump,length(p-cs[i].xy)-cs[i].z);
  // Inverse rotation gives each wheel stable local coordinates. Both its
  // geometry and the original dense grain are evaluated in this frame.
  vec2 q1=rotateLocalOriginal(p-vec2(208,224),-angle);
  vec2 q2=rotateLocalOriginal(p-vec2(486,236),-angle);
  float w1=originalWheel(q1,54.),w2=originalWheel(q2,67.);
  float nPaper=denseGrain(p),nRail=denseGrain(p+vec2(17,31)),nBump=denseGrain(p+vec2(53,11));
  float nW1=denseGrain(q1+vec2(71,29)),nW2=denseGrain(q2+vec2(131,47));
  vec2 ballLocal=p-ball;float nBall=denseGrain(ballLocal+vec2(23,61));
  vec3 paper=vec3(.957,.91,.785)*(1.-grain*.055*nPaper);
  float ra=smoothstep(12.+nRail*4.,6.+nRail*2.,rail)*pigment;
  float bumpA=smoothstep(4.+nBump*2.,-1.+nBump,bump)*pigment*(.7+.3*nBump);
  float w1A=smoothstep(4.+nW1*2.,-1.+nW1,w1)*pigment*(.7+.3*nW1);
  float w2A=smoothstep(4.+nW2*2.,-1.+nW2,w2)*pigment*(.7+.3*nW2);
  float oa=max(bumpA,max(w1A,w2A));
  float ba=smoothstep(16.+nBall,13.-nBall,length(ballLocal))*pigment*(.78+.22*nBall);
  ra*=.65+.35*step(.10+grain*.12,hash(floor(p*2.)));
  vec3 col=mix(paper,vec3(.11,.22,.52),ra);col=mix(col,vec3(.84,.36,.09),oa);col=mix(col,vec3(.035,.30,.78),ba);
  outColor=vec4(col,1.);
}`;

const glCache = new WeakMap();
function shaderProgram(canvas, fragmentSource = fragment) {
  const gl=canvas.getContext("webgl2",{antialias:true}); if(!gl)return null;
  const compile=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;};
  const program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,vertex));gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragmentSource));gl.linkProgram(program);
  const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
  const loc=gl.getAttribLocation(program,"p");gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
  return {gl,program};
}
function renderShader(canvas,a,original=false){fitCanvas(canvas);let c=glCache.get(canvas);try{if(!c){c=shaderProgram(canvas,original?originalFragment:fragment);if(c)glCache.set(canvas,c);}}catch(e){console.error(e);c=null;}if(!c){(original?shaderOriginalStatus:shaderStatus).textContent="WebGL2 is not supported";return;}const {gl,program}=c,cfg=state(),b=ballPosition(ballTime);gl.viewport(0,0,canvas.width,canvas.height);gl.useProgram(program);gl.uniform2f(gl.getUniformLocation(program,"resolution"),canvas.width,canvas.height);gl.uniform2f(gl.getUniformLocation(program,"ball"),b.x,b.y);gl.uniform1f(gl.getUniformLocation(program,"pigment"),cfg.pigment);gl.uniform1f(gl.getUniformLocation(program,"grain"),cfg.grain);gl.uniform1f(gl.getUniformLocation(program,"angle"),a);gl.drawArrays(gl.TRIANGLES,0,6);}

function renderAll(){for(const card of cards){const canvas=card.querySelector("canvas");const type=card.dataset.renderer;if(type==="wax")renderCanvas(canvas,angle,false);else if(type==="fiber")renderCanvas(canvas,angle,true);else renderShader(canvas,angle,type==="shader-original");}}
function frame(now){if(animation){const dt=Math.min(50,now-previous)*.001;angle+=dt;ballTime+=dt;renderAll();}previous=now;requestAnimationFrame(frame);}

cards.forEach(card=>card.addEventListener("click",()=>{cards.forEach(c=>c.classList.toggle("selected",c===card));selection.textContent=`Selected favorite: ${card.querySelector("h2").textContent}.`; }));
[pigmentControl,grainControl].forEach(el=>el.addEventListener("input",renderAll));
animateButton.addEventListener("click",()=>{animation=!animation;animateButton.setAttribute("aria-pressed",String(animation));animateButton.textContent=animation?"■ Stop animation":"▶ Start animation";if(!animation)renderAll();});
new ResizeObserver(()=>renderAll()).observe(document.querySelector("#comparison"));
renderAll(); requestAnimationFrame(frame);
