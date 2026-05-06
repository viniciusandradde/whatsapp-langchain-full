"""Catálogo canônico de permissões + sync no startup (E2.A RBAC).

Convenção: `<modulo>.<acao>`. Toda ação sensível do sistema deve
declarar uma permissão aqui ANTES de existir um endpoint que requer ela.

Sync: `sync_catalogo(pool)` é chamado no boot da API/Worker via
`bootstrap_langgraph_schema()` adjacente. UPSERT idempotente — adicionar
uma entrada nova aqui + redeploy é suficiente pra ela aparecer.

Uso em rota:
    from whatsapp_langchain.shared.permissoes import require_permission

    @router.post("/algo")
    async def handler(_: None = Depends(require_permission("cliente.write"))):
        ...

Uso no frontend: hook `usePermission("cliente.write")` esconde/desabilita
botões — checagem real continua server-side.
"""

from __future__ import annotations

from typing import Final

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# (codigo, descricao, modulo)
CATALOGO: Final[list[tuple[str, str, str]]] = [
    # Cliente
    ("cliente.read", "Ver clientes e ficha", "cliente"),
    ("cliente.write", "Criar/editar cliente, tags, anotações", "cliente"),
    ("cliente.delete", "Deletar cliente (operação permanente)", "cliente"),

    # Atendimento
    ("atendimento.read", "Ver atendimentos da empresa", "atendimento"),
    ("atendimento.write", "Responder no composer (envia outbound)", "atendimento"),
    ("atendimento.claim", "Pegar atendimento aguardando", "atendimento"),
    ("atendimento.transfer", "Transferir atendimento pra outro user", "atendimento"),
    ("atendimento.close", "Fechar/abandonar atendimento", "atendimento"),
    ("atendimento.reset_thread", "Resetar checkpoint LangGraph (admin only típico)", "atendimento"),
    ("atendimento.scope.departamento", "Ver atendimentos só do próprio departamento", "atendimento"),

    # Agendamento (Calendar v2)
    ("agendamento.read", "Ver agendamentos da empresa", "agendamento"),
    ("agendamento.create", "Criar agendamento", "agendamento"),
    ("agendamento.cancel", "Cancelar agendamento", "agendamento"),
    ("agendamento.reschedule", "Reagendar evento existente", "agendamento"),
    ("agendamento.approve", "Aprovar/rejeitar pedido pendente (gestor)", "agendamento"),
    ("agendamento.regras.write", "Editar regras de negócio (horário, dias, antecedência)", "agendamento"),

    # Conexão / WhatsApp providers
    ("conexao.read", "Ver conexões cadastradas", "conexao"),
    ("conexao.write", "Adicionar/editar/desabilitar conexão", "conexao"),

    # Agente IA
    ("agente.config", "Editar prompt/temperatura/modelo do agente", "agente"),
    ("agente.template.use", "Aplicar template de agente novo (Etapa 3)", "agente"),

    # Menu chatbot árvore (Sub-fase B)
    ("menu_chatbot.read", "Ver menus chatbot configurados", "menu_chatbot"),
    ("menu_chatbot.write", "Criar/editar menus + items + reordenar", "menu_chatbot"),

    # Quick replies
    ("modelo_mensagem.read", "Ver templates de resposta rápida", "modelo_mensagem"),
    ("modelo_mensagem.write", "Criar/editar templates", "modelo_mensagem"),

    # Hooks (webhooks de eventos)
    ("hook.read", "Ver hooks cadastrados + logs", "hook"),
    ("hook.write", "Criar/editar hooks", "hook"),
    ("hook.dlq.retry", "Reagendar entregas em DLQ", "hook"),

    # Variáveis de ambiente
    ("variavel.read", "Ver variáveis", "variavel"),
    ("variavel.write", "Criar/editar variáveis", "variavel"),

    # Base de conhecimento (RAG)
    ("base_conhecimento.read", "Ver documentos cadastrados", "base_conhecimento"),
    ("base_conhecimento.write", "Adicionar/editar/remover documentos", "base_conhecimento"),

    # Empresa / membros
    ("empresa.update", "Editar dados da empresa", "empresa"),
    ("empresa.member.add", "Adicionar novo membro (manual ou convite)", "empresa"),
    ("empresa.member.remove", "Remover membro", "empresa"),
    ("empresa.member.role", "Alterar role/perfil de membro", "empresa"),
    ("empresa.member.status", "Ativar/desativar membro", "empresa"),

    # Perfis (RBAC) — admin de admins
    ("perfil.read", "Ver perfis e suas permissões", "perfil"),
    ("perfil.write", "Criar/editar/deletar perfil custom", "perfil"),

    # Segurança / audit
    ("security.audit.read", "Ver histórico de login + audit", "security"),

    # Departamento / horário
    ("departamento.read", "Ver departamentos", "departamento"),
    ("departamento.write", "Criar/editar departamentos", "departamento"),
    ("horario.write", "Editar horários de funcionamento", "horario"),
]


