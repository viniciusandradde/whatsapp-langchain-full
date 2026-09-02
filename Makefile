.PHONY: dev-acesso dev-isolamento dev-banco-refresh migrar-exportar migrar-preparar migrar-importar backup backup-instalar backup-restaurar repo-comparar help dev setup db migrate api worker frontend up down reset logs lint format format-check fix typecheck check ci test test-x test-v test-live test-media test-demo test-demo-up test-flows test-e2e report-e2e backfill-rag stress stress-evolution langfuse-up langfuse-down langfuse-logs langfuse-health langfuse-reset clean

# Cores para output
CYAN := \033[36m
RESET := \033[0m

# Nome do projeto Docker. Sem isto o compose usa o nome do diretório, e um
# `make up` sobe um SEGUNDO stack nas mesmas portas do override — conflito de
# porta com o que já está no ar. Sobrescreva com: make up COMPOSE_PROJETO=outro
COMPOSE_PROJETO ?= chatnexus-dev
COMPOSE := docker compose -p $(COMPOSE_PROJETO)

##@ Geral
help: ## Mostra esta mensagem de ajuda
	@awk 'BEGIN {FS = ":.*##"; printf "\nUso:\n  make $(CYAN)<comando>$(RESET)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2 } /^##@/ { printf "\n%s\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup
setup: ## Cria .venv e instala dependências
	uv venv
	uv pip install -e ".[dev]"

##@ Desenvolvimento
dev: ## Inicia LangGraph Studio (desenvolvimento de agentes)
	uv run langgraph dev

db: ## Inicia apenas o PostgreSQL (com pgvector)
	$(COMPOSE) up -d db

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
	$(COMPOSE) up -d

down: ## Para todos os serviços
	$(COMPOSE) down

reset: ## Reseta stack Docker (remove containers/rede/volumes e sobe com build limpo)
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up -d --build
	$(COMPOSE) ps

logs: ## Mostra logs de todos os serviços
	$(COMPOSE) logs -f

##@ Ambiente de desenvolvimento
# O ambiente vive na máquina Ubuntu, isolado da produção. Ver docs/MIGRACAO_DEV.md.
IP_LAN := $(shell ip route get 1.1.1.1 2>/dev/null | awk '{print $$7; exit}')

dev-acesso: ## Mostra URLs, login e o estado dos serviços do ambiente de dev
	@echo "  painel   http://$(IP_LAN):3100    login admin@dev.local"
	@echo "  API      http://$(IP_LAN):8081"
	@echo "  banco    postgresql://postgres:postgres@localhost:5434/whatsapp_langchain"
	@echo ""
	@$(COMPOSE) ps --format "  {{.Service}}\t{{.Status}}" 2>/dev/null || true

dev-isolamento: ## Confere as travas que impedem o dev de falar com a produção
	@falhou=0; \
	for trava in EVOLUTION_OUTBOUND_MODE=mock \
	             LANGFUSE_ENABLED=false ENVIRONMENT=development; do \
	  if grep -qE "^$$trava$$" .env; then echo "  ok     $$trava"; \
	  else echo "  FALHOU $$trava"; falhou=1; fi; \
	done; \
	if grep -qE '^DATABASE_URL=.*(vsanexus|100\.67\.148\.26|@db:)' .env; then \
	  echo "  FALHOU DATABASE_URL aponta pra fora"; falhou=1; \
	else echo "  ok     DATABASE_URL é local"; fi; \
	exit $$falhou

dev-banco-refresh: ## Restaura um dump saneado novo no banco de dev (DUMP=/caminho/dev.dump)
	@test -n "$(DUMP)" || { echo "uso: make dev-banco-refresh DUMP=/caminho/dev.dump"; exit 1; }
	$(COMPOSE) exec -T db pg_restore -U postgres -d whatsapp_langchain \
	  --no-owner --no-acl --clean --if-exists < "$(DUMP)"

##@ Migração e backup
# Ver docs/MIGRACAO_DEV.md para o roteiro completo e o contrato de isolamento.
# Ver docs/BACKUP.md para as três cópias e o setup da cópia externa (rclone).
migrar-exportar: ## Monta o pacote de migração — roda no VPS, só lê (SAIDA=/tmp/...)
	scripts/migrar-dev/00-exportar.sh $(SAIDA)

migrar-preparar: ## Instala o que a máquina de desenvolvimento precisa (Docker, uv, Node 22)
	scripts/migrar-dev/01-preparar-maquina.sh

migrar-importar: ## Importa o pacote e sobe o ambiente (ORIGEM=vps-docker03:/tmp/chatnexus-migracao)
	@test -n "$(ORIGEM)" || { echo "uso: make migrar-importar ORIGEM=host:/caminho"; exit 1; }
	scripts/migrar-dev/02-importar.sh "$(ORIGEM)"

backup: ## Backup da produção agora (pg_dump -Fc comprimido em /home/dev/backup)
	scripts/backup_prod.sh

backup-instalar: ## Instala o timer systemd do backup diário (precisa sudo)
	sudo scripts/backup_prod.sh --instalar

backup-restaurar: ## Restaura um backup numa base NOVA, nunca por cima (ARQ=/home/dev/backup/...)
	@test -n "$(ARQ)" || { echo "uso: make backup-restaurar ARQ=/home/dev/backup/prod-AAAA-MM-DD.dump.zst"; exit 1; }
	scripts/backup_prod.sh --restaurar "$(ARQ)"

repo-comparar: ## Prova por LISTA que nenhum commit ficou só na outra cópia (OUTRO=/caminho)
	@test -n "$(OUTRO)" || { echo "uso: make repo-comparar OUTRO=/home/dev/projetos/chatnexus"; exit 1; }
	@git log --all --oneline | sort > /tmp/repo-aqui.txt; \
	git -C "$(OUTRO)" log --all --oneline | sort > /tmp/repo-outro.txt; \
	if comm -23 /tmp/repo-outro.txt /tmp/repo-aqui.txt | grep -q .; then \
	  echo "  commits que existem SÓ em $(OUTRO) — não apague ainda:"; \
	  comm -23 /tmp/repo-outro.txt /tmp/repo-aqui.txt | sed 's/^/    /'; exit 1; \
	else echo "  ok     nada exclusivo em $(OUTRO)"; \
	  echo "  lembre: .env, docker-compose.override.yml e as capturas do benchmark"; \
	  echo "          estão no .gitignore e NÃO aparecem nesta comparação"; fi

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

check-web: ## Verifica o frontend (eslint + tsc + build + métricas de UI)
#  Até 2026-07-30 NADA validava o frontend: `make check` roda só Python, e a
#  única checagem real era o `next build` dentro do docker build do deploy —
#  em arm64 emulado, depois do push. Este alvo é o gate que faltava (ADR-013).
#  O INTERNAL_API_URL é obrigatório no build porque o rewrite de /uploads
#  congela a destination no route-manifest em build time.
	cd frontend && npm run lint && npm run typecheck
	cd frontend && INTERNAL_API_URL=$${INTERNAL_API_URL:-http://api:8000} npm run build
	bash scripts/ui_metrics.sh --check

ci: ## CI/CD: verifica tudo + roda testes com gate de coverage 50%
	uv run ruff check . && uv run ruff format --check . && uv run pyright src/ && uv run pytest -m "not docker_demo" --cov --cov-fail-under=50

cov: ## Roda tests + relatório HTML de coverage (htmlcov/index.html)
	uv run pytest -m "not docker_demo" --cov --cov-report=html --cov-report=term-missing

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
	$(COMPOSE) up -d --build
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

stress-both: ## Stress nos dois providers ao mesmo tempo
	LOCUST_PROVIDER=both $(LOCUST)

stress: stress-evolution ## Alias do stress-evolution (default)

# Alternativa via Docker (sem precisar de uv local)
LOCUST_DOCKER = sg docker -c "docker build -q -t whatsapp-stress stress >/dev/null && \
                docker run --rm \
                -e LOCUST_PROVIDER=$$LOCUST_PROVIDER \
                -e EVOLUTION_INSTANCE_NAME=$${EVOLUTION_INSTANCE_NAME:-vsa-tecnologia} \
                -e EVOLUTION_API_KEY \
                whatsapp-stress \
                locust --headless -u $(USERS) -r $(RATE) -t $(TIME) -f locustfile.py --host $(HOST)"

stress-evolution-docker: ## Stress Evolution via Docker (sem uv)
	LOCUST_PROVIDER=evolution $(LOCUST_DOCKER)

##@ Langfuse (observabilidade LLM self-hosted)
# Stack separada (5 serviços de infra própria). Sobe sob demanda — não
# acopla ao `make up`. Acessar em http://localhost:3001 após sobir.

langfuse-up: ## Sobe stack Langfuse (web + worker + clickhouse + redis + minio + db)
	docker compose -f docker-compose.langfuse.yml up -d
	@echo ""
	@echo "✅ Stack Langfuse iniciando — aguarde ~60s na 1ª subida (migrations + bootstrap)."
	@echo ""
	@echo "Compose NÃO publica porta no host (evita conflito multi-projeto)."
	@echo "Pra acessar o painel em DEV local, opções:"
	@echo "  1) Traefik local com Domain langfuse.localhost → langfuse-web:3000"
	@echo "  2) Bind ad-hoc temporário:"
	@echo "       docker run --rm -d --name lf-proxy --network langfuse_net \\"
	@echo "         -p 3001:3000 alpine/socat tcp-listen:3000,fork tcp:langfuse-web:3000"
	@echo "     Acessar: http://localhost:3001"
	@echo "  3) Em Dokploy: configurar Domain no service (Traefik roteia)."
	@echo ""
	@echo "Health interno: make langfuse-health"

langfuse-down: ## Para stack Langfuse (mantém volumes)
	docker compose -f docker-compose.langfuse.yml down

langfuse-logs: ## Tail logs Langfuse (web + worker)
	docker compose -f docker-compose.langfuse.yml logs -f langfuse-web langfuse-worker

langfuse-health: ## Bate no /api/public/health dentro da rede do compose
	docker compose -f docker-compose.langfuse.yml exec langfuse-web \
	  sh -c 'wget -qO- http://$$HOSTNAME:3000/api/public/health' && echo ""

langfuse-reset: ## Reset total Langfuse (DROP volumes — perde traces + projetos)
	docker compose -f docker-compose.langfuse.yml down -v
	@echo "⚠️  Volumes removidos. Próximo langfuse-up parte do zero."

##@ Limpeza
clean: ## Remove arquivos de cache do Python
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
