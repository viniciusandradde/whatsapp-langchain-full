"""CRUD de Agentes IA cadastráveis (Sub-fase A).

Substitui agente_ia_config (mig 014) que era só override pontual. Agora
cada empresa pode ter N agentes; cada conexão WhatsApp aponta pra um
agente via `conexao.default_agent_id` (slug).

Mapping `estilo_resposta` → (temperatura, top_p):
- preciso: 0.1 / 0.6 (mais factual)
- equilibrado: 0.5 / 0.85 (default)
- criativo: 0.9 / 0.95
- muito_criativo: 1.3 / 0.99

`temperatura_override` / `top_p_override` permitem ignorar o preset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import structlog
from psycopg import AsyncConnection
from psycopg import errors as pg_errors
from psycopg.abc import QueryNoTemplate as Query
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# ---- Mapping estilo → (temperatura, top_p) ----

ESTILO_PRESETS: dict[str, tuple[float, float]] = {
    "preciso": (0.1, 0.6),
    "equilibrado": (0.5, 0.85),
    "criativo": (0.9, 0.95),
    "muito_criativo": (1.3, 0.99),
}


def resolve_temperatura_top_p(
    estilo: str,
    temperatura_override: float | None,
    top_p_override: float | None,
) -> tuple[float, float]:
    """Aplica preset + permite override fino."""
    base_temp, base_top_p = ESTILO_PRESETS.get(estilo, (0.5, 0.85))
    return (
        temperatura_override if temperatura_override is not None else base_temp,
        top_p_override if top_p_override is not None else base_top_p,
    )


# ---- Modelo + helpers ----


class DuplicateAgenteError(ValueError):
    """Slug já existe na empresa."""


_COLS = (
    "id, empresa_id, slug, nome, descricao, template_catalog, "
    "prompt_override, modelo, estilo_resposta, temperatura_override, "
    "max_tokens, top_p_override, tools_enabled, tools_config, "
    "aceita_imagem, aceita_audio, aceita_documento, anuncia_transferencia, "
    "base_conhecimento_ids, variavel_ids, mcp_server_ids, "
    "limite_custo_acao, ativo, is_default, "
    "created_by_user_id, created_at, updated_at, "
    # Sprint 2 padrão profissional (mig 043)
    "modelo_provedor, modelo_nome, tipo_memoria, janela_memoria, "
    "timeout_minutos, acao_limite_menu_id, "
    # Triagem omnichannel (mig 061): depto destino fixo quando agente
    # chama transfer_to_human (IA não escolhe — admin configura).
    "departamento_default_id"
)


@dataclass
class AgenteIA:
    id: int
    empresa_id: int
    slug: str
    nome: str
    descricao: str | None
    template_catalog: str
    prompt_override: str | None
    modelo: str | None
    estilo_resposta: str
    temperatura_override: float | None
    max_tokens: int | None
    top_p_override: float | None
    tools_enabled: list[str]
    tools_config: dict
    aceita_imagem: bool
    aceita_audio: bool
    aceita_documento: bool
    # Quando False, transfer_to_human nao manda a mensagem de sistema
    # citando o departamento (mig 143). A transferencia ocorre igual.
    anuncia_transferencia: bool
    base_conhecimento_ids: list[int]
    variavel_ids: list[int]
    mcp_server_ids: list[int]
    limite_custo_acao: str
    ativo: bool
    is_default: bool
    created_by_user_id: str | None
    created_at: Any
    updated_at: Any
    # Sprint 2 padrão profissional (mig 043)
    modelo_provedor: str | None = None
    modelo_nome: str | None = None
    tipo_memoria: str = "window"
    janela_memoria: int | None = None
    timeout_minutos: int | None = None
    acao_limite_menu_id: int | None = None
    # Triagem omnichannel (mig 061)
    departamento_default_id: int | None = None

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
            "empresa_id": self.empresa_id,
            "slug": self.slug,
            "nome": self.nome,
            "descricao": self.descricao,
            "template_catalog": self.template_catalog,
            "prompt_override": self.prompt_override,
            "modelo": self.modelo,
            "estilo_resposta": self.estilo_resposta,
            "temperatura_override": (
                float(self.temperatura_override)
                if self.temperatura_override is not None
                else None
            ),
            "max_tokens": self.max_tokens,
            "top_p_override": (
                float(self.top_p_override) if self.top_p_override is not None else None
            ),
            "tools_enabled": list(self.tools_enabled or []),
            "tools_config": self.tools_config or {},
            "aceita_imagem": self.aceita_imagem,
            "aceita_audio": self.aceita_audio,
            "aceita_documento": self.aceita_documento,
            "anuncia_transferencia": self.anuncia_transferencia,
            "base_conhecimento_ids": list(self.base_conhecimento_ids or []),
            "variavel_ids": list(self.variavel_ids or []),
            "mcp_server_ids": list(self.mcp_server_ids or []),
            "limite_custo_acao": self.limite_custo_acao,
            "ativo": self.ativo,
            "is_default": self.is_default,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # Sprint 2 padrão profissional
            "modelo_provedor": self.modelo_provedor,
            "modelo_nome": self.modelo_nome,
            "tipo_memoria": self.tipo_memoria,
            "janela_memoria": self.janela_memoria,
            "timeout_minutos": self.timeout_minutos,
            "acao_limite_menu_id": self.acao_limite_menu_id,
            # Triagem omnichannel (mig 061)
            "departamento_default_id": self.departamento_default_id,
        }
        # Campos derivados (pra UI mostrar valores efetivos)
        temp, top_p = resolve_temperatura_top_p(
            self.estilo_resposta,
            float(self.temperatura_override)
            if self.temperatura_override is not None
            else None,
            float(self.top_p_override) if self.top_p_override is not None else None,
        )
        out["temperatura_efetiva"] = temp
        out["top_p_efetivo"] = top_p
        return out


def _row_to_agente(row) -> AgenteIA:
    return AgenteIA(*row)


# ---- CRUD ----


async def list_agentes(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    only_active: bool = False,
    user_id: str | None = None,
) -> list[AgenteIA]:
    """Lista agentes da empresa, opcionalmente filtrados por ACL do user.

    Sprint C — quando `user_id` é passado, retorna apenas agentes onde
    `user_can_access_agente(user_id, empresa_id, agente_id, 'read')`
    retorna TRUE. Sem `user_id` (uso interno worker/sistema), retorna
    todos. Mantém compat: agentes sem ACL configurada aparecem pra todos.
    """
    params: list = [empresa_id]
    where = "a.empresa_id = %s"
    if only_active:
        where += " AND a.ativo = TRUE"

    if user_id is not None:
        # Filtro ACL: só inclui agente se user_can_access_agente == TRUE
        where += " AND user_can_access_agente(%s, %s, a.id, 'read')"
        params.extend([user_id, empresa_id])

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM agente_ia a WHERE {where} "
            "ORDER BY a.is_default DESC, a.nome",
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_agente(r) for r in rows]


# ---- ACL agente_perfil (Sprint C) ----


async def list_perfis_de_agente(
    pool: AsyncConnectionPool, agente_id: int
) -> list[dict]:
    """Retorna ACL atual: [{perfil_id, nome, can_read, can_write}, ...]."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT p.id, p.nome, ap.can_read, ap.can_write
              FROM agente_perfil ap
              JOIN perfil_acesso p ON p.id = ap.perfil_id
             WHERE ap.agente_id = %s
             ORDER BY p.nome
            """,
            (agente_id,),
        )
        rows = await cur.fetchall()
    return [
        {
            "perfil_id": int(r[0]),
            "nome": r[1],
            "can_read": bool(r[2]),
            "can_write": bool(r[3]),
        }
        for r in rows
    ]


async def replace_acl_agente(
    pool: AsyncConnectionPool,
    agente_id: int,
    empresa_id: int,
    entries: list[dict],
) -> list[dict]:
    """Substitui ACL inteira do agente (idempotente).

    `entries` é lista de `{perfil_id, can_read, can_write}`. Perfis
    omitidos são removidos. Lista vazia limpa ACL (volta pro modo compat).

    Valida que todos perfil_id pertencem à mesma empresa do agente
    (defense in depth contra forjar acesso cross-tenant).
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            # Validação: perfis precisam ser da mesma empresa
            if entries:
                perfil_ids = [int(e["perfil_id"]) for e in entries]
                cur = await conn.execute(
                    "SELECT id FROM perfil_acesso "
                    "WHERE empresa_id = %s AND id = ANY(%s)",
                    (empresa_id, perfil_ids),
                )
                valid_ids = {int(r[0]) for r in await cur.fetchall()}
                invalid = set(perfil_ids) - valid_ids
                if invalid:
                    raise ValueError(
                        f"Perfis fora da empresa {empresa_id}: {sorted(invalid)}"
                    )

            await conn.execute(
                "DELETE FROM agente_perfil WHERE agente_id = %s",
                (agente_id,),
            )
            for entry in entries:
                await conn.execute(
                    """
                    INSERT INTO agente_perfil
                        (agente_id, perfil_id, can_read, can_write)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        agente_id,
                        int(entry["perfil_id"]),
                        bool(entry.get("can_read", True)),
                        bool(entry.get("can_write", False)),
                    ),
                )
    return await list_perfis_de_agente(pool, agente_id)


async def get_agente_by_slug(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> AgenteIA | None:
    # PREFERE o agente ativo e é determinístico: slugs podem colidir
    # (duplicatas — ex. agente criado 2x). Sem ORDER, o `fetchone()` devolvia
    # uma linha ARBITRÁRIA, e cair na duplicata sem config (ex. sem
    # departamento_default_id) quebrava o handoff (prod 2026-06-01).
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_COLS} FROM agente_ia
             WHERE empresa_id = %s AND slug = %s
             ORDER BY ativo DESC, id DESC
             LIMIT 1
            """,
            (empresa_id, slug),
        )
        row = await cur.fetchone()
    return _row_to_agente(row) if row else None


