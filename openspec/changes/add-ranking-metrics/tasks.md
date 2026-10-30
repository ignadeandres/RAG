# Tasks

## 1. Corpus ampliado

- [x] 1.1 Escribir ~26 documentos sintéticos nuevos en `docs/` (D6): temas variados, al menos 4 de más de 3.200 caracteres y solapes entre niveles; actualizar el test de corpus para exigir ≥ 30 documentos, ≥ 6 por nivel y ≥ 4 documentos con varios fragmentos, y verificar que pasa
- [x] 1.2 Indexar el corpus ampliado en el sistema en marcha y verificar en el log del `indexer` (o con `ingest`) que no hay documentos fallidos

## 2. Métricas

- [x] 2.1 Implementar `services/metrics.py` (`document_ranking`, `reciprocal_rank`, `ndcg`) (D1); tests unitarios con casos calculados a mano: relevante en posición 3, sin relevantes, orden ideal = 1, grados 2/1 invertidos, corte k
- [x] 2.2 Exponer `RetrievalService.candidates()` y `RetrievalService.select()` sin cambiar el comportamiento de `retrieve()` (D2); verificar que los tests de recuperación existentes siguen pasando y añadir uno de `select()`

## 3. Evaluación

- [x] 3.1 Soportar `expected` con grados o lista en la carga de preguntas (D4); test de ambos formatos
- [x] 3.2 Implementar la evaluación de ranking en un solo recorrido por pregunta: vectorial, BM25, híbrido antes y después del reranker, hit-rate final, rechazo fuera de dominio, reintentos y exclusiones (D2, D3); tests con fakes que verifican una sola llamada al reranker por pregunta, mismos candidatos antes/después y exclusión si el reranker falla
- [x] 3.3 Actualizar `python -m roboost_rag eval` con la tabla de métricas, Δ, mejoras/empates/empeoramientos y detalle con `-v` (D5); verificar la salida con una ejecución real

## 4. Conjunto de evaluación difícil

- [x] 4.1 Reescribir `tests/eval/questions.yaml` con ~50 preguntas con grados (paráfrasis, multi-documento, temas solapados, dependientes del rol), 3 fuera de dominio y ~10 de acceso denegado (D6); verificar que todas las rutas de `expected` existen en `docs/` con un test

## 5. Resultados y documentación

- [x] 5.1 Ejecutar la evaluación completa con Cohere contra el corpus ampliado, incluida la de fugas (`--answers`), y registrar los resultados (tabla antes/después) en el README
- [x] 5.2 Actualizar README y `diagrams/` (README y `.mmd`) con la evaluación y las métricas, incluido un diagrama del flujo de evaluación, y republicar la página de arquitectura
