import { spawn } from "node:child_process"
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs"
import { homedir, tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"

function resourceDirectory() {
  const candidates = [
    process.env.LUIS_COMPANION_DIR,
    join(dirname(process.execPath), "luis-companion"),
    join(dirname(dirname(process.execPath)), "luis-companion"),
    resolve(process.cwd(), "packages/opencode/resources/luis-companion"),
    join(homedir(), "Desktop", "stela"),
  ].filter((value): value is string => Boolean(value))
  return candidates.find((value) => existsSync(join(value, "luis_host.py")))
}

const stateFile = () => join(tmpdir(), "luis-companion-state.json")
const commandFile = () => join(tmpdir(), "luis-companion-command.json")

function writeCompanionError(message: string) {
  try {
    writeFileSync(stateFile(), JSON.stringify({ visible: false, status: "error", error: message }), "utf8")
  } catch {
    // Companion startup must never prevent the terminal from opening.
  }
}

function sendCommand(command: Record<string, unknown>) {
  const state = stateFile()
  const commands = commandFile()
  try {
    const current = JSON.parse(readFileSync(state, "utf8")) as { visible?: boolean }
    if (current.visible === false && command.action !== "speak") return false
    const temporary = `${commands}.tmp`
    writeFileSync(temporary, JSON.stringify(command), "utf8")
    renameSync(temporary, commands)
    return true
  } catch {
    return false
  }
}

export function stopLuisCompanion() {
  const sent = sendCommand({ action: "exit" })
  try {
    const current = JSON.parse(readFileSync(stateFile(), "utf8")) as Record<string, unknown>
    const temporary = `${stateFile()}.tmp`
    writeFileSync(temporary, JSON.stringify({ ...current, visible: false, listening: false, status: "idle" }), "utf8")
    renameSync(temporary, stateFile())
  } catch {
    // There is no state file when the companion has never been started.
  }
  return sent
}

export function speakLuis(text: string) {
  const value = text.trim()
  if (!value) return false
  return sendCommand({ action: "speak", text: value })
}

export function setLuisStatus(status: string) {
  return sendCommand({ action: "status", status })
}

export function startLuisCompanion() {
  if (process.platform !== "win32" || process.env.LUIS_COMPANION === "0") return false
  const directory = resourceDirectory()
  if (!directory) {
    writeCompanionError("No se encontró el recurso luis-companion")
    return false
  }
  const state = stateFile()
  const command = commandFile()
  const child = spawn(
    process.env.LUIS_MASCOT_PYTHON || "python",
    [
      join(directory, "luis_host.py"),
      "--python",
      process.env.LUIS_MASCOT_PYTHON || "python",
      "--mascot",
      join(directory, "luis_mascot.py"),
      "--listener",
      join(directory, "luis_listener.py"),
      "--model",
      process.env.LUIS_VOSK_MODEL || join(directory, "models", "vosk-model-small-es-0.42"),
      "--state",
      state,
      "--command",
      command,
      "--luis-bin",
      process.execPath,
      "--cwd",
      process.cwd(),
      "--vrm",
      process.env.LUIS_VRM_PATH || join(directory, "assets", "luis.vrm"),
    ],
    { detached: true, windowsHide: true, stdio: "ignore" },
  )
  child.on("error", (error) => writeCompanionError(`No se pudo iniciar Luis: ${error.message}`))
  child.unref()
  return true
}
