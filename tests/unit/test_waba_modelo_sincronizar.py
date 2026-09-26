"""Sincronizar modelo e auditoria com data (produção, 25/09/2026).

1. A Meta devolve `quality_score` como OBJETO (`{"score": "GREEN", "date": …}`)
   e o "Sincronizar" gravava o dict na coluna de texto → `cannot adapt type
   'dict'` e erro 500 no painel.
2. `record_audit` usava `json.dumps` puro; o diff de `cliente.update` traz
   datetime (`updated_at`, `classificado_em`) e a auditoria se perdia com
   "datetime is not JSON serializable".
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from whatsapp_langchain.integrations.waba import templates as waba_templates
from whatsapp_langchain.integrations.waba.models import WabaTemplateRecord
from whatsapp_langchain.server.routes import waba_templates as rota
from whatsapp_langchain.shared.audit import record_audit


class TestNotaDeQualidade:
    def test_objeto_da_meta_vira_texto(self):
        assert (
            waba_templates.nota_de_qualidade({"score": "GREEN", "date": 1727})
            == "GREEN"
        )

    def test_objeto_sem_nota(self):
        assert waba_templates.nota_de_qualidade({"date": 1727}) is None
        assert waba_templates.nota_de_qualidade({"score": ""}) is None

    def test_texto_passa(self):
        assert waba_templates.nota_de_qualidade("UNKNOWN") == "UNKNOWN"

    def test_vazio(self):
        assert waba_templates.nota_de_qualidade(None) is None
        assert waba_templates.nota_de_qualidade("") is None


class _Cur:
    def __init__(self, row):
        self._row = row

    async def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, pool):
        self._pool = pool

    async def execute(self, sql, params=None):
        self._pool.chamadas.append((" ".join(sql.split()), params))
        return _Cur(self._pool.row)

    async def commit(self):
        pass


class _Pool:
    def __init__(self, row):
        self.row = row
        self.chamadas: list[tuple[str, tuple | None]] = []

    @asynccontextmanager
    async def connection(self):
        yield _Conn(self)


def _modelo() -> WabaTemplateRecord:
    agora = datetime.now(UTC)
    return WabaTemplateRecord(
        id=1,
        empresa_id=1025,
        conexao_id=7,
        nome="hello_world",
        categoria="UTILITY",
        idioma="en_US",
        componentes_json=[],
        status="approved",
        meta_template_id="1375186281121391",
        meta_quality_score=None,
        motivo_rejeicao=None,
        ultimo_sync_at=None,
        created_at=agora,
        updated_at=agora,
        created_by_user_id=None,
        provider="waba",
        content_sid=None,
    )


class TestSincronizar:
    async def test_grava_a_nota_como_texto(self, monkeypatch):
        agora = datetime.now(UTC)
        linha = (
            1,
            1025,
            7,
            "hello_world",
            "UTILITY",
            "en_US",
            [],
            "approved",
            "1375186281121391",
            "GREEN",
            None,
            agora,
            agora,
            agora,
            None,
            "waba",
            None,
        )
        pool = _Pool(row=linha)

        async def _cred(_pool, _cid):
            return {"access_token": "tok-de-teste"}

        async def _meta(_tok, _mid):
            return {
                "status": "APPROVED",
                "quality_score": {"score": "GREEN", "date": 1727000000},
                "rejected_reason": "NONE",
            }

        monkeypatch.setattr(rota, "get_credentials_decrypted", _cred)
        monkeypatch.setattr(rota.waba_templates, "sync_template_status", _meta)

        out = await rota._sync_template_internal(pool, _modelo())  # type: ignore[arg-type]

        assert out is not None
        _sql, params = pool.chamadas[0]
        assert params is not None
        status, qualidade = params[0], params[1]
        assert status == "approved"
        assert qualidade == "GREEN", "o dict da Meta não pode chegar ao banco"


class TestAuditoriaComData:
    async def test_diff_com_datetime_e_decimal_e_gravado(self):
        pool = _Pool(row=(99,))
        quando = datetime(2026, 9, 25, 20, 41, tzinfo=UTC)
        rid = await record_audit(
            pool,  # type: ignore[arg-type]
            empresa_id=1025,
            user_id="u1",
            action="cliente.update",
            entity_type="cliente",
            entity_id="10856",
            payload_diff={
                "before": {
                    "updated_at": quando,
                    "valor_estimado_brl": Decimal("10.50"),
                },
                "after": {"updated_at": quando, "classificado_em": quando},
            },
        )
        assert rid == 99, "a auditoria não pode se perder por causa de uma data"
        _sql, params = pool.chamadas[0]
        assert params is not None
        gravado = json.loads(params[5])
        assert gravado["after"]["classificado_em"].startswith("2026-09-25 20:41")
        assert gravado["before"]["valor_estimado_brl"] == "10.50"
