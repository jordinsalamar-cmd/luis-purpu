import { APP_DISPLAY_NAME, CLI_COMMAND, CREATOR_NAME } from "../branding"
import { logoAnsi } from "../logo-image"

const reset = "\x1b[0m"
const bold = "\x1b[1m"
const dim = "\x1b[90m"

function wordmark(pad = "") {
  return logoAnsi(pad).split("\n")
}

export function sessionEpilogue(input: { title: string; sessionID?: string }) {
  const weak = (text: string) => `${dim}${text.padEnd(10, " ")}${reset}`
  return [
    ...wordmark("  "),
    `  ${bold}${APP_DISPLAY_NAME}${reset}`,
    `  ${dim}Creador: ${CREATOR_NAME}${reset}`,
    "",
    `  ${weak("Session")}${bold}${input.title}${reset}`,
    `  ${weak("Continue")}${bold}${CLI_COMMAND} -s ${input.sessionID}${reset}`,
    "",
  ].join("\n")
}
