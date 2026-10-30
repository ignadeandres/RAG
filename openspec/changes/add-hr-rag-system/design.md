# Design

## Context

Proyecto greenfield: el repo solo contiene `openspec/`, un `.gitignore` y un `.venv` (Python 3.15) con `ollama`, `httpx`, `pydantic` y `numpy`. La máquina de desarrollo (macOS) tiene Ollama 0.40.11 nativo con `qwen3.5:9b` y `bge-m3` ya descargados. El corpus de `docs/` es sintético, generado para esta prueba. Motivación en `proposal.md` (Why); requisitos en `specs/`. Restricciones que condicionan el diseño: generación conversacional local (Ollama), embeddings locales (`bge-m3` en Ollama; no hay clave de OpenAI), reranking vía Cohere, filtrado por rol en BD en todas las búsquedas, orquestación con `docker-compose` y una arquitectura que permita añadir agentes después sin reescribir el núcleo.

## Goals / Non-Goals

**Goals:**
- Núcleo por capas (dominio → puertos → servicios → adaptadores) donde cada dependencia externa (Ollama, Postgres, Cohere, OpenAI opcional) sea sustituible por inyección.
- Un único punto de verdad para la regla de visibilidad por rol, usado tanto por las SQL (vectorial y BM25) como por los tests.
- Ingesta idempotente: ejecutar la sincronización N veces sin cambios en `docs/` no produce llamadas a la API de embeddings.
- Servicios de aplicación (`IngestionService`, `QueryService`) invocables como "herramientas" por un futuro orquestador de agentes.

**Non-Goals:**
- API REST pública; la UI llama a los servicios en proceso.
- Gestión real de identidades (SSO/LDAP), multi-tenant o histórico de conversaciones persistente.
- Formatos PDF/DOCX en la ingesta.
- Ejecutar Ollama dentro de Docker (sin GPU en Docker Desktop para macOS).

## Decisions

### D1. Estructura del paquete
```
roboost_rag/
  domain/        # modelos pydantic: Document, Chunk, Role, AccessLevel, Answer, Source
  ports/         # Protocols: Embedder, VectorStore, LexicalIndex, Reranker, LLM, DocumentSource
  services/      # IngestionService, SyncScheduler, RetrievalService, QueryService, fusion (RRF)
  adapters/      # ollama_embedder, openai_embedder, paradedb_store, cohere_reranker, ollama_llm, fs_source
  config.py      # pydantic-settings (env vars)
  container.py   # composición: construye servicios con sus adaptadores
  cli.py         # `python -m roboost_rag ingest|sync|eval`
ui/app.py        # Streamlit
db/init.sql      # extensiones vector + pg_search, tablas, índices
docs/            # corpus
tests/
```
*Por qué*: los puertos como `typing.Protocol` dan desacoplamiento sin frameworks de DI; `container.py` es el único sitio que conoce implementaciones concretas, así un agente futuro recibe los mismos servicios. *Alternativa*: LangChain/LlamaIndex — descartadas por acoplar el núcleo a abstracciones ajenas y añadir boilerplate que el BRD pide evitar.

### D2. Base de datos: ParadeDB (Postgres + `pgvector` + `pg_search`)
Imagen `paradedb/paradedb` con versión fijada: es PostgreSQL estándar con `pgvector` (búsqueda vectorial) y `pg_search` (índice BM25 real sobre Tantivy) preinstalados. Tablas, SQL y cliente `psycopg` son los mismos que con Postgres puro.

- `documents(id, path UNIQUE, title, access_level, content_hash, updated_at)`
- `chunks(id, document_id FK ON DELETE CASCADE, position, content, access_level, embedding vector(1024))`
- `access_level` como `SMALLINT` ordinal (`public=0`, `hr_manager=1`, `admin=2`) desnormalizado en `chunks`; el rol tiene el mismo ordinal y el filtro es `access_level <= :role_rank` dentro de cada SQL de búsqueda.
- Índice **HNSW** (`vector_cosine_ops`) sobre `embedding`.
- Índice **BM25** de `pg_search` sobre `(id, content, access_level)` con `key_field = id`; `access_level` se indexa como campo filtrable para que el filtro se aplique dentro del índice BM25.

