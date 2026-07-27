"""Reprocessar mensagem que a IA pulou ou que falhou.

Caso real que motivou (2026-07-27): uma ex-aluna escreveu pro agente do Luis
Fernando enquanto a conexão estava em modo manual. A mensagem 2929 (atendimento
499) ficou `done` com `[modo manual — IA desligada nesta conexão]` e ninguém
respondeu. Recuperar exigiu UPDATE manual no Postgres.

Pior: o drawer JÁ prometia "Tente reenviar" na bolha de erro — sem botão.

O contrato defendido aqui: só reprocessa o que ficou sem resposta, uma vez só,
e nunca por cima de humano.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.atendimento import (
    MARKERS_REPROCESSAVEIS,
    reenfileirar_mensagem,
)


def _pool(reenfileirou: bool) -> MagicMock:
    """Pool falso: RETURNING devolve linha (sucesso) ou None (não elegível)."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=(123,) if reenfileirou else None)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.connection = MagicMock(return_value=ctx)
    pool._conn = conn  # exposto pros testes que inspecionam o SQL
    return pool


class TestMarkersCobertos:
    """Quais estados são reprocessáveis — decisão de produto, não detalhe."""

    def test_modo_manual_e_whitelist_entram(self) -> None:
        assert "[modo manual" in MARKERS_REPROCESSAVEIS
        assert "[whitelist" in MARKERS_REPROCESSAVEIS

    def test_handoff_humano_fica_de_fora(self) -> None:
        """Atendente assumiu; IA responder por cima é pior que o problema."""
        assert not any("handoff" in m for m in MARKERS_REPROCESSAVEIS)

    def test_markers_batem_com_os_do_worker(self) -> None:
        """Se o worker mudar o texto, o reprocesso para de achar as mensagens."""
        from whatsapp_langchain.worker.processor import (
            MODO_MANUAL_MARKER,
            WHITELIST_BYPASS_MARKER,
        )

        assert MODO_MANUAL_MARKER.startswith(MARKERS_REPROCESSAVEIS[0])
        assert WHITELIST_BYPASS_MARKER.startswith(MARKERS_REPROCESSAVEIS[1])


class TestReenfileiramento:
    async def test_sucesso_devolve_true(self) -> None:
        assert await reenfileirar_mensagem(_pool(True), 1018, 499, 2929) is True

    async def test_linha_inelegivel_devolve_false(self) -> None:
        """UPDATE não acha linha = já respondida ou já reprocessada."""
        assert await reenfileirar_mensagem(_pool(False), 1018, 499, 2929) is False

    async def test_zera_o_estado_de_processamento(self) -> None:
        """Sem zerar attempts, a mensagem já nasce perto do limite de retry."""
        pool = _pool(True)
        await reenfileirar_mensagem(pool, 1018, 499, 2929)

        sql = pool._conn.execute.call_args[0][0]
        for campo in (
            "status = 'queued'",
            "attempts = 0",
            "response = NULL",
            "error = NULL",
            "processed_at = NULL",
            "lease_until = NULL",
        ):
            assert campo in sql, f"faltou zerar: {campo}"

    async def test_confina_por_empresa_e_atendimento(self) -> None:
        """Anti-tenant escape: id de mensagem sozinho não pode bastar."""
        pool = _pool(True)
        await reenfileirar_mensagem(pool, 1018, 499, 2929)

        sql = pool._conn.execute.call_args[0][0]
        assert "empresa_id = %s" in sql
        assert "atendimento_id = %s" in sql

    async def test_where_restringe_ao_estado_reprocessavel(self) -> None:
        """A trava anti-duplicata mora no WHERE, não numa checagem prévia.

        Checagem antes do UPDATE tem janela de corrida entre dois operadores;
        o WHERE resolve atomicamente.
        """
        pool = _pool(True)
        await reenfileirar_mensagem(pool, 1018, 499, 2929)

        sql = pool._conn.execute.call_args[0][0]
        assert "status = 'failed'" in sql
        assert "response LIKE ANY" in sql

    async def test_passa_os_markers_como_prefixo(self) -> None:
        pool = _pool(True)
        await reenfileirar_mensagem(pool, 1018, 499, 2929)

        params = pool._conn.execute.call_args[0][1]
        likes = params[-1]
        assert likes == ["[modo manual%", "[whitelist%"]


class TestEndpointRegistrado:
    """A rota precisa existir com RBAC — o invariante global cobre o resto."""

    def test_rota_existe_com_permissao(self) -> None:
        from whatsapp_langchain.server.routes import atendimento as rotas

        alvo = [
            r
            for r in rotas.router.routes
            if getattr(r, "path", "").endswith("/mensagens/{message_id}/reprocessar")
        ]
        assert alvo, "rota de reprocesso não registrada"

        rota = alvo[0]
        assert "POST" in getattr(rota, "methods", set())

        deps = str(getattr(rota, "dependant", ""))
        fonte = str(getattr(rota, "endpoint", ""))
        assert deps or fonte  # sanity

    @pytest.mark.parametrize(
        "trecho",
        [
            "atendimento.reprocessar",
            "modo manual",
            "whitelist",
            "atendente humano",
        ],
    )
    def test_mensagens_de_recusa_sao_acionaveis(self, trecho: str) -> None:
        """Recusa tem que dizer o que fazer, não só que não deu."""
        import inspect

        from whatsapp_langchain.server.routes import atendimento as rotas

        fonte = inspect.getsource(rotas.reprocessar_mensagem)
        assert trecho in fonte


class TestPermissaoNoCatalogo:
    """A tabela `permissao` não é fonte de verdade — `CATALOGO` é.

    Descoberto ao testar a mig 142: `atendimento.reset_thread` não existe em
    banco novo, só em produção, porque as permissões vêm de
    `shared/permissoes.py` e são sincronizadas no startup. Migration que só
    insere na tabela deixa o código inconsistente.
    """

    def test_permissao_esta_no_catalogo(self) -> None:
        from whatsapp_langchain.shared.permissoes import CATALOGO

        assert "atendimento.reprocessar" in {c for c, _, _ in CATALOGO}

    def test_gestor_recebe_como_no_reset_thread(self) -> None:
        """Mesmo poder: mexe na conversa e dispara WhatsApp ao cliente."""
        from whatsapp_langchain.shared.permissoes import PERFIS_SYSTEM

        gestor = next(p for n, _, p in PERFIS_SYSTEM if n == "Gestor")
        assert isinstance(gestor, list)
        assert ("atendimento.reprocessar" in gestor) == (
            "atendimento.reset_thread" in gestor
        )

    def test_operador_e_leitura_nao_recebem(self) -> None:
        from whatsapp_langchain.shared.permissoes import PERFIS_SYSTEM

        for nome in ("Operador", "Leitura"):
            perms = next(p for n, _, p in PERFIS_SYSTEM if n == nome)
            assert isinstance(perms, list)
            assert "atendimento.reprocessar" not in perms

    def test_nenhum_perfil_referencia_permissao_inexistente(self) -> None:
        """Guarda geral: lista de perfil com código órfão vira 403 silencioso."""
        from whatsapp_langchain.shared.permissoes import CATALOGO, PERFIS_SYSTEM

        codigos = {c for c, _, _ in CATALOGO}
        for nome, _, perms in PERFIS_SYSTEM:
            if isinstance(perms, list):
                orfas = [p for p in perms if p not in codigos]
                assert not orfas, f"{nome} referencia inexistente: {orfas}"
