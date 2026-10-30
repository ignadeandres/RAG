# Proposal

## Why

La evaluación actual solo mide hit-rate: si el documento correcto aparece entre los 4 fragmentos finales. No mide en qué posición aparece, que es precisamente lo que cambia el reranker, así que hoy no podemos saber si Cohere aporta algo. Además, el corpus (12 documentos, casi todos de un solo fragmento) y las 23 preguntas son demasiado fáciles: el orden de la fusión RRF ya acierta casi siempre y no deja margen para medir mejoras.

## What Changes

- Nuevas métricas de ranking **MRR** y **nDCG** a nivel de documento, con cortes @4 (lo que llega al LLM) y @10 (todos los candidatos), calculadas **antes** (orden RRF) y **después** (orden de Cohere) del reranker sobre los mismos 10 candidatos.
- Relevancia graduada en el conjunto de evaluación (2 = responde directamente, 1 = relacionado), compatible con el formato actual de lista.
- Comparación por pregunta (mejora / empate / empeora) y tasa de rechazo de preguntas fuera de dominio, separadas de MRR/nDCG.
- Métricas también para la búsqueda vectorial y la BM25 por separado, sin reranker.
- Corpus sintético ampliado a unos 38 documentos de temas muy variados, varios de ellos largos (varios fragmentos), con temas solapados entre niveles.
- Conjunto de evaluación ampliado a unas 50 preguntas más difíciles: paráfrasis sin las palabras del documento, respuestas repartidas entre varios documentos, temas solapados y preguntas dependientes del rol.
- Documentación y diagramas actualizados.

## Capabilities

### New Capabilities
- `retrieval-evaluation`: suite de evaluación de la recuperación: conjunto de preguntas con relevancia graduada, métricas de ranking (MRR, nDCG) antes y después del reranker, hit-rate, rechazo fuera de dominio y detección de fugas por rol.

### Modified Capabilities
- `hr-corpus`: el corpus sintético inicial pasa a exigir más documentos, más variedad y documentos de varios fragmentos.

## Impact

- **Código**: `roboost_rag/services/metrics.py` (nuevo), `services/evaluation.py`, `services/retrieval.py` (exponer candidatos y selección final para la evaluación), `cli.py` (`eval`).
- **Datos**: `docs/` (~26 documentos nuevos), `tests/eval/questions.yaml` (reescrito con grados).
- **Coste externo**: una llamada a Cohere por pregunta da el antes y el después; con la clave de prueba (10 llamadas/min) la evaluación tarda unos 6–7 minutos.
- **Sin cambios** en la recuperación ni en la generación que ven los usuarios.
