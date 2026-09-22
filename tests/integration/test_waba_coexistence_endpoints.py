"""Smoke + E2E do WhatsApp Coexistence (mig 200).

Smoke (sem DB): rota nova existe e exige service token.

E2E (stack de dev rodando, `docker_demo`): o webhook `/webhook/waba` recebe
payloads no formato da Meta ASSINADOS com o `META_APP_SECRET` do dev e o
teste confere no banco o que o backend garante:

1. schema — `waba_mode` default `cloud_api`; Evolution não pode ser coexistence;
2. cliente escreve → cliente + atendimento abertos, mensagem na fila do worker;
3. a empresa responde pelo celular (eco) → linha de SAÍDA `done`, origem
   `whatsapp_business_app`, sem linha nova na fila e sem chamada de IA;
4. o atendimento fica com o dono "celular" → a próxima do cliente cai no
   marcador de handoff (IA calada); "Devolver à IA" limpa o dono;
5. o mesmo eco reentregue → uma linha só;
6. assinatura inválida → nada gravado;
7. `phone_number_id` de outra empresa nunca grava nesta;
8. histórico → atendimento `resolvido` com as mensagens, sem abrir conversa na fila;
9. `account_update` PARTNER_REMOVED → conexão desconectada.

Rodar:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_waba_coexistence_endpoints.py -v

O segredo vem de `META_APP_SECRET` no ambiente ou do `.env.local` do dev. O
token falso da conexão é cifrado com a mesma chave do dev (sem
`INTEGRACOES_ENCRYPTION_KEY`, ela cai no `INTERNAL_SERVICE_TOKEN`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
import time
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.integrations.crypto import encrypt_dict

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
# Números só com dígitos (a Meta manda sem `+`); únicos por run.
_NUM_EMPRESA = f"5567{int(_RUN, 16) % 10**8:08d}"
_NUM_CLIENTE = f"5511{(int(_RUN, 16) + 1) % 10**8:08d}"
_NUM_HIST = f"5521{(int(_RUN, 16) + 2) % 10**8:08d}"
_PHONE_ID = f"e2e-coex-{_RUN}"
_PHONE_ID_B = f"e2e-coex-b-{_RUN}"
_WABA_ID = f"e2e-waba-{_RUN}"


# ============================================================================
# Smoke
# ============================================================================


class TestSmoke:
    def test_sincronizar_sem_auth_401(self) -> None:
        from whatsapp_langchain.server.main import app

        r = TestClient(app).post("/api/conexoes/1/waba/sincronizar")
        assert r.status_code == 401, r.text


# ============================================================================
# E2E
# ============================================================================


def _segredo() -> str | None:
    if os.getenv("META_APP_SECRET"):
        return os.environ["META_APP_SECRET"]
    arquivo = pathlib.Path(__file__).resolve().parents[2] / ".env.local"
    if arquivo.exists():
        for linha in arquivo.read_text().splitlines():
            if linha.startswith("META_APP_SECRET="):
                return linha.split("=", 1)[1].strip() or None
    return None


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("API não saudável. Rode: make up")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")
    if not _segredo():
        pytest.skip("META_APP_SECRET ausente (ambiente ou .env.local do dev)")
    return get_db_url()


@pytest.fixture(scope="module")
def cenario(db_url: str):
    """Empresa Pro + agente + conexão Coexistence; e uma 2ª empresa (tenant)."""
    ids: dict = {}
    with psycopg.connect(db_url, autocommit=True) as conn:
        for chave, phone_id, numero in (
            ("a", _PHONE_ID, _NUM_EMPRESA),
            ("b", _PHONE_ID_B, f"5531{int(_RUN, 16) % 10**8:08d}"),
        ):
            eid = conn.execute(
                "INSERT INTO empresa (nome, slug, plano, status)"
                " VALUES (%s, %s, 'pro', 'active') RETURNING id",
                (f"e2e-coex-{chave}-{_RUN}", f"e2e-coex-{chave}-{_RUN}"),
            ).fetchone()[0]
            slug = f"agente-coex-{chave}-{_RUN}"
            conn.execute(
                "INSERT INTO agente_ia (empresa_id, slug, nome, ativo, is_default)"
                " VALUES (%s, %s, %s, TRUE, TRUE)",
                (eid, slug, f"Agente Coex {_RUN}"),
            )
            cid = conn.execute(
                """
                INSERT INTO conexao (empresa_id, provider, from_number,
                                     display_name, default_agent_id, status,
                                     tipo_atendimento, waba_account_id,
                                     waba_phone_id, waba_mode, connection_state)
                VALUES (%s, 'waba', %s, %s, %s, 'active', 'manual', %s, %s,
                        'coexistence', 'open')
                RETURNING id
                """,
                (
                    eid,
                    "+" + numero,
                    f"Coex {chave} {_RUN}",
                    slug,
                    _WABA_ID if chave == "a" else f"{_WABA_ID}-b",
                    phone_id,
                ),
            ).fetchone()[0]
            # O worker monta o cliente de saída antes dos gates: sem token
            # cifrado a row volta pra fila. Token falso — nada sai (modo
            # manual, e depois o gate de handoff cala antes de enviar).
            conn.execute(
                "UPDATE conexao SET credentials_encrypted = %s WHERE id = %s",
                (
                    encrypt_dict(
                        {
                            "access_token": f"token-falso-{_RUN}",
                            "waba_account_id": _WABA_ID,
                            "phone_id": phone_id,
                        }
                    ),
                    cid,
                ),
            )
            ids[chave] = {"empresa": eid, "conexao": cid, "slug": slug}
        uid = f"e2e-coex-user-{_RUN}"
        conn.execute(
            'INSERT INTO auth."user" (id, name, email, "emailVerified",'
            ' "createdAt", "updatedAt", status, is_superadmin)'
            " VALUES (%s, 'E2E Coex', %s, TRUE, NOW(), NOW(), 'active', TRUE)",
            (uid, f"{uid}@e2e.test"),
        )
        conn.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)"
            " VALUES (%s, %s, 'admin', TRUE)",
            (ids["a"]["empresa"], uid),
        )
        ids["user"] = uid
    yield ids
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "DELETE FROM waba_wamid_processado WHERE wamid LIKE %s",
            (f"wamid.e2e-{_RUN}-%",),
        )
        for chave in ("a", "b"):
            eid = ids[chave]["empresa"]
            conn.execute("DELETE FROM message_queue WHERE empresa_id = %s", (eid,))
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))
        conn.execute('DELETE FROM auth."user" WHERE id = %s', (ids["user"],))


def _post(payload: dict, *, segredo: str | None = None) -> httpx.Response:
    corpo = json.dumps(payload).encode()
    chave = (segredo or _segredo() or "").encode()
    sig = "sha256=" + hmac.new(chave, corpo, hashlib.sha256).hexdigest()
    return httpx.post(
        f"{API_BASE_URL}/webhook/waba",
        content=corpo,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        timeout=15,
    )


def _envelope(field: str, value: dict, entry_id: str = _WABA_ID) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": entry_id, "changes": [{"field": field, "value": value}]}],
    }


def _metadata(phone_id: str = _PHONE_ID) -> dict:
    return {"display_phone_number": _NUM_EMPRESA, "phone_number_id": phone_id}


def _inbound(wamid: str, texto: str, phone_id: str = _PHONE_ID) -> dict:
    return _envelope(
        "messages",
        {
            "messaging_product": "whatsapp",
            "metadata": _metadata(phone_id),
            "contacts": [{"wa_id": _NUM_CLIENTE, "profile": {"name": "Cliente E2E"}}],
            "messages": [
                {
                    "from": _NUM_CLIENTE,
                    "id": wamid,
                    "timestamp": str(int(time.time())),
                    "type": "text",
                    "text": {"body": texto},
                }
            ],
        },
    )


def _eco(wamid: str, texto: str) -> dict:
    return _envelope(
        "smb_message_echoes",
        {
            "messaging_product": "whatsapp",
            "metadata": _metadata(),
            "message_echoes": [
                {
                    "from": _NUM_EMPRESA,
                    "to": _NUM_CLIENTE,
                    "id": wamid,
                    "timestamp": str(int(time.time())),
                    "type": "text",
                    "text": {"body": texto},
                }
            ],
        },
    )


def _wamid(nome: str) -> str:
    return f"wamid.e2e-{_RUN}-{nome}"


def _um(db_url: str, sql: str, params: tuple):
    with psycopg.connect(db_url) as conn:
        return conn.execute(sql, params).fetchone()


def _todas(db_url: str, sql: str, params: tuple):
    with psycopg.connect(db_url) as conn:
        return conn.execute(sql, params).fetchall()


def _esperar_done(db_url: str, wamid: str, timeout: float = 45.0):
    """Espera o worker do dev processar a row do cliente; devolve a response."""
    fim = time.time() + timeout
    while time.time() < fim:
        row = _um(
            db_url,
            "SELECT status, response FROM message_queue WHERE message_id = %s",
            (wamid,),
        )
        if row and row[0] in ("done", "failed"):
            return row
        time.sleep(1)
    pytest.fail(f"worker não processou {wamid} em {timeout}s")


@pytest.mark.docker_demo
class TestE2E:
    def test_1_schema_waba_mode(self, db_url: str, cenario) -> None:
        row = _um(
            db_url,
            "SELECT waba_mode FROM conexao WHERE id = %s",
            (cenario["a"]["conexao"],),
        )
        assert row == ("coexistence",)
        with psycopg.connect(db_url, autocommit=True) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO conexao (empresa_id, provider, from_number,"
                    " waba_mode) VALUES (%s, 'evolution', %s, 'coexistence')",
                    (cenario["a"]["empresa"], f"evolution:e2e-{_RUN}"),
                )
        # Conexão que não informa o modo nasce cloud_api.
        with psycopg.connect(db_url, autocommit=True) as conn:
            modo = conn.execute(
                "INSERT INTO conexao (empresa_id, provider, from_number, status)"
                " VALUES (%s, 'waba', %s, 'disabled') RETURNING waba_mode",
                (cenario["a"]["empresa"], f"+5500{int(_RUN, 16) % 10**8:08d}"),
            ).fetchone()
        assert modo == ("cloud_api",)

    def test_1b_api_expoe_waba_mode(self, cenario) -> None:
        h = get_admin_api_headers()
        h["X-User-Id"] = cenario["user"]
        h["X-Empresa-Id"] = str(cenario["a"]["empresa"])
        r = httpx.get(
            f"{API_BASE_URL}/api/conexoes/{cenario['a']['conexao']}",
            headers=h,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["waba_mode"] == "coexistence"

    def test_2_cliente_abre_atendimento_e_vai_ao_worker(
        self, db_url: str, cenario
    ) -> None:
        r = _post(_inbound(_wamid("in1"), "Olá, tudo bem?"))
        assert r.status_code == 200, r.text
        row = _um(
            db_url,
            "SELECT atendimento_id, empresa_id, conexao_id FROM message_queue"
            " WHERE message_id = %s",
            (_wamid("in1"),),
        )
        assert row is not None, "mensagem do cliente não entrou na fila"
        assert row[0] is not None, "WABA inbound sem atendimento (lacuna antiga)"
        assert row[1:] == (cenario["a"]["empresa"], cenario["a"]["conexao"])
        cli = _um(
            db_url,
            "SELECT nome FROM cliente WHERE empresa_id = %s AND telefone = %s",
            (cenario["a"]["empresa"], "+" + _NUM_CLIENTE),
        )
        assert cli == ("Cliente E2E",)
        # Conexão em modo manual: o worker registra sem chamar a IA.
        status, _resp = _esperar_done(db_url, _wamid("in1"))
        assert status == "done"
        cenario["atendimento"] = row[0]

    def test_3_eco_vira_saida_sem_ia(self, db_url: str, cenario) -> None:
        antes = _um(
            db_url,
            "SELECT COUNT(*) FROM message_queue WHERE empresa_id = %s",
            (cenario["a"]["empresa"],),
        )[0]
        r = _post(_eco(_wamid("eco1"), "Respondi pelo celular"))
        assert r.status_code == 200, r.text
        row = _um(
            db_url,
            "SELECT status, incoming_message, response, normalized_input,"
            " origem_resposta, atendimento_id FROM message_queue"
            " WHERE message_id = %s",
            (_wamid("eco1"),),
        )
        assert row is not None, r.text
        status, incoming, response, normalized, origem, atd = row
        assert status == "done"  # o claim do worker nunca pega
        assert incoming == ""
        assert response == "Respondi pelo celular"
        assert normalized == "manual:app:whatsapp_business"
        assert origem == "whatsapp_business_app"
        assert atd == cenario["atendimento"]
        depois = _um(
            db_url,
            "SELECT COUNT(*) FROM message_queue WHERE empresa_id = %s",
            (cenario["a"]["empresa"],),
        )[0]
        assert depois == antes + 1
        fila = _um(
            db_url,
            "SELECT COUNT(*) FROM message_queue WHERE empresa_id = %s"
            " AND status IN ('queued', 'processing')",
            (cenario["a"]["empresa"],),
        )[0]
        assert fila == 0
        ia = _um(
            db_url,
            "SELECT COUNT(*) FROM ia_execucao WHERE empresa_id = %s",
            (cenario["a"]["empresa"],),
        )[0]
        assert ia == 0

    def test_4_ia_pausada_ate_devolver(self, db_url: str, cenario) -> None:
        atd = _um(
            db_url,
            "SELECT status, assigned_to_user_id FROM atendimento WHERE id = %s",
            (cenario["atendimento"],),
        )
        assert atd == ("em_andamento", "whatsapp_business_app")

        # Conexão passa a IA: a próxima do cliente tem de cair no handoff.
        with psycopg.connect(db_url, autocommit=True) as conn:
            conn.execute(
                "UPDATE conexao SET tipo_atendimento = 'ia' WHERE id = %s",
                (cenario["a"]["conexao"],),
            )
        try:
            assert _post(_inbound(_wamid("in2"), "Ainda está aí?")).status_code == 200
            status, response = _esperar_done(db_url, _wamid("in2"))
            assert status == "done"
            assert response == "[handoff humano — operador respondendo]"
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                conn.execute(
                    "UPDATE conexao SET tipo_atendimento = 'manual' WHERE id = %s",
                    (cenario["a"]["conexao"],),
                )

        h = get_admin_api_headers()
        h["X-User-Id"] = cenario["user"]
        h["X-Empresa-Id"] = str(cenario["a"]["empresa"])
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{cenario['atendimento']}/devolver-ia",
            headers=h,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        atd = _um(
            db_url,
            "SELECT status, assigned_to_user_id FROM atendimento WHERE id = %s",
            (cenario["atendimento"],),
        )
        assert atd == ("aguardando", None)

    def test_5_eco_reentregue_grava_uma_vez(self, db_url: str, cenario) -> None:
        for _ in range(2):
            assert _post(_eco(_wamid("eco2"), "Duplicado?")).status_code == 200
        n = _um(
            db_url,
            "SELECT COUNT(*) FROM message_queue WHERE message_id = %s",
            (_wamid("eco2"),),
        )[0]
        assert n == 1

    def test_6_assinatura_invalida_nao_grava(self, db_url: str, cenario) -> None:
        r = _post(_eco(_wamid("forjado"), "forjado"), segredo="errado")
        assert r.json()["status"] == "rejected"
        assert (
            _um(
                db_url,
                "SELECT COUNT(*) FROM message_queue WHERE message_id = %s",
                (_wamid("forjado"),),
            )[0]
            == 0
        )

    def test_7_tenant_pelo_phone_number_id(self, db_url: str, cenario) -> None:
        r = _post(_inbound(_wamid("in-b"), "Oi empresa B", phone_id=_PHONE_ID_B))
        assert r.status_code == 200, r.text
        row = _um(
            db_url,
            "SELECT empresa_id FROM message_queue WHERE message_id = %s",
            (_wamid("in-b"),),
        )
        assert row == (cenario["b"]["empresa"],)
        # phone_number_id desconhecido: nada gravado em lugar nenhum.
        r = _post(_inbound(_wamid("in-x"), "ninguém", phone_id=f"nao-existe-{_RUN}"))
        assert r.status_code == 200
        assert (
            _um(
                db_url,
                "SELECT COUNT(*) FROM message_queue WHERE message_id = %s",
                (_wamid("in-x"),),
            )[0]
            == 0
        )

    def test_8_historico_em_atendimento_resolvido(self, db_url: str, cenario) -> None:
        agora = int(time.time())
        payload = _envelope(
            "history",
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "history": [
                    {
                        "metadata": {"phase": 0, "chunk_order": 1, "progress": 100},
                        "threads": [
                            {
                                "id": _NUM_HIST,
                                "messages": [
                                    {
                                        "from": _NUM_HIST,
                                        "id": _wamid("h1"),
                                        "timestamp": str(agora - 7200),
                                        "type": "text",
                                        "text": {"body": "Pergunta antiga"},
                                    },
                                    {
                                        "from": _NUM_EMPRESA,
                                        "id": _wamid("h2"),
                                        "timestamp": str(agora - 7100),
                                        "type": "text",
                                        "text": {"body": "Resposta antiga"},
                                    },
                                    {
                                        "from": _NUM_HIST,
                                        "id": _wamid("h3"),
                                        "timestamp": str(agora - 7000),
                                        "type": "image",
                                        "image": {},
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
        )
        for _ in range(2):  # reentrega não duplica
            assert _post(payload).status_code == 200
        rows = _todas(
            db_url,
            "SELECT q.message_id, q.incoming_message, q.response, q.status,"
            " a.status, a.assigned_to_user_id"
            " FROM message_queue q JOIN atendimento a ON a.id = q.atendimento_id"
            " WHERE q.message_id = ANY(%s) ORDER BY q.created_at",
            ([_wamid("h1"), _wamid("h2"), _wamid("h3")],),
        )
        # Só texto: a imagem sem legenda não entra.
        assert [r[0] for r in rows] == [_wamid("h1"), _wamid("h2")]
        assert rows[0][1] == "Pergunta antiga" and rows[0][2] is None
        assert rows[1][1] == "" and rows[1][2] == "Resposta antiga"
        assert {r[3] for r in rows} == {"done"}
        assert {(r[4], r[5]) for r in rows} == {("resolvido", "whatsapp_business_app")}
        # Não abre conversa na fila.
        abertos = _um(
            db_url,
            "SELECT COUNT(*) FROM atendimento a JOIN cliente c ON c.id = a.cliente_id"
            " WHERE c.empresa_id = %s AND c.telefone = %s"
            " AND a.status IN ('aguardando', 'em_andamento')",
            (cenario["a"]["empresa"], "+" + _NUM_HIST),
        )[0]
        assert abertos == 0

    def test_9_partner_removed_desconecta(self, db_url: str, cenario) -> None:
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": _WABA_ID,
                    "time": int(time.time()),
                    "changes": [
                        {
                            "field": "account_update",
                            "value": {
                                "phone_number": _NUM_EMPRESA,
                                "event": "PARTNER_REMOVED",
                                "disconnection_info": {
                                    "reason": "PRIMARY_INACTIVITY",
                                    "initiated_by": "SYSTEM",
                                },
                            },
                        }
                    ],
                }
            ],
        }
        assert _post(payload).status_code == 200
        row = _um(
            db_url,
            "SELECT connection_state, ultimo_health_check_ok, state_message"
            " FROM conexao WHERE id = %s",
            (cenario["a"]["conexao"],),
        )
        assert row[0] == "disconnected"
        assert row[1] is False
        assert "WhatsApp Business" in row[2]
        # A conexão da outra empresa (outra WABA) não é tocada.
        outra = _um(
            db_url,
            "SELECT connection_state FROM conexao WHERE id = %s",
            (cenario["b"]["conexao"],),
        )
        assert outra == ("open",)
