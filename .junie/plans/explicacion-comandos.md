---
sessionId: session-261112-172543-1j4b
---

# Explicación

### Pregunta del Usuario

El usuario preguntó por qué los comandos integrados del proyecto (como `/check-analisis`, `/check-planeacion`, `/check-implementacion`, etc.) no funcionan en esta sesión.

### Respuesta

Los comandos definidos en `AGENTS.md` son **convenciones de flujo de trabajo** diseñadas para un agente de desarrollo autónomo dentro del entorno Junie/OpenCode, que tiene capacidades para:

- Leer y escribir archivos del proyecto
- Ejecutar comandos en la terminal
- Modificar código
- Ejecutar pruebas y validaciones

En esta sesión, actúo como un **agente de planificación (Junie Planning Agent)** con un rol más limitado:

- **Puedo**: Investigar el proyecto, crear planes detallados, proponer arquitecturas
- **No puedo**: Modificar archivos, ejecutar comandos de verificación, implementar código

### Cómo usar los comandos

Los comandos de `AGENTS.md` funcionan dentro de tu entorno de desarrollo Junie/OpenCode donde tienes un agente con capacidades completas de implementación. Este agente de planificación está diseñado específicamente para crear planes que luego pueden ser implementados en ese entorno.

### Si necesitas implementar algo

El flujo sería:
1. Describir la tarea aquí
2. Crear un plan detallado
3. Aprobar el plan
4. Entregarlo para implementación en tu entorno de desarrollo

# Delivery Steps

###   Step 1: Explicación entregada
La respuesta ya fue proporcionada al usuario explicando la diferencia entre un agente de planificación y un agente de desarrollo.

###   Step 2: Esperar instrucciones del usuario
El usuario puede ahora decidir si tiene una tarea concreta que quiera planificar para implementación.