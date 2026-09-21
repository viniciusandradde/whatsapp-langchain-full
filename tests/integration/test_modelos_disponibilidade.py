"""E2E da disponibilidade real dos modelos em uso (21/09/2026): `modelos_em_uso`
lê o modelo do seletor (provedor/nome), a sonda falsa abre `modelo_indisponivel`
e avisa o canal (caixa falsa), o catálogo marca o modelo como indisponível,
`modelo_fora_de_circulacao` manda o runtime para o padrão, e mensagens
`failed` em série abrem `agente_falhando`.

Rodar contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_modelos_disponibilidade.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import _criar_empresa, _dar_perfil_admin, _headers
from .test_plano_leva_e_endpoints import _apagar_empresa, _criar_user

_RUN = uuid.uuid4().hex[:8]
_SLUG = "deepseek/deepseek-v4.1-flash"


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        if httpx.get(f"{API_BASE_URL}/health", timeout=3).status_code != 200:
            pytest.skip("API não saudável")
    except Exception:
        pytest.skip("API não acessível")
    return get_db_url()


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-modelos-{_RUN}")
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM ia_alerta WHERE modelo_slug LIKE %s", (f"agente:{eid}:%",)
        )
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def agente_slug(db_url: str, empresa_id: int):
    slug = f"ag-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agente_ia (empresa_id, slug, nome, ativo, modelo,
                                   modelo_provedor, modelo_nome)
            VALUES (%s, %s, 'Agente teste', TRUE, 'google/gemini-2.5-flash-lite',
                    'deepseek', 'deepseek-v4.1-flash')
            """,
            (empresa_id, slug),
        )
    yield slug


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-modelos-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        _criar_user(cur, user_id, superadmin=False)
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, user_id),
        )
        _dar_perfil_admin(cur, empresa_id, user_id)
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


class _Caixa:
    def __init__(self) -> None:
        self.msgs: list[tuple[str, list[str]]] = []

    async def notificar(self, titulo: str, linhas: list[str]) -> bool:
        self.msgs.append((titulo, linhas))
        return True


def _ativos(db_url: str, chave: str) -> list[str]:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT tipo FROM ia_alerta WHERE modelo_slug = %s AND resolvido_em IS NULL ORDER BY tipo",
            (chave,),
        )
        return [r[0] for r in cur.fetchall()]


def _limpar_episodios_do_slug(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ia_alerta WHERE modelo_slug = %s", (_SLUG,))


@pytest.mark.docker_demo
class TestE2E:
    async def test_01_modelos_em_uso_le_o_modelo_do_seletor(
        self, db_url: str, agente_slug: str
    ) -> None:
        from whatsapp_langchain.shared.openrouter_catalogo import modelos_em_uso

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            slugs = await modelos_em_uso(pool, incluir_curados=False)
        assert _SLUG in slugs, slugs

    async def test_02_sonda_inexistente_abre_avisa_e_marca_o_catalogo(
        self, db_url: str, empresa_id: int, agente_slug: str, admin_user_id: str
    ) -> None:
        from whatsapp_langchain.shared import ia_alertas
        from whatsapp_langchain.shared.llm import SondaModelo

        _limpar_episodios_do_slug(db_url)

        async def sonda(slug: str) -> SondaModelo:
            if slug == _SLUG:
                return SondaModelo(
                    slug, False, 404, "sem provedor disponível", inexistente=True
                )
            return SondaModelo(slug, True, 200, "responde")

        caixa = _Caixa()
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(ia_alertas, "_notificar", caixa.notificar)
                c = await ia_alertas.avaliar_alertas(pool, sondar=sonda)
                assert c["abertos"] >= 1, c
                # o loader troca pelo padrão; o cache foi invalidado pela abertura
                ind = await ia_alertas.modelos_indisponiveis(pool)
        assert "modelo_indisponivel" in _ativos(db_url, _SLUG)
        assert ia_alertas.modelo_fora_de_circulacao(_SLUG, ind)
        linhas = [li for _, ls in caixa.msgs for li in ls if _SLUG in li]
        assert (
            linhas and "modelo padrão" in linhas[0] and f"({empresa_id})" in linhas[0]
        ), caixa.msgs

        # catálogo do seletor: o item vem marcado (o cache do catálogo é de 10 min,
        # mas a marca é aplicada na cópia a cada chamada)
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/modelos-llm/catalogo",
            headers=_headers(admin_user_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        item = next((i for i in r.json()["itens"] if i["slug"] == _SLUG), None)
        if item is not None:  # o slug pode não estar no catálogo do dev
            assert item["disponivel"] is False
            assert "sem provedor" in (item.get("indisponivel_motivo") or "")

        # sonda boa resolve o episódio
        async def sonda_ok(slug: str) -> SondaModelo:
            return SondaModelo(slug, True, 200, "responde")

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(ia_alertas, "_notificar", caixa.notificar)
                await ia_alertas.avaliar_alertas(pool, sondar=sonda_ok)
        assert "modelo_indisponivel" not in _ativos(db_url, _SLUG)
        _limpar_episodios_do_slug(db_url)

    async def test_03_agente_falhando_em_serie_avisa(
        self, db_url: str, empresa_id: int, agente_slug: str
    ) -> None:
        from whatsapp_langchain.shared import ia_alertas
        from whatsapp_langchain.shared.llm import SondaModelo

        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            for k in range(3):
                cur.execute(
                    """
                    INSERT INTO message_queue (message_id, phone_number, agent_id, thread_id,
                                               incoming_message, status, error, empresa_id)
                    VALUES (%s, %s, %s, %s, 'oi', 'failed',
                            'processing_failed:NotFoundError:404', %s)
                    """,
                    (
                        f"e2e-falha:{_RUN}:{k}",
                        f"+5567{_RUN[:8]}",
                        agente_slug,
                        f"t:{_RUN}",
                        empresa_id,
                    ),
                )

        async def sonda_ok(slug: str) -> SondaModelo:
            return SondaModelo(slug, True, 200, "responde")

        caixa = _Caixa()
        chave = f"agente:{empresa_id}:{agente_slug}"
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(ia_alertas, "_notificar", caixa.notificar)
                await ia_alertas.avaliar_alertas(pool, sondar=sonda_ok)
        assert _ativos(db_url, chave) == ["agente_falhando"]
        linhas = [li for _, ls in caixa.msgs for li in ls if agente_slug in li]
        assert linhas and "3 mensagens falharam" in linhas[0] and "404" in linhas[0], (
            caixa.msgs
        )

        # falhas saem da janela → resolve
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE message_queue SET updated_at = NOW() - interval '2 hours' "
                "WHERE agent_id = %s AND empresa_id = %s",
                (agente_slug, empresa_id),
            )
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(ia_alertas, "_notificar", caixa.notificar)
                await ia_alertas.avaliar_alertas(pool, sondar=sonda_ok)
        assert _ativos(db_url, chave) == []
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM message_queue WHERE agent_id = %s", (agente_slug,))
