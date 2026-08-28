import { expect, it } from "bun:test"
import { classifyLuisTask, luisWorkflowContext } from "../../src/luis/workflow"

it("routes engineering work to inspect, test, and report", () => {
  expect(classifyLuisTask("arregla el bug del backend y ejecuta los tests")).toBe("engineering")
  const context = luisWorkflowContext("arregla el bug del backend")
  expect(context).toContain("Ruta: engineering")
  expect(context).toContain("verificación proporcional")
  expect(context).toContain("Autoverificación antes de cerrar")
})

it("keeps delegation limited to independent work", () => {
  expect(classifyLuisTask("divide esta investigación entre agentes en paralelo")).toBe("coordination")
  expect(luisWorkflowContext("coordina agentes para revisar módulos")).toContain("unidades independientes")
})

it("requires authorization and canaries for security work", () => {
  const context = luisWorkflowContext("audita la seguridad de mi API")
  expect(context).toContain("canarios")
  expect(context).toContain("retest")
})
