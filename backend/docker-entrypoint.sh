#!/bin/sh
# Seed initial model into volume if empty (first run)
if [ ! -f /app/app/ml/artifacts/v1.pkl ]; then
  echo "[ENTRYPOINT] Seeding initial model artifacts..."
  cp -r /app/initial_artifacts/. /app/app/ml/artifacts/ 2>/dev/null || true
  echo "[ENTRYPOINT] Done."
fi

exec "$@"
