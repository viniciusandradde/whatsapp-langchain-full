#!/usr/bin/env python3
"""Raio-X de acesso — cruza o CÓDIGO (gates das rotas) com o BANCO (catálogo,
perfis e usuários) e aponta as inconsistências de permissão.

Inspirado nas telas de inconsistência do blueprint `one-for-all` (wareaudit) e
na cobertura por módulo/função do ZigChat (ver docs/zigchat/). Leitura pura:
não escreve nada, pode rodar em produção.

    uv run python scripts/raio_x_acesso.py                    # texto
    uv run python scripts/raio_x_acesso.py --json             # máquina
    uv run python scripts/raio_x_acesso.py --empresa 1        # divergências de 1 empresa

O que procura:

1. **Rotas sem gate** — endpoint de negócio que exige só `get_empresa_context`
   (ser membro). Hoje é onde `cliente`, `variavel`, `departamento` e
   `modelo_mensagem` caem: um perfil "somente leitura" cria e apaga.
2. **Rotas no `is_admin_of`** — gate pelo `role` legado, que ignora perfis
   (a Decisão 2 / achado A4).
3. **Permissões órfãs** — existem no catálogo (e aparecem na tela de perfil),
   mas nenhuma rota as exige: a UI promete o que o backend ignora.
4. **Permissões fantasma** — o código exige, mas não existem no catálogo.
   Grave: ninguém consegue passar, a rota fica inacessível.
5. **Divergência role × perfil** — `role='admin'` com perfil restritivo (ou o
   inverso). É o A4 tornado visível.
6. **Perfis sem usuário** e **usuários sem perfil**.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ROTAS_DIR = RAIZ / "src" / "whatsapp_langchain" / "server" / "routes"

# Rotas que legitimamente não têm gate de permissão de usuário.
SEM_GATE_OK = {
    "__init__.py",
    "health.py",
    "evolution_webhook.py",
    "webhook_waba.py",
    "asaas_webhook.py",
    "webhook_sync.py",  # só fora de produção
}

_RE_PERM = re.compile(r"""require_permission\(\s*["']([^"']+)["']""")
_RE_ROTA = re.compile(r"""@\w*router\w*\.(get|post|put|patch|delete)\(""")


def varrer_codigo() -> dict:
    """Lê os arquivos de rota e classifica o gate de cada um."""
    com_perm: dict[str, list[str]] = {}
    com_admin_of: list[str] = []
    so_superadmin: list[str] = []
    sem_gate: list[tuple[str, int]] = []
    perms_no_codigo: set[str] = set()

    for arq in sorted(ROTAS_DIR.glob("*.py")):
        txt = arq.read_text(encoding="utf-8")
        nome = arq.name
        perms = sorted(set(_RE_PERM.findall(txt)))
        n_rotas = len(_RE_ROTA.findall(txt))
        perms_no_codigo.update(perms)

        if perms:
            com_perm[nome] = perms
        elif "is_admin_of" in txt:
            com_admin_of.append(nome)
        elif "_exigir_superadmin" in txt or "is_superadmin" in txt:
            so_superadmin.append(nome)
        elif nome not in SEM_GATE_OK and n_rotas > 0:
            sem_gate.append((nome, n_rotas))

    return {
        "com_perm": com_perm,
        "com_admin_of": com_admin_of,
        "so_superadmin": so_superadmin,
        "sem_gate": sem_gate,
        "perms_no_codigo": perms_no_codigo,
    }


async def consultar_banco(dsn: str, empresa_id: int | None) -> dict:
    import psycopg

    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        # `permissao` tem PK textual (`codigo`) e já traz `modulo` — o mesmo
        # agrupamento que o ZigChat chama de `categoria`.
        cat = await (
            await conn.execute("SELECT codigo, modulo FROM permissao")
        ).fetchall()
        catalogo = {r[0] for r in cat}
        modulos = {r[0]: r[1] for r in cat}

        # Divergência role × perfil: quem tem role 'admin' mas nenhum perfil que
        # conceda `empresa.update` (o que `is_admin_of` deveria significar), e o
        # inverso — quem tem o perfil mas não o role.
        filtro = "AND m.empresa_id = %s" if empresa_id else ""
        args = (empresa_id,) if empresa_id else ()
        # `perfil_permissao` liga pelo CÓDIGO da permissão (não por id).
        sql_div = f"""
            SELECT m.empresa_id, m.user_id, m.role,
                   COALESCE(
                     BOOL_OR(pp.permissao_codigo LIKE 'empresa.update%%'), FALSE
                   ) AS tem_perm,
                   COUNT(DISTINCT up.perfil_id) AS qtd_perfis
              FROM empresa_membro m
              LEFT JOIN usuario_perfil up
                     ON up.user_id = m.user_id AND up.empresa_id = m.empresa_id
              LEFT JOIN perfil_permissao pp ON pp.perfil_id = up.perfil_id
             WHERE TRUE {filtro}
             GROUP BY m.empresa_id, m.user_id, m.role
        """
        linhas = await (await conn.execute(sql_div, args)).fetchall()

        divergentes = []
        sem_perfil = []
        for emp, uid, role, tem_perm, qtd_perfis in linhas:
            if qtd_perfis == 0:
                sem_perfil.append({"empresa_id": emp, "user_id": uid, "role": role})
            elif role == "admin" and not tem_perm:
                divergentes.append(
                    {"empresa_id": emp, "user_id": uid, "role": role,
                     "situacao": "role admin SEM permissão de admin no perfil"}
                )
            elif role != "admin" and tem_perm:
                divergentes.append(
                    {"empresa_id": emp, "user_id": uid, "role": role,
                     "situacao": "perfil de admin MAS role não-admin (toma 403 no is_admin_of)"}
                )

        perfis_vazios = await (
            await conn.execute(
                """
                SELECT pf.empresa_id, pf.id, pf.nome
                  FROM perfil_acesso pf
                  LEFT JOIN usuario_perfil up ON up.perfil_id = pf.id
                 WHERE up.perfil_id IS NULL
                 ORDER BY pf.empresa_id, pf.nome
                """
            )
        ).fetchall()

    return {
        "catalogo": catalogo,
        "modulos": modulos,
        "divergentes": divergentes,
        "sem_perfil": sem_perfil,
        "perfis_vazios": [
            {"empresa_id": e, "perfil_id": i, "nome": n} for e, i, n in perfis_vazios
        ],
    }


def montar_relatorio(codigo: dict, banco: dict) -> dict:
    catalogo: set[str] = banco["catalogo"]
    usadas: set[str] = codigo["perms_no_codigo"]

    # Órfã: está no catálogo mas nenhuma rota exige. Compara também o prefixo,
    # porque `require_permission("cliente.read")` cobre `.own`/`.all`.
    def usada(cod: str) -> bool:
        if cod in usadas:
            return True
        base = cod.rsplit(".", 1)[0]
        return base in usadas and cod.rsplit(".", 1)[-1] in ("own", "all")

    orfas = sorted(c for c in catalogo if not usada(c))
    fantasmas = sorted(u for u in usadas if u not in catalogo)

    total_arqs = len(codigo["com_perm"]) + len(codigo["com_admin_of"]) + len(
        codigo["so_superadmin"]
    ) + len(codigo["sem_gate"])

    por_modulo = defaultdict(list)
    for c in orfas:
        por_modulo[c.split(".", 1)[0]].append(c)

    return {
        "cobertura": {
            "arquivos_com_permissao": len(codigo["com_perm"]),
            "arquivos_com_is_admin_of": len(codigo["com_admin_of"]),
            "arquivos_so_superadmin": len(codigo["so_superadmin"]),
            "arquivos_sem_gate": len(codigo["sem_gate"]),
            "total_classificado": total_arqs,
        },
        "rotas_sem_gate": codigo["sem_gate"],
        "rotas_is_admin_of": codigo["com_admin_of"],
        "permissoes_orfas": orfas,
        "orfas_por_modulo": dict(por_modulo),
        "permissoes_fantasma": fantasmas,
        "divergencia_role_perfil": banco["divergentes"],
        "usuarios_sem_perfil": banco["sem_perfil"],
        "perfis_sem_usuario": banco["perfis_vazios"],
        "totais": {
            "catalogo": len(catalogo),
            "usadas_no_codigo": len(usadas),
            "orfas": len(orfas),
            "fantasmas": len(fantasmas),
        },
    }


def imprimir(r: dict) -> None:
    c = r["cobertura"]
    print("=" * 72)
    print("RAIO-X DE ACESSO — permissões, perfis e rotas")
    print("=" * 72)
    print("\n1. COBERTURA DAS ROTAS")
    print(f"   com require_permission : {c['arquivos_com_permissao']}")
    print(f"   no is_admin_of (legado): {c['arquivos_com_is_admin_of']}")
    print(f"   só superadmin          : {c['arquivos_so_superadmin']}")
    print(f"   SEM gate de permissão  : {c['arquivos_sem_gate']}")

    if r["rotas_is_admin_of"]:
        print("\n2. ROTAS NO `is_admin_of` (ignoram perfis — achado A4)")
        for nome in r["rotas_is_admin_of"]:
            print(f"   - {nome}")

    if r["rotas_sem_gate"]:
        print("\n3. ROTAS DE NEGÓCIO SEM GATE (basta ser membro da empresa)")
        for nome, n in sorted(r["rotas_sem_gate"], key=lambda x: -x[1]):
            print(f"   - {nome:32s} {n} endpoint(s)")

    t = r["totais"]
    print(f"\n4. PERMISSÕES ÓRFÃS — no catálogo, exigidas por ninguém "
          f"({t['orfas']} de {t['catalogo']})")
    for mod, cods in sorted(r["orfas_por_modulo"].items()):
        print(f"   {mod}: {', '.join(cods)}")

    if r["permissoes_fantasma"]:
        print("\n5. ⚠️  PERMISSÕES FANTASMA — o código exige, o catálogo não tem")
        print("   (rota inacessível: ninguém consegue receber a permissão)")
        for cod in r["permissoes_fantasma"]:
            print(f"   - {cod}")

    d = r["divergencia_role_perfil"]
    print(f"\n6. DIVERGÊNCIA role × perfil ({len(d)})")
    if not d:
        print("   nenhuma")
    for x in d[:20]:
        print(f"   - empresa {x['empresa_id']} · user {x['user_id'][:12]}… "
              f"role={x['role']} → {x['situacao']}")

    print(f"\n7. USUÁRIOS SEM PERFIL: {len(r['usuarios_sem_perfil'])}"
          f"   ·   PERFIS SEM USUÁRIO: {len(r['perfis_sem_usuario'])}")
    for x in r["usuarios_sem_perfil"][:10]:
        print(f"   - empresa {x['empresa_id']} · user {x['user_id'][:12]}… role={x['role']}")
    for x in r["perfis_sem_usuario"][:10]:
        print(f"   - perfil vazio: empresa {x['empresa_id']} · {x['nome']}")
    print()


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="saída JSON")
    ap.add_argument("--empresa", type=int, default=None, help="filtra divergências")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()

    if not args.dsn:
        print("DATABASE_URL não definido (ou use --dsn).", file=sys.stderr)
        return 2

    codigo = varrer_codigo()
    banco = await consultar_banco(args.dsn, args.empresa)
    rel = montar_relatorio(codigo, banco)

    if args.json:
        print(json.dumps(rel, indent=2, ensure_ascii=False))
    else:
        imprimir(rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
