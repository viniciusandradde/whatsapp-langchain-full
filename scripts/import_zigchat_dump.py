"""Sprint R.1 — Streaming importer do dump ZigChat (3 meses, 178MB).

Usa ijson pra parsear o array `atendimentos[]` sem carregar 178MB em RAM.
Pra cada atendimento, extrai o ULTIMO par (cliente_msg, agente_resposta_bot)
e popula:
- fewshot_example (status=pending pra embedding posterior)
- rag_query_log (mode=imported, com outcome calculado)

Outcome derivado:
- success: data_hora_finalizacao IS NOT NULL E sem operador humano (todas
           msgs com usuario=null) E qtde_resposta_invalida < 2
- transferred: alguma msg com usuario != null (humano assumiu)
- escalated: qtde_resposta_invalida >= 2
- abandoned: data_hora_finalizacao IS NULL E ultima_atividade > 24h atras
- unknown: ainda em curso

PII redact (CPF/email/telefone/cartao) aplicado em todas as mensagens via
shared/guardrails/pii_redactor.py mode='mask'.

Idempotente: cada atendimento tem zigchat_atendimento_id em metadata. Re-runs
skipam (UNIQUE-ish via SELECT antes do INSERT em batch).

Uso:
    python scripts/import_zigchat_dump.py \
        --file docs/dump_3m_2026-02-08_a_2026-05-08.json \
        --empresa-id 999 \
        --batch 1000 \
        [--limit 100]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import ijson

# Sprint U.1 — descarta mensagens system-generated do ZigChat que não são respostas
# substantivas. Identificadas durante eval (Sprint T): saudações de menu, transferências
# entre atendentes, NPS automático, status de bot, ack curtos, etc.
SYSTEM_GENERATED_RE = re.compile(
    r"(seja\s+bem.+vind|posi[cç][aã]o\s+\d+\s+da\s+fila|"
    r"central\s+de\s+atendimento\s+do|"
    r"^\s*aguarde\b|^\s*um\s+momento|"
    r"\b1\.\s*atendimento.+2\.\s*agend|"
    r"voc[eê]\s+foi\s+transferido\s+para|"
    r"transferindo\s+para\s+o?\s*atendente|"
    r"atribua\s+uma\s+nota\s+de\s+0|"
    r"avalie\s+o?\s*atendimento|"
    r"deseja\s+confirmar.+digite\s*\*?1\*?|"
    r"atendente\s+\*?\w+\*?\s+est[áa]\s+indispon[ií]vel|"
    r"fora\s+de\s+hor[áa]rio|"
    r"sua\s+mensagem\s+ser[áa]\s+respondida|"
    r"🔴|🟢|🟡|"
    r"^\s*(ok|tudo\s+bem|certo|obrigad[oa])\s*[!\.]*\s*$)",
    re.I | re.S,
)


def _is_system_generated(text: str) -> bool:
    """Retorna True se o texto é claramente uma mensagem automática do sistema
    (não uma resposta substantiva do bot ou atendente).
    """
    if not text or len(text.strip()) < 5:
        return True
    head = text[:300]
    return bool(SYSTEM_GENERATED_RE.search(head))


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.shared.db import close_pool, get_pool
from whatsapp_langchain.shared.guardrails.pii_redactor import redact_pii

# Map dept_id ZigChat -> nome legivel (placeholder; user pode ajustar)
DEPT_LABELS: dict[int, str] = {
    80: "Atendimento Geral",
    81: "TI",
    82: "Hospital",
    83: "Financeiro",
    87: "Diretoria",
    88: "Operacional",
    115: "RH",
    116: "Suporte",
    123: "Comercial",
    223: "Faturamento",
    288: "Cobranca",
    304: "Recepcao",
    355: "Auditoria",
    356: "Compliance",
    648: "Engenharia",
    741: "Manutencao",
}


def _hash_phone(phone: str) -> str:
    """Hash determinístico do telefone pra agrupar sem expor numero."""
    if not phone:
        return ""
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


def _extract_last_pair(mensagens: list[dict]) -> tuple[str | None, str | None]:
    """Pega ÚLTIMO par substantivo (cliente_msg, resposta).

    Sprint U.1: aceita resposta de BOT OU HUMANO, descartando system-generated
    (saudação/menu/transferência/NPS/status). Resposta humana é preferível porque
    tem contexto/julgamento — bot só responde substancialmente em casos automatizáveis.

    Algoritmo:
    - Itera mensagens em ordem cronológica
    - Marca pending_cliente quando vê msg do cliente (usuario=null AND automatica=false)
    - Quando vê resposta (automatica OR humano) com pending: avalia is_system_generated.
      Se substantiva → registra como último par; se system → reseta pending sem registrar.
    - Retorna o ÚLTIMO par válido encontrado (assume que é a resolução final).
    """
    if not mensagens:
        return None, None

    msgs = sorted(mensagens, key=lambda m: m.get("timestamp") or 0)
    last_pair: tuple[str, str] | None = None
    pending_cliente: str | None = None

    for m in msgs:
        body = (m.get("mensagem") or "").strip()
        if not body or len(body) < 3:
            continue
        if body.lower() in ("atendimento encerrado.", "ok", "."):
            continue

        is_auto = bool(m.get("automatica"))
        usuario = m.get("usuario")
        is_human_op = usuario is not None

        if not is_auto and not is_human_op:
            pending_cliente = body
        elif (is_auto or is_human_op) and pending_cliente:
            if not _is_system_generated(body):
                last_pair = (pending_cliente, body)
            pending_cliente = None

    if last_pair:
        return last_pair[0], last_pair[1]
    return None, None


def _detect_outcome(atendimento: dict) -> str:
    """Calcula outcome baseado no estado final do atendimento."""
    qtde_invalidas = atendimento.get("qtde_resposta_invalida") or 0
    finalizado = atendimento.get("data_hora_finalizacao")
    mensagens = atendimento.get("mensagens") or []
    has_human = any(m.get("usuario") is not None for m in mensagens)

    if has_human:
        return "transferred"
    if qtde_invalidas >= 2:
        return "escalated"
    if finalizado:
        return "success"
    # Aberto ainda — verifica se abandonado
    ultima = atendimento.get("data_hora_ultima_atividade")
    if ultima:
        try:
            ts = datetime.fromisoformat(ultima.replace("Z", "+00:00"))
            age_hours = (datetime.now(UTC) - ts).total_seconds() / 3600
            if age_hours > 24:
                return "abandoned"
        except (ValueError, AttributeError):
            pass
    return "unknown"


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def iter_atendimentos(file_path: Path) -> Iterator[dict]:
    """Stream parser — yields cada atendimento sem carregar tudo na RAM."""
    with file_path.open("rb") as f:
        # ijson.items('atendimentos.item') itera elementos do array `atendimentos`
        for atendimento in ijson.items(f, "atendimentos.item"):
            yield atendimento


async def fetch_already_imported_ids(pool, empresa_id: int) -> set[int]:
    """Preload zigchat_ids já importados (lê de metadata JSONB)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT (metadata->>'zigchat_atendimento_id')::bigint
              FROM fewshot_example
             WHERE empresa_id = %s
               AND metadata ? 'zigchat_atendimento_id'
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return {int(r[0]) for r in rows if r[0] is not None}


