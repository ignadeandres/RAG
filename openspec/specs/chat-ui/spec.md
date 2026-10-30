# chat-ui Specification

## Purpose
Ofrece a los empleados y al equipo de RRHH una interfaz web conversacional mínima, autenticada por rol, para consultar la documentación de RRHH.

## Requirements

### Requirement: Pantalla de inicio de sesión
La UI SHALL mostrar una pantalla de acceso con usuario y contraseña antes de permitir cualquier consulta, y SHALL mostrar el rol activo una vez autenticado.

#### Scenario: Acceso sin sesión
- **WHEN** un usuario abre la UI sin haber iniciado sesión
- **THEN** solo ve el formulario de acceso y no puede enviar preguntas

#### Scenario: Sesión iniciada
- **WHEN** el usuario se autentica como `hr_manager`
- **THEN** la UI muestra el chat e indica el rol `hr_manager`

### Requirement: Conversación
La UI SHALL permitir enviar preguntas en lenguaje natural y mostrar el historial de preguntas y respuestas de la sesión, cada respuesta con sus fuentes.

#### Scenario: Pregunta respondida
- **WHEN** el usuario envía una pregunta
- **THEN** la UI muestra la respuesta y debajo la lista de documentos fuente

### Requirement: Cierre de sesión
La UI SHALL permitir cerrar sesión, borrando el historial de conversación y el rol asociado.

#### Scenario: Logout
- **WHEN** el usuario pulsa "Cerrar sesión"
- **THEN** vuelve a la pantalla de acceso y el historial anterior ya no es visible

### Requirement: Errores visibles y seguros
La UI SHALL mostrar mensajes de error comprensibles cuando un servicio dependiente no esté disponible, sin mostrar trazas ni datos internos.

#### Scenario: Backend no disponible
- **WHEN** la base de datos o Ollama no están disponibles al enviar una pregunta
- **THEN** la UI muestra un aviso de servicio no disponible sin traza de excepción
