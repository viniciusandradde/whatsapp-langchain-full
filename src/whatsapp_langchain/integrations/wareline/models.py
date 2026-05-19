"""Pydantic models pros payloads Wareline.

Aliasing pra campos abreviados do provider (cpfpac, nomepac, etc.).
Validation leve — o provider valida no schema deles, só precisamos
mapear pra nomes legíveis em Python e fornecer dataclasses tipadas
pras tools.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WarelineCredentials(BaseModel):
    """Credenciais armazenadas no DB (já descriptografadas)."""

    empresa_id: int
    base_url: str
    pacientes_base_url: str
    username: str
    password: str
    client_id: str
    client_secret: str
    ativo: bool = True


class TokenResponse(BaseModel):
    """Resposta do endpoint OAuth2 token."""

    access_token: str
    expires_in: int = 300
    refresh_expires_in: int = 3600
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str | None = None


class Paciente(BaseModel):
    """Paciente Wareline (resposta de /pacientes?cpfpac=...).

    Aliasing: cpfpac → cpf, codpac → codigo, nomepac → nome,
    nomemae → nome_mae, numlogr → numero, nombai → bairro,
    nomemun → municipio, ceppac → cep.
    """

    cpf: str = Field(alias="cpfpac")
    codigo: int = Field(alias="codpac")
    nome: str = Field(alias="nomepac")
    nome_mae: str | None = Field(default=None, alias="nomemae")
    logradouro: str | None = None
    numero: int | str | None = Field(default=None, alias="numlogr")
    bairro: str | None = Field(default=None, alias="nombai")
    municipio: str | None = Field(default=None, alias="nomemun")
    estado: str | None = None
    cep: str | None = Field(default=None, alias="ceppac")
    email: str | None = None
    celular: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class Prestador(BaseModel):
    codprest: str
    nomeprest: str


class CentroCusto(BaseModel):
    codcc: str
    nome: str


class AgendaItem(BaseModel):
    """Item de agenda do prestador."""

    num_agenda: int = Field(alias="numAgenda")
    data: str  # YYYY-MM-DD
    horario: str  # HH:MM:SS
    prestador: Prestador
    centro_custo: CentroCusto | None = Field(default=None, alias="centroCusto")

    model_config = ConfigDict(populate_by_name=True)


class PacienteAgendamentoInput(BaseModel):
    """Subobjeto `paciente` ao criar agendamento."""

    cod_paciente: int
    nome_paciente: str
    data_nascimento: str  # YYYY-MM-DD
    cpf_paciente: str
    numero_telefone: str | None = None


class ServicoAgendamentoInput(BaseModel):
    cod_servico_interna: str
    quantidade: str = "1"


class CriarAgendamentoInput(BaseModel):
    """Payload pra POST /services/terapias-api/agendas."""

    cod_agenda: int
    cod_plano: str = "BPA"
    cod_especialidade: str = "015"
    cod_tipo_agendamento: str = "C"
    paciente: PacienteAgendamentoInput
    data_marcacao: str  # YYYY-MM-DDTHH:MM:SS
    primeira_vez: str = "N"
    encaixe: str = "N"
    servicos: list[ServicoAgendamentoInput] = Field(
        default_factory=lambda: [
            ServicoAgendamentoInput(cod_servico_interna="00000048", quantidade="1")
        ]
    )


class AgendamentoResponse(BaseModel):
    """Resposta do criar_agendamento."""

    status: str
    mensagem: str
    dados: dict | None = None
