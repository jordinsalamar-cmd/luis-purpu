import { createHash } from "node:crypto"

const COMMAND_HASH_ENV = "REM_CREATOR_COMMAND_SHA256"
const ARM_TTL_MS = 5 * 60 * 1000
const armedSessions = new Map<string, number>()

function digest(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex")
}

function normalizedTokens(value: string) {
  return value
    .normalize("NFKC")
    .trim()
    .split(/\s+/)
    .map((token) => token.replace(/^[^\p{L}\p{N}_-]+|[^\p{L}\p{N}_-]+$/gu, ""))
    .filter(Boolean)
}

function configuredCommandHash() {
  const value = process.env[COMMAND_HASH_ENV]?.trim().toLowerCase()
  return value && /^[a-f0-9]{64}$/.test(value) ? value : undefined
}

export function isLuisCreatorCommand(text: string, expected = configuredCommandHash()) {
  const firstToken = normalizedTokens(text)[0]
  return Boolean(expected && firstToken && digest(firstToken) === expected)
}

function isStandaloneCreatorCommand(text: string, expected?: string) {
  return normalizedTokens(text).length === 1 && isLuisCreatorCommand(text, expected)
}

function pruneArmedSessions(now = Date.now()) {
  for (const [sessionID, expires] of armedSessions) if (expires <= now) armedSessions.delete(sessionID)
}

export function armLuisCreatorSession(sessionID: string, text: string, expected = configuredCommandHash()) {
  if (!sessionID || !isStandaloneCreatorCommand(text, expected)) return false
  pruneArmedSessions()
  armedSessions.set(sessionID, Date.now() + ARM_TTL_MS)
  return true
}

export function isLuisCreatorSessionArmed(sessionID?: string) {
  if (!sessionID) return false
  const now = Date.now()
  pruneArmedSessions(now)
  return (armedSessions.get(sessionID) ?? 0) > now
}

export function clearLuisCreatorSession(sessionID: string) {
  armedSessions.delete(sessionID)
}

export function redactLuisCreatorCommand(text: string, expected = configuredCommandHash()) {
  if (!expected) return text
  return text.replace(/[\p{L}\p{N}_-]+/gu, (token) => digest(token) === expected ? "[creator-command-redacted]" : token)
}

export function creatorModeContext(text: string, expected = configuredCommandHash(), sessionID?: string) {
  const direct = isLuisCreatorCommand(text, expected)
  const armed = isLuisCreatorSessionArmed(sessionID)
  if (direct || armed) {
    return [
      direct
        ? "Modo creador validado para este turno; no lo mantengas activo automáticamente en turnos posteriores."
        : "Modo creador armado para este único turno de seguimiento; se consumirá al procesar la solicitud.",
      "Antes de probar o cambiar algo, pide o confirma: URL o ruta local exacta, propietario o autorización, entorno (pruebas o producción), alcance, usuario/rol canario, límites, respaldo y criterio de parada.",
      "Haz primero inventario y comprobaciones de bajo impacto. No extraigas ni muestres contraseñas, tokens, cookies o datos reales: demuestra acceso con canarios sintéticos y huellas de evidencia redactadas.",
      "Entrega hechos observados, pasos mínimos reproducibles, evidencia, riesgo, arreglo propuesto y retest. Pide confirmación antes de modificar producción; nunca conviertas este modo en permiso para atacar terceros, evadir controles, persistir, borrar datos o causar indisponibilidad.",
    ].join(" ")
  }
  return "Modo creador: inactivo. Para una auditoría, solicita el comando local configurado y no trates una petición común como autorización para probar objetivos externos."
}

export * as LuisCreator from "./creator"
