import {
  getLuisEmotion,
  recordLuisEmotion,
  type LuisEmotionState,
  type LuisMood,
} from "./memory"

type EmotionDelta = Partial<Pick<LuisEmotionState, "energy" | "warmth" | "confidence" | "curiosity" | "stress" | "trust">> & {
  mood?: LuisMood
  reason: string
}

function clamp(value: number) {
  return Math.max(0, Math.min(1, value))
}

function evolve(current: LuisEmotionState, delta: EmotionDelta): LuisEmotionState {
  const next = { ...current }
  for (const key of ["energy", "warmth", "confidence", "curiosity", "stress", "trust"] as const) {
    const change = delta[key] ?? 0
    next[key] = clamp(next[key] + change)
  }
  if (delta.mood) next.mood = delta.mood
  next.interactions += 1
  next.lastReason = delta.reason
  next.updated = Date.now()
  return next
}

function infer(text: string): EmotionDelta {
  const value = text.toLocaleLowerCase("es")
  if (/\b(gracias|genial|perfecto|jaj|jeje|me gusta|bien hecho)\b/.test(value)) {
    return { mood: "joyful", warmth: 0.04, energy: 0.03, stress: -0.03, reason: "el jefe mostró satisfacción" }
  }
  if (/\b(error|falló|fallo|no funciona|roto|problema|mierda|harto|cansado)\b/.test(value)) {
    return { mood: "concerned", warmth: 0.06, confidence: 0.03, stress: 0.08, energy: -0.03, reason: "el jefe reportó un problema" }
  }
  if (/\?|cómo|como|por qué|porque|qué|que|investiga|aprende/.test(value)) {
    return { mood: "curious", curiosity: 0.06, energy: 0.02, stress: -0.02, reason: "el jefe pidió comprender algo" }
  }
  if (value.length > 280 || /\b(código|programa|implementa|arregla|compila|instala)\b/.test(value)) {
    return { mood: "focused", confidence: 0.04, curiosity: 0.03, stress: 0.02, reason: "el jefe inició una tarea técnica" }
  }
  if (/\b(hola|hey|buenas|bro)\b/.test(value)) {
    return { mood: "joyful", warmth: 0.03, stress: -0.02, reason: "el jefe saludó a Luis" }
  }
  return { mood: "calm", curiosity: 0.01, energy: -0.005, reason: "interacción cotidiana" }
}

function context(state: LuisEmotionState) {
  const style = {
    calm: "sereno y claro",
    joyful: "cálido, juguetón y entusiasta",
    focused: "concentrado, preciso y resolutivo",
    curious: "interesado y explorador",
    concerned: "atento, paciente y orientado a solucionar",
    tired: "tranquilo y breve, sin perder claridad",
  }[state.mood]
  return [
    "<luis_personality>",
    "Esto es un estado emocional simulado para adaptar la conducta; no afirma conciencia ni sentimientos reales.",
    `Ánimo actual: ${state.mood} (${style}). Energía: ${state.energy.toFixed(2)}. Calidez: ${state.warmth.toFixed(2)}. Confianza: ${state.confidence.toFixed(2)}. Curiosidad: ${state.curiosity.toFixed(2)}. Estrés: ${state.stress.toFixed(2)}. Interacciones aprendidas: ${state.interactions}.`,
    "Adapta el tono y la longitud a este estado, mantén honestidad, llama jefe al usuario y no uses emojis. Si la petición es corta, responde corto.",
    "</luis_personality>",
  ].join("\n")
}

export async function prepareLuisPersonality(input: { sessionID: string; text: string }) {
  const current = await getLuisEmotion()
  const next = evolve(current, infer(input.text))
  void recordLuisEmotion({ sessionID: input.sessionID, state: next, reason: next.lastReason })
  return context(next)
}

export async function settleLuisPersonality(input: { sessionID: string; text: string }) {
  const current = await getLuisEmotion()
  const delta: EmotionDelta = input.text.length > 1200
    ? { mood: "tired", energy: -0.04, stress: 0.02, reason: "Luis terminó una respuesta extensa" }
    : { energy: 0.01, stress: -0.02, reason: "Luis terminó una respuesta" }
  const next = evolve(current, delta)
  await recordLuisEmotion({ sessionID: input.sessionID, state: next, reason: next.lastReason })
}

export * as LuisPersonality from "./personality"
