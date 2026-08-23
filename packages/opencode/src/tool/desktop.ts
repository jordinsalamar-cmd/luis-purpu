import { execFile } from "node:child_process"
import { existsSync } from "node:fs"
import { readFile, unlink } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { promisify } from "node:util"
import { Effect, Schema } from "effect"
import * as Tool from "./tool"

const execFileAsync = promisify(execFile)

const Action = Schema.Union([
  Schema.Literal("app_list"),
  Schema.Literal("open_app"),
  Schema.Literal("screenshot"),
  Schema.Literal("window_list"),
  Schema.Literal("focus"),
  Schema.Literal("open"),
  Schema.Literal("move"),
  Schema.Literal("click"),
  Schema.Literal("double_click"),
  Schema.Literal("type"),
  Schema.Literal("paste"),
  Schema.Literal("key"),
  Schema.Literal("scroll"),
])
const Button = Schema.Union([Schema.Literal("left"), Schema.Literal("right"), Schema.Literal("middle")])

export const Parameters = Schema.Struct({
  action: Action,
  x: Schema.optional(Schema.Number),
  y: Schema.optional(Schema.Number),
  button: Schema.optional(Button),
  text: Schema.optional(Schema.String),
  key: Schema.optional(Schema.String),
  modifiers: Schema.optional(Schema.Array(Schema.String)),
  amount: Schema.optional(Schema.Number),
  target: Schema.optional(Schema.String),
  wait: Schema.optional(Schema.Number),
})

type ParametersType = Schema.Schema.Type<typeof Parameters>

function scriptCandidates() {
  return [
    process.env.LUIS_DESKTOP_SCRIPT,
    path.join(path.dirname(process.execPath), "luis-companion", "luis_desktop.py"),
    path.join(path.dirname(path.dirname(process.execPath)), "luis-companion", "luis_desktop.py"),
    path.resolve(process.cwd(), "packages/opencode/resources/luis-companion/luis_desktop.py"),
    path.join(os.homedir(), "Desktop", "stela", "luis_desktop.py"),
  ].filter((value): value is string => Boolean(value))
}

function scriptPath() {
  const found = scriptCandidates().find((value) => {
    return existsSync(value)
  })
  if (!found) throw new Error("No encontré el módulo de control de escritorio de Luis.")
  return found
}

function needsConfirmation(params: ParametersType) {
  if (!["type", "paste"].includes(params.action)) return false
  return /(contraseña|password|token|api[\s_-]*key|otp|c[oó]digo de seguridad|cvv|tarjeta|pasaporte|documento de identidad)/i.test(
    params.text ?? "",
  )
}

function validate(params: ParametersType) {
  if (["move", "click", "double_click"].includes(params.action) && (params.x === undefined || params.y === undefined)) {
    throw new Error(`${params.action} requiere x e y.`)
  }
  if (["type", "paste"].includes(params.action) && params.text === undefined) throw new Error(`${params.action} requiere text.`)
  if (params.action === "key" && !params.key) throw new Error("key requiere key.")
  if (["open", "focus"].includes(params.action) && !params.target) throw new Error(`${params.action} requiere target.`)
  if (["open_app"].includes(params.action) && !params.target) throw new Error(`${params.action} requiere target.`)
}

export const DesktopTool = Tool.define(
  "desktop",
  Effect.succeed({
    description: [
      "Controla el escritorio real de Windows de Luis.",
      "app_list descubre aplicaciones instaladas en la PC actual desde Inicio, accesos directos, PATH y carpetas de programas; sus rutas se detectan de forma local en cada equipo.",
      "Para abrir por nombre humano usa open_app, por ejemplo target=WhatsApp; no supongas rutas de otra computadora. Si hay varias coincidencias, consulta app_list y elige la correcta.",
      "open_app espera a que la ventana aparezca y la deja independiente de Luis; no encadenes focus inmediatamente salvo que sea necesario para una interacción posterior.",
      "Usa screenshot solo si necesitas coordenadas o inspección visual; si ya conoces la ventana, usa focus, paste o key y verifica con window_list.",
      "Puede abrir aplicaciones o URLs, enfocar ventanas, mover y pulsar el mouse, escribir o pegar texto, usar teclas, hacer scroll y listar ventanas.",
      "Para código o texto largo usa paste: pega todo de una vez en la ventana activa y evita escribir carácter por carácter.",
      "Para reproducir un video no te limites a abrir una búsqueda: observa, selecciona el resultado correcto, pulsa reproducir y verifica el título/estado del reproductor.",
      "Si aparece un anuncio, observa antes de actuar y busca controles como Saltar anuncio, Omitir, cerrar o silenciar; no pulses coordenadas adivinadas.",
      "Después de cada acción, usa la salida o una nueva observación para confirmar qué cambió antes de continuar.",
      "No escribas contraseñas, tokens ni datos sensibles sin confirmación explícita del jefe.",
    ].join("\n"),
    parameters: Parameters,
    execute: (params: ParametersType, ctx: Tool.Context) =>
      Effect.gen(function* () {
        validate(params)
        if (needsConfirmation(params)) {
          yield* ctx.ask({
            permission: "desktop_sensitive_input",
            patterns: ["sensitive-input"],
            always: [],
            metadata: { action: params.action },
          })
        }

        const request = JSON.stringify(params)
        const python = process.env.LUIS_DESKTOP_PYTHON || process.env.LUIS_MASCOT_PYTHON || "python"
        const result = yield* Effect.tryPromise({
          try: () => execFileAsync(python, [scriptPath(), "--request", request], { windowsHide: true, maxBuffer: 2_000_000 }),
          catch: (error) => new Error(`No se pudo controlar el escritorio: ${String(error)}`),
        })

        let payload: { ok?: boolean; action?: string; error?: string; screenshot?: string; windows?: unknown[]; window?: unknown }
        try {
          payload = JSON.parse(result.stdout.trim())
        } catch {
          throw new Error(result.stderr || result.stdout || "El control de escritorio no devolvió un resultado válido.")
        }
        if (!payload.ok) throw new Error(payload.error || "La acción de escritorio falló.")

        const attachments: NonNullable<Tool.ExecuteResult["attachments"]> = []
        if (payload.screenshot) {
          const bytes = yield* Effect.tryPromise({
            try: () => readFile(payload.screenshot!),
            catch: (error) => new Error(`No se pudo leer la captura de pantalla: ${String(error)}`),
          })
          attachments.push({ type: "file", mime: "image/png", url: `data:image/png;base64,${bytes.toString("base64")}` })
          yield* Effect.promise(() => unlink(payload.screenshot!).catch(() => undefined))
        }

        return {
          title: `desktop ${params.action}`,
          output: JSON.stringify({ action: payload.action, windows: payload.windows, window: payload.window }, null, 2),
          metadata: { action: params.action, screenshot: Boolean(payload.screenshot) },
          attachments,
        }
      }).pipe(Effect.orDie),
  }),
)
