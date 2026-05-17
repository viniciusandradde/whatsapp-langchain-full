---
title: Atendimento — Operação (fluxo cliente → IA → atendente)
type: area
status: ativo
priority: alta
created: 2026-05-04
updated: 2026-05-17
tags: [atendimento, operacao, whatsapp, fluxo]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: produto
area:
projeto_pai:
relacionados: [Workflow-Mackenzie, Wizard-Coleta-Menu]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Atendimento — Operação

## Fluxo de uma mensagem inbound

1. **Webhook** chega em `/webhook/twilio` ou `/webhook/evolution`
2. Resolve `conexao` pela origem → resolve `agente_atual` via fallback de `resolve_agente_runtime`
3. `enqueue_or_buffer` enfileira em `message_queue` (debounce text-only 2s; mídia bypassa)
4. **Worker** polla `message_queue` com `FOR UPDATE SKIP LOCKED`
5. `process_message` ordem de tentativas:
   - `_try_handle_coleta_em_curso` (wizard de coleta em curso)
   - `_try_handle_workflow` (workflow LangGraph)
   - `_try_handle_menu` (menu chatbot legacy)
   - Agente IA (LangGraph com checkpointer)
6. Outbound via `OutboundClient` Protocol (TwilioClient / EvolutionClient)
7. `mark_done` apenas APÓS envio outbound confirmado

## Estado de um atendimento

- `aguardando` — esperando atendente humano puxar
- `em_andamento` — atendente humano assumiu (`assigned_to_user_id`)
- `resolvido` — fechado positivamente
- `abandonado` — fechado sem solução

## UI atendente humano (`/atendimento`)

- Lista 4 visualizações: meus, aguardando, grupos, outros
- Drawer com:
  - Card "Triagem IA" (resumo, classificação, prioridade, sentimento)
  - Card "🗂 Coleta prévia" (vars do wizard se tiver) — [[Wizard-Coleta-Menu]]
  - Histórico de mensagens via SSE (real-time, sem polling)
  - Composer manual
  - Transferência (modal popover atendente | departamento)

## Mecanismos de qualidade

- **NPS auto-capture** ao fechar atendimento (nota 0-10 → categoria promotor/neutro/detrator + comentário opcional 60s)
- Dashboard `/dashboard/qualidade` (mig 073+074)
- Hook `atendimento.fechado` dispara webhook externo opcional

## Riscos

- Múltiplos workers podem processar mensagens do mesmo atendimento simultâneo — protegido por `FOR UPDATE SKIP LOCKED` + lease (60s) + `pg_advisory_xact_lock` em workflows
- Worker travado (lease > 60s sem mark_done) → row volta pra `queued` com backoff progressivo

## Relacionados

- [[01-Projects/Workflow-Mackenzie]]
- [[01-Projects/Wizard-Coleta-Menu]]
- [[02-Areas/Observabilidade]]
