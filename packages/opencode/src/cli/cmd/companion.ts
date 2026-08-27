import { cmd } from "./cmd"
import { setLuisStatus, setLuisVision, stopLuisCompanion } from "@/luis/companion"
import { UI } from "../ui"

const CompanionStopCommand = cmd({
  command: "stop",
  describe: "close the floating Rem companion",
  async handler() {
    UI.println(stopLuisCompanion() ? "Acompañante de Rem apagado." : "No había un acompañante activo.")
  },
})

const CompanionGestureCommand = cmd({
  command: "gesture <name>",
  describe: "play a Rem companion gesture",
  builder: (yargs) =>
    yargs.positional("name", {
      type: "string",
      choices: [
        "greet",
        "listening",
        "speaking",
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
        "bow",
        "side",
        "nod",
        "shake-head",
        "shy",
        "stretch",
        "wave-both",
        "celebrate",
        "salute",
        "clap",
        "shrug",
        "sit",
        "kneel",
        "walk",
        "run",
        "spin",
      ],
      describe: "gesture to play",
    }),
  async handler(args) {
    UI.println(setLuisStatus(String(args.name)) ? `Gesto de Rem: ${args.name}` : "Rem no está visible.")
  },
})

const CompanionVisionCommand = cmd({
  command: "vision <state>",
  describe: "enable or disable Rem screen observation",
  builder: (yargs) =>
    yargs.positional("state", {
      type: "string",
      choices: ["on", "off"],
      describe: "screen observation state",
    }),
  async handler(args) {
    const enabled = String(args.state) === "on"
    UI.println(setLuisVision(enabled) ? `Visión de pantalla: ${enabled ? "activa" : "apagada"}.` : "Rem no está visible.")
  },
})

export const CompanionCommand = cmd({
  command: "companion",
  describe: "manage the floating Rem companion",
  builder: (yargs) => yargs.command(CompanionStopCommand).command(CompanionGestureCommand).command(CompanionVisionCommand).demandCommand(),
  async handler() {},
})
