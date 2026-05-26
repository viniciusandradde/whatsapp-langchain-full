.PHONY: help dev setup db migrate api worker frontend up down reset logs lint format format-check fix typecheck check ci test test-x test-v test-live test-media test-demo test-demo-up test-flows test-e2e report-e2e backfill-rag stress stress-evolution stress-twilio stress-both langfuse-up langfuse-down langfuse-logs langfuse-reset clean

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

ci: ## CI/CD: verifica tudo + roda testes com gate de coverage 50%
	uv run ruff check . && uv run ruff format --check . && uv run pyright src/ && uv run pytest -m "not docker_demo and not twilio_real" --cov --cov-fail-under=50

cov: ## Roda tests + relatório HTML de coverage (htmlcov/index.html)
	uv run pytest -m "not docker_demo and not twilio_real" --cov --cov-report=html --cov-report=term-missing

##@ Testes
test: ## Roda todos os testes
	uv run pytest -m "not docker_demo and not twilio_real"

test-x: ## Roda testes, para no primeiro erro
	uv run pytest -x -m "not docker_demo and not twilio_real"

test-v: ## Roda testes com output verboso
	uv run pytest -v -m "not docker_demo and not twilio_real"

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

test-e2e: ## Sprint K — bateria E2E multi-setor (28 cenários) com Allure
	uv run pytest tests/e2e/ -v -s \
	  --alluredir=tests/reports/allure-results \
	  --junitxml=tests/reports/junit-e2e.xml \
	  -m docker_demo

test-rag-eval: ## Sprint N.3 — eval RAG nos 3 modos (vector/hybrid/hybrid_hyde) com dataset golden
	uv run pytest tests/rag/test_rag_eval.py -v -s

report-e2e: test-e2e ## Gera HTML do Allure em tests/reports/allure
	@command -v allure >/dev/null 2>&1 || \
	  { echo "ERRO: allure CLI não instalado. Use 'npm i -g allure-commandline' ou baixe do site oficial."; exit 1; }
	allure generate tests/reports/allure-results \
	  -o tests/reports/allure --clean
	@echo "✅ Relatório gerado em tests/reports/allure/index.html"
	@echo "   Para servir: 'allure open tests/reports/allure'"

test-twilio-smoke: ## Smoke test e2e com Twilio real (custos $$$). Requer TWILIO_LIVE_TESTS=1 e stack Docker.
	uv run pytest tests/integration/test_twilio_smoke.py -v -s -m twilio_real

##@ RAG
backfill-rag: ## Re-chunka docs sem chunks (pós migration 018). --doc-id N força um.
	uv run python scripts/backfill_rag_chunks.py $(ARGS)

##@ Stress (Locust headless)
# Defaults: -u 10 -r 2 -t 60s contra api.vsanexus.com
# Sobrescreva via:
#   make stress-evolution USERS=20 RATE=5 TIME=120s HOST=https://outra.url
USERS  ?= 10
RATE   ?= 2
TIME   ?= 60s
HOST   ?= https://api.vsanexus.com
LOCUST  = cd stress && uv run --with locust --with faker --with python-dotenv \
          locust --headless -u $(USERS) -r $(RATE) -t $(TIME) -f locustfile.py --host $(HOST)

stress-evolution: ## Stress test do webhook Evolution (default: 10u, 2/s, 60s)
	LOCUST_PROVIDER=evolution $(LOCUST)

stress-twilio: ## Stress test do webhook Twilio (precisa TWILIO_AUTH_TOKEN)
	LOCUST_PROVIDER=twilio $(LOCUST)

stress-both: ## Stress nos dois providers ao mesmo tempo
	LOCUST_PROVIDER=both $(LOCUST)

stress: stress-evolution ## Alias do stress-evolution (default)

# Alternativa via Docker (sem precisar de uv local)
LOCUST_DOCKER = sg docker -c "docker build -q -t whatsapp-stress stress >/dev/null && \
                docker run --rm \
                -e LOCUST_PROVIDER=$$LOCUST_PROVIDER \
                -e EVOLUTION_INSTANCE_NAME=$${EVOLUTION_INSTANCE_NAME:-vsa-tecnologia} \
                -e EVOLUTION_API_KEY \
                -e TWILIO_AUTH_TOKEN \
                -e TWILIO_WEBHOOK_URL \
                whatsapp-stress \
                locust --headless -u $(USERS) -r $(RATE) -t $(TIME) -f locustfile.py --host $(HOST)"

stress-evolution-docker: ## Stress Evolution via Docker (sem uv)
	LOCUST_PROVIDER=evolution $(LOCUST_DOCKER)

stress-twilio-docker: ## Stress Twilio via Docker (precisa TWILIO_AUTH_TOKEN no env)
	LOCUST_PROVIDER=twilio $(LOCUST_DOCKER)

##@ Langfuse (observabilidade LLM self-hosted)
# Stack separada (5 serviços de infra própria). Sobe sob demanda — não
# acopla ao `make up`. Acessar em http://localhost:3001 após sobir.

langfuse-up: ## Sobe stack Langfuse (web + worker + clickhouse + redis + minio + db)
	docker compose -f docker-compose.langfuse.yml up -d
	@echo ""
	@echo "✅ Stack Langfuse iniciando — aguarde ~60s na 1ª subida (migrations + bootstrap)."
	@echo "   Painel: http://localhost:3001"
	@echo "   Health: curl http://localhost:3001/api/public/health"
	@echo ""
	@echo "Próximo passo: criar org+projeto no painel, copiar API keys pro .env."

langfuse-down: ## Para stack Langfuse (mantém volumes)
	docker compose -f docker-compose.langfuse.yml down

langfuse-logs: ## Tail logs Langfuse (web + worker)
	docker compose -f docker-compose.langfuse.yml logs -f langfuse-web langfuse-worker

langfuse-reset: ## Reset total Langfuse (DROP volumes — perde traces + projetos)
	docker compose -f docker-compose.langfuse.yml down -v
	@echo "⚠️  Volumes removidos. Próximo langfuse-up parte do zero."

##@ Limpeza
clean: ## Remove arquivos de cache do Python
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
