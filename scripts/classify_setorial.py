"""Sprint R.2 — Classificação setorial automática via LLM (gpt-4o-mini).

Lê fewshot_example com setor_classificado IS NULL na empresa sandbox 999,
classifica em 1 dos 5 setores: ti, hospitalar, financeiro, diretoria,
operacional, outro.

Cache local em scripts/cache/classify/<hash>.txt — re-runs pulam.
Asyncio + semaphore (8 concorrentes) — ~10-20min pra 9.8k items.
Custo estimado ~$5-8 (gpt-4o-mini).

Após terminar: UPDATE agente_slug pra `radio-<setor>` consistente.

Uso:
    EMPRESA_ID=999 python scripts/classify_setorial.py [--limit 100]
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


CACHE_DIR = Path(__file__).parent / "cache" / "classify"
SETORES = {"ti", "hospitalar", "financeiro", "diretoria", "operacional", "outro"}

PROMPT_TEMPLATE = """Classifique a mensagem de um cliente em UM dos setores:
- ti: tecnologia, sistemas, redes, backup, GLPI, ERP, MV Soul, impressoras, login, senha, internet, computador
- hospitalar: pacientes, exames, prontuário, medicamentos, plantão, enfermagem, médico, leito, internação
- financeiro: pagamento, boleto, cobrança, fatura, NF, contrato, valor, parcelamento, vencimento
- diretoria: aprovação, decisão executiva, indicador, orçamento estratégico, comunicação interna
- operacional: rotina, escala, plantão, alerta, ronda, manutenção, almoxarifado
- outro: nada acima

Responda APENAS UMA palavra (uma das opções acima).

Mensagem: {msg}

Setor:"""


def _cache_path(msg: str) -> Path:
    h = hashlib.sha256(msg.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.txt"


def _check_cache(msg: str) -> str | None:
    p = _cache_path(msg)
    if p.exists():
        return p.read_text().strip()
    return None


def _save_cache(msg: str, setor: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(msg).write_text(setor)


async def classify_one(llm, msg: str, sem: asyncio.Semaphore) -> str:
    cached = _check_cache(msg)
    if cached and cached in SETORES:
        return cached
    async with sem:
        try:
            resp = await llm.ainvoke([
                HumanMessage(content=PROMPT_TEMPLATE.format(msg=msg[:300]))
            ])
            text = (resp.content if isinstance(resp.content, str) else str(resp.content))
            text = text.strip().lower().split()[0] if text else "outro"
            text = text.strip(".,;:")
            if text not in SETORES:
                text = "outro"
            _save_cache(msg, text)
            return text
        except Exception as e:
            print(f"  [error] {e} (msg: {msg[:50]})")
            return "outro"


async def fetch_pending(pool, empresa_id: int, limit: int) -> list[tuple[int, str]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, cliente_msg
              FROM fewshot_example
             WHERE empresa_id = %s
               AND setor_classificado IS NULL
               AND char_length(cliente_msg) >= 5
             ORDER BY id ASC
             LIMIT %s
            """,
            (empresa_id, limit),
        )
        return [(int(r[0]), r[1]) for r in await cur.fetchall()]


# Mapeamento setor classificado → agente_slug do chat-nexus prod (8 agentes)
SETOR_TO_AGENT = {
    "ti": "atendimento",
    "hospitalar": "exames",
    "financeiro": "orcamento",
    "diretoria": "atendimento",
    "operacional": "atendimento",
    "outro": "atendimento",
}


async def update_setores(pool, updates: list[tuple[int, str]]) -> int:
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
            [
                (setor, SETOR_TO_AGENT.get(setor, "atendimento"), fid)
                for fid, setor in updates
            ],
        )
        await conn.commit()
    return len(updates)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa-id", type=int,
                        default=int(os.environ.get("EMPRESA_ID", "999")))
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--batch", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    print(f"=== Sprint R.2 Classificador Setorial ===")
    print(f"empresa_id: {args.empresa_id}")
    print(f"concurrency: {args.concurrency}, batch: {args.batch}")
    print()

    pool = await get_pool()
    llm = create_chat_model(model="openai/gpt-4o-mini", temperature=0.0, max_tokens=10)
    sem = asyncio.Semaphore(args.concurrency)

    total_done = 0
    try:
        while True:
            pending = await fetch_pending(pool, args.empresa_id, args.batch)
            if not pending:
                print("[done] no more pending")
                break
            if total_done >= args.limit:
                break

            # Classifica em paralelo (semaphore controla concurrency)
            tasks = [classify_one(llm, msg, sem) for _, msg in pending]
            setores = await asyncio.gather(*tasks)
            updates = [(fid, setor) for (fid, _), setor in zip(pending, setores)]

            n = await update_setores(pool, updates)
            total_done += n

            # Snapshot da distribuição
            dist: dict[str, int] = {}
            for s in setores:
                dist[s] = dist.get(s, 0) + 1
            print(f"  [{total_done:>5}] batch={n} dist={dist}")
    finally:
        await close_pool()

    # Distribuição final
    print()
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
    print("=== DISTRIBUIÇÃO FINAL ===")
    for setor, n in rows:
        print(f"  {setor}: {n}")
    await close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
