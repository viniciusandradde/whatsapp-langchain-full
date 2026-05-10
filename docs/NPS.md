# Módulo NPS / Pesquisa de Satisfação

Captura automática de NPS (Net Promoter Score 0-10) ao fechar atendimentos
no WhatsApp, com dashboard executivo, ranking de operadores e breakdown por
departamento. Padrão de mercado (estilo ZigChat).

Status: **production** (Sprint X + Y).

## Visão geral do fluxo

```
Operador clica "Resolver"        Cliente envia número 0-10        Cliente envia texto
no painel /atendimento           via WhatsApp (≤ 24h)             como comentário (≤ 60s)
        │                                  │                              │
        ▼                                  ▼                              ▼
POST /atendimentos/{id}/close   _try_capture_avaliacao         _try_capture_avaliacao
trigger_csat_se_ativo()         (no início do worker)          (mesmo handler)
        │                                  │                              │
        ▼                                  ▼                              ▼
Bot envia pergunta NPS 0-10     INSERT atendimento_avaliacao   UPDATE comentario
+ set aguardando_avaliacao_at   + set aguardando_comentario_at + clear flags
                                + bot pergunta comentário      + bot agradece
```

A coluna `atendimento.aguardando_avaliacao_at` (janela 24h) e
`aguardando_comentario_at` (janela 60s) controlam se o worker intercepta a
próxima mensagem do cliente como nota/comentário ou deixa cair no fluxo
normal (agente IA / menu).

## Configuração por empresa

A pesquisa NPS é controlada por 4 colunas em `empresa` (migration 074):

| Coluna | Tipo | Default | Descrição |
|---|---|---|---|
| `csat_ativo` | bool | `false` | Liga/desliga o envio automático |
| `csat_pergunta` | text | `null` | Texto enviado ao cliente. Vazio = "Como você avalia o atendimento que acabou de receber?" |
| `csat_msg_agradecimento` | text | `null` | Resposta após nota/comentário. Vazio = "Obrigado pelo seu feedback! 😊" |
| `csat_solicita_comentario` | bool | `true` | Se pede comentário follow-up após a nota |

UI de configuração: `/companies` → Editar empresa → seção
**"Pesquisa de Satisfação (NPS)"** abaixo do form da empresa.

Endpoints REST:

```bash
# Ler config
GET  /api/empresas/{id}/csat
# Atualizar (só admin local ou superadmin)
PUT  /api/empresas/{id}/csat
{
  "csat_ativo": true,
  "csat_pergunta": "Avalie nosso atendimento",
  "csat_msg_agradecimento": "Obrigado!",
  "csat_solicita_comentario": true
}
```

## Captura

`shared/avaliacao.py` centraliza a lógica:

| Função | Responsabilidade |
|---|---|
| `parse_nota(text)` | Extrai inteiro 0-10 de texto livre via regex |
| `classify_nota(n)` | NPS clássico: 9-10 promotor, 7-8 neutro, 0-6 detrator |
| `save_avaliacao(...)` | UPSERT em `atendimento_avaliacao` (1:1 com atendimento) |
| `find_aguardando_avaliacao(...)` | Resolve atendimento na janela de captura |
| `set_aguardando_avaliacao` / `set_aguardando_comentario` / `clear_flags` | Manipula as flags |
| `trigger_csat_se_ativo(pool, empresa_id, atendimento_id)` | Ler config + enviar pergunta + setar flag (best-effort) |

A pergunta sempre adiciona `"\n\nResponda com um número de *0* a *10*."` —
escala fixa pra padronizar o cálculo NPS (não tem sentido empresa por
empresa usar escalas diferentes).

### Onde `trigger_csat_se_ativo` é chamado

1. **Painel** (`POST /api/atendimentos/{id}/close` quando
   `status='resolvido'`) — endpoint chama diretamente após `dispatch_event`.
2. **Worker** (cliente digita "encerrar atendimento" via WhatsApp) —
   `_send_csat_se_configurado` resolve atendimento pelo `phone_number` e
   delega.

Status `'abandonado'` **não** dispara CSAT (cliente desistiu — não faz
sentido pedir nota).

### Captura da resposta

`worker/processor.py::_try_capture_avaliacao` roda no início de
`process_message`, **antes** de menu/agente IA:

1. Resolve `cliente_id` pelo telefone (early-return se não há cliente
   cadastrado).
2. `find_aguardando_avaliacao` checa flags `aguardando_*_at` na janela.
3. Se aguardando comentário (≤ 60s) e mensagem é texto livre: salva
   comentário, agradece, `mark_done` + return True.
4. Se aguardando avaliação (≤ 24h) e mensagem casa com `parse_nota`:
   salva nota, define flag de comentário (se config), responde, `mark_done`
   + return True.
5. Se mensagem não casa com nenhum dos dois: return False (deixa cair no
   fluxo normal — não desperdiça a flag).

