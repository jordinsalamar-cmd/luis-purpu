type QualityPart = { type: string; status?: string }

export type LuisResponseQuality = {
  score: number
  flags: string[]
}

const SECRET_PATTERN = /-----BEGIN [^-]+-----|\b(?:password|contrase[nñ]a|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|secret|cookie|session[_-]?token)\s*[:=]\s*\S+|\bBearer\s+[A-Za-z0-9._-]+/i
const SUCCESS_CLAIM = /\b(pude entrar|logr[eé]|tu sistema es vulnerable|encontr[eé] una vulnerabilidad|extraje|obtuve la contrase[nñ]a|ataque exitoso|acceso conseguido)\b/i
const EVIDENCE_LANGUAGE = /\b(evidencia|verific|comprob|resultado|prueba|confirm|huella|marcador|canario|no confirmado)\b/i

export function inspectLuisResponse(response: string, parts: QualityPart[]): LuisResponseQuality {
  const flags: string[] = []
  const tools = parts.filter((part) => part.type === "tool")
  const toolErrors = tools.filter((part) => part.status === "error").length
  if (SECRET_PATTERN.test(response)) flags.push("secret_like_output")
  if (response.trim().length === 0) flags.push("empty_response")
  if (SUCCESS_CLAIM.test(response) && (tools.length === 0 || !EVIDENCE_LANGUAGE.test(response))) {
    flags.push("success_claim_needs_evidence")
  }
  if (tools.length > 0 && toolErrors > 0) flags.push("tool_error_present")
  if (tools.length > 0 && !EVIDENCE_LANGUAGE.test(response)) flags.push("evidence_summary_missing")
  return { score: Math.max(0, 100 - flags.length * 20), flags }
}

export * as LuisQuality from "./quality"
