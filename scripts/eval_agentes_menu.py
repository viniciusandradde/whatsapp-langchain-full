"""Eval offline-first dos 8 agentes do menu (sandbox empresa 999).

Lê dataset LangSmith (read-only), amostra balanceado por agente_slug, invoca
cada agente local, roda LLM-as-judge correctness, salva JSON local com tudo.
Tenta também sincronizar pro LangSmith (best-effort — silencia 429).

Uso (dentro do container api):
    OPENAI_API_KEY=$OPENROUTER_API_KEY \
    OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
    python /app/eval_agentes_menu.py --per-agent 6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Regex pra descartar exemplos onde o "expected" é apenas ruído operacional —
# resíduo do importer Sprint R/S: 1º turno do atendente é menu, transferência ou NPS.
SAUDACAO_RE = re.compile(
    r"(seja\s+bem.+vind|posi[cç][aã]o\s+\d+\s+da\s+fila|"
    r"central\s+de\s+atendimento\s+do|"
    r"^\s*aguarde\b|^\s*um\s+momento|"
    r"\b1\.\s*atendimento.+2\.\s*agend|"
    # transferência interna entre atendentes
    r"voc[eê]\s+foi\s+transferido\s+para|"
    r"transferindo\s+para\s+o?\s*atendente|"
    # NPS automático ao fim do atendimento
    r"atribua\s+uma\s+nota\s+de\s+0|"
    r"avalie\s+o?\s*atendimento|"
    r"deseja\s+confirmar.+digite\s*\*?1\*?|"
    # status automático de bot (atendente indisponível, fora de horário, etc)
    r"atendente\s+\*?\w+\*?\s+est[áa]\s+indispon[ií]vel|"
    r"fora\s+de\s+hor[áa]rio|"
    r"sua\s+mensagem\s+ser[áa]\s+respondida|"
    r"🔴|🟢|🟡|"
    # ack curto sem conteúdo
    r"^\s*(ok|tudo\s+bem|certo|obrigad[oa])\s*[!\.]*\s*$)",
    re.I | re.S,
)


def is_saudacao_menu(text: str) -> bool:
    if not text or len(text.strip()) < 10:
        return True
    head = text[:300]
    return bool(SAUDACAO_RE.search(head))


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


EMPRESA_ID = 999
DEFAULT_DATASET_V2 = "mackenzie-hospital-curated-v2"
OUTPUT_DIR = Path("/app") if Path("/app/src").exists() else Path.cwd()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET_V2)
    parser.add_argument(
        "--per-agent",
        type=int,
        default=6,
        help="Quantos exemplos por agente_slug (8 agentes × 6 = 48 total)",
    )
    parser.add_argument(
        "--max-pool",
        type=int,
        default=500,
        help="Quantos exemplos do dataset percorrer pra fazer sampling balanceado",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--keep-saudacao",
        action="store_true",
        help="NÃO filtrar exemplos com expected = saudação/menu (default: filtrar)",
    )
    parser.add_argument(
        "--judge",
        choices=["binary", "continuous", "both"],
        default="both",
        help="binary=openevals strict; continuous=custom 0-10 helpful; both=ambos",
    )
    args = parser.parse_args()

    api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        print("ERRO: LANGCHAIN_API_KEY ausente", file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.WARNING)
    random.seed(args.seed)

    print("=== Eval Agentes Menu (sandbox 999) ===")
    print(f"dataset: {args.dataset}")
    print(f"per_agent: {args.per_agent}\n")

    from langsmith import Client

    client = Client(api_key=api_key)
    dataset = client.read_dataset(dataset_name=args.dataset)

    # 1. Sampling balanceado: lê pool grande, agrupa por agente_slug, pega N de cada
    print(f"Lendo até {args.max_pool} exemplos do dataset...")
    pool: dict[str, list] = defaultdict(list)
    discarded_saudacao = 0
    for ex in client.list_examples(dataset_id=dataset.id, limit=args.max_pool):
        slug = (ex.inputs or {}).get("agente_slug") or "?"
        expected = (ex.outputs or {}).get("agente_resposta_esperada", "")
        if not args.keep_saudacao and is_saudacao_menu(expected):
            discarded_saudacao += 1
            continue
        pool[slug].append(ex)

    if discarded_saudacao:
        print(f"⚠ Descartados {discarded_saudacao} exemplos com expected=saudação/menu")
    print("Distribuição no pool (filtrado):")
    for slug, items in sorted(pool.items()):
        print(f"  {slug}: {len(items)}")

    samples: list = []
    for slug, items in sorted(pool.items()):
        if slug == "?":
            continue
        random.shuffle(items)
        samples.extend(items[: args.per_agent])
    print(f"\nTotal sampled: {len(samples)} (cap {args.per_agent}/agente)\n")

    # 2. Loaders
    from langchain_core.messages import HumanMessage

    from whatsapp_langchain.agents.loader import load_graph
    from whatsapp_langchain.shared.agente import resolve_agente_runtime
    from whatsapp_langchain.shared.db import close_pool, get_pool

    pool_db = await get_pool()

    # 3. Judges
    judge_binary = None
    if args.judge in ("binary", "both"):
        try:
            from openevals.llm import create_llm_as_judge
            from openevals.prompts import CORRECTNESS_PROMPT

            judge_binary = create_llm_as_judge(
                prompt=CORRECTNESS_PROMPT,
                model="openai:gpt-4o-mini",
                feedback_key="correctness",
            )
            print("Judge binary: openevals correctness gpt-4o-mini")
        except ImportError:
            print("WARN: openevals não instalado")

    judge_continuous = None
    if args.judge in ("continuous", "both"):
        from langchain_openai import ChatOpenAI

        _judge_llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=200,
        )
        CONTINUOUS_PROMPT = """Você é um avaliador imparcial de respostas de um agente de IA \
