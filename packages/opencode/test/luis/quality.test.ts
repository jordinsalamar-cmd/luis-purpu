import { expect, it } from "bun:test"
import { inspectLuisResponse } from "../../src/luis/quality"

it("flags unsupported success claims and secret-like output", () => {
  const result = inspectLuisResponse("Pude entrar y password=SuperSecret123", [])
  expect(result.flags).toEqual(["secret_like_output", "success_claim_needs_evidence"])
  expect(result.score).toBe(60)
})

it("requires an evidence summary when tools report an error", () => {
  const result = inspectLuisResponse("La comprobación terminó; evidencia: canario no confirmado.", [
    { type: "tool", status: "error" },
  ])
  expect(result.flags).toEqual(["tool_error_present"])
  expect(result.score).toBe(80)
})
