#!/bin/sh
# Runs once, on the first start of an empty data volume. The accounts service
# connects as a role that is not a superuser and owns only its own database.
set -eu

psql -v ON_ERROR_STOP=1 -v password="$ACCOUNTS_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname postgres <<'SQL'
CREATE ROLE accounts LOGIN PASSWORD :'password';
CREATE DATABASE accounts OWNER accounts;
SQL
