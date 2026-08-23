import type { Provider } from "@/provider/provider"

export type LuisModelRef = {
  providerID: string
  modelID: string
}

export function configuredFallbacks(): LuisModelRef[] {
  const raw = process.env.LUIS_MODEL_FALLBACKS ?? ""
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .flatMap((value) => {
      const separator = value.indexOf("/") >= 0 ? "/" : ":"
      const index = value.indexOf(separator)
      if (index <= 0 || index === value.length - 1) return []
      return [{ providerID: value.slice(0, index), modelID: value.slice(index + 1) }]
    })
}

export function isModelLimitError(error: unknown) {
  const text = (() => {
    try {
      return JSON.stringify(error)
    } catch {
      return String(error)
    }
  })().toLowerCase()
  return /429|quota|usage.?limit|rate.?limit|resource.?exhausted|too many requests|credits? exhausted|capacity/.test(
    text,
  )
}

export function sameModel(a: Provider.Model, b: Provider.Model) {
  return a.providerID === b.providerID && a.id === b.id
}
