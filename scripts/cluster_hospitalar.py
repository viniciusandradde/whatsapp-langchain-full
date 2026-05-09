"""Sprint R.4 (revisado) — Clustering hospitalar por sub-setor.

Usa os 8 slugs do chat-nexus (atendimento, agendamentos, exames, etc).
Pra cada slug com >=10 fewshots:
- Embeda mensagens em batch (OpenAI)
- Greedy clustering por cosine ≥ 0.78
- Pra cada cluster com >=3 msgs, gera draft (titulo + conteudo) via LLM
- INSERT em documento_sugerido com pasta_id correto

Após terminar, admin aprova top-N na UI.

Uso:
    python scripts/cluster_hospitalar.py [--slug agendamentos] [--top 10]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langchain_core.messages import HumanMessage
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import close_pool, get_pool
from whatsapp_langchain.shared.llm import create_chat_model

SLUGS = [
    "atendimento", "atendimento-cliente", "agendamentos", "exames",
    "orcamento", "ouvidoria", "rh-recrutamento-selecao", "tesouraria",
]
MIN_CLUSTER_SIZE = 3
SIMILARITY_THRESHOLD = 0.78
MAX_PER_CLUSTER = 30
DEFAULT_TOP_N = 10

# Map slug → pasta_nome
PASTA_BY_SLUG = {
    "atendimento": "KB Atendimento",
    "atendimento-cliente": "KB Atendimento Cliente VSA",
    "agendamentos": "KB Agendamentos",
    "exames": "KB Exames",
    "orcamento": "KB Orçamento",
    "ouvidoria": "KB Ouvidoria",
    "rh-recrutamento-selecao": "KB Recrutamento",
    "tesouraria": "KB Tesouraria",
}


def _cosine(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


async def fetch_msgs(pool, empresa_id: int, slug: str, limit: int = 1500) -> list[str]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT cliente_msg FROM fewshot_example
             WHERE empresa_id = %s AND setor_classificado = %s
               AND char_length(cliente_msg) BETWEEN 10 AND 300
             ORDER BY id ASC
             LIMIT %s
            """,
            (empresa_id, slug, limit),
        )
        return [r[0] for r in await cur.fetchall()]


async def embed_all(msgs: list[str]) -> list[list[float]]:
    api_key = settings.openrouter_api_key
    secret = SecretStr(api_key.get_secret_value()) if api_key else None
    embedder = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=secret,
        base_url=settings.openrouter_base_url,
    )
    out = []
    for i in range(0, len(msgs), 100):
        chunk = msgs[i:i + 100]
        out.extend(await embedder.aembed_documents(chunk))
        print(f"    embed {i + len(chunk)}/{len(msgs)}", flush=True)
    return out


def cluster_greedy(msgs: list[str], vecs: list[list[float]]) -> list[list[str]]:
    used: set[int] = set()
    clusters: list[list[str]] = []
    for i, seed in enumerate(vecs):
        if i in used:
            continue
        cluster = [msgs[i]]
        used.add(i)
        for j in range(i + 1, len(vecs)):
            if j in used:
                continue
            if _cosine(seed, vecs[j]) >= SIMILARITY_THRESHOLD:
                cluster.append(msgs[j])
                used.add(j)
                if len(cluster) >= MAX_PER_CLUSTER:
                    break
        if len(cluster) >= MIN_CLUSTER_SIZE:
            clusters.append(cluster)
    return sorted(clusters, key=lambda c: -len(c))


