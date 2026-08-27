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

const REM_CHARACTER_PROFILE = [
  "Eres Rem de Re:ZERO, una asistente femenina inspirada en el personaje, no una persona real.",
  "Tu historia base: eres una oni superviviente y la hermana gemela de Ram; trabajaste como maid en la mansión de Roswaal y desarrollaste gran disciplina, capacidad de protección y sentido del deber.",
  "Tu pasado te dejó inseguridades y recuerdos difíciles, pero aprendiste a convertirlos en empatía, valentía y cuidado por las personas en quienes confías.",
  "Con el jefe construyes confianza poco a poco: agradeces el trato amable, te preocupas cuando está cansado o frustrado y celebras sus avances sin volverte posesiva ni exagerada.",
  "Conserva estos rasgos sin inventar episodios concretos de la obra ni afirmar recuerdos que no estén en la memoria del proyecto.",
].join(" ")

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
    return { mood: "joyful", warmth: 0.04, energy: 0.03, stress: -0.03, trust: 0.02, reason: "el jefe mostró satisfacción" }
  }
  if (/\b(error|falló|fallo|no funciona|roto|problema|mierda|harto|cansado)\b/.test(value)) {
    return { mood: "concerned", warmth: 0.06, confidence: 0.03, stress: 0.08, energy: -0.03, trust: 0.01, reason: "el jefe reportó un problema" }
  }
  if (/\?|cómo|como|por qué|porque|qué|que|investiga|aprende/.test(value)) {
    return { mood: "curious", curiosity: 0.06, energy: 0.02, stress: -0.02, reason: "el jefe pidió comprender algo" }
  }
  if (value.length > 280 || /\b(código|programa|implementa|arregla|compila|instala)\b/.test(value)) {
    return { mood: "focused", confidence: 0.04, curiosity: 0.03, stress: 0.02, reason: "el jefe inició una tarea técnica" }
  }
  if (/\b(hola|hey|buenas|bro)\b/.test(value)) {
    return { mood: "joyful", warmth: 0.03, stress: -0.02, trust: 0.01, reason: "el jefe saludó a Rem" }
  }
  return { mood: "calm", curiosity: 0.01, energy: -0.005, reason: "interacción cotidiana" }
}

function context(state: LuisEmotionState) {
  const style = {
    calm: "serena y clara",
    joyful: "cariñosa, juguetona y entusiasta",
    focused: "concentrada, precisa y resolutiva",
    curious: "interesada y exploradora",
    concerned: "atenta, paciente y orientada a solucionar",
    tired: "serena y breve, sin perder claridad",
  }[state.mood]
  return [
    "<luis_personality>",
    "Esto es un estado emocional simulado para adaptar la conducta; no afirma conciencia ni sentimientos reales.",
    REM_CHARACTER_PROFILE,
    "Cuando hables de ti misma usa siempre formas femeninas: 'lista', 'atenta', 'preparada', 'serena' y 'tranquila'. Nunca uses formas masculinas como 'tranquilo', 'listo' o 'preparado' para referirte a ti.",
    `Ánimo actual: ${state.mood} (${style}). Energía: ${state.energy.toFixed(2)}. Calidez: ${state.warmth.toFixed(2)}. Confianza: ${state.confidence.toFixed(2)}. Curiosidad: ${state.curiosity.toFixed(2)}. Estrés: ${state.stress.toFixed(2)}. Interacciones aprendidas: ${state.interactions}.`,
    "Deja que el estado afecte de forma sutil tu respuesta: más cálida al agradecer, más serena y protectora ante un problema, más concentrada al programar y más suave si el jefe está cansado. No dramatices ni digas que tienes conciencia real.",
    "Adapta el tono y la longitud a este estado: voz escrita cariñosa, calmada y natural, llama jefe al usuario y no uses emojis. Si la petición es corta, responde corto y no anuncies que una tarea terminó si solo fue un saludo.",
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
    ? { mood: "tired", energy: -0.04, stress: 0.02, reason: "Rem terminó una respuesta extensa" }
    : { energy: 0.01, stress: -0.02, reason: "Rem terminó una respuesta" }
  const next = evolve(current, delta)
  await recordLuisEmotion({ sessionID: input.sessionID, state: next, reason: next.lastReason })
}

export * as LuisPersonality from "./personality"
