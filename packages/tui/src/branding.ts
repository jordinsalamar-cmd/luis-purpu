export const APP_DISPLAY_NAME = "RE:ZERO"
export const CLI_COMMAND = "rem"
export const WAKE_WORD = "rem"
export const CREATOR_NAME = "JORDIN ARIEL SALAMAR ZAMBRANO"

// ANSI 256-color endpoints chosen to move from Re:Zero purple into electric blue.
export const BRAND_COLOR_START = 99
export const BRAND_COLOR_END = 33

export function displayProviderName(providerID: string, providerName: string) {
  if (providerID === "opencode") return APP_DISPLAY_NAME + " Zen"
  if (providerID === "opencode-go") return APP_DISPLAY_NAME + " Go"
  return providerName
}
