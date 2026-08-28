import { createHash } from "node:crypto"
import { appendFile, copyFile, mkdir, stat, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { luisGraphDirectory } from "./memory"
import { redactLuisSensitiveText } from "./redaction"

type EvidencePart = {
  type: string
  id?: string
  status?: string
}

type EvidenceInput = {
  sessionID: string
  request: string
  response: string
  parts: EvidencePart[]
  durationMs?: number
  quality?: { score: number; flags: string[] }
}

let evidenceQueue: Promise<void> = Promise.resolve()
const MAX_EVIDENCE_BYTES = 2 * 1024 * 1024

function redact(value: string) {
  return redactLuisSensitiveText(value)
}

function fingerprint(value: string) {
  return createHash("sha256").update(value).digest("hex")
}

function evidencePath() {
  return join(luisGraphDirectory(), "rem-evidence.jsonl")
}

async function rotateEvidenceIfNeeded(path: string) {
  try {
    const info = await stat(path)
    if (info.size <= MAX_EVIDENCE_BYTES) return
    await copyFile(path, `${path}.1`)
    await writeFile(path, "", "utf8")
  } catch {
    // A missing or temporarily unavailable log must not interrupt the turn.
  }
}

async function writeEvidence(input: EvidenceInput) {
  const safeRequest = redact(input.request)
  const safeResponse = redact(input.response)
  const partCounts = input.parts.reduce<Record<string, number>>((counts, part) => {
    counts[part.type] = (counts[part.type] ?? 0) + 1
    return counts
  }, {})
  const toolParts = input.parts.filter((part) => part.type === "tool")
  const entry = {
    version: 1,
    created: new Date().toISOString(),
    sessionID: input.sessionID.slice(0, 80),
    requestSHA256: fingerprint(safeRequest),
    responseSHA256: fingerprint(safeResponse),
    requestChars: safeRequest.length,
    responseChars: safeResponse.length,
    durationMs: typeof input.durationMs === "number" ? Math.max(0, Math.round(input.durationMs)) : undefined,
    partCounts,
    toolCount: toolParts.length,
    toolErrors: toolParts.filter((part) => part.status === "error").length,
    toolCompleted: toolParts.filter((part) => part.status === "completed").length,
    qualityScore: input.quality?.score,
    qualityFlags: input.quality?.flags ?? [],
    parts: input.parts.slice(0, 80),
    note: "Metadatos locales del turno; no prueban por sí solos un resultado externo.",
  }
  await mkdir(luisGraphDirectory(), { recursive: true })
  const path = evidencePath()
  await rotateEvidenceIfNeeded(path)
  await appendFile(path, `${JSON.stringify(entry)}\n`, "utf8")
}

export function recordLuisEvidence(input: EvidenceInput) {
  const task = evidenceQueue.then(() => writeEvidence(input))
  evidenceQueue = task.catch(() => {})
  return task
}

export * as LuisEvidence from "./evidence"
