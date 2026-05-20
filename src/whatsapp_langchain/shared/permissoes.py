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

from typing import Final, Literal

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# (codigo, descricao, modulo)
CATALOGO: Final[list[tuple[str, str, str]]] = [
    # Cliente — perms record-level (.own/.all). Versão sem sufixo continua
    # válida (alias = .all) pra compat com perfis criados pré-mig 083.
    ("cliente.read", "Ver clientes e ficha (legacy alias = .all)", "cliente"),
    ("cliente.read.all", "Ver TODOS os clientes da empresa", "cliente"),
    (
        "cliente.read.own",
        "Ver clientes vinculados aos departamentos do user",
        "cliente",
    ),
    ("cliente.write", "Criar/editar cliente (legacy alias = .all)", "cliente"),
    ("cliente.write.all", "Criar/editar QUALQUER cliente da empresa", "cliente"),
    ("cliente.write.own", "Criar/editar clientes do depto do user", "cliente"),
    ("cliente.delete", "Deletar cliente (operação permanente)", "cliente"),
    # Atendimento — perms record-level (.own/.all)
    ("atendimento.read", "Ver atendimentos (legacy alias = .all)", "atendimento"),
    ("atendimento.read.all", "Ver TODOS os atendimentos da empresa", "atendimento"),
    (
        "atendimento.read.own",
        "Ver atendimentos do user OU do depto dele",
        "atendimento",
    ),
    ("atendimento.write", "Responder no composer (legacy alias = .all)", "atendimento"),
    ("atendimento.write.all", "Responder em qualquer atendimento", "atendimento"),
    (
        "atendimento.write.own",
        "Responder só nos atendimentos do depto do user",
        "atendimento",
    ),
    ("atendimento.claim", "Pegar atendimento aguardando", "atendimento"),
    (
        "atendimento.transfer",
        "Transferir atendimento (legacy alias = .all)",
        "atendimento",
    ),
    ("atendimento.transfer.all", "Transferir qualquer atendimento", "atendimento"),
    ("atendimento.transfer.own", "Transferir só do depto do user", "atendimento"),
    (
        "atendimento.close",
        "Fechar/abandonar atendimento (legacy alias = .all)",
        "atendimento",
    ),
    ("atendimento.close.all", "Fechar qualquer atendimento", "atendimento"),
    ("atendimento.close.own", "Fechar só do depto do user", "atendimento"),
    (
        "atendimento.reset_thread",
        "Resetar checkpoint LangGraph (admin only típico)",
        "atendimento",
    ),
    (
        "atendimento.scope.departamento",
        "Ver atendimentos só do próprio departamento (deprecated, use .own)",
        "atendimento",
    ),
    # Agendamento (Calendar v2)
    ("agendamento.read", "Ver agendamentos da empresa", "agendamento"),
    ("agendamento.create", "Criar agendamento", "agendamento"),
    ("agendamento.cancel", "Cancelar agendamento", "agendamento"),
    ("agendamento.reschedule", "Reagendar evento existente", "agendamento"),
    ("agendamento.approve", "Aprovar/rejeitar pedido pendente (gestor)", "agendamento"),
    (
        "agendamento.regras.write",
        "Editar regras de negócio (horário, dias, antecedência)",
        "agendamento",
    ),
    # Conexão / WhatsApp providers
    ("conexao.read", "Ver conexões cadastradas", "conexao"),
    ("conexao.write", "Adicionar/editar/desabilitar conexão", "conexao"),
    # Agente IA
    ("agente.config", "Editar prompt/temperatura/modelo do agente", "agente"),
    ("agente.template.use", "Aplicar template de agente novo", "agente"),
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
    (
        "base_conhecimento.write",
        "Adicionar/editar/remover documentos",
        "base_conhecimento",
    ),
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
    # Atendimento UX (Sprint 1.1) — abas pessoais, tags, notas internas
    (
        "atendimento.aba.manage",
        "Criar/editar/deletar próprias abas no painel de atendimento",
        "atendimento",
    ),
    (
        "atendimento.tag.aplicar",
        "Aplicar/remover tags em atendimentos visíveis",
        "atendimento",
    ),
    (
        "atendimento.nota_interna.criar",
        "Criar notas internas (privadas) na timeline",
        "atendimento",
    ),
    ("tag.manage", "CRUD de tags da empresa (admin/gestor only)", "tag"),
    # Integrações externas (Sprint Wareline)
    (
        "integracao.wareline.manage",
        "Gerenciar credenciais da integração Wareline ConecteHub",
        "integracao",
    ),
    # Conector genérico de APIs (Sprint Conector API)
    (
        "integracao.manage",
        "Gerenciar conexões de API (qualquer provider do catálogo)",
        "integracao",
    ),
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
            # cliente/atendimento: scope .all (vê tudo da empresa)
            "cliente.read.all",
            "cliente.write.all",
            "atendimento.read.all",
            "atendimento.write.all",
            "atendimento.claim",
            "atendimento.transfer.all",
            "atendimento.close.all",
            "atendimento.reset_thread",
            "agendamento.read",
            "agendamento.create",
            "agendamento.cancel",
            "agendamento.reschedule",
            "agendamento.approve",
            "agendamento.regras.write",
            "conexao.read",
            "modelo_mensagem.read",
            "modelo_mensagem.write",
            "hook.read",
            "hook.dlq.retry",
            "variavel.read",
            "base_conhecimento.read",
            "base_conhecimento.write",
            "empresa.member.status",
            "departamento.read",
            "departamento.write",
            "horario.write",
            "atendimento.aba.manage",
            "atendimento.tag.aplicar",
            "atendimento.nota_interna.criar",
            "tag.manage",
            "integracao.wareline.manage",
            "integracao.manage",
            "security.audit.read",
        ],
    ),
    (
        "Operador",
        (
            "Atende clientes via WhatsApp; só vê clientes/atendimentos do(s) "
            "depto(s) dele."
        ),
        [
            # cliente/atendimento: scope .own (filtra por usuario_departamento)
            "cliente.read.own",
            "cliente.write.own",
            "atendimento.read.own",
            "atendimento.write.own",
            "atendimento.claim",
            "atendimento.transfer.own",
            "atendimento.close.own",
            "agendamento.read",
            "agendamento.create",
            "agendamento.cancel",
            "modelo_mensagem.read",
            "base_conhecimento.read",
            "departamento.read",
            "atendimento.aba.manage",
            "atendimento.tag.aplicar",
            "atendimento.nota_interna.criar",
        ],
    ),
    (
        "Leitura",
        "Read-only — pra auditoria/visualização sem mutação. Vê tudo da empresa.",
        [
            "cliente.read.all",
            "atendimento.read.all",
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


# ============================================================
# Record-level scope resolution (mig 083)
# ============================================================

# Tipo retornado: 'all' (vê tudo da empresa), 'own' (só escopo do user
# via usuario_departamento), None (sem permissão sequer pra ver).
Scope = Literal["all", "own"] | None


def effective_scope(perms: set[str], base: str) -> Scope:
    """Resolve qual scope o usuário tem pra uma permissão base.

    Args:
        perms: set de codigos que o user tem (de get_user_permissions)
        base: nome base sem sufixo, ex: "cliente.read", "atendimento.write"

    Returns:
        - 'all' se tem `<base>.all` OU `<base>` (legacy alias) → vê tudo
        - 'own' se tem APENAS `<base>.own` → escopo restrito
        - None se não tem nenhuma variante → sem permissão

    Precedência: `.all` > `.own` > legacy. Quando user tem ambas
    `.all` e `.own`, ganha `.all` (mais permissivo).
    """
    if f"{base}.all" in perms or base in perms:
        return "all"
    if f"{base}.own" in perms:
        return "own"
    return None


async def get_user_departamento_ids(
    pool: AsyncConnectionPool, user_id: str, empresa_id: int
) -> list[int]:
    """Lista IDs dos departamentos vinculados ao user na empresa.

    Usado pra aplicar filtro `.own` em queries de cliente/atendimento.
    Retorna lista vazia se user não tem nenhum depto vinculado — nesse
    caso, queries `.own` devem retornar zero records (segurança por
    default).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT DISTINCT d.id
              FROM usuario_departamento ud
              JOIN departamento d ON d.id = ud.departamento_id
             WHERE ud.user_id = %s AND d.empresa_id = %s AND d.ativo = TRUE
            """,
            (user_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]
