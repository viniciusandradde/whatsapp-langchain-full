---
title: Compliance LGPD
type: area
status: ativo
priority: alta
created: 2026-05-04
updated: 2026-05-17
tags: [lgpd, compliance, audit, juridico]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: governanca
area:
projeto_pai:
relacionados: [Governanca-RBAC-Backend, Workflow-Mackenzie]
stakeholders: [Vinicius-Andrade, Mackenzie-Hospital]
deadline:
progresso:
---

# Compliance LGPD

## Por que importa pra Nexus

Cliente principal é Hospital Mackenzie — saúde tem LGPD pesada (Art. 11, dados sensíveis de saúde). Plataforma processa: nome, CPF, telefone, dados clínicos via WhatsApp.

## Controles em produção

### Captura de consentimento
- Workflow Mackenzie tem **LGPD gate obrigatório** antes de coletar nome
- Cliente deve responder "1. Sim, Li e Concordo" pra prosseguir
- Recusa → encerra atendimento

### Audit trail
- `audit_log` (mig 026, login_event) — auditoria de login/logout/IP/UA
- `audit_governanca` (mig 084) — mudanças de perfil/depto/role/status com payload_before/after
- `workflow_evento` (mig 078) — node-by-node do workflow LangGraph (eventos `lgpd_consented`, `var_saved`, etc.)
- `hook_log` + `hook_dead_letter` — webhooks de eventos

### Retenção
- TODO — sem política formal de TTL pra audit_log/workflow_evento

### Reset password sem email (decisão LGPD)
- Better Auth `sendResetPassword` callback persiste link em `auth.password_reset_pending` (1h TTL) em vez de mandar email
- Admin compartilha pelo canal escolhido (WhatsApp pessoal, etc.) — controle do canal está com admin, não com Better Auth/SMTP
- Sprint Governança trocou pra "gerar nova senha server-side" (CSPRNG) — senha aparece UMA VEZ pro admin copiar

### Filtros record-level (mig 083)
- Operador só vê clientes/atendimentos de **seus departamentos** vinculados
- Permissões `.own/.all` aplicam no SQL WHERE via JOIN com `usuario_departamento`

## Riscos abertos

- ⚠ **Sem TTL/cleanup de audit_log e workflow_evento** — banco vai crescer indefinidamente
- ⚠ **PII em logs** — `structlog` registra `phone`, `email` em vários eventos. Reset password log mostra email
- ⚠ **Sem DPO formal nem rota `/privacy` no painel** — usuário final não tem como exercer direitos (esquecimento, portabilidade)
- ⚠ **VALIDATE_TWILIO_SIGNATURE=false em produção** (warning no boot) — webhooks Twilio aceitam payloads não autenticados se o endpoint vazar

## Próximos passos

- [ ] Política de retenção: 1 ano pra `audit_*`, 90 dias pra `workflow_evento`
- [ ] Redaction de PII em logs (filter no structlog)
- [ ] Rota `/privacy` no painel cliente com botões "exportar meus dados" / "esquecer"
- [ ] Habilitar VALIDATE_TWILIO_SIGNATURE em prod (depois de validar com Twilio Console)

## Relacionados

- [[01-Projects/Governanca-RBAC-Backend]]
- [[01-Projects/Workflow-Mackenzie]]
- [[Empresas/Mackenzie-Hospital]]
