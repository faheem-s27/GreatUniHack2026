#!/usr/bin/env bash
# One-command local Canvas LMS setup (open source, AGPL-3.0).
#
#   ./scripts/setup-canvas.sh          # install (if needed) and start
#   ./scripts/setup-canvas.sh start    # start an existing install
#   ./scripts/setup-canvas.sh stop     # stop Canvas
#   ./scripts/setup-canvas.sh status   # show container status
#   ./scripts/setup-canvas.sh reset    # delete .canvas/ and reinstall
#
# Canvas is cloned into .canvas/canvas-lms and is never committed to this repo.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANVAS_DIR="${CANVAS_DIR:-$REPO_ROOT/.canvas/canvas-lms}"
CANVAS_REPO="${CANVAS_REPO:-https://github.com/instructure/canvas-lms.git}"
MARKER="$REPO_ROOT/.canvas/.installed"

CANVAS_HOST_PORT="${CANVAS_HOST_PORT:-80}"
CANVAS_ADMIN_EMAIL="${CANVAS_ADMIN_EMAIL:-admin@lostpoint.local}"
CANVAS_ADMIN_PASSWORD="${CANVAS_ADMIN_PASSWORD:-lostpoint-canvas}"
CANVAS_ACCOUNT_NAME="${CANVAS_ACCOUNT_NAME:-LostPoint}"
CANVAS_ADD_HOSTS="${CANVAS_ADD_HOSTS:-1}"
CANVAS_STUDENT_EMAIL="${CANVAS_STUDENT_EMAIL:-student@lostpoint.local}"
CANVAS_STUDENT_PASSWORD="${CANVAS_STUDENT_PASSWORD:-lostpoint-student}"

ORIGINAL_ARGS=("$@")
COMMAND="${1:-install}"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: ./scripts/setup-canvas.sh [command]

Commands:
  install   Install Canvas if needed, then start it (default)
  start     Start an existing Canvas install
  stop      Stop Canvas containers
  status    Show Canvas container status
  reset     Delete .canvas/ and reinstall (destructive)
EOF
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    info "Installing Docker"
    if command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y docker docker-compose-plugin 2>/dev/null ||
        sudo dnf install -y docker docker-compose 2>/dev/null ||
        die "Could not install Docker. See https://docs.docker.com/engine/install/"
    elif command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update
      sudo apt-get install -y docker.io docker-compose-v2 ||
        die "Could not install Docker. See https://docs.docker.com/engine/install/"
    else
      die "Install Docker manually: https://docs.docker.com/engine/install/"
    fi
  fi

  if ! docker info >/dev/null 2>&1; then
    if command -v systemctl >/dev/null 2>&1; then
      sudo systemctl enable --now docker >/dev/null 2>&1 || true
    fi
    sleep 2
  fi

  if ! docker info >/dev/null 2>&1; then
    if command -v sg >/dev/null 2>&1 && sg docker -c 'docker info' >/dev/null 2>&1; then
      info "Re-running with the docker group"
      exec sg docker -c "$(printf '%q ' "$0" "${ORIGINAL_ARGS[@]}")"
    fi
    if ! id -Gn "$USER" | grep -qw docker; then
      info "Adding $USER to the docker group"
      sudo usermod -aG docker "$USER"
      if command -v sg >/dev/null 2>&1; then
        exec sg docker -c "$(printf '%q ' "$0" "${ORIGINAL_ARGS[@]}")"
      fi
    fi
    die "Docker is not reachable. Log out and back in, then re-run this script."
  fi

  docker compose version >/dev/null 2>&1 ||
    die "Docker Compose v2 is required (the 'docker compose' command)."
}

ensure_selinux() {
  if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" = "Enforcing" ]; then
    warn "SELinux is enforcing; Canvas bind mounts may be denied."
    info "Temporarily setting SELinux to permissive for this boot"
    sudo setenforce 0 || warn "Could not set SELinux permissive; continuing."
  fi
}

