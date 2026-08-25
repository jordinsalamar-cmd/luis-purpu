import { spawn } from "node:child_process"
import { existsSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs"
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
const inputFile = () => join(tmpdir(), "luis-companion-input.json")
const inputListeners = new Set<(text: string) => void>()
let inputPoller: ReturnType<typeof setInterval> | undefined

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

function companionHostAlive() {
  const pidPath = stateFile().replace(/\.json$/, ".pid")
  try {
    const pid = Number(readFileSync(pidPath, "utf8").trim())
    if (!Number.isInteger(pid) || pid <= 0) return false
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function pollLuisInput() {
  try {
    const payload = JSON.parse(readFileSync(inputFile(), "utf8")) as { text?: unknown }
    unlinkSync(inputFile())
    const text = typeof payload.text === "string" ? payload.text.trim() : ""
    if (!text) return
    for (const listener of [...inputListeners]) listener(text)
  } catch {
    // The companion writes atomically; a missing or half-written file is normal.
  }
}

export function onLuisInput(listener: (text: string) => void) {
  if (process.platform !== "win32" || process.env.LUIS_COMPANION === "0") return () => {}
  inputListeners.add(listener)
  ensureLuisCompanion()
  inputPoller ??= setInterval(pollLuisInput, 120)
  return () => {
    inputListeners.delete(listener)
    if (inputListeners.size === 0 && inputPoller) {
      clearInterval(inputPoller)
      inputPoller = undefined
    }
  }
}

function companionPython() {
  const configured = process.env.LUIS_MASCOT_PYTHON || "python"
  if (process.platform !== "win32" || !configured.toLowerCase().endsWith("python.exe")) return configured
  const windowless = join(dirname(configured), "pythonw.exe")
  return existsSync(windowless) ? windowless : configured
}

function ensureLuisCompanion() {
  if (process.platform !== "win32" || process.env.LUIS_COMPANION === "0") return
  let state: { visible?: boolean; voice?: boolean } | undefined
  try {
    state = JSON.parse(readFileSync(stateFile(), "utf8")) as { visible?: boolean; voice?: boolean }
  } catch {
    // The host may not have created its state file yet.
  }

  // A closed/crashed host must not silently swallow speech commands. Preserve an
  // intentional mute while restarting only when the companion itself is gone.
  if (state?.voice === false && state.visible === true && companionHostAlive()) return
  if (state?.visible !== true || !companionHostAlive()) startLuisCompanion()
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
  ensureLuisCompanion()
  return sendCommand({ action: "speak", text: value })
}

export function setLuisStatus(status: string) {
  return sendCommand({ action: "status", status })
}

export function setLuisVision(enabled: boolean) {
  ensureLuisCompanion()
  return sendCommand({ action: enabled ? "vision_on" : "vision_off" })
}

export function startLuisCompanion() {
  if (process.platform !== "win32" || process.env.LUIS_COMPANION === "0") return false
  if (companionHostAlive()) return true
  const directory = resourceDirectory()
  if (!directory) {
    writeCompanionError("No se encontró el recurso luis-companion")
    return false
  }
  const state = stateFile()
  const command = commandFile()
  const python = companionPython()
  const child = spawn(
    python,
    [
      join(directory, "luis_host.py"),
      "--python",
      python,
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