hospitalar (Mackenzie Hospital Evangélico de Dourados).

Sua tarefa: avaliar de 0 a 10 quão bem a RESPOSTA_DO_AGENTE atendeu a MENSAGEM_DO_CLIENTE,
considerando que a REFERENCIA é apenas um exemplo histórico — pode haver respostas igualmente
válidas ou MELHORES que sejam diferentes da referência.

CRITÉRIOS:
- 0-2: Irrelevante, errado ou prejudicial.
- 3-5: Tópico certo mas incompleto, vago ou sem informação útil.
- 6-7: Atende à necessidade do cliente, mesmo se diferente da referência.
- 8-9: Resposta clara, correta e útil; melhor ou igual à referência.
- 10: Excelente — completa, precisa, empática e acionável.

Considere:
- Pertinência ao pedido (resolveu o que foi perguntado?)
- Tom apropriado pra hospital (cordial, claro, sem jargão excessivo)
- Acionabilidade (o cliente sabe o próximo passo?)
- Faithfulness (não inventa info — se incerto, encaminha pra humano é OK)

NÃO penalize por:
- Diferença textual com a REFERENCIA se a resposta resolve o problema
- Brevidade quando o cliente fez pergunta simples
- Encaminhar pra atendente humano em casos complexos (é o comportamento correto)

Retorne APENAS um JSON válido:
{{"score": <inteiro 0-10>, "rationale": "<1 frase em pt-BR>"}}

