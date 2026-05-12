"""CRUD + tree helpers do menu chatbot árvore (Sub-fase B).

Modelo:
- `MenuChatbot`: 1 menu por (empresa, conexao_id|NULL). Boas-vindas + keywords
  pra reset + msg de opção inválida.
- `MenuItem`: árvore via self-FK (`parent_id`). 5 `acao_tipo`.
- `AtendimentoMenuHistorico`: trilha + `posicao_atual_item_id` pra resolver
  próxima escolha numérica relativa ao nível atual.

O handler `_try_handle_menu` no worker é o consumidor principal — ver
`worker/processor.py`. Decisões de ação ficam aqui (formatação,
parsing de número, resolução de filhos), enquanto efeitos colaterais
(transferir dep, fechar atendimento) ficam no chamador.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# ---- Constantes ----

ACAO_TIPOS = (
    # MVP (mig 040)
    "submenu",
    "transferir_dep",
    "chamar_agente",
    "enviar_msg",
    "fechar",
    # Sub-fase B+ (padrão profissional) (mig 042)
    "transferir_atendente",
    "enviar_template",
    "chamar_webhook",
    "enviar_link",
    "pesquisa_csat",
    "mudar_manual",
    "setar_nome",
)

# Regex de número de opção: aceita "1", " 1 ", "01", até 2 dígitos. Maiores
# (ex: "100") são tratados como texto inválido — evita confusão com IDs.
_NUMERO_OPCAO_RE = re.compile(r"^\s*(\d{1,2})\s*$")


# ---- Models ----


@dataclass
class MenuChatbot:
    id: int
    empresa_id: int
    conexao_id: int | None
    nome: str
    ativo: bool
    mensagem_boas_vindas: str
    trigger_keywords: list[str]
    mensagem_opcao_invalida: str
    created_at: Any
    updated_at: Any
    created_by_user_id: str | None
    # Sub-fase B+ (padrão profissional) (mig 041)
    atalho: str | None = None
    solicitar_nome: bool = False
    menu_moderno: bool = False
    auto_navegar_para_item_id: int | None = None
    qtde_acesso: int = 0
    arquivo_url: str | None = None
    mensagem_coleta: str | None = None
    mensagem_confirmar_coleta: str | None = None
    mensagem_final_coleta: str | None = None
    resposta_confidencial: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "empresa_id": self.empresa_id,
            "conexao_id": self.conexao_id,
            "nome": self.nome,
            "ativo": self.ativo,
            "mensagem_boas_vindas": self.mensagem_boas_vindas,
            "trigger_keywords": list(self.trigger_keywords or []),
            "mensagem_opcao_invalida": self.mensagem_opcao_invalida,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by_user_id": self.created_by_user_id,
            "atalho": self.atalho,
            "solicitar_nome": self.solicitar_nome,
            "menu_moderno": self.menu_moderno,
            "auto_navegar_para_item_id": self.auto_navegar_para_item_id,
            "qtde_acesso": self.qtde_acesso,
            "arquivo_url": self.arquivo_url,
            "mensagem_coleta": self.mensagem_coleta,
            "mensagem_confirmar_coleta": self.mensagem_confirmar_coleta,
            "mensagem_final_coleta": self.mensagem_final_coleta,
            "resposta_confidencial": self.resposta_confidencial,
        }


@dataclass
class MenuItem:
    id: int
    menu_id: int
    parent_id: int | None
    ordem: int
    label: str
    acao_tipo: str
    acao_payload: dict
    ativo: bool
    created_at: Any
    updated_at: Any
    # Sub-fase B+ (padrão profissional) (mig 042)
    comando: str | None = None
    acao_atendente_id: str | None = None
    acao_modelo_mensagem_id: int | None = None
    webhook_url: str | None = None
    hook_id: int | None = None
    link_url: str | None = None
    nota_min: int | None = None
    nota_max: int | None = None
    nota_pergunta: str | None = None
    grupo: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "menu_id": self.menu_id,
            "parent_id": self.parent_id,
            "ordem": self.ordem,
            "label": self.label,
            "acao_tipo": self.acao_tipo,
            "acao_payload": self.acao_payload or {},
            "ativo": self.ativo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "comando": self.comando,
            "acao_atendente_id": self.acao_atendente_id,
            "acao_modelo_mensagem_id": self.acao_modelo_mensagem_id,
            "webhook_url": self.webhook_url,
            "hook_id": self.hook_id,
            "link_url": self.link_url,
            "nota_min": self.nota_min,
            "nota_max": self.nota_max,
            "nota_pergunta": self.nota_pergunta,
            "grupo": self.grupo,
        }


_MENU_COLS = (
    "id, empresa_id, conexao_id, nome, ativo, mensagem_boas_vindas, "
    "trigger_keywords, mensagem_opcao_invalida, created_at, updated_at, "
    "created_by_user_id, "
    # B+ (mig 041)
    "atalho, solicitar_nome, menu_moderno, auto_navegar_para_item_id, "
    "qtde_acesso, arquivo_url, mensagem_coleta, mensagem_confirmar_coleta, "
    "mensagem_final_coleta, resposta_confidencial"
)
_ITEM_COLS = (
    "id, menu_id, parent_id, ordem, label, acao_tipo, acao_payload, "
    "ativo, created_at, updated_at, "
    # B+ (mig 042)
    "comando, acao_atendente_id, acao_modelo_mensagem_id, webhook_url, "
    "hook_id, link_url, nota_min, nota_max, nota_pergunta, grupo"
)


def _row_to_menu(row) -> MenuChatbot:
    return MenuChatbot(*row)


def _row_to_item(row) -> MenuItem:
    return MenuItem(*row)


# ---- CRUD Menu ----


async def list_menus(
    pool: AsyncConnectionPool, empresa_id: int, *, only_active: bool = False
) -> list[MenuChatbot]:
    where = "empresa_id = %s"
    if only_active:
        where += " AND ativo = TRUE"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_MENU_COLS} FROM menu_chatbot WHERE {where} "
            "ORDER BY created_at DESC",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_menu(r) for r in rows]


async def get_menu_by_id(
    pool: AsyncConnectionPool, empresa_id: int, menu_id: int
) -> MenuChatbot | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_MENU_COLS} FROM menu_chatbot WHERE empresa_id = %s AND id = %s",
            (empresa_id, menu_id),
        )
        row = await cur.fetchone()
    return _row_to_menu(row) if row else None


async def get_menu_ativo_para_conexao(
    pool: AsyncConnectionPool, empresa_id: int, conexao_id: int
) -> MenuChatbot | None:
    """Resolve menu ativo pra essa conexão.

    Prioridade: menu específico da conexão > menu genérico (conexao_id IS NULL).
    Retorna None se nenhum dos dois existir.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_MENU_COLS} FROM menu_chatbot
            WHERE empresa_id = %s
              AND ativo = TRUE
              AND (conexao_id = %s OR conexao_id IS NULL)
            ORDER BY conexao_id NULLS LAST
            LIMIT 1
            """,
            (empresa_id, conexao_id),
        )
        row = await cur.fetchone()
    return _row_to_menu(row) if row else None


async def create_menu(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    nome: str,
    mensagem_boas_vindas: str,
    conexao_id: int | None = None,
    trigger_keywords: list[str] | None = None,
    mensagem_opcao_invalida: str | None = None,
    user_id: str | None = None,
) -> MenuChatbot:
    keywords = trigger_keywords or ["menu", "opcoes", "inicio"]
    invalida = (
        mensagem_opcao_invalida
        or "Opção inválida. Por favor, escolha um número da lista."
    )
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO menu_chatbot
                (empresa_id, conexao_id, nome, mensagem_boas_vindas,
                 trigger_keywords, mensagem_opcao_invalida, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s::text[], %s, %s)
            RETURNING {_MENU_COLS}
            """,
            (empresa_id, conexao_id, nome, mensagem_boas_vindas,
             keywords, invalida, user_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return _row_to_menu(row)


async def update_menu(
    pool: AsyncConnectionPool,
    empresa_id: int,
    menu_id: int,
    **fields: Any,
) -> MenuChatbot | None:
    READONLY = {"id", "empresa_id", "created_at", "updated_at",
                "created_by_user_id"}
    sets: list[str] = []
    params: list = []
    for k, v in fields.items():
        if k in READONLY or v is None:
            continue
        if k == "trigger_keywords":
            sets.append("trigger_keywords = %s::text[]")
            params.append(list(v))
        else:
            sets.append(f"{k} = %s")
            params.append(v)
    if not sets:
        return await get_menu_by_id(pool, empresa_id, menu_id)
    sets.append("updated_at = NOW()")
    params.extend([empresa_id, menu_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE menu_chatbot SET {", ".join(sets)}
             WHERE empresa_id = %s AND id = %s
            RETURNING {_MENU_COLS}
            """,
            tuple(params),
        )
        row = await cur.fetchone()
        await conn.commit()
    return _row_to_menu(row) if row else None


async def delete_menu(
    pool: AsyncConnectionPool, empresa_id: int, menu_id: int
) -> bool:
    """Hard delete — cascade limpa items + historicos."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM menu_chatbot WHERE empresa_id = %s AND id = %s",
            (empresa_id, menu_id),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


# ---- CRUD Item ----


async def list_items_do_menu(
    pool: AsyncConnectionPool, menu_id: int, *, only_active: bool = True
) -> list[MenuItem]:
    """Retorna TODOS items do menu (raiz + filhos). Ordenados por
    (parent_id, ordem) — UI/handler reconstrói hierarquia."""
    where = "menu_id = %s"
    if only_active:
        where += " AND ativo = TRUE"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_ITEM_COLS} FROM menu_item WHERE {where} "
            "ORDER BY parent_id NULLS FIRST, ordem",
            (menu_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_item(r) for r in rows]


async def list_children(
    pool: AsyncConnectionPool, menu_id: int, parent_id: int | None
) -> list[MenuItem]:
    """Filhos de um nó específico (raiz quando parent_id=None)."""
    if parent_id is None:
        sql = (
            f"SELECT {_ITEM_COLS} FROM menu_item "
            "WHERE menu_id = %s AND parent_id IS NULL AND ativo = TRUE "
            "ORDER BY ordem"
        )
        params: tuple = (menu_id,)
    else:
        sql = (
            f"SELECT {_ITEM_COLS} FROM menu_item "
            "WHERE menu_id = %s AND parent_id = %s AND ativo = TRUE "
            "ORDER BY ordem"
        )
        params = (menu_id, parent_id)
    async with pool.connection() as conn:
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()
    return [_row_to_item(r) for r in rows]


async def get_item(
    pool: AsyncConnectionPool, item_id: int
) -> MenuItem | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_ITEM_COLS} FROM menu_item WHERE id = %s",
            (item_id,),
        )
        row = await cur.fetchone()
    return _row_to_item(row) if row else None