*Versión y sintaxis confirmadas (tarea 4.1)*: imagen `paradedb/paradedb:0.26.3-pg17`. En 0.26 el método de índice es `USING paradedb` y `key_field` está obsoleto. Tokenizador `pdb.simple('stemmer=spanish', 'ascii_folding=true')` sobre `content` (stemmer español soportado; `ascii_folding` elimina acentos). Consulta con el operador de disyunción `|||`, que tokeniza la entrada con el mismo tokenizador del campo (sin sintaxis de query parser, por lo que la entrada del usuario no necesita escape), y puntuación con `pdb.score(id)`.

*Alternativas*: `pgvector/pgvector` + `tsvector`/`ts_rank` — `ts_rank` no es BM25 (no usa IDF ni normaliza por longitud de documento); BM25 en Python (`rank_bm25`) — el filtro por rol saldría de la BD, incumpliendo `access-control`. *HNSW sobre IVFFlat*: IVFFlat degrada si se crea con la tabla vacía (primer arranque); HNSW no. Se fija `hnsw.ef_search = 100` y `hnsw.iterative_scan = relaxed_order` para garantizar N resultados aunque el filtro sea selectivo.

### D3. Recuperación híbrida con Reciprocal Rank Fusion
1. Dos consultas filtradas por rol: top‑N vectorial (`ORDER BY embedding <=> :q`) y top‑N BM25 (`content @@@ :query` ordenado por `paradedb.score(id)`), N=20.
2. Fusión en Python: `score(d) = Σ w_i / (k + rank_i(d))`, con `k = 60`, `w_vector = w_bm25 = 1.0` por defecto (configurables).
3. Top‑10 fusionado → reranker → top‑K=4.

*Por qué RRF*: combina posiciones, no puntuaciones, así que no hay que normalizar BM25 (sin cota) contra similitud coseno ([0,1]); es robusto tanto para consultas genéricas (domina la vectorial) como específicas (domina BM25) sin ajustar por consulta. *Alternativa*: suma ponderada con normalización min‑max y α — sensible a la distribución de puntuaciones de cada consulta; descartada. Las dos consultas se lanzan en paralelo; la consulta de texto para BM25 se escapa para que la sintaxis de búsqueda del usuario no rompa la query.

### D3b. Embeddings: `bge-m3` en el Ollama del host
`OllamaEmbedder` llama a `/api/embed` de `OLLAMA_HOST` con `bge-m3` (multilingüe, 1024 dimensiones, rendimiento sólido en español), en lotes y con reintentos con backoff ante errores de conexión o 5xx. `EMBEDDING_PROVIDER=openai` selecciona el adaptador de OpenAI, que pide `dimensions=1024` a `text-embedding-3-small` para encajar en el mismo esquema. El esquema fija `vector(1024)`: cambiar a un modelo de otra dimensión exige recrear la tabla y reindexar. *Por qué*: no hay clave de OpenAI disponible; `bge-m3` ya está en el host, es gratuito y mantiene todo el texto dentro de la máquina. *Alternativa*: Cohere Embed — descartado porque las claves de prueba tienen una cuota mensual de llamadas compartida con el reranker.

### D4. Deduplicación y sincronización
- Hash SHA-256 del contenido normalizado (front-matter + cuerpo, espacios colapsados). Incluir el front-matter hace que un cambio de `access_level` cuente como modificación.
- Sincronización = diff entre `{path: hash}` en disco y en `documents`: nuevos → indexar; hash distinto → reindexar; ausentes → borrar. Duplicados por contenido entre rutas: se conserva una ruta (la de nivel más restrictivo; empate → orden alfabético).
- Reemplazo atómico: embeddings calculados **antes** de abrir la transacción; dentro de ella `DELETE chunks` + `INSERT` + `UPDATE documents`. El índice BM25 de `pg_search` es transaccional, por lo que ambas búsquedas ven la misma versión.
- Exclusión mutua con `pg_try_advisory_lock`.

### D5. Chunking
Splitter recursivo propio (~40 líneas): separadores `\n\n` → `\n` → `. ` → espacio; tamaño máximo por defecto ≈ 3 200 caracteres (~800 tokens), overlap = `int(0.1 * max)`. Se antepone el título del documento a cada fragmento (ayuda tanto a la vectorial como a BM25). *Alternativa*: `langchain-text-splitters` — se evita la dependencia por una función trivial y testeable.

### D6. Reranker: Cohere Rerank
Adaptador `CohereReranker` con el SDK `cohere` y modelo multilingüe configurable (por defecto `rerank-v3.5`), `top_n = K`, timeout corto (~5 s). Si no hay `COHERE_API_KEY` o la llamada falla, `RetrievalService` usa el orden RRF (spec: degradación sin reranker) y no aplica umbral. *Por qué no Ollama*: Ollama 0.40.11 no expone endpoint de rerank (`/api/rerank` → 404) y un cross-encoder no puede servirse correctamente vía generación de texto. *Alternativa*: cross-encoder local `bge-reranker-v2-m3` con `sentence-transformers` — descartado por preferencia del usuario y para aligerar la imagen (~1–2 GB menos).

