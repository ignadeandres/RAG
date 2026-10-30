# scheduled-reindex Specification

## Purpose
Mantiene el índice vectorial sincronizado con `docs/` de forma desatendida, para que cualquier alta, modificación o baja sea consultable sin reiniciar servicios ni ejecutar comandos manuales.

## Requirements

### Requirement: Ejecución periódica
Un servicio en segundo plano SHALL ejecutar una pasada de sincronización de `docs/` al arrancar y luego cada 5 minutos (intervalo configurable), sin intervención manual.

#### Scenario: Documento nuevo consultable en menos de 5 minutos
- **WHEN** se añade un documento válido a `docs/` con los contenedores en marcha
- **THEN** en menos de 5 minutos el documento queda indexado y sus fragmentos son recuperables por los roles autorizados

### Requirement: Detección de modificaciones
La sincronización SHALL detectar documentos cuyo contenido o `access_level` haya cambiado y reindexarlos con sus nuevos metadatos.

#### Scenario: Cambio de nivel de acceso
- **WHEN** un documento pasa de `access_level: public` a `access_level: admin`
- **THEN** tras la siguiente pasada sus fragmentos dejan de ser recuperables para `public` y `hr_manager`

### Requirement: Detección de bajas
La sincronización SHALL eliminar del índice los fragmentos de documentos que ya no existan en `docs/`.

#### Scenario: Documento eliminado
- **WHEN** se borra un documento de `docs/`
- **THEN** tras la siguiente pasada ninguno de sus fragmentos es recuperable por ningún rol

### Requirement: Resiliencia de la pasada
Un fallo al procesar un documento SHALL no abortar la pasada ni detener el servicio; el documento fallido se reintentará en la siguiente pasada.

#### Scenario: Documento corrupto
- **WHEN** un documento no puede leerse o vectorizarse durante una pasada
- **THEN** el resto de documentos se procesa con normalidad y el servicio sigue programando pasadas

### Requirement: Exclusión de pasadas concurrentes
El sistema SHALL impedir que dos pasadas de sincronización se ejecuten simultáneamente sobre el mismo índice.

#### Scenario: Pasada solapada
- **WHEN** se dispara una pasada mientras la anterior sigue en curso
- **THEN** la nueva pasada se omite o espera, y se registra en el log
