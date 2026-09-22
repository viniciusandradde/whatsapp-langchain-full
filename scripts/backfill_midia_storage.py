"""Backfill da mídia base64 → object storage (Fase C do plano de 2026-09-15).

Move a mídia que já está gravada **inteira em base64** em
`message_queue.media_url` (`data:<mime>;base64,...`) para o bucket S3: sobe o
objeto (tabela `arquivo`), grava `media_arquivo_uuid` na linha e zera
`media_url`. Reclama os ~861 MB medidos em produção. Espelha exatamente o que o
webhook da Fase B passou a fazer para mídia nova.

Roda **o dono, em produção** — o classificador do harness barra escrita em
massa em prod para o assistente (mesma restrição da limpeza dos checkpoints).

Propriedades:
- **Idempotente**: só toca linhas com `media_url LIKE 'data:%'` E
  `media_arquivo_uuid IS NULL`; rodar de novo continua de onde parou.
- **Por empresa**: o INSERT em `arquivo` tem RLS — cada empresa é processada no
  próprio `empresa_scope`, então a linha do bucket nasce com o `empresa_id`
  certo.
- **Por lote**, com commit por linha (uma mídia problemática não desfaz o lote)
  e pausa configurável entre lotes (não sufoca o banco em horário de pico).
- **`--dry-run`**: só conta e mede, não escreve nada nem sobe objeto.

Uso (dentro do container da API/worker em produção):
    python -m scripts.backfill_midia_storage --dry-run
    python -m scripts.backfill_midia_storage                 # tudo
    python -m scripts.backfill_midia_storage --empresa 1     # só a empresa 1
    python -m scripts.backfill_midia_storage --batch 50 --sleep 0.5 --limit 500

Pré-requisitos: `storage_ativo()` verdadeiro (S3_* setados) e o MinIO de pé —
o script aborta se o storage não estiver configurado.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import sys


def _parse_data_url(media_url: str) -> tuple[str | None, bytes] | None:
    """`data:<mime>;base64,<payload>` → (mime, bytes). None se não casar."""
    if not media_url.startswith("data:"):
        return None
    try:
        cabecalho, payload = media_url[len("data:") :].split(",", 1)
    except ValueError:
        return None
    if ";base64" not in cabecalho:
        return None
    mime = cabecalho.split(";", 1)[0].strip() or None
    try:
        conteudo = base64.b64decode(payload)
    except Exception:
        return None
    return mime, conteudo


async def _empresas_com_pendencia(pool, empresa_filtro: int | None) -> list[int]:
    from whatsapp_langchain.shared.rls_context import empresa_scope

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            if empresa_filtro is not None:
                cur = await conn.execute(
                    # '%%' escapado: a query também usa %s, então o % literal do
                    # LIKE tem que ser dobrado (psycopg pyformat).
                    "SELECT DISTINCT empresa_id FROM message_queue "
                    "WHERE media_url LIKE 'data:%%' AND media_arquivo_uuid IS NULL "
                    "AND empresa_id = %s",
                    (empresa_filtro,),
                )
            else:
                cur = await conn.execute(
                    "SELECT DISTINCT empresa_id FROM message_queue "
                    "WHERE media_url LIKE 'data:%' AND media_arquivo_uuid IS NULL "
                    "ORDER BY empresa_id"
                )
            rows = await cur.fetchall()
    return [int(r[0]) for r in rows if r and r[0] is not None]


async def _proximo_lote(
    pool, empresa_id: int, batch: int, depois_de_id: int
) -> list[tuple]:
    """Lote de (id, media_url, media_filename) pendentes da empresa com
    `id > depois_de_id`.

    Keyset pagination na PK: cada lote avança o cursor, então (1) o dry-run
    termina mesmo sem migrar nada — sem cursor, o mesmo lote voltaria pra
    sempre — e (2) o run real não re-varre desde o início a cada lote (evita
    O(n²) numa tabela grande de base64).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            # '%%' escapado (a query usa %s — ver _empresas_com_pendencia).
            "SELECT id, media_url, media_filename FROM message_queue "
            "WHERE empresa_id = %s AND id > %s AND media_url LIKE 'data:%%' "
            "AND media_arquivo_uuid IS NULL "
            "ORDER BY id LIMIT %s",
            (empresa_id, depois_de_id, batch),
        )
        return await cur.fetchall()