### D7. Generación: Ollama nativo del host
Adaptador `OllamaLLM` usando el paquete `ollama` contra `OLLAMA_HOST` (por defecto `http://host.docker.internal:11434` desde los contenedores; `http://localhost:11434` fuera de Docker), `temperature=0.1`, `think=False`. Prompt de sistema en español: responder solo con el contexto, citar `[n]`, decir "no dispongo de esa información" si falta. Al arrancar, `GET /api/tags` verifica que el modelo existe (spec `local-deployment`). En Linux, el compose añade `extra_hosts: host.docker.internal:host-gateway`.

### D8. UI y autenticación
Streamlit con `st.session_state`. Usuarios en env (`APP_USERS="ana:<bcrypt>:public,luis:<bcrypt>:hr_manager,..."`). El rol se resuelve en el servidor a partir del login y se pasa al `QueryService`; no existe selector de rol en la UI. *Alternativa*: FastAPI + frontend estático — más código para Fase 1; el `QueryService` queda listo para exponerse por API después.

### D9. Contenedores
- `postgres`: `paradedb/paradedb:<versión fijada>`, monta `db/init.sql` en `docker-entrypoint-initdb.d`, healthcheck `pg_isready`, volumen `pgdata`.
- `indexer`: imagen propia, `python -m roboost_rag sync --loop`, monta `./docs:/app/docs:ro`.
- `app`: misma imagen, `streamlit run ui/app.py`, puerto 8501.
- Sin contenedor de Ollama: ambos servicios Python reciben `OLLAMA_HOST`.

### D10. Evaluación
`tests/eval/questions.yaml` con ~20 pares (pregunta, rol, documento esperado o "denegado"), mezclando preguntas genéricas y con términos exactos. `python -m roboost_rag eval` calcula el hit-rate (KPI ≥ 0,90) en tres modos — solo vectorial, solo BM25 e híbrido — para justificar la fusión y calibrar pesos y umbral. Tests unitarios con fakes de los puertos; tests de integración con ParadeDB real (marcados `integration`).

## Risks / Trade-offs

- [Tokenizador en español de `pg_search` no confirmado (stemming/stopwords)] → Verificar en la tarea del índice BM25; si no hay stemmer español, usar tokenizador por defecto con minúsculas y eliminación de acentos y dejar que la búsqueda vectorial cubra las variaciones morfológicas.
- [Cambios de sintaxis entre versiones de `pg_search`] → Versión de imagen fijada en el compose; la SQL BM25 encapsulada en un solo adaptador.
- [Dependencia de Cohere (red, cuota, latencia)] → Degradación a orden RRF; timeout corto; el umbral solo se aplica con reranker activo.
- [Ollama del host no arrancado] → Comprobación al inicio con mensaje claro; la UI muestra "servicio no disponible".
- [`host.docker.internal` no existe por defecto en Linux] → `extra_hosts: host-gateway` en el compose.
- [Autenticación simulada no es segura para producción] → Fuera de alcance (Fase 1 local); el rol se deriva siempre en servidor.
- [El filtro tras el índice HNSW puede devolver menos de N filas] → `iterative_scan` (D2) y test de integración que lo verifica.

## Migration Plan

Greenfield: no hay migración. Despliegue: asegurar Ollama en ejecución con `qwen3.5:9b` y `bge-m3` → `cp .env.example .env` → rellenar `COHERE_API_KEY` y usuarios → `docker compose up -d`. Rollback: `docker compose down -v` borra el índice; el corpus en `docs/` es la fuente de verdad y se reconstruye con la siguiente ingesta.

## Open Questions

- Pesos RRF: se mantienen en 1,0/1,0; la evaluación da el mismo hit-rate con vectorial, BM25 e híbrido sobre este corpus pequeño, así que no hay señal para ajustarlos.
- Umbral del reranker *(resuelto)*: 0,04. Con `rerank-v3.5`, la mejor puntuación fuera de dominio fue 0,017 y la más baja dentro de dominio 0,069 (`eval -v`).
- Tamaño de fragmento definitivo (≈800 tokens es el punto de partida); ajustable por env sin cambiar specs.
