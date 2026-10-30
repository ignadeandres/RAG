# Spec Delta

## Purpose

Define el formato de los documentos fuente de RRHH en `docs/`, los metadatos de clasificación que gobiernan su visibilidad y el corpus sintético inicial con el que se valida el sistema.

## ADDED Requirements

### Requirement: Formato de documento fuente
Cada documento fuente SHALL ser un fichero Markdown (`.md`) o de texto plano (`.txt`) ubicado en `docs/` (incluyendo subcarpetas), con una cabecera YAML front-matter que declare al menos `title` y `access_level`.

#### Scenario: Documento con cabecera válida
- **WHEN** un fichero `docs/beneficios/seguro_medico.md` contiene front-matter con `title` y `access_level: public`
- **THEN** el sistema lo acepta como documento indexable con esos metadatos

#### Scenario: Extensión no soportada
- **WHEN** existe un fichero `docs/nomina.xlsx`
- **THEN** el sistema lo ignora y registra un aviso sin interrumpir la ingesta del resto

### Requirement: Nivel de acceso por defecto restrictivo
Si un documento no declara `access_level`, o declara un valor distinto de `public`, `hr_manager` o `admin`, el sistema SHALL tratarlo con el nivel más restrictivo (`admin`) y registrar un aviso.

#### Scenario: Documento sin access_level
- **WHEN** un documento en `docs/` carece de `access_level` en su front-matter
- **THEN** se indexa con `access_level = admin` y se emite un aviso en el log

#### Scenario: Valor de access_level desconocido
- **WHEN** un documento declara `access_level: interno`
- **THEN** se indexa con `access_level = admin` y se emite un aviso en el log

### Requirement: Corpus sintético inicial
El repositorio SHALL incluir en `docs/` un conjunto sintético de documentos de RRHH de ROBOOST que cubra los tres niveles de acceso, con al menos tres documentos por nivel, y temas de normativa interna, beneficios, políticas salariales y procedimientos.

#### Scenario: Cobertura de niveles
- **WHEN** se inspecciona el corpus inicial de `docs/`
- **THEN** existen al menos tres documentos con `access_level` `public`, tres con `hr_manager` y tres con `admin`

### Requirement: Casos de sensibilidad cruzada
El corpus sintético SHALL incluir temas que aparezcan en varios niveles con contenido distinto (p. ej., una política salarial pública general y las bandas salariales detalladas restringidas), para validar que el filtrado por rol no filtra contenido sensible.

#### Scenario: Mismo tema en niveles distintos
- **WHEN** se inspecciona el corpus inicial
- **THEN** al menos un tema (como la política salarial) tiene un documento `public` y otro `hr_manager` o `admin` con información adicional confidencial
