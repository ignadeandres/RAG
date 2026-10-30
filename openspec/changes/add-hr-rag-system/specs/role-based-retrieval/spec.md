# Spec Delta

## Purpose

Recupera, para una pregunta y un rol, los fragmentos autorizados más relevantes combinando búsqueda léxica (BM25) y búsqueda vectorial, y los reordena con una capa de reranking antes de pasarlos a la generación.

## ADDED Requirements

### Requirement: Búsqueda vectorial filtrada por rol
Dada una pregunta y un rol, el sistema SHALL vectorizar la pregunta con el mismo modelo de embeddings que la ingesta y obtener los N fragmentos autorizados más similares por distancia coseno (N configurable, por defecto 20).

#### Scenario: Pregunta genérica o parafraseada
- **WHEN** un usuario pregunta "¿qué ayudas tengo si voy a tener un hijo?" y el documento relevante habla de "permiso por nacimiento" sin usar esas palabras
- **THEN** la búsqueda vectorial devuelve fragmentos de ese documento

### Requirement: Búsqueda léxica BM25 filtrada por rol
Dada una pregunta y un rol, el sistema SHALL obtener los N fragmentos autorizados con mayor puntuación BM25 sobre el texto de los fragmentos (N configurable, por defecto 20).

#### Scenario: Término exacto
- **WHEN** un usuario pregunta por un código o nombre propio que aparece literalmente en un documento (p. ej., "procedimiento PRL-04")
- **THEN** la búsqueda BM25 devuelve fragmentos que contienen ese término entre sus primeros resultados

### Requirement: Fusión de resultados
Los resultados de ambas búsquedas SHALL combinarse mediante Reciprocal Rank Fusion, con pesos configurables por búsqueda, produciendo hasta 10 candidatos únicos ordenados por puntuación fusionada.

#### Scenario: Fragmento presente en ambas listas
- **WHEN** un fragmento aparece en posiciones altas tanto en la búsqueda vectorial como en BM25
- **THEN** queda por encima de fragmentos que solo aparecen en una de las dos listas en posiciones equivalentes

#### Scenario: Una búsqueda sin resultados
- **WHEN** la búsqueda BM25 no devuelve resultados (ningún término coincide) y la vectorial sí
- **THEN** los candidatos se forman solo con los resultados vectoriales, sin error

#### Scenario: Índice vacío para el rol
- **WHEN** no existe ningún fragmento autorizado para el rol
- **THEN** se devuelve una lista vacía sin error

### Requirement: Reranking de candidatos
Los candidatos fusionados SHALL reordenarse mediante un servicio de reranking que puntúe cada par (pregunta, fragmento), y solo los mejores K (configurable, por defecto 4) SHALL pasar a la generación.

#### Scenario: Reordenación
- **WHEN** se obtienen 10 candidatos de la fusión
- **THEN** se devuelven los K de mayor puntuación de reranking en orden descendente

### Requirement: Degradación sin reranker
Si el servicio de reranking no está configurado o falla, el sistema SHALL continuar usando el orden de la fusión para seleccionar los K mejores candidatos y registrar un aviso, sin devolver error al usuario.

#### Scenario: Reranker no disponible
- **WHEN** la API de reranking devuelve un error o agota el tiempo de espera
- **THEN** se devuelven los K primeros candidatos de la fusión y se registra un aviso

### Requirement: Umbral de relevancia
Cuando el reranking está disponible, el sistema SHALL descartar candidatos cuya puntuación quede por debajo de un umbral configurable, y SHALL devolver una lista vacía si ninguno lo supera.

#### Scenario: Pregunta fuera de dominio
- **WHEN** se pregunta algo sin relación con el corpus (p. ej., una receta de cocina)
- **THEN** ningún candidato supera el umbral y la recuperación devuelve una lista vacía

### Requirement: Solo contenido autorizado sale hacia el reranker
El sistema SHALL enviar al servicio de reranking únicamente fragmentos ya filtrados por el rol del usuario.

#### Scenario: Usuario public
- **WHEN** un usuario `public` hace una consulta
- **THEN** ninguno de los fragmentos enviados al reranker tiene `access_level` `hr_manager` o `admin`

### Requirement: Precisión de recuperación
Sobre un conjunto de evaluación de preguntas con su documento esperado, el documento esperado SHALL aparecer entre los fragmentos finales recuperados en al menos el 90 % de los casos.

#### Scenario: Evaluación de precisión
- **WHEN** se ejecuta la suite de evaluación de recuperación contra el corpus sintético indexado
- **THEN** la tasa de aciertos es mayor o igual a 0,90
