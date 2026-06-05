# Gestão de Usuários (Sprint U)

Módulo `/usuarios` — gestão completa de atendentes/usuários da empresa.
Caminho **preferido** sobre o legado `/api/empresas/{id}/membros` (que
permanece por compatibilidade). UI em `frontend/src/app/usuarios/`.

## Onde o Nexus já supera o ZigChat
- **RBAC granular** (`.own`/`.all`) + perfis customizados (vs lista flat).
- **Multi-empresa** (`empresa_membro`): um usuário pode pertencer a N empresas.
- **Avatar** local re-encodado (Pillow 256×256), servido em `/uploads/avatars`.
- **Heartbeat** de atendente (online/ausente/pausa/offline) + capacidade.
- **Auditoria** rica (`audit_governanca`).

## Endpoints `/api/usuarios` (perm `empresa.member.add`, salvo indicado)
| Método | Rota | Função |
|---|---|---|
| GET | `/api/usuarios` | lista enriquecida + **paginação** (`limit`/`offset`, retorna `total`) + filtros (search/perfil/depto/status) |
| GET | `/api/usuarios/{id}` | detalhe |
| POST | `/api/usuarios` | criar (perfis + deptos + **conexões** + capacidade) |
| PUT | `/api/usuarios/{id}` | atualizar |
| PATCH | `/api/usuarios/{id}/status` | ativar/desativar **com transferência** (`empresa.member.status`) |
| POST | `/api/usuarios/{id}/replicar` | **clonar** usuário |
| POST | `/api/usuarios/{id}/avatar` | upload avatar |
| POST | `/api/usuarios/{id}/sessions/invalidate` | força re-login |
| DELETE | `/api/usuarios/{id}` | **remover** da empresa (`empresa.member.remove`) |
| GET | `/api/usuarios/exists/{id}` | checagem leve |

### Features ZigChat (paridade+)
- **Transferência ao desativar** (`PATCH .../status` body `on_disable`):
  `reassign` (→ outro atendente via `transfer_atendimento`), `departamento`
  (→ fila do depto via `transfer_atendimento_to_departamento`) ou `none`.
  Retorna `{status, transferidos}`. UI: modal ao desativar.
- **Conexão padrão por usuário** (mig 111 `usuario_conexao`): atribuição +
  default. Roteamento de outbound continua por `atendimento.conexao_id` — esta
  é atribuição/metadado + fallback do compositor.
- **Clonar usuário** (`/replicar`): copia perfis + deptos + conexões + role +
  capacidade. Senha nova gerada no fluxo do create.
- **Capacidade** (`atendente_max_paralelos`) editável no form (aba Atendimento)
  via `PUT /api/atendentes/{id}/max-paralelos`.

### Guards
- Não remover/desabilitar a si mesmo; não remover/desabilitar o último admin.
- Validação de tenant: perfis/deptos/conexões precisam pertencer à empresa
  (→ 422 claro).

## Turnos / Jornada (Fase 2)
Módulo `/settings/turnos` (perm leitura `departamento.read`, escrita
`horario.write`). Tabelas mig 112: `turno`, `turno_horario`, `usuario_turno`.

| Método | Rota |
|---|---|
| GET/POST | `/api/turnos` |
| GET/PUT/DELETE | `/api/turnos/{id}` |
| GET/PUT | `/api/turnos/{id}/users` |

Janelas por dia da semana (0=Dom..6=Sáb) + atribuição de atendentes.
O *gate de distribuição* já está **ligado**: `pick_best_atendente`
(`shared/atendente.py`) só roteia pra atendentes dentro da janela do turno
ativo (ou sem turno atribuído = irrestrito), via `turno_gate_sql`/`turno_now`
(`shared/turno.py`) no fuso da empresa.

## Migrations
- `111_usuario_conexao.sql` — conexão por usuário + RLS.
- `112_turnos.sql` — turnos/jornada + RLS.

## Testes
- Smoke (CI): `tests/unit/test_usuarios_endpoints_smoke.py`,
  `tests/unit/test_turnos_endpoints_smoke.py`.
- E2E (`docker_demo`): `tests/integration/test_usuarios_endpoints.py`
  (criar/clonar/status+transferência/delete/isolamento),
  `tests/integration/test_turnos_endpoints.py`.

## Status / shipped
- Aba **"Atividade"** (auditoria por usuário) no modal de edição — entregue
  (`usuario-form-modal.tsx`, lazy-load via `loadAtividadeAction`).
- **Gate de distribuição por turno** — entregue (ver "Turnos / Jornada" acima).
