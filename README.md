# LUIS-PURPU

Agente de escritorio para Windows con terminal interactiva, memoria persistente, grafo del proyecto, voz masculina, escucha por micrófono, companion VRM y automatización del equipo.

**Creador:** Jordin Ariel Salamar Zambrano

## Instalación en Windows

En una PC nueva con Windows 10/11, abre PowerShell y ejecuta:

```powershell
git clone https://github.com/jordinsalamar-cmd/luis-purpu.git
cd luis-purpu
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Si la PC todavía no tiene Git, puede descargar y preparar todo con un solo bloque de PowerShell:

```powershell
$z="$env:TEMP\luis-purpu.zip"; irm https://github.com/jordinsalamar-cmd/luis-purpu/archive/refs/heads/master.zip -OutFile $z; Expand-Archive $z -DestinationPath "$env:USERPROFILE\luis-purpu" -Force; cd "$env:USERPROFILE\luis-purpu\luis-purpu-master"; powershell -ExecutionPolicy Bypass -File .\install.ps1
```

El instalador prepara automáticamente Python 3.12, Bun, FFmpeg para la voz online, el entorno de voz/visión de Python, Chromium para el companion, las dependencias del proyecto y el build portable. Usa `winget`, por lo que la primera instalación necesita internet. Después abre una terminal nueva y ejecuta:

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

## Voz y modelos

El reconocimiento del micrófono usa el modelo Vosk incluido y puede funcionar sin internet. La voz intenta usar `edge-tts` con una voz masculina online y, si no hay conexión, usa la voz local de Windows.

La respuesta inteligente usa el proveedor/modelo configurado en cada equipo. El repositorio no incluye un modelo grande de lenguaje: para usarlo sin internet hay que instalar y configurar Ollama, LM Studio u otro proveedor local. La instalación no descarga varios gigabytes de modelo automáticamente.

Para consultar los proveedores configurados:

```powershell
luis auth list
```

La memoria local y el grafo se guardan en el equipo del usuario; no se suben automáticamente a GitHub.

## Desarrollo

```powershell
bun install --frozen-lockfile
bun run --cwd packages/opencode build --single --skip-install --skip-embed-web-ui
```

El proyecto conserva compatibilidad interna con el motor heredado, pero la interfaz, el comando y la identidad visible son Luis-Purpu.
