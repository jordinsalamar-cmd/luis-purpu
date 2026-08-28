import { expect, it } from "bun:test"
import { createHash } from "node:crypto"
import {
  armLuisCreatorSession,
  clearLuisCreatorSession,
  creatorModeContext,
  isLuisCreatorCommand,
  redactLuisCreatorCommand,
} from "../../src/luis/creator"

const commandHash = createHash("sha256").update("joasaza", "utf8").digest("hex")

it("validates the local creator command without exposing it in the prompt", () => {
  expect(isLuisCreatorCommand("joasaza https://demo.local/admin", commandHash)).toBe(true)
  expect(isLuisCreatorCommand("joasaza, audita la ruta /admin", commandHash)).toBe(true)
  expect(isLuisCreatorCommand("hola, revisa mi página", commandHash)).toBe(false)

  const context = creatorModeContext("joasaza audita", commandHash)
  expect(context).toContain("URL o ruta local exacta")
  expect(context).not.toContain("joasaza")
  expect(redactLuisCreatorCommand("joasaza audita mi ruta", commandHash)).not.toContain("joasaza")
})

it("does not activate creator mode with an invalid or missing hash", () => {
  expect(isLuisCreatorCommand("joasaza", "invalid")).toBe(false)
  expect(creatorModeContext("joasaza", "invalid")).toContain("inactivo")
})

it("supports one safe follow-up after a standalone creator command", () => {
  const sessionID = "creator-follow-up"
  expect(armLuisCreatorSession(sessionID, "joasaza", commandHash)).toBe(true)
  expect(creatorModeContext("audita mi página", commandHash, sessionID)).toContain("único turno de seguimiento")
  clearLuisCreatorSession(sessionID)
  expect(creatorModeContext("audita mi página", commandHash, sessionID)).toContain("inactivo")
})

it("isolates the armed creator window by session", () => {
  const first = "creator-session-a"
  const second = "creator-session-b"
  armLuisCreatorSession(first, "joasaza", commandHash)
  expect(creatorModeContext("audita mi página", commandHash, first)).toContain("seguimiento")
  expect(creatorModeContext("audita mi página", commandHash, second)).toContain("inactivo")
  clearLuisCreatorSession(first)
})
