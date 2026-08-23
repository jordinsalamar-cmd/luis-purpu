import { readFile, writeFile } from "node:fs/promises"
import { dirname, resolve } from "node:path"

const input = process.argv[2] || "graphify-out/graph.html"
const output = process.argv[3] || input
const source = await readFile(input, "utf8")

function readConstant(name, nextName) {
  const start = source.indexOf(`const ${name} = `)
  if (start < 0) throw new Error(`No encontré ${name} en ${input}`)
  const valueStart = start + `const ${name} = `.length
  const end = nextName ? source.indexOf(`const ${nextName} = `, valueStart) : source.indexOf(";", valueStart)
  const raw = source.slice(valueStart, end).replace(/;\s*$/, "").trim()
  return JSON.parse(raw)
}

const data = {
  nodes: readConstant("RAW_NODES", "RAW_EDGES"),
  edges: readConstant("RAW_EDGES", "LEGEND"),
  legend: readConstant("LEGEND"),
}

try {
  const analysis = JSON.parse(await readFile(resolve(dirname(input), ".graphify_analysis.json"), "utf8"))
  const communities = analysis.communities || {}
  data.legend = data.nodes.map((node) => ({
    cid: node.community,
    color: node.color?.background || "#8e76dc",
    label: node.community_name || `Community ${node.community}`,
    count: Array.isArray(communities[String(node.community)]) ? communities[String(node.community)].length : 1,
  }))
  const counts = new Map(data.legend.map((item) => [String(item.cid), item.count]))
  for (const node of data.nodes) node.memberCount = counts.get(String(node.community)) || 1
} catch {
  data.legend = data.nodes.map((node) => ({
    cid: node.community,
    color: node.color?.background || "#8e76dc",
    label: node.community_name || `Community ${node.community}`,
    count: 1,
  }))
}
const serialized = JSON.stringify(data).replace(/</g, "\\u003c")

