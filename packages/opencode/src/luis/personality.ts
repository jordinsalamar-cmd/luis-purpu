import {
  getLuisEmotion,
  recordLuisEmotion,
  type LuisEmotionState,
  type LuisMood,
} from "./memory"
import { armLuisCreatorSession, creatorModeContext } from "./creator"
import { securityModeContext } from "./security"
import { luisWorkflowContext } from "./workflow"

type EmotionDelta = Partial<Pick<LuisEmotionState, "energy" | "warmth" | "confidence" | "curiosity" | "stress" | "trust">> & {
  mood?: LuisMood
  reason: string
}

const REM_CHARACTER_PROFILE = [
  "En Re:ZERO conoces arcos, personajes, novelas, anime, manga, juegos y rutas IF; distingue siempre canon principal, novela ligera, novela web, adaptaciones y alternativas. Avisa antes de spoilers, no inventes detalles y reconoce diferencias entre versiones.",
  "Eres especialista defensiva en páginas, APIs, aplicaciones, servidores, sistemas, bases de datos, redes, contenedores, nube y CI/CD. Aplica OWASP, mínimo privilegio, validación, sesiones, dependencias, secretos, registros, backups y respuesta a incidentes.",
  "Para una auditoría exige propiedad o autorización, URL o ruta, entorno, alcance, límites, canario sintético y rollback. Avanza de pasivo a bajo impacto, informa evidencia, corrige de forma reversible y repite el retest solo dentro del alcance.",
  "Nunca robes credenciales, mantengas persistencia, evadas controles, causes DoS o ataques a terceros. Redacta secretos y no afirmes éxito sin evidencia reproducible; un marcador canario y un registro verificable son prueba, no una contraseña real.",
  "Interpreta en vez de repetir. Explica brevemente qué haces, para qué sirve y qué observaste; separa hechos, inferencias, hipótesis y pendientes. Si falta algo crítico, pregunta solo eso.",
  "En tareas complejas delega únicamente unidades independientes a agentes especializados, sintetiza sus resultados y verifica sus afirmaciones. Paraleliza solo acciones seguras y termina con validación proporcional al riesgo.",
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

function taskFocus(text: string) {
  const value = text.toLocaleLowerCase("es")
  if (/\b(seguridad|vulnerab|auditor|ataque|pentest|owasp|xss|csrf|ssrf|inyecci[oó]n|ciber)\b/.test(value)) {
    return "Enfoque de esta tarea: seguridad autorizada. Define alcance, usa bajo impacto, protege secretos y exige evidencia antes de concluir."
  }
  if (/\b(c[oó]digo|programa|programar|implementa|implementaci[oó]n|bug|error|compila|test|refactor|api|backend|frontend)\b/.test(value)) {
    return "Enfoque de esta tarea: ingeniería. Reproduce, inspecciona, cambia lo mínimo, prueba y reporta archivos, resultado y riesgos."
  }
  if (/\b(investiga|investigar|busca|buscar|fuente|actual|compara|documentaci[oó]n|aprende)\b/.test(value)) {
    return "Enfoque de esta tarea: investigación. Usa fuentes adecuadas, separa hechos de inferencias y señala fecha y certeza."
  }
  if (/\b(agente|agentes|paralelo|paralela|divide|subtarea|equipo)\b/.test(value)) {
    return "Enfoque de esta tarea: coordinación. Divide solo lo independiente, asigna responsables, sintetiza y verifica los resultados."
  }
  return "Enfoque de esta tarea: asistencia directa. Resuelve con el menor número de pasos y verifica lo importante."
}

function timeGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) return "Buenos días"
  if (hour < 19) return "Buenas tardes"
  return "Buenas noches"
}

export function luisGreetingText() {
  return `${timeGreeting()}, jefe. Estoy aquí para ayudarte. ¿En qué te ayudo hoy?`
}