DADOS:
MENSAGEM_DO_CLIENTE: {cliente_msg}
REFERENCIA: {referencia}
RESPOSTA_DO_AGENTE: {resposta}
"""

        async def judge_continuous(cliente_msg, referencia, resposta):
            from langchain_core.messages import HumanMessage

            prompt = CONTINUOUS_PROMPT.format(
                cliente_msg=cliente_msg[:800],
                referencia=referencia[:800],
                resposta=resposta[:800],
            )
            try:
                resp = await _judge_llm.ainvoke([HumanMessage(content=prompt)])
                content = resp.content.strip()
                # Extrai JSON
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:].strip()
                m = re.search(r"\{[^{}]+\}", content, re.S)
                if m:
                    data = json.loads(m.group(0))
                    raw = int(data.get("score", 0))
                    return {
                        "score": max(0, min(10, raw)) / 10.0,
                        "rationale": data.get("rationale", "")[:200],
                    }
            except Exception as e:
                return {"score": None, "rationale": f"judge_error: {e}"}
            return {"score": None, "rationale": "parse_failed"}

        print("Judge continuous: custom 0-10 helpful gpt-4o-mini")
    print()

    # 4. Loop
    results = []
    by_agent: dict[str, list[float]] = defaultdict(list)
    for i, ex in enumerate(samples, 1):
        slug = ex.inputs.get("agente_slug", "atendimento")
        cliente_msg = ex.inputs.get("cliente_msg", "")
        expected = (ex.outputs or {}).get("agente_resposta_esperada", "")
        print(f"[{i}/{len(samples)}] {slug} :: {cliente_msg[:60]}", flush=True)

        # Invoca agente
        try:
            runtime = await resolve_agente_runtime(pool_db, EMPRESA_ID, slug)
            graph = await load_graph(
                slug,
                checkpointer=None,
                store=None,
                pool=pool_db,
                empresa_id=EMPRESA_ID,
                agente_runtime=runtime,
            )
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=cliente_msg)]},
                config={
                    "configurable": {
                        "thread_id": f"eval-menu-{i}",
                        "user_id": "eval-langsmith",
                        "empresa_id": EMPRESA_ID,
                        "atendimento_id": None,
                        "media_url": None,
                        "media_type": None,
                        "base_conhecimento_ids": runtime.base_conhecimento_ids
                        if runtime
                        else [],
                    }
                },
            )
            actual = result["messages"][-1].content
            error = None
        except Exception as e:
            actual = ""
            error = f"{type(e).__name__}: {e}"
            print(f"  ⚠️ ERROR: {error}")

        # Judges
        score_binary = None
        comment_binary = ""
        score_continuous = None
        rationale_continuous = ""

        if actual:
            if judge_binary:
                try:
                    fb = judge_binary(
                        inputs={"cliente_msg": cliente_msg},
                        outputs={"agente_resposta": actual},
                        reference_outputs={"agente_resposta_esperada": expected},
                    )
                    raw = fb.get("score")
                    score_binary = float(raw) if raw is not None else None
                    comment_binary = (fb.get("comment") or "")[:200]
                except Exception as e:
                    comment_binary = f"judge_binary_error: {e}"

            if judge_continuous:
                try:
                    fb = await judge_continuous(cliente_msg, expected, actual)
                    score_continuous = fb.get("score")
                    rationale_continuous = fb.get("rationale", "")
                except Exception as e:
                    rationale_continuous = f"judge_continuous_error: {e}"

        # Métrica primária pra agregação: continuous se disponível, senão binary
        primary_score = (
            score_continuous if score_continuous is not None else score_binary
        )
        if primary_score is not None:
            by_agent[slug].append(float(primary_score))

        results.append(
            {
                "fewshot_id": (ex.metadata or {}).get("fewshot_id"),
                "agente_slug": slug,
                "setor": ex.inputs.get("setor"),
                "cliente_msg": cliente_msg,
                "expected": expected,
                "actual": actual,
                "score_binary": score_binary,
                "score_continuous": score_continuous,
                "comment_binary": comment_binary,
                "rationale_continuous": rationale_continuous,
                "error": error,
            }
        )
        sb = "—" if score_binary is None else f"{score_binary:.2f}"
        sc = "—" if score_continuous is None else f"{score_continuous:.2f}"
        print(f"  → bin={sb} cont={sc} resp={actual[:70]}")

    # 5. Summary
    print("\n=== SUMMARY ===")
    bin_scores = [r["score_binary"] for r in results if r["score_binary"] is not None]
    cont_scores = [
        r["score_continuous"] for r in results if r["score_continuous"] is not None
    ]
    if bin_scores:
        avg = sum(bin_scores) / len(bin_scores)
        ok = sum(1 for s in bin_scores if s >= 0.7)
        print(f"BINARY     overall avg: {avg:.3f} ({ok}/{len(bin_scores)} ≥ 0.7)")
    if cont_scores:
        avg = sum(cont_scores) / len(cont_scores)
        ok = sum(1 for s in cont_scores if s >= 0.6)
        print(f"CONTINUOUS overall avg: {avg:.3f} ({ok}/{len(cont_scores)} ≥ 0.6)")
    print("\nPor agente (continuous primário):")
    for slug in sorted(by_agent):
        scores = by_agent[slug]
        avg = sum(scores) / len(scores)
        ok = sum(1 for s in scores if s >= 0.6)
        print(f"  {slug:30s} avg={avg:.3f}  {ok}/{len(scores)} ≥ 0.6")

    # 6. Save JSON
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.output) if args.output else OUTPUT_DIR / f"eval_results_{ts}.json"
    out.write_text(
        json.dumps(
            {
                "dataset": args.dataset,
                "dataset_id": str(dataset.id),
                "timestamp": datetime.now().isoformat(),
                "per_agent_target": args.per_agent,
                "total": len(results),
                "by_agent_avg": {slug: sum(s) / len(s) for slug, s in by_agent.items()},
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"\nJSON salvo em: {out}")

    await close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
