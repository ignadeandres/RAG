# Spec Delta

## Purpose

Mide la calidad de la recuperación de forma reproducible, incluida la calidad del orden de los resultados antes y después del reranker, para decidir con datos si cada etapa aporta.

## ADDED Requirements

### Requirement: Conjunto de evaluación con relevancia graduada
El conjunto de evaluación SHALL asociar a cada pregunta un rol y sus documentos relevantes con un grado (2 = responde directamente, 1 = relacionado). Una lista de documentos sin grado SHALL interpretarse como grado 1 para todos.

#### Scenario: Pregunta con grados
- **WHEN** una pregunta declara `{vacaciones_y_permisos.md: 2, beneficios_sociales.md: 1}`
- **THEN** la evaluación usa esos grados para calcular nDCG

#### Scenario: Formato de lista heredado
- **WHEN** una pregunta declara una lista `[a.md, b.md]`
- **THEN** ambos documentos cuentan como relevantes con grado 1

### Requirement: Ranking a nivel de documento
Las métricas de ranking SHALL calcularse sobre la lista de documentos obtenida de los fragmentos en su orden, contando cada documento solo en su primera aparición.

#### Scenario: Varios fragmentos del mismo documento
- **WHEN** los candidatos ordenados son fragmentos de A, A, B
- **THEN** el ranking de documentos evaluado es A, B

### Requirement: MRR y nDCG
Para cada pregunta con documentos relevantes, el sistema SHALL calcular MRR@k (inverso de la posición del primer documento relevante, 0 si no aparece en los k primeros) y nDCG@k con ganancia `2^grado − 1` y descuento `log2(posición + 1)`, normalizado por el orden ideal de los grados etiquetados, para k = 4 y k = 10, y SHALL informar de la media sobre todas las preguntas.

#### Scenario: Documento relevante en tercera posición
- **WHEN** el primer documento relevante aparece en la posición 3
- **THEN** su MRR@4 y MRR@10 valen 1/3

#### Scenario: Orden ideal
- **WHEN** los documentos aparecen ordenados de mayor a menor grado y no falta ninguno relevante
- **THEN** su nDCG@k vale 1

### Requirement: Comparación antes y después del reranker
La evaluación SHALL calcular las métricas de ranking sobre los mismos candidatos fusionados (top-10) en dos órdenes: el orden de la fusión RRF (antes) y el orden asignado por el reranker a esos mismos candidatos, sin umbral (después), con una sola llamada al reranker por pregunta.

#### Scenario: Mismos candidatos
- **WHEN** se evalúa una pregunta
- **THEN** los rankings antes y después contienen exactamente los mismos documentos y solo difiere su orden

#### Scenario: Reranker no disponible para una pregunta
- **WHEN** el reranker falla para una pregunta tras reintentar
- **THEN** esa pregunta se excluye de la comparación antes/después y el informe indica cuántas se excluyeron

### Requirement: Comparación por pregunta
El informe SHALL indicar cuántas preguntas mejoran, empatan o empeoran su nDCG@10 con el reranker, y SHALL poder listar las preguntas que empeoran.

#### Scenario: Resumen de cambios
- **WHEN** termina la evaluación con reranker
- **THEN** el informe muestra el número de preguntas que mejoran, empatan y empeoran

### Requirement: Métricas por buscador
La evaluación SHALL informar también de MRR y nDCG para la búsqueda vectorial sola y para la BM25 sola, sin reranker.

#### Scenario: Tabla comparativa
- **WHEN** se ejecuta la evaluación
- **THEN** el informe muestra MRR@4, MRR@10, nDCG@4 y nDCG@10 para vectorial, BM25, híbrido antes del reranker e híbrido después del reranker

### Requirement: Preguntas fuera de dominio
Las preguntas sin documentos relevantes SHALL excluirse de MRR y nDCG y SHALL medirse aparte como tasa de rechazo: proporción de ellas para las que el sistema completo no devuelve ningún fragmento.

#### Scenario: Pregunta fuera de dominio
- **WHEN** una pregunta sin documentos relevantes no devuelve fragmentos tras el umbral del reranker
- **THEN** cuenta como rechazada correctamente y no afecta a MRR ni nDCG

### Requirement: Respeto del límite de llamadas del reranker
La evaluación SHALL espaciar las llamadas al reranker según un intervalo configurable, por defecto compatible con 10 llamadas por minuto.

#### Scenario: Clave de prueba de Cohere
- **WHEN** se ejecuta la evaluación con el intervalo por defecto
- **THEN** no se superan 10 llamadas al reranker por minuto
