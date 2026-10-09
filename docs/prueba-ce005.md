# Prueba de reproducibilidad (CE-005)

## Objetivo

Comprobar que una persona que no participó del desarrollo puede levantar el proyecto y obtener una respuesta del agente siguiendo **solo el [README](../README.md)**. No se evalúa a la persona: se evalúa el README. Cada tropiezo es un defecto del texto (o del código) que hay que corregir.

## Qué necesita la persona

- Docker con Compose, funcionando.
- Python 3.12 a 3.14.
- Una clave de la API de Gemini (Google AI Studio).
- El repositorio clonado en una carpeta nueva, con los cambios de la entrega ya subidos.

## La regla

La persona usa **solo el README**. Quien la acompaña observa y anota, pero no explica, no corrige comandos ni da pistas. Si la persona se traba, lo anota como tropiezo y recién entonces se la ayuda para que pueda seguir, dejando escrito qué ayuda hizo falta.

## Para quien acompaña, antes de empezar

- Confirmar que `.gitattributes` está en el repositorio que se clona (evita el fin de línea CRLF en `db/init/02_roles.sh` en Windows).
- Confirmar que el puerto 5432 está libre y que no hay una base del proyecto corriendo.
- No pasarle el archivo `.env` propio: la persona crea el suyo con su clave.
- Empezar a medir cuando abre el README.

## Registro

| Campo | Valor |
|-------|-------|
| Fecha | |
| Persona (rol, no hace falta el nombre) | |
| Sistema operativo | |
| Versión de Python | |
| Hora de inicio | |
| Hora de la primera respuesta del agente | |
| Tiempo hasta la primera respuesta | |
| Pregunta que hizo | |
| ¿Usó la app o la consola? | |
| ¿Llegó a una respuesta sin ayuda? (sí / no) | |

### Tropiezos

Un renglón por cada vez que la persona se frenó, se equivocó o necesitó ayuda.

| N.º | Paso del README | Qué pasó | Cómo lo resolvió | ¿Hizo falta ayuda? | Corrección (README o código) |
|-----|-----------------|----------|------------------|--------------------|------------------------------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

Cantidad de tropiezos: ____

## Qué debería ver

Marcar lo que apareció:

- [ ] Una respuesta en castellano (o en inglés si la pregunta fue en inglés), sin mensajes de error.
- [ ] El rótulo **Fuente** (Base de datos, Documentos, Ambas o Rechazada), coherente con la pregunta.
- [ ] Si la fuente incluye la base: el desplegable **Consulta SQL ejecutada** con la sentencia.
- [ ] Si la fuente incluye documentos: el desplegable **Documentos citados** con el documento y la página.
- [ ] El tiempo que tardó la respuesta.

## Resultado

- Primera respuesta lograda siguiendo solo el README: sí / no.
- Tiempo hasta la primera respuesta: ____ min.
- Tropiezos: ____ (corregidos en el README: ____; corregidos en el código: ____).
- Observaciones:
