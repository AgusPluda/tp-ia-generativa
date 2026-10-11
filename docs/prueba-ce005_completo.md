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
| Fecha | 11/10 |
| Persona (rol, no hace falta el nombre) | yo |
| Sistema operativo | Windows 10 |
| Versión de Python | 3.14 |
| Hora de inicio | 18:12 |
| Hora de la primera respuesta del agente |18:26 |
| Tiempo hasta la primera respuesta |14 min. |
| Pregunta que hizo |¿Cuántos socios tiene cada plan? |
| ¿Usó la app o la consola? |app |
| ¿Llegó a una respuesta sin ayuda? (sí / no) | si|

### Tropiezos

Un renglón por cada vez que la persona se frenó, se equivocó o necesitó ayuda.

| N.º | Paso del README | Qué pasó | Cómo lo resolvió | ¿Hizo falta ayuda? | Corrección (README o código) |
|-----|-----------------|----------|------------------|--------------------|------------------------------|
| 1 |Datos y Documentos: python scripts/generate_data.py |Error de conexion a la base de datos via psycopg |Claude |De claude |Reiniciar usando docker compose down -v y iniciandolo denuevo, con docker compose up -d, revision de logs con docker compose logs db y volve a intentar lanzar el script, siendo exitosa esa vez |
| 2 | | | | | |
| 3 | | | | | |

Cantidad de tropiezos: 1

## Qué debería ver

Marcar lo que apareció:

- [x] Una respuesta en castellano (o en inglés si la pregunta fue en inglés), sin mensajes de error.
- [x] El rótulo **Fuente** (Base de datos, Documentos, Ambas o Rechazada), coherente con la pregunta.
- [x] Si la fuente incluye la base: el desplegable **Consulta SQL ejecutada** con la sentencia.
- [x] Si la fuente incluye documentos: el desplegable **Documentos citados** con el documento y la página.
- [x] El tiempo que tardó la respuesta.

## Resultado

- Primera respuesta lograda siguiendo solo el README: no, pero solo con un tropiezo y correccion rapida, apagando y volviendo a prender el container de docker para que no tenga credenciales viejas, que colapsaban con las nuevas como pide en el README..
- Tiempo hasta la primera respuesta:  14 min.
- Tropiezos: 1 (corregidos en el README: Nada; corregidos en el código: Sin correcciones de codigo.
- Observaciones: El error que tuvimos tanto mi tester como yo es que ya teniamos un container de docker del mismo tipo porque habiamos ya levantado el container y probado del agente, entonces a la hora de crear esta prueba las creedenciales del trabajo original colapsaron con las nuevas cuando se quiso acceder a la base de datos, se corrigio simplemente bajando el container, volviendo a levantar, una pequeña revision de logs por las dudas, lanzado del primer script de datos y esta vez si funcionando.
 En el caso de que otra persona quiera iniciar/revisar este trabajo, no deberia tener problema porque el camino del README solamente fallo por una concurrencia de credenciales la cual es un fallo que solo nos podria ocurrir a los integrantes del grupo que hemos creado un container con las mismas caracteristicas por el simple hecho de realizar el trabajo integrador.