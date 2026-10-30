# Design

## Context

Ver `proposal.md` (Why). La evaluación vive en `services/evaluation.py` y se lanza con `python -m roboost_rag eval`. `RetrievalService` hace búsqueda vectorial + BM25 → RRF (top-10) → Cohere → umbral 0,04 → top-4. La clave de prueba de Cohere admite 10 llamadas por minuto.

## Goals / Non-Goals

**Goals:**
- Aislar el efecto del reranker: mismas entradas, solo cambia el orden.
- Métricas estándar y fáciles de verificar a mano (funciones puras con tests).
- Una sola llamada a Cohere por pregunta para no duplicar el tiempo de evaluación.

**Non-Goals:**
- Etiquetas de relevancia por fragmento (las etiquetas son por documento).
- Tests de significación estadística; se informa de mejoras/empates/empeoramientos por pregunta.
- Cambiar el comportamiento de la recuperación que ven los usuarios.

## Decisions

### D1. Métricas como funciones puras (`services/metrics.py`)
- `document_ranking(chunks)`: rutas en orden de primera aparición.
- `reciprocal_rank(ranking, grades, k)`: `1 / posición` del primer documento con grado > 0 dentro de k; 0 si no hay.
- `ndcg(ranking, grades, k)`: `DCG = Σ (2^g − 1) / log2(i + 1)` para i = 1..k; `IDCG` con los grados etiquetados ordenados de mayor a menor y truncados a k. Ganancia exponencial para que un documento de grado 2 pese el triple que uno de grado 1.
*Alternativa*: librerías como `ranx` o `pytrec_eval`; descartadas por añadir dependencias para unas 30 líneas.

### D2. Un solo recorrido por pregunta
Para cada pregunta: `candidates = retrieval.candidates(q, rol, "hybrid")` (top-10 RRF) → ranking "antes". `reranked = reranker.rerank(q, candidates, top_n=len(candidates))` → ranking "después" (todos los candidatos, sin umbral). La salida final del sistema (para hit-rate y rechazo fuera de dominio) se obtiene aplicando a `reranked` la misma selección que en producción (`retrieval.select(reranked)`: umbral + top-K), así que no hace falta otra llamada.
Para vectorial y BM25 solos se usa `candidates(q, rol, "vector" | "bm25")`, sin Cohere.
`RetrievalService` expone `candidates()` y `select()` como métodos públicos; `retrieve()` sigue igual por fuera.

### D3. Reintentos y exclusión
Si Cohere falla para una pregunta (p. ej. 429), se espera y se reintenta hasta 2 veces con espera creciente. Si sigue fallando, la pregunta se excluye de la comparación antes/después y del hit-rate final, y el informe lo indica.

### D4. Formato del conjunto de evaluación
```yaml
answerable:
  - {role: public, q: "...", expected: {procedimientos/vacaciones_y_permisos.md: 2, beneficios/beneficios_sociales.md: 1}}
  - {role: admin, q: "...", expected: []}       # fuera de dominio
denied:
  - {role: public, q: "...", forbidden: ["52.000"]}
```
`expected` admite dict (grados) o lista (grado 1).

### D5. Informe
Tabla con filas MRR@4, MRR@10, nDCG@4, nDCG@10 y columnas vectorial, BM25, híbrido antes, híbrido después y Δ (después − antes). Debajo: mejoras/empates/empeoramientos de nDCG@10 (empate si |Δ| < 0,001), preguntas excluidas, hit-rate del sistema completo (KPI ≥ 0,90) y tasa de rechazo fuera de dominio. Con `-v`, lista de preguntas que empeoran y de fallos de hit-rate.

### D6. Corpus y preguntas
Unos 26 documentos nuevos (total ~38), de temas variados (onboarding, viajes y gastos, igualdad, evaluación del desempeño, nóminas, seguridad de la información, voluntariado, historia de la empresa, bonus detallado, absentismo, clima, brecha salarial, convenio, incidentes, litigios, retención…). Al menos 4 superan los 3.200 caracteres y producen varios fragmentos. Temas solapados a propósito (variable: política pública ↔ cálculo detallado `hr_manager` ↔ comité de dirección `admin`; igualdad pública ↔ auditoría de brecha `admin`). Unas 50 preguntas con grados, en su mayoría parafraseadas, varias multi-documento, 3 fuera de dominio y ~10 de acceso denegado.

## Risks / Trade-offs

- [Conjunto pequeño: diferencias de pocos puntos pueden ser ruido] → Se informa de mejoras/empates/empeoramientos por pregunta, no solo de la media.
- [Etiquetado subjetivo de los grados] → Grados simples (1/2) y criterios escritos en el propio YAML.
- [Corpus nuevo puede bajar el hit-rate por debajo del KPI] → Es información útil; si ocurre se documenta y se analiza antes de tocar parámetros.
- [Evaluación lenta con la clave de prueba (~6–7 min)] → Intervalo configurable con `--pace`; con una clave de producción se pone a 0.

## Migration Plan

Sin migración: tras añadir los documentos, el `indexer` los indexa en su siguiente pasada (o con `docker compose exec indexer python -m roboost_rag ingest`).
