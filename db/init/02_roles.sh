#!/bin/bash
# Crea el usuario de SOLO LECTURA que usa el agente.
# Se ejecuta después de 01_schema.sql (orden alfabético) con las variables del .env.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
    CREATE ROLE agente_ro LOGIN PASSWORD '${AGENTE_RO_PASSWORD}';

    -- Defensa en profundidad: aunque el LLM genere un INSERT/UPDATE/DELETE/DROP,
    -- la base lo rechaza (sin permisos + transacciones de solo lectura + timeout).
    ALTER ROLE agente_ro SET default_transaction_read_only = on;
    ALTER ROLE agente_ro SET statement_timeout = '5s';

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO agente_ro;
    GRANT USAGE ON SCHEMA public, rag TO agente_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO agente_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA rag TO agente_ro;

    -- Las tablas que se creen más adelante también quedan de solo lectura para este usuario.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agente_ro;
    ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT SELECT ON TABLES TO agente_ro;
EOSQL
