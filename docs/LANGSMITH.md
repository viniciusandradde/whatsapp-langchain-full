# LangSmith — Datasets + Avaliação Sistemática (Sprint T)

Guia passo-a-passo para usar LangSmith no Nexus Chat AI: criar datasets a partir
dos atendimentos reais, rodar avaliações com LLM-as-judge e iterar prompts.

---

## 1. O que é LangSmith

[LangSmith](https://smith.langchain.com) é a plataforma da LangChain para
observabilidade, datasets e avaliação de aplicações LLM. Permite:

- **Trace** — visualizar cada chamada do agente (já temos via `/api/traces`)
- **Datasets** — coleções de exemplos input/output pra testar regressão
- **Experiments** — comparar versões do agente contra o mesmo dataset
- **Evaluators** — funções (heurísticas ou LLM-as-judge) que pontuam respostas
- **A/B testing** — mesmo dataset × 2 prompts, ver qual ganha

Docs oficiais: <https://docs.smith.langchain.com>

---

## 2. Setup

### 2.1 Criar conta + API key

1. Acesse <https://smith.langchain.com> e cadastre-se (free tier: 5.000 traces/mês)
2. Settings → API Keys → "Create API Key" → copie (`ls_...`)
3. Crie um Project (ex: `nexus-chat-ai-prod`) — workspace pra agrupar runs

### 2.2 Configurar env

No `.env` (local) ou no painel Dokploy (prod):

```bash
LANGCHAIN_API_KEY=ls_seu_token_aqui
LANGCHAIN_PROJECT=nexus-chat-ai-prod
LANGSMITH_TRACING=true   # opcional — liga tracing automático em LangChain
```

A integração é **gracefully degraded**: sem essas vars, `/api/traces` e os
endpoints `/langsmith/*` retornam 503 mas o resto do sistema funciona normal.

### 2.3 Verificação

```bash
python -c "
from langsmith import Client
import os
c = Client(api_key=os.environ['LANGCHAIN_API_KEY'])
runs = list(c.list_runs(limit=1))
print('OK' if runs else 'API key OK mas sem runs ainda')
"
```

---

## 3. Sincronizar dataset (3 caminhos)

### 3.1 Via UI (recomendado)

1. Acesse `/dashboard/rag/sandbox` no painel admin
2. Card "🔬 LangSmith Eval" — toggle "Apenas success" se quiser só os curados
3. Click "Sincronizar dataset" — leva ~30-60s pros 9k registros
4. Resultado: "9055 novos / 0 já presentes / total 9055" + botão "Abrir no LangSmith"

### 3.2 Via API

```bash
curl -X POST -H "Authorization: Bearer $INTERNAL_SERVICE_TOKEN" \
  "https://chat.vsanexus.com/api/admin/rag/langsmith/sync?empresa_id=999&filter_success=false"
```

Resposta:
```json
{
  "dataset_id": "abc123-...",
  "dataset_url": "https://smith.langchain.com/datasets/abc123-...",
  "total_db": 9055,
  "already_synced": 0,
  "created": 9055,
  "errors": []
}
```

### 3.3 Via CLI

```bash
# Dry run primeiro pra confirmar
LANGCHAIN_API_KEY=ls_... python scripts/sync_dataset_to_langsmith.py \
    --empresa-id 999 --dry-run

# Sync completo
LANGCHAIN_API_KEY=ls_... python scripts/sync_dataset_to_langsmith.py \
    --empresa-id 999

# Só os curados (outcome=success)
LANGCHAIN_API_KEY=ls_... python scripts/sync_dataset_to_langsmith.py \
    --empresa-id 999 --filter-success
```

### 3.4 Schema gerado no LangSmith

Cada exemplo no dataset tem:

```python
{
  "inputs": {
    "cliente_msg": "como agendar uma consulta?",
    "setor": "agendamentos",
    "agente_slug": "agendamentos"
  },
  "outputs": {
    "agente_resposta_esperada": "Para agendar..."
  },
  "metadata": {
    "fewshot_id": 1234,
    "outcome": "success",
    "csat_nota": 5,
    "source": "sandbox_999",
    "imported_at": "2026-05-09T..."
  }
}
```

**Idempotência**: re-runs filtram via `metadata.fewshot_id` — só inserem novos.
A tabela `fewshot_example` no PostgreSQL continua sendo a fonte de verdade.

---

## 4. Rodar avaliação

### 4.1 Conceito

Uma avaliação tem 3 partes:

1. **Target function** — o que avaliar (nosso agente). Recebe `inputs`, retorna `outputs`.
2. **Dataset** — exemplos contra os quais rodar (já criado no passo 3)
3. **Evaluators** — funções que pontuam: comparam `target output` vs `expected output`

LangSmith roda o target em paralelo contra cada exemplo, aplica os evaluators,
e cria um "experiment" (snapshot agregado) que aparece na UI.

### 4.2 Eval default — LLM-as-judge correctness

```bash
# Custo aprox: $0.001/exemplo × 50 = $0.05
LANGCHAIN_API_KEY=ls_... OPENROUTER_API_KEY=sk-or-v1-... \
    python scripts/eval_langsmith.py --limit 50
```

Output:
```
=== RESULT ===
experiment_name: atendimento-20260509-1430-abc123
URL: https://smith.langchain.com/datasets/.../experiments/...

Abra no LangSmith pra ver scores por exemplo.
```

### 4.3 Custom evaluators

Pra criar um evaluator próprio, edite `scripts/eval_langsmith.py`:

```python
def relevance_evaluator(run, example) -> dict:
    """Score de relevância — quão relacionada é a resposta à pergunta."""
    actual = run.outputs.get("agente_resposta", "")
    cliente_msg = example.inputs.get("cliente_msg", "")
    # Heurística simples: tem palavras-chave do cliente?
    tokens_msg = set(cliente_msg.lower().split())
    tokens_resp = set(actual.lower().split())
    overlap = len(tokens_msg & tokens_resp) / max(len(tokens_msg), 1)
    return {"key": "relevance", "score": overlap}
```

Adicione na lista `evaluators=[correctness_evaluator, relevance_evaluator]`.

### 4.4 Built-in evaluators (openevals)

```python
from openevals.llm import create_llm_as_judge
from openevals.prompts import (
    CORRECTNESS_PROMPT,
    HALLUCINATION_PROMPT,
    CONCISENESS_PROMPT,
)

# Correctness — bate com expected?
judge_correct = create_llm_as_judge(
    prompt=CORRECTNESS_PROMPT, model="openai:gpt-4o-mini",
)

# Hallucination — inventou fatos?
judge_hallucinate = create_llm_as_judge(
    prompt=HALLUCINATION_PROMPT, model="openai:gpt-4o-mini",
)
```

---

## 5. Ler resultados

### 5.1 Dataset view

`https://smith.langchain.com/datasets/{dataset_id}`:
- Aba "Examples" — lista paginada com inputs/outputs/metadata (50 por página)
- Aba "Experiments" — todas as runs já feitas contra esse dataset
- Filtros: por metadata (ex: `setor:agendamentos`)

### 5.2 Experiment view

Cada experiment mostra:
- **Score agregado** por evaluator (média + distribuição)
- **Tabela** exemplo a exemplo: input → expected → actual → score
- **Diff** vs experimento anterior (regressão automática)

### 5.3 Compare experiments

Útil pra A/B test. Selecione 2+ experiments → "Compare":
- Side-by-side por exemplo
- Stats: ganho/perda/neutro
- Filter: só onde scores divergem

---

## 6. Workflow recomendado

### 6.1 Iteração de prompt (ciclo de melhoria)

```
1. Sync dataset (1x) ─┐
                      │
2. Rode eval baseline │
   ↓                  │
3. Anote score atual  │
   (ex: correctness 0.65)
   ↓                  │
4. Edita prompt       │
   atendimento_completo
   ↓                  │
5. Rode eval V2       │
   ↓                  │
6. Compare V1 vs V2 ◄─┘
   ↓
7. Se ganho → deploy
   Se perda → rollback
```

### 6.2 Regression check pre-deploy

Adicione no GitHub Actions ou script de deploy:

```bash
# .github/workflows/pre-deploy.yml ou Makefile
python scripts/eval_langsmith.py --limit 30 --experiment-prefix pre-deploy-$(git rev-parse --short HEAD)
# Falha se score cai > 5% vs baseline (script futuro)
```

### 6.3 A/B test em produção

- Sync dataset uma vez
- Rode eval com prompt V1 → save experiment "prompt-v1"
- Mude env `OPENROUTER_MODEL` → rode com V2 → save "prompt-v2-grok"
- LangSmith Compare mostra qual ganhou

---

## 7. Custos

### Free tier (gratis)

- **5.000 traces/mês**
- **5.000 examples/dataset** (sem limite hard, mas rate limit 50k events/h)
- API rate: 2.000 req/min

### LLM-as-judge

- gpt-4o-mini ≈ **$0.001/exemplo** (input ~500 tokens + output ~50)
- Run típico de 50 exemplos = **$0.05**
- Run de 100 = **$0.10**

### Recomendação

- Use `--limit 50` por default (custo $0.05)
- Eval semanal (~$0.20/mês)
- Free tier cobre uso normal

---

## 8. API Reference rápida

### Criar dataset

```python
from langsmith import Client

client = Client()
dataset = client.create_dataset(
    dataset_name="meu-dataset",
    description="QA pairs do hospital",
)
```

### Bulk add examples

```python
client.create_examples(
    dataset_id=dataset.id,
    examples=[
        {
            "inputs": {"q": "..."},
            "outputs": {"a": "..."},
            "metadata": {"source": "..."},
        }
        for ... in ...
    ],
)
```

### Run evaluation

```python
from langsmith import evaluate

results = evaluate(
    target_fn,
    data="meu-dataset",
    evaluators=[my_evaluator],
    experiment_prefix="run-v1",
    max_concurrency=4,
)
```

### List existing examples (idempotência)

```python
existing = {
    ex.metadata.get("fewshot_id")
    for ex in client.list_examples(dataset_id=dataset.id)
}
```

---

## 9. Troubleshooting

| Erro | Causa | Solução |
|---|---|---|
| `401 Unauthorized` | API key inválida ou expirada | Regenere em smith.langchain.com → Settings → API Keys |
| `503 Service Unavailable` no `/langsmith/sync` | `LANGCHAIN_API_KEY` ausente no env | Configure no Dokploy/`.env` |
| `429 Too Many Requests` | Rate limit (2k req/min) | Reduza `--batch` ou `--max-concurrency` |
| `Dataset already exists` | Re-rodando script | Sem problema — script é idempotente, só insere novos |
| Empty results no experiment | Target falhou com exception | Veja logs no terminal; check `OPENROUTER_API_KEY` |
| Score `null` | Evaluator deu erro | LangSmith UI mostra exception no exemplo |
| 100% score 1.0 | Evaluator pode ter bug (ex: comparação errada) | Inspecione 1 example → "View run" → confira input/output |

---

## 10. Próximos passos opcionais

- **Captura automática**: criar webhook que adiciona ao dataset todo atendimento com `outcome=success` no prod (atualizar `shared/fewshot.py`)
- **Eval scheduled**: cron rodando `eval_langsmith.py` nightly + alerta se score cai
- **Promote dataset → prod**: depois de validar V2 wins, promover docs aprovados pra empresa 1
- **Multi-evaluator**: adicionar relevance + tom + hallucination + safety
- **Custom dashboards**: LangSmith permite charts customizados via API