async def backfill(
    *,
    dry_run: bool,
    batch: int,
    sleep: float,
    limit: int | None,
    empresa_filtro: int | None,
) -> dict[str, int]:
    from whatsapp_langchain.shared import storage
    from whatsapp_langchain.shared.db import get_pool
    from whatsapp_langchain.shared.rls_context import empresa_scope

    if not storage.storage_ativo():
        print("ERRO: storage não configurado (S3_* / MinIO). Abortando.")
        sys.exit(2)

    pool = await get_pool()
    empresas = await _empresas_com_pendencia(pool, empresa_filtro)
    print(f"Empresas com mídia base64 pendente: {len(empresas)} -> {empresas}")

    migradas = 0
    bytes_reclamados = 0
    erros = 0

    for eid in empresas:
        cursor = 0  # keyset: maior id já visto nesta empresa
        while True:
            if limit is not None and migradas >= limit:
                break
            with empresa_scope(empresa_id=eid):
                lote = await _proximo_lote(pool, eid, batch, cursor)
            if not lote:
                break
            cursor = int(lote[-1][0])  # avança o cursor (dry-run também termina)

            for mq_id, media_url, media_filename in lote:
                if limit is not None and migradas >= limit:
                    break
                parsed = _parse_data_url(media_url or "")
                if parsed is None:
                    print(f"  [skip] mq {mq_id}: media_url não é data:base64")
                    continue
                mime, conteudo = parsed

                if dry_run:
                    migradas += 1
                    bytes_reclamados += len(conteudo)
                    continue

                try:
                    with empresa_scope(empresa_id=eid):
                        arq = await storage.guardar_midia(
                            pool, eid, conteudo, mime, media_filename
                        )
                        async with pool.connection() as conn:
                            await conn.execute(
                                "UPDATE message_queue SET media_arquivo_uuid = %s, "
                                "media_url = NULL WHERE id = %s",
                                (arq.uuid, mq_id),
                            )
                            await conn.commit()
                    migradas += 1
                    bytes_reclamados += len(conteudo)
                except Exception as exc:  # noqa: BLE001
                    erros += 1
                    print(f"  [ERRO] mq {mq_id} (empresa {eid}): {str(exc)[:200]}")

            print(
                f"  empresa {eid}: migradas={migradas} "
                f"reclamado={bytes_reclamados / 1_048_576:.1f} MB erros={erros}"
            )
            if sleep > 0 and not dry_run:
                await asyncio.sleep(sleep)

    resumo = {
        "migradas": migradas,
        "bytes_reclamados": bytes_reclamados,
        "erros": erros,
    }
    print(
        f"\n{'[DRY-RUN] ' if dry_run else ''}FIM: {migradas} mídias, "
        f"{bytes_reclamados / 1_048_576:.1f} MB, {erros} erros."
    )
    return resumo


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill mídia base64 → object storage")
    ap.add_argument("--dry-run", action="store_true", help="só conta/mede, não escreve")
    ap.add_argument("--batch", type=int, default=100, help="linhas por lote")
    ap.add_argument("--sleep", type=float, default=0.2, help="pausa (s) entre lotes")
    ap.add_argument("--limit", type=int, default=None, help="teto de mídias migradas")
    ap.add_argument(
        "--empresa", type=int, default=None, help="processa só esta empresa"
    )
    args = ap.parse_args()

    asyncio.run(
        backfill(
            dry_run=args.dry_run,
            batch=args.batch,
            sleep=args.sleep,
            limit=args.limit,
            empresa_filtro=args.empresa,
        )
    )


if __name__ == "__main__":
    main()
