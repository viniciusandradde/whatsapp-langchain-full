"""Sprint R.4 — Clustering por setor pra extrair docs base do conhecimento.

Pra cada setor (ti, hospitalar, financeiro, diretoria, operacional, outro):
- SELECT cliente_msg WHERE empresa_id=999 AND setor_classificado=<setor>
- Embeda em batch
- Greedy clustering por cosine similarity (≥0.75, min cluster=3)
- Pra cada cluster, gera draft (titulo + conteudo) via gpt-4o-mini
- INSERT em documento_sugerido com pasta_id correto

Reusa parts do shared/rag_learner.py mas customizado pra rodar por setor.

Uso:
    EMPRESA_ID=999 python scripts/cluster_per_setor.py [--setor ti] [--limit 5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langchain_core.messages import HumanMessage
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import close_pool, get_pool
from whatsapp_langchain.shared.llm import create_chat_model


SETORES = ["ti", "hospitalar", "financeiro", "diretoria", "operacional", "outro"]
MIN_CLUSTER_SIZE = 3
SIMILARITY_THRESHOLD = 0.78
MAX_QUERIES_PER_CLUSTER = 30
MAX_SUGGESTIONS_PER_SETOR = 10


def _cosine(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


async def fetch_msgs(pool, empresa_id: int, setor: str) -> list[tuple[int, str]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, cliente_msg
              FROM fewshot_example
             WHERE empresa_id = %s AND setor_classificado = %s
               AND char_length(cliente_msg) BETWEEN 10 AND 300
             LIMIT 1500
            """,
            (empresa_id, setor),
        )
        return [(int(r[0]), r[1]) for r in await cur.fetchall()]


async def embed_all(msgs: list[str]) -> list[list[float]]:
    api_key = settings.openrouter_api_key
    secret = SecretStr(api_key.get_secret_value()) if api_key else None
    embedder = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=secret,
        base_url=settings.openrouter_base_url,
    )
    # Batch de 100 (limite OpenAI)
    all_vecs = []
    for i in range(0, len(msgs), 100):
        chunk = msgs[i:i + 100]
        vecs = await embedder.aembed_documents(chunk)
        all_vecs.extend(vecs)
        print(f"    embed {i + len(chunk)}/{len(msgs)}")
    return all_vecs


def cluster_greedy(msgs: list[str], vecs: list[list[float]]) -> list[list[str]]:
    """Greedy single-linkage clustering."""
    used: set[int] = set()
    clusters: list[list[str]] = []
    for i, seed_vec in enumerate(vecs):
        if i in used:
            continue
        cluster = [msgs[i]]
        used.add(i)
        for j in range(i + 1, len(vecs)):
            if j in used:
                continue
            if _cosine(seed_vec, vecs[j]) >= SIMILARITY_THRESHOLD:
                cluster.append(msgs[j])
                used.add(j)
                if len(cluster) >= MAX_QUERIES_PER_CLUSTER:
                    break
        if len(cluster) >= MIN_CLUSTER_SIZE:
            clusters.append(cluster)
    clusters.sort(key=lambda c: -len(c))
    return clusters


async def generate_draft(setor: str, queries: list[str]) -> tuple[str, str]:
    queries_block = "\n".join(f"- {q}" for q in queries[:8])
    prompt = f"""Você é especialista em FAQ pra atendimento corporativo no setor {setor}.

Os clientes fizeram as perguntas abaixo e o agente NÃO encontrou resposta na base.
Crie UM documento que responda essas perguntas claramente.

Perguntas frequentes:
{queries_block}

Gere JSON com 2 campos:
- "titulo": curto (max 80 chars)
- "conteudo": resposta completa (200-500 chars), em parágrafos. Linguagem brasileira simples.
  Use placeholders [verificar com supervisor] pra dados específicos.

Saída APENAS o JSON."""

    llm = create_chat_model(model="openai/gpt-4o-mini", temperature=0.3, max_tokens=600)
    try:
        r = await llm.ainvoke([HumanMessage(content=prompt)])
        text = (r.content if isinstance(r.content, str) else str(r.content)).strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        return str(data.get("titulo", ""))[:200], str(data.get("conteudo", ""))[:2000]
    except Exception as e:
        print(f"    [draft fail] {e}")
        return f"FAQ {setor}: {queries[0][:60]}", queries[0]


async def get_pasta_id_for_setor(pool, setor: str) -> int | None:
    nome = f"KB Rádio {setor.capitalize()}" if setor != "ti" else "KB Rádio TI"
    if setor == "hospitalar":
        nome = "KB Rádio Hospitalar"
    elif setor == "financeiro":
        nome = "KB Rádio Financeiro"
    elif setor == "diretoria":
        nome = "KB Rádio Diretoria"
    elif setor == "operacional":
        nome = "KB Rádio Operacional"
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id FROM pasta WHERE empresa_id=999 AND nome=%s LIMIT 1",
            (nome,),
        )
        r = await cur.fetchone()
    return int(r[0]) if r else None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setor", default=None,
                        help="Apenas um setor (default: todos)")
    parser.add_argument("--limit", type=int, default=MAX_SUGGESTIONS_PER_SETOR)
    args = parser.parse_args()

    setores = [args.setor] if args.setor else SETORES
    pool = await get_pool()
    total_created = 0

    try:
        for setor in setores:
            print(f"\n=== Setor: {setor} ===")
            msgs_data = await fetch_msgs(pool, 999, setor)
            if len(msgs_data) < MIN_CLUSTER_SIZE:
                print(f"  [skip] só {len(msgs_data)} msgs (min={MIN_CLUSTER_SIZE})")
                continue
            print(f"  msgs: {len(msgs_data)}")

            msgs = [m[1] for m in msgs_data]
            print(f"  embedding...")
            vecs = await embed_all(msgs)
            print(f"  clustering...")
            clusters = cluster_greedy(msgs, vecs)
            print(f"  clusters: {len(clusters)} (min size {MIN_CLUSTER_SIZE})")

            pasta_id = await get_pasta_id_for_setor(pool, setor)
            print(f"  pasta_id: {pasta_id}")

            top_clusters = clusters[:args.limit]
            for i, cluster in enumerate(top_clusters):
                titulo, conteudo = await generate_draft(setor, cluster)
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        INSERT INTO documento_sugerido
                          (empresa_id, pasta_id, titulo, conteudo_draft,
                           queries_amostra, cluster_size, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                        """,
                        (999, pasta_id, titulo, conteudo,
                         cluster[:MAX_QUERIES_PER_CLUSTER], len(cluster)),
                    )
                    await conn.commit()
                print(f"    [{i+1}/{len(top_clusters)}] cluster {len(cluster)} → {titulo[:60]}")
                total_created += 1
    finally:
        await close_pool()

    print(f"\n=== TOTAL: {total_created} sugestões criadas ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
