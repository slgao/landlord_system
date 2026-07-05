# Hausverwaltung — container orchestration
#
#   make up      build (if needed) and start all containers in the background
#   make down    stop and remove all containers
#   make logs     follow logs from every service
#   make ps       show running containers
#   make restart  restart all services
#   make build    (re)build images without starting
#   make migrate  run Alembic migrations inside the api container
#   make seed     load demo data inside the api container
#   make clean    stop containers and remove volumes (DELETES the database)

# Prefer Docker Compose v2 ("docker compose"), fall back to legacy v1 binary.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

.DEFAULT_GOAL := help
.PHONY: help up down logs ps restart build migrate seed clean

help:
	@echo "Hausverwaltung — available targets:"
	@echo "  make up       start all containers (db, api, frontend)"
	@echo "  make down     stop and remove containers"
	@echo "  make logs     follow logs from all services"
	@echo "  make ps       list running containers"
	@echo "  make restart  restart all services"
	@echo "  make build    rebuild images"
	@echo "  make migrate  run database migrations"
	@echo "  make seed     load demo data"
	@echo "  make clean    stop and remove containers + volumes (wipes the DB)"
	@echo ""
	@echo "Using: $(COMPOSE)"

up:
	@# If a standalone dev database container (landlord-pg) is running, make sure
	@# it shares the compose network so the api can reach it by name. Harmless and
	@# skipped when the container or network is absent.
	@# Compose v2 refuses to adopt an unlabeled network, so pre-create it with
	@# the labels compose expects.
	@docker network inspect landlord_system_default >/dev/null 2>&1 || docker network create --label com.docker.compose.network=default --label com.docker.compose.project=landlord_system landlord_system_default >/dev/null 2>&1 || true
	-@docker network connect landlord_system_default landlord-pg >/dev/null 2>&1 || true
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  Frontend  → http://localhost:3000"
	@echo "  FastAPI   → http://localhost:8000  (docs at /docs)"

down:
	@# Detach the external dev database (if attached) so compose can remove the
	@# network cleanly. Non-fatal when it was never connected.
	-@docker network disconnect landlord_system_default landlord-pg >/dev/null 2>&1 || true
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

restart:
	$(COMPOSE) restart

build:
	$(COMPOSE) build

migrate:
	$(COMPOSE) exec api alembic upgrade head

seed:
	$(COMPOSE) exec api python seed_demo.py

clean:
	$(COMPOSE) down -v