A captura **respeita `csat_solicita_comentario`**: se `false`, após salvar
a nota o bot envia direto a mensagem de agradecimento e limpa as flags.

## Schema

`db/migrations/073_atendimento_avaliacao.sql`:

```sql
CREATE TABLE atendimento_avaliacao (
  id SERIAL PRIMARY KEY,
  atendimento_id BIGINT NOT NULL UNIQUE
      REFERENCES atendimento(id) ON DELETE CASCADE,
  empresa_id BIGINT NOT NULL,
  cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
  departamento_id INT REFERENCES departamento(id) ON DELETE SET NULL,
  -- snapshot do operador no momento do close
  assigned_to_user_id TEXT,
  nota SMALLINT NOT NULL CHECK (nota BETWEEN 0 AND 10),
  comentario TEXT,
  categoria TEXT NOT NULL CHECK (categoria IN ('promotor','neutro','detrator')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE atendimento
  ADD COLUMN aguardando_avaliacao_at TIMESTAMPTZ,
  ADD COLUMN aguardando_comentario_at TIMESTAMPTZ;
```

Indexes em `(empresa_id, created_at DESC)`, `(departamento_id, created_at DESC)`,
`(assigned_to_user_id, created_at DESC)`.

`UNIQUE (atendimento_id)` impede dupla avaliação. UPSERT garante que se a
nota chegar e depois o comentário, ambos persistem na mesma row.

`departamento_id` e `assigned_to_user_id` são **snapshots** do estado do
atendimento no momento do INSERT — preservam o ranking mesmo se o
atendimento for transferido depois (raro, mas possível).

## Relatórios

4 endpoints em `/api/relatorios/nps` (auth via `verify_service_token`,
escopados pela empresa ativa via `get_empresa_context`):

| Endpoint | Retorna |
|---|---|
| `GET /api/relatorios/nps?periodo=30` | Score geral + breakdown promotor/neutro/detrator + CSAT médio + série diária |
| `GET /api/relatorios/nps/por-departamento?periodo=30` | Lista por depto (ORDER BY score DESC) |
| `GET /api/relatorios/nps/ranking-operadores?periodo=30` | Lista por operador com avaliações_total + score + CSAT |
| `GET /api/relatorios/nps/avaliacoes?periodo=30&categoria=detrator&pagina=1` | Lista paginada de avaliações com comentários |

Cálculo NPS clássico:

```sql
ROUND((
    100.0 * COUNT(*) FILTER (WHERE categoria='promotor') / NULLIF(COUNT(*), 0)
  - 100.0 * COUNT(*) FILTER (WHERE categoria='detrator') / NULLIF(COUNT(*), 0)
)::numeric, 1)
```

`NULLIF(COUNT, 0)` retorna NULL no score quando ainda não há avaliações
no período (evita divisão por zero e o frontend mostra "—").

## Dashboard

`/dashboard/qualidade` (server component em
`frontend/src/app/dashboard/qualidade/page.tsx`):

- 4 cards superiores: NPS Score (com cor por faixa), Total avaliações,
  %Promotores, %Detratores
- Tabela "Por departamento" — Avaliações, NPS, CSAT, Promot./Detrat.
- Tabela "Ranking operadores" — colunas equivalentes, JOIN com
  `auth.user` pra nome/avatar
- Lista "Avaliações com comentário" — filtro por categoria
  (default detrator), paginação de 20 por página, mostra protocolo +
  cliente + depto + atendente
- Filtro `?periodo=7|30|90` no header

Acessível pelo menu **Observabilidade → NPS / Qualidade**.

## Como ativar

1. Login no painel como admin da empresa
2. `/companies` → Editar empresa
3. Section "Pesquisa de Satisfação (NPS)" → marcar **Ativar pesquisa NPS**
4. (Opcional) personalizar pergunta + agradecimento
5. Salvar config NPS

A partir desse momento, qualquer **Resolver** no painel
(`POST /atendimentos/{id}/close` com `status=resolvido`) dispara a pergunta
automaticamente. Resultados começam a aparecer em
`/dashboard/qualidade` conforme clientes respondem.

## Limitações conhecidas

- Sem migração de dados históricos: NPS começa do zero a partir do deploy.
- Cliente pode ignorar a pesquisa — não há retry/lembrete (próximas
  mensagens do cliente cancelam silenciosamente a janela quando vence).
- Edição/deleção de avaliação é manual via SQL (sem UI).
- Sem evento de hook `atendimento.avaliado` ainda — adicionar se algum
  consumidor externo precisar reagir a feedback.

## Não-objetivos (decisões fixadas)

- ❌ Múltiplas escalas por empresa (escala fixa 0-10)
- ❌ Edição inline de avaliação no painel (read-only no dashboard)
- ❌ Cron de cleanup das flags `aguardando_*_at` — janelas se invalidam
  por timestamp na próxima checagem