async def get_agente_by_id(
    pool: AsyncConnectionPool, agente_id: int
) -> AgenteIA | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM agente_ia WHERE id = %s",
            (agente_id,),
        )
        row = await cur.fetchone()
    return _row_to_agente(row) if row else None


async def get_default_agente(
    pool: AsyncConnectionPool, empresa_id: int
) -> AgenteIA | None:
    """Retorna o agente default da empresa (uq_agente_ia_default)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM agente_ia "
            "WHERE empresa_id = %s AND is_default = TRUE AND ativo = TRUE LIMIT 1",
            (empresa_id,),
        )
        row = await cur.fetchone()
    return _row_to_agente(row) if row else None


def prompt_do_template(template_catalog: str) -> str | None:
    """Lê o `SYSTEM_PROMPT` do módulo da topologia.

    Import tardio de propósito: `agents/` importa `shared/`, então trazer o
    catálogo pro topo deste módulo fecharia um ciclo. Mesmo motivo do import
    dentro de `_validar_template` na route.
    """
    try:
        from importlib import import_module

        mod = import_module(
            f"whatsapp_langchain.agents.catalog.{template_catalog}.prompts"
        )
        texto = getattr(mod, "SYSTEM_PROMPT", None)
        return texto if texto else None
    except Exception as e:  # noqa: BLE001 — topologia sem prompts.py é válida
        logger.warning(
            "prompt_do_template_indisponivel", template=template_catalog, error=str(e)
        )
        return None


async def create_agente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    slug: str,
    nome: str,
    template_catalog: str,
    descricao: str | None = None,
    user_id: str | None = None,
) -> AgenteIA:
    """Cria o agente já com o prompt da topologia escrito no campo.

    Antes o agente nascia com `prompt_override` vazio e respondia usando o
    `SYSTEM_PROMPT` do módulo Python — a tela mostrava um campo em branco
    enquanto o backend usava outro texto, e ninguém conseguia ver nem editar
    o que o agente de fato seguia. Materializar na criação faz o painel ser a
    fonte de verdade e dá versão 1 no histórico desde o primeiro dia.
    """
    prompt = prompt_do_template(template_catalog)
    try:
        async with pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    f"""
                    INSERT INTO agente_ia
                        (empresa_id, slug, nome, descricao, template_catalog,
                         prompt_override, created_by_user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_COLS}
                    """,
                    (
                        empresa_id,
                        slug,
                        nome,
                        descricao,
                        template_catalog,
                        prompt,
                        user_id,
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                await registrar_versao_prompt(
                    conn,
                    empresa_id=empresa_id,
                    agente_id=row[0],
                    texto=prompt,
                    origem="inicial",
                    user_id=user_id,
                )
    except pg_errors.UniqueViolation as e:
        raise DuplicateAgenteError(
            f"Agente com slug '{slug}' já existe nessa empresa"
        ) from e
    assert row is not None
    return _row_to_agente(row)


# ---- Histórico de prompt (mig 158) ----


@dataclass
class PromptVersao:
    """Uma versão do prompt. `texto` só vem preenchido no detalhe —
    a listagem devolve `caracteres` porque o texto passa de 30 KB."""

    versao: int
    nota: str | None
    origem: str
    restaurada_de: int | None
    criado_por_user_id: str | None
    criado_por_nome: str | None
    criado_em: Any
    caracteres: int
    texto: str | None = None

    def to_dict(self) -> dict:
        out = {
            "versao": self.versao,
            "nota": self.nota,
            "origem": self.origem,
            "restaurada_de": self.restaurada_de,
            "criado_por_user_id": self.criado_por_user_id,
            "criado_por_nome": self.criado_por_nome,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "caracteres": self.caracteres,
        }
        if self.texto is not None:
            out["texto"] = self.texto
        return out


async def registrar_versao_prompt(
    conn: AsyncConnection,
    *,
    empresa_id: int,
    agente_id: int,
    texto: str | None,
    nota: str | None = None,
    origem: str = "edicao",
    restaurada_de: int | None = None,
    user_id: str | None = None,
) -> int:
    """Grava a nova versão do prompt e devolve o número dela.

    Recebe **conexão**, não pool, de propósito: roda na mesma transação do
    UPDATE que mudou o prompt. Diferente de `record_audit`, a falha aqui NÃO
    é engolida — perder histórico em silêncio é justamente o defeito que
    esta tabela existe para corrigir.

    O caller deve ter travado a linha do agente (`FOR UPDATE`) antes, o que
    serializa duas edições simultâneas e mantém a numeração densa.
    """
    cur = await conn.execute(
        """
        INSERT INTO agente_prompt_versao
            (empresa_id, agente_id, versao, texto, nota, origem,
             restaurada_de, criado_por_user_id)
        SELECT %s, %s, COALESCE(MAX(versao), 0) + 1, %s, %s, %s, %s, %s
          FROM agente_prompt_versao WHERE agente_id = %s
        RETURNING versao
        """,
        (
            empresa_id,
            agente_id,
            texto,
            nota,
            origem,
            restaurada_de,
            user_id,
            agente_id,
        ),
    )
    row = await cur.fetchone()
    assert row is not None
    return row[0]


_VERSAO_COLS = (
    "v.versao, v.nota, v.origem, v.restaurada_de, v.criado_por_user_id, "
    "u.name, v.criado_em, length(COALESCE(v.texto, ''))"
)


async def list_versoes_prompt(
    pool: AsyncConnectionPool, empresa_id: int, slug: str, *, limit: int = 100
) -> list[PromptVersao]:
    """Histórico do mais recente pro mais antigo, sem o texto."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            cast(
                Query,
                f"""
            SELECT {_VERSAO_COLS}
              FROM agente_prompt_versao v
              JOIN agente_ia a ON a.id = v.agente_id
              LEFT JOIN auth."user" u ON u.id = v.criado_por_user_id
             WHERE a.empresa_id = %s AND a.slug = %s
             ORDER BY v.versao DESC
             LIMIT %s
            """,
            ),
            (empresa_id, slug, limit),
        )
        rows = await cur.fetchall()
    return [PromptVersao(*r) for r in rows]


