#!/bin/sh
set -e

echo "[entrypoint] applying migrations"
alembic upgrade head

echo "[entrypoint] seeding catalog if empty"
python -m scripts.seed --if-empty || echo "[entrypoint] seed skipped"

echo "[entrypoint] starting api"
exec "$@"
