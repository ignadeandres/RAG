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
docker compose run --rm app python -m roboost_rag eval -v     # MRR, nDCG y hit-rate antes y después del reranker
docker compose run --rm app python -m roboost_rag eval --answers  # además, busca fugas de datos restringidos
```

## Evaluación de la recuperación

`eval` mide la recuperación con el conjunto de preguntas de `tests/eval/questions.yaml`. Cada pregunta lleva su rol y sus documentos relevantes con un grado: 2 si responde directamente y 1 si está relacionado. Hay preguntas parafraseadas, otras con la respuesta repartida en varios documentos, preguntas fuera de dominio y preguntas de acceso denegado. Calcula:

- **MRR@4 y MRR@10**: lo arriba que aparece el primer documento relevante.
- **nDCG@4 y nDCG@10**: la calidad del orden completo, teniendo en cuenta los grados.
- Ambas métricas para la búsqueda vectorial sola, la BM25 sola y la híbrida **antes** (orden RRF) y **después** del reranker. Antes y después usan los mismos 10 candidatos, así que la diferencia (Δ) mide solo el efecto de Cohere.
- Cuántas preguntas mejoran, empatan o empeoran con el reranker.
- **Hit-rate** del sistema completo (KPI ≥ 90 %) y porcentaje de preguntas fuera de dominio rechazadas.
- Con `--answers`, genera respuestas a las preguntas de acceso denegado y busca fugas de datos restringidos.

Con la clave de prueba de Cohere (10 llamadas por minuto) la evaluación espacia las llamadas 6,5 s (`--pace`) y tarda unos 8 minutos. Con una clave de producción, usa `--pace 0`. El detalle de las métricas y el diagrama del flujo están en [`diagrams/`](diagrams/README.md).

### Resultados (30 de octubre de 2026)

Corpus de 38 documentos y 42 fragmentos, con 54 preguntas (51 con respuesta y 3 fuera de dominio) y 12 de acceso denegado, usando `bge-m3` y `rerank-v3.5`:

| Métrica | Vectorial | BM25 | Híbrido antes | Híbrido después | Δ rerank |
|---|---|---|---|---|---|
| MRR@4 | 0,904 | 0,750 | 0,904 | **0,980** | +0,077 |
| MRR@10 | 0,906 | 0,765 | 0,907 | **0,980** | +0,074 |
| nDCG@4 | 0,878 | 0,735 | 0,902 | **0,970** | +0,068 |
| nDCG@10 | 0,901 | 0,779 | 0,916 | **0,971** | +0,056 |

- **El reranker aporta**: mejora el nDCG@10 de 11 preguntas, deja igual 39 y empeora 1 (la de brecha salarial con rol `admin`, donde antepone el Plan de Igualdad a la auditoría). Las mayores mejoras son preguntas cuyo término exacto RRF no ponía primero ("ROBOOST Explora", "política de mesa limpia") y preguntas de varios documentos.
- **La combinación híbrida** mejora el nDCG respecto a la vectorial sola (0,916 frente a 0,901). BM25 sola rinde menos porque la mayoría de las preguntas están parafraseadas.
- **Hit-rate del sistema completo: 96,3 %**, por encima del KPI del 90 %. Sin reranker sería 90,7 %.
- **Fugas de información: 0** en las 12 preguntas de acceso denegado.
- **Punto débil: solo se rechaza 1 de las 3 preguntas fuera de dominio.** Con el corpus ampliado, la mejor puntuación de Cohere para "mundial de fútbol" (0,041) y "router wifi" (0,042) queda a la altura de la pregunta válida peor puntuada (0,049), así que con el umbral de 0,04 pasan. En esos casos el LLM responde igualmente "No dispongo de esa información", porque el contexto no contiene la respuesta. Subir el umbral a 0,045 los separaría en este conjunto, pero con un margen tan pequeño se ha preferido no ajustarlo.


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
  services/   ingesta, scheduler, recuperación híbrida, consultas, auth, evaluación y métricas (MRR, nDCG)
  container.py  composición de dependencias
ui/app.py     interfaz Streamlit
db/init.sql   esquema e índices
docs/         corpus sintético
```

Los servicios (`IngestionService`, `RetrievalService`, `QueryService`) dependen solo de los puertos, de modo que un futuro orquestador de agentes puede usarlos como herramientas o sustituir cualquier adaptador.