async def get_versao_prompt(
    pool: AsyncConnectionPool, empresa_id: int, slug: str, versao: int
) -> PromptVersao | None:
    """Uma versão específica, com o texto completo."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            cast(
                Query,
                f"""
            SELECT {_VERSAO_COLS}, v.texto
              FROM agente_prompt_versao v
              JOIN agente_ia a ON a.id = v.agente_id
              LEFT JOIN auth."user" u ON u.id = v.criado_por_user_id
             WHERE a.empresa_id = %s AND a.slug = %s AND v.versao = %s
            """,
            ),
            (empresa_id, slug, versao),
        )
        row = await cur.fetchone()
    return PromptVersao(*row) if row else None


async def restaurar_versao_prompt(
    pool: AsyncConnectionPool,
    empresa_id: int,
    slug: str,
    versao: int,
    *,
    user_id: str | None = None,
) -> AgenteIA | None:
    """Grava o texto da versão pedida como uma versão NOVA (modelo
    `git revert`). Nada é reescrito nem apagado, então restaurar por engano
    também é reversível.

    Devolve None quando o agente ou a versão não existem.
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT id FROM agente_ia WHERE empresa_id = %s AND slug = %s "
                "FOR UPDATE",
                (empresa_id, slug),
            )
            alvo = await cur.fetchone()
            if alvo is None:
                return None
            agente_id = alvo[0]

            cur = await conn.execute(
                "SELECT texto FROM agente_prompt_versao "
                " WHERE agente_id = %s AND versao = %s",
                (agente_id, versao),
            )
            origem_row = await cur.fetchone()
            if origem_row is None:
                return None
            texto = origem_row[0]

            cur = await conn.execute(
                cast(
                    Query,
                    f"""
                UPDATE agente_ia SET prompt_override = %s, updated_at = NOW()
                 WHERE id = %s
                RETURNING {_COLS}
                """,
                ),
                (texto, agente_id),
            )
            row = await cur.fetchone()

            nova = await registrar_versao_prompt(
                conn,
                empresa_id=empresa_id,
                agente_id=agente_id,
                texto=texto,
                nota=f"Restaurada da versão {versao}",
                origem="restauracao",
                restaurada_de=versao,
                user_id=user_id,
            )
    logger.info(
        "prompt_restaurado",
        empresa_id=empresa_id,
        slug=slug,
        de_versao=versao,
        nova_versao=nova,
    )
    return _row_to_agente(row) if row else None


