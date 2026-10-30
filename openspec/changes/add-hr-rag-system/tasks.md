# Tasks

## 1. Scaffolding y configuración

- [x] 1.1 Crear `pyproject.toml` con dependencias (openai, cohere, psycopg[binary], pgvector, ollama, pydantic, pydantic-settings, python-frontmatter, streamlit, bcrypt, pytest) y verificar que `pip install -e .[dev]` termina sin errores
- [x] 1.2 Crear la estructura `roboost_rag/{domain,ports,services,adapters}`, `ui/`, `db/`, `tests/` (D1) y verificar que `python -c "import roboost_rag"` funciona
- [x] 1.3 Implementar `config.py` con pydantic-settings y `.env.example` sin secretos; test que verifica error claro cuando falta `OPENAI_API_KEY`
- [x] 1.4 Añadir `.env` a `.gitignore` y verificar con `git check-ignore .env`

## 2. Dominio, roles y puertos

- [x] 2.1 Implementar modelos de dominio (`Document`, `Chunk`, `AccessLevel`, `Role`, `Answer`, `Source`) con ordinales de acceso y función única `visible_levels(role)`; tests unitarios de la jerarquía public ⊂ hr_manager ⊂ admin
- [x] 2.2 Definir los `Protocol` `Embedder`, `VectorStore`, `LexicalIndex`, `Reranker`, `LLM`, `DocumentSource` y fakes en memoria en `tests/fakes.py`; verificar que los fakes satisfacen los protocolos con un test de tipado/instanciación

## 3. Corpus sintético

- [x] 3.1 Escribir ≥ 9 documentos de RRHH en `docs/` (≥ 3 por nivel) con front-matter `title`/`access_level`, cubriendo normativa, beneficios, política salarial y procedimientos, incluidos casos de sensibilidad cruzada (política salarial pública vs. bandas salariales `hr_manager`; expedientes/sanciones `admin`); verificar con un test que cuenta documentos por nivel
- [x] 3.2 Implementar el adaptador `fs_source` (lectura recursiva de `.md`/`.txt`, parseo de front-matter, nivel `admin` por defecto con aviso, ignorar otras extensiones); tests unitarios de cada caso de la spec `hr-corpus`

## 4. Base de datos

- [x] 4.1 Elegir y fijar la versión de la imagen `paradedb/paradedb`, confirmar en su documentación la sintaxis del índice BM25 y el soporte de tokenizador español, y registrar la decisión (tokenizador elegido) en `design.md`
- [x] 4.2 Escribir `db/init.sql` con extensiones `vector` y `pg_search`, tablas `documents`/`chunks`, índice HNSW `vector_cosine_ops` e índice BM25 sobre `(id, content, access_level)` (D2); verificar aplicándolo en el contenedor ParadeDB y comprobando que ambos índices existen
- [x] 4.3 Implementar el adaptador `paradedb_store` (upsert atómico por documento, borrado, listado `{path: hash}`, búsqueda vectorial con `access_level <= :rank` e `iterative_scan`); tests de integración que verifican que un rol `public` nunca recibe filas restringidas y que se obtienen N resultados con filtro selectivo
- [x] 4.4 Implementar la búsqueda BM25 en el mismo adaptador (`|||` + `pdb.score`, filtro por rol dentro de la consulta, entrada del usuario tokenizada sin sintaxis de query parser); tests de integración: término exacto encontrado, término de un documento `admin` invisible para `public`, entrada con caracteres especiales sin error

## 5. Ingesta

- [x] 5.1 Implementar el chunker recursivo con overlap del 10 % y título antepuesto (D5); tests unitarios de documento largo (overlap ≈ 0,1·N, ningún fragmento > N) y documento corto (un fragmento)
- [x] 5.2 Implementar el adaptador `openai_embedder` (`text-embedding-3-small`, lotes, reintentos con backoff exponencial ante 429/5xx); tests con cliente HTTP simulado que verifican reintentos y fallo tras agotarlos
- [x] 5.3 Implementar `IngestionService` (hash SHA-256 normalizado, diff alta/modificación/baja, deduplicación entre rutas conservando el nivel más restrictivo, embeddings antes de la transacción); tests con fakes que verifican cero llamadas al embedder en una segunda pasada sin cambios y conservación de la versión previa si el embedder falla
- [x] 5.4 Implementar el comando `python -m roboost_rag ingest` con resumen (añadidos/actualizados/eliminados/omitidos/fallidos) y verificar que termina con código 0 contra Postgres local

