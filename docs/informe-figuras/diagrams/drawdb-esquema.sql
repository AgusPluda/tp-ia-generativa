-- Esquema simplificado para importar en drawDB (Import -> SQL, dialecto PostgreSQL).
-- Se quitaron CHECK, DEFAULT y el esquema "rag" (en la base real son rag.documentos y rag.chunks),
-- y el vector(1536) se declara como TEXT porque drawDB no conoce ese tipo.

CREATE TABLE planes (
    id_plan           SERIAL PRIMARY KEY,
    nombre            VARCHAR(50)   NOT NULL UNIQUE,
    precio_mensual    NUMERIC(10,2) NOT NULL,
    clases_por_semana INT           NOT NULL,
    duracion_meses    INT           NOT NULL
);

CREATE TABLE socios (
    id_socio         SERIAL PRIMARY KEY,
    nombre           VARCHAR(60)  NOT NULL,
    apellido         VARCHAR(60)  NOT NULL,
    email            VARCHAR(120) NOT NULL UNIQUE,
    fecha_nacimiento DATE         NOT NULL,
    fecha_alta       DATE         NOT NULL,
    id_plan          INT          NOT NULL,
    estado           VARCHAR(10)  NOT NULL
);

CREATE TABLE instructores (
    id_instructor SERIAL PRIMARY KEY,
    nombre        VARCHAR(60) NOT NULL,
    apellido      VARCHAR(60) NOT NULL,
    especialidad  VARCHAR(60) NOT NULL,
    fecha_ingreso DATE        NOT NULL
);

CREATE TABLE clases (
    id_clase      SERIAL PRIMARY KEY,
    nombre        VARCHAR(60) NOT NULL,
    id_instructor INT         NOT NULL,
    dia_semana    VARCHAR(10) NOT NULL,
    hora          TIME        NOT NULL,
    cupo          INT         NOT NULL,
    sala          VARCHAR(30) NOT NULL
);

CREATE TABLE asistencias (
    id_asistencia SERIAL PRIMARY KEY,
    id_socio      INT     NOT NULL,
    id_clase      INT     NOT NULL,
    fecha         DATE    NOT NULL,
    presente      BOOLEAN NOT NULL
);

CREATE TABLE pagos (
    id_pago             SERIAL PRIMARY KEY,
    id_socio            INT           NOT NULL,
    fecha_pago          DATE,
    monto               NUMERIC(10,2) NOT NULL,
    mes_correspondiente DATE          NOT NULL,
    medio_pago          VARCHAR(20)   NOT NULL,
    estado              VARCHAR(10)   NOT NULL
);

CREATE TABLE equipamiento (
    id_equipo            SERIAL PRIMARY KEY,
    nombre               VARCHAR(80) NOT NULL,
    tipo                 VARCHAR(40) NOT NULL,
    sala                 VARCHAR(30) NOT NULL,
    estado               VARCHAR(20) NOT NULL,
    fecha_adquisicion    DATE        NOT NULL,
    ultimo_mantenimiento DATE
);

CREATE TABLE rag_documentos (
    id_documento   SERIAL PRIMARY KEY,
    nombre_archivo VARCHAR(200) NOT NULL UNIQUE,
    titulo         VARCHAR(200) NOT NULL,
    fecha_ingesta  TIMESTAMP    NOT NULL
);

CREATE TABLE rag_chunks (
    id_chunk     SERIAL PRIMARY KEY,
    id_documento INT  NOT NULL,
    pagina       INT,
    orden        INT  NOT NULL,
    contenido    TEXT NOT NULL,
    embedding    TEXT NOT NULL
);

ALTER TABLE socios      ADD FOREIGN KEY (id_plan)       REFERENCES planes(id_plan);
ALTER TABLE clases      ADD FOREIGN KEY (id_instructor) REFERENCES instructores(id_instructor);
ALTER TABLE asistencias ADD FOREIGN KEY (id_socio)      REFERENCES socios(id_socio);
ALTER TABLE asistencias ADD FOREIGN KEY (id_clase)      REFERENCES clases(id_clase);
ALTER TABLE pagos       ADD FOREIGN KEY (id_socio)      REFERENCES socios(id_socio);
ALTER TABLE rag_chunks  ADD FOREIGN KEY (id_documento)  REFERENCES rag_documentos(id_documento);