async def update_agente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    slug: str,
    *,
    user_id: str | None = None,
    nota: str | None = None,
    **fields: Any,
) -> AgenteIA | None:
    """Atualiza qualquer subset de campos. Bloqueia colunas read-only
    (id, slug, empresa_id, created_at, etc).

    Convenção PATCH (docs/dev/PATCH_PATTERN.md): None = "limpar" o
    campo (vira NULL no DB). Caller deve passar SÓ os campos explícitos
    (use `body.model_dump(exclude_unset=True)` na route).

    Quando `prompt_override` vem no patch e o texto muda de verdade, grava
    uma versão em `agente_prompt_versao` na MESMA transação (mig 158).
    `nota` é a "mensagem de commit" opcional dessa versão e não é coluna de
    `agente_ia` — chega por nome e nunca entra no SET.
    """
    READONLY = {
        "id",
        "empresa_id",
        "slug",
        "created_at",
        "updated_at",
        "created_by_user_id",
        "temperatura_efetiva",
        "top_p_efetivo",
    }
    sets: list[str] = []
    params: list = []
    for k, v in fields.items():
        if k in READONLY:
            continue
        # Listas + JSON precisam cast explícito em alguns drivers
        if k in (
            "tools_enabled",
            "base_conhecimento_ids",
            "variavel_ids",
            "mcp_server_ids",
        ):
            sets.append(
                f"{k} = %s::text[]" if k == "tools_enabled" else f"{k} = %s::bigint[]"
            )
            params.append(list(v) if v is not None else None)
        elif k == "tools_config":
            import json

            sets.append("tools_config = %s::jsonb")
            params.append(json.dumps(v) if v is not None else None)
        else:
            sets.append(f"{k} = %s")
            params.append(v)

    if not sets:
        return await get_agente_by_slug(pool, empresa_id, slug)
    sets.append("updated_at = NOW()")
    params.extend([empresa_id, slug])

    versionar = "prompt_override" in fields
    async with pool.connection() as conn:
        async with conn.transaction():
            antes: str | None = None
            agente_id: int | None = None
            if versionar:
                # Trava a linha antes de ler: serializa duas edições
                # simultâneas do mesmo agente e mantém a numeração densa.
                cur = await conn.execute(
                    "SELECT id, prompt_override FROM agente_ia "
                    " WHERE empresa_id = %s AND slug = %s FOR UPDATE",
                    (empresa_id, slug),
                )
                alvo = await cur.fetchone()
                if alvo is not None:
                    agente_id, antes = alvo

            cur = await conn.execute(
                # query dinâmica (colunas do SET), valores parametrizados via %s
                cast(
                    Query,
                    f"""
                UPDATE agente_ia SET {", ".join(sets)}
                 WHERE empresa_id = %s AND slug = %s
                RETURNING {_COLS}
                """,
                ),
                tuple(params),
            )
            row = await cur.fetchone()
            atualizado = _row_to_agente(row) if row else None

            # Só versiona quando o texto muda de verdade — salvar a aba sem
            # tocar no prompt não deve poluir o histórico. NULL e "" são o
            # mesmo estado ("sem prompt"), então não contam como mudança.
            # Compara com o valor GRAVADO, não com o que veio no patch.
            if versionar and agente_id is not None and atualizado is not None:
                if (antes or "") != (atualizado.prompt_override or ""):
                    await registrar_versao_prompt(
                        conn,
                        empresa_id=empresa_id,
                        agente_id=agente_id,
                        texto=atualizado.prompt_override,
                        nota=nota,
                        origem="edicao",
                        user_id=user_id,
                    )
    return atualizado


