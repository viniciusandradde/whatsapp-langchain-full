# F2b — Motor de disparo durável

**Data:** 2026-09-03 · **Fase:** F2b do projeto Prospecção Enterprise
**Fecha:** §4.3 do relatório de Fase 0 (campanha `running` órfã) = meta **G1c**
**Antecede:** F3 (status de entrega) · **Depende de:** F2a ✅ (RLS, mig 182, em produção)

---

## 1. O que quebra hoje

Três defeitos, todos com a mesma raiz: **o motor mora no processo errado**.

### 1.1 O dispatcher roda dentro da API

`server/main.py:223` sobe `run_scheduled_poller` no lifespan da API, e
`schedule_dispatch` (`shared/campanha.py:1318`) cria a task com
`asyncio.create_task` **de dentro do handler HTTP** (`routes/campanha.py:394`,
`routes/disparador.py:264`).

A API é o processo que reinicia a cada deploy — e neste repo **merge é deploy**.
Uma campanha de 4 h atravessa quase toda janela de trabalho: qualquer merge no
meio dela mata o envio. O motor está no único processo que não pode hospedá-lo.

### 1.2 `running` é estado terminal irrecuperável

`claim_scheduled_due` (`:1335`) reivindica **só** `status='scheduled'`. Não há
lease, heartbeat nem varredura de `running`. Se a task morre — deploy, OOM,
exceção não tratada — a campanha fica `running` para sempre, os destinatários
ficam `pendente` para sempre, e não existe endpoint de retomada (o próprio
código admite o TODO em `routes/campanha.py:378`). **Só SQL manual recupera.**

### 1.3 O lote de destinatários não tem lock

```sql
SELECT cd.id, cd.telefone, ...
  FROM campanha_destinatario cd
 WHERE cd.campanha_id = %s AND cd.status = 'pendente'
 ORDER BY cd.id LIMIT 50          -- ← sem FOR UPDATE SKIP LOCKED
```

Dois motores na mesma campanha leem o mesmo lote e **enviam tudo duas vezes**.
Hoje não acontece por acidente (só uma instância da API roda o poller), mas é
justamente a garantia que a fase precisa dar — e produção já roda **dois
workers**, então no destino a corrida é real, não hipotética.

### 1.4 Consequência do §9.2: nada disso foi observado

O disparo nunca rodou com dados reais em produção (0 campanhas). Todo achado
acima vem de leitura de código. O motor tem que ser construído assumindo que o
**primeiro disparo real é também o primeiro teste real**.

---

## 2. Princípio: não inventar mecanismo

O repositório já resolveu este problema uma vez. `message_queue` é uma fila em
Postgres com `FOR UPDATE SKIP LOCKED` + lease + heartbeat + backoff, rodando no
worker, e é o pedaço mais confiável do sistema. **A F2b aplica esse padrão ao
disparador** — mesmo vocabulário, mesmo formato de claim, mesmo lugar
(`worker/main.py`, que já tem `_lease_heartbeat` em `:165` e sete loops de
fundo).

Nada de Redis, Celery ou broker novo. O ganho da fase é durabilidade, e
durabilidade aqui é uma cláusula `WHERE` a mais no claim.

---

## 3. Desenho

### 3.1 Máquina de estados

**Campanha** — hoje `draft → running → done|partial|aborted` (+ `scheduled`):

```
draft ──dispatch──► queued ──claim do worker──► running ──► done | partial
  │                    ▲                          │  ▲
  └──agendar──► scheduled ──poller──┘             │  └── paused ──retomar──┘
                    ▲                             │
                    └────── reagendar warm-up ────┘
                                                  └──► aborted (terminal)
```

Dois estados novos, cada um pagando uma dívida:

- **`queued`** — o usuário mandou disparar, nenhum worker pegou ainda. Hoje o
  `POST /dispatch` cria a task *dentro da API*; passa a só marcar `queued` e
  devolver 202. **É esta troca que torna o motor durável** — o trabalho deixa de
  depender do processo que atendeu o HTTP.
