"""Validação de telefone BR para cadastro de pessoas.

Existe porque `campanha.normalize_phone` não basta para telefone de USUÁRIO:
ela aceita qualquer coisa com 8+ dígitos e só prefixa `+`. Foi exatamente o
que deixou `+55996460034` (11 dígitos, sem DDD) passar no cadastro da empresa
1 — e o envio do relatório mensal falhou com `exists: false` no provedor,
cinco tentativas, um mês perdido.

Telefone de usuário é destino de WhatsApp (convite de acesso, avisos). Ou é
um número completo — país + DDD + linha — ou não serve, e a hora de recusar
é o cadastro, não o envio.

Contrato de `normalizar_br`:
- 12–13 dígitos começando com 55 → aceito como está (`+55` + DDD + 8/9)
- 10–11 dígitos → assume BR e prefixa `55`
- Resto → None. Inclusive o que `normalize_phone` deixaria passar.
"""

from __future__ import annotations

import re

_NAO_DIGITO = re.compile(r"\D")

# DDDs válidos no plano brasileiro (11–99, sem os furos: 20-23, 25, 26, 29,
# 30, 36, 39, 40, 50, 52, 56-60, 70, 72, 76, 78, 80, 90). Recusa "55" + um
# nono dígito colado que só PARECE ter DDD — o caso real da empresa 1 era
# `55 99 646...`, e "99" é DDD válido (Maranhão), então esse a gente não pega
# por DDD; pega pelo comprimento. Mas "5500..." e afins morrem aqui.
_DDDS_VALIDOS = frozenset(
    {
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        21,
        22,
        24,
        27,
        28,
        31,
        32,
        33,
        34,
        35,
        37,
        38,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        49,
        51,
        53,
        54,
        55,
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        71,
        73,
        74,
        75,
        77,
        79,
        81,
        82,
        83,
        84,
        85,
        86,
        87,
        88,
        89,
        91,
        92,
        93,
        94,
        95,
        96,
        97,
        98,
        99,
    }
)


def normalizar_br(raw: str | None) -> str | None:
    """Normaliza telefone BR para E.164 (`+55DDNNNNNNNNN`) ou devolve None.

    None significa "não dá para mandar WhatsApp para isto" — quem chama
    decide se recusa o cadastro ou segue sem telefone.
    """
    s = (raw or "").strip()
    if not s:
        return None
    digitos = _NAO_DIGITO.sub("", s)
    com_pais = s.lstrip().startswith("+")

    # O `+` desfaz a ambiguidade que derrubou a empresa 1: `+55996460034` tem
    # 11 dígitos, e "55" ali é o PAÍS (declarado pelo +) — logo faltou DDD.
    # Já `55996460034` sem `+` é um celular legítimo do DDD 55 (região de
    # Santa Maria-RS). Mesmos dígitos, leituras opostas.
    if com_pais:
        if len(digitos) not in (12, 13) or not digitos.startswith("55"):
            return None
    # 10-11 dígitos sem país: DDD + linha (8 fixo / 9 celular). Assume Brasil.
    elif len(digitos) in (10, 11):
        digitos = "55" + digitos
    # 12-13 dígitos: precisa ser 55 + DDD + linha.
    elif len(digitos) in (12, 13):
        if not digitos.startswith("55"):
            return None
    else:
        return None

    ddd = int(digitos[2:4])
    if ddd not in _DDDS_VALIDOS:
        return None

    linha = digitos[4:]
    # Celular (9 dígitos) começa com 9; fixo tem 8. Qualquer outra forma é
    # um número truncado ou com dígito sobrando.
    if len(linha) == 9 and not linha.startswith("9"):
        return None

    return f"+{digitos}"
