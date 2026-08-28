import { redactLuisCreatorCommand } from "./creator"

export function redactLuisSensitiveText(value: string, limit = 4000) {
  return redactLuisCreatorCommand(value)
    .replace(/-----BEGIN [^-]+-----[\s\S]*?-----END [^-]+-----/gi, "[private-key-redacted]")
    .replace(/\b(?:eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b/g, "[token-redacted]")
    .replace(/(https?:\/\/[^\s/@]+):[^\s/@]+@/gi, "$1:[credential-redacted]@")
    .replace(
      /(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|pwd|secret|private[_-]?key|authorization|cookie|session[_-]?token)\s*[:=]\s*[^\s,;]+/gi,
      "$1=[redacted]",
    )
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [redacted]")
    .slice(0, limit)
}

export * as LuisRedaction from "./redaction"