async def create_item(
    pool: AsyncConnectionPool,
    menu_id: int,
    *,
    label: str,
    acao_tipo: str,
    acao_payload: dict | None = None,
    parent_id: int | None = None,
    ordem: int | None = None,
) -> MenuItem:
    if acao_tipo not in ACAO_TIPOS:
        raise ValueError(
            f"acao_tipo '{acao_tipo}' inválido. Esperado: {ACAO_TIPOS}"
        )
    payload = acao_payload or {}
    if ordem is None:
        # Auto-incrementa: pega max(ordem) + 1 do mesmo nível
        async with pool.connection() as conn:
            if parent_id is None:
                cur = await conn.execute(
                    "SELECT COALESCE(MAX(ordem), 0) + 1 FROM menu_item "
                    "WHERE menu_id = %s AND parent_id IS NULL",
                    (menu_id,),
                )
            else:
                cur = await conn.execute(
                    "SELECT COALESCE(MAX(ordem), 0) + 1 FROM menu_item "
                    "WHERE menu_id = %s AND parent_id = %s",
                    (menu_id, parent_id),
                )
            row = await cur.fetchone()
            ordem = (row[0] if row else 1) or 1

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO menu_item
                (menu_id, parent_id, ordem, label, acao_tipo, acao_payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING {_ITEM_COLS}
            """,
            (menu_id, parent_id, ordem, label, acao_tipo, json.dumps(payload)),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return _row_to_item(row)


async def update_item(
    pool: AsyncConnectionPool, item_id: int, **fields: Any
) -> MenuItem | None:
    READONLY = {"id", "menu_id", "parent_id", "created_at", "updated_at"}
    sets: list[str] = []
    params: list = []
    for k, v in fields.items():
        if k in READONLY or v is None:
            continue
        if k == "acao_tipo" and v not in ACAO_TIPOS:
            raise ValueError(f"acao_tipo '{v}' inválido")
        if k == "acao_payload":
            sets.append("acao_payload = %s::jsonb")
            params.append(json.dumps(v))
        else:
            sets.append(f"{k} = %s")
            params.append(v)
    if not sets:
        return await get_item(pool, item_id)
    sets.append("updated_at = NOW()")
    params.append(item_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"UPDATE menu_item SET {', '.join(sets)} WHERE id = %s "
            f"RETURNING {_ITEM_COLS}",
            tuple(params),
        )
        row = await cur.fetchone()
        await conn.commit()
    return _row_to_item(row) if row else None


async def delete_item(pool: AsyncConnectionPool, item_id: int) -> bool:
    """Hard delete — cascade limpa filhos via parent_id FK."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM menu_item WHERE id = %s",
            (item_id,),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


async def reorder_items(
    pool: AsyncConnectionPool, menu_id: int, parent_id: int | None,
    ordered_ids: list[int],
) -> None:
    """Reordena items de um nível (raiz ou submenu).

    Workaround pro UNIQUE (menu_id, parent_id, ordem): primeiro joga
    ordens em negativos temporários, depois aplica positivos finais.
    """
    where_parent = "parent_id IS NULL" if parent_id is None else "parent_id = %s"
    parent_params: tuple = () if parent_id is None else (parent_id,)
    async with pool.connection() as conn:
        async with conn.transaction():
            for i, item_id in enumerate(ordered_ids, start=1):
                await conn.execute(
                    f"UPDATE menu_item SET ordem = %s "
                    f"WHERE id = %s AND menu_id = %s AND {where_parent}",
                    (-i, item_id, menu_id) + parent_params,
                )
            for i, item_id in enumerate(ordered_ids, start=1):
                await conn.execute(
                    "UPDATE menu_item SET ordem = %s WHERE id = %s",
                    (i, item_id),
                )


# ---- Tree formatting (worker handler usa) ----


def format_menu_message(
    boas_vindas: str | None,
    items: list[MenuItem],
) -> str:
    """Formata mensagem WhatsApp-like com lista numerada de opções.

    Ex:
        "Olá! Em que posso ajudar?

         1. Falar com vendas
         2. Suporte técnico
         3. Outras dúvidas

         Digite o número da opção desejada."
    """
    parts: list[str] = []
    if boas_vindas:
        parts.append(boas_vindas.strip())
        parts.append("")
    for it in items:
        parts.append(f"{it.ordem}. {it.label}")
    if items:
        parts.append("")
        parts.append("Digite o número da opção desejada.")
    return "\n".join(parts).strip()


def parse_numero_opcao(text: str) -> int | None:
    """Extrai número de opção de uma mensagem.

    Aceita "1", " 1 ", "01" — ignora outros (texto livre, "x", "menu",
    "1 e 2"). Retorna None quando não bate exatamente um número de 1-2 dígitos.
    """
    m = _NUMERO_OPCAO_RE.match(text or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if n > 0 else None


def is_trigger_keyword(text: str, keywords: list[str]) -> bool:
    """Match case-insensitive trim — usuário pode escrever 'Menu', 'MENU'."""
    norm = (text or "").strip().lower()
    return norm in {k.strip().lower() for k in (keywords or []) if k}


# ---- Histórico ----


async def registrar_historico(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    menu_id: int,
    item_id: int | None,
    posicao_atual_item_id: int | None,
    resposta: str | None = None,
) -> None:
    """Grava trilha de navegação do menu.

    `resposta` (mig 045): texto cru que o cliente respondeu — útil pra
    debug + análise UX (ex: ver qual texto o cliente digitou quando errou).
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO atendimento_menu_historico
                (atendimento_id, menu_id, item_id, posicao_atual_item_id, resposta)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (atendimento_id, menu_id, item_id, posicao_atual_item_id, resposta),
        )
        await conn.commit()


async def get_posicao_atual(
    pool: AsyncConnectionPool, atendimento_id: int
) -> tuple[int | None, int | None]:
    """Retorna (menu_id, posicao_atual_item_id) do último registro.

    `(None, None)` quando não há histórico — significa "primeira mensagem,
    ainda não recebeu menu". `(menu_id, None)` quer dizer "está na raiz".
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT menu_id, posicao_atual_item_id FROM atendimento_menu_historico "
            "WHERE atendimento_id = %s ORDER BY escolhido_at DESC LIMIT 1",
            (atendimento_id,),
        )
        row = await cur.fetchone()
    if not row:
        return (None, None)
    return (row[0], row[1])


# Ações de menu que tiram o cliente do menu — após qualquer uma delas,
# próximas mensagens do cliente devem ir pro agente IA / atendente humano,
# NÃO ser interpretadas como navegação no menu.
_ACOES_SAIDA_MENU = frozenset(
    {
        "chamar_agente",
        "transferir_dep",
        "transferir_atendente",
        "fechar",
        "mudar_manual",
    }
)


async def find_csat_item_ativo(
    pool: AsyncConnectionPool, empresa_id: int
) -> MenuItem | None:
    """Retorna o primeiro item `acao_tipo='pesquisa_csat'` ativo da empresa.

    Usado pra disparar pesquisa de satisfação automaticamente após
    `close_atendimento` (Sprint F.3). Se nenhum item CSAT cadastrado,
    retorna None — o close não envia nada.
    """
    # `_ITEM_COLS` não tem alias — prefixa com `mi.` no JOIN pra evitar
    # ambiguidade com `mc.id` (ambas têm coluna `id`).
    item_cols_aliased = ", ".join(
        f"mi.{c.strip()}" for c in _ITEM_COLS.split(",")
    )
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {item_cols_aliased}
              FROM menu_item mi
              JOIN menu_chatbot mc ON mc.id = mi.menu_id
             WHERE mc.empresa_id = %s
               AND mc.ativo
               AND mi.ativo
               AND mi.acao_tipo = 'pesquisa_csat'
             ORDER BY mi.id LIMIT 1
            """,  # type: ignore[arg-type]
            (empresa_id,),
        )
        row = await cur.fetchone()
    return _row_to_item(row) if row else None


async def cliente_ja_saiu_do_menu(
    pool: AsyncConnectionPool, atendimento_id: int
) -> bool:
    """True se a última escolha do cliente foi uma ação que saiu do menu.

    Sem isso, depois de "3" → "Vou te conectar com Agendamentos…", a próxima
    mensagem do cliente cai em `posicao_atual=None` + `hist_menu_id != None`,
    e o handler antigo trata como "navegação na raiz" → 'Opção inválida' em
    vez de deixar pro agente. Esse helper desambígua.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT mi.acao_tipo
              FROM atendimento_menu_historico h
              LEFT JOIN menu_item mi ON mi.id = h.item_id
             WHERE h.atendimento_id = %s
              AND h.item_id IS NOT NULL
             ORDER BY h.escolhido_at DESC
             LIMIT 1
            """,
            (atendimento_id,),
        )
        row = await cur.fetchone()
    if not row:
        return False
    return row[0] in _ACOES_SAIDA_MENU


# "Sair do menu" não é estado dedicado — o handler do worker combina sinais
# externos (atendimento.agente_atual atribuído / departamento_id atribuído /
# status='resolvido') com get_posicao_atual pra decidir se a próxima msg
# vai pro menu ou pro agente. Isso evita uma flag boolean redundante.
