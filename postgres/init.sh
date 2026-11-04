#!/bin/bash
# Runs once, on first boot of an empty data volume.
# Creates one database per service and enables pgvector where needed.
set -euo pipefail

for db in concierge n8n chatwoot twenty; do
  echo "Creating database: ${db}"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "CREATE DATABASE ${db};"
done

for db in concierge chatwoot; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${db}" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;"
done
