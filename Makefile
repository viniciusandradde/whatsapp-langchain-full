.PHONY: help dev setup db migrate api worker frontend up down reset logs lint format format-check fix typecheck check ci test test-x test-v test-live test-media test-demo test-demo-up test-flows clean

# Cores para output
CYAN := \033[36m
RESET := \033[0m

##@ Geral
help: ## Mostra esta mensagem de ajuda
	@awk 'BEGIN {FS = ":.*##"; printf "\nUso:\n  make $(CYAN)<comando>$(RESET)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(CYAN)%-15s$(RESET) %s\n", $$1, $$2 } /^##@/ { printf "\n%s\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup
setup: ## Cria .venv e instala dependências
	uv venv
	uv pip install -e ".[dev]"

##@ Desenvolvimento
dev: ## Inicia LangGraph Studio (desenvolvimento de agentes)
	uv run langgraph dev

db: ## Inicia apenas o PostgreSQL (com pgvector)
	docker compose up -d db

migrate: ## Aplica migrações pendentes no banco
	uv run python db/migrate.py

api: ## Roda a API localmente (fora do Docker)
	uv run uvicorn whatsapp_langchain.server.main:app --reload --port 8000

worker: ## Roda o Worker localmente (fora do Docker)
	uv run python -m whatsapp_langchain.worker.main

frontend: ## Admin Panel (Next.js)
	cd frontend && npm run dev

##@ Docker
up: ## Inicia todos os serviços (API + Worker + Frontend + DB)
	docker compose up -d

down: ## Para todos os serviços
	docker compose down

reset: ## Reseta stack Docker (remove containers/rede/volumes e sobe com build limpo)
	docker compose down -v --remove-orphans
	docker compose up -d --build
	docker compose ps

logs: ## Mostra logs de todos os serviços
	docker compose logs -f

##@ Qualidade de Código
# Estes comandos verificam estilo e tipos, NÃO lógica.
# Para testar lógica, use: make test
#
# Fluxo típico:
#   make fix && make format   # Corrige e formata
#   make check                # Verifica se está tudo ok
#   git commit

lint: ## Encontra problemas (imports, sintaxe) — não altera arquivos
	uv run ruff check .

format: ## Formata código — ALTERA arquivos
	uv run ruff format .

format-check: ## Verifica se está formatado — não altera (para CI)
	uv run ruff format --check .

fix: ## Corrige problemas automaticamente — ALTERA arquivos
	uv run ruff check --fix .

typecheck: ## Verifica tipos estáticos (pyright) — não altera arquivos
	uv run pyright src/

check: ## Verifica tudo (lint + format + types) — não altera arquivos
	uv run ruff check . && uv run ruff format --check . && uv run pyright src/

ci: ## CI/CD: verifica tudo + roda testes — não altera arquivos
	uv run ruff check . && uv run ruff format --check . && uv run pyright src/ && uv run pytest -m "not docker_demo"

##@ Testes
test: ## Roda todos os testes
	uv run pytest -m "not docker_demo"

test-x: ## Roda testes, para no primeiro erro
	uv run pytest -x -m "not docker_demo"

test-v: ## Roda testes com output verboso
	uv run pytest -v -m "not docker_demo"

test-live: ## Roda integracoes live com OpenRouter real (requer OPENROUTER_API_KEY valida)
	OPENROUTER_LIVE_TESTS=1 uv run pytest tests/integration/test_context_middleware.py tests/integration/test_memory.py tests/integration/test_media_real.py -v

test-media: ## Roda testes de mídia real (requer OPENROUTER_API_KEY)
	OPENROUTER_LIVE_TESTS=1 uv run pytest tests/integration/test_media_real.py -v -s

test-demo: ## Roda testes demonstrativos (requer stack Docker rodando)
	uv run pytest -m docker_demo -v

test-demo-up: ## Sobe stack Docker e roda testes demonstrativos
	docker compose up -d --build
	uv run pytest -m docker_demo -v

test-flows: ## Roda testes de fluxo realista (requer stack Docker)
	uv run pytest tests/integration/test_realistic_flows.py -v -s

##@ Limpeza
clean: ## Remove arquivos de cache do Python
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
