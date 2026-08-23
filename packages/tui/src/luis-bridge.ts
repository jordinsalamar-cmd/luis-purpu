import { readFileSync, unlinkSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const inputFile = join(tmpdir(), "luis-companion-input.json")

export function takeLuisInput() {
  try {
    const payload = JSON.parse(readFileSync(inputFile, "utf8")) as { text?: unknown }
    unlinkSync(inputFile)
    return typeof payload.text === "string" ? payload.text.trim() : ""
  } catch {
    return ""
  }
}
