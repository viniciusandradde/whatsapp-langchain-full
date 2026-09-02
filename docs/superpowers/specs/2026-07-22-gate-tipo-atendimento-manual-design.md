# Gate de IA por conexão — honrar `tipo_atendimento` (modo manual)

**Data:** 2026-07-22 · **Status:** aprovado pelo Vinicius

## Problema

Empresa recém-criada + WhatsApp conectado → o bot já responde imediatamente.
Causa: `conexao.tipo_atendimento` (`manual|ia|hibrido`, mig 048) tem select na
UI de conexões mas **não é lido em lugar nenhum** do pipeline (webhook/worker).
Como empresa nova não tem `agente_ia` cadastrado, `resolve_agente_runtime`
retorna `None` e o worker cai no fallback legacy do catálogo (template
hardcoded) — respondendo sem nenhuma configuração.

## Decisões (com o usuário)

- Modo `manual` = **silêncio total**: mensagem registrada, atendimento entra
  na fila humana (`aguardando`, visível em `/atendimento`), nenhuma resposta
  automática (sem workflow, sem menu, sem IA, sem CSAT).
- Exceção única: opt-out (STOP/PARAR) continua sendo processado ANTES do gate
  — compliance anti-ban do Disparador não pode depender do modo da conexão.
- Modo `hibrido` = comportamento idêntico a `ia` por enquanto.
- Conexões **novas** nascem `manual`; conexões existentes não mudam (zero
  impacto nas empresas em produção, que dependem do fallback legacy).

## Mudanças

1. **Migration `132_conexao_tipo_atendimento_default_manual.sql`** — muda o
   DEFAULT da coluna pra `'manual'` (sem UPDATE em rows existentes).
2. **`shared/conexao.py::upsert_conexao`** — `COALESCE(%s, 'ia')` vira
   `COALESCE(%s, 'manual')` no INSERT (o UPDATE do upsert já preserva o valor
   atual quando o payload não manda o campo). Todos os fluxos de criação
   (cadastro manual, auto-provision Evolution, Embedded Signup WABA) passam
   por aqui.
3. **Gate no worker (`worker/processor.py::process_message`)** — logo após
   `_try_handle_opt_out`: carrega a conexão (`message.conexao_id`); se
   `tipo_atendimento == 'manual'`, faz `mark_done` com marker
   `MODO_MANUAL_MARKER = "[modo manual — IA desligada nesta conexão]"`
   (mesmo padrão do `HANDOFF_HUMANO_MARKER`) preservando `incoming_message`
   na timeline, loga `worker_skipped_agent_modo_manual` e retorna. Sem
   preprocessing de mídia (não gasta token de transcrição).
4. **Frontend** — drawer de atendimento: filtro de bolha automática passa a
   reconhecer também o prefixo `"[modo manual"`. Tela de conexões: aviso
   visual quando `tipo_atendimento === 'manual'` ("IA desligada — configure o
   agente e mude para IA quando estiver pronto").
5. **Testes** — unit no modelo de `tests/unit/test_processor_outbound.py`:
   (a) conexão manual → nenhuma resposta outbound + mark_done com marker;
   (b) conexão ia → fluxo atual inalterado; (c) opt-out responde mesmo em
   manual. Smoke dos endpoints tocados permanece verde.

## Fluxo resultante

criar empresa → conectar WhatsApp → conexão nasce `manual` → mensagens entram
na fila humana em silêncio → admin configura agente → muda select pra `ia` →
bot passa a responder.
