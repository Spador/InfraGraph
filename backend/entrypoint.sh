#!/bin/bash
set -e

# Run seed loader if SEED_ON_START is enabled.
# Seed data is in /app/seed/ (mounted from project root via docker-compose).
# Execution scripts are in /app/execution/ (mounted from project root).
if [ "${SEED_ON_START}" = "true" ]; then
  echo "[entrypoint] Running seed loader..."
  python /app/execution/seed_loader.py --seed-dir /app/seed
  echo "[entrypoint] Seed complete."
fi

echo "[entrypoint] Starting Flask..."
exec python -m flask run
