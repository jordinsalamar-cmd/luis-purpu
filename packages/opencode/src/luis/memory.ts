import { createHash } from "node:crypto"
import { execFile } from "node:child_process"
import { copyFile, mkdir, mkdtemp, readFile, rename, rm, unlink, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)

export type LuisMemoryKind = "identity" | "session" | "conversation" | "preference" | "lesson" | "capability" | "emotion"

export type LuisMood = "calm" | "joyful" | "focused" | "curious" | "concerned" | "tired"

export type LuisEmotionState = {
  mood: LuisMood
  energy: number
  warmth: number
  confidence: number
  curiosity: number
  stress: number
  trust: number
  interactions: number
  lastReason: string
  updated: number
}

export type LuisMemoryNode = {
  id: string
  label: string
  type: LuisMemoryKind
  content?: string
  created: number
  updated: number
  source?: string
  importance?: number
}

export type LuisMemoryEdge = {
  source: string
  target: string
  relation: string
  confidence: "EXTRACTED" | "INFERRED" | "AMBIGUOUS"
}

export type LuisMemoryGraph = {
  version: string
  directed?: boolean
  nodes: LuisMemoryNode[]
  edges: LuisMemoryEdge[]
  metadata?: Record<string, unknown>
}

const defaultProjectRoot = () => resolve(dirname(process.execPath), "..", "..", "..", "..", "..")
const graphDirectory = () => join(process.env.LUIS_GRAPH_ROOT || defaultProjectRoot(), "graphify-out")
const graphPath = () => join(graphDirectory(), "luis-memory.json")
const htmlPath = () => join(graphDirectory(), "luis-memory.html")
const oldHtmlPaths = () => [join(graphDirectory(), "index.html"), join(graphDirectory(), "luis-brain.html")]

function redact(value: string) {
  return value
    .replace(
      /(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|private[_-]?key|authorization)\s*[:=]\s*[^\s,;]+/gi,
      "$1=[redacted]",
    )
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [redacted]")
    .slice(0, 4000)
}

const MEMORY_STOP_WORDS = new Set(
  "a al algo aqui así con como de del el ella en es esta este fue ha hay la las le lo los me mi muy no para por que se si su sus te todo un una y yo".split(
    " ",
  ),
)

function memoryTokens(value: string) {
  return new Set(
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .split(/[^a-z0-9áéíóúüñ]+/i)
      .filter((token) => token.length > 2 && !MEMORY_STOP_WORDS.has(token)),
  )
}

function importance(kind: LuisMemoryKind, content: string) {
  if (kind === "identity" || kind === "preference" || kind === "capability") return 1
  if (kind === "emotion") return 0.75
  if (kind === "lesson") return 0.85
  const tokens = memoryTokens(content)
  const markers = [
    "recuerda",
    "siempre",
    "prefiero",
    "mi nombre",
    "no uses",
    "aprende",
    "error",
    "solucion",
    "configura",
  ]
  return Math.min(
    0.8,
    0.25 +
      markers.filter((marker) => content.toLowerCase().includes(marker)).length * 0.1 +
      Math.min(0.2, tokens.size / 100),
  )
}

function idFor(value: string) {
  return `luis:${createHash("sha1").update(value).digest("hex").slice(0, 20)}`
}

async function loadGraph(): Promise<LuisMemoryGraph> {
  try {
    const raw = JSON.parse(await readFile(graphPath(), "utf8")) as Partial<LuisMemoryGraph>
    return {
      version: typeof raw.version === "string" ? raw.version : "graphify+luis-v1",
      directed: raw.directed ?? true,
      nodes: Array.isArray(raw.nodes) ? (raw.nodes as LuisMemoryNode[]) : [],
      edges: Array.isArray(raw.edges) ? (raw.edges as LuisMemoryEdge[]) : [],
      metadata: raw.metadata ?? {},
    }
  } catch {
    return { version: "graphify+luis-v1", directed: true, nodes: [], edges: [], metadata: {} }
  }
}

function addNode(graph: LuisMemoryGraph, node: LuisMemoryNode) {
  const existing = graph.nodes.find((item) => item.id === node.id)
  if (existing) {
    existing.updated = node.updated
    if (node.content) existing.content = node.content
    if (node.importance !== undefined) existing.importance = node.importance
    return existing
  }
  graph.nodes.push(node)
  return node
}

