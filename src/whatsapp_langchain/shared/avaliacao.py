"""Sprint X — captura e persistência de avaliações NPS.

Fluxo:
1. Worker fecha atendimento → `send_csat_survey` envia pergunta + set
   `atendimento.aguardando_avaliacao_at = NOW()`
2. Cliente responde nota → worker chama `_try_capture_avaliacao`:
   - se mensagem for número 0-10 dentro de 24h da flag → `save_avaliacao`,
     limpa flag avaliação, set `aguardando_comentario_at`
   - bot pergunta comentário
3. Cliente responde comentário (≤60s) → `save_avaliacao(comentario=...)` faz
   UPSERT do registro existente, limpa flag comentário
4. Cliente ignora → flags expiram (re-avaliadas pelo timestamp na próxima
   mensagem; não há job de cleanup)
"""

from __future__ import annotations

import re

from psycopg_pool import AsyncConnectionPool

WINDOW_NOTA_HORAS = 24
WINDOW_COMENTARIO_SEGUNDOS = 60

# Captura: número inteiro 0-10. Aceita "10", "9", "nota 8", "8/10", etc.
# Mas exige que apareça SOZINHO ou rodeado de espaços/pontuação — evita pegar
# números embedded em frases longas tipo "marquei pra 9h".
_NOTA_RE = re.compile(r"(?:^|[^\d])(10|[0-9])(?:[^\d]|$)")


def classify_nota(nota: int) -> str:
    """Categoria NPS clássica: 9-10 promotor, 7-8 neutro, 0-6 detrator."""
    if nota >= 9:
        return "promotor"
    if nota >= 7:
        return "neutro"
    return "detrator"


def parse_nota(text: str) -> int | None:
    """Extrai nota 0-10 de texto livre. Retorna None se não match.

    Aceita "9", "nota 9", "9/10", "9 obrigado", etc. Rejeita texto puro sem
    número e números fora do range 0-10. Pega só o PRIMEIRO match.
    """
    if not text:
        return None
    m = _NOTA_RE.search(text.strip())
    if not m:
        return None
    n = int(m.group(1))
    return n if 0 <= n <= 10 else None


async def save_avaliacao(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    nota: int | None = None,
    comentario: str | None = None,
) -> int:
    """Insere/atualiza avaliação. Resolve cliente_id/depto_id/user_id do
    atendimento.

    Modos:
    - 1ª chamada com `nota`: INSERT inicial com categoria calculada
    - 2ª chamada com `comentario` (mesma atendimento_id): UPDATE do comentário
      via UPSERT (não muda nota nem categoria)

    Retorna o id da linha em atendimento_avaliacao.
    """
    if nota is None and comentario is None:
        raise ValueError("Forneça `nota` ou `comentario`.")

    if nota is not None:
        if not (0 <= nota <= 10):
            raise ValueError(f"Nota fora do range 0-10: {nota}")
        categoria = classify_nota(nota)
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO atendimento_avaliacao
                  (atendimento_id, empresa_id, cliente_id, departamento_id,
                   assigned_to_user_id, nota, comentario, categoria)
                SELECT a.id, a.empresa_id, a.cliente_id, a.departamento_id,
                       a.assigned_to_user_id, %s, %s, %s
                  FROM atendimento a
                 WHERE a.id = %s
                ON CONFLICT (atendimento_id) DO UPDATE
                  SET nota = EXCLUDED.nota,
                      categoria = EXCLUDED.categoria,
                      comentario = COALESCE(
                          EXCLUDED.comentario,
                          atendimento_avaliacao.comentario
                      )
                RETURNING id
                """,
                (nota, comentario, categoria, atendimento_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    else:
        # Só comentário: UPDATE direto (assume INSERT prévio)
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE atendimento_avaliacao
                   SET comentario = %s
                 WHERE atendimento_id = %s
                RETURNING id
                """,
                (comentario, atendimento_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    if row is None:
        raise RuntimeError(
            f"Falha ao salvar avaliação para atendimento {atendimento_id}"
        )
    return int(row[0])


async def find_aguardando_avaliacao(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    cliente_id: int,
) -> dict | None:
    """Busca o atendimento mais recente do cliente que está aguardando nota
    (≤24h) ou comentário (≤60s). Retorna None se nenhum.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, aguardando_avaliacao_at, aguardando_comentario_at
              FROM atendimento
             WHERE cliente_id = %s
               AND empresa_id = %s
               AND (
                    (aguardando_avaliacao_at IS NOT NULL
                     AND aguardando_avaliacao_at >
                         NOW() - (%s || ' hours')::INTERVAL)
                 OR (aguardando_comentario_at IS NOT NULL
                     AND aguardando_comentario_at >
                         NOW() - (%s || ' seconds')::INTERVAL)
               )
             ORDER BY id DESC
             LIMIT 1
            """,
            (cliente_id, empresa_id, WINDOW_NOTA_HORAS, WINDOW_COMENTARIO_SEGUNDOS),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "atendimento_id": int(row[0]),
        "aguardando_avaliacao_at": row[1],
        "aguardando_comentario_at": row[2],
    }


async def set_aguardando_avaliacao(
    pool: AsyncConnectionPool, atendimento_id: int
) -> None:
    """Marca o atendimento como aguardando nota (após enviar pesquisa CSAT)."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE atendimento SET aguardando_avaliacao_at = NOW() "
            "WHERE id = %s",
            (atendimento_id,),
        )
        await conn.commit()


async def set_aguardando_comentario(
    pool: AsyncConnectionPool, atendimento_id: int
) -> None:
    """Marca o atendimento como aguardando comentário (após capturar nota).
    Limpa a flag de avaliação no mesmo UPDATE pra evitar dupla captura.
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE atendimento
               SET aguardando_comentario_at = NOW(),
                   aguardando_avaliacao_at = NULL
             WHERE id = %s
            """,
            (atendimento_id,),
        )
        await conn.commit()


async def clear_flags(
    pool: AsyncConnectionPool, atendimento_id: int
) -> None:
    """Limpa ambas as flags (após capturar comentário ou expirar)."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE atendimento
               SET aguardando_avaliacao_at = NULL,
                   aguardando_comentario_at = NULL
             WHERE id = %s
            """,
            (atendimento_id,),
        )
        await conn.commit()