async def insert_batch(pool, rows: list[dict]) -> int:
    """Bulk INSERT em fewshot_example + rag_query_log via executemany."""
    if not rows:
        return 0
    import json as _json

    fewshot_params = [
        (
            r["empresa_id"],
            r["agente_slug"],
            r["cliente_msg"][:1000],
            r["agente_resposta"][:1500],
            r["outcome"],
            _json.dumps({"zigchat_atendimento_id": r["zigchat_atendimento_id"]}),
            r["created_at"],
        )
        for r in rows
    ]
    log_params = [
        (
            r["empresa_id"],
            r["cliente_msg"][:500],
            r["agente_slug"],
            1 if r["agente_resposta"] else 0,
            r["outcome"],
            r["created_at"],
        )
        for r in rows
    ]
    async with pool.connection() as conn:
        try:
            cur = conn.cursor()
            await cur.executemany(
                """
                INSERT INTO fewshot_example
                  (empresa_id, agente_slug, cliente_msg, agente_resposta,
                   outcome, metadata, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'pending',
                        COALESCE(%s, NOW()))
                """,
                fewshot_params,
            )
            await cur.executemany(
                """
                INSERT INTO rag_query_log
                  (empresa_id, query_text, agente_slug, hits, top_score,
                   outcome, mode, created_at)
                VALUES (%s, %s, %s, %s, NULL, %s, 'imported',
                        COALESCE(%s, NOW()))
                """,
                log_params,
            )
            await conn.commit()
            return len(rows)
        except Exception as e:
            await conn.rollback()
            print(f"  [batch error] {e}")
            return 0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--empresa-id", type=int, default=999)
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument(
        "--limit", type=int, default=0, help="Limita atendimentos processados (0=todos)"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        return 2

    print("=== Sprint R.1 ZigChat Importer ===")
    print(f"file: {args.file}")
    print(f"empresa_id: {args.empresa_id}")
    print(f"batch: {args.batch}")
    print(f"dry-run: {args.dry_run}")
    print()

    pool = await get_pool() if not args.dry_run else None

    # Preload IDs já importados pra check in-memory (evita N queries)
    already_ids: set[int] = set()
    if pool:
        already_ids = await fetch_already_imported_ids(pool, args.empresa_id)
        print(f"[preload] {len(already_ids)} IDs já importados (skip)")

    stats = {
        "seen": 0,
        "skip_no_pair": 0,  # nenhum par cliente-resposta substantivo encontrado
        "skip_already": 0,
        "by_outcome": {},
        "by_dept": {},
        "inserted": 0,
        "errors": 0,
    }
    batch: list[dict] = []

    try:
        for atendimento in iter_atendimentos(args.file):
            stats["seen"] += 1
            if args.limit and stats["seen"] > args.limit:
                break

            zigchat_id = atendimento.get("id")
            if not zigchat_id:
                continue

            # Idempotencia (in-memory check, super rápido)
            if zigchat_id in already_ids:
                stats["skip_already"] += 1
                continue

            cliente_msg, bot_resp = _extract_last_pair(
                atendimento.get("mensagens") or []
            )
            if not cliente_msg or not bot_resp:
                stats["skip_no_pair"] += 1
                continue

            # PII redact
            cliente_msg_redacted = redact_pii(cliente_msg, mode="mask").text
            bot_resp_redacted = redact_pii(bot_resp, mode="mask").text

            outcome = _detect_outcome(atendimento)
            stats["by_outcome"][outcome] = stats["by_outcome"].get(outcome, 0) + 1

            dept_id = atendimento.get("departamento_id")
            dept_label = DEPT_LABELS.get(dept_id, "outro") if dept_id else "outro"
            stats["by_dept"][dept_label] = stats["by_dept"].get(dept_label, 0) + 1

            # agente_slug derivado do dept (placeholder — R.2 reclassifica)
            slug_safe = (
                dept_label.lower()
                .replace(" ", "-")
                .replace("ç", "c")
                .replace("ã", "a")
                .replace("á", "a")
                .replace("ó", "o")
                .replace("ô", "o")
                .replace("é", "e")
                .replace("ê", "e")
                .replace("í", "i")
                .replace("ú", "u")
            )
            agente_slug = f"radio-{slug_safe}"

            row = {
                "empresa_id": args.empresa_id,
                "agente_slug": agente_slug,
                "cliente_msg": cliente_msg_redacted,
                "agente_resposta": bot_resp_redacted,
                "outcome": outcome,
                "zigchat_atendimento_id": zigchat_id,
                "created_at": _parse_iso(atendimento.get("data_hora_criacao")),
            }
            batch.append(row)

            if len(batch) >= args.batch:
                if not args.dry_run:
                    n = await insert_batch(pool, batch)
                    stats["inserted"] += n
                batch.clear()
                print(
                    f"  [{stats['seen']:>5}] seen, {stats['inserted']} inserted, "
                    f"{stats['skip_no_pair']} no-pair, {stats['skip_already']} dup"
                )

        # Flush
        if batch and not args.dry_run:
            n = await insert_batch(pool, batch)
            stats["inserted"] += n

    finally:
        if pool:
            await close_pool()

    print()
    print("=== FINAL ===")
    print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