async def soft_delete_agente(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> bool:
    """Marca como ativo=false. Não DROPa pra preservar atendimentos passados."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE agente_ia SET ativo = FALSE, updated_at = NOW() "
            "WHERE empresa_id = %s AND slug = %s",
            (empresa_id, slug),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


async def set_default_agente(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> bool:
    """Promove agente a default da empresa. Limpa default antigo (uq partial)."""
    async with pool.connection() as conn:
        async with conn.transaction():
            # Limpa default atual (não conflita com partial unique)
            await conn.execute(
                "UPDATE agente_ia SET is_default = FALSE WHERE empresa_id = %s AND is_default = TRUE",
                (empresa_id,),
            )
            cur = await conn.execute(
                "UPDATE agente_ia SET is_default = TRUE, updated_at = NOW() "
                "WHERE empresa_id = %s AND slug = %s AND ativo = TRUE",
                (empresa_id, slug),
            )
            return (cur.rowcount or 0) > 0


# ---- Runtime resolution (A.6) ----


@dataclass
class AgenteRuntime:
    """Config efetiva pro loader montar o graph.

    Combina `agente_ia` row + ESTILO_PRESETS resolvidos. `template_catalog`
    indica qual diretório Python carregar; demais campos viram overrides
    aplicados em `build_graph` do template.
    """

    slug: str
    template_catalog: str
    prompt_override: str | None
    modelo: str | None
    temperatura: float
    top_p: float
    max_tokens: int | None
    tools_enabled: list[str]
    base_conhecimento_ids: list[int]
    # Portão das tools `midia.*` no registry: reanalisar imagem só faz sentido
    # em agente que recebe imagem.
    aceita_imagem: bool = True
    aceita_audio: bool = True
    aceita_documento: bool = True
    # Sprint 2 padrão profissional (mig 043)
    tipo_memoria: str = "window"
    janela_memoria: int | None = None
    timeout_minutos: int | None = None
    acao_limite_menu_id: int | None = None

    @classmethod
    def from_agente(cls, agente: AgenteIA) -> AgenteRuntime:
        temp, top_p = resolve_temperatura_top_p(
            agente.estilo_resposta,
            float(agente.temperatura_override)
            if agente.temperatura_override is not None
            else None,
            float(agente.top_p_override) if agente.top_p_override is not None else None,
        )
        # Resolve modelo efetivo: provedor + nome separados (mig 043) OU
        # modelo único legado. Provedor + nome ganha precedência se ambos
        # preenchidos (cobre o caso pós-backfill).
        modelo_efetivo: str | None
        if agente.modelo_provedor and agente.modelo_nome:
            modelo_efetivo = f"{agente.modelo_provedor}/{agente.modelo_nome}"
        else:
            modelo_efetivo = agente.modelo
        return cls(
            slug=agente.slug,
            template_catalog=agente.template_catalog,
            prompt_override=agente.prompt_override,
            modelo=modelo_efetivo,
            temperatura=temp,
            top_p=top_p,
            max_tokens=agente.max_tokens,
            tools_enabled=list(agente.tools_enabled or []),
            base_conhecimento_ids=list(agente.base_conhecimento_ids or []),
            aceita_imagem=agente.aceita_imagem,
            aceita_audio=agente.aceita_audio,
            aceita_documento=agente.aceita_documento,
            tipo_memoria=agente.tipo_memoria,
            janela_memoria=agente.janela_memoria,
            timeout_minutos=agente.timeout_minutos,
            acao_limite_menu_id=agente.acao_limite_menu_id,
        )


async def resolve_agente_runtime(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> AgenteRuntime | None:
    """Resolve runtime config pra um slug — multi-agente DB com fallbacks.

    Ordem de resolução:
    1. agente_ia.row(slug) ativo → usa diretamente
    2. agente_ia.row(slug) inativo → cai pro default da empresa
    3. nenhuma row pro slug → retorna None (caller usa caminho legacy)

    Retorna None significa "não tem agente cadastrado em DB pra esse slug —
    use comportamento legacy (catálogo + agente_ia_config)".
    """
    agente = await get_agente_by_slug(pool, empresa_id, slug)
    if agente is not None and agente.ativo:
        return AgenteRuntime.from_agente(agente)
    # Fallback default — útil quando admin desativa o agente atual
    default = await get_default_agente(pool, empresa_id)
    if default is not None:
        return AgenteRuntime.from_agente(default)
    return None
