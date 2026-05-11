"""Eval offline-first dos 8 agentes do menu (sandbox empresa 999).

Lê dataset LangSmith (read-only) OU goldens.json local, amostra balanceado
por agente_slug, invoca cada agente local, roda LLM-as-judge correctness
(binary + continuous), retorna dict + salva JSON local.

Judge continuous (Sprint Eval): CoT estruturada com `EVALUATION_STEPS` (5
passos) + `RUBRIC` 4 bandas → JSON `{score, reason}`. Inspirado em
`docs/eval-101/src/eval_101/geval_template_ptbr.py` mas sem dependência
DeepEval — usa LangChain ChatOpenAI direto.

Modos:
- `--source langsmith` (default): lê dataset via API
- `--source local`: lê `--goldens-file` (default docs/agente/eval-runs/goldens.json)
- `--export-goldens`: amostra do LangSmith, escreve goldens.json e sai

Função pública `evaluate_agentes(...)` (Sprint Eval-UI) é importada por
`tests/eval/test_eval_agentes_menu.py` pra rodar via pytest + Allure.

Uso CLI (dentro do container api):
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
from types import SimpleNamespace

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


# === Sprint Eval: judge continuous estruturado (CoT + rubric) ===
#
# Inspirado em eval-101 (docs/eval-101/src/eval_101/*).
# O prompt antigo era monolítico com critérios inline — agora está separado em
# CRITERIA + EVALUATION_STEPS (CoT explícita, 5 passos) + RUBRIC (4 bandas com
# expected_outcome verbal). Reduz variance do judge e produz `reason` rica.

CRITERIA = (
    "Avaliar se a RESPOSTA_DO_AGENTE atendeu a MENSAGEM_DO_CLIENTE em contexto "
    "hospitalar (Mackenzie Hospital Evangélico de Dourados), aceitando paráfrases "
    "e respostas diferentes da REFERENCIA quando o sentido estiver preservado. "
    "Penalizar contradições factuais, omissões importantes, jargão inadequado "
    "e respostas não-acionáveis."
)

EVALUATION_STEPS = [
    "Identifique a intenção principal da MENSAGEM_DO_CLIENTE.",
    "Compare os fatos da RESPOSTA_DO_AGENTE com a REFERENCIA "
    "(datas, valores, encaminhamentos).",
    "Verifique contradições ou informações inventadas (alucinação).",
    "Avalie se o cliente sai sabendo o próximo passo (acionabilidade).",
    "Não penalize diferenças de estilo, brevidade adequada, ou encaminhamento "
    "humano em casos complexos.",
]

RUBRIC = [
    (0, 2, "Irrelevante, contraditória ou prejudicial ao cliente."),
    (3, 5, "Parcialmente correta, com omissões importantes ou formulação vaga."),
    (
        6,
        8,
        "Majoritariamente correta, atende a necessidade com pequenas perdas "
        "de clareza.",
    ),
    (
        9,
        10,
        "Correta, completa, clara e acionável; equivalente ou melhor que a REFERENCIA.",
    ),
]


def build_continuous_prompt(cliente_msg: str, referencia: str, resposta: str) -> str:
    """Monta o prompt do judge continuous com CoT + rubric estruturada.

    Retorna string pronta pra `_judge_llm.ainvoke([HumanMessage(content=...)])`.
    O modelo deve devolver JSON `{"score": int 0-10, "reason": str pt-BR}`.
    """
    steps_txt = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(EVALUATION_STEPS))
    rubric_txt = "\n".join(f"- {lo}-{hi}: {outcome}" for lo, hi, outcome in RUBRIC)
    return (
        "Você é um avaliador criterioso de respostas de atendimento"
        " em português brasileiro.\n"
        "\n"
        "CRITÉRIO:\n"
        f"{CRITERIA}\n"
        "\n"
        "PASSOS DE AVALIAÇÃO (siga em ordem):\n"
        f"{steps_txt}\n"
        "\n"
        "RUBRICA (escala 0-10):\n"
        f"{rubric_txt}\n"
        "\n"
        "REGRAS:\n"
        "- Não use conhecimento externo; baseie-se apenas nas evidências do caso.\n"
        "- Aceite paráfrases quando o sentido estiver preservado.\n"
        "- Penalize alucinações (informação não suportada pela referência "
        "ou que claramente inventa fato).\n"
        "\n"
        "DADOS DO CASO:\n"
        f"MENSAGEM_DO_CLIENTE: {cliente_msg[:800]}\n"
        f"REFERENCIA: {referencia[:800]}\n"
        f"RESPOSTA_DO_AGENTE: {resposta[:800]}\n"
        "\n"
        "Retorne APENAS JSON válido com as chaves:\n"
        '- "score": inteiro entre 0 e 10\n'
        '- "reason": justificativa curta em pt-BR (1-2 frases, '
        "específica sobre acertos/omissões/contradições)\n"
        "\n"
        "Exemplo:\n"
        '{"score": 7, "reason": "Direciona ao setor correto mas omite '
        'o horário de funcionamento da referência."}\n'
        "\n"
        "JSON:"
    )


# === Sprint Eval: goldens.json offline ===
#
# Schema espelha LangSmith Example pra o loop principal não precisar mudar.
# Cada item: {name, inputs: {cliente_msg, setor, agente_slug},
#             outputs: {agente_resposta_esperada}, metadata: {fewshot_id, ...}}


def load_local_goldens(path: Path) -> list:
    """Carrega goldens.json e retorna lista de SimpleNamespace com mesma
    forma de `langsmith.schemas.Example` (inputs/outputs/metadata).
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        SimpleNamespace(
            inputs=item.get("inputs", {}),
            outputs=item.get("outputs", {}),
            metadata=item.get("metadata") or {},
        )
        for item in raw
    ]


