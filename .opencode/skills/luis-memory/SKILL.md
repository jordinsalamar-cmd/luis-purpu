---
name: luis-memory
description: Usa y mantiene la memoria persistente de Luis y su grafo de conocimiento.
---

# Memoria de Luis

La memoria persistente vive en `graphify-out/luis-memory.json` y su visor en `graphify-out/luis-memory.html`.

- Guarda preferencias, identidad, capacidades, aprendizajes y hechos útiles, no secretos.
- Redacta API keys, tokens, contraseñas y credenciales antes de guardar.
- Recupera recuerdos relevantes para la petición actual y dales menos prioridad que la instrucción actual.
- Deja que la compactación automática reduzca el contexto de sesiones largas. No borres el grafo completo para resolver una conversación grande.
- Si el grafo crece demasiado, conserva identidad, preferencias, capacidades, aprendizajes y recuerdos recientes; elimina solo conversaciones antiguas de baja importancia.
