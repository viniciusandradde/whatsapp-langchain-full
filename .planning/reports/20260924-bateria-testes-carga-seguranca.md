# Bateria de testes — carga, segurança e volume (24/09/2026)

Sistema ChatNexus, com você como único usuário conectado. Conduzido como teste
de qualidade e confiabilidade do próprio sistema: medir capacidade e confirmar
que as proteções existentes (isolamento entre empresas, autenticação,
assinatura de webhook, limites) seguem funcionando. Sem técnicas ofensivas.

## Ambientes

| | Dev | Produção |
|---|---|---|
| Envio ao WhatsApp | simulado (mock) — risco zero | real |
| Worker | concorrência 4 × 1 réplica = 4 slots | concorrência 4 × 2 réplicas = **8 slots** |
| Servidor | — | 4 CPU / 11 GB, ~ocioso no teste |
| Onde rodou a carga pesada | aqui | só carga leve isolada + verificações |

## 1. Capacidade e volume de conversas simultâneas

### Borda do webhook (aceitar e enfileirar) — Locust, dev
30 usuários por 60 s no `/webhook/evolution`:
- **p50 11 ms, p95 24 ms, p99 120 ms**, máx 260 ms.
- Tarefa "normal" (números variados): **0% de falha**.
- Tarefa "rajada" (mesmo número em loop): 429 — é a **proteção por telefone**
  funcionando (30/h no dev; 5.000/h em produção). Não é erro.
- A borda não satura: com p50 de 11 ms, uma instância aguenta ~90 req/s. O
  gargalo não é aceitar a mensagem.

### Worker com IA real — dev, 4 slots
200 conversas distintas injetadas pelo caminho real (mesmas funções do webhook),
agente `google/gemini-3.1-flash-lite`:
- Injeção (borda): **200 em 1,3 s**.
- Dreno pela IA: **200 em 135 s, 0 falhas, 0 erros 429**, dreno linear.
- **~22 turnos de IA por minuto por slot** (~2,7 s por turno, incluindo
  carregar contexto, montar ferramentas e chamar o modelo).
- Memória do worker estável em ~174 MB (teto de 512 MB por réplica).

### Extrapolação para produção (8 slots)
- **~178 turnos de IA por minuto** (~10.700/hora), limitado na prática pela
  latência e pelo limite do provedor de IA, não pelo servidor.
- A fila é durável (Postgres): um pico de centenas de conversas simultâneas é
  **aceito quase de imediato e não se perde**; o que regula é a velocidade de
  dreno, não a de aceitação.
- CPU e memória sobraram folgadas o tempo todo.

**Conclusão de capacidade:** para a operação atual (poucos clientes), há muita
folga. O primeiro limite a aparecer, ao crescer, será o **provedor de IA**
(latência/limite por chamada), não a API, o worker nem o banco.

## 2. Isolamento entre empresas e proteções

### Isolamento — produção (2 empresas de teste, apagadas ao fim): 7/7
- Empresa A vê o próprio cliente; **empresa B não vê o de A na lista**.
- B **não lê, não altera e não classifica** o cliente de A (404).
- B **forjando o cabeçalho de empresa = A** é barrado (403).
- Sem token de serviço → 401.

### Proteções — produção passiva: 11/12
- Cabeçalhos `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, **HSTS** presentes.
- `/webhook/sync` **desligado em produção** (404).
- `/docs` e `/openapi.json` **não expostos** (404).
- Webhook WABA sem assinatura ou com assinatura inválida → **recusado**
  (`rejected_no_signature`), não processa.
- Webhook Evolution sem apikey → **401**.
- Certificado TLS válido (expira em **54 dias**, 18/11/2026).
- Isolamento idêntico também validado no dev (14/16; as 2 "falhas" eram do
  próprio teste, não do sistema).

### Limite de requisição por usuário
600/min por usuário em produção (visto no incidente de hoje, em que uma aba
antiga gerou ~900/min e foi barrada — a causa do loop já foi corrigida no #188).

## 3. Telas (Playwright, dev)
Abriram limpas, sem tela de erro: Atendimento, Clientes, Conexões, Agentes,
Campanhas, Usuários, Empresas, Dashboard de IA, Dashboard de Qualidade,
Modelos, Base de Conhecimento, Dashboard de Atendimento (renderiza em ~4,3 s).

## Achados e melhorias

| # | Gravidade | Achado | Recomendação |
|---|---|---|---|
| 1 | Baixa/Média | `/metrics` público expõe métricas internas (versão do Python, memória, caminhos e volume de requisições por endpoint). Sem credenciais. | Proteger com token ou expor só na rede interna. |
| 2 | Baixa | `/dashboard/atendimento` gera um aviso de hidratação do React (#418) — texto que o servidor e o navegador renderizam diferente (provável data/fuso). Não quebra a tela. | Ajustar o campo que difere (renderizar a data só no cliente). |
| 3 | Muito baixa | `/dashboard` puro dá 404 (só existem as subpáginas). | Redirecionar `/dashboard` → `/dashboard/atendimento`. |
| 4 | Info | Certificado TLS expira em 54 dias. | Confirmar que a renovação é automática. |

**Nenhum achado de alto risco.** O isolamento entre empresas, a autenticação, a
assinatura de webhook e os cabeçalhos de segurança estão sólidos.

## O que NÃO foi testado (e por quê)
- Carga pesada direto em produção: por decisão, só carga leve e isolada, para
  não pesar no atendimento real.
- Volume alto de IA (>1.000): a IA real ficou limitada a ~200 conversas para
  segurar o custo (medido ~US$ 0,011 por atendimento).
- Envio real ao WhatsApp sob carga: seria enviar a números reais; o caminho de
  envio da API oficial já está coberto pela suíte de entrega (mig 203).

## Limpeza
Empresas e usuários de teste apagados em produção (0 restantes) e no dev.
