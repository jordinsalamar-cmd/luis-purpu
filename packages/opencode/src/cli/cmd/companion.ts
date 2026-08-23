import { cmd } from "./cmd"
import { stopLuisCompanion } from "@/luis/companion"
import { UI } from "../ui"

const CompanionStopCommand = cmd({
  command: "stop",
  describe: "close the floating Luis companion",
  async handler() {
    UI.println(stopLuisCompanion() ? "Acompañante de Luis apagado." : "No había un acompañante activo.")
  },
})

export const CompanionCommand = cmd({
  command: "companion",
  describe: "manage the floating Luis companion",
  builder: (yargs) => yargs.command(CompanionStopCommand).demandCommand(),
  async handler() {},
})
