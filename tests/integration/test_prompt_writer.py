"""Assistente de redação: o prompt gerado só pode citar o que existe.

Criar um agente termina num campo de texto vazio, e o que vai ali é o que
separa um agente que funciona de um que não funciona. O assistente redige esse
texto a partir de uma descrição de duas linhas — mas o valor dele não está em
"gerar prompt", e sim em gerar conhecendo a configuração REAL do agente.

Dois defeitos de produção justificam cada regra testada aqui:

1. **Ferramenta fantasma.** No agente ativo da empresa 1, das 6 tools citadas
   no prompt só 1 existia; ao mesmo tempo ele tinha 12 tools reais que o prompt
   nunca mencionava. Não gera erro — o modelo ignora o nome errado, e o agente
   promete ao cliente o que não pode cumprir.
2. **Despedida na transferência.** Com `anuncia_transferencia = false`
   (mig 143), o sistema não anuncia nada. Se o agente não escrever a frase de
   despedida na MESMA mensagem da tool call, o cliente fica em silêncio — foram
   16 mensagens em 5 dias.

Nenhum teste aqui chama o LLM: custa OpenRouter, mesma regra do eval. O que se
testa é o contexto que alimenta o redator e as regras do meta-prompt.

Só smoke:
    uv run pytest tests/integration/test_prompt_writer.py::TestSmoke -v

E2E (precisa do banco):
    uv run pytest tests/integration/test_prompt_writer.py -v
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from whatsapp_langchain.shared import prompt_writer as pw

from .helpers import get_db_url


def _ctx(**kw) -> pw.ContextoRedacao:
    base = dict(
        empresa_nome="Clínica Exemplo",
        agente_nome="Atendimento",
        ferramentas=[
            ("transfer_to_human", "Transfere o atendimento ao departamento."),
            ("search_knowledge_base", "Busca na base de conhecimento."),
        ],
        variaveis=["LINK_PORTAL", "HORARIO_ATENDIMENTO"],
        departamento_nome="Recepção",
        anuncia_transferencia=True,
        avisos=[],
    )
    base.update(kw)
    return pw.ContextoRedacao(**base)


# ============================================================================
# Smoke (sem DB — roda em CI)
# ============================================================================


class TestSmoke:
    def test_rota_registrada(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {
            (m, r.path)
            for r in app.routes
            for m in getattr(r, "methods", set()) or set()
        }
        assert ("POST", "/api/v1/agentes/{slug}/prompt/redigir") in rotas

    def test_modelo_do_redator_esta_no_catalogo_curado(self) -> None:
        """Redigir 5 mil caracteres estruturados não é tarefa de modelo barato,
        e o id precisa existir de verdade — `grok-4.1-fast` já foi aposentado
        da OpenRouter estando cadastrado aqui."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.llm import CURATED_MODELS

        ids = {m["id"] if isinstance(m, dict) else m for m in CURATED_MODELS}
        assert settings.prompt_writer_model in ids

    def test_meta_prompt_lista_as_ferramentas_reais(self) -> None:
        meta = pw.montar_meta_prompt(_ctx(), "assistente de matrículas")
        assert "transfer_to_human" in meta
        assert "search_knowledge_base" in meta

    def test_meta_prompt_proibe_inventar_ferramenta(self) -> None:
        """A regra que impede o defeito nº 1.

        Checa a sentença que carrega a proibição, não uma paráfrase: se alguém
        suavizar o texto, o teste tem que cair.
        """
        meta = pw.montar_meta_prompt(_ctx(), "qualquer coisa").lower()
        assert "nunca invente nome de ferramenta" in meta
        assert "use apenas estas" in meta

    def test_meta_prompt_manda_declarar_o_que_o_agente_nao_faz(self) -> None:
        """Sem isto o modelo inventa a capacidade em prosa quando a ferramenta
        não existe — que é como o prompt passa a prometer o impossível."""
        meta = pw.montar_meta_prompt(_ctx(), "x").lower()
        assert "não tem essa capacidade" in meta

    def test_meta_prompt_ensina_a_sintaxe_certa_de_variavel(self) -> None:
        """Chave que não resolve fica LITERAL na resposta ao cliente. O erro
        clássico é ensinar `{{$NOME}}`, que não casa com o regex de
        `shared/variavel.py::render_template`."""
        meta = pw.montar_meta_prompt(_ctx(), "x")
        assert "{{var.LINK_PORTAL}}" in meta
        assert "{{$" not in meta

    def test_meta_prompt_nao_oferece_variavel_inexistente(self) -> None:
        meta = pw.montar_meta_prompt(_ctx(variaveis=[]), "x")
        assert "{{var." not in meta

    def test_anuncio_desligado_exige_a_despedida(self) -> None:
        """A entrega do defeito nº 2: sem anúncio do sistema, a frase do
        agente é a única coisa que o cliente recebe — e ela tem que sair na
        mesma mensagem da tool call, porque depois dela não há turno de fala."""
        meta = pw.montar_meta_prompt(_ctx(anuncia_transferencia=False), "x")
        assert "mesma mensagem" in meta.lower()

    def test_anuncio_ligado_nao_exige(self) -> None:
        """Com o anúncio ligado o sistema fala por si; forçar a regra aqui
        tornaria o teste acima incapaz de detectar regressão."""
        meta = pw.montar_meta_prompt(_ctx(anuncia_transferencia=True), "x")
        assert "mesma mensagem" not in meta.lower()

    def test_meta_prompt_carrega_a_descricao(self) -> None:
        meta = pw.montar_meta_prompt(_ctx(), "assistente de matrículas da UNIGRAN")
        assert "assistente de matrículas da UNIGRAN" in meta

    def test_meta_prompt_pede_o_formato_da_casa(self) -> None:
        meta = pw.montar_meta_prompt(_ctx(), "x")
        for tag in ("<role>", "<tool_use_policy>"):
            assert tag in meta


