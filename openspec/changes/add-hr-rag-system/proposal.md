# Proposal

## Why

El equipo de RRHH de ROBOOST dedica un tiempo significativo a responder consultas repetitivas sobre normativas, beneficios, políticas salariales y procedimientos, y parte de esa documentación es altamente sensible (salarios, expedientes, políticas confidenciales). Se necesita un sistema RAG local, autónomo y con control de acceso por rol aplicado en la base de datos, que sirva además como base desacoplada para futuras capacidades multi-agente (BRD v1.0.0, Fase 1).

## What Changes

- Nuevo corpus sintético de documentación de RRHH en `docs/`, con metadatos de sensibilidad (`public`, `hr_manager`, `admin`) y casos de sensibilidad cruzada.
- Nuevo pipeline de ingesta en Python: deduplicación ligera por hash de contenido, *chunking* con solapamiento del 10 %, embeddings locales con `bge-m3` servido por el Ollama del host (1024 dimensiones; OpenAI `text-embedding-3-small` queda como proveedor alternativo configurable) y persistencia en PostgreSQL (ParadeDB: `pgvector` + `pg_search`) con índice vectorial HNSW e índice léxico BM25.
- Nuevo servicio en background que reindexa `docs/` cada 5 minutos de forma incremental (altas, modificaciones y bajas) sin reinicios ni pasos manuales.
- Nueva recuperación **híbrida**: búsqueda léxica BM25 y búsqueda vectorial, ambas con filtrado por rol **dentro de la consulta SQL**, fusionadas con Reciprocal Rank Fusion en un top‑10 y reordenadas con el reranker de Cohere.
- Nueva generación de respuestas con el Ollama nativo de la máquina anfitriona (`qwen3.5:9b`), con citas de las fuentes y respuesta de "no hay información disponible" cuando no se recupera contexto autorizado.
- Nueva UI minimalista (Streamlit) con inicio de sesión simulado por rol y conversación.
- Nueva orquestación local con `docker-compose` (ParadeDB, worker de indexación, app) conectada al Ollama del host.
- Arquitectura Python por capas con interfaces (puertos) para embeddings, almacén vectorial, reranker y LLM, preparada para inyectar agentes en fases posteriores.

## Capabilities

### New Capabilities
- `hr-corpus`: formato y metadatos de los documentos fuente en `docs/` (nivel de acceso, título, tipo) y el conjunto sintético inicial.
- `access-control`: roles (`public`, `hr_manager`, `admin`), su jerarquía de visibilidad, autenticación simulada y la garantía de que el filtrado se aplica en la base de datos.
- `document-ingestion`: lectura, deduplicación, *chunking* con 10 % de overlap, generación de embeddings y persistencia vectorial con metadatos.
- `scheduled-reindex`: detección periódica (cada 5 min) de documentos nuevos, modificados y eliminados y sincronización incremental del índice.
- `role-based-retrieval`: búsqueda híbrida BM25 + vectorial filtrada por rol, fusión top‑10 y reranking de candidatos.
- `answer-generation`: construcción del prompt con contexto autorizado, generación local con Ollama del host y citación de fuentes.
- `chat-ui`: interfaz conversacional con selección/autenticación de rol.
- `local-deployment`: orquestación con `docker-compose`, configuración por variables de entorno y arranque reproducible.

### Modified Capabilities
<!-- Ninguna: proyecto greenfield sin specs existentes. -->

## Impact

- **Código nuevo**: paquete Python `roboost_rag/` (dominio, puertos, adaptadores, servicios), `docs/`, `docker-compose.yml`, `Dockerfile`, migraciones SQL, tests.
- **Dependencias**: `cohere`, `openai` (solo si se elige como proveedor de embeddings), `psycopg[binary]` + `pgvector`, `ollama` (ya presente en `.venv`), `pydantic`/`pydantic-settings`, `streamlit`, `pytest`.
- **Sistemas externos**: API de Cohere para reranking (`COHERE_API_KEY`); embeddings y generación son locales (Ollama). Ninguna llamada a LLMs conversacionales externos. El corpus es sintético, por lo que el envío de fragmentos a Cohere no expone datos reales.
- **Infraestructura**: contenedores `postgres` (imagen ParadeDB con `pgvector` y `pg_search`), `indexer`, `app`; volumen persistente para datos. Ollama corre de forma nativa en el host (macOS, con GPU) y ya tiene `qwen3.5:9b` y `bge-m3` descargados.
- **Fuera de alcance**: despliegue en nube pública, integraciones con pasarelas de pago o CRMs, autenticación real (SSO/LDAP).
