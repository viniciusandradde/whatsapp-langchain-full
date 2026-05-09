"""Sprint T.4 — Avalia agente real contra dataset LangSmith.

Pipeline:
1. Resolve dataset por nome
2. target() invoca o agente atendimento_completo
3. correctness evaluator (LLM-as-judge gpt-4o-mini)
4. client.evaluate(target, data, evaluators) → cria experiment
5. Imprime URL pra ver no smith.langchain.com

Custo: ~$0.001 por exemplo (gpt-4o-mini).
Recomendado --limit 50-100 pra controlar.

Uso:
    LANGCHAIN_API_KEY=ls_... OPENROUTER_API_KEY=sk-or-v1-...
    python scripts/eval_langsmith.py [--limit 100]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.shared.langsmith_sync import DEFAULT_DATASET_NAME


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET_NAME)
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Sample size pra controlar custo (default 50)",
    )
    parser.add_argument(
        "--experiment-prefix",
        default=f"atendimento-{datetime.now().strftime('%Y%m%d-%H%M')}",
    )
    parser.add_argument("--max-concurrency", type=int, default=4)
    args = parser.parse_args()

    api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        print("ERRO: LANGCHAIN_API_KEY não setada.", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    print("=== Sprint T.4 LangSmith Eval ===")
    print(f"dataset: {args.dataset}")
    print(f"limit: {args.limit}")
    print(f"experiment: {args.experiment_prefix}")
    print()

    from langsmith import Client

    client = Client(api_key=api_key)

    # 1. Resolve dataset
    try:
        dataset = client.read_dataset(dataset_name=args.dataset)
    except Exception as e:
        print(f"ERRO: dataset '{args.dataset}' não encontrado: {e}")
        print("Rode primeiro: python scripts/sync_dataset_to_langsmith.py")
        return 3
    print(f"dataset_id: {dataset.id}")

    # 2. Target — invoca agente atendimento_completo
    # Lazy import pra evitar carregar tudo se eval não rodar
    from langchain_core.messages import HumanMessage

    from whatsapp_langchain.agents.loader import load_graph
    from whatsapp_langchain.shared.agente import resolve_agente_runtime
    from whatsapp_langchain.shared.db import get_pool

    pool = await get_pool()
    EMPRESA_ID = 999  # sandbox

    async def target(inputs: dict) -> dict:
        cliente_msg = inputs.get("cliente_msg", "")
        agente_slug = inputs.get("agente_slug", "atendimento")
        try:
            runtime = await resolve_agente_runtime(pool, EMPRESA_ID, agente_slug)
            graph = await load_graph(
                agente_slug,
                checkpointer=None,
                store=None,
                pool=pool,
                empresa_id=EMPRESA_ID,
                agente_runtime=runtime,
            )
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=cliente_msg)]},
                config={
                    "configurable": {
                        "thread_id": f"eval-{cliente_msg[:30]}",
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
            response_text = result["messages"][-1].content
            return {"agente_resposta": response_text}
        except Exception as e:
            return {"agente_resposta": f"[ERROR] {str(e)[:200]}"}

    # 3. Evaluator — LLM-as-judge correctness
    def correctness_evaluator(run, example) -> dict:
        """Compara agente_resposta atual vs agente_resposta_esperada."""
        try:
            from openevals.llm import create_llm_as_judge
            from openevals.prompts import CORRECTNESS_PROMPT

            judge = create_llm_as_judge(
                prompt=CORRECTNESS_PROMPT,
                model="openai:gpt-4o-mini",
                feedback_key="correctness",
            )
            return judge(
                inputs=example.inputs,
                outputs=run.outputs or {},
                reference_outputs=example.outputs or {},
            )
        except ImportError:
            # Fallback simples: substring match
            actual = (run.outputs or {}).get("agente_resposta", "").lower()
            expected = (
                (example.outputs or {}).get("agente_resposta_esperada", "").lower()
            )
            score = 1.0 if expected[:30] in actual or actual[:30] in expected else 0.0
            return {"key": "correctness_substring", "score": score}

    # 4. Limita examples — pega só `args.limit` randomly
    print("\nIniciando eval (target + correctness)...")
    print(f"Custo estimado: ~${args.limit * 0.001:.3f} (gpt-4o-mini judge)")
    print()

    try:
        results = client.evaluate(
            target,
            data=client.list_examples(dataset_id=dataset.id, limit=args.limit),
            evaluators=[correctness_evaluator],
            experiment_prefix=args.experiment_prefix,
            max_concurrency=args.max_concurrency,
            metadata={"runner": "scripts/eval_langsmith.py"},
        )
    except Exception as e:
        print(f"ERRO no evaluate: {e}", file=sys.stderr)
        from whatsapp_langchain.shared.db import close_pool

        await close_pool()
        return 4

    print("\n=== RESULT ===")
    try:
        print(f"experiment_name: {results.experiment_name}")
    except Exception:
        pass
    # URL no LangSmith
    print(f"URL: https://smith.langchain.com/datasets/{dataset.id}")
    print()
    print("Abra no LangSmith pra ver scores por exemplo.")

    from whatsapp_langchain.shared.db import close_pool

    await close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
