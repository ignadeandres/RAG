# Spec Delta

## Purpose

Permite levantar todo el sistema en local con un único comando de `docker-compose`, de forma reproducible y aislada, usando el Ollama nativo de la máquina anfitriona y sin pasos manuales de inicialización.

## ADDED Requirements

### Requirement: Arranque con un único comando
Ejecutar `docker compose up` SHALL levantar la base de datos (búsqueda vectorial y BM25), el servicio de reindexación y la UI, en el orden de dependencias correcto, conectándolos al Ollama de la máquina anfitriona.

#### Scenario: Arranque desde cero
- **WHEN** en una máquina con Docker, Ollama en ejecución con `qwen3.5:9b` y un `.env` válido se ejecuta `docker compose up -d`
- **THEN** todos los servicios alcanzan estado saludable y la UI es accesible en el puerto configurado

### Requirement: Inicialización automática
En el primer arranque, el sistema SHALL crear el esquema de base de datos, las extensiones y los índices vectorial y BM25, y SHALL ejecutar la ingesta inicial de `docs/`, sin comandos manuales.

#### Scenario: Primer arranque
- **WHEN** se arranca con volúmenes vacíos
- **THEN** el esquema y los índices existen y la ingesta inicial de `docs/` se completa

### Requirement: Verificación del modelo en el host
Al arrancar, la aplicación SHALL comprobar que el Ollama configurado es accesible y tiene disponibles los modelos configurados (generación y embeddings), y SHALL informar con un mensaje claro si no lo está, sin intentar descargarlo.

#### Scenario: Ollama del host apagado
- **WHEN** se arranca la app y Ollama no está en ejecución en el host
- **THEN** la app registra y muestra un aviso indicando que Ollama no es accesible en la URL configurada

#### Scenario: Modelo no descargado
- **WHEN** Ollama es accesible pero no tiene `qwen3.5:9b`
- **THEN** el aviso indica el modelo que falta y el comando `ollama pull` para obtenerlo

### Requirement: Persistencia entre reinicios
Los datos indexados SHALL persistir en un volumen, de modo que un reinicio no requiera reindexar.

#### Scenario: Reinicio
- **WHEN** se ejecuta `docker compose restart`
- **THEN** el índice previo sigue disponible y los documentos sin cambios no se re-vectorizan

### Requirement: Configuración por variables de entorno
Toda la configuración (claves, URLs, modelos, intervalo de reindexación, tamaños de fragmento, pesos de fusión, credenciales de usuarios) SHALL leerse de variables de entorno, y el repositorio SHALL incluir un `.env.example` sin secretos reales.

#### Scenario: Proveedor de embeddings externo sin clave
- **WHEN** se configura OpenAI como proveedor de embeddings y no se define `OPENAI_API_KEY`
- **THEN** los servicios fallan al inicio con un mensaje claro indicando la variable ausente

#### Scenario: Falta la clave de Cohere
- **WHEN** se arranca sin `COHERE_API_KEY`
- **THEN** la app arranca, registra un aviso de que el reranking está desactivado y opera con el orden de la fusión

### Requirement: Montaje de docs en caliente
La carpeta `docs/` del host SHALL montarse en el servicio de reindexación, de modo que los cambios en el host se reflejen sin reconstruir imágenes ni reiniciar contenedores.

#### Scenario: Fichero añadido en el host
- **WHEN** se copia un documento a `docs/` en el host
- **THEN** el servicio de reindexación lo ve en su siguiente pasada sin reinicio
