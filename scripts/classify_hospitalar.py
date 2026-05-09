"""Sprint R.2 (revisado) — Classificador HOSPITALAR.

Sistema é hospital: classifica em 1 dos 8 sub-setores do atendimento
hospitalar:
- agendamentos: marcar/desmarcar consulta, exame, procedimento
- exames: tipos, preparo, jejum, resultado, retirar laudo
- orcamento: valores, preços, convênios, parcelamento, simulação
- ouvidoria: reclamação, sugestão, elogio, LGPD, problemas com atendente
- rh: vagas, processo seletivo, currículo, benefícios (rh-recrutamento-selecao)
- tesouraria: 2ª via boleto, negociação, reembolso, débito
- atendimento: triagem geral, dúvida sobre serviços, primeira interação
- atendimento-cliente: cliente já cadastrado pedindo suporte específico

Cache + asyncio + batch. ~10-15min pra 9.055 items.

Uso:
    python scripts/classify_hospitalar.py [--reset] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langchain_core.messages import HumanMessage

from whatsapp_langchain.shared.db import close_pool, get_pool
from whatsapp_langchain.shared.llm import create_chat_model


CACHE_DIR = Path(__file__).parent / "cache" / "hospitalar"

SLUGS = {
    "atendimento", "atendimento-cliente", "agendamentos", "exames",
    "orcamento", "ouvidoria", "rh-recrutamento-selecao", "tesouraria",
}

PROMPT = """Você classifica mensagens de pacientes/clientes de um HOSPITAL em UM dos
sub-setores abaixo. Responda APENAS o nome (uma palavra).

Sub-setores:
- agendamentos: marcar, remarcar, desmarcar, cancelar consulta/exame/procedimento. Disponibilidade de horário.
- exames: tipos de exame, preparo (jejum), preparo, resultado, laudo, retirada
- orcamento: valor, preço, simulação, convênios aceitos, parcelamento, formas de pagamento
- ouvidoria: reclamação, queixa, sugestão, elogio, LGPD, exclusão dados, problema atendente
- rh: vagas abertas, processo seletivo, currículo, benefícios, RH/recrutamento
- tesouraria: 2ª via boleto, negociação dívida, reembolso, débito vencido, pagamento atrasado
- atendimento: saudação, dúvida geral, primeira mensagem, triagem, pedido de informação genérica
- atendimento-cliente: cliente já cadastrado pedindo suporte específico (acesso, login, atualizar dados)

Mensagem: {msg}

Sub-setor:"""


def _cache_path(msg: str) -> Path:
    h = hashlib.sha256(msg.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.txt"


def _check_cache(msg: str) -> str | None:
    p = _cache_path(msg)
    if p.exists():
        return p.read_text().strip()
    return None


def _save_cache(msg: str, slug: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(msg).write_text(slug)


def _normalize(text: str) -> str:
    """Aceita variantes do LLM e mapeia pro slug oficial."""
    t = text.strip().lower().split()[0] if text.strip() else "atendimento"
    t = t.strip(".,;:")
    # Aliases comuns
    if t in ("rh", "recrutamento", "rh-recrutamento", "selecao", "vagas"):
        return "rh-recrutamento-selecao"
    if t in ("cliente", "atendimento-cliente", "suporte"):
        return "atendimento-cliente"
    if t == "agendamento":
        return "agendamentos"
    if t == "exame":
        return "exames"
    if t in ("preço", "preco", "orçamento"):
        return "orcamento"
    if t in SLUGS:
        return t
    return "atendimento"  # fallback


async def classify_one(llm, msg: str, sem: asyncio.Semaphore) -> str:
    cached = _check_cache(msg)
    if cached and cached in SLUGS:
        return cached
    async with sem:
        try:
            r = await llm.ainvoke([HumanMessage(content=PROMPT.format(msg=msg[:300]))])
            text = r.content if isinstance(r.content, str) else str(r.content)
            slug = _normalize(text)
            _save_cache(msg, slug)
            return slug
        except Exception as e:
            print(f"  [error] {e} (msg: {msg[:50]})")
            return "atendimento"


async def fetch_pending(pool, empresa_id: int, limit: int) -> list[tuple[int, str]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, cliente_msg
              FROM fewshot_example
             WHERE empresa_id = %s
               AND setor_classificado IS NULL
               AND char_length(cliente_msg) >= 3
             ORDER BY id ASC
             LIMIT %s
            """,
            (empresa_id, limit),
        )
        return [(int(r[0]), r[1]) for r in await cur.fetchall()]


async def update_slugs(pool, updates: list[tuple[int, str]]) -> int:
    if not updates:
        return 0
    async with pool.connection() as conn:
        cur = conn.cursor()
        await cur.executemany(
            """
            UPDATE fewshot_example
               SET setor_classificado = %s,
                   agente_slug = %s
             WHERE id = %s
            """,
            [(slug, slug, fid) for fid, slug in updates],
        )
        await conn.commit()
    return len(updates)


async def reset_classification(pool, empresa_id: int) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE fewshot_example SET setor_classificado = NULL "
            "WHERE empresa_id = %s",
            (empresa_id,),
        )
        await conn.commit()
        return cur.rowcount


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa-id", type=int,
                        default=int(os.environ.get("EMPRESA_ID", "999")))
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--batch", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=15)
    parser.add_argument("--reset", action="store_true",
                        help="Reseta setor_classificado=NULL antes")
    args = parser.parse_args()

    print(f"=== Sprint R.2 Hospitalar ===")
    print(f"empresa_id: {args.empresa_id}")
    print(f"concurrency: {args.concurrency}, batch: {args.batch}")
    print()

    pool = await get_pool()
    if args.reset:
        n = await reset_classification(pool, args.empresa_id)
        print(f"[reset] {n} rows zeradas")

    llm = create_chat_model(model="openai/gpt-4o-mini", temperature=0.0, max_tokens=10)
    sem = asyncio.Semaphore(args.concurrency)
    total_done = 0

    try:
        while True:
            pending = await fetch_pending(pool, args.empresa_id, args.batch)
            if not pending or total_done >= args.limit:
                break
            tasks = [classify_one(llm, msg, sem) for _, msg in pending]
            slugs = await asyncio.gather(*tasks)
            updates = [(fid, slug) for (fid, _), slug in zip(pending, slugs)]
            n = await update_slugs(pool, updates)
            total_done += n
            dist: dict[str, int] = {}
            for s in slugs:
                dist[s] = dist.get(s, 0) + 1
            print(f"  [{total_done:>5}] batch={n} dist={dist}", flush=True)
    finally:
        await close_pool()

    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT setor_classificado, COUNT(*)
              FROM fewshot_example
             WHERE empresa_id = %s AND setor_classificado IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC
            """,
            (args.empresa_id,),
        )
        rows = await cur.fetchall()
    print()
    print("=== DISTRIBUIÇÃO FINAL ===")
    for slug, n in rows:
        print(f"  {slug}: {n}")
    await close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
