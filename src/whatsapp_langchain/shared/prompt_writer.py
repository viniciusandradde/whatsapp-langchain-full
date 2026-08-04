"""Assistente de redação do prompt do agente.

Criar um agente termina num campo de texto vazio, e o que vai ali é o que
separa um agente que funciona de um que não funciona. Este módulo redige esse
texto a partir de uma descrição curta.

O valor não está em "gerar prompt" — está em gerar **conhecendo a configuração
real do agente**. Dois defeitos achados em produção explicam por quê:

1. No agente ativo da empresa 1, das 6 ferramentas citadas no prompt **só 1
   existia**, e ao mesmo tempo ele tinha 12 reais que o prompt nunca mencionava.
   Nada erra: o LangChain só oferece ao modelo as tools que existem, então o
   nome errado é ignorado — e o agente promete ao cliente o que não pode fazer.
2. Com `anuncia_transferencia = false` (mig 143), o sistema não manda nenhuma
   mensagem de transferência. Se o agente não se despedir na MESMA mensagem em
   que chama a tool, o cliente fica em silêncio: foram 16 mensagens em 5 dias.

Por isso `montar_contexto` lê o registry e o banco, e `montar_meta_prompt` é
função pura — dá pra testar as regras sem gastar um token.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


@dataclass
class ContextoRedacao:
    """O que o redator precisa saber pra não inventar."""

    empresa_nome: str
    agente_nome: str
    # (nome, primeira linha da docstring) — é o que o modelo lê pra saber
    # quando chamar cada uma.
    ferramentas: list[tuple[str, str]]
    variaveis: list[str]
    departamento_nome: str | None
    anuncia_transferencia: bool
    avisos: list[str] = field(default_factory=list)


def _primeira_linha(texto: str | None) -> str:
    for linha in (texto or "").strip().splitlines():
        if linha.strip():
            return linha.strip()
    return ""


async def montar_contexto(
    pool: AsyncConnectionPool, empresa_id: int, agente
) -> ContextoRedacao:
    """Reúne a configuração real do agente.

    As ferramentas vêm de `resolve_tools`, nunca de lista escrita à mão: no dia
    em que o registry mudar, uma lista fixa aqui passaria a ditar prompt citando
    tool que não existe mais — que é exatamente o defeito que este módulo existe
    pra evitar.
    """
    from whatsapp_langchain.agents.tools.registry import resolve_tools
    from whatsapp_langchain.shared.empresa import get_empresa_by_id
    from whatsapp_langchain.shared.variavel import list_variaveis

    avisos: list[str] = []

    empresa = await get_empresa_by_id(pool, empresa_id)
    empresa_nome = (
        getattr(empresa, "nome_exibicao", None) or getattr(empresa, "nome", None) or ""
    )

    knowledge_enabled = bool(getattr(agente, "base_conhecimento_ids", None))
    tools = resolve_tools(
        getattr(agente, "tools_enabled", None),
        calendar_enabled=False,
        knowledge_enabled=knowledge_enabled,
        aceita_imagem=bool(getattr(agente, "aceita_imagem", False)),
        aceita_audio=bool(getattr(agente, "aceita_audio", False)),
        aceita_documento=bool(getattr(agente, "aceita_documento", False)),
    )
    ferramentas = [
        (t.name, _primeira_linha(getattr(t, "description", ""))) for t in tools
    ]
    if not ferramentas:
        avisos.append(
            "Nenhuma ferramenta habilitada: o prompt sai sem política de uso de "
            "ferramentas. Marque as que o agente pode usar na aba Ferramentas."
        )

    variaveis = [
        v.nome for v in await list_variaveis(pool, empresa_id, apenas_ativos=True)
    ]

    departamento_nome: str | None = None
    dep_id = getattr(agente, "departamento_default_id", None)
    if dep_id:
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT nome FROM departamento WHERE id = %s AND empresa_id = %s",
                (dep_id, empresa_id),
            )
            row = await cur.fetchone()
        departamento_nome = row[0] if row else None

    # A tool existe mas o destino não: em runtime ela devolve erro instrutivo
    # ("admin precisa setar o departamento"). O prompt não pode prometer uma
    # transferência que vai falhar.
    if any(n == "transfer_to_human" for n, _ in ferramentas) and not departamento_nome:
        avisos.append(
            "O agente pode transferir, mas não tem departamento de destino "
            "configurado — a transferência falha em runtime. Defina o "
            "departamento padrão antes de usar este prompt."
        )

    return ContextoRedacao(
        empresa_nome=empresa_nome,
        agente_nome=getattr(agente, "nome", "") or "",
        ferramentas=ferramentas,
        variaveis=variaveis,
        departamento_nome=departamento_nome,
        anuncia_transferencia=bool(getattr(agente, "anuncia_transferencia", True)),
        avisos=avisos,
    )


def montar_meta_prompt(ctx: ContextoRedacao, descricao: str) -> str:
    """Instruções pro redator. Função pura — testável sem gastar token."""
    if ctx.ferramentas:
        bloco_tools = "\n".join(
            f"- `{nome}` — {desc}" if desc else f"- `{nome}`"
            for nome, desc in ctx.ferramentas
        )
    else:
        bloco_tools = "(nenhuma — não escreva a seção <tool_use_policy>)"

    if ctx.variaveis:
        bloco_vars = "\n".join(f"- `{{{{var.{nome}}}}}`" for nome in ctx.variaveis)
    else:
        bloco_vars = (
            "(nenhuma cadastrada — não use nenhuma chave `var.`; só "
            "`{{empresa.nome}}` e `{{data.hoje}}`)"
        )

    destino = ctx.departamento_nome or "(não configurado)"

    # A regra que impede o silêncio: com o anúncio desligado, a frase do agente
    # é a ÚNICA coisa que o cliente recebe ao ser transferido. Só entra quando
    # se aplica — senão o teste que verifica a ausência não detecta regressão.
    regra_despedida = ""
    if not ctx.anuncia_transferencia:
        regra_despedida = (
            "\n**Transferência sem anúncio do sistema.** Esta empresa NÃO envia "
            "mensagem automática ao transferir. Portanto o fluxo de "
            "transferência DEVE instruir o agente a escrever a frase de "
            "despedida na MESMA mensagem em que chama a ferramenta de "
            "transferência — depois dela ele não tem mais turno de fala, e o "
            "cliente ficaria sem resposta nenhuma.\n"
        )

    return f"""Você redige prompts de sistema para agentes de WhatsApp em português brasileiro.

