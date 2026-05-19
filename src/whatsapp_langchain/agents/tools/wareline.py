"""Tools do agente IA pra integração Wareline ConecteHub.

Injetadas no agente `catalog/agendamentos/` quando a empresa tem
`wareline_credentials` ativo (factory consulta antes de incluir).
Cada tool recebe `empresa_id` via `runtime.config.configurable.empresa_id`.

Tools retornam strings curtas pro agente formatar a resposta — pattern
do projeto. Erros viram `[ERRO Wareline: ...]` pra o LLM decidir se
transfere humano.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.integrations.wareline import (
    WarelineAuthError,
    WarelineClient,
    WarelineError,
    WarelineNotFoundError,
)
from whatsapp_langchain.integrations.wareline.models import (
    CriarAgendamentoInput,
    PacienteAgendamentoInput,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()


def _extract_empresa_id(runtime: Any) -> int | None:
    """Lê empresa_id do LangGraph runtime (mesmo pattern do calendar.py)."""
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            cfg = config.get("configurable", {})
            if isinstance(cfg, dict) and "empresa_id" in cfg:
                return int(cfg["empresa_id"])
    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict) and "empresa_id" in configurable:
            return int(configurable["empresa_id"])
    return None


async def _get_client(runtime: Any) -> WarelineClient | None:
    """Helper: resolve empresa_id + retorna client. None se sem empresa."""
    empresa_id = _extract_empresa_id(runtime)
    if empresa_id is None:
        return None
    pool = await get_pool()
    return WarelineClient(pool, empresa_id=empresa_id)


@tool
async def wareline_buscar_paciente(
    cpf: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Busca paciente no Wareline pelo CPF (11 dígitos, sem máscara).

    Use SEMPRE antes de criar agendamento — preciso confirmar codpac
    e dados do paciente. Retorna JSON com nome, telefone, endereço.

    Se paciente não cadastrado: retorna "[NÃO ENCONTRADO]" — orienta o
    cliente a se cadastrar pessoalmente na recepção ou transfere humano.
    """
    client = await _get_client(runtime)
    if client is None:
        return "[ERRO Wareline: empresa_id ausente do contexto]"
    cpf_limpo = "".join(c for c in cpf if c.isdigit())
    if len(cpf_limpo) != 11:
        return f"[ERRO: CPF inválido — '{cpf}' precisa ter 11 dígitos]"
    try:
        pacientes = await client.buscar_paciente(cpf_limpo)
        # Provider devolve lista (pode ter homônimos por CPF duplicado raro)
        return json.dumps(
            [p.model_dump(by_alias=False) for p in pacientes],
            ensure_ascii=False,
        )
    except WarelineNotFoundError:
        return f"[NÃO ENCONTRADO: nenhum paciente com CPF {cpf_limpo}]"
    except WarelineAuthError as exc:
        logger.warning("wareline_auth_failed_buscar", error=str(exc))
        return "[ERRO Wareline: credenciais inválidas, contate o admin]"
    except WarelineError as exc:
        logger.warning("wareline_buscar_paciente_failed", error=str(exc))
        return f"[ERRO Wareline: {exc!s:.200}]"


@tool
async def wareline_consultar_agenda(
    prestador: str,
    data_inicio: str,
    data_final: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Lista horários da agenda de um prestador no Wareline.

    - prestador: código do prestador (ex: "003297")
    - data_inicio/data_final: formato YYYY-MM-DD (ex: "2025-08-01")

    Retorna até 20 itens: data, horário, numAgenda (use no criar_agendamento),
    nome do prestador, centro de custo. JSON estruturado.
    """
    client = await _get_client(runtime)
    if client is None:
        return "[ERRO Wareline: empresa_id ausente do contexto]"
    try:
        agendas = await client.listar_agenda_prestador(
            prestador, data_inicio, data_final
        )
        if not agendas:
            return (
                f"[AGENDA VAZIA: prestador {prestador} não tem horários "
                f"entre {data_inicio} e {data_final}]"
            )
        return json.dumps(
            [a.model_dump(by_alias=False) for a in agendas],
            ensure_ascii=False,
        )
    except WarelineAuthError as exc:
        logger.warning("wareline_auth_failed_agenda", error=str(exc))
        return "[ERRO Wareline: credenciais inválidas, contate o admin]"
    except WarelineError as exc:
        logger.warning(
            "wareline_consultar_agenda_failed",
            error=str(exc),
            prestador=prestador,
        )
        return f"[ERRO Wareline: {exc!s:.200}]"


@tool
async def wareline_criar_agendamento(
    cod_agenda: int,
    cod_paciente: int,
    nome_paciente: str,
    data_nascimento: str,
    cpf_paciente: str,
    data_marcacao: str,
    numero_telefone: str = "",
    cod_especialidade: str = "015",
    cod_plano: str = "BPA",
    cod_tipo_agendamento: str = "C",
    cod_servico: str = "00000048",
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Cria agendamento no Wareline. Use SOMENTE após confirmar com o paciente.

    Params obrigatórios:
    - cod_agenda: número de agenda do horário (obtido via wareline_consultar_agenda)
    - cod_paciente: codpac do paciente (obtido via wareline_buscar_paciente)
    - nome_paciente, cpf_paciente, data_nascimento (YYYY-MM-DD)
    - data_marcacao: ISO YYYY-MM-DDTHH:MM:SS

    Defaults sensatos pra Mackenzie:
    - cod_especialidade="015", cod_plano="BPA", cod_tipo="C" (consulta)
    - cod_servico="00000048" (serviço padrão)

    Retorna cod_agendamento gerado (use pra confirmar com cliente).
    """
    client = await _get_client(runtime)
    if client is None:
        return "[ERRO Wareline: empresa_id ausente do contexto]"
    try:
        payload = CriarAgendamentoInput(
            cod_agenda=cod_agenda,
            cod_plano=cod_plano,
            cod_especialidade=cod_especialidade,
            cod_tipo_agendamento=cod_tipo_agendamento,
            paciente=PacienteAgendamentoInput(
                cod_paciente=cod_paciente,
                nome_paciente=nome_paciente,
                data_nascimento=data_nascimento,
                cpf_paciente=cpf_paciente,
                numero_telefone=numero_telefone or None,
            ),
            data_marcacao=data_marcacao,
        )
        # Ajuste cod_servico se diferente do default
        if cod_servico and cod_servico != "00000048":
            payload.servicos[0].cod_servico_interna = cod_servico

        resp = await client.criar_agendamento(payload)
        if resp.status != "SUCESSO":
            return f"[FALHA: {resp.mensagem}]"
        cod_ag = (
            resp.dados.get("cod_agendamento") if resp.dados else None
        )
        return json.dumps(
            {
                "ok": True,
                "cod_agendamento": cod_ag,
                "mensagem": resp.mensagem,
                "data_marcacao": data_marcacao,
            },
            ensure_ascii=False,
        )
    except WarelineAuthError as exc:
        logger.warning("wareline_auth_failed_criar", error=str(exc))
        return "[ERRO Wareline: credenciais inválidas, contate o admin]"
    except WarelineError as exc:
        logger.warning("wareline_criar_agendamento_failed", error=str(exc))
        return f"[ERRO Wareline: {exc!s:.200}]"
