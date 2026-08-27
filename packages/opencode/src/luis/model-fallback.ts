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
  const text = errorText(error)
  return /429|quota|usage.?limit|rate.?limit|resource.?exhausted|too many requests|credits? exhausted|capacity/.test(
    text,
  )
}

export function isProviderUnavailableError(error: unknown) {
  const text = errorText(error)
  return /endpoint is unavailable|upstream request failed|service unavailable|bad gateway|gateway timeout|fetch failed|network error|connection (?:refused|reset|timed out)|econn(?:refused|reset|timedout)|\b(?:502|503|504)\b/.test(
    text,
  )
}

function errorText(error: unknown) {
  try {
    return JSON.stringify(error).toLowerCase()
  } catch {
    return String(error).toLowerCase()
  }
}

export function availableFallbacks(providers: Record<string, Provider.Info>, current: Provider.Model): LuisModelRef[] {
  const providerPriority = ["ollama", "lmstudio", "llamacpp", "google", "google-generative-ai", "openai"]
  const modelPriority = ["qwen", "coder", "phi", "gemma", "flash", "mini", "small"]

  return Object.values(providers)
    .filter((provider) => provider.id !== current.providerID)
    .sort((left, right) => {
      const leftRank = providerPriority.indexOf(left.id)
      const rightRank = providerPriority.indexOf(right.id)
      return (leftRank < 0 ? providerPriority.length : leftRank) - (rightRank < 0 ? providerPriority.length : rightRank)
    })
    .flatMap((provider) =>
      Object.values(provider.models)
        .filter(
          (model) =>
            model.status !== "deprecated" &&
            model.capabilities.input.text &&
            model.capabilities.output.text,
        )
        .sort((left, right) => {
          const leftRank = modelPriority.findIndex((part) => left.id.toLowerCase().includes(part))
          const rightRank = modelPriority.findIndex((part) => right.id.toLowerCase().includes(part))
          return (leftRank < 0 ? modelPriority.length : leftRank) - (rightRank < 0 ? modelPriority.length : rightRank)
        })
        .map((model) => ({ providerID: provider.id, modelID: model.id })),
    )
}

export function sameModel(a: Provider.Model, b: Provider.Model) {
  return a.providerID === b.providerID && a.id === b.id
}
