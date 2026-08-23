import { access } from "node:fs/promises"
import { dirname, resolve } from "node:path"
import open from "open"
import { cmd } from "../cmd/cmd"
import { UI } from "../ui"

const defaultGraphFile = "graphify-out/graph.html"

async function locateDefaultGraph() {
  const candidates = [
    process.env.LUIS_GRAPH_FILE,
    resolve(dirname(process.execPath), "..", "..", "..", "..", "..", defaultGraphFile),
    resolve(process.cwd(), defaultGraphFile),
  ].filter((value): value is string => Boolean(value))
  for (const candidate of candidates) {
    try {
      await access(candidate)
      return candidate
    } catch {
      // Try the next known project location.
    }
  }
  return candidates[0] ?? resolve(process.cwd(), defaultGraphFile)
}

export const BrainCommand = cmd({
  command: "brain",
  describe: "open the project's Graphify code graph",
  builder: (yargs) =>
    yargs.option("file", {
      type: "string",
      default: defaultGraphFile,
      describe: "HTML graph file to open",
    }),
  handler: async (args) => {
    const file = args.file === defaultGraphFile ? await locateDefaultGraph() : resolve(process.cwd(), args.file)
    try {
      await access(file)
    } catch {
      UI.error(`No existe el grafo de código todavía: ${file}`)
      UI.println("Ejecuta graphify sobre la carpeta del proyecto para crear graphify-out/graph.html.")
      return
    }
    await open(file)
    UI.println(UI.Style.TEXT_SUCCESS + "Cerebro de Luis abierto: " + UI.Style.TEXT_NORMAL + file)
  },
})
