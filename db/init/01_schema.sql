-- =====================================================================
-- Esquema del gimnasio + almacenamiento vectorial para el RAG
-- Se ejecuta automáticamente al crear el contenedor por primera vez.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------
-- Datos de negocio (esquema public): los consulta la SQL tool
-- ---------------------------------------------------------------------

CREATE TABLE planes (
    id_plan           SERIAL PRIMARY KEY,
    nombre            VARCHAR(50)   NOT NULL UNIQUE,
    precio_mensual    NUMERIC(10,2) NOT NULL CHECK (precio_mensual > 0),
    clases_por_semana INT           NOT NULL CHECK (clases_por_semana >= 0),
    duracion_meses    INT           NOT NULL DEFAULT 1 CHECK (duracion_meses > 0)
);

CREATE TABLE socios (
    id_socio         SERIAL PRIMARY KEY,
    nombre           VARCHAR(60)  NOT NULL,
    apellido         VARCHAR(60)  NOT NULL,
    email            VARCHAR(120) NOT NULL UNIQUE,
    fecha_nacimiento DATE         NOT NULL,
    fecha_alta       DATE         NOT NULL,
    id_plan          INT          NOT NULL REFERENCES planes(id_plan),
    estado           VARCHAR(10)  NOT NULL DEFAULT 'activo'
                     CHECK (estado IN ('activo', 'congelado', 'baja'))
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
    id_instructor INT         NOT NULL REFERENCES instructores(id_instructor),
    dia_semana    VARCHAR(10) NOT NULL
                  CHECK (dia_semana IN ('lunes','martes','miercoles','jueves','viernes','sabado','domingo')),
    hora          TIME        NOT NULL,
    cupo          INT         NOT NULL CHECK (cupo > 0),
    sala          VARCHAR(30) NOT NULL
);

CREATE TABLE asistencias (
    id_asistencia SERIAL PRIMARY KEY,
    id_socio      INT     NOT NULL REFERENCES socios(id_socio),
    id_clase      INT     NOT NULL REFERENCES clases(id_clase),
    fecha         DATE    NOT NULL,
    presente      BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (id_socio, id_clase, fecha)
);

CREATE TABLE pagos (
    id_pago             SERIAL PRIMARY KEY,
    id_socio            INT           NOT NULL REFERENCES socios(id_socio),
    fecha_pago          DATE,          -- NULL mientras el pago está pendiente
    monto               NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    mes_correspondiente DATE          NOT NULL, -- primer día del mes que se paga
    medio_pago          VARCHAR(20)   NOT NULL
                        CHECK (medio_pago IN ('efectivo','transferencia','tarjeta','mercado_pago')),
    estado              VARCHAR(10)   NOT NULL
                        CHECK (estado IN ('pagado','pendiente','vencido'))
);

CREATE TABLE equipamiento (
    id_equipo           SERIAL PRIMARY KEY,
    nombre              VARCHAR(80) NOT NULL,
    tipo                VARCHAR(40) NOT NULL,
    sala                VARCHAR(30) NOT NULL,
    estado              VARCHAR(20) NOT NULL
                        CHECK (estado IN ('operativo','en_mantenimiento','fuera_de_servicio')),
    fecha_adquisicion   DATE        NOT NULL,
    ultimo_mantenimiento DATE
);

CREATE INDEX idx_socios_plan          ON socios(id_plan);
CREATE INDEX idx_asistencias_socio    ON asistencias(id_socio, fecha);
CREATE INDEX idx_asistencias_clase    ON asistencias(id_clase);
CREATE INDEX idx_pagos_socio_mes      ON pagos(id_socio, mes_correspondiente);

-- ---------------------------------------------------------------------
-- Almacenamiento del RAG (esquema rag): lo consulta la RAG tool.
-- Se mantiene separado para que la SQL tool solo "vea" las tablas de negocio.
-- ---------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE rag.documentos (
    id_documento   SERIAL PRIMARY KEY,
    nombre_archivo VARCHAR(200) NOT NULL UNIQUE,
    titulo         VARCHAR(200) NOT NULL,
    fecha_ingesta  TIMESTAMP    NOT NULL DEFAULT now()
);

CREATE TABLE rag.chunks (
    id_chunk     SERIAL PRIMARY KEY,
    id_documento INT  NOT NULL REFERENCES rag.documentos(id_documento) ON DELETE CASCADE,
    pagina       INT,
    orden        INT  NOT NULL,
    contenido    TEXT NOT NULL,
    -- Modelo de embeddings: gemini-embedding-001. Devuelve 3072 dimensiones por defecto,
    -- pero el índice HNSW de pgvector admite hasta 2000: hay que pedir
    -- output_dimensionality=1536 al generar los embeddings (en la ingesta y en las consultas).
    -- Si se cambia el modelo o la dimensión, hay que ajustar este valor y volver a ingestar.
    embedding    vector(1536) NOT NULL
);

CREATE INDEX idx_chunks_embedding ON rag.chunks USING hnsw (embedding vector_cosine_ops);
