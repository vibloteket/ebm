(() => {
  const MAX_SEGMENTS = 24;
  const MAX_CIRCLES = 12;
  const vertex = `#version 300 es
  in vec2 p; out vec2 uv; void main(){uv=p*.5+.5;gl_Position=vec4(p,0.,1.);}`;
  const fragment = `#version 300 es
  precision highp float;
  #define MAX_SEGMENTS 24
  #define MAX_CIRCLES 12
  in vec2 uv; out vec4 outColor;
  uniform int segmentCount,circleCount;
  uniform vec4 segments[MAX_SEGMENTS];
  uniform vec3 circles[MAX_CIRCLES];
  uniform float radii[MAX_SEGMENTS];
  uniform float seed;
  uniform vec2 size;
  uniform vec3 materialColor;
  float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1)),f.x),f.y);}
  float sdSeg(vec2 p,vec2 a,vec2 b){vec2 pa=p-a,ba=b-a;float h=clamp(dot(pa,ba)/max(dot(ba,ba),.001),0.,1.);return length(pa-ba*h);}
  float fbm(vec2 p){float v=0.;v+=noise(p)*.533;p=mat2(1.63,-1.17,1.17,1.63)*p+vec2(7.1,3.7);v+=noise(p)*.267;p=mat2(1.71,.93,-.93,1.71)*p+vec2(5.3,11.9);v+=noise(p)*.133;p=mat2(1.47,-1.29,1.29,1.47)*p+vec2(13.7,2.1);v+=noise(p)*.067;return v;}
  float edgeWarp(vec2 p,float s){float broad=fbm(p*.052+vec2(s*5.7,-s*2.1));float chips=fbm(p*.145+vec2(-s*3.3,s*7.9));return (broad-.5)*5.2+(step(.54,chips)-.5)*1.8;}
  float crayon(vec2 p,float s){float fractal=fbm(p*.035+vec2(s*3.1,s*1.7));float broken=fbm(p*.087+vec2(s*7.3,-s*2.9));float fibres=noise(vec2(p.x*.07,p.y*.48)+s*9.1);float grit=hash(floor(p*1.05+s*41.));float body=step(.37,fractal),dense=step(.56,fractal),branches=step(.46,broken),fibreCut=step(.50,fibres),gritCut=step(.48,grit);float coverage=body*(.43+.27*dense)+.19*branches+.10*gritCut;coverage*=mix(.68,1.,fibreCut);coverage-=.087*(1.-fibreCut)*(1.-dense);return clamp(coverage,0.,1.);}
  void main(){
    vec2 q=vec2(uv.x*size.x,(1.-uv.y)*size.y);float d=999.;
    for(int i=0;i<MAX_SEGMENTS;i++){if(i>=segmentCount)break;d=min(d,sdSeg(q,segments[i].xy,segments[i].zw)-max(4.,radii[i]*1.9));}
    for(int i=0;i<MAX_CIRCLES;i++){if(i>=circleCount)break;d=min(d,length(q-circles[i].xy)-circles[i].z);}
    float warped=d+edgeWarp(q,seed);float shape=smoothstep(1.2,-.2,warped);float pigment=crayon(q,seed);
    float core=smoothstep(-4.,-6.,d)*step(.34,fbm(q*.075+vec2(seed*4.7,seed*2.)));float alpha=shape*clamp(pigment+core*.22,0.,1.);
    outColor=vec4(materialColor,alpha);
  }`;

  function compile(gl,type,source){const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;}
  window.renderV3Tile = (segments, circles, seed = 1, cssSize = 228, scale = 1, color = [0.075,0.19,0.49]) => {
    const canvas=document.createElement('canvas');canvas.width=Math.ceil(cssSize*scale);canvas.height=Math.ceil(cssSize*scale);
    const gl=canvas.getContext('webgl2',{alpha:true,antialias:true,premultipliedAlpha:true});if(!gl)return null;
    const program=gl.createProgram();gl.attachShader(program,compile(gl,gl.VERTEX_SHADER,vertex));gl.attachShader(program,compile(gl,gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);
    const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const loc=gl.getAttribLocation(program,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
    const sf=new Float32Array(MAX_SEGMENTS*4),rf=new Float32Array(MAX_SEGMENTS),cf=new Float32Array(MAX_CIRCLES*3);
    segments.slice(0,MAX_SEGMENTS).forEach((v,i)=>{sf.set(v.slice(0,4),i*4);rf[i]=v[4]||3;});circles.slice(0,MAX_CIRCLES).forEach((v,i)=>cf.set(v.slice(0,3),i*3));
    gl.uniform1i(gl.getUniformLocation(program,'segmentCount'),Math.min(segments.length,MAX_SEGMENTS));gl.uniform1i(gl.getUniformLocation(program,'circleCount'),Math.min(circles.length,MAX_CIRCLES));gl.uniform4fv(gl.getUniformLocation(program,'segments[0]'),sf);gl.uniform1fv(gl.getUniformLocation(program,'radii[0]'),rf);gl.uniform3fv(gl.getUniformLocation(program,'circles[0]'),cf);gl.uniform1f(gl.getUniformLocation(program,'seed'),seed);gl.uniform2f(gl.getUniformLocation(program,'size'),cssSize,cssSize);gl.uniform3f(gl.getUniformLocation(program,'materialColor'),color[0],color[1],color[2]);gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLES,0,6);return canvas;
  };
})();
