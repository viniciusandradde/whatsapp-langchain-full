#!/usr/bin/env python3
"""Etapa 0 do ADR-002 — concede via PERFIL o que o `role` concede hoje.

Pré-requisito da Decisão 2/3 (`is_admin_of` derivar de permissão). Sem isso,
trocar o gate tira o acesso administrativo de quem depende só do
`empresa_membro.role`.

⚠️ O número "8 de 11 membros em produção", da primeira medição, **contava
superadmins** — e `is_admin_of` checa `is_superadmin` ANTES do role, então para
esses não existe divergência possível. O raio-X foi corrigido para separá-los;
o risco real em produção precisa ser **remedido** com a versão nova antes de
tratar a Etapa 3 como bloqueada. No dev, depois desta migração: divergência 0.

    uv run python scripts/migrar_role_para_perfil.py              # dry-run (padrão)
    uv run python scripts/migrar_role_para_perfil.py --apply
    uv run python scripts/migrar_role_para_perfil.py --empresa 1018
    uv run python scripts/migrar_role_para_perfil.py --json

**Nunca remove nada.** Só cria perfil system que falta e insere linha em
`usuario_perfil`. A coluna `role` não é tocada (fallback + rollback).

## Duas coisas acontecem, e a segunda não é óbvia

1. **Atribuição** — membro sem perfil nenhum ganha o perfil equivalente ao
   `role`. Para quem já resolvia pelo fallback legado, o conjunto efetivo de
   permissões **não muda**: só deixa de ser implícito.

2. **Seed** — `seed_default_perfis` só roda para a empresa 1 no boot
   (`server/main.py`), então as demais nunca ganharam os 4 perfis system. Nessas
   empresas o fallback legado procura o perfil "Admin"/"Operador" pelo nome,
   **não acha, e devolve conjunto vazio**: hoje esses membros passam em tudo que
   é gateado por `is_admin_of` e são barrados em tudo que exige
   `require_permission`. Criar o perfil **já muda o efetivo** — mesmo antes de
   atribuir — porque conserta o fallback. Isso é ALARGAMENTO real, e é o que a
   Etapa 0 se propõe a fazer: dar via perfil o que o role sempre significou.

O dry-run mostra o alargamento usuário a usuário justamente para essa decisão
ser tomada com o número na frente, não por confiança no rótulo "só concede".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from whatsapp_langchain.shared.perfil import LEGACY_ROLE_TO_PERFIL  # noqa: E402
from whatsapp_langchain.shared.permissoes import (  # noqa: E402
    CATALOGO,
    PERFIS_SYSTEM,
)

# Permissão que `is_admin_of` passa a exigir na Etapa 3 (Decisão 1 do ADR-002).
PERM_ADMIN = "empresa.update"


async def _carregar(conn, empresa_filtro: int | None) -> dict:
    """Fotografa o estado atual: empresas, perfis, permissões e membros."""
    filtro = "WHERE m.empresa_id = %s" if empresa_filtro else ""
    args = (empresa_filtro,) if empresa_filtro else ()

    membros = await (
        await conn.execute(
            f"""
            SELECT m.empresa_id, m.user_id, m.role,
                   COALESCE(u.is_superadmin, FALSE)
              FROM empresa_membro m
              LEFT JOIN auth."user" u ON u.id = m.user_id
              {filtro}
             ORDER BY m.empresa_id, m.user_id
            """,
            args,
        )
    ).fetchall()

    perfis = await (
        await conn.execute("SELECT id, empresa_id, nome, is_system FROM perfil_acesso")
    ).fetchall()
    # `perfil_acesso` tem UNIQUE(empresa_id, nome) — um perfil CUSTOM chamado
    # "Admin" impede o seed de criar o system homônimo (ON CONFLICT DO NOTHING)
    # e a atribuição (que filtra is_system) não acha nada: falharia calada.
    nomes_ocupados_custom = {(e, n) for _pid, e, n, is_sys in perfis if not is_sys}

    perfil_perms: dict[int, set[str]] = {}
    for pid, codigo in await (
        await conn.execute("SELECT perfil_id, permissao_codigo FROM perfil_permissao")
    ).fetchall():
        perfil_perms.setdefault(pid, set()).add(codigo)

    atribuicoes: dict[tuple[int, str], set[int]] = {}
    for emp, uid, pid in await (
        await conn.execute("SELECT empresa_id, user_id, perfil_id FROM usuario_perfil")
    ).fetchall():
        atribuicoes.setdefault((emp, uid), set()).add(pid)

    return {
        "membros": membros,
        # (empresa_id, nome) -> perfil_id, só os system (o fallback legado
        # procura por nome E is_system=TRUE).
        "sys_por_nome": {(e, n): pid for pid, e, n, is_sys in perfis if is_sys},
        "perfil_perms": perfil_perms,
        "atribuicoes": atribuicoes,
        "catalogo": {c[0] for c in CATALOGO},
        "nomes_ocupados_custom": nomes_ocupados_custom,
    }


def _perms_efetivas(
    estado: dict,
    empresa_id: int,
    user_id: str,
    role: str,
    superadmin: bool,
    *,
    sys_existe: set[tuple[int, str]],
) -> set[str]:
    """Espelha `perfil.get_user_permissions` — MESMA ordem de precedência.

    `sys_existe` permite simular o estado PÓS-seed sem escrever no banco.
    """
    if superadmin:
        return set(estado["catalogo"])

    pids = estado["atribuicoes"].get((empresa_id, user_id), set())
    if pids:
        efetivo: set[str] = set()
        for pid in pids:
            efetivo |= estado["perfil_perms"].get(pid, set())
        return efetivo

    # Fallback legado: resolve o perfil system pelo NOME.
    nome = LEGACY_ROLE_TO_PERFIL.get(role)
    if not nome or (empresa_id, nome) not in sys_existe:
        return set()
    return _perms_perfil_alvo(estado, empresa_id, nome)


def _perms_perfil_alvo(estado: dict, empresa_id: int, nome: str) -> set[str]:
    """Permissões que o perfil `nome` da empresa terá DEPOIS da migração.

    Se o perfil já existe, valem as permissões que estão no BANCO — o seed não
    sobrescreve perfil existente (`ON CONFLICT DO NOTHING`), e um perfil editado
    à mão diverge da definição do código de propósito. Só quando ele vai ser
    criado agora é que a definição de `PERFIS_SYSTEM` responde.
    """
    pid = estado["sys_por_nome"].get((empresa_id, nome))
    if pid is not None:
        return estado["perfil_perms"].get(pid, set())
    for n, _desc, perms in PERFIS_SYSTEM:
        if n == nome:
            return set(estado["catalogo"]) if perms == "all" else set(perms)
    return set()


async def planejar(dsn: str, empresa_filtro: int | None) -> dict:
    import psycopg

    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        estado = await _carregar(conn, empresa_filtro)

    empresas = sorted({m[0] for m in estado["membros"]})
    sys_hoje = set(estado["sys_por_nome"])
    nomes_system = [n for n, _d, _p in PERFIS_SYSTEM]

    ocupados = estado["nomes_ocupados_custom"]

    # 1. Perfis system que faltam nas empresas com membro. Nome já tomado por
    #    perfil custom vira CONFLITO (não dá para criar nem para atribuir).
    a_criar = [
        {"empresa_id": e, "nome": n}
        for e in empresas
        for n in nomes_system
        if (e, n) not in sys_hoje and (e, n) not in ocupados
    ]
    conflitos = [
        {"empresa_id": e, "nome": n}
        for e in empresas
        for n in nomes_system
        if (e, n) not in sys_hoje and (e, n) in ocupados
    ]
    sys_depois = sys_hoje | {(x["empresa_id"], x["nome"]) for x in a_criar}

    # 2. Atribuições.
    a_atribuir: list[dict] = []
    for empresa_id, user_id, role, superadmin in estado["membros"]:
        pids = estado["atribuicoes"].get((empresa_id, user_id), set())
        uniao: set[str] = set()
        for pid in pids:
            uniao |= estado["perfil_perms"].get(pid, set())

        if not pids:
            nome = LEGACY_ROLE_TO_PERFIL.get(role)
            motivo = "sem perfil — recebe o equivalente ao role"
        elif role == "admin" and PERM_ADMIN not in uniao:
            nome = "Admin"
            motivo = f"role=admin mas nenhum perfil concede `{PERM_ADMIN}`"
        else:
            continue

        if not nome:
            a_atribuir.append(
                {
                    "empresa_id": empresa_id,
                    "user_id": user_id,
                    "role": role,
                    "perfil": None,
                    "motivo": f"role `{role}` sem perfil equivalente — IGNORADO",
                    "ganha": [],
                }
            )
            continue

        if (empresa_id, nome) in ocupados and (empresa_id, nome) not in sys_hoje:
            a_atribuir.append(
                {
                    "empresa_id": empresa_id,
                    "user_id": user_id,
                    "role": role,
                    "perfil": None,
                    "motivo": (
                        f"CONFLITO: já existe perfil custom chamado `{nome}` nessa "
                        "empresa — renomeie-o ou atribua o perfil à mão"
                    ),
                    "ganha": [],
                }
            )
            continue

        antes = _perms_efetivas(
            estado, empresa_id, user_id, role, superadmin, sys_existe=sys_hoje
        )
        depois = (uniao if pids else set()) | _perms_perfil_alvo(
            estado, empresa_id, nome
        )
        if superadmin:
            depois = set(estado["catalogo"])

        a_atribuir.append(
            {
                "empresa_id": empresa_id,
                "user_id": user_id,
                "role": role,
                "perfil": nome,
                "motivo": motivo,
                "superadmin": superadmin,
                "antes": len(antes),
                "depois": len(depois),
                "ganha": sorted(depois - antes),
                # Deve ser SEMPRE vazio: a migração só faz UNION. Se aparecer
                # algo aqui, há bug no plano — não aplique.
                "perde": sorted(antes - depois),
            }
        )

    # 3. Quem muda de efetivo SÓ por causa do seed (não recebe atribuição).
    alargados_pelo_seed = []
    for empresa_id, user_id, role, superadmin in estado["membros"]:
        if estado["atribuicoes"].get((empresa_id, user_id)):
            continue
        antes = _perms_efetivas(
            estado, empresa_id, user_id, role, superadmin, sys_existe=sys_hoje
        )
        depois = _perms_efetivas(
            estado, empresa_id, user_id, role, superadmin, sys_existe=sys_depois
        )
        if depois - antes:
            alargados_pelo_seed.append(
                {
                    "empresa_id": empresa_id,
                    "user_id": user_id,
                    "role": role,
                    "ganha": len(depois - antes),
                }
            )

    return {
        "empresas": empresas,
        "perfis_a_criar": a_criar,
        "conflitos_de_nome": conflitos,
        "atribuicoes": a_atribuir,
        "alargados_pelo_seed": alargados_pelo_seed,
        "total_membros": len(estado["membros"]),
    }


async def aplicar(dsn: str, plano: dict) -> dict:
    """Cria os perfis system que faltam e insere as atribuições. Idempotente."""
    import psycopg

    todos = [c[0] for c in CATALOGO]
    criados = atribuidos = 0

    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        async with conn.transaction():
            # Perfis system — mesma definição de `permissoes.PERFIS_SYSTEM`,
            # que continua sendo a fonte única.
            for nome, descricao, perms_def in PERFIS_SYSTEM:
                alvo = [
                    x["empresa_id"]
                    for x in plano["perfis_a_criar"]
                    if x["nome"] == nome
                ]
                for empresa_id in alvo:
                    cur = await conn.execute(
                        """
                        INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (empresa_id, nome) DO NOTHING
                        RETURNING id
                        """,
                        (empresa_id, nome, descricao),
                    )
                    row = await cur.fetchone()
                    if row is None:
                        continue
                    criados += 1
                    perms = todos if perms_def == "all" else perms_def
                    for codigo in perms:
                        await conn.execute(
                            """
                            INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
                            VALUES (%s, %s) ON CONFLICT DO NOTHING
                            """,
                            (row[0], codigo),
                        )

            for item in plano["atribuicoes"]:
                if not item["perfil"]:
                    continue
                cur = await conn.execute(
                    """
                    INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id)
                    SELECT %s, pa.id, %s
                      FROM perfil_acesso pa
                     WHERE pa.empresa_id = %s AND pa.nome = %s AND pa.is_system
                    ON CONFLICT (user_id, perfil_id, empresa_id) DO NOTHING
                    """,
                    (
                        item["user_id"],
                        item["empresa_id"],
                        item["empresa_id"],
                        item["perfil"],
                    ),
                )
                atribuidos += cur.rowcount

    return {"perfis_criados": criados, "atribuicoes_inseridas": atribuidos}


def imprimir(plano: dict, aplicado: dict | None) -> None:
    print()
    print("=" * 72)
    print("  ETAPA 0 — role → perfil   " + ("APLICADO" if aplicado else "DRY-RUN"))
    print("=" * 72)
    print(
        f"\n{plano['total_membros']} membro(s) em {len(plano['empresas'])} empresa(s)."
    )

    criar = plano["perfis_a_criar"]
    print(f"\n1. PERFIS SYSTEM A CRIAR: {len(criar)}")
    por_emp: dict[int, list[str]] = {}
    for x in criar:
        por_emp.setdefault(x["empresa_id"], []).append(x["nome"])
    for emp, nomes in sorted(por_emp.items()):
        print(f"   - empresa {emp}: {', '.join(sorted(nomes))}")

    conf = plano.get("conflitos_de_nome") or []
    if conf:
        print(
            f"\n   ⚠️  {len(conf)} nome(s) tomados por perfil CUSTOM — não dá para criar:"
        )
        for x in conf:
            print(f"      empresa {x['empresa_id']} · `{x['nome']}`")

    alarg = plano["alargados_pelo_seed"]
    print(f"\n2. ⚠️  ALARGADOS SÓ PELO SEED (sem atribuição): {len(alarg)}")
    if alarg:
        print("   Hoje o fallback legado não acha o perfil pelo nome e devolve VAZIO.")
        print(
            "   Criar o perfil já conserta o fallback — o efetivo muda antes de atribuir."
        )
    for x in alarg[:12]:
        print(
            f"   - empresa {x['empresa_id']} · {x['user_id'][:12]}… "
            f"role={x['role']} → ganha {x['ganha']} permissões"
        )
    if len(alarg) > 12:
        print(f"   … e mais {len(alarg) - 12}")

    atrib = plano["atribuicoes"]
    print(f"\n3. ATRIBUIÇÕES: {len(atrib)}")
    for x in atrib:
        if not x["perfil"]:
            print(
                f"   ⚠️  empresa {x['empresa_id']} · {x['user_id'][:12]}… {x['motivo']}"
            )
            continue
        delta = len(x["ganha"])
        marca = "  " if delta == 0 else "→ "
        print(
            f"   {marca}empresa {x['empresa_id']} · {x['user_id'][:12]}… "
            f"role={x['role']} → perfil `{x['perfil']}` "
            f"({x['antes']}→{x['depois']} perms, +{delta})"
        )
        print(f"      motivo: {x['motivo']}")
        if delta and delta <= 8:
            print(f"      ganha: {', '.join(x['ganha'])}")

    sem_mudanca = sum(1 for x in atrib if x["perfil"] and not x["ganha"])
    print(
        f"\n   {sem_mudanca} atribuição(ões) sem NENHUMA mudança de efetivo "
        "(só tornam explícito o que o fallback já dava)."
    )

    perdas = [x for x in atrib if x.get("perde")]
    if perdas:
        print(
            f"\n   🚨 {len(perdas)} atribuição(ões) PERDERIAM permissão — NÃO APLIQUE."
        )
        for x in perdas:
            print(
                f"      empresa {x['empresa_id']} · {x['user_id'][:12]}… "
                f"perde: {', '.join(x['perde'])}"
            )
    else:
        print("   ✅ Nenhuma permissão perdida (a migração só faz união).")

    if aplicado:
        print(
            f"\n✅ APLICADO — {aplicado['perfis_criados']} perfil(is) criado(s), "
            f"{aplicado['atribuicoes_inseridas']} atribuição(ões) inserida(s)."
        )
        print("   Confira com: uv run python scripts/raio_x_acesso.py")
    else:
        print("\n(dry-run — nada foi escrito. Use --apply para executar.)")
    print()


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="executa (padrão: dry-run)")
    ap.add_argument("--empresa", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()

    if not args.dsn:
        print("DATABASE_URL não definido (ou use --dsn).", file=sys.stderr)
        return 2

    plano = await planejar(args.dsn, args.empresa)

    # Guarda dura: a Etapa 0 é por definição aditiva. Se o plano prevê perda,
    # o bug está no plano — aplicar seria tirar acesso de quem trabalha.
    perdas = [x for x in plano["atribuicoes"] if x.get("perde")]
    if args.apply and perdas:
        imprimir(plano, None)
        print(
            f"ABORTADO: {len(perdas)} atribuição(ões) perderiam permissão.",
            file=sys.stderr,
        )
        return 1

    aplicado = await aplicar(args.dsn, plano) if args.apply else None

    if args.json:
        print(
            json.dumps(
                {"plano": plano, "aplicado": aplicado}, indent=2, ensure_ascii=False
            )
        )
    else:
        imprimir(plano, aplicado)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
