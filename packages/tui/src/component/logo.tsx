import { RGBA } from "@opentui/core"
import { For } from "solid-js"
import { LOGO_RASTER, logoPixels } from "../logo-image"

export function Logo() {
  return (
    <box flexDirection="column">
      <For each={LOGO_RASTER.rows}>
        {(row) => (
          <box flexDirection="row">
            <For each={logoPixels(row)}>
              {(pixel) => (
                <text
                  fg={RGBA.fromInts(pixel.foreground[0], pixel.foreground[1], pixel.foreground[2])}
                  bg={RGBA.fromInts(pixel.background[0], pixel.background[1], pixel.background[2])}
                  selectable={false}
                >
                  ▀
                </text>
              )}
            </For>
          </box>
        )}
      </For>
    </box>
  )
}
