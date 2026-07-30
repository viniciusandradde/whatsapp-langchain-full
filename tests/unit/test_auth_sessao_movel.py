"""Auth de sessão pro cliente móvel (Fase 0 do app Android).

A API confia no header `X-User-Id` porque assume estar atrás do
`INTERNAL_SERVICE_TOKEN` numa rede interna. Um APK não pode carregar esse
token: extraído, ele permitiria mandar `X-User-Id`/`X-Empresa-Id` arbitrários e
ler/escrever em TODOS os tenants.

A saída foi aceitar também um token de sessão do Better Auth, derivando a
identidade de `auth.session` em vez do header. Estes testes travam as duas
propriedades que sustentam a segurança disso:

1. Service token continua funcionando exatamente como antes (o Next.js não pode
   quebrar).
2. Quando a identidade vem da sessão, ela tem **precedência absoluta** sobre o
   header — um `X-User-Id` divergente é ignorado, não obedecido.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from whatsapp_langchain.server.dependencies import (
    _resolve_session_user,
    get_user_id_from_request,
    verify_service_token,
)

SERVICE_TOKEN = "service-token-de-teste-com-32-chars!!"
SESSION_TOKEN = "sessao-do-better-auth-32-caracteres"
USER_DA_SESSAO = "user-vindo-do-banco"


def _request(path="/api/atendimentos", headers=None):
    """Request mínimo: só o que as dependencies tocam (state, headers, url)."""
    return SimpleNamespace(
        state=SimpleNamespace(),
        headers=headers or {},
        url=SimpleNamespace(path=path),
    )


def _bearer(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _pool_com(row):
    """Pool mockado cujo fetchone devolve `row`."""
    from contextlib import asynccontextmanager

    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=row)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = AsyncMock()

    @asynccontextmanager
    async def _conn():
        yield conn

    pool.connection = _conn
    return pool


class TestResolveSessionUser:
    """`_resolve_session_user` — a única porta de identidade do app."""

    async def test_token_curto_nao_consulta_banco(self):
        """Guard de tamanho evita query inútil (nada em auth.session é <16)."""
        with patch("whatsapp_langchain.server.dependencies.get_pool") as get_pool:
            assert await _resolve_session_user("abc") is None
            get_pool.assert_not_called()

    async def test_sessao_valida_devolve_user_id(self):
        with patch(
            "whatsapp_langchain.server.dependencies.get_pool",
            AsyncMock(return_value=_pool_com((USER_DA_SESSAO,))),
        ):
            assert await _resolve_session_user(SESSION_TOKEN) == USER_DA_SESSAO

    async def test_sessao_e_renovada_no_uso(self):
        """Sessão DESLIZANTE: usar o app estende a validade.

        O Better Auth renova quando o navegador chama `getSession`. O app nunca
        chama — ele fala com esta API, que só LIA a sessão. Resultado: o token
        expirava em 7 dias corridos por mais que o operador usasse o app todo
        dia, e ele voltava pra tela de login sem motivo aparente (foi o que
        aconteceu em uso real).

        O UPDATE precisa estar no MESMO statement do SELECT: uma segunda ida ao
        banco em toda request autenticada dobraria o custo do caminho comum.
        """
        pool = _pool_com((USER_DA_SESSAO,))
        with patch(
            "whatsapp_langchain.server.dependencies.get_pool",
            AsyncMock(return_value=pool),
        ):
            assert await _resolve_session_user(SESSION_TOKEN) == USER_DA_SESSAO

        # Um único execute, com SELECT e UPDATE juntos.
        async with pool.connection() as conn:
            sql = conn.execute.await_args.args[0]
        assert "UPDATE auth.session" in sql
        assert 'SET "expiresAt" = NOW()' in sql
        # E o UPDATE é condicional, senão seria uma escrita por request.
        assert '"expiresAt" < NOW()' in sql

    async def test_sessao_inexistente_ou_expirada_devolve_none(self):
        """A query já filtra `expiresAt > NOW()` e `status='active'`, então
        sessão expirada, revogada ou de usuário desativado cai aqui."""
        with patch(
            "whatsapp_langchain.server.dependencies.get_pool",
            AsyncMock(return_value=_pool_com(None)),
        ):
            assert await _resolve_session_user(SESSION_TOKEN) is None

    async def test_falha_de_banco_nao_autentica(self):
        """Fail-CLOSED: erro de lookup nunca vira sessão válida.

        Oposto do fail-safe de `detectar_fluxo_guiado` — ali degradar é barato,
        aqui degradar seria deixar entrar sem credencial.
        """
        with patch(
            "whatsapp_langchain.server.dependencies.get_pool",
            AsyncMock(side_effect=RuntimeError("banco caiu")),
        ):
            assert await _resolve_session_user(SESSION_TOKEN) is None


class TestVerifyServiceToken:
    """Os dois caminhos de autenticação da rota admin."""

    async def test_service_token_passa_sem_tocar_no_banco(self):
        """Regressão do Next.js: o caminho antigo não pode nem consultar
        auth.session — seria uma query extra em toda request do painel."""
        req = _request()
        with (
            patch("whatsapp_langchain.server.dependencies.settings") as st,
            patch(
                "whatsapp_langchain.server.dependencies._resolve_session_user"
            ) as resolve,
        ):
            st.internal_service_token = SERVICE_TOKEN
            await verify_service_token(req, _bearer(SERVICE_TOKEN))
            resolve.assert_not_called()
        assert not hasattr(req.state, "session_user_id")

    async def test_token_de_sessao_grava_identidade_no_state(self):
        req = _request()
        with (
            patch("whatsapp_langchain.server.dependencies.settings") as st,
            patch(
                "whatsapp_langchain.server.dependencies._resolve_session_user",
                AsyncMock(return_value=USER_DA_SESSAO),
            ),
        ):
            st.internal_service_token = SERVICE_TOKEN
            await verify_service_token(req, _bearer(SESSION_TOKEN))
        assert req.state.session_user_id == USER_DA_SESSAO

    async def test_token_desconhecido_401(self):
        with (
            patch("whatsapp_langchain.server.dependencies.settings") as st,
            patch(
                "whatsapp_langchain.server.dependencies._resolve_session_user",
                AsyncMock(return_value=None),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            st.internal_service_token = SERVICE_TOKEN
            await verify_service_token(
                _request(), _bearer("lixo-qualquer-32-chars-aqui")
            )
        assert exc.value.status_code == 401

    async def test_header_ausente_401(self):
        with pytest.raises(HTTPException) as exc:
            await verify_service_token(_request(), None)
        assert exc.value.status_code == 401

    async def test_scheme_nao_bearer_401(self):
        cred = HTTPAuthorizationCredentials(scheme="Basic", credentials="x")
        with pytest.raises(HTTPException) as exc:
            await verify_service_token(_request(), cred)
        assert exc.value.status_code == 401


class TestPrecedenciaDaSessao:
    """A propriedade de segurança que sustenta o app inteiro."""

    def test_sessao_vence_header_divergente(self):
        """Com sessão resolvida, `X-User-Id` é IGNORADO.

        Se o header vencesse, o app (que legitimamente tem um token de sessão)
        poderia se passar por qualquer usuário — inclusive superadmin, ganhando
        acesso cross-tenant via `X-Empresa-Id`. É exatamente o furo que o
        service token no APK abriria.
        """
        req = _request(headers={"X-User-Id": "usuario-que-eu-quero-virar"})
        req.state.session_user_id = USER_DA_SESSAO
        assert get_user_id_from_request(req) == USER_DA_SESSAO

    def test_sem_sessao_usa_header(self):
        """Caminho do Next.js, intacto."""
        req = _request(headers={"X-User-Id": "user-do-painel"})
        assert get_user_id_from_request(req) == "user-do-painel"

    def test_sem_sessao_e_sem_header_401(self):
        with pytest.raises(HTTPException) as exc:
            get_user_id_from_request(_request())
        assert exc.value.status_code == 401


class TestTokenAssinado:
    """O Better Auth devolve o token do cookie ASSINADO.

    O plugin `bearer` entrega o mesmo valor do cookie no header
    `set-auth-token`, no formato `<token>.<assinatura>`. Mas
    `auth.session.token` guarda só o token — 32 caracteres, sem ponto,
    conferido em produção.

    Sem tratar isso, o app loga com sucesso e toma 401 na chamada seguinte, e o
    sintoma na tela é a seleção de empresa aparecer e voltar pro login em
    milissegundos (o interceptor apaga a sessão em 401). Aconteceu 15 vezes no
    primeiro teste em aparelho real.
    """

    async def test_token_assinado_valida_pela_parte_antes_do_ponto(self):
        capturado = {}

        def _pool(row):
            from contextlib import asynccontextmanager

            cur = AsyncMock()
            cur.fetchone = AsyncMock(return_value=row)
            conn = AsyncMock()

            async def _exec(sql, args):
                capturado["candidatos"] = args[0]
                return cur

            conn.execute = AsyncMock(side_effect=_exec)
            pool = AsyncMock()

            @asynccontextmanager
            async def _c():
                yield conn

            pool.connection = _c
            return pool

        assinado = f"{SESSION_TOKEN}.assinatura-hmac-em-base64"
        with patch(
            "whatsapp_langchain.server.dependencies.get_pool",
            AsyncMock(return_value=_pool((USER_DA_SESSAO,))),
        ):
            assert await _resolve_session_user(assinado) == USER_DA_SESSAO

        # As duas formas vão pro banco: a crua (caso o cookie não seja
        # assinado) e a parte antes do ponto.
        assert capturado["candidatos"] == [assinado, SESSION_TOKEN]

    async def test_token_sem_ponto_consulta_apenas_uma_forma(self):
        capturado = {}

        def _pool():
            from contextlib import asynccontextmanager

            cur = AsyncMock()
            cur.fetchone = AsyncMock(return_value=(USER_DA_SESSAO,))
            conn = AsyncMock()

            async def _exec(sql, args):
                capturado["candidatos"] = args[0]
                return cur

            conn.execute = AsyncMock(side_effect=_exec)
            pool = AsyncMock()

            @asynccontextmanager
            async def _c():
                yield conn

            pool.connection = _c
            return pool

        with patch(
            "whatsapp_langchain.server.dependencies.get_pool",
            AsyncMock(return_value=_pool()),
        ):
            await _resolve_session_user(SESSION_TOKEN)

        assert capturado["candidatos"] == [SESSION_TOKEN]