# Perfis padrão (system, criados por empresa via seed_default_perfis).
# Cada entry: (nome, descricao, lista_de_permissoes ou "all").
PERFIS_SYSTEM: Final[list[tuple[str, str, str | list[str]]]] = [
    (
        "Admin",
        "Acesso total — equivalente ao role 'admin' legacy.",
        "all",  # explode pra todas as permissões do catálogo
    ),
    (
        "Gestor",
        "Gerencia operação e equipe, sem acesso a config crítica de empresa/perfis.",
        [
            "cliente.read", "cliente.write",
            "atendimento.read", "atendimento.write", "atendimento.claim",
            "atendimento.transfer", "atendimento.close", "atendimento.reset_thread",
            "agendamento.read", "agendamento.create", "agendamento.cancel",
            "agendamento.reschedule", "agendamento.approve",
            "agendamento.regras.write",
            "conexao.read",
            "modelo_mensagem.read", "modelo_mensagem.write",
            "hook.read", "hook.dlq.retry",
            "variavel.read",
            "base_conhecimento.read", "base_conhecimento.write",
            "empresa.member.status",
            "departamento.read", "departamento.write",
            "horario.write",
            "security.audit.read",
        ],
    ),
    (
        "Operador",
        "Atende clientes via WhatsApp; sem permissões de gestão.",
        [
            "cliente.read", "cliente.write",
            "atendimento.read", "atendimento.write", "atendimento.claim",
            "atendimento.transfer", "atendimento.close",
            "agendamento.read", "agendamento.create", "agendamento.cancel",
            "modelo_mensagem.read",
            "base_conhecimento.read",
            "departamento.read",
        ],
    ),
    (
        "Leitura",
        "Read-only — pra auditoria/visualização sem mutação.",
        [
            "cliente.read",
            "atendimento.read",
            "agendamento.read",
            "conexao.read",
            "modelo_mensagem.read",
            "hook.read",
            "variavel.read",
            "base_conhecimento.read",
            "departamento.read",
            "security.audit.read",
        ],
    ),
]


async def sync_catalogo(pool: AsyncConnectionPool) -> None:
    """Sincroniza tabela `permissao` com o catálogo do código.

    Idempotente. Adicionar entry nova em CATALOGO + restart = entry
    aparece em todas as empresas. Remoção de entry NÃO deleta row
    (preserva FK em perfil_permissao); rebuild manual se necessário.
    """
    async with pool.connection() as conn:
        for codigo, descricao, modulo in CATALOGO:
            await conn.execute(
                """
                INSERT INTO permissao (codigo, descricao, modulo)
                VALUES (%s, %s, %s)
                ON CONFLICT (codigo) DO UPDATE SET
                    descricao = EXCLUDED.descricao,
                    modulo = EXCLUDED.modulo
                """,
                (codigo, descricao, modulo),
            )
        await conn.commit()
    logger.info("permissoes_synced", total=len(CATALOGO))


async def seed_default_perfis(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Cria os 4 perfis system na empresa (Admin/Gestor/Operador/Leitura).

    Idempotente via UNIQUE(empresa_id, nome). Retorna número de perfis
    realmente criados (skip dos que já existem).
    """
    todos_codigos = [c[0] for c in CATALOGO]
    criados = 0

    async with pool.connection() as conn:
        for nome, descricao, perms_def in PERFIS_SYSTEM:
            cur = await conn.execute(
                """
                INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (empresa_id, nome) DO NOTHING
                RETURNING id
                """,
                (empresa_id, nome, descricao),
            )
            row = await cur.fetchone()
            if row is None:
                # Já existia — skip (não sobrescreve permissões)
                continue
            perfil_id = row[0]
            criados += 1

            # Resolve lista de permissões: 'all' = todas
            perms = todos_codigos if perms_def == "all" else perms_def
            for codigo in perms:
                await conn.execute(
                    """
                    INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (perfil_id, codigo),
                )
        await conn.commit()

    if criados:
        logger.info(
            "perfis_default_seeded",
            empresa_id=empresa_id,
            criados=criados,
        )
    return criados
