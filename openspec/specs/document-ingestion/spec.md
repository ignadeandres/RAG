# document-ingestion Specification

## Purpose
Transforma los documentos fuente de `docs/` en fragmentos con embeddings y metadatos de acceso persistidos en el almacén vectorial, evitando duplicados y preservando el contexto entre fragmentos.

## Requirements

### Requirement: Deduplicación ligera por contenido
La ingesta SHALL calcular un hash del contenido normalizado de cada documento y SHALL no volver a generar embeddings de un documento cuyo hash ya esté indexado.

#### Scenario: Documento sin cambios
- **WHEN** se ejecuta la ingesta y un documento tiene el mismo hash que su versión indexada
- **THEN** no se regeneran sus embeddings ni se llama a la API de embeddings para él

#### Scenario: Copia idéntica con otra ruta
- **WHEN** dos ficheros en `docs/` tienen contenido normalizado idéntico
- **THEN** el contenido se indexa una sola vez y se registra el duplicado en el log

#### Scenario: Copias idénticas con niveles distintos
- **WHEN** dos ficheros tienen contenido idéntico pero distinto `access_level`
- **THEN** la copia conservada lleva el nivel más restrictivo de ambos

### Requirement: Chunking con solapamiento del 10 %
La ingesta SHALL dividir cada documento en fragmentos de tamaño máximo configurable, donde cada fragmento (salvo el primero) comience con un solapamiento equivalente al 10 % del tamaño máximo tomado del final del fragmento anterior, intentando cortar en límites de párrafo o frase.

#### Scenario: Documento largo
- **WHEN** se fragmenta un documento con un tamaño máximo de fragmento N
- **THEN** cada par de fragmentos consecutivos comparte aproximadamente 0,1·N de contenido y ningún fragmento supera N

#### Scenario: Documento corto
- **WHEN** un documento es menor que el tamaño máximo de fragmento
- **THEN** produce un único fragmento sin solapamiento

### Requirement: Embeddings de 1024 dimensiones
Cada fragmento SHALL vectorizarse con un modelo de embeddings de 1024 dimensiones, por defecto `bge-m3` servido por el Ollama local; las preguntas SHALL vectorizarse con el mismo modelo. Los fragmentos se envían en lotes y se reintenta ante errores transitorios.

#### Scenario: Embeddings locales por defecto
- **WHEN** se ingesta un documento con la configuración por defecto
- **THEN** sus fragmentos se vectorizan con `bge-m3` en el Ollama local sin llamar a APIs externas

#### Scenario: Error transitorio del servicio de embeddings
- **WHEN** el servicio de embeddings no responde o devuelve un error de límite de tasa o 5xx
- **THEN** la ingesta reintenta con espera exponencial antes de marcar el documento como fallido

#### Scenario: Fallo persistente
- **WHEN** un documento no puede vectorizarse tras agotar los reintentos
- **THEN** su versión indexada anterior (si existe) se conserva intacta y el error se registra

### Requirement: Persistencia con metadatos de acceso
Cada fragmento SHALL persistirse con su vector, texto, ruta del documento origen, título, posición, hash del documento y `access_level` heredado del documento.

#### Scenario: Metadatos heredados
- **WHEN** se indexa un documento `hr_manager` con 5 fragmentos
- **THEN** los 5 fragmentos almacenados tienen `access_level = hr_manager` y la misma ruta y título de origen

### Requirement: Reemplazo atómico de documentos
Al reindexar un documento modificado, la sustitución de sus fragmentos antiguos por los nuevos SHALL ser atómica, de modo que ninguna consulta observe una mezcla de versiones ni un documento sin fragmentos.

#### Scenario: Consulta durante la reindexación
- **WHEN** se consulta mientras un documento modificado se está reindexando
- **THEN** la consulta ve íntegramente la versión anterior o íntegramente la nueva

### Requirement: Ingesta bajo demanda
El sistema SHALL ofrecer un comando que ejecute una pasada completa de ingesta sobre `docs/` y finalice informando de documentos añadidos, actualizados, eliminados, omitidos y fallidos.

#### Scenario: Ejecución manual
- **WHEN** un operador ejecuta el comando de ingesta
- **THEN** el comando termina con código 0 y muestra el resumen de la pasada
