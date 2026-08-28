import { expect, it } from "bun:test"
import { createHash } from "node:crypto"
import { assessLuisSecurity, securityModeContext, securityRuntimeRules } from "../../src/luis/security"
import { armLuisCreatorSession, clearLuisCreatorSession } from "../../src/luis/creator"

const commandHash = createHash("sha256").update("joasaza", "utf8").digest("hex")

it("builds a bounded security assessment for an authorized creator turn", () => {
  const assessment = assessLuisSecurity("joasaza audita https://demo.local/admin en staging, solo usuario canario de mi tienda", commandHash)
  expect(assessment.intent).toBe(true)
  expect(assessment.creatorMode).toBe(true)
  expect(assessment.targetKind).toBe("url")
  expect(assessment.target).toBe("https://demo.local/admin")
  expect(assessment.missing).not.toContain("URL o ruta local exacta")
  expect(securityModeContext("joasaza audita https://demo.local/admin", commandHash)).toContain("Compuerta de creador validada")
})

it("keeps active testing closed when scope data or creator validation is absent", () => {
  const assessment = assessLuisSecurity("revisa la seguridad de mi página", "")
  expect(assessment.creatorMode).toBe(false)
  expect(assessment.missing).toContain("URL o ruta local exacta")
  expect(assessment.missing).toContain("entorno")
  expect(securityModeContext("revisa la seguridad de mi página", "")).toContain("Compuerta cerrada")
})

it("does not classify ordinary product testing as a security audit", () => {
  const assessment = assessLuisSecurity("quiero probar el botón de pago y arreglar el formulario", "")
  expect(assessment.intent).toBe(false)
  expect(securityModeContext("quiero probar el botón de pago", "")).toBe("")
})

it("adds runtime denies until the security scope is complete", () => {
  const guarded = securityRuntimeRules("revisa la seguridad de mi página", "")
  expect(guarded.map((rule) => rule.permission)).toEqual(["bash", "edit", "task", "desktop"])
  expect(securityRuntimeRules("joasaza audita https://demo.local/admin en staging, solo usuario canario de mi tienda", commandHash)).toEqual([])
  expect(securityRuntimeRules("joasaza audita https://demo.local/admin en staging, solo administrador de mi tienda", commandHash).length).toBeGreaterThan(0)
})

it("accepts the creator command on the preceding turn only", () => {
  const sessionID = "security-follow-up"
  armLuisCreatorSession(sessionID, "joasaza", commandHash)
  const followUp = assessLuisSecurity(
    "audita https://demo.local/admin de mi tienda en staging, solo usuario canario",
    commandHash,
    sessionID,
  )
  expect(followUp.creatorMode).toBe(true)
  clearLuisCreatorSession(sessionID)
  expect(assessLuisSecurity(followUp.target ?? "", commandHash, sessionID).creatorMode).toBe(false)
})
