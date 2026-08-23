import { expect, test } from "bun:test"
import { sessionEpilogue } from "../../src/util/presentation"
import { APP_DISPLAY_NAME, CLI_COMMAND } from "../../src/branding"

test("formats session continuation summary", () => {
  const epilogue = sessionEpilogue({ title: "A session", sessionID: "ses_123" })
  expect(epilogue).toContain(APP_DISPLAY_NAME)
  expect(epilogue).toContain("A session")
  expect(epilogue).toContain(`${CLI_COMMAND} -s ses_123`)
})
