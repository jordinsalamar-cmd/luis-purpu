export const APP_DISPLAY_NAME = "LUIS-PURPU"
export const CLI_COMMAND = "luis"
export const WAKE_WORD = "luis"
export const CREATOR_NAME = "JORDIN ARIEL SALAMAR ZAMBRANO"

// ANSI 256-color endpoints chosen to move from electric blue into purple.
export const BRAND_COLOR_START = 45
export const BRAND_COLOR_END = 135

export function displayProviderName(providerID: string, providerName: string) {
  if (providerID === "opencode") return APP_DISPLAY_NAME + " Zen"
  if (providerID === "opencode-go") return APP_DISPLAY_NAME + " Go"
  return providerName
}
