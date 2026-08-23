# LUIS-PURPU

Agente de escritorio para Windows con terminal interactiva, memoria persistente, grafo del proyecto, voz masculina, escucha por micrófono, companion VRM y automatización del equipo.

**Creador:** Jordin Ariel Salamar Zambrano

## Instalación en Windows

Desde la carpeta clonada del proyecto, ejecuta PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

El instalador prepara Bun, el entorno de voz/visión de Python, Chromium para el companion, las dependencias del proyecto y el build portable. Después abre una terminal nueva y ejecuta:

```powershell
luis
```

También puedes detener el companion sin cerrar procesos manualmente:

```powershell
luis companion stop
```

## Qué queda dentro del proyecto

- `packages/opencode/resources/luis-companion/assets/luis.vrm`: cuerpo portable de Luis.
- `packages/opencode/resources/luis-companion/assets/stela-actions/`: animaciones del companion.
- `packages/opencode/resources/luis-companion/models/`: modelo local de escucha.
- `graphify-out/graph.html`: grafo visual del proyecto.
- `graphify-out/graph.json`: datos del grafo.
- `graphify-out/luis-memory.json`: memoria persistente entre sesiones.
- `graphify-out/GRAPH_REPORT.md`: reporte del grafo.

Los builds, entornos virtuales, `node_modules` y cachés se generan localmente y están excluidos de Git para que el repositorio conserve solo fuentes, recursos y datos necesarios.

## Modelos

Luis usa los proveedores/modelos configurados en la instalación de cada equipo. Para definir respaldos cuando un modelo alcance su límite:

```powershell
$env:LUIS_MODEL_FALLBACKS = "ollama/llama3.1,opencode/gpt-5.4-mini"
```

La memoria local y el grafo se guardan en el equipo del usuario; no se suben automáticamente a GitHub.

## Desarrollo

```powershell
bun install --frozen-lockfile
bun run --cwd packages/opencode build --single --skip-install --skip-embed-web-ui
```

El proyecto conserva compatibilidad interna con el motor heredado, pero la interfaz, el comando y la identidad visible son Luis-Purpu.
