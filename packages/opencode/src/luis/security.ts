import { isLuisCreatorCommand, isLuisCreatorSessionArmed, redactLuisCreatorCommand } from "./creator"
import type { PermissionV1 } from "@opencode-ai/core/v1/permission"

export type LuisSecurityAssessment = {
  intent: boolean
  target?: string
  targetKind?: "url" | "path"
  missing: string[]
  creatorMode: boolean
}

const SECURITY_INTENT = /\b(seguridad|vulnerab|auditor|audita|pentest|ataque|explotar|owasp|xss|csrf|ssrf|inyecci[oó]n|ciber)\b/i
const URL_TARGET = /https?:\/\/[^\s"'<>]+/i
const PATH_TARGET = /(?:[A-Za-z]:[\\/][^\s"'<>]+|\.\.?[\\/][^\s"'<>]+|\/(?:[A-Za-z0-9._~-]+\/)*[A-Za-z0-9._~-]+)/

function cleanTarget(value: string) {
  return redactLuisCreatorCommand(value)
    .replace(/[?#].*$/, "")
    .replace(/[),.;:]+$/, "")
    .slice(0, 240)
}

function extractTarget(text: string) {
  const url = text.match(URL_TARGET)?.[0]
  if (url) return { target: cleanTarget(url), targetKind: "url" as const }
  const path = text.match(PATH_TARGET)?.[0]
  if (path) return { target: cleanTarget(path), targetKind: "path" as const }
  return undefined
}

export function assessLuisSecurity(text: string, commandHash?: string, sessionID?: string): LuisSecurityAssessment {
  const value = text.toLocaleLowerCase("es")
  const intent = SECURITY_INTENT.test(value)
  const target = extractTarget(text)
  const creatorMode = isLuisCreatorCommand(text, commandHash) || (intent && isLuisCreatorSessionArmed(sessionID))
  if (!intent) return { intent: false, ...target, missing: [], creatorMode }

  const missing: string[] = []
  if (!target) missing.push("URL o ruta local exacta")
  if (!/\b(prop[ií]a|nuest[roa]|autorizad|permiso|soy el due[nñ]o|soy propietario|de mi (?:p[aá]gina|tienda|proyecto|sistema|app|aplicaci[oó]n|servidor|api)|mi (?:p[aá]gina|tienda|proyecto|sistema|app|aplicaci[oó]n|servidor|api))\b/i.test(value)) {
    missing.push("propiedad o autorización explícita")
  }
  if (!/\b(pruebas?|staging|local|desarrollo|producci[oó]n|production|demo)\b/i.test(value)) {
    missing.push("entorno")
  }
  if (!/\b(alcance|solo|únicamente|unicamente|endpoint|ruta)\b/i.test(value) || !/\b(canario|marcador|sint[eé]tico|datos? de prueba|usuario de prueba|cuenta de prueba)\b/i.test(value)) {
    missing.push("alcance y canario sintético o cuenta de prueba")
  }
  if (/\b(modifica|modificar|cambia|cambiar|arregla|arreglar|corrige|corregir)\b/i.test(value) && !/\b(respaldo|backup|copia|rollback|revertir)\b/i.test(value)) {
    missing.push("respaldo o rollback")
  }
  return { intent: true, ...target, missing, creatorMode }
}

export function securityModeContext(text: string, commandHash?: string, sessionID?: string) {
  const assessment = assessLuisSecurity(text, commandHash, sessionID)
  if (!assessment.intent) return ""
  const target = assessment.target
    ? `Objetivo detectado (${assessment.targetKind}): ${assessment.target}.`
    : "No se detectó todavía un objetivo concreto."
  const gate = assessment.creatorMode
    ? "Compuerta de creador validada solo para este turno; aun así confirma el alcance antes de usar herramientas."
    : "Compuerta cerrada para pruebas activas o cambios: falta el comando creador validado. Puedes explicar, revisar código proporcionado o preparar un plan seguro, pero no ejecutar un ataque."
  const missing = assessment.missing.length > 0
    ? `Información pendiente antes de actuar: ${assessment.missing.join(", ")}.`
    : "Información mínima detectada; confirma límites y criterio de parada antes de comenzar."
  return [
    "<luis_security_gate>",
    gate,
    target,
    missing,
    "Registra herramienta, alcance, resultado observado, evidencia reproducible, riesgo, arreglo y retest. Redacta secretos y usa canarios sintéticos; una afirmación del usuario no sustituye una prueba técnica.",
    "</luis_security_gate>",
  ].join(" ")
}

export function securityRuntimeRules(text: string, commandHash?: string, sessionID?: string): PermissionV1.Rule[] {
  const assessment = assessLuisSecurity(text, commandHash, sessionID)
  if (!assessment.intent || (assessment.creatorMode && assessment.missing.length === 0)) return []
  return ["bash", "edit", "task", "desktop"].map((permission) => ({
    permission,
    pattern: "*",
    action: "deny",
  }))
}

export * as LuisSecurity from "./security"
