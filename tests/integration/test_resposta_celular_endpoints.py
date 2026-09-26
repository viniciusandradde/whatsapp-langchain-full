"""E2E da ADR-008 (mig 205): resposta do dono pelo celular (Evolution
`fromMe`) vira bolha "WhatsApp (celular)" e pausa a IA na conversa;
"Devolver à IA" retoma.

Usa a conexão Evolution padrão da empresa 1 do dev (worker em
`EVOLUTION_OUTBOUND_MODE=mock`, nada sai para o WhatsApp).

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_resposta_celular_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import psycopg
import pytest

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
_TEL = f"+5567998{int(_RUN[:5], 16) % 1000000:06d}"


@pytest.fixture(scope="module")
def ambiente():
    try:
        if httpx.get(f"{API_BASE_URL}/health", timeout=3).status_code != 200:
            pytest.skip("API do dev fora do ar")
    except Exception:
        pytest.skip("API do dev fora do ar")
    url = get_db_url()
    instancia = os.environ.get("EVOLUTION_INSTANCE_NAME", "empresa1_nexus_dev")
    apikey = os.environ.get("EVOLUTION_API_KEY", "")
    if not apikey:
        pytest.skip("EVOLUTION_API_KEY não definido")
    yield {"db": url, "instancia": instancia, "apikey": apikey}
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'true', false)")
        cur.execute(
            "DELETE FROM message_queue WHERE empresa_id = 1 AND phone_number = %s",
            (_TEL,),
        )
        cur.execute(
            "DELETE FROM atendimento WHERE empresa_id = 1 AND cliente_id IN "
            "(SELECT id FROM cliente WHERE empresa_id = 1 AND telefone = %s)",
            (_TEL,),
        )
        cur.execute(
            "DELETE FROM cliente WHERE empresa_id = 1 AND telefone = %s", (_TEL,)
        )


def _upsert(amb, *, from_me: bool, texto: str, mid: str) -> httpx.Response:
    corpo = {
        "event": "messages.upsert",
        "instance": amb["instancia"],
        "data": {
            "key": {
                "remoteJid": f"{_TEL.lstrip('+')}@s.whatsapp.net",
                "fromMe": from_me,
                "id": mid,
            },
            "message": {"conversation": texto},
            "pushName": "E2E Celular",
            "messageTimestamp": int(time.time()),
            "source": "android",
        },
    }
    return httpx.post(
        f"{API_BASE_URL}/webhook/evolution",
        json=corpo,
        headers={"apikey": amb["apikey"]},
        timeout=15,
    )


def _consulta(amb, sql: str, params: tuple):
    with psycopg.connect(amb["db"]) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


@pytest.mark.docker_demo
class TestE2ERespostaCelular:
    def test_01_resposta_do_celular_vira_bolha_e_pausa_a_ia(self, ambiente):
        mid = f"CEL-{_RUN}-1"
        assert (
            _upsert(
                ambiente, from_me=True, texto="Oi, aqui é pelo celular", mid=mid
            ).status_code
            == 200
        )
        linhas = _consulta(
            ambiente,
            "SELECT origem_resposta, normalized_input, response, atendimento_id FROM message_queue "
            "WHERE message_id = %s",
            (mid,),
        )
        assert len(linhas) == 1, linhas
        origem, ni, resp, atd = linhas[0]
        assert (
            origem == "celular"
            and ni == "manual:app:whatsapp"
            and resp == "Oi, aqui é pelo celular"
        )
        dono = _consulta(
            ambiente,
            "SELECT status, assigned_to_user_id FROM atendimento WHERE id = %s",
            (atd,),
        )
        assert dono == [("em_andamento", "whatsapp_celular")]

    def test_02_reentrega_nao_duplica(self, ambiente):
        mid = f"CEL-{_RUN}-1"
        assert (
            _upsert(
                ambiente, from_me=True, texto="Oi, aqui é pelo celular", mid=mid
            ).status_code
            == 200
        )
        n = _consulta(
            ambiente,
            "SELECT count(*) FROM message_queue WHERE message_id = %s",
            (mid,),
        )
        assert n == [(1,)]

    def test_03_grupo_fica_de_fora(self, ambiente):
        corpo_mid = f"CEL-{_RUN}-G"
        r = httpx.post(
            f"{API_BASE_URL}/webhook/evolution",
            json={
                "event": "messages.upsert",
                "instance": ambiente["instancia"],
                "data": {
                    "key": {
                        "remoteJid": "120363000000000@g.us",
                        "fromMe": True,
                        "id": corpo_mid,
                    },
                    "message": {"conversation": "no grupo"},
                },
            },
            headers={"apikey": ambiente["apikey"]},
            timeout=15,
        )
        assert r.status_code == 200
        assert _consulta(
            ambiente,
            "SELECT count(*) FROM message_queue WHERE message_id = %s",
            (corpo_mid,),
        ) == [(0,)]

    def test_04_cliente_escreve_e_a_ia_fica_calada(self, ambiente):
        mid = f"CLI-{_RUN}-1"
        assert (
            _upsert(
                ambiente, from_me=False, texto="Tudo certo então?", mid=mid
            ).status_code
            == 200
        )
        resp = None
        for _ in range(40):
            rows = _consulta(
                ambiente,
                "SELECT status, response FROM message_queue WHERE message_id = %s ORDER BY id DESC LIMIT 1",
                (mid,),
            )
            if rows and rows[0][0] in ("done", "failed"):
                resp = rows[0][1]
                break
            time.sleep(1)
        assert resp is not None, "worker não processou"
        assert resp.startswith("[handoff humano"), resp

    def test_05_devolver_a_ia_retoma(self, ambiente):
        atd = _consulta(
            ambiente,
            "SELECT atendimento_id FROM message_queue WHERE message_id = %s",
            (f"CEL-{_RUN}-1",),
        )[0][0]
        h = get_admin_api_headers()
        h["X-User-Id"] = "dev-admin-0001"
        h["X-Empresa-Id"] = "1"
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atd}/devolver-ia", headers=h, timeout=15
        )
        assert r.status_code == 200, r.text
        dono = _consulta(
            ambiente,
            "SELECT assigned_to_user_id FROM atendimento WHERE id = %s",
            (atd,),
        )
        assert dono == [(None,)]
