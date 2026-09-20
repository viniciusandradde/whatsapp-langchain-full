"""Opt-out é respeitado em TODO caminho que vira destinatário (H0).

O bug que isto fecha: `telefones_suprimidos()` só era chamado no preview
do disparo. `create_campanha`, `add_destinatarios` e `clonar_campanha`
inseriam qualquer telefone, e o `_dispatch_loop` lia `status='pendente'`
sem consultar a supressão — uma campanha criada no painel `/campanhas`
enviava para quem tinha pedido descadastro.

São quatro portas, e cada teste aqui tranca uma:

    1. criar campanha            → o suprimido não vira destinatário
    2. adicionar destinatários   → idem, e o retorno diz quantos ignorou
    3. clonar campanha           → a cópia não ressuscita quem saiu
    4. na hora do envio          → quem pediu descadastro DEPOIS de a
                                   campanha ser criada também é poupado
                                   (campanha em warm-up dura dias)

Rodar:

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_opt_out_campanha.py -v
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from .helpers import get_db_url

_RUN = uuid.uuid4().hex[:8]

# Três telefones estáveis por execução: o do meio é o que pede descadastro.
_TEL_OK1 = "+5567" + f"9{int(_RUN, 16) % 100_000_000:08d}"[:9]
_TEL_STOP = "+5568" + f"9{int(_RUN, 16) % 100_000_000:08d}"[:9]
_TEL_OK2 = "+5569" + f"9{int(_RUN, 16) % 100_000_000:08d}"[:9]


@pytest.mark.docker_demo
class TestOptOutNaCampanha:
    @pytest.fixture(scope="class")
    def empresa(self):
        """Empresa isolada com UM telefone já na lista de supressão."""
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug, plano) VALUES (%s, %s, 'pro') RETURNING id",
                (f"optout-{_RUN}", f"optout-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
            conn.execute(
                """
                INSERT INTO disparador_opt_out
                    (empresa_id, wa_jid, telefone, motivo, origem)
                VALUES (%s, %s, %s, 'user_request', 'teste')
                """,
                (eid, f"{_TEL_STOP.lstrip('+')}@s.whatsapp.net", _TEL_STOP),
            )
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def _criar(self, pool, empresa, telefones: list[str]) -> dict:
        from whatsapp_langchain.shared.campanha import create_campanha
        from whatsapp_langchain.shared.rls_context import empresa_scope

        with empresa_scope(empresa):
            return await create_campanha(
                pool,
                empresa,
                nome=f"oo-{_RUN}-{uuid.uuid4().hex[:4]}",
                descricao=None,
                mensagem="oi",
                conexao_id=None,
                intervalo_ms=500,
                max_destinatarios=1000,
                telefones_brutos=telefones,
                user_id=None,
            )

    def _telefones(self, camp_id: int) -> set[str]:
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            rows = conn.execute(
                "SELECT telefone FROM campanha_destinatario WHERE campanha_id = %s",
                (camp_id,),
            ).fetchall()
        return {r[0] for r in rows}

    # ---------- porta 1: criar ----------

    async def test_1_criar_nao_inclui_suprimido(self, empresa) -> None:
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp = await self._criar(pool, empresa, [_TEL_OK1, _TEL_STOP, _TEL_OK2])

        assert self._telefones(camp["id"]) == {_TEL_OK1, _TEL_OK2}
        assert camp["ignorados_opt_out"] == 1

    async def test_2_total_destinatarios_desconta_o_suprimido(self, empresa) -> None:
        """Se `total` contasse o suprimido, a campanha nunca chegaria a 'done'
        — `_mark_finished` compara `enviados == total_destinatarios`."""
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp = await self._criar(pool, empresa, [_TEL_OK1, _TEL_STOP, _TEL_OK2])
        assert camp["total_destinatarios"] == 2

    async def test_3_lista_toda_suprimida_e_recusada(self, empresa) -> None:
        """Campanha sem nenhum destinatário elegível não deve nascer."""
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        with pytest.raises(ValueError, match="descadastr"):
            await self._criar(pool, empresa, [_TEL_STOP])

    # ---------- porta 2: adicionar ----------

    async def test_4_add_destinatarios_ignora_suprimido(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha import add_destinatarios
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        camp = await self._criar(pool, empresa, [_TEL_OK1])
        with empresa_scope(empresa):
            out = await add_destinatarios(
                pool, empresa, camp["id"], [_TEL_OK2, _TEL_STOP]
            )

        assert out["novos"] == 1
        assert out["ignorados_opt_out"] == 1
        assert out["total"] == 2
        assert self._telefones(camp["id"]) == {_TEL_OK1, _TEL_OK2}

    # ---------- porta 3: clonar ----------

    async def test_5_clonar_nao_ressuscita_quem_saiu(self, empresa) -> None:
        """A campanha de origem é anterior ao opt-out: a cópia tem de respeitar
        a supressão de hoje, não a lista de ontem."""
        from whatsapp_langchain.shared.campanha import clonar_campanha
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        camp = await self._criar(pool, empresa, [_TEL_OK1, _TEL_OK2])
        # Injeta o suprimido direto na origem, simulando a campanha antiga.
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                "INSERT INTO campanha_destinatario"
                " (campanha_id, empresa_id, telefone) VALUES (%s, %s, %s)",
                (camp["id"], empresa, _TEL_STOP),
            )
        assert _TEL_STOP in self._telefones(camp["id"])

        with empresa_scope(empresa):
            copia = await clonar_campanha(pool, empresa, camp["id"])

        assert self._telefones(copia["id"]) == {_TEL_OK1, _TEL_OK2}
        assert copia["total_destinatarios"] == 2

    # ---------- porta 4: na hora do envio ----------

    async def test_6_dispatch_remove_quem_saiu_depois(self, empresa) -> None:
        """Warm-up espalha a campanha por dias. Quem pede STOP no dia 1 não
        pode receber no dia 2 — o gate roda por lote, não só na criação."""
        from whatsapp_langchain.shared.campanha import remover_suprimidos_pendentes
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        camp = await self._criar(pool, empresa, [_TEL_OK1, _TEL_OK2])
        # O opt-out chega DEPOIS: injeta o telefone na campanha já criada.
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                "INSERT INTO campanha_destinatario"
                " (campanha_id, empresa_id, telefone) VALUES (%s, %s, %s)",
                (camp["id"], empresa, _TEL_STOP),
            )

        with empresa_scope(empresa):
            removidos = await remover_suprimidos_pendentes(
                pool, empresa, camp["id"], [_TEL_OK1, _TEL_STOP, _TEL_OK2]
            )

        assert removidos == {_TEL_STOP}
        assert self._telefones(camp["id"]) == {_TEL_OK1, _TEL_OK2}
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT total_destinatarios FROM campanha WHERE id = %s",
                (camp["id"],),
            ).fetchone()
        assert row is not None
        assert row[0] == 2, "total precisa cair, senão a campanha morre em 'partial'"

    async def test_7_lote_sem_suprimido_nao_toca_no_banco(self, empresa) -> None:
        """Caminho quente: campanha limpa não paga DELETE nem UPDATE por lote."""
        from whatsapp_langchain.shared.campanha import remover_suprimidos_pendentes
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        camp = await self._criar(pool, empresa, [_TEL_OK1, _TEL_OK2])
        with empresa_scope(empresa):
            removidos = await remover_suprimidos_pendentes(
                pool, empresa, camp["id"], [_TEL_OK1, _TEL_OK2]
            )
        assert removidos == set()
        assert self._telefones(camp["id"]) == {_TEL_OK1, _TEL_OK2}

    # ---------- isolamento ----------

    async def test_8_supressao_nao_vaza_entre_empresas(self, empresa) -> None:
        """Opt-out é por empresa: o STOP dado na empresa A não pode bloquear
        o mesmo telefone na empresa B."""
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug, plano) VALUES (%s, %s, 'pro') RETURNING id",
                (f"optout-b-{_RUN}", f"optout-b-{_RUN}"),
            ).fetchone()
            assert row is not None
            outra = row[0]
        try:
            camp = await self._criar(pool, outra, [_TEL_OK1, _TEL_STOP])
            assert self._telefones(camp["id"]) == {_TEL_OK1, _TEL_STOP}
            assert camp["ignorados_opt_out"] == 0
        finally:
            with psycopg.connect(db, autocommit=True) as conn:
                conn.execute("DELETE FROM empresa WHERE id = %s", (outra,))