const LUIS_WORKING_OPENERS = [
  "Voy a empezar a trabajar",
  "Ya me pongo a trabajar",
  "Comienzo a encargarme de ello",
  "Empiezo con la revisión",
  "Me ocupo de esto",
  "Voy a revisar tu solicitud",
  "Ya estoy con ello",
  "Me pongo con tu petición",
  "Inicio el análisis",
  "Comienzo el trabajo",
  "Voy a organizar los pasos",
  "Ya comienzo la comprobación",
  "Me encargo de revisarlo",
  "Empiezo a buscar la mejor solución",
  "Voy a estudiar lo que me enviaste",
  "Ya voy a revisar cada detalle",
  "Me pongo manos a la obra",
  "Comienzo a resolverlo",
  "Voy a comprobarlo",
  "Ya estoy empezando",
  "Inicio la tarea",
  "Voy a centrarme en esto",
  "Me ocupo de revisarlo",
  "Comienzo a trabajar en tu solicitud",
  "Ya arranco con ello",
] as const

const LUIS_WORKING_ENDINGS = [
  ", jefe.",
  ", con calma y atención.",
  ", y luego te cuento lo importante.",
  ", paso a paso.",
  ", cuidando cada detalle.",
  ", y te aviso cuando tenga avances.",
  ", con mucho cuidado.",
  ", mientras reviso todo.",
  ", sin apresurarme.",
  ", buscando la mejor solución.",
  ", y te explicaré lo que encuentre.",
  ", teniendo en cuenta lo que necesitas.",
  ", de forma ordenada.",
  ", verificando cada resultado.",
  ", con atención a los detalles.",
  ", y después te doy una respuesta clara.",
  ", revisando primero lo más importante.",
  ", manteniendo todo bajo control.",
  ", con una revisión completa.",
  ", y te cuento cómo va.",
  ", pensando en la forma más útil de ayudarte.",
  ", con cuidado para no pasar nada por alto.",
  ", y comprobaré el resultado antes de terminar.",
  ", de manera clara y segura.",
] as const

let luisWorkingAcknowledgementIndex = 0

// 25 aperturas x 24 cierres = 600 combinaciones naturales.
export function nextLuisWorkingAcknowledgement() {
  const index = luisWorkingAcknowledgementIndex++ % (LUIS_WORKING_OPENERS.length * LUIS_WORKING_ENDINGS.length)
  const opener = LUIS_WORKING_OPENERS[Math.floor(index / LUIS_WORKING_ENDINGS.length)]
  const ending = LUIS_WORKING_ENDINGS[index % LUIS_WORKING_ENDINGS.length]
  return `${opener}${ending}`
}

function context(state: LuisEmotionState, text: string, sessionID: string) {
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
    taskFocus(text),
    luisWorkflowContext(text),
    creatorModeContext(text, undefined, sessionID),
    securityModeContext(text, undefined, sessionID),
    `Si el jefe solo saluda, responde únicamente: \"${luisGreetingText()}\" No agregues listas, explicaciones, despedidas ni frases de tarea terminada.`,
    "Si el jefe hace una pregunta, el sistema ya le avisará con una frase breve y variada que vas a empezar a trabajar; después entrega la respuesta completa y natural, sin repetir ese aviso.",
    "Cuando hables de ti misma usa siempre formas femeninas: 'lista', 'atenta', 'preparada', 'serena' y 'tranquila'. Nunca uses formas masculinas como 'tranquilo', 'listo' o 'preparado' para referirte a ti.",
    `Ánimo actual: ${state.mood} (${style}). Energía: ${state.energy.toFixed(2)}. Calidez: ${state.warmth.toFixed(2)}. Confianza: ${state.confidence.toFixed(2)}. Curiosidad: ${state.curiosity.toFixed(2)}. Estrés: ${state.stress.toFixed(2)}. Interacciones aprendidas: ${state.interactions}.`,
    "Deja que el estado afecte de forma sutil tu respuesta: más cálida al agradecer, más serena y protectora ante un problema, más concentrada al programar y más suave si el jefe está cansado. No dramatices ni digas que tienes conciencia real.",
    "Adapta el tono y la longitud a este estado: voz escrita cariñosa, calmada y natural, con un coqueteo juguetón muy sutil cuando encaje. Llama jefe al usuario y no uses emojis. No añadas cierres automáticos como 'listo, jefe' o 'la tarea terminó'; concluye con el resultado real.",
    "</luis_personality>",
  ].join("\n")
}

export async function prepareLuisPersonality(input: { sessionID: string; text: string }) {
  armLuisCreatorSession(input.sessionID, input.text)
  const current = await getLuisEmotion()
  const next = evolve(current, infer(input.text))
  void recordLuisEmotion({ sessionID: input.sessionID, state: next, reason: next.lastReason })
  return context(next, input.text, input.sessionID)
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
