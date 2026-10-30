# answer-generation Specification

## Purpose
Genera respuestas en lenguaje natural a partir exclusivamente del contexto autorizado recuperado, usando un LLM local para que ningún dato corporativo salga hacia LLMs conversacionales externos.

## Requirements

### Requirement: Generación local con Ollama
Las respuestas SHALL generarse con el modelo `qwen3.5:9b` servido por un Ollama local, por defecto el instalado de forma nativa en la máquina anfitriona y con URL configurable; el sistema MUST NOT enviar preguntas ni contexto a APIs externas de LLMs conversacionales.

#### Scenario: Respuesta generada localmente
- **WHEN** un usuario hace una pregunta con contexto recuperado
- **THEN** la respuesta se obtiene del Ollama local configurado con el modelo `qwen3.5:9b`

### Requirement: Respuesta fundamentada en el contexto
El prompt SHALL instruir al modelo a responder únicamente con la información de los fragmentos proporcionados, en el idioma de la pregunta, y a indicar que no dispone de la información si el contexto no la contiene.

#### Scenario: Contexto insuficiente
- **WHEN** los fragmentos recuperados no contienen la respuesta
- **THEN** la respuesta indica que no dispone de esa información en lugar de inventarla

### Requirement: Sin contexto no se invoca al LLM
Si la recuperación devuelve una lista vacía, el sistema SHALL responder con un mensaje fijo de "no hay información disponible" sin invocar al modelo.

#### Scenario: Recuperación vacía
- **WHEN** la recuperación no devuelve fragmentos para la pregunta y rol
- **THEN** se devuelve el mensaje fijo y no se realiza ninguna llamada a Ollama

### Requirement: Citación de fuentes
Cada respuesta generada SHALL acompañarse de la lista de documentos fuente (título y ruta) de los fragmentos usados como contexto, todos autorizados para el rol.

#### Scenario: Respuesta con fuentes
- **WHEN** se genera una respuesta a partir de fragmentos de dos documentos
- **THEN** la respuesta incluye ambos documentos como fuentes

### Requirement: Indisponibilidad del modelo
Si Ollama no está disponible o el modelo no está descargado, el sistema SHALL devolver un error comprensible al usuario sin exponer detalles internos ni fragmentos de contexto.

#### Scenario: Ollama caído
- **WHEN** el servicio Ollama no responde
- **THEN** el usuario recibe un mensaje de servicio no disponible y el error se registra en el log