function compactGraph(graph: LuisMemoryGraph) {
  const maxNodes = Number.parseInt(process.env.LUIS_MEMORY_MAX_NODES ?? "12000", 10)
  if (!Number.isFinite(maxNodes) || maxNodes < 1000 || graph.nodes.length <= maxNodes) return

  const keep = new Set(
    graph.nodes.filter((node) => node.type === "identity" || (node.importance ?? 0) >= 0.75).map((node) => node.id),
  )
  const recent = [...graph.nodes]
    .filter((node) => !keep.has(node.id))
    .sort((a, b) => b.updated - a.updated)
    .slice(0, Math.max(0, maxNodes - keep.size))
  for (const node of recent) keep.add(node.id)
  graph.nodes = graph.nodes.filter((node) => keep.has(node.id))
  graph.edges = graph.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target))
  graph.metadata = { ...(graph.metadata ?? {}), lastGraphCompaction: Date.now() }
}

function addEdge(graph: LuisMemoryGraph, edge: LuisMemoryEdge) {
  if (
    graph.edges.some(
      (item) => item.source === edge.source && item.target === edge.target && item.relation === edge.relation,
    )
  )
    return
  graph.edges.push(edge)
}

let memoryQueue: Promise<void> = Promise.resolve()

const DEFAULT_EMOTION: LuisEmotionState = {
  mood: "calm",
  energy: 0.72,
  warmth: 0.7,
  confidence: 0.68,
  curiosity: 0.62,
  stress: 0.12,
  trust: 0.5,
  interactions: 0,
  lastReason: "inicio de Luis",
  updated: 0,
}

function clamp(value: number) {
  return Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0.5))
}

function normalizeEmotion(value: unknown): LuisEmotionState {
  const raw = value && typeof value === "object" ? (value as Partial<LuisEmotionState>) : {}
  const moods: LuisMood[] = ["calm", "joyful", "focused", "curious", "concerned", "tired"]
  return {
    mood: moods.includes(raw.mood as LuisMood) ? (raw.mood as LuisMood) : DEFAULT_EMOTION.mood,
    energy: clamp(Number(raw.energy ?? DEFAULT_EMOTION.energy)),
    warmth: clamp(Number(raw.warmth ?? DEFAULT_EMOTION.warmth)),
    confidence: clamp(Number(raw.confidence ?? DEFAULT_EMOTION.confidence)),
    curiosity: clamp(Number(raw.curiosity ?? DEFAULT_EMOTION.curiosity)),
    stress: clamp(Number(raw.stress ?? DEFAULT_EMOTION.stress)),
    trust: clamp(Number(raw.trust ?? DEFAULT_EMOTION.trust)),
    interactions: Math.max(0, Number(raw.interactions ?? 0)),
    lastReason: typeof raw.lastReason === "string" ? raw.lastReason.slice(0, 180) : DEFAULT_EMOTION.lastReason,
    updated: Number(raw.updated ?? 0),
  }
}

export async function getLuisEmotion() {
  const graph = await loadGraph()
  return normalizeEmotion(graph.metadata?.luisEmotion)
}

export function recordLuisEmotion(input: {
  sessionID: string
  state: LuisEmotionState
  reason: string
}) {
  const task = memoryQueue.then(async () => {
    const graph = await loadGraph()
    const now = Date.now()
    const state = normalizeEmotion({ ...input.state, lastReason: input.reason, updated: now })
    const identity = addNode(graph, {
      id: "luis:identity",
      label: "Luis",
      type: "identity",
      content: "Asistente de escritorio en español; llama jefe al usuario.",
      created: now,
      updated: now,
    })
    const emotion = addNode(graph, {
      id: idFor(`emotion:${input.sessionID}:${now}`),
      label: `ánimo ${state.mood}`,
      type: "emotion",
      content: `mood=${state.mood}; energía=${state.energy.toFixed(2)}; calidez=${state.warmth.toFixed(2)}; confianza=${state.confidence.toFixed(2)}; curiosidad=${state.curiosity.toFixed(2)}; estrés=${state.stress.toFixed(2)}; motivo=${state.lastReason}`,
      created: now,
      updated: now,
      source: "luis.personality",
      importance: 0.75,
    })
    addEdge(graph, { source: identity.id, target: emotion.id, relation: "expresa", confidence: "INFERRED" })
    graph.metadata = { ...(graph.metadata ?? {}), luisEmotion: state, lastLuisEmotion: now }
    compactGraph(graph)
    await mkdir(graphDirectory(), { recursive: true })
    const temp = `${graphPath()}.tmp`
    await writeFile(temp, JSON.stringify(graph, null, 2), "utf8")
    await rename(temp, graphPath())
    await writeGraphViewer(graph)
  })
  memoryQueue = task.catch(() => {})
  return task
}