Escreva o prompt COMPLETO do agente descrito abaixo. Devolva **apenas o texto do
prompt** — sem comentário seu, sem cercas de código, sem preâmbulo.

## O agente

Empresa: {ctx.empresa_nome}
Nome do agente: {ctx.agente_nome}
Departamento de destino em transferências: {destino}

Descrição dada por quem vai usá-lo:
{descricao.strip()}

## Formato obrigatório

Seções delimitadas por tags em snake_case, com Markdown dentro:

<role>              quem o agente é, com quem fala, e o que ele NÃO é
<company_context>   fatos da empresa; negrito no que importa
<fluxo_de_atendimento>  passos numerados, com o que fazer e o que não fazer
<tool_use_policy>   quando chamar cada ferramenta
<regras_de_seguranca>   o que nunca fazer, o que nunca prometer
<estilo_de_resposta>    tom, tamanho, formatação para WhatsApp

Nas regras críticas use blocos `❌ Errado:` / `✅ Certo:` com exemplo concreto —
instrução abstrata o modelo contorna, exemplo ele copia.

## Ferramentas disponíveis — use APENAS estas

{bloco_tools}

**Nunca invente nome de ferramenta.** Citar uma que não existe não gera erro: o
nome é silenciosamente ignorado, e o agente passa a prometer ao cliente algo que
nunca vai acontecer. Se a descrição pedir uma capacidade que não está na lista
acima, escreva explicitamente no prompt que o agente NÃO tem essa capacidade.
{regra_despedida}
## Variáveis disponíveis — use APENAS estas

{bloco_vars}

A sintaxe é `{{{{namespace.chave}}}}`. Chave que não existe fica LITERAL na
resposta enviada ao cliente, então nunca invente nome de variável.

## Qualidade

- Português brasileiro, tratando o cliente por você.
- Concreto: o que dizer, o que perguntar, quando parar.
- Sem repetir a mesma regra em duas seções.
- Nada de promessa que dependa de sistema externo não listado aqui.
"""


async def redigir_prompt(
    pool: AsyncConnectionPool, empresa_id: int, agente, descricao: str
) -> tuple[str, list[str]]:
    """Devolve (prompt, avisos). Não salva — quem salva é o `PUT /{slug}`,
    que versiona pela mig 158 e deixa a geração revertível por um clique."""
    from whatsapp_langchain.shared.config import settings
    from whatsapp_langchain.shared.llm import create_chat_model

    ctx = await montar_contexto(pool, empresa_id, agente)
    meta = montar_meta_prompt(ctx, descricao)

    model = create_chat_model(model=settings.prompt_writer_model, temperature=0.4)
    resposta = await model.ainvoke(meta)
    texto = resposta.content if isinstance(resposta.content, str) else ""
    texto = texto.strip()

    if not texto:
        raise RuntimeError("O redator não devolveu texto. Tente novamente.")

    logger.info(
        "prompt_redigido",
        empresa_id=empresa_id,
        agente=getattr(agente, "nome", ""),
        chars=len(texto),
        ferramentas=len(ctx.ferramentas),
        avisos=len(ctx.avisos),
    )
    return texto, ctx.avisos
