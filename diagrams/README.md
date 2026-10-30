# Arquitectura del asistente RAG de RRHH

Cada diagrama está también como fichero `.mmd` independiente en esta carpeta (`01-arquitectura-sistema.mmd`, `02-flujo-pregunta.mmd`, `03-reindexacion.mmd`, `04-estructura-codigo.mmd`), útil para editarlo en [mermaid.live](https://mermaid.live) o exportarlo a imagen.

## 1. Arquitectura del sistema

Qué corre dónde y cómo se comunica. Ollama corre en el Mac (con GPU) y los contenedores lo alcanzan en `host.docker.internal:11434`. Lo único que sale a internet es la llamada al reranker de Cohere, y solo con fragmentos que el rol del usuario ya puede ver.

```mermaid
flowchart LR
    user(["Usuario<br/>navegador"])
    cohere["Cohere Rerank<br/>rerank-v3.5 (internet)"]

    subgraph host["Tu Mac"]
        docs[("docs/<br/>Markdown con front-matter")]
        subgraph ollama["Ollama nativo (GPU)"]
            qwen["qwen3.5:9b<br/>genera respuestas"]
            bge["bge-m3<br/>embeddings 1024d"]
        end
        subgraph compose["Docker Compose"]
            app["app<br/>Streamlit :8501"]
            indexer["indexer<br/>sincroniza cada 5 min"]
            db[("postgres · ParadeDB<br/>pgvector HNSW + pg_search BM25")]
        end
    end

    user -->|"login y pregunta"| app
    docs -.->|"montado en solo lectura"| indexer
    indexer -->|"vectoriza fragmentos"| bge
    indexer -->|"guarda documentos y fragmentos"| db
    app -->|"vectoriza la pregunta"| bge
    app -->|"búsqueda vectorial + BM25<br/>filtradas por rol en SQL"| db
    app -->|"10 candidatos autorizados"| cohere
    app -->|"contexto + pregunta"| qwen
```

## 2. Qué pasa cuando alguien pregunta

```mermaid
sequenceDiagram
    actor U as Usuario
    participant UI as app (Streamlit)
    participant Q as QueryService
    participant R as RetrievalService
    participant O as Ollama
    participant DB as ParadeDB
    participant C as Cohere

    U->>UI: usuario y contraseña
    UI->>UI: bcrypt → rol (public / hr_manager / admin)
    U->>UI: pregunta
    UI->>Q: ask(pregunta, rol)
    Q->>R: retrieve(pregunta, rol)
    par búsqueda por similitud
        R->>O: bge-m3: vector de la pregunta
        R->>DB: top-20 más cercanos WHERE access_level <= rol
    and búsqueda por palabras clave
        R->>DB: top-20 BM25 (|||) WHERE access_level <= rol
    end
    R->>R: fusión RRF → top-10
    R->>C: rerank(pregunta, 10 fragmentos)
    C-->>R: puntuación de relevancia
    Note over R,C: si Cohere falla o hay 429: orden RRF, sin umbral
    R->>R: umbral 0,04 → top-4
    alt ningún fragmento supera el filtro
        R-->>Q: lista vacía
        Q-->>UI: "No dispongo de información…" (sin llamar al LLM)
    else hay fragmentos
        Q->>O: qwen3.5:9b con fragmentos [1]…[4]
        O-->>Q: respuesta con citas
        Q-->>UI: respuesta + fuentes
    end
```

## 3. Cómo se mantiene el índice al día

```mermaid
flowchart TD
    tick["Al arrancar y cada 5 minutos"] --> lock{"¿Hay otra pasada en curso?<br/>pg_try_advisory_lock"}
    lock -- sí --> skip["Se omite esta pasada"]
    lock -- no --> read["Leer docs/<br/>front-matter → title y access_level<br/>sin access_level válido → admin"]
    read --> dedup["Quitar duplicados por contenido<br/>se conserva la copia más restrictiva"]
    dedup --> diff{"¿Cambió el hash<br/>respecto al índice?"}
    diff -- igual --> omit["Omitir: no se recalculan embeddings"]
    diff -- nuevo o cambiado --> chunk["Fragmentar: máx. 3200 caracteres<br/>10 % de solapamiento, título delante"]
    chunk --> emb["bge-m3: un vector por fragmento"]
    emb --> tx["Una transacción: borra los fragmentos viejos<br/>e inserta los nuevos"]
    diff -- el fichero ya no existe --> del["Borrar del índice"]
```

## 4. Cómo está organizado el código

Arquitectura por capas. Los servicios solo conocen interfaces (`ports/`); `container.py` es el único sitio que elige las implementaciones concretas (`adapters/`). Para cambiar Cohere por otro reranker u Ollama por otro LLM basta con un adaptador nuevo y una línea en `container.py`.

```mermaid
flowchart TB
    subgraph entry["Puntos de entrada"]
        ui["ui/app.py<br/>interfaz Streamlit"]
        cli["cli.py<br/>ingest · sync · eval · check · hash-password"]
    end

    container["container.py<br/>construye y conecta todas las piezas"]

    subgraph services["services/ · lógica de negocio"]
        ingestion["ingestion.py<br/>IngestionService"]
        scheduler["scheduler.py<br/>SyncScheduler"]
        chunking["chunking.py<br/>Chunker"]
        retrieval["retrieval.py<br/>RetrievalService"]
        fusion["fusion.py<br/>RRF"]
        query["query.py<br/>QueryService + prompt"]
        auth["auth.py<br/>UserDirectory"]
        evaluation["evaluation.py<br/>KPIs"]
    end

    subgraph ports["ports/ · interfaces"]
        p_src["DocumentSource"]
        p_emb["Embedder"]
        p_vec["VectorStore"]
        p_lex["LexicalIndex"]
        p_rr["Reranker"]
        p_llm["LLM"]
    end

    subgraph adapters["adapters/ · implementaciones"]
        a_fs["fs_source.py"]
        a_oemb["ollama_embedder.py"]
        a_oai["openai_embedder.py<br/>(opcional)"]
        a_pdb["paradedb_store.py"]
        a_coh["cohere_reranker.py"]
        a_llm["ollama_llm.py"]
    end

    domain["domain/models.py<br/>Role · AccessLevel · Document · Chunk · Answer"]

    ui --> container
    cli --> container
    container --> services
    container --> adapters
    scheduler --> ingestion
    ingestion --> chunking
    query --> retrieval
    retrieval --> fusion
    services -->|"dependen solo de"| ports
    a_fs -.-> p_src
    a_oemb -.-> p_emb
    a_oai -.-> p_emb
    a_pdb -.-> p_vec
    a_pdb -.-> p_lex
    a_coh -.-> p_rr
    a_llm -.-> p_llm
    ports --> domain
```

| Interfaz (`ports/`) | Implementación (`adapters/`) | Qué hace |
|---|---|---|
| `DocumentSource` | `fs_source.py` | Lee `docs/` y su front-matter |
| `Embedder` | `ollama_embedder.py` (`openai_embedder.py` opcional) | Convierte texto en vectores de 1024 dimensiones |
| `VectorStore` | `paradedb_store.py` | Guarda fragmentos y busca por similitud filtrando por rol |
| `LexicalIndex` | `paradedb_store.py` | Búsqueda BM25 filtrando por rol |
| `Reranker` | `cohere_reranker.py` | Reordena los 10 candidatos por relevancia |
| `LLM` | `ollama_llm.py` | Genera la respuesta con `qwen3.5:9b` |
