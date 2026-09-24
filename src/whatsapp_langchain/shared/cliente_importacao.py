"""Importação e exportação de clientes em CSV (cadastro manual, mig 201).

Funções puras — nada aqui toca o banco. A rota lê o arquivo, chama
`ler_csv_clientes` e grava cada linha válida com `criar_cliente`.

Formato aceito (o que planilhas brasileiras costumam exportar):
- separador `;` ou `,` (detectado pela primeira linha);
- UTF-8 com ou sem BOM; se não decodificar, Latin-1 (Excel antigo);
- cabeçalho obrigatório, com nomes flexíveis (`telefone`, `celular`,
  `whatsapp`…) — só a coluna de telefone é obrigatória.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from whatsapp_langchain.shared.telefone import normalizar_br

MAX_LINHAS_IMPORTACAO = 5_000
MAX_BYTES_IMPORTACAO = 2 * 1024 * 1024

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NAO_DIGITO = re.compile(r"\D")

# nome normalizado do cabeçalho → campo
_ALIASES: dict[str, str] = {
    "nome": "nome",
    "name": "nome",
    "nome completo": "nome",
    "contato": "nome",
    "telefone": "telefone",
    "numero de telefone": "telefone",
    "numero": "telefone",
    "celular": "telefone",
    "whatsapp": "telefone",
    "fone": "telefone",
    "phone": "telefone",
    "email": "email",
    "e-mail": "email",
    "e mail": "email",
    "origem": "origem",
    "regiao / origem": "origem",
    "regiao/origem": "origem",
    "regiao": "origem",
    "source": "origem",
}


@dataclass
class LinhaCliente:
    linha: int  # número da linha no arquivo (cabeçalho = 1)
    telefone: str
    nome: str | None = None
    email: str | None = None
    origem: str | None = None


@dataclass
class ResultadoLeitura:
    validas: list[LinhaCliente] = field(default_factory=list)
    invalidas: list[dict] = field(default_factory=list)  # {linha, motivo}
    erro: str | None = None  # problema no arquivo inteiro


def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in base if not unicodedata.combining(c))


def _campo_do_cabecalho(nome: str) -> str | None:
    chave = _sem_acento(nome).strip().lower()
    return _ALIASES.get(chave)


def normalizar_telefone_cadastro(raw: str | None) -> str | None:
    """Telefone de cliente cadastrado à mão, em E.164 com `+`.

    Brasil segue a regra de `normalizar_br` (país + DDD obrigatórios). Número
    de outro país só é aceito com `+` explícito e 8–15 dígitos.
    """
    br = normalizar_br(raw)
    if br is not None:
        return br
    s = (raw or "").strip()
    digitos = _NAO_DIGITO.sub("", s)
    if s.startswith("+") and not digitos.startswith("55") and 8 <= len(digitos) <= 15:
        return f"+{digitos}"
    return None


def email_valido(email: str) -> bool:
    return bool(_EMAIL.match(email))


def _decodificar(conteudo: bytes) -> str:
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


def ler_csv_clientes(conteudo: bytes) -> ResultadoLeitura:
    """Lê o CSV e separa linhas válidas das recusadas (com o motivo)."""
    res = ResultadoLeitura()
    if not conteudo.strip():
        res.erro = "O arquivo está vazio."
        return res
    if len(conteudo) > MAX_BYTES_IMPORTACAO:
        res.erro = "O arquivo passa de 2 MB. Divida em partes menores."
        return res

    texto = _decodificar(conteudo)
    primeira = texto.splitlines()[0] if texto.splitlines() else ""
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.reader(io.StringIO(texto), delimiter=separador)

    try:
        cabecalho = next(leitor)
    except StopIteration:
        res.erro = "O arquivo está vazio."
        return res
    campos = [_campo_do_cabecalho(c) for c in cabecalho]
    if "telefone" not in campos:
        res.erro = (
            "Não achei a coluna de telefone. A primeira linha precisa ter os "
            "nomes das colunas, por exemplo: nome;telefone;email;origem"
        )
        return res

    vistos: set[str] = set()
    for numero_linha, valores in enumerate(leitor, start=2):
        if not any(v.strip() for v in valores):
            continue
        if len(res.validas) + len(res.invalidas) >= MAX_LINHAS_IMPORTACAO:
            res.erro = f"O arquivo passa de {MAX_LINHAS_IMPORTACAO} linhas. Divida em partes menores."
            return res
        dados: dict[str, str] = {}
        for campo, valor in zip(campos, valores, strict=False):
            if campo and valor.strip() and campo not in dados:
                dados[campo] = valor.strip()

        telefone = normalizar_telefone_cadastro(dados.get("telefone"))
        if telefone is None:
            motivo = (
                "Telefone vazio"
                if not dados.get("telefone")
                else "Telefone inválido: use país e DDD, por exemplo 5567999990000"
            )
            res.invalidas.append({"linha": numero_linha, "motivo": motivo})
            continue
        if telefone in vistos:
            res.invalidas.append(
                {"linha": numero_linha, "motivo": "Telefone repetido no arquivo"}
            )
            continue
        email = dados.get("email")
        if email and not email_valido(email):
            res.invalidas.append({"linha": numero_linha, "motivo": "E-mail inválido"})
            continue
        vistos.add(telefone)
        res.validas.append(
            LinhaCliente(
                linha=numero_linha,
                telefone=telefone,
                nome=(dados.get("nome") or None) and dados["nome"][:200],
                email=email[:200] if email else None,
                origem=(dados.get("origem") or None) and dados["origem"][:120],
            )
        )
    return res


def escrever_csv_clientes(
    linhas: Sequence[Sequence[object]], cabecalho: list[str]
) -> bytes:
    """CSV com `;` e BOM — abre certo no Excel em português."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(cabecalho)
    for linha in linhas:
        w.writerow(["" if v is None else _sem_formula(str(v)) for v in linha])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _sem_formula(valor: str) -> str:
    """Evita injeção de fórmula ao abrir no Excel (`=`, `+`, `-`, `@`).

    Telefone em E.164 começa com `+` e é o caso comum — ele fica como está
    porque só dígitos depois do `+` não formam fórmula perigosa.
    """
    if valor[:1] in ("=", "-", "@") or (
        valor[:1] == "+" and not _NAO_DIGITO.sub("", valor[1:]) == valor[1:]
    ):
        return "'" + valor
    return valor
