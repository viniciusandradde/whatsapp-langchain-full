"""Chave da OpenRouter por empresa (ADR-007, mig 204).

Cobre o que não depende de banco nem de rede real: o contexto (empresa vence
plataforma e volta ao sair), a factory de modelo honrando o contexto, a
marca `chave_propria` no `ia_execucao`, o cache de leitura, e o cliente da
OpenRouter com respostas simuladas (respx) — inclusive o formato barrado
ANTES de qualquer chamada de rede.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from pydantic import SecretStr

from whatsapp_langchain.integrations import openrouter_gestao as gestao
from whatsapp_langchain.integrations.crypto import encrypt_str
from whatsapp_langchain.shared import openrouter_chave as oc
from whatsapp_langchain.shared.config import settings

_BASE = settings.openrouter_base_url.rstrip("/")


@pytest.fixture(autouse=True)
def _plataforma(monkeypatch):
    monkeypatch.setattr(
        settings, "openrouter_api_key", SecretStr("sk-or-v1-plataforma-000000")
    )
    monkeypatch.setattr(settings, "openrouter_tts_api_key", None)
    monkeypatch.setattr(settings, "openrouter_provisioning_key", None)
    oc.limpar_cache()
    yield
    oc.limpar_cache()


# --- contexto -----------------------------------------------------------------


class TestContexto:
    def test_sem_contexto_usa_a_plataforma(self):
        chave = oc.chave_openrouter()
        assert chave is not None
        assert chave.get_secret_value() == "sk-or-v1-plataforma-000000"
        assert oc.chave_e_da_empresa() is False

    def test_com_contexto_usa_a_da_empresa_e_volta_ao_sair(self):
        with oc.usar_chave("sk-or-v1-empresa-111111"):
            chave = oc.chave_openrouter()
            assert chave is not None
            assert chave.get_secret_value() == "sk-or-v1-empresa-111111"
            assert oc.chave_e_da_empresa() is True
            assert (
                oc.chave_openrouter_tts().get_secret_value()
                == "sk-or-v1-empresa-111111"
            )  # type: ignore[union-attr]
        assert oc.chave_openrouter().get_secret_value() == "sk-or-v1-plataforma-000000"  # type: ignore[union-attr]
        assert oc.chave_e_da_empresa() is False

    def test_contexto_vazio_nao_apaga_a_plataforma(self):
        with oc.usar_chave(None):
            assert (
                oc.chave_openrouter().get_secret_value() == "sk-or-v1-plataforma-000000"
            )  # type: ignore[union-attr]

    def test_tts_dedicada_da_plataforma_quando_a_empresa_nao_tem_chave(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            settings, "openrouter_tts_api_key", SecretStr("sk-or-v1-tts-222222")
        )
        assert oc.chave_openrouter_tts().get_secret_value() == "sk-or-v1-tts-222222"  # type: ignore[union-attr]

    def test_factory_do_modelo_honra_o_contexto(self):
        from whatsapp_langchain.shared.llm import create_chat_model

        with oc.usar_chave("sk-or-v1-empresa-333333"):
            model = create_chat_model(model="x/y")
        assert model.openai_api_key is not None
        assert model.openai_api_key.get_secret_value() == "sk-or-v1-empresa-333333"
        fora = create_chat_model(model="x/y")
        assert fora.openai_api_key.get_secret_value() == "sk-or-v1-plataforma-000000"  # type: ignore[union-attr]

    def test_embeddings_um_cliente_por_chave(self):
        from whatsapp_langchain.shared import embeddings as emb

        emb.limpar_clientes()
        plataforma = emb.embeddings_openrouter()
        with oc.usar_chave("sk-or-v1-empresa-444444"):
            da_empresa = emb.embeddings_openrouter()
            assert emb.embeddings_openrouter() is da_empresa
        assert da_empresa is not plataforma
        assert emb.embeddings_openrouter() is plataforma
        assert da_empresa.openai_api_key.get_secret_value() == "sk-or-v1-empresa-444444"  # type: ignore[union-attr]


# --- banco falso ----------------------------------------------------------------


class _Cursor:
    def __init__(self, row):
        self._row = row

    async def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, pool):
        self._pool = pool

    async def execute(self, sql, params=None):
        self._pool.chamadas.append((" ".join(sql.split()), params))
        return _Cursor(self._pool.row)

    async def commit(self):
        self._pool.commits += 1


class _Pool:
    """Devolve sempre `row` e guarda as chamadas."""

    def __init__(self, row=None):
        self.row = row
        self.chamadas: list[tuple[str, tuple | None]] = []
        self.commits = 0

    @asynccontextmanager
    async def connection(self):
        yield _Conn(self)


class TestCarregarChave:
    async def test_decifra_e_cacheia(self):
        pool = _Pool(row=(encrypt_str("sk-or-v1-guardada-555555"),))
        assert await oc.carregar_chave_empresa(pool, 42) == "sk-or-v1-guardada-555555"  # type: ignore[arg-type]
        assert await oc.carregar_chave_empresa(pool, 42) == "sk-or-v1-guardada-555555"  # type: ignore[arg-type]
        assert len(pool.chamadas) == 1, "segunda leitura vem do cache"
        oc.limpar_cache(42)
        await oc.carregar_chave_empresa(pool, 42)  # type: ignore[arg-type]
        assert len(pool.chamadas) == 2

    async def test_sem_chave_e_plataforma(self):
        pool = _Pool(row=(None,))
        assert await oc.carregar_chave_empresa(pool, 7) is None  # type: ignore[arg-type]
        async with oc.chave_da_empresa(pool, 7):  # type: ignore[arg-type]
            assert oc.chave_e_da_empresa() is False

    async def test_cifra_ilegivel_cai_na_plataforma(self):
        pool = _Pool(row=("gAAAAA-lixo-que-nao-decifra",))
        assert await oc.carregar_chave_empresa(pool, 8) is None  # type: ignore[arg-type]

    async def test_chave_da_empresa_entra_no_contexto(self):
        pool = _Pool(row=(encrypt_str("sk-or-v1-guardada-666666"),))
        async with oc.chave_da_empresa(pool, 9) as chave:  # type: ignore[arg-type]
            assert chave == "sk-or-v1-guardada-666666"
            assert oc.chave_openrouter().get_secret_value() == chave  # type: ignore[union-attr]
        assert oc.chave_e_da_empresa() is False


class TestMarcaNoIaExecucao:
    async def test_registrar_execucao_marca_chave_propria(self):
        from whatsapp_langchain.shared.governanca_ia import registrar_execucao

        pool = _Pool(row=(1,))
        with oc.usar_chave("sk-or-v1-empresa-777777"):
            await registrar_execucao(
                pool,  # type: ignore[arg-type]
                empresa_id=1,
                modelo_provedor="google",
                modelo_nome="gemini",
                metadata={"finalidade": "teste"},
            )
        _sql, params = pool.chamadas[0]
        assert params is not None
        meta = json.loads(params[13])
        assert meta == {"finalidade": "teste", "chave_propria": True}

    async def test_sem_contexto_nao_marca(self):
        from whatsapp_langchain.shared.governanca_ia import registrar_execucao

        pool = _Pool(row=(1,))
        await registrar_execucao(
            pool,  # type: ignore[arg-type]
            empresa_id=1,
            modelo_provedor="google",
            modelo_nome="gemini",
        )
        _sql, params = pool.chamadas[0]
        assert params is not None
        assert json.loads(params[13]) == {}


# --- cliente da OpenRouter --------------------------------------------------


class TestMascarar:
    def test_prefixo_curto(self):
        assert gestao.mascarar("sk-or-v1-abcdef0123456789abcdef") == "sk-or-v1-abc…"
        assert gestao.mascarar("curta") == "…"

    def test_formato(self):
        assert gestao.formato_plausivel("sk-or-v1-" + "a" * 40)
        assert not gestao.formato_plausivel("EAAG" + "a" * 60), "token da Meta"
        assert not gestao.formato_plausivel("sk-proj-" + "a" * 40), "chave da OpenAI"
        assert not gestao.formato_plausivel("sk-or-v1-abc def")


class TestConsultarChave:
    async def test_formato_errado_nao_vai_a_rede(self):
        with respx.mock(assert_all_called=False) as mock:
            rota = mock.get(f"{_BASE}/key")
            with pytest.raises(gestao.ChaveInvalidaError):
                await gestao.consultar_chave("EAAG-token-da-meta-" + "x" * 30)
            assert rota.call_count == 0

    async def test_chave_valida(self):
        with respx.mock() as mock:
            mock.get(f"{_BASE}/key").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": {
                            "label": "sk-or-v1-abc...123",
                            "limit": 50,
                            "limit_remaining": 49.5,
                            "usage": 0.5,
                            "usage_monthly": 0.25,
                            "is_free_tier": False,
                        }
                    },
                )
            )
            info = await gestao.consultar_chave("sk-or-v1-" + "a" * 40)
        assert info.limite_usd == 50
        assert info.limite_restante_usd == 49.5
        assert info.uso_usd == 0.5
        assert info.uso_mes_usd == 0.25
        assert info.gratuita is False

    async def test_chave_recusada(self):
        with respx.mock() as mock:
            mock.get(f"{_BASE}/key").mock(
                return_value=httpx.Response(401, json={"error": "x"})
            )
            with pytest.raises(gestao.ChaveInvalidaError):
                await gestao.consultar_chave("sk-or-v1-" + "b" * 40)

    async def test_sem_rede(self):
        with respx.mock() as mock:
            mock.get(f"{_BASE}/key").mock(side_effect=httpx.ConnectError("x"))
            with pytest.raises(gestao.OpenRouterGestaoError):
                await gestao.consultar_chave("sk-or-v1-" + "c" * 40)


class TestGestao:
    async def test_sem_chave_de_provisionamento(self):
        with pytest.raises(gestao.ProvisionamentoNaoConfiguradoError):
            await gestao.criar_chave(nome="x", limite_usd=10)
        assert gestao.provisionamento_configurado() is False

    async def test_criar_chave_le_key_e_hash(self, monkeypatch):
        monkeypatch.setattr(
            settings, "openrouter_provisioning_key", SecretStr("sk-or-v1-gestao-888888")
        )
        with respx.mock() as mock:
            rota = mock.post(f"{_BASE}/keys").mock(
                return_value=httpx.Response(
                    201,
                    json={
                        "data": {
                            "hash": "h123",
                            "name": "chatnexus-1-vsa",
                            "limit": 25,
                        },
                        "key": "sk-or-v1-" + "d" * 40,
                    },
                )
            )
            criada = await gestao.criar_chave(nome="chatnexus-1-vsa", limite_usd=25)
        assert criada.hash == "h123"
        assert criada.chave.startswith("sk-or-v1-dddd")
        assert criada.limite_usd == 25
        pedido = json.loads(rota.calls[0].request.content)
        assert pedido == {"name": "chatnexus-1-vsa", "limit": 25.0}
        assert (
            rota.calls[0].request.headers["Authorization"]
            == "Bearer sk-or-v1-gestao-888888"
        )

    async def test_criar_chave_sem_limite_nao_manda_limit(self, monkeypatch):
        monkeypatch.setattr(
            settings, "openrouter_provisioning_key", SecretStr("sk-or-v1-gestao-888888")
        )
        with respx.mock() as mock:
            rota = mock.post(f"{_BASE}/keys").mock(
                return_value=httpx.Response(
                    200, json={"data": {"hash": "h1"}, "key": "sk-or-v1-" + "e" * 40}
                )
            )
            await gestao.criar_chave(nome="n", limite_usd=None)
        assert json.loads(rota.calls[0].request.content) == {"name": "n"}

    async def test_gestao_recusada_e_erro_de_configuracao(self, monkeypatch):
        monkeypatch.setattr(
            settings, "openrouter_provisioning_key", SecretStr("sk-or-v1-gestao-errada")
        )
        with respx.mock() as mock:
            mock.post(f"{_BASE}/keys").mock(return_value=httpx.Response(401))
            with pytest.raises(gestao.ProvisionamentoNaoConfiguradoError):
                await gestao.criar_chave(nome="n", limite_usd=None)

    async def test_apagar_404_e_idempotente(self, monkeypatch):
        monkeypatch.setattr(
            settings, "openrouter_provisioning_key", SecretStr("sk-or-v1-gestao-888888")
        )
        with respx.mock() as mock:
            mock.delete(f"{_BASE}/keys/h9").mock(return_value=httpx.Response(404))
            assert await gestao.apagar_chave_gerida("h9") is True

    async def test_atualizar_limite(self, monkeypatch):
        monkeypatch.setattr(
            settings, "openrouter_provisioning_key", SecretStr("sk-or-v1-gestao-888888")
        )
        with respx.mock() as mock:
            rota = mock.patch(f"{_BASE}/keys/h9").mock(
                return_value=httpx.Response(
                    200, json={"data": {"hash": "h9", "limit": 30}}
                )
            )
            info = await gestao.atualizar_chave_gerida("h9", limite_usd=30)
        assert info.limite_usd == 30
        assert json.loads(rota.calls[0].request.content) == {"limit": 30.0}


# --- operações sobre o banco falso -------------------------------------------


class _PoolLinha(_Pool):
    """Simula a linha de `empresa` lida por `_ler` e responde 1 para o audit."""

    def __init__(self, linha):
        super().__init__(row=linha)


class TestDefinirChavePropria:
    async def test_grava_cifrada_e_nao_devolve_a_chave(self, monkeypatch):
        linha = (1, "vsa", None, None, None, None, None, None)
        pool = _PoolLinha(linha)

        async def _audit(*a, **k):
            return 1

        monkeypatch.setattr("whatsapp_langchain.shared.audit.record_audit", _audit)
        with respx.mock() as mock:
            mock.get(f"{_BASE}/key").mock(
                return_value=httpx.Response(
                    200, json={"data": {"usage": 0, "limit": None}}
                )
            )
            st = await oc.definir_chave_propria(
                pool,  # type: ignore[arg-type]
                1,
                "sk-or-v1-" + "f" * 40,
                user_id="u1",
            )
        assert st is not None
        update = next(c for c in pool.chamadas if c[0].startswith("UPDATE empresa"))
        params = update[1]
        assert params is not None
        assert params[0] != "sk-or-v1-" + "f" * 40, "vai cifrada"
        assert params[1] == "sk-or-v1-fff…"
        assert params[2] == "propria"
        assert "sk-or-v1-" + "f" * 40 not in json.dumps(st.to_dict())

    async def test_chave_recusada_nao_grava(self, monkeypatch):
        pool = _PoolLinha((1, "vsa", None, None, None, None, None, None))
        with respx.mock() as mock:
            mock.get(f"{_BASE}/key").mock(return_value=httpx.Response(401))
            with pytest.raises(gestao.ChaveInvalidaError):
                await oc.definir_chave_propria(
                    pool,  # type: ignore[arg-type]
                    1,
                    "sk-or-v1-" + "g" * 40,
                    user_id="u1",
                )
        assert not any(c[0].startswith("UPDATE") for c in pool.chamadas)

    async def test_limite_so_para_provisionada(self):
        pool = _PoolLinha(
            (
                1,
                "vsa",
                encrypt_str("sk-or-v1-" + "h" * 40),
                "sk-or-v1-hhh…",
                "propria",
                None,
                None,
                None,
            )
        )
        with pytest.raises(oc.ChaveNaoGeridaError):
            await oc.definir_limite(pool, 1, 10, user_id="u1")  # type: ignore[arg-type]