const html = `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Luis · cerebro del proyecto</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0f0f1a;color:#eee;font:14px system-ui,-apple-system,Segoe UI,sans-serif}#layout{display:grid;grid-template-columns:minmax(0,1fr) 280px;width:100%;height:100%}#stage{position:relative;min-width:0;background:radial-gradient(circle at 50% 48%,#171a32 0,#10111f 42%,#0d0e18 78%)}canvas{display:block;width:100%;height:100%;cursor:grab}canvas:active{cursor:grabbing}.title{position:absolute;left:22px;top:18px;color:#bdb8e0;letter-spacing:.08em;text-transform:uppercase;font-size:11px}.hint{position:absolute;left:22px;bottom:18px;color:#77748f;font-size:12px}.glow{position:absolute;inset:12% 12%;pointer-events:none;background:radial-gradient(circle,rgba(106,86,220,.12),transparent 58%);filter:blur(22px)}#sidebar{background:#19182c;border-left:1px solid #343152;display:flex;flex-direction:column;min-height:0}.search{padding:14px;border-bottom:1px solid #302e4a}.search input{width:100%;padding:8px 11px;border:1px solid #4d4972;border-radius:7px;background:#111020;color:#eee;outline:0}.search input:focus{border-color:#8e76dc}.results{max-height:145px;overflow:auto}.result{padding:6px 3px;color:#c7c2e5;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.result:hover{color:#fff}.panel{padding:14px;border-bottom:1px solid #302e4a}.panel h3,.legend h3{margin:0 0 12px;text-transform:uppercase;font-size:13px;letter-spacing:.04em;color:#f0eefc}.empty{color:#77758d;font-style:italic}.info-label{color:#aaa4c5;font-size:12px;margin-top:7px}.info-value{color:#eee;word-break:break-word}.legend{flex:1;overflow:auto;padding:14px}.legend label{display:flex;align-items:center;gap:8px;padding:6px 0;color:#dedaf3;cursor:pointer}.legend label.off{opacity:.35}.swatch{width:12px;height:12px;border-radius:50%;display:inline-block;box-shadow:0 0 8px currentColor}.legend em{margin-left:auto;color:#8c88a8;font-style:normal;font-size:12px}.stats{padding:14px;color:#b7b2cf;border-top:1px solid #302e4a;font-size:12px}
</style></head><body><div id="layout"><main id="stage"><div class="glow"></div><canvas id="canvas"></canvas><div class="title">Luis · cerebro del proyecto</div><div class="hint">arrastra para rotar · rueda para zoom · clic en un nodo para inspeccionar</div></main><aside id="sidebar"><div class="search"><input id="search" placeholder="Search nodes..." autocomplete="off"><div id="results"></div></div><section class="panel"><h3>Node Info</h3><div id="info"><span class="empty">Click a node to inspect it</span></div></section><section class="legend"><h3>Communities</h3><label><input id="all" type="checkbox" checked> Select All</label><div id="communities"></div></section><div class="stats" id="stats"></div></aside></div>
<script>
const data=${serialized};
const canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d'),stage=document.getElementById('stage');
const nodes=data.nodes||[],edges=data.edges||[],legend=data.legend||[];const hidden=new Set();const projected=[];let width=0,height=0,scale=1,rotX=0,rotY=0,drag=false,lastX=0,lastY=0,selected=null;
const maxDegree=Math.max(1,...nodes.map(n=>Number(n.degree)||0)),maxMembers=Math.max(1,...nodes.map(n=>Number(n.memberCount)||1));
function hash(value){let h=2166136261;for(let i=0;i<value.length;i++){h^=value.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0)/4294967296}
function prepare(){nodes.forEach((n,i)=>{const t=(i+.5)/nodes.length,phi=Math.acos(1-2*t),theta=Math.PI*(3-Math.sqrt(5))*i;const degree=Math.min(1,(Number(n.degree)||0)/maxDegree),importance=Math.min(1,Math.log1p(Number(n.memberCount)||1)/Math.log1p(maxMembers));const radius=.36+.64*(1-Math.max(degree*.24,importance*.78));n.p={x:Math.sin(phi)*Math.cos(theta)*radius,y:Math.cos(phi)*radius,z:Math.sin(phi)*Math.sin(theta)*radius,twinkle:hash(String(n.id))*Math.PI*2};});}
function resize(){const r=stage.getBoundingClientRect(),d=Math.min(2,window.devicePixelRatio||1);width=r.width;height=r.height;canvas.width=width*d;canvas.height=height*d;canvas.style.width=width+'px';canvas.style.height=height+'px';ctx.setTransform(d,0,0,d,0,0)}
function project(n){const p=n.p,cx=Math.cos(rotY),sx=Math.sin(rotY),cy=Math.cos(rotX),sy=Math.sin(rotX);const x=p.x*cx-p.z*sx,z=p.x*sx+p.z*cx,y=p.y*cy-z*sy,depth=p.y*sy+z*cy;const importance=Math.min(1,Math.log1p(Number(n.memberCount)||1)/Math.log1p(maxMembers));return {x:width/2+x*Math.min(width,height)*.47*scale,y:height/2+y*Math.min(width,height)*.47*scale,z:depth,r:Math.max(1.35,1.35+importance*5+Math.min(2,(Number(n.degree)||0)/40))}}
function color(n){return n.color?.background||'#8e76dc'}
function render(time=0){ctx.clearRect(0,0,width,height);const radius=Math.min(width,height)*.47*scale;ctx.beginPath();ctx.arc(width/2,height/2,radius,0,Math.PI*2);ctx.strokeStyle='rgba(130,112,220,.09)';ctx.stroke();projected.length=0;for(const n of nodes){const p=project(n);projected.push({n,p});}
for(const e of edges){const a=projected.find(x=>String(x.n.id)===String(e.from??e.source)),b=projected.find(x=>String(x.n.id)===String(e.to??e.target));if(!a||!b||hidden.has(a.n.community)||hidden.has(b.n.community)||a.p.z<-.35||b.p.z<-.35)continue;ctx.beginPath();ctx.moveTo(a.p.x,a.p.y);ctx.lineTo(b.p.x,b.p.y);ctx.strokeStyle='rgba(132,117,185,'+(Math.max(0,(a.p.z+b.p.z)/2)*.11+.025)+')';ctx.lineWidth=.5;ctx.stroke();}
for(const item of projected){const n=item.n,p=item.p;if(hidden.has(n.community)||p.z<-.72)continue;const alpha=.5+p.z*.48;ctx.globalAlpha=alpha;ctx.shadowBlur=selected===n?18:8;ctx.shadowColor=color(n);ctx.fillStyle=color(n);ctx.beginPath();ctx.arc(p.x,p.y,p.r+(Math.sin(time/900+n.p.twinkle)*.35),0,Math.PI*2);ctx.fill();if(selected===n){ctx.shadowBlur=0;ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(p.x,p.y,p.r+5,0,Math.PI*2);ctx.stroke();}}ctx.globalAlpha=1;ctx.shadowBlur=0;requestAnimationFrame(render)}
function showInfo(n){selected=n;const info=document.getElementById('info');info.innerHTML='';[['label',n.label],['community',n.community_name||('Community '+n.community)],['degree',n.degree??''],['source',n.source_file||''],['location',n.source_location||'']].forEach(([k,v])=>{if(v===undefined||v==='')return;const a=document.createElement('div');a.className='info-label';a.textContent=k;const b=document.createElement('div');b.className='info-value';b.textContent=String(v);info.append(a,b)})}
function pick(x,y){let best=null,dist=18;for(const item of projected){if(hidden.has(item.n.community)||item.p.z<-.35)continue;const d=Math.hypot(item.p.x-x,item.p.y-y);if(d<dist){dist=d;best=item.n}}if(best)showInfo(best)}
function buildLegend(){const holder=document.getElementById('communities');const rows=[...legend].sort((a,b)=>(b.count||0)-(a.count||0));for(const item of rows){const row=document.createElement('label');const cb=document.createElement('input');cb.type='checkbox';cb.checked=true;cb.addEventListener('change',()=>{if(cb.checked)hidden.delete(item.cid);else hidden.add(item.cid);row.classList.toggle('off',!cb.checked);document.getElementById('all').checked=hidden.size===0});const sw=document.createElement('span');sw.className='swatch';sw.style.background=item.color;sw.style.color=item.color;const text=document.createElement('span');text.textContent=item.label;const count=document.createElement('em');count.textContent=item.count??'';row.append(cb,sw,text,count);holder.append(row)}}
document.getElementById('all').addEventListener('change',e=>{for(const item of legend){if(e.target.checked)hidden.delete(item.cid);else hidden.add(item.cid)}document.querySelectorAll('#communities input').forEach(x=>x.checked=e.target.checked);document.querySelectorAll('#communities label').forEach(x=>x.classList.toggle('off',!e.target.checked))});
const search=document.getElementById('search'),results=document.getElementById('results');search.addEventListener('input',()=>{results.innerHTML='';const q=search.value.toLowerCase().trim();if(!q)return;nodes.filter(n=>(n.label+' '+(n.source_file||'')+' '+(n.community_name||'')).toLowerCase().includes(q)).slice(0,14).forEach(n=>{const row=document.createElement('div');row.className='result';row.textContent=n.label+' · '+(n.source_file||n.community_name||'');row.onclick=()=>showInfo(n);results.append(row)})});
canvas.addEventListener('pointerdown',e=>{drag=true;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId)});canvas.addEventListener('pointermove',e=>{if(!drag)return;rotY+=(e.clientX-lastX)*.008;rotX+=(e.clientY-lastY)*.008;lastX=e.clientX;lastY=e.clientY});canvas.addEventListener('pointerup',()=>drag=false);canvas.addEventListener('wheel',e=>{e.preventDefault();scale=Math.max(.55,Math.min(2.4,scale*(e.deltaY<0?1.08:.93)))},{passive:false});canvas.addEventListener('click',e=>{if(!drag)pick(e.offsetX,e.offsetY)});window.addEventListener('resize',resize);
document.getElementById('stats').textContent=nodes.length+' nodos · '+edges.length+' conexiones · '+legend.length+' comunidades';prepare();buildLegend();resize();requestAnimationFrame(render);
</script></body></html>`

const themed = html
  .replaceAll("background:#0f0f1a", "background:#000")
  .replaceAll("background:radial-gradient(circle at 50% 48%,#171a32 0,#10111f 42%,#0d0e18 78%)", "background:#000")
  .replaceAll("rgba(106,86,220,.12)", "rgba(150,110,255,.08)")
await writeFile(output, themed, "utf8")
console.log(`Vista galaxia generada: ${output} (${data.nodes.length} nodos, ${data.edges.length} conexiones)`)
