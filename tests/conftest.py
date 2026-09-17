"""Fixtures compartilhadas para testes.

Este arquivo é carregado automaticamente pelo pytest.
Contém fixtures reutilizáveis em todos os testes.
"""

import contextlib
import os

import pytest
from dotenv import load_dotenv

# Carrega .env antes de qualquer teste
load_dotenv()

_PLACEHOLDER_OPENROUTER_KEYS = {
    "",
    "xxx",
    "sk-or-v1-xxx",
}


def _has_valid_live_openrouter_key() -> bool:
    """Retorna True apenas quando os testes live estão explicitamente habilitados."""
    enabled = os.getenv("OPENROUTER_LIVE_TESTS", "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return False

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return api_key not in _PLACEHOLDER_OPENROUTER_KEYS


@pytest.fixture
def live_openrouter_api_key():
    """Exige uma API key real e opt-in explícito para testes live."""
    if not _has_valid_live_openrouter_key():
        pytest.skip(
            "Teste live requer OPENROUTER_API_KEY valido e OPENROUTER_LIVE_TESTS=1"
        )

    return os.environ["OPENROUTER_API_KEY"]


@pytest.fixture
def api_sem_banco():
    """Tira o Postgres do caminho dos testes de ROTA (ADR-002, Etapa 1).

    Faz duas coisas, pelo mesmo motivo — o assunto desses testes é o
    handler (status, JSON, validação), não a infraestrutura:

    1. **Permissões.** Depois que as rotas de negócio ganharam portão,
       `require_permission` resolve o perfil no banco. Sem isto, um teste de
       serialização passa a responder 403 e a acusar um problema que não é o
       dele. Quem cobre a autorização de verdade é
       `tests/unit/test_permissao_escopo.py` (a regra) e
       `test_endpoint_permission_invariant.py` (quem tem portão).

    2. **Pool.** Os handlers chamam `await get_pool()` antes de usar a função
       de dados — que o teste já substitui por mock. O pool sobrava: abria
       conexão de verdade dentro do portal do `TestClient` (criado sem
       `lifespan`), e o desmonte do portal ficava esperando para sempre as
       tarefas do pool num event loop já fechado. Era o travamento local
       registrado em `gotcha_suite_trava_testclient_pool` — existe desde antes
       desta etapa e some com isto.

    Os módulos de rota fazem `from ... import get_pool`, então o nome vive em
    cada módulo: trocar só em `shared.db` não teria efeito.
    """
    import sys
    from unittest.mock import patch

    class _TudoLiberado(set):
        def __contains__(self, _item: object) -> bool:
            return True

    async def _perms(*_args, **_kwargs):
        return _TudoLiberado()

    async def _pool(*_args, **_kwargs):
        return object()  # sentinela: o teste mocka quem de fato usaria

    alvos = [
        nome
        for nome, mod in list(sys.modules.items())
        if nome.startswith("whatsapp_langchain.server.routes.")
        and getattr(mod, "get_pool", None) is not None
    ]

    with patch(
        "whatsapp_langchain.server.dependencies_rbac._resolve_user_perms",
        new=_perms,
    ):
        with contextlib.ExitStack() as pilha:
            for nome in alvos:
                pilha.enter_context(patch(f"{nome}.get_pool", new=_pool))
            yield


@pytest.fixture
def sample_messages():
    """Mensagens de exemplo para testes de contexto."""
    return [
        {"role": "user", "content": "Olá, meu nome é João."},
        {"role": "assistant", "content": "Olá João! Como posso ajudar?"},
        {"role": "user", "content": "Gosto de programação Python."},
        {"role": "assistant", "content": "Python é ótimo! O que desenvolve?"},
        {"role": "user", "content": "Estou aprendendo sobre LangChain."},
        {"role": "assistant", "content": "LangChain é excelente para agentes."},
        {"role": "user", "content": "Qual a diferença entre trim e summarize?"},
    ]
