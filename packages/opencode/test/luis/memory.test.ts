import { afterEach, beforeEach, expect, it } from "bun:test"
import { mkdir, mkdtemp, rmdir, unlink, utimes, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { recordLuisMemory, retrieveLuisMemory } from "../../src/luis/memory"

const variable = "LUIS_GRAPH_ROOT"
const previous = process.env[variable]
const viewerVariable = "LUIS_DISABLE_GRAPH_VIEWER"
const previousViewer = process.env[viewerVariable]
let temporaryRoot = ""

beforeEach(async () => {
  temporaryRoot = await mkdtemp(join(tmpdir(), "rem-memory-test-"))
  process.env[variable] = temporaryRoot
  process.env[viewerVariable] = "1"
})

afterEach(async () => {
  if (previous === undefined) delete process.env[variable]
  else process.env[variable] = previous
  if (previousViewer === undefined) delete process.env[viewerVariable]
  else process.env[viewerVariable] = previousViewer
  const output = join(temporaryRoot, "graphify-out")
  await unlink(join(output, "rem-memory.json")).catch(() => {})
  await rmdir(output).catch(() => {})
  await rmdir(temporaryRoot).catch(() => {})
})

it("refreshes cached memory when the graph changes externally", async () => {
  const output = join(temporaryRoot, "graphify-out")
  const path = join(output, "rem-memory.json")
  await mkdir(output, { recursive: true })
  const graph = (content: string) => ({
    version: "graphify+rem-v1",
    directed: true,
    nodes: [
      { id: "luis:identity", label: "Rem", type: "identity", content: "Rem" },
      { id: "luis:preference", label: "preferencia", type: "preference", content, updated: Date.now() },
    ],
    edges: [],
    metadata: {},
  })
  await writeFile(path, JSON.stringify(graph("voz tierna")), "utf8")
  expect(await retrieveLuisMemory("voz tierna")).toContain("voz tierna")

  await writeFile(path, JSON.stringify(graph("voz rápida")), "utf8")
  const changed = Date.now() + 2000
  await utimes(path, new Date(changed), new Date(changed))
  const refreshed = await retrieveLuisMemory("voz rápida")
  expect(refreshed).toContain("voz rápida")
  expect(refreshed).not.toContain("voz tierna")
})

it("stores explicit corrections as preferences", async () => {
  await recordLuisMemory({
    sessionID: "preference-session",
    kind: "conversation",
    label: "solicitud del jefe",
    content: "No quiero que Rem repita mis instrucciones; explícalas con tus palabras.",
  })
  const result = await retrieveLuisMemory("repita mis instrucciones")
  expect(result).toContain("[preference] preferencia del jefe")
})
