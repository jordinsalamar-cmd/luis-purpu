import { cmd } from "./cmd"
import { setLuisStatus, setLuisVision, stopLuisCompanion } from "@/luis/companion"
import { UI } from "../ui"

const CompanionStopCommand = cmd({
  command: "stop",
  describe: "close the floating Luis companion",
  async handler() {
    UI.println(stopLuisCompanion() ? "Acompañante de Luis apagado." : "No había un acompañante activo.")
  },
})

const CompanionGestureCommand = cmd({
  command: "gesture <name>",
  describe: "play a Luis companion gesture",
  builder: (yargs) =>
    yargs.positional("name", {
      type: "string",
      choices: [
        "greet",
        "listening",
        "thinking",
        "head-touch",
        "crossed",
        "reading",
        "coding",
        "typing",
        "pointing",
        "success",
        "error",
        "sleeping",
        "dancing",
      ],
      describe: "gesture to play",
    }),
  async handler(args) {
    UI.println(setLuisStatus(String(args.name)) ? `Gesto de Luis: ${args.name}` : "Luis no está visible.")
  },
})

const CompanionVisionCommand = cmd({
  command: "vision <state>",
  describe: "enable or disable Luis screen observation",
  builder: (yargs) =>
    yargs.positional("state", {
      type: "string",
      choices: ["on", "off"],
      describe: "screen observation state",
    }),
  async handler(args) {
    const enabled = String(args.state) === "on"
    UI.println(setLuisVision(enabled) ? `Visión de pantalla: ${enabled ? "activa" : "apagada"}.` : "Luis no está visible.")
  },
})

export const CompanionCommand = cmd({
  command: "companion",
  describe: "manage the floating Luis companion",
  builder: (yargs) => yargs.command(CompanionStopCommand).command(CompanionGestureCommand).command(CompanionVisionCommand).demandCommand(),
  async handler() {},
})