def dump_goldens(samples: list, path: Path) -> None:
    """Escreve `samples` (list de Examples LangSmith ou SimpleNamespace
    compatível) em `path` no formato goldens.json.
    """
    payload = [
        {
            "name": f"fewshot-{(ex.metadata or {}).get('fewshot_id', i)}",
            "inputs": dict(ex.inputs or {}),
            "outputs": dict(ex.outputs or {}),
            "metadata": dict(ex.metadata or {}),
        }
        for i, ex in enumerate(samples)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


EMPRESA_ID = 999
DEFAULT_DATASET_V2 = "mackenzie-hospital-curated-v2"
OUTPUT_DIR = Path("/app") if Path("/app/src").exists() else Path.cwd()
DEFAULT_GOLDENS_PATH = (
    Path(__file__).parent.parent / "docs/agente/eval-runs/goldens.json"
)


def _resolve_samples_from_local(goldens_file: Path) -> tuple[list, str, str]:
    """Carrega samples de goldens.json local; retorna (samples, dataset_id, name)."""
    if not goldens_file.exists():
        raise FileNotFoundError(
            f"goldens local {goldens_file} não existe. "
            f"Rode `--export-goldens` primeiro."
        )
    samples = load_local_goldens(goldens_file)
    return samples, f"local:{goldens_file.name}", goldens_file.name


def _resolve_samples_from_langsmith(
    *,
    dataset_name: str,
    per_agent: int,
    max_pool: int,
    keep_saudacao: bool,
    verbose: bool = True,
) -> tuple[list, str, str, int]:
    """Lê dataset LangSmith + sampling balanceado.

    Retorna `(samples, dataset_id_str, dataset_name, n_descartados)`.
    Levanta `RuntimeError` se LANGCHAIN_API_KEY ausente.
    """
    api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        raise RuntimeError("LANGCHAIN_API_KEY ausente — modo langsmith exige.")

    from langsmith import Client

    client = Client(api_key=api_key)
    dataset = client.read_dataset(dataset_name=dataset_name)

    if verbose:
        print(f"Lendo até {max_pool} exemplos do dataset...")
    pool: dict[str, list] = defaultdict(list)
    discarded = 0
    for ex in client.list_examples(dataset_id=dataset.id, limit=max_pool):
        slug = (ex.inputs or {}).get("agente_slug") or "?"
        expected = (ex.outputs or {}).get("agente_resposta_esperada", "")
        if not keep_saudacao and is_saudacao_menu(expected):
            discarded += 1
            continue
        pool[slug].append(ex)

    if verbose:
        if discarded:
            print(f"⚠ Descartados {discarded} exemplos com expected=saudação/menu")
        print("Distribuição no pool (filtrado):")
        for slug, items in sorted(pool.items()):
            print(f"  {slug}: {len(items)}")

    samples: list = []
    for slug, items in sorted(pool.items()):
        if slug == "?":
            continue
        random.shuffle(items)
        samples.extend(items[:per_agent])

    return samples, str(dataset.id), dataset_name, discarded


async def evaluate_agentes(
    *,
    source: str = "local",
    per_agent: int = 3,
    max_pool: int = 1500,
    seed: int = 42,
    judge: str = "continuous",
    keep_saudacao: bool = False,
    dataset_name: str = DEFAULT_DATASET_V2,
    goldens_file: Path | None = None,
    filter_agente: str | None = None,
    verbose: bool = True,
) -> dict:
    """Roda eval programática (sem CLI). Retorna dict com `results`,
    `overall_continuous`, `overall_binary`, `by_agent_avg`, `total`.

    Usada por `tests/eval/test_eval_agentes_menu.py` (pytest) e por `main()`.

    Args:
        source: "local" (lê goldens.json) ou "langsmith" (lê dataset via API)
        per_agent: quantos exemplos amostrar por agente_slug
        filter_agente: se preenchido, filtra `samples` pra só esse slug
        judge: "binary" | "continuous" | "both"
    """
    random.seed(seed)
    if goldens_file is None:
        goldens_file = DEFAULT_GOLDENS_PATH

    # 1. Resolve samples
    if source == "local":
        samples, dataset_id_str, ds_name = _resolve_samples_from_local(goldens_file)
        if verbose:
            print(f"=== Eval Agentes Menu (LOCAL goldens, {len(samples)} exemplos) ===")
            print(f"goldens: {goldens_file}\n")
    elif source == "langsmith":
        if verbose:
            print("=== Eval Agentes Menu (sandbox 999) ===")
            print(f"dataset: {dataset_name}")
            print(f"per_agent: {per_agent}\n")
        samples, dataset_id_str, ds_name, _ = _resolve_samples_from_langsmith(
            dataset_name=dataset_name,
            per_agent=per_agent,
            max_pool=max_pool,
            keep_saudacao=keep_saudacao,
            verbose=verbose,
        )
        if verbose:
            print(f"\nTotal sampled: {len(samples)} (cap {per_agent}/agente)\n")
    else:
        raise ValueError(f"source inválido: {source}")

    # Filtra por agente_slug se requisitado (T.2)
    if filter_agente:
        samples = [
            s for s in samples if (s.inputs or {}).get("agente_slug") == filter_agente
        ]
        if verbose:
            print(f"Filtrado por agente_slug={filter_agente}: {len(samples)} ex")

    # 2. Loaders
    from langchain_core.messages import HumanMessage

    from whatsapp_langchain.agents.loader import load_graph
    from whatsapp_langchain.shared.agente import resolve_agente_runtime
    from whatsapp_langchain.shared.db import get_pool

    pool_db = await get_pool()

    # 3. Judges
    judge_binary = None
    if judge in ("binary", "both"):
        try:
            from openevals.llm import create_llm_as_judge
            from openevals.prompts import CORRECTNESS_PROMPT

            judge_binary = create_llm_as_judge(
                prompt=CORRECTNESS_PROMPT,
                model="openai:gpt-4o-mini",
                feedback_key="correctness",
            )
            if verbose:
                print("Judge binary: openevals correctness gpt-4o-mini")
        except ImportError:
            if verbose:
                print("WARN: openevals não instalado")

    judge_continuous = None
    if judge in ("continuous", "both"):
        from langchain_openai import ChatOpenAI

        _judge_llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=320,
        )

        async def judge_continuous(cliente_msg, referencia, resposta):
            prompt = build_continuous_prompt(cliente_msg, referencia, resposta)
            try:
                resp = await _judge_llm.ainvoke([HumanMessage(content=prompt)])
                content = resp.content.strip()
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:].strip()
                m = re.search(r"\{.*\}", content, re.S)
                if m:
                    data = json.loads(m.group(0))
                    raw = int(data.get("score", 0))
                    reason = data.get("reason") or data.get("rationale") or ""
                    return {
                        "score": max(0, min(10, raw)) / 10.0,
                        "reason": reason[:300],
                    }
            except Exception as e:
                return {"score": None, "reason": f"judge_error: {e}"}
            return {"score": None, "reason": "parse_failed"}

        if verbose:
            print(
                "Judge continuous: custom 0-10 (CoT + rubric) gpt-4o-mini "
                "[returns {score, reason}]"
            )
    if verbose:
        print()

    # 4. Loop
    results: list[dict] = []
    by_agent: dict[str, list[float]] = defaultdict(list)
    for i, ex in enumerate(samples, 1):
        slug = ex.inputs.get("agente_slug", "atendimento")
        cliente_msg = ex.inputs.get("cliente_msg", "")
        expected = (ex.outputs or {}).get("agente_resposta_esperada", "")
        if verbose:
            print(f"[{i}/{len(samples)}] {slug} :: {cliente_msg[:60]}", flush=True)

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
            if verbose:
                print(f"  ⚠️ ERROR: {error}")

        # Judges
        score_binary = None
        comment_binary = ""
        score_continuous = None
        reason_continuous = ""

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
                    reason_continuous = fb.get("reason", "")
                except Exception as e:
                    reason_continuous = f"judge_continuous_error: {e}"

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
                "reason_continuous": reason_continuous,
                "rationale_continuous": reason_continuous,  # compat shim
                "error": error,
            }
        )
        if verbose:
            sb = "—" if score_binary is None else f"{score_binary:.2f}"
            sc = "—" if score_continuous is None else f"{score_continuous:.2f}"
            print(f"  → bin={sb} cont={sc} resp={actual[:70]}")

    # 5. Agregados
    bin_scores = [r["score_binary"] for r in results if r["score_binary"] is not None]
    cont_scores = [
        r["score_continuous"] for r in results if r["score_continuous"] is not None
    ]
    overall_binary = sum(bin_scores) / len(bin_scores) if bin_scores else None
    overall_continuous = sum(cont_scores) / len(cont_scores) if cont_scores else None
    by_agent_avg = {slug: sum(s) / len(s) for slug, s in by_agent.items()}

    if verbose:
        print("\n=== SUMMARY ===")
        if bin_scores:
            ok = sum(1 for s in bin_scores if s >= 0.7)
            print(
                f"BINARY     overall avg: {overall_binary:.3f} "
                f"({ok}/{len(bin_scores)} ≥ 0.7)"
            )
        if cont_scores:
            ok = sum(1 for s in cont_scores if s >= 0.6)
            print(
                f"CONTINUOUS overall avg: {overall_continuous:.3f} "
                f"({ok}/{len(cont_scores)} ≥ 0.6)"
            )
        print("\nPor agente (continuous primário):")
        for slug in sorted(by_agent):
            scores = by_agent[slug]
            avg = sum(scores) / len(scores)
            ok = sum(1 for s in scores if s >= 0.6)
            print(f"  {slug:30s} avg={avg:.3f}  {ok}/{len(scores)} ≥ 0.6")

    return {
        "dataset": ds_name,
        "dataset_id": dataset_id_str,
        "source": source,
        "total": len(results),
        "per_agent_target": per_agent,
        "filter_agente": filter_agente,
        "overall_binary": overall_binary,
        "overall_continuous": overall_continuous,
        "by_agent_avg": by_agent_avg,
        "results": results,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET_V2)
    parser.add_argument("--per-agent", type=int, default=6)
    parser.add_argument("--max-pool", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=None)
    parser.add_argument("--keep-saudacao", action="store_true")
    parser.add_argument(
        "--judge", choices=["binary", "continuous", "both"], default="both"
    )
    parser.add_argument("--source", choices=["langsmith", "local"], default="langsmith")
    parser.add_argument("--export-goldens", action="store_true")
    parser.add_argument("--goldens-file", default=str(DEFAULT_GOLDENS_PATH))
    parser.add_argument(
        "--filter-agente",
        default=None,
        help="Se preenchido, filtra samples pra só esse agente_slug",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    # Early-exit: --export-goldens roda só amostragem LangSmith e salva
    if args.export_goldens:
        if args.source != "langsmith":
            print(
                "--export-goldens exige --source langsmith (default)",
                file=sys.stderr,
            )
            return 2
        random.seed(args.seed)
        samples, _, _, _ = _resolve_samples_from_langsmith(
            dataset_name=args.dataset,
            per_agent=args.per_agent,
            max_pool=args.max_pool,
            keep_saudacao=args.keep_saudacao,
            verbose=True,
        )
        out_path = Path(args.goldens_file)
        dump_goldens(samples, out_path)
        print(f"✓ Exportados {len(samples)} goldens para {out_path}")
        return 0

    try:
        result = await evaluate_agentes(
            source=args.source,
            per_agent=args.per_agent,
            max_pool=args.max_pool,
            seed=args.seed,
            judge=args.judge,
            keep_saudacao=args.keep_saudacao,
            dataset_name=args.dataset,
            goldens_file=Path(args.goldens_file),
            filter_agente=args.filter_agente,
            verbose=True,
        )
    except FileNotFoundError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    # 6. Save JSON
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.output) if args.output else OUTPUT_DIR / f"eval_results_{ts}.json"
    out.write_text(
        json.dumps(
            {
                **{k: v for k, v in result.items() if k != "results"},
                "timestamp": datetime.now().isoformat(),
                "results": result["results"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"\nJSON salvo em: {out}")

    from whatsapp_langchain.shared.db import close_pool

    await close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