function html(graph: LuisMemoryGraph) {
  const memoryNodes = graph.nodes.filter((node) => node.id.startsWith("luis:"))
  const sourceNodes = memoryNodes.length > 0 ? memoryNodes : graph.nodes
  const visibleNodes = sourceNodes.length > 1200 ? sourceNodes.slice(-1200) : sourceNodes
  const visibleIDs = new Set(visibleNodes.map((node) => node.id))
  const visibleEdges = graph.edges.filter((edge) => visibleIDs.has(edge.source) && visibleIDs.has(edge.target))
  const communities = [...new Set(visibleNodes.map((node) => node.type))].sort()
  const view = {
    version: graph.version,
    nodes: visibleNodes,
    edges: visibleEdges,
    totalNodes: sourceNodes.length,
    totalEdges: visibleEdges.length,
    communities,
  }
  const serialized = JSON.stringify(view).replace(/</g, "\\u003c")
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Luis · memory graph</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;overflow:hidden;background:#0d0c18;color:#eee;font:14px system-ui,sans-serif}#graph{position:absolute;inset:0 280px 0 0;background:#0d0c18}#sidebar{position:absolute;top:0;right:0;width:280px;height:100vh;background:#19182c;border-left:1px solid #322f52;display:flex;flex-direction:column}#search-wrap{padding:14px;border-bottom:1px solid #302e4a}#search{width:100%;padding:8px 11px;border:1px solid #4d4972;border-radius:7px;background:#111020;color:#eee;outline:0}#search:focus{border-color:#8e76dc}#search-results{max-height:145px;overflow:auto}.result{padding:5px 3px;color:#c7c2e5;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.result:hover{color:#fff}.panel{padding:14px;border-bottom:1px solid #302e4a}h3{margin:0 0 12px;text-transform:uppercase;font-size:13px;letter-spacing:.04em;color:#f0eefc}.empty{color:#77758d;font-style:italic}.info-label{color:#aaa4c5;font-size:12px;margin-top:7px}.info-value{color:#eee;word-break:break-word}.legend{flex:1;overflow:auto;padding:14px}.legend label{display:flex;align-items:center;gap:8px;padding:7px 0;color:#dedaf3;cursor:pointer}.swatch{width:12px;height:12px;border-radius:50%;display:inline-block}.muted{opacity:.35}.stats{padding:14px;color:#b7b2cf;border-top:1px solid #302e4a;font-size:12px}.edge{stroke:#5e527f;stroke-opacity:.48;stroke-width:1}.node{stroke:#0d0c18;stroke-width:1.5;cursor:pointer}.node.selected{stroke:#fff;stroke-width:3}.label{fill:#d8d4ed;font-size:10px;pointer-events:none}.identity{fill:#e95dff}.session{fill:#4d9cff}.conversation{fill:#ff9a25}.preference{fill:#67c2b6}.lesson{fill:#e85b68}.capability{fill:#78b75c}</style></head>
<body><svg id="graph" viewBox="0 0 920 800" preserveAspectRatio="xMidYMid meet"></svg><aside id="sidebar"><div id="search-wrap"><input id="search" placeholder="Search nodes..." autocomplete="off"><div id="search-results"></div></div><section class="panel"><h3>Node info</h3><div id="info"><span class="empty">Click a node to inspect it</span></div></section><section class="legend"><h3>Communities</h3><label><input id="select-all" type="checkbox" checked> Select All</label><div id="communities"></div></section><div class="stats" id="stats"></div></aside>
<script>const data=${serialized};const svg=document.querySelector('#graph');const ns='http://www.w3.org/2000/svg';const nodes=data.nodes||[];const edges=data.edges||[];const colors={identity:'#e95dff',session:'#4d9cff',conversation:'#ff9a25',preference:'#67c2b6',lesson:'#e85b68',capability:'#78b75c'};const hidden=new Set();const pos=new Map();const nodeType=new Map();const groups=new Map();nodes.forEach(n=>{nodeType.set(n.id,n.type);if(!groups.has(n.type))groups.set(n.type,[]);groups.get(n.type).push(n)});[...groups].forEach(([type,list],groupIndex)=>{const cx=180+(groupIndex%4)*190;const cy=175+Math.floor(groupIndex/4)*240;list.forEach((n,i)=>{const angle=i*2.399;const radius=24+Math.sqrt(i+1)*18;pos.set(n.id,{x:cx+Math.cos(angle)*Math.min(145,radius),y:cy+Math.sin(angle)*Math.min(125,radius)})})});const edgeEls=[];edges.forEach(e=>{const a=pos.get(e.source),b=pos.get(e.target);if(!a||!b)return;const line=document.createElementNS(ns,'line');line.setAttribute('class','edge');line.setAttribute('x1',a.x);line.setAttribute('y1',a.y);line.setAttribute('x2',b.x);line.setAttribute('y2',b.y);svg.append(line);edgeEls.push({el:line,e})});const nodeEls=[];function showInfo(n){const info=document.querySelector('#info');info.replaceChildren();[['label',n.label],['type',n.type],['content',n.content||''],['source',n.source||'']].forEach(pair=>{if(!pair[1])return;const label=document.createElement('div');label.className='info-label';label.textContent=pair[0];const value=document.createElement('div');value.className='info-value';value.textContent=pair[1];info.append(label,value)});document.querySelectorAll('.node').forEach(x=>x.classList.remove('selected'));const found=nodeEls.find(x=>x.n.id===n.id);if(found)found.el.classList.add('selected')}nodes.forEach(n=>{const p=pos.get(n.id);const circle=document.createElementNS(ns,'circle');circle.setAttribute('class','node '+n.type);circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);circle.setAttribute('r',n.type==='identity'?9:5);circle.addEventListener('click',()=>showInfo(n));svg.append(circle);const text=document.createElementNS(ns,'text');text.setAttribute('class','label');text.setAttribute('x',p.x+8);text.setAttribute('y',p.y+4);text.textContent=n.label.slice(0,28);svg.append(text);nodeEls.push({el:circle,text,n})});const communityBox=document.querySelector('#communities');const all=document.querySelector('#select-all');function apply(){nodeEls.forEach(x=>{const hide=hidden.has(x.n.type);x.el.style.display=hide?'none':'';x.text.style.display=hide?'none':''});edgeEls.forEach(x=>{const hide=hidden.has(nodeType.get(x.e.source))||hidden.has(nodeType.get(x.e.target));x.el.style.display=hide?'none':''})}function toggle(type,on){if(on)hidden.delete(type);else hidden.add(type);apply();all.checked=hidden.size===0}for(const type of data.communities||[]){const label=document.createElement('label');const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=true;checkbox.addEventListener('change',()=>toggle(type,checkbox.checked));const swatch=document.createElement('span');swatch.className='swatch';swatch.style.background=colors[type]||'#aaa';label.append(checkbox,swatch,document.createTextNode(type+' '+nodes.filter(n=>n.type===type).length));communityBox.append(label)}all.addEventListener('change',()=>{(data.communities||[]).forEach(type=>{if(all.checked)hidden.delete(type);else hidden.add(type)});document.querySelectorAll('#communities input').forEach(x=>x.checked=all.checked);apply()});const search=document.querySelector('#search');const results=document.querySelector('#search-results');search.addEventListener('input',()=>{results.replaceChildren();const q=search.value.toLowerCase().trim();if(!q)return;nodes.filter(n=>(n.label+' '+(n.content||'')).toLowerCase().includes(q)).slice(0,12).forEach(n=>{const item=document.createElement('div');item.className='result';item.textContent=n.label;item.onclick=()=>showInfo(n);results.append(item)})});document.querySelector('#stats').textContent=data.totalNodes+' nodes · '+data.totalEdges+' edges · '+(data.communities||[]).length+' communities';</script></body></html>`
}

function graphifyInput(graph: LuisMemoryGraph) {
  const memoryNodes = graph.nodes.filter((node) => node.id.startsWith("luis:"))
  const nodes = memoryNodes.length > 0 ? memoryNodes : graph.nodes
  const types = [...new Set(nodes.map((node) => node.type))].sort()
  const communities = new Map(types.map((type, index) => [type, index]))
  return {
    version: graph.version,
    directed: true,
    nodes: nodes.map((node) => ({
      id: node.id,
      label: node.label,
      type: node.type,
      content: node.content,
      source: node.source,
      community: communities.get(node.type),
    })),
    edges: graph.edges.filter(
      (edge) => nodes.some((node) => node.id === edge.source) && nodes.some((node) => node.id === edge.target),
    ),
  }
}

async function exportGraphify(graph: LuisMemoryGraph) {
  const output = graphDirectory()
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "luis-graphify-"))
  try {
    const temporaryGraph = join(temporaryDirectory, "graph.json")
    const data = graphifyInput(graph)
    await writeFile(temporaryGraph, JSON.stringify(data, null, 2), "utf8")
    const labels = Object.fromEntries(
      [...new Set(data.nodes.map((node) => [node.community, node.type] as const))].map(([community, type]) => [
        String(community),
        type === "conversation"
          ? "Memoria conversacional"
          : type === "lesson"
            ? "Aprendizajes de Luis"
            : type === "session"
              ? "Sesiones"
              : type === "identity"
                ? "Identidad de Luis"
                : type,
      ]),
    )
    await writeFile(join(temporaryDirectory, ".graphify_labels.json"), JSON.stringify(labels), "utf8")
    await execFileAsync(process.env.LUIS_GRAPHIFY || "graphify", ["export", "html", "--graph", temporaryGraph], {
      cwd: temporaryDirectory,
      windowsHide: true,
      maxBuffer: 8 * 1024 * 1024,
    })
    await copyFile(join(temporaryDirectory, "graph.html"), htmlPath())
    return true
  } catch {
    return false
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true }).catch(() => {})
  }
}

async function writeGraphViewer(graph: LuisMemoryGraph) {
  await mkdir(graphDirectory(), { recursive: true })
  const exported = await exportGraphify(graph)
  if (!exported) await writeFile(htmlPath(), html(graph), "utf8")
  for (const oldPath of oldHtmlPaths()) await unlink(oldPath).catch(() => {})
}

async function writeLuisMemory(input: {
  sessionID: string
  kind: Exclude<LuisMemoryKind, "identity">
  label: string
  content: string
  source?: string
}) {
  const content = redact(input.content.trim())
  if (!content) return
  const now = Date.now()
  const graph = await loadGraph()
  const identity = addNode(graph, {
    id: "luis:identity",
    label: "Luis",
    type: "identity",
    content: "Asistente de escritorio en español; llama jefe al usuario.",
    created: now,
    updated: now,
  })
  const session = addNode(graph, {
    id: idFor(`session:${input.sessionID}`),
    label: `sesión ${input.sessionID.slice(0, 8)}`,
    type: "session",
    created: now,
    updated: now,
    source: input.source,
  })
  const memory = addNode(graph, {
    id: idFor(`${input.sessionID}:${input.kind}:${input.label}:${content}`),
    label: input.label.slice(0, 120),
    type: input.kind,
    content,
    created: now,
    updated: now,
    source: input.source,
    importance: importance(input.kind, content),
  })
  addEdge(graph, { source: identity.id, target: session.id, relation: "participa_en", confidence: "EXTRACTED" })
  addEdge(graph, { source: session.id, target: memory.id, relation: "recuerda", confidence: "EXTRACTED" })
  compactGraph(graph)
  graph.metadata = { ...(graph.metadata ?? {}), lastLuisMemory: now, memoryVersion: "luis-v1" }
  await mkdir(graphDirectory(), { recursive: true })
  const temp = `${graphPath()}.tmp`
  await writeFile(temp, JSON.stringify(graph, null, 2), "utf8")
  await rename(temp, graphPath())
  await writeGraphViewer(graph)
}

export async function retrieveLuisMemory(query: string, limit = 8) {
  const graph = await loadGraph()
  const queryTokens = memoryTokens(query)
  const now = Date.now()
  const ranked = graph.nodes
    .filter((node) => node.id.startsWith("luis:") && node.type !== "identity" && node.content)
    .map((node) => {
      const tokens = memoryTokens(`${node.label} ${node.content ?? ""}`)
      const overlap = [...queryTokens].filter((token) => tokens.has(token)).length
      const ageDays = Math.max(0, (now - node.updated) / 86_400_000)
      const recency = Math.max(0, 0.15 - ageDays / 3650)
      const score = overlap * 2 + (node.importance ?? importance(node.type, node.content ?? "")) + recency
      return { node, score, overlap }
    })
    .filter((item) => queryTokens.size === 0 || item.overlap > 0 || (item.node.importance ?? 0) >= 0.8)
    .sort((a, b) => b.score - a.score || b.node.updated - a.node.updated)
    .slice(0, Math.max(1, limit))

  if (ranked.length === 0) return undefined
  return [
    "<luis_memory>",
    "Recuerdos relevantes del grafo persistente. Úsalos como contexto, pero prioriza la petición actual:",
    ...ranked.map(({ node }) => `- [${node.type}] ${node.label}: ${redact(node.content ?? "")}`),
    "</luis_memory>",
  ].join("\n")
}

export function recordLuisMemory(input: {
  sessionID: string
  kind: Exclude<LuisMemoryKind, "identity">
  label: string
  content: string
  source?: string
}) {
  const task = memoryQueue.then(() => writeLuisMemory(input))
  memoryQueue = task.catch(() => {})
  return task
}

export async function refreshLuisMemoryGraph() {
  const graph = await loadGraph()
  await writeGraphViewer(graph)
}

export * as LuisMemory from "./memory"
