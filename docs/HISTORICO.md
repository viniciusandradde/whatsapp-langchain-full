# Módulo Histórico de Atendimentos (aba "Conversas")

Consulta, filtragem, detalhe e exportação de **todos** os atendimentos da
empresa — abertos e finalizados (`aguardando`, `em_andamento`, `resolvido`,
`abandonado`). Substitui a antiga aba "Conversas" (`/chats`, que só listava a
tabela legada `conversations`). Construído como **paridade + superação** do
módulo de Histórico/Conversas do ZigChat.

Status: **production** (Fase 1). Fase 2 (relatórios/analytics) — roadmap no fim.

> Diferença pro painel ao vivo (`/atendimento`): aquele usa
> `atendimento.list_atendimentos` (só status abertos, via `tipo`). O histórico
> usa `shared/historico.py::list_atendimentos_historico`, que varre o conjunto
> completo com período + filtros + paginação.

## Endpoints (`/api/historico`)

Todos exigem service token (`verify_service_token`) + RBAC `atendimento.read`
(`.own` filtra por departamento do operador; `.all` vê tudo da empresa).

| Endpoint | Função |
|---|---|
| `GET /api/historico` | Lista paginada `{rows, total, page, limit}` com filtros + ordenação |
| `GET /api/historico/{id}` | Detalhe agregado (timeline + tags + transferências + avaliação + anotações + eventos) |
| `GET /api/historico/export?formato=csv\|xlsx` | Download do histórico filtrado (cap 50k linhas) |

### Filtros (query params da lista e do export)

| Param | Tipo | Descrição |
|---|---|---|
| `created_de` / `created_ate` | datetime ISO | Período de abertura |
| `closed_de` / `closed_ate` | datetime ISO | Período de fechamento |
| `status` | multi | `aguardando\|em_andamento\|resolvido\|abandonado` |
| `conexao_id` | int | Canal (conexão WhatsApp) |
| `departamento_id` | int | Departamento |
| `atendente_id` | str | Atendente (`assigned_to_user_id`) |
| `tag_id` | int | Tag aplicada |
| `prioridade` | str | `baixa\|media\|alta\|urgente` |
| `sentimento` | str | `positivo\|neutro\|negativo\|frustrado` |
| `iniciado_cliente` | bool | Quem iniciou |
| `q` | str | **Busca full-text**: protocolo, cliente.nome, telefone, `resumo_ia` **e o conteúdo das mensagens** (`message_queue.incoming_message/response`) |

Ordenação: `sort_field` ∈ `{created_at, closed_at, last_message_at, duracao,
nota, status, protocolo}` × `sort_order` ∈ `{asc, desc}`. Paginação: `page`
(≥1) + `limit` (1–200).

## Modelo de dados (reuso, sem tabelas novas)

A query faz `LEFT JOIN` sobre tabelas já existentes:

- `atendimento` (base + `protocolo`, `prioridade`, `sentimento`, `resumo_ia`,
  `departamento_id`, `assigned_to_user_id`, `closed_at`, `created_at`)
- `cliente` (nome, telefone) · `conexao` (`display_name`/`from_number` = canal)
- `departamento` (nome) · `auth."user"` (nome do atendente)
- `atendimento_avaliacao` (`nota`, `categoria` = CSAT)
- `atendimento_tag` (filtro por tag) · `message_queue` (busca full-text + timeline)
- `atendimento_transferencia` (auditoria no detalhe)

Campo computado: `duracao_seg = EXTRACT(EPOCH FROM (COALESCE(closed_at,
last_message_at) - created_at))`.

Migration **`110_historico_indexes.sql`**: índices `(empresa_id, created_at)`,
`(empresa_id, closed_at)`, `(empresa_id, status, created_at)` pra paginar
volumes grandes (dump real ZigChat ~9,8k atendimentos / 3 meses por empresa).

## Detalhe agregado (`GET /api/historico/{id}`)