- **`paused`** — pausa real, retomável. Hoje pausar não existe: `abort_campanha`
  (`:784`) grava `aborted` + `finished_at`, e o CHECK não deixa voltar. Quem
  quer só "segura aí" perde a campanha.

`running` **não** precisa ser dividido: o lease distingue "worker vivo
trabalhando" de "abandonada", que é a ambiguidade real do §1.2.

**Destinatário** — hoje `pendente → enviado | falhou`, e o `pendente` acumula
dois significados ("na fila" e "peguei mas ainda não terminei"). Separar:

- **`enviando`** — reivindicado, em voo. Com `claimed_at` e `claimed_by`.
- **`incerto`** — chamamos o provedor e morremos antes de gravar o resultado.

### 3.2 A política do órfão (decisão de comportamento)

Quando um destinatário fica `enviando` com `claimed_at` vencido, houve crash. A
pergunta é o que fazer, e as duas saídas erradas são simétricas: **devolver pra
`pendente` pode mandar a mensagem duas vezes; marcar `incerto` pode deixar um
buraco.**

Dá pra decidir sem chutar, gravando `provider_chamado_at` imediatamente antes de
chamar o provedor:

| Situação | Leitura | Destino |
|---|---|---|
| `claimed_at` setado, `provider_chamado_at` NULL | nunca chegou no provedor | → `pendente` (reenvia, seguro) |
| ambos setados, sem resultado | pode ter saído | → `incerto` (**não** reenvia) |

**Decisão minha, sinalizada:** no caso genuinamente incerto, **não reenviar**.
Em disparo em massa a duplicata é pior que o buraco — é exatamente o sinal de
spam que queimou o número na campanha 9, e o buraco é visível e corrigível por
um reenvio manual, enquanto a duplicata já saiu. O `incerto` entra no relatório
da campanha para decisão humana. Se preferir o contrário, é uma linha.

### 3.3 O claim que fecha o §4.3

```sql
UPDATE campanha
   SET status = 'running',
       lease_owner = %s, lease_expires_at = NOW() + INTERVAL '2 minutes',
       heartbeat_at = NOW(), started_at = COALESCE(started_at, NOW())
 WHERE id IN (
    SELECT id FROM campanha
     WHERE status = 'queued'
        OR (status = 'scheduled' AND scheduled_at <= NOW())
        OR (status = 'running'  AND lease_expires_at < NOW())   -- ← a órfã
     ORDER BY COALESCE(scheduled_at, updated_at)
     FOR UPDATE SKIP LOCKED
     LIMIT 1
 )
RETURNING empresa_id, id;
```

A terceira cláusula do `WHERE` é a fase inteira: campanha cujo dono morreu volta
a ser reivindicável, e o worker que a pega continua de onde parou (os
destinatários `enviado` já estão gravados, o loop só lê `pendente`).

O heartbeat renova `lease_expires_at` enquanto o worker trabalha — mesmo
contrato do `_lease_heartbeat` do `message_queue`.

### 3.4 Claim por destinatário

```sql
UPDATE campanha_destinatario
   SET status = 'enviando', claimed_at = NOW(), claimed_by = %s
 WHERE id IN (
    SELECT id FROM campanha_destinatario
     WHERE campanha_id = %s AND status = 'pendente'
     ORDER BY id FOR UPDATE SKIP LOCKED LIMIT %s
 )
RETURNING id, telefone, cliente_id, variaveis;
```

Fecha o §1.3. Dois workers na mesma campanha passam a dividir o trabalho em vez
de duplicá-lo.

### 3.5 `campanha_evento` — trilha em vez de string

Hoje o histórico da campanha é **concatenado no campo `descricao`**
(`_mark_finished:1273`, `_reagendar_warmup:1305`): motivo de abort, nota de
warm-up e o que mais aparecer viram texto solto no campo que o usuário escreveu.
Não dá pra consultar, ordenar nem exibir.

Tabela nova, append-only, sob RLS desde o nascimento (lição da F2a):
`campanha_evento (id, campanha_id, empresa_id, tipo, payload JSONB, created_at)`.

