# Spec Delta

## MODIFIED Requirements

### Requirement: Corpus sintético inicial
El repositorio SHALL incluir en `docs/` un conjunto sintético de documentos de RRHH de ROBOOST de al menos 30 documentos que cubra los tres niveles de acceso, con al menos seis documentos por nivel, al menos cuatro documentos que superen el tamaño máximo de fragmento, y temas variados de normativa interna, beneficios, políticas salariales, procedimientos y otros ámbitos de la empresa.

#### Scenario: Cobertura de niveles
- **WHEN** se inspecciona el corpus inicial de `docs/`
- **THEN** existen al menos treinta documentos, con al menos seis con `access_level` `public`, seis con `hr_manager` y seis con `admin`

#### Scenario: Documentos de varios fragmentos
- **WHEN** se fragmenta el corpus inicial con el tamaño de fragmento por defecto
- **THEN** al menos cuatro documentos producen más de un fragmento