async def generate_draft(slug: str, queries: list[str]) -> tuple[str, str]:
    queries_block = "\n".join(f"- {q}" for q in queries[:8])
    prompt = f"""Você é especialista em FAQ de hospital. Sub-setor: {slug}.

Pacientes/clientes fizeram as perguntas abaixo e o sistema NÃO encontrou
resposta na base. Crie UM documento de FAQ que responda essas perguntas
claramente em pt-BR.

Perguntas frequentes:
{queries_block}

Gere JSON com 2 campos:
- "titulo": curto, max 80 chars
- "conteudo": resposta completa (200-500 chars), em parágrafos. Tom
  acolhedor mas profissional, brasileiro. Use placeholders
  [verificar com supervisor] pra dados específicos do hospital.

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
        print(f"    [draft fail] {e}", flush=True)
        return f"FAQ {slug}: {queries[0][:60]}", queries[0]


async def get_pasta_id(pool, empresa_id: int, slug: str) -> int | None:
    nome = PASTA_BY_SLUG.get(slug)
    if not nome:
        return None
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id FROM pasta WHERE empresa_id=%s AND nome=%s LIMIT 1",
            (empresa_id, nome),
        )
        r = await cur.fetchone()
    return int(r[0]) if r else None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa-id", type=int, default=999)
    parser.add_argument("--slug", default=None,
                        help="Apenas um slug (default: todos)")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N,
                        help="Top-N clusters por slug a virar sugestão")
    args = parser.parse_args()

    slugs = [args.slug] if args.slug else SLUGS
    pool = await get_pool()
    total_created = 0

    try:
        for slug in slugs:
            print(f"\n=== {slug} ===", flush=True)
            msgs = await fetch_msgs(pool, args.empresa_id, slug)
            if len(msgs) < MIN_CLUSTER_SIZE:
                print(f"  [skip] só {len(msgs)} msgs", flush=True)
                continue
            print(f"  msgs: {len(msgs)}", flush=True)

            print(f"  embedding...", flush=True)
            vecs = await embed_all(msgs)
            print(f"  clustering...", flush=True)
            clusters = cluster_greedy(msgs, vecs)
            print(f"  clusters: {len(clusters)}", flush=True)

            pasta_id = await get_pasta_id(pool, args.empresa_id, slug)
            if not pasta_id:
                print(f"  [warn] pasta não encontrada para {slug}", flush=True)
                continue

            # Anti-dupe: preserva sugestões já criadas (qualquer status)
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT titulo, queries_amostra
                      FROM documento_sugerido
                     WHERE empresa_id = %s AND pasta_id = %s
                       AND status IN ('pending','approved','rejected')
                    """,
                    (args.empresa_id, pasta_id),
                )
                existing_rows = await cur.fetchall()
            existing_titles = {(r[0] or "").strip().lower() for r in existing_rows}
            existing_queries: set[str] = set()
            for r in existing_rows:
                for q in (r[1] or [])[:3]:
                    existing_queries.add(q.strip().lower()[:100])

            top_clusters = clusters[:args.top]
            skipped = 0
            for i, cluster in enumerate(top_clusters):
                titulo, conteudo = await generate_draft(slug, cluster)
                # Skip se duplicata
                title_lower = titulo.strip().lower()
                if title_lower in existing_titles:
                    skipped += 1
                    print(f"    [{i+1}/{len(top_clusters)}] SKIP dup-title → {titulo[:60]}", flush=True)
                    continue
                new_q = {q.strip().lower()[:100] for q in cluster[:3]}
                if len(new_q & existing_queries) >= 2:
                    skipped += 1
                    print(f"    [{i+1}/{len(top_clusters)}] SKIP dup-queries → {titulo[:60]}", flush=True)
                    continue
                # Add ao set imediatamente
                existing_titles.add(title_lower)
                for q in cluster[:3]:
                    existing_queries.add(q.strip().lower()[:100])
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        INSERT INTO documento_sugerido
                          (empresa_id, pasta_id, titulo, conteudo_draft,
                           queries_amostra, cluster_size, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                        """,
                        (args.empresa_id, pasta_id, titulo, conteudo,
                         cluster[:MAX_PER_CLUSTER], len(cluster)),
                    )
                    await conn.commit()
                print(f"    [{i+1}/{len(top_clusters)}] cluster_size={len(cluster)} → {titulo[:60]}", flush=True)
            if skipped > 0:
                print(f"    skipped {skipped} duplicates (preservou trabalho do admin)", flush=True)
                total_created += 1
    finally:
        await close_pool()

    print(f"\n=== TOTAL: {total_created} sugestões ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