- [x] 5.5 Implementar el adaptador `ollama_embedder` (`bge-m3`, 1024 dimensiones, lotes, reintentos con backoff), selección de proveedor con `EMBEDDING_PROVIDER` (`ollama` por defecto, `openai` con `dimensions=1024`), esquema a `vector(1024)` y comprobación de `bge-m3` al arrancar (D3b); tests con cliente simulado de reintentos y del error de configuración si se elige OpenAI sin clave; prueba real contra el Ollama del Mac

## 6. Reindexación programada

- [x] 6.1 Implementar `SyncScheduler` (`sync --loop`, pasada al arrancar y cada `REINDEX_INTERVAL_SECONDS`=300, `pg_try_advisory_lock`, errores por documento no abortan la pasada); tests que verifican omisión de pasada concurrente y continuidad tras un documento corrupto
- [x] 6.2 Test de integración: alta, cambio de `access_level` public→admin y baja de un documento se reflejan en la recuperación tras una pasada

## 7. Recuperación híbrida y reranking

- [x] 7.1 Implementar la fusión RRF (`k=60`, pesos configurables, deduplicación, corte a 10) (D3); tests unitarios: fragmento en ambas listas queda primero, una lista vacía, ambas vacías
- [x] 7.2 Implementar el adaptador `cohere_reranker` (modelo configurable, `top_n=K`, timeout) (D6); tests con cliente simulado que verifican orden descendente, corte a top‑K y que un error se propaga como excepción tipada
- [x] 7.3 Implementar `RetrievalService` (vectorial y BM25 en paralelo → RRF → rerank → umbral → top‑K; degradación a orden RRF sin umbral si el reranker falta o falla; rechaza consultas sin rol); tests con fakes para lista vacía, umbral, reranker caído y rol ausente

## 8. Generación de respuestas

- [x] 8.1 Implementar el adaptador `ollama_llm` (`OLLAMA_HOST` configurable, `qwen3.5:9b`, `temperature=0.1`, `think=False`), la comprobación de disponibilidad del modelo vía `/api/tags` y el prompt de sistema en español con citas `[n]` (D7); tests con cliente simulado que verifican el modelo usado, el aviso con `ollama pull` si falta el modelo y el error genérico con Ollama caído; prueba manual contra el Ollama nativo del Mac
- [x] 8.2 Implementar `QueryService` (retrieval → si vacío, mensaje fijo sin llamar al LLM → generación → fuentes autorizadas); tests con fakes de recuperación vacía (cero llamadas al LLM) y respuesta con dos fuentes

## 9. Interfaz de usuario

- [x] 9.1 Implementar autenticación local con usuarios en `APP_USERS` y contraseñas bcrypt, rol derivado en servidor; tests de credenciales válidas e inválidas
- [x] 9.2 Implementar `ui/app.py` en Streamlit (login, rol visible, chat con historial y fuentes, cerrar sesión, errores sin trazas) usando `container.py`; verificar manualmente los escenarios de la spec `chat-ui` con `streamlit run` y con `streamlit.testing.AppTest` para login/logout

## 10. Contenedorización

- [x] 10.1 Escribir `Dockerfile` multi-stage para la imagen Python compartida y verificar que `docker build` finaliza
- [x] 10.2 Escribir `docker-compose.yml` con `postgres` (ParadeDB), `indexer` (monta `./docs:ro`) y `app`, healthchecks, volumen `pgdata`, `OLLAMA_HOST=http://host.docker.internal:11434` y `extra_hosts: host-gateway` (D9); verificar que `docker compose up -d` deja todos los servicios saludables, la UI accesible en `:8501` y la app conectada al Ollama del Mac
- [x] 10.3 Escribir `README.md` con requisitos (Docker, Ollama nativo con `qwen3.5:9b`, `bge-m3`, clave de Cohere), pasos de arranque y la nota de que el corpus es sintético; verificar que los comandos documentados funcionan tal cual

## 11. Validación de KPIs de extremo a extremo

- [x] 11.1 Crear `tests/eval/questions.yaml` (~20 preguntas genéricas y con términos exactos, con rol y documento esperado o "denegado") y el comando `python -m roboost_rag eval` con modos vectorial, BM25 e híbrido (D10); verificar hit-rate híbrido ≥ 0,90 y calibrar pesos RRF y umbral del reranker
- [x] 11.2 Verificar el KPI de control de accesos: todas las preguntas de rol `public` sobre contenido restringido devuelven el mensaje de "no hay información" sin citar documentos restringidos
- [x] 11.3 Verificar el KPI de autoservicio: con el stack levantado, copiar un documento nuevo a `docs/` y comprobar que es consultable en < 5 minutos sin reinicios ni comandos manuales
