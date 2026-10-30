# access-control Specification

## Purpose
Garantiza que cada consulta se ejecute en nombre de un rol autenticado y que ningún contenido por encima de ese rol sea recuperado, generado ni mostrado, aplicando el filtrado en la propia base de datos.

## Requirements

### Requirement: Roles y jerarquía de visibilidad
El sistema SHALL reconocer los roles `public`, `hr_manager` y `admin` con visibilidad jerárquica: `public` ve solo `public`; `hr_manager` ve `public` y `hr_manager`; `admin` ve los tres niveles.

#### Scenario: Visibilidad de hr_manager
- **WHEN** un usuario con rol `hr_manager` consulta
- **THEN** solo son candidatos fragmentos con `access_level` `public` o `hr_manager`

#### Scenario: Visibilidad de admin
- **WHEN** un usuario con rol `admin` consulta
- **THEN** son candidatos fragmentos de los tres niveles

### Requirement: Filtrado en la base de datos
El filtro por nivel de acceso SHALL aplicarse como condición de cada consulta de búsqueda (vectorial y léxica BM25) en la base de datos, de modo que los fragmentos no autorizados nunca se devuelvan a la aplicación.

#### Scenario: Ningún fragmento restringido sale de la BD
- **WHEN** un usuario `public` realiza cualquier consulta
- **THEN** el conjunto de filas devuelto por la base de datos no contiene ningún fragmento con `access_level` `hr_manager` o `admin`

#### Scenario: Término exacto de un documento restringido
- **WHEN** un usuario `public` busca un término que solo aparece literalmente en un documento `admin`
- **THEN** la búsqueda léxica no devuelve ningún fragmento de ese documento

### Requirement: Denegación ante contenido restringido
Cuando un usuario `public` pregunta por información que solo existe en documentos restringidos, el sistema SHALL devolver una respuesta vacía o de denegación sin revelar contenido, títulos ni existencia de dichos documentos.

#### Scenario: Pregunta pública sobre bandas salariales
- **WHEN** un usuario `public` pregunta "¿Cuál es la banda salarial de un Senior Engineer?" y esa información solo está en un documento `hr_manager`
- **THEN** el sistema responde que no dispone de información para esa consulta y no cita ni menciona el documento restringido

### Requirement: Autenticación simulada por rol
El sistema SHALL exigir que el usuario se autentique con credenciales locales configuradas antes de consultar, y SHALL derivar el rol exclusivamente de esas credenciales, nunca de un parámetro editable por el cliente en la consulta.

#### Scenario: Credenciales válidas
- **WHEN** un usuario introduce credenciales configuradas para el rol `hr_manager`
- **THEN** la sesión queda asociada al rol `hr_manager`

#### Scenario: Credenciales inválidas
- **WHEN** un usuario introduce credenciales no configuradas
- **THEN** el acceso es rechazado y no se ejecuta ninguna consulta

#### Scenario: Rol no especificado
- **WHEN** una consulta llega al servicio de recuperación sin rol asociado
- **THEN** la consulta se rechaza con error en lugar de asumir un rol por defecto
