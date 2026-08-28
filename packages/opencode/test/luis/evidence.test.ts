import { afterEach, beforeEach, expect, it } from "bun:test"
import { mkdtemp, readFile, rmdir, unlink } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { recordLuisEvidence } from "../../src/luis/evidence"
import { redactLuisSensitiveText } from "../../src/luis/redaction"

const variable = "LUIS_GRAPH_ROOT"
const previous = process.env[variable]
let temporaryRoot = ""

beforeEach(async () => {
  temporaryRoot = await mkdtemp(join(tmpdir(), "rem-evidence-test-"))
  process.env[variable] = temporaryRoot
})

afterEach(async () => {
  if (previous === undefined) delete process.env[variable]
  else process.env[variable] = previous
  const output = join(temporaryRoot, "graphify-out")
  await unlink(join(output, "rem-evidence.jsonl")).catch(() => {})
  await rmdir(output).catch(() => {})
  await rmdir(temporaryRoot).catch(() => {})
})

it("records timing and tool outcomes while redacting secrets", async () => {
  expect(redactLuisSensitiveText("password=SuperSecret123")).not.toContain("SuperSecret123")
  await recordLuisEvidence({
    sessionID: "session-evidence",
    request: "audita password=SuperSecret123",
    response: "resultado redactado",
    durationMs: 1234.6,
    parts: [
      { type: "tool", id: "one", status: "completed" },
      { type: "tool", id: "two", status: "error" },
      { type: "text", status: "completed" },
    ],
  })

  const path = join(temporaryRoot, "graphify-out", "rem-evidence.jsonl")
  const entry = JSON.parse((await readFile(path, "utf8")).trim())
  expect(entry.durationMs).toBe(1235)
  expect(entry.partCounts).toEqual({ tool: 2, text: 1 })
  expect(entry.toolCount).toBe(2)
  expect(entry.toolErrors).toBe(1)
  expect(entry.toolCompleted).toBe(1)
  expect(JSON.stringify(entry)).not.toContain("SuperSecret123")
})
