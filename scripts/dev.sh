#!/usr/bin/env bash
# NeuroSeek AI — one-command development setup.
#
# What this does, in order:
#   1. Ensures .env exists (copies from .env.example if missing).
#   2. Builds the docker images that need building (web, celery, realtime).
#   3. Brings up all 6 services and waits for healthchecks.
#   4. Runs Django migrations.
#   5. Creates the demo superuser if it doesn't exist (rony@neuroseek.ai / rony123).
#   6. Prints helpful URLs.
#
# Run from the repo root: `./scripts/dev.sh` (after `chmod +x scripts/dev.sh`).
set -euo pipefail

cd "$(dirname "$0")/.."

readonly DEMO_EMAIL="${DEMO_EMAIL:-rony@neuroseek.ai}"
readonly DEMO_PASSWORD="${DEMO_PASSWORD:-rony123}"
readonly DEMO_NAME="${DEMO_NAME:-rony}"

c_blue=$'\033[1;34m'
c_green=$'\033[1;32m'
c_yellow=$'\033[1;33m'
c_red=$'\033[1;31m'
c_reset=$'\033[0m'

step() { printf "%s▸ %s%s\n" "$c_blue" "$*" "$c_reset"; }
ok()   { printf "%s✓ %s%s\n" "$c_green" "$*" "$c_reset"; }
warn() { printf "%s! %s%s\n" "$c_yellow" "$*" "$c_reset"; }
fail() { printf "%s✗ %s%s\n" "$c_red" "$*" "$c_reset"; exit 1; }

# 1. Sanity checks ----------------------------------------------------------
command -v docker >/dev/null 2>&1 || fail "Docker is not installed."
docker info >/dev/null 2>&1 || fail "Docker daemon is not running. Start Docker Desktop and re-run."

# 2. .env ------------------------------------------------------------------
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    ok "Created .env from .env.example"
  else
    fail ".env and .env.example are both missing."
  fi
fi

# 3. Build images that need building ----------------------------------------
step "Building images (first time: 5–8 min — pulls torch CPU + sentence-transformers)..."
docker compose build web celery realtime
ok "Images built."

# 4. Pull pre-built images --------------------------------------------------
step "Pulling pre-built service images (db, redis, searxng)..."
docker compose pull db redis searxng
ok "Images pulled."

# 5. Up ---------------------------------------------------------------------
step "Starting all services..."
docker compose up -d

# 6. Wait for db + redis health --------------------------------------------
step "Waiting for db + redis to be healthy..."
for i in $(seq 1 60); do
  if docker compose ps --format '{{.Service}} {{.Health}}' \
     | grep -E '^(db|redis) healthy$' | wc -l | grep -q '2'; then
    ok "db + redis healthy"
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    fail "db/redis didn't reach 'healthy' within 120s. Check 'docker compose logs'."
  fi
done

# 7. Migrate ----------------------------------------------------------------
step "Running migrations..."
docker compose exec -T web python manage.py migrate
ok "Migrations applied."

# 8. Demo superuser ---------------------------------------------------------
step "Creating demo superuser if missing..."
docker compose exec -T web python manage.py shell <<PY
from django.contrib.auth import get_user_model
User = get_user_model()
email = "${DEMO_EMAIL}"
u, created = User.objects.get_or_create(email=email, defaults={"full_name": "${DEMO_NAME}"})
u.full_name = "${DEMO_NAME}"
u.is_staff = True
u.is_superuser = True
u.is_active = True
u.set_password("${DEMO_PASSWORD}")
u.save()
print("created" if created else "updated", email)
PY
ok "Demo superuser ready."

# 9. Summary ----------------------------------------------------------------
cat <<EOF

${c_green}─────────────────────────────────────────────────────────────────${c_reset}
  NeuroSeek AI is up and running.

  Landing  →  http://localhost:8000/
  Sign in  →  http://localhost:8000/login    (${DEMO_EMAIL} / ${DEMO_PASSWORD})
  App      →  http://localhost:8000/app/
  Admin    →  http://localhost:8000/admin/
  SearXNG  →  http://localhost:8080/         (web UI for debugging)
  Realtime →  http://localhost:8001/healthz  (Go hub status)

  Useful:
    docker compose ps                 — service status
    docker compose logs -f celery     — watch Celery worker
    docker compose logs -f realtime   — watch Go hub
    docker compose down               — stop everything (data preserved)
    docker compose down -v            — stop AND wipe data volumes
${c_green}─────────────────────────────────────────────────────────────────${c_reset}
EOF
