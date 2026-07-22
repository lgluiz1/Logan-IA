# Logan AI — Makefile
# Comandos utilitários para desenvolvimento e deploy

.PHONY: help dev up down build logs clean test lint simulate

# ── Help ──
help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Desenvolvimento ──
dev: ## Inicia ambiente de desenvolvimento (sem OBD real)
	LOGAN_ENV=demo docker compose up --build

up: ## Inicia todos os serviços
	docker compose up -d

down: ## Para todos os serviços
	docker compose down

build: ## Rebuild dos containers
	docker compose build --no-cache

logs: ## Mostra logs em tempo real
	docker compose logs -f

logs-supervisor: ## Logs apenas do Supervisor
	docker compose logs -f supervisor

# ── Simulação ──
simulate: ## Roda simulador OBD standalone
	docker compose exec supervisor python scripts/simulate_obd.py

# ── Testes ──
test: ## Roda testes unitários
	docker compose exec supervisor python -m pytest tests/unit/ -v

test-integration: ## Roda testes de integração
	docker compose exec supervisor python -m pytest tests/integration/ -v

test-coverage: ## Roda testes com cobertura
	docker compose exec supervisor python -m pytest tests/ -v --cov=core --cov=workers --cov=drivers --cov=services --cov-report=html

# ── Qualidade ──
lint: ## Verifica código com ruff
	docker compose exec supervisor ruff check .

format: ## Formata código com ruff
	docker compose exec supervisor ruff format .

typecheck: ## Verifica tipos com mypy
	docker compose exec supervisor mypy core/ workers/ drivers/ services/

# ── Banco de Dados ──
db-init: ## Inicializa banco SQLite
	docker compose exec supervisor python -c "import sqlite3; conn = sqlite3.connect('/app/db/logan.db'); conn.executescript(open('/app/data/migrations/001_initial.sql').read()); conn.close(); print('DB inicializado')"

db-shell: ## Abre shell SQLite
	docker compose exec supervisor sqlite3 /app/db/logan.db

# ── Redis ──
redis-cli: ## Abre Redis CLI
	docker compose exec redis redis-cli

redis-monitor: ## Monitora comandos Redis em tempo real
	docker compose exec redis redis-cli monitor

# ── Limpeza ──
clean: ## Remove containers, volumes e dados temporários
	docker compose down -v
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache

clean-logs: ## Limpa logs
	docker compose exec supervisor rm -rf /app/logs/*.log

# ── Deploy ──
deploy-orangepi: ## Deploy na Orange Pi
	./scripts/deploy.sh

backup: ## Backup do banco de dados
	./scripts/backup.sh