# ============================================================================
# E2E (banco real)
# ============================================================================

_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db_url() -> str:
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Rode: make db")
    return url


@pytest.fixture
def empresa_id(db_url: str):
    slug = f"test-pw-{_RUN}-{uuid.uuid4().hex[:6]}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active') RETURNING id
                """,
                (slug, slug),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


class _AgenteFake:
    """Só os campos que `montar_contexto` lê — evita montar `agente_ia` real."""

    def __init__(self, **kw) -> None:
        self.nome = kw.get("nome", "Atendimento")
        self.tools_enabled = kw.get("tools_enabled", ["transferir_dep", "tag_cliente"])
        self.aceita_imagem = kw.get("aceita_imagem", True)
        self.aceita_audio = kw.get("aceita_audio", True)
        self.aceita_documento = kw.get("aceita_documento", True)
        self.anuncia_transferencia = kw.get("anuncia_transferencia", True)
        self.base_conhecimento_ids = kw.get("base_conhecimento_ids", [])
        self.departamento_default_id = kw.get("departamento_default_id", None)


@pytest.mark.docker_demo
class TestE2E:
    async def test_ferramentas_vem_do_registry(
        self, db_url: str, empresa_id: int
    ) -> None:
        """Não pode ser lista fixa no módulo: o dia em que o registry mudar,
        o prompt gerado passaria a citar tool que não existe mais."""
        from psycopg_pool import AsyncConnectionPool

        from whatsapp_langchain.agents.tools.registry import resolve_tools

        agente = _AgenteFake()
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            ctx = await pw.montar_contexto(pool, empresa_id, agente)

        esperado = {
            t.name
            for t in resolve_tools(
                agente.tools_enabled,
                calendar_enabled=False,
                knowledge_enabled=False,
                aceita_imagem=True,
                aceita_audio=True,
                aceita_documento=True,
            )
        }
        assert {n for n, _ in ctx.ferramentas} == esperado

    async def test_agente_que_nao_aceita_imagem_nao_ganha_tool_de_imagem(
        self, db_url: str, empresa_id: int
    ) -> None:
        from psycopg_pool import AsyncConnectionPool

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            com = await pw.montar_contexto(pool, empresa_id, _AgenteFake())
            sem = await pw.montar_contexto(
                pool, empresa_id, _AgenteFake(aceita_imagem=False)
            )

        nomes_com = {n for n, _ in com.ferramentas}
        nomes_sem = {n for n, _ in sem.ferramentas}
        assert nomes_sem <= nomes_com

    async def test_variaveis_sao_as_da_empresa(
        self, db_url: str, empresa_id: int
    ) -> None:
        """Variável de outra empresa no prompt vira chave que não resolve —
        e chave que não resolve vai LITERAL pro cliente."""
        from psycopg_pool import AsyncConnectionPool

        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active') RETURNING id
                    """,
                    (f"outra-{_RUN}", f"outra-{_RUN}"),
                )
                row = cur.fetchone()
                assert row is not None
                outra = int(row[0])
                cur.execute(
                    "INSERT INTO variavel_ambiente (empresa_id, nome, valor) "
                    "VALUES (%s, 'MINHA_VAR', 'x'), (%s, 'VAR_ALHEIA', 'y')",
                    (empresa_id, outra),
                )
        try:
            async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
                ctx = await pw.montar_contexto(pool, empresa_id, _AgenteFake())
            assert "MINHA_VAR" in ctx.variaveis
            assert "VAR_ALHEIA" not in ctx.variaveis
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM empresa WHERE id = %s", (outra,))

    async def test_sem_ferramenta_habilitada_avisa(
        self, db_url: str, empresa_id: int
    ) -> None:
        """Falha visível: o prompt sai sem `<tool_use_policy>` útil e quem
        pediu precisa saber por quê, em vez de descobrir na conversa."""
        from psycopg_pool import AsyncConnectionPool

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            ctx = await pw.montar_contexto(
                pool, empresa_id, _AgenteFake(tools_enabled=["__inexistente__"])
            )
        assert ctx.avisos, "nenhum aviso quando o agente ficou sem ferramenta"

    async def test_transferencia_sem_departamento_avisa(
        self, db_url: str, empresa_id: int
    ) -> None:
        """`transfer_to_human` sem `departamento_default_id` devolve erro
        instrutivo em runtime — o prompt não pode prometer a transferência."""
        from psycopg_pool import AsyncConnectionPool

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            ctx = await pw.montar_contexto(
                pool,
                empresa_id,
                _AgenteFake(
                    tools_enabled=["transferir_dep"], departamento_default_id=None
                ),
            )
        assert any("departamento" in a.lower() for a in ctx.avisos)
