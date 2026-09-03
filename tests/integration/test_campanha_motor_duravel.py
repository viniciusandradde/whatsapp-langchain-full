"""Motor durável de disparo (mig 183, F2b).

Estes testes cobrem a garantia que a fase inteira existe pra dar: **reiniciar
o processo no meio de uma campanha não perde nem duplica destinatário**.

Antes da mig 183 o dispatcher rodava dentro da API, e `claim_scheduled_due` só
reivindicava `scheduled` — campanha `running` cujo dono morresse ficava presa
nesse estado para sempre. Aqui a morte do worker é simulada do jeito mais
honesto possível: escrevendo no banco exatamente o estado que ela deixa
(lease vencido, destinatário em `enviando`), sem mock do motor.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    uv run pytest tests/integration/test_campanha_motor_duravel.py -v
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from .helpers import get_db_url

_RUN = uuid.uuid4().hex[:8]


def _sql(query: str, params: tuple = ()):
    with psycopg.connect(get_db_url(), autocommit=True) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else []


@pytest.mark.docker_demo
class TestMotorDuravel:
    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            eid = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"motor-{_RUN}", f"motor-{_RUN}"),
            ).fetchone()[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    def _nova_campanha(self, empresa: int, status: str, **cols) -> int:
        """Campanha crua no banco, no estado exato que o teste precisa."""
        extra_cols = "".join(f", {k}" for k in cols)
        extra_vals = "".join(", %s" for _ in cols)
        return _sql(
            "INSERT INTO campanha (empresa_id, nome, mensagem, intervalo_ms,"
            f" max_destinatarios, total_destinatarios, status{extra_cols})"
            f" VALUES (%s, %s, 'oi', 500, 100, 0, %s{extra_vals}) RETURNING id",
            (empresa, f"c-{uuid.uuid4().hex[:6]}", status, *cols.values()),
        )[0][0]

    def _dest(
        self, empresa: int, camp_id: int, status: str = "pendente", **cols
    ) -> int:
        extra_cols = "".join(f", {k}" for k in cols)
        extra_vals = "".join(", %s" for _ in cols)
        return _sql(
            "INSERT INTO campanha_destinatario"
            f" (campanha_id, empresa_id, telefone, status{extra_cols})"
            f" VALUES (%s, %s, %s, %s{extra_vals}) RETURNING id",
            (
                camp_id,
                empresa,
                f"+5511{uuid.uuid4().int % 10**9:09d}",
                status,
                *cols.values(),
            ),
        )[0][0]

    async def _claim_ate_achar(self, camp_id: int, tentativas: int = 30):
        """Reivindica até cair na campanha do teste (o claim é LIMIT 1)."""
        from whatsapp_langchain.shared.campanha_motor import claim_campanha
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        for _ in range(tentativas):
            claim = await claim_campanha(pool)
            if claim is None:
                return None
            if claim.camp_id == camp_id:
                return claim
        return None

    # ---------- a garantia central: a órfã volta ----------

    async def test_1_campanha_running_com_lease_vencido_e_retomada(
        self, empresa
    ) -> None:
        """§4.3: era estado terminal. Agora o lease vencido a devolve pra fila.

        Simula exatamente o que um deploy deixa para trás: status `running`,
        lease de um worker que não existe mais, e a hora de expiração no
        passado.
        """
        camp_id = self._nova_campanha(
            empresa,
            "running",
            lease_owner="worker-morto:999",
            lease_expires_at="2020-01-01T00:00:00+00:00",
        )
        claim = await self._claim_ate_achar(camp_id)
        assert claim is not None, "campanha órfã NÃO foi reivindicada (§4.3 aberto)"
        assert claim.era_orfa, "deveria ser reconhecida como retomada de órfã"
        assert claim.dono_anterior == "worker-morto:999"

    async def test_2_running_com_lease_vivo_nao_e_roubada(self, empresa) -> None:
        """O outro lado: worker vivo não pode ter a campanha tomada dele."""
        camp_id = self._nova_campanha(
            empresa,
            "running",
            lease_owner="worker-vivo:1",
            lease_expires_at="2999-01-01T00:00:00+00:00",
        )
        claim = await self._claim_ate_achar(camp_id)
        assert claim is None or claim.camp_id != camp_id, (
            "campanha com lease VIVO foi reivindicada — dois workers enviariam"
        )

    async def test_3_queued_e_reivindicada(self, empresa) -> None:
        """`queued` é a porta nova: o endpoint só enfileira, o worker pega."""
        camp_id = self._nova_campanha(empresa, "queued")
        claim = await self._claim_ate_achar(camp_id)
        assert claim is not None, "campanha 'queued' não foi reivindicada"
        assert claim.status_anterior == "queued"
        assert not claim.era_orfa

    async def test_4_draft_nunca_e_reivindicada(self, empresa) -> None:
        """Rascunho não dispara sozinho — precisa passar pelo endpoint."""
        camp_id = self._nova_campanha(empresa, "draft")
        claim = await self._claim_ate_achar(camp_id)
        assert claim is None or claim.camp_id != camp_id, "draft foi disparada!"

    # ---------- fence do lease ----------

    async def test_5_renovar_lease_falha_se_perdeu_a_propriedade(self, empresa) -> None:
        """Perder o lease PARA o envio — senão dois workers duplicam tudo."""
        from whatsapp_langchain.shared.campanha_motor import renovar_lease
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "queued")
        claim = await self._claim_ate_achar(camp_id)
        assert claim is not None

        assert await renovar_lease(pool, camp_id) is True, "dono não conseguiu renovar"

        # Outro worker assume (é o que o claim faria depois do lease vencer).
        _sql(
            "UPDATE campanha SET lease_owner = 'outro-worker:2' WHERE id = %s",
            (camp_id,),
        )
        assert await renovar_lease(pool, camp_id) is False, (
            "renovou lease que não é mais dele — o fence não está pegando"
        )

    # ---------- claim de destinatário ----------

    async def test_6_destinatario_nao_e_entregue_duas_vezes(self, empresa) -> None:
        """O SELECT sem lock deixava dois motores lerem o MESMO lote."""
        from whatsapp_langchain.shared.campanha_motor import claim_destinatarios
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "running")
        esperados = {self._dest(empresa, camp_id) for _ in range(5)}

        lote1 = await claim_destinatarios(pool, empresa, camp_id, limite=3)
        lote2 = await claim_destinatarios(pool, empresa, camp_id, limite=3)
        ids1 = {r[0] for r in lote1}
        ids2 = {r[0] for r in lote2}

        assert len(ids1) == 3
        assert len(ids2) == 2, "segundo lote deveria trazer só o que sobrou"
        assert not (ids1 & ids2), f"MESMO destinatário em dois lotes: {ids1 & ids2}"
        assert ids1 | ids2 == esperados

        lote3 = await claim_destinatarios(pool, empresa, camp_id, limite=3)
        assert lote3 == [], "reivindicou destinatário já em voo"

    async def test_7_claim_marca_enviando_e_conta_tentativa(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha_motor import (
            WORKER_ID,
            claim_destinatarios,
        )
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "running")
        dest_id = self._dest(empresa, camp_id)

        await claim_destinatarios(pool, empresa, camp_id, limite=10)
        row = _sql(
            "SELECT status, claimed_by, tentativas, claimed_at IS NOT NULL,"
            " provider_chamado_at FROM campanha_destinatario WHERE id = %s",
            (dest_id,),
        )[0]
        assert row[0] == "enviando"
        assert row[1] == WORKER_ID
        assert row[2] == 1
        assert row[3] is True
        assert row[4] is None, "provider_chamado_at só é marcado antes do envio"

    # ---------- a política do órfão ----------

    async def test_8_orfao_que_nunca_chegou_no_provedor_volta_pra_fila(
        self, empresa
    ) -> None:
        """`provider_chamado_at` NULL = não saiu. Reenviar é seguro."""
        from whatsapp_langchain.shared.campanha_motor import (
            recuperar_destinatarios_orfaos,
        )
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "running")
        dest_id = self._dest(
            empresa,
            camp_id,
            "enviando",
            claimed_at="2020-01-01T00:00:00+00:00",
            claimed_by="worker-morto:999",
        )

        devolvidos, incertos = await recuperar_destinatarios_orfaos(
            pool, empresa, camp_id
        )
        assert (devolvidos, incertos) == (1, 0)
        assert (
            _sql("SELECT status FROM campanha_destinatario WHERE id = %s", (dest_id,))[
                0
            ][0]
            == "pendente"
        )

    async def test_9_orfao_que_pode_ter_saido_vira_incerto_e_nao_reenvia(
        self, empresa
    ) -> None:
        """A decisão de produto: duplicata é pior que buraco.

        Foi blast de mídia em ritmo de texto que queimou o número na campanha 9;
        mandar a mesma mensagem duas vezes é o mesmo sinal de spam. O buraco
        aparece no relatório e é corrigível à mão — a duplicata já saiu.
        """
        from whatsapp_langchain.shared.campanha_motor import (
            recuperar_destinatarios_orfaos,
        )
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "running")
        dest_id = self._dest(
            empresa,
            camp_id,
            "enviando",
            claimed_at="2020-01-01T00:00:00+00:00",
            provider_chamado_at="2020-01-01T00:00:01+00:00",
        )

        devolvidos, incertos = await recuperar_destinatarios_orfaos(
            pool, empresa, camp_id
        )
        assert (devolvidos, incertos) == (0, 1)
        status = _sql(
            "SELECT status FROM campanha_destinatario WHERE id = %s", (dest_id,)
        )[0][0]
        assert status == "incerto", "não pode voltar pra 'pendente' — reenviaria"

    async def test_10_em_voo_recente_nao_e_mexido(self, empresa) -> None:
        """Envio vivo não é órfão: só depois de DEST_ORFAO_SEGUNDOS."""
        from whatsapp_langchain.shared.campanha_motor import (
            recuperar_destinatarios_orfaos,
        )
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "running")
        dest_id = self._dest(empresa, camp_id, "enviando", claimed_at="NOW()")
        _sql(
            "UPDATE campanha_destinatario SET claimed_at = NOW() WHERE id = %s",
            (dest_id,),
        )

        assert await recuperar_destinatarios_orfaos(pool, empresa, camp_id) == (0, 0)
        assert (
            _sql("SELECT status FROM campanha_destinatario WHERE id = %s", (dest_id,))[
                0
            ][0]
            == "enviando"
        )

    # ---------- o gate de opt-out sobrevive ao claim ----------

    async def test_11_opt_out_remove_destinatario_ja_reivindicado(
        self, empresa
    ) -> None:
        """Regressão que o claim quase introduziu.

        `remover_suprimidos_pendentes` filtrava por `status='pendente'`. Com o
        claim, o lote está em `enviando` quando o gate roda — o DELETE viraria
        no-op silencioso e o número que pediu descadastro receberia.
        """
        from whatsapp_langchain.shared.campanha import remover_suprimidos_pendentes
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "running")
        telefone = f"+5511{uuid.uuid4().int % 10**9:09d}"
        dest_id = _sql(
            "INSERT INTO campanha_destinatario"
            " (campanha_id, empresa_id, telefone, status)"
            " VALUES (%s, %s, %s, 'enviando') RETURNING id",
            (camp_id, empresa, telefone),
        )[0][0]
        # `wa_jid` é NOT NULL e é a chave única real da supressão; `telefone`
        # é a coluna que o lookup usa.
        _sql(
            "INSERT INTO disparador_opt_out (empresa_id, wa_jid, telefone)"
            " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (empresa, f"{telefone.lstrip('+')}@s.whatsapp.net", telefone),
        )

        removidos = await remover_suprimidos_pendentes(
            pool, empresa, camp_id, [telefone]
        )
        assert telefone in removidos
        assert (
            _sql(
                "SELECT count(*) FROM campanha_destinatario WHERE id = %s", (dest_id,)
            )[0][0]
            == 0
        ), "suprimido em 'enviando' NÃO foi removido — receberia a mensagem"

    # ---------- trilha ----------

    async def test_12_evento_e_gravado_e_isolado_por_empresa(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha_motor import registrar_evento
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp_id = self._nova_campanha(empresa, "running")
        await registrar_evento(
            pool, empresa, camp_id, "lease_expirada", {"dono": "worker-morto:999"}
        )
        rows = _sql(
            "SELECT tipo, payload, empresa_id FROM campanha_evento"
            " WHERE campanha_id = %s",
            (camp_id,),
        )
        assert len(rows) == 1
        assert rows[0][0] == "lease_expirada"
        assert rows[0][1]["dono"] == "worker-morto:999"
        assert rows[0][2] == empresa
