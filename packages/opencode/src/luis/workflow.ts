export type LuisTaskMode = "direct" | "engineering" | "security" | "research" | "coordination"

const MODE_PATTERNS: Array<[LuisTaskMode, RegExp]> = [
  ["security", /\b(seguridad|vulnerab|auditor|pentest|ataque|owasp|xss|csrf|ssrf|inyecci[oó]n|ciber)\b/i],
  ["engineering", /\b(c[oó]digo|programa|implementa|bug|error|compila|test|refactor|api|backend|frontend|arregla)\b/i],
  ["research", /\b(investiga|buscar|fuente|actual|compara|documentaci[oó]n|aprende|analiza)\b/i],
  ["coordination", /\b(agente|agentes|paralelo|paralela|divide|subtarea|equipo|coordina)\b/i],
]

export function classifyLuisTask(text: string): LuisTaskMode {
  return MODE_PATTERNS.find(([, pattern]) => pattern.test(text))?.[0] ?? "direct"
}

const MODE_GUIDANCE: Record<LuisTaskMode, string> = {
  direct: "Resuelve directamente; no uses agentes ni herramientas si no aportan valor.",
  engineering: "Inspecciona antes de editar; aplica el cambio mínimo; ejecuta pruebas y reporta archivos y riesgos.",
  security: "Confirma alcance autorizado y canarios; usa bajo impacto; registra evidencia, arreglo reversible y retest.",
  research: "Separa hechos, inferencias y pendientes; contrasta fuentes y fecha cuando el dato pueda cambiar.",
  coordination: "Divide solo unidades independientes; asigna un entregable a cada agente; sintetiza y verifica sus resultados.",
}

export function luisWorkflowContext(text: string) {
  const mode = classifyLuisTask(text)
  return [
    "<luis_execution_policy>",
    `Ruta: ${mode}. ${MODE_GUIDANCE[mode]}`,
    "Orden de trabajo: objetivo y restricciones → acción mínima → verificación proporcional → informe de hechos, cambios, evidencia, límites y siguiente paso.",
    "Autoverificación antes de cerrar: ¿declaré solo resultados observados?, ¿expliqué errores o datos faltantes?, ¿evité secretos?, ¿dejé una prueba o retest reproducible cuando corresponde?",
    "Pide únicamente la información que bloquee la acción; si una suposición es segura, declárala. Nunca presentes una inferencia como resultado observado.",
    "</luis_execution_policy>",
  ].join(" ")
}

export * as LuisWorkflow from "./workflow"