Tipos: `criada`, `enfileirada`, `iniciada`, `pausada`, `retomada`,
`reagendada_warmup`, `conexao_fora_do_pool`, `kill_switch`, `lease_expirada`,
`retomada_apos_orfa`, `finalizada`.

`lease_expirada` + `retomada_apos_orfa` são o que torna o §4.3 **observável**
depois de corrigido — sem eles, "a campanha se recuperou sozinha" é indistinguível
de "nunca quebrou".

---

## 4. Fatiamento

Três PRs, cada um validado no dev e mostrado antes do merge (contrato do
CLAUDE.md). O primeiro já entrega o valor da fase.

| PR | Escopo | Fecha |
|---|---|---|
| **1 — Durabilidade** | migration (lease, `queued`/`paused`, `enviando`/`incerto`, `campanha_evento`); claim com lease; motor sai da API e vai pro worker; heartbeat; retomada de órfã; `POST /dispatch` vira enfileiramento | **§4.3 / G1c** |
| **2 — Controle** | pausar/retomar de verdade; endpoint de reenvio de pendentes/falhos/incertos (o TODO de `routes/campanha.py:378`); trilha de eventos na UI | dívida do §1.2 |
| **3 — Ritmo (G1a)** | concorrência N + token bucket alimentado pelo `messaging_limit` da Meta — **só WABA**. Evolution segue sequencial **de propósito** (G1b: velocidade e anti-ban são objetivos opostos) | G1a |

---

## 5. Ponto que merece ser reaberto: a flag `disparador_v2`

Em 2026-09-02 você aprovou (P1) uma feature flag por empresa, para o motor
antigo coexistir com o novo durante a migração. **A resposta do §9.2 tirou o
chão dessa decisão:** não há campanha nenhuma em produção — nem uma linha em
`campanha` ou `campanha_destinatario`. Não existe tráfego para proteger nem
migração para escalonar.

Manter os dois motores custa: dois caminhos de código para testar, o gate em
cada endpoint, e o motor velho (o que perde a campanha no restart) continuando
a existir como fallback ativável.

**Sugestão: descartar a flag e substituir o motor de uma vez.** O risco que ela
cobria é zero hoje, e o rollback continua existindo pelo caminho normal — reverter
o PR. Se você preferir manter, mantenho; é a sua chamada, só não quero implementar
uma proteção cuja premissa mudou sem avisar.

---

## 6. Riscos

1. **Worker hospedando trabalho longo.** O dispatch vira mais um loop ao lado do
   processamento de mensagens. Uma campanha não pode monopolizar o worker: o
   envio é I/O-bound e cooperativo, mas o limite de campanhas simultâneas por
   worker precisa ser explícito (proposta: 1 por worker, `LIMIT 1` no claim).
2. **Duas réplicas de worker em produção.** Passa a ser garantia testada, não
   coincidência — daí o `FOR UPDATE SKIP LOCKED` nos dois níveis.
3. **`campanha_evento` cresce sem teto.** Uma campanha de 10 mil não gera 10 mil
   eventos (eventos são de campanha, não de destinatário), mas vale índice por
   `(campanha_id, created_at DESC)` e política de retenção na F8.
4. **Migration mexe em CHECK de tabela sob RLS.** Mesmo cuidado da 182: guard,
   idempotência e validação no fim. Produção está vazia, então é barato agora —
   e só agora.
5. **Sem dado real para calibrar.** Lease de 2 min, lote de 50, heartbeat de 30 s
   são chutes informados pelo `message_queue`. O primeiro disparo real é que
   ajusta.

---

## 7. Estado

- ✅ Código do motor atual mapeado (`shared/campanha.py:914-1384`, `server/main.py:221-223`).
- ✅ Desenho fechado, fatiamento proposto.
- ⏸️ **Aguarda: decisão sobre a flag `disparador_v2` (§5).** O PR 1 começa
  independente dela — a flag só muda se o motor velho continua alcançável.