`shared/historico.py::get_historico_detalhe` reusa os helpers existentes e
monta um único JSON:

```json
{
  "atendimento": { ...campos base... },
  "mensagens":   [ ...timeline via list_atendimento_mensagens... ],
  "tags":        [ ...list_tags_de_atendimento (humano vs IA)... ],
  "transferencias": [ {de/para user/depto, motivo, created_at} ],
  "avaliacao":   { "nota": 10, "categoria": "promotor", "comentario": "..." },
  "anotacoes":   [ ...list_anotacoes do cliente... ],
  "eventos":     [ {tipo: "aberto|triagem|transferencia|fechado|avaliacao", at} ]
}
```

## Exportação CSV / Excel

`GET /api/historico/export?formato=csv|xlsx` reusa a query da lista (sem
paginação, cap **50k** linhas com `log` se truncar) e gera o arquivo:

- **CSV**: `;` como separador + BOM UTF-8 (acentos corretos no Excel).
- **XLSX**: via `openpyxl` (cabeçalho em negrito).

No frontend o download passa por um **route handler** Next.js
(`/api/historico-export`) que injeta o service token server-side e faz proxy
streaming pro backend — o browser nunca vê o token. Os botões "CSV"/"Excel"
da barra de filtros apontam pra lá com os filtros atuais na querystring.

## Frontend (`frontend/src/app/chats/`)

| Arquivo | Papel |
|---|---|
| `page.tsx` | Server: lê filtros de `searchParams`, busca `getHistorico` + dropdowns, renderiza |
| `historico-filters.tsx` | Filtros (período, busca, canal, depto, tag, prioridade, status multi) + export |
| `historico-table.tsx` | Tabela ordenável + paginação + abre o drawer |
| `historico-detalhe-drawer.tsx` | Detalhe (timeline, avaliação, transferências, tags, eventos) |
| `actions.ts` | Server action `loadHistoricoDetalheAction` |
| `api/historico-export/route.ts` | Route handler de download (proxy autenticado) |

API client (`lib/api.ts`): `getHistorico`, `getHistoricoDetalhe`,
`proxyHistoricoExport` + tipos `HistoricoRow`/`HistoricoResponse`/
`HistoricoFiltrosParams`.

## Diferenciais vs ZigChat

1. **Busca full-text no conteúdo das mensagens** (ZigChat só protocolo/nome/telefone).
2. **Export nativo CSV + Excel** (ZigChat não exporta).
3. **Duração** computada por atendimento (e métricas de tempo/SLA na Fase 2).
4. **Colunas de IA**: prioridade, sentimento, `resumo_ia`, tags humano-vs-IA.
5. **Timeline unificada de eventos** (aberto/triagem/transferência/fechado/avaliação).

## Testes

- `tests/unit/test_historico_endpoints_smoke.py` — smoke (CI, sem DB): cada
  endpoint existe + exige auth (401).
- `tests/integration/test_historico_endpoints.py` — E2E `docker_demo`
  (httpx + psycopg): lista, filtro por status, busca por nome, detalhe (com
  avaliação + timeline + eventos), export CSV e XLSX, e isolamento entre
  empresas. Rodar com a stack de pé:
  ```bash
  DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
  INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
  uv run pytest tests/integration/test_historico_endpoints.py
  ```

## Roadmap — Fase 2 (relatórios / analytics)

- Migration: `atendimento.primeira_resposta_at` (worker seta no 1º outbound +
  backfill) → métrica de tempo de 1ª resposta.
- `shared/historico_relatorios.py` + `GET /api/historico/relatorios/*`:
  - `resumo` — volume total/por status/por dia, tempo médio de resolução e de
    1ª resposta, CSAT médio + NPS.
  - `por-operador`, `por-departamento`, `por-canal` — volume, SLA, tempo médio, CSAT.
- Frontend: sub-aba "Relatórios" (KPI cards + gráficos + tabelas), reusando o
  layout de `dashboard/qualidade`.
