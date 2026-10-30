# ROBOOST · Asistente RAG de RRHH

Sistema RAG local para consultar la documentación de RRHH de ROBOOST con control de acceso por rol (`public`, `hr_manager`, `admin`).

> **El corpus de `docs/` es sintético**: todos los documentos, nombres y cifras son ficticios y se han generado para este desarrollo de prueba.

## Cómo funciona

1. **Ingesta** (`indexer`): lee `docs/` cada 5 minutos, deduplica, fragmenta con un 10 % de solapamiento, calcula embeddings con `bge-m3` en tu Ollama local y guarda los fragmentos en ParadeDB (PostgreSQL + `pgvector` + `pg_search`).
2. **Recuperación híbrida**: cada pregunta lanza una búsqueda por similitud (vectorial) y otra por palabras clave (BM25), **ambas filtradas por rol dentro de la base de datos**. Los resultados se combinan con Reciprocal Rank Fusion y los 10 mejores se reordenan con Cohere Rerank.
3. **Generación**: `qwen3.5:9b` en el Ollama nativo de tu máquina responde solo con los fragmentos autorizados y cita las fuentes.

## Requisitos

- Docker con Docker Compose.
- [Ollama](https://ollama.com) instalado y en ejecución en el host, con los modelos descargados:
  ```bash
  ollama pull qwen3.5:9b   # generación
  ollama pull bge-m3       # embeddings
  ```
- Opcional: clave de Cohere para el reranking. Sin ella el sistema funciona sin reranking.
- Opcional: `EMBEDDING_PROVIDER=openai` y `OPENAI_API_KEY` para usar OpenAI en lugar de `bge-m3` (exige reindexar todo).

## Puesta en marcha

```bash
cp .env.example .env
# Edita .env: COHERE_API_KEY y APP_USERS (ver abajo)
docker compose up -d --build
```

La UI queda en <http://localhost:8501>. En el primer arranque se crean el esquema y los índices, y el `indexer` indexa `docs/`.

### Usuarios

`APP_USERS` define usuarios locales como `usuario:hash_bcrypt:rol`, separados por comas. Para generar un hash:

```bash
docker compose run --rm app python -m roboost_rag hash-password
```

Ejemplo:

```
APP_USERS='ana:$2b$12$...:public,luis:$2b$12$...:hr_manager,eva:$2b$12$...:admin'
```

> Pon el valor entre **comillas simples**: los hashes contienen `$` y, sin comillas, Docker Compose intentaría interpretarlos como variables.

## Añadir o cambiar documentos

Copia un `.md` o `.txt` en `docs/` (puede ir en subcarpetas) con esta cabecera:

```markdown
---
title: Título del documento
access_level: public   # public | hr_manager | admin
---
```

El `indexer` lo detecta en menos de 5 minutos, sin reiniciar nada. Si falta `access_level` o no es válido, el documento se trata como `admin`. Al borrar un fichero, sus fragmentos desaparecen del índice en la siguiente pasada.

## Comandos útiles

```bash
docker compose logs -f indexer                                # ver las pasadas de sincronización
docker compose exec indexer python -m roboost_rag ingest     # forzar una pasada ahora (en el indexer, que monta docs/)
docker compose run --rm app python -m roboost_rag check       # comprobar Ollama y el reranker
docker compose run --rm app python -m roboost_rag eval -v     # hit-rate vectorial / BM25 / híbrido
docker compose run --rm app python -m roboost_rag eval --answers  # además, busca fugas de datos restringidos
```

## Desarrollo local

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                                   # tests unitarios
docker compose up -d postgres
# Los tests de integración vacían las tablas: usan su propia base de datos, nunca la del sistema.
docker compose exec -T postgres createdb -U roboost roboost_test
docker compose exec -T postgres psql -q -U roboost -d roboost_test < db/init.sql
TEST_DATABASE_URL=postgresql://roboost:roboost@localhost:5432/roboost_test \
  .venv/bin/pytest -m integration                  # tests contra ParadeDB
```

## Estructura

```
roboost_rag/
  domain/     modelos y jerarquía de roles
  ports/      interfaces (Embedder, VectorStore, LexicalIndex, Reranker, LLM, DocumentSource)
  adapters/   OpenAI, ParadeDB, Cohere, Ollama, sistema de ficheros
  services/   ingesta, scheduler, recuperación híbrida, consultas, auth, evaluación
  container.py  composición de dependencias
ui/app.py     interfaz Streamlit
db/init.sql   esquema e índices
docs/         corpus sintético
```

Los servicios (`IngestionService`, `RetrievalService`, `QueryService`) dependen solo de los puertos, de modo que un futuro orquestador de agentes puede usarlos como herramientas o sustituir cualquier adaptador.