ensure_hosts() {
  [ "$CANVAS_ADD_HOSTS" = "1" ] || return 0
  if ! grep -qE '(^|[[:space:]])canvas\.docker([[:space:]]|$)' /etc/hosts 2>/dev/null; then
    info "Adding canvas.docker to /etc/hosts"
    echo "127.0.0.1 canvas.docker" | sudo tee -a /etc/hosts >/dev/null ||
      warn "Could not update /etc/hosts; use http://localhost instead."
  fi
}

clone_canvas() {
  if [ ! -d "$CANVAS_DIR/.git" ]; then
    info "Cloning Canvas LMS into $CANVAS_DIR (shallow)"
    mkdir -p "$(dirname "$CANVAS_DIR")"
    git clone --depth 1 "$CANVAS_REPO" "$CANVAS_DIR"
  fi
  cd "$CANVAS_DIR"
  [ -x script/docker_dev_setup.sh ] || die "Not a Canvas checkout: $CANVAS_DIR"
}

write_config() {
  info "Writing Docker configuration"
  [ -f config/database.yml ] || cp docker-compose/config/*.yml config/
  [ -f docker-compose.override.yml ] ||
    cp config/docker-compose.override.yml.example docker-compose.override.yml

  if [ ! -f docker-compose.local.yml ]; then
    cat > docker-compose.local.yml <<EOF
services:
  web:
    ports:
      - "${CANVAS_HOST_PORT}:80"
    environment:
      CANVAS_LMS_ADMIN_EMAIL: "${CANVAS_ADMIN_EMAIL}"
      CANVAS_LMS_ADMIN_PASSWORD: "${CANVAS_ADMIN_PASSWORD}"
      CANVAS_LMS_ACCOUNT_NAME: "${CANVAS_ACCOUNT_NAME}"
      CANVAS_LMS_STATS_COLLECTION: "opt_out"
      DISABLE_SPRING: "1"
EOF
  fi

  if [ ! -f .env ] || ! grep -q '^COMPOSE_FILE=' .env; then
    echo "COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml:docker-compose.local.yml" > .env
  fi
}

install_canvas() {
  info "Building images (the long step; 30-90+ minutes on first run)"
  docker compose build --pull --build-arg USER_ID="$(id -u)"

  info "Installing gems, JS packages, and compiling assets"
  docker compose up --no-start web
  docker compose run --rm web ./script/install_assets.sh

  info "Creating and migrating the database"
  docker compose up -d postgres redis
  sleep 5
  docker compose run --rm web bundle exec rake db:create
  docker compose run --rm web bundle exec rake db:migrate RAILS_ENV=development
  docker compose run --rm -e RAILS_ENV=test web bundle exec rake db:create
  docker compose run --rm -e RAILS_ENV=test web bundle exec rake db:migrate

  info "Creating the admin account"
  docker compose run --rm web bundle exec rake db:initial_setup

  touch "$MARKER"
}

start_canvas() {
  info "Starting Canvas"
  # webpack is only needed while changing Canvas source/assets; skip it.
  docker compose up -d postgres redis web jobs
}

canvas_url() {
  local url="http://localhost"
  [ "$CANVAS_HOST_PORT" = "80" ] || url="http://localhost:${CANVAS_HOST_PORT}"
  printf '%s' "$url"
}

wait_for_canvas() {
  local url="$1"
  command -v curl >/dev/null 2>&1 || return 0
  info "Waiting for Canvas to respond at ${url}"
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null --max-time 5 "${url}/login" 2>/dev/null; then
      return 0
    fi
    sleep 5
  done
  return 1
}

provision_oauth() {
  local url token output
  url="$(canvas_url)"

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found; skipping automatic Canvas OAuth setup."
    return 0
  fi
  if ! wait_for_canvas "$url"; then
    warn "Canvas did not respond in time; skipping automatic OAuth setup."
    warn "Once Canvas is up, run: $0 start"
    return 0
  fi

  info "Creating an admin API token for LostPoint provisioning"
  cd "$CANVAS_DIR"
  output="$(
    docker compose exec -T -e LP_ADMIN_EMAIL="$CANVAS_ADMIN_EMAIL" web \
      bundle exec rails runner '
pseudonym = Pseudonym.find_by(unique_id: ENV.fetch("LP_ADMIN_EMAIL"))
abort "admin user not found" unless pseudonym
user = pseudonym.user
user.access_tokens.where(purpose: "LostPoint setup").destroy_all
token = user.access_tokens.create!(purpose: "LostPoint setup")
puts "LP_TOKEN=#{token.full_token}"
' 2>/dev/null || true
  )"
  token="$(printf '%s\n' "$output" | sed -n 's/^LP_TOKEN=//p' | tail -n 1)"

  if [ -z "$token" ]; then
    warn "Could not create an admin API token automatically."
    warn "Log in to Canvas, create a token under Account -> Settings,"
    warn "put it in backend/.env as CANVAS_API_TOKEN, then run:"
    warn "  python3 backend/scripts/setup_canvas_oauth.py"
    return 0
  fi

  info "Configuring the LostPoint developer key, demo student, and backend/.env"
  if ! CANVAS_BASE_URL="$url" \
    CANVAS_API_TOKEN="$token" \
    CANVAS_ADMIN_EMAIL="$CANVAS_ADMIN_EMAIL" \
    CANVAS_STUDENT_EMAIL="$CANVAS_STUDENT_EMAIL" \
    CANVAS_STUDENT_PASSWORD="$CANVAS_STUDENT_PASSWORD" \
    python3 "$REPO_ROOT/backend/scripts/setup_canvas_oauth.py"; then
    warn "Canvas OAuth provisioning failed; see the message above."
  fi
}

print_summary() {
  local url
  url="$(canvas_url)"
  cat <<EOF

Canvas is running.

  URL:      ${url}/        (also http://canvas.docker/)
  Admin:    ${CANVAS_ADMIN_EMAIL}
  Password: ${CANVAS_ADMIN_PASSWORD}

Demo student (already enrolled in the demo course):
  Email:    ${CANVAS_STUDENT_EMAIL}
  Password: ${CANVAS_STUDENT_PASSWORD}

Backend:
  cd backend
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  .venv/bin/uvicorn main:app --reload

Frontend (proxies /api to the backend):
  cd frontend && npm install && npm run dev

Sign in with Canvas:
  ${FRONTEND_ORIGIN:-http://localhost:5173}/api/auth/canvas/login

Add your PDF slides to a course module as the admin; the student sees them
through the backend at /api/courses and /api/files/{id}/content.
EOF
}

case "$COMMAND" in
  install)
    ensure_docker
    if [ -f "$MARKER" ]; then
      info "Canvas is already installed; starting it"
      clone_canvas
      start_canvas
    else
      ensure_selinux
      ensure_hosts
      clone_canvas
      write_config
      install_canvas
      start_canvas
    fi
    provision_oauth
    print_summary
    ;;
  start)
    ensure_docker
    [ -d "$CANVAS_DIR/.git" ] || die "Canvas is not installed yet. Run: $0 install"
    clone_canvas
    start_canvas
    provision_oauth
    print_summary
    ;;
  stop)
    ensure_docker
    [ -d "$CANVAS_DIR/.git" ] || die "Canvas is not installed yet."
    cd "$CANVAS_DIR"
    docker compose stop
    ;;
  status)
    ensure_docker
    [ -d "$CANVAS_DIR/.git" ] || die "Canvas is not installed yet."
    cd "$CANVAS_DIR"
    docker compose ps
    ;;
  reset)
    warn "This deletes $REPO_ROOT/.canvas and reinstalls Canvas."
    read -r -p "Continue? [y/N] " reply
    [[ "${reply:-n}" =~ ^[Yy]$ ]] || exit 0
    rm -rf "$REPO_ROOT/.canvas"
    exec "$0" install
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
