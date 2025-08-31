#!/usr/bin/env sh
set -e

echo "[entrypoint] Starting Cosbrain app..."

mkdir -p /app/logs /app/uploaded_files /app/yara/output

if [ -n "$DATABASE_URL" ]; then
  echo "[entrypoint] Using DATABASE_URL from env"
else
  export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-cosbrain}"
  echo "[entrypoint] Built DATABASE_URL=$DATABASE_URL"
fi

echo "[entrypoint] Waiting for Postgres to be ready..."
MAX_TRIES=60
TRIES=0
until python - <<'PY'
import os
from sqlalchemy import create_engine, text
url=os.environ['DATABASE_URL']
engine=create_engine(url,pool_pre_ping=True)
with engine.connect() as c:
    c.execute(text('SELECT 1'))
print('ok')
PY
do
  TRIES=$((TRIES+1))
  if [ "$TRIES" -ge "$MAX_TRIES" ]; then
    echo "[entrypoint] Postgres not ready after $MAX_TRIES attempts" >&2
    exit 1
  fi
  sleep 2
done

python - <<'PY'
import os
from sqlalchemy import create_engine, text
engine=create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
with engine.connect() as c:
    try:
        c.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        c.commit()
        print('pgvector extension ensured')
    except Exception as e:
        print('warning ensuring pgvector:', e)
PY

if [ "${RUN_DB_INIT:-false}" = "true" ]; then
  echo "[entrypoint] Running DB init (drop & create all tables)"
  python - <<'PY'
import project.database as d
d.init_db()
PY
fi

python - <<'PY'
import os, sys
sys.path.insert(0, '/app')
try:
    from yara.scripts.production_config import initialize_yara_for_production
    initialize_yara_for_production()
    print('YARA initialized')
except Exception as e:
    print('YARA init skipped/warn:', e)
PY

echo "[entrypoint] Launching Uvicorn..."
exec python -m uvicorn project.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8001}
