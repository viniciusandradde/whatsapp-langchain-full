"""Normalização de telefones brasileiros — pegadinha do "9 extra" mobile.

Em 2012 a ANATEL passou a exigir o dígito `9` antes do número de celular
após o DDD (DDDs 11..99 + 9 + 8 dígitos = 9 dígitos no número). Mas
sistemas legados, exportações antigas e alguns provedores (Evolution
inclusive) continuam armazenando/enviando o formato pré-2012 sem o 9.

Cenário típico:
- Usuário cadastra `+5567996460034` no painel (com 9, formato moderno).
- WhatsApp/Evolution envia inbound como `+556796460034` (sem 9).
- Lookup direto na DB falha. Bug silencioso.

Este módulo NÃO normaliza no INSERT (não mexe no que já está gravado).
Em vez disso: gera variantes na hora da BUSCA. Quem precisa comparar
phone usa `phone_variants(p)` e busca `WHERE col = ANY(variants)`.
"""

from __future__ import annotations

# DDDs válidos no Brasil (2 dígitos cada).
# Fonte: ANATEL — usado pra garantir que só geramos variantes pra phones
# que parecem brasileiros, sem mexer em internacionais.
_VALID_BR_DDDS: frozenset[str] = frozenset(
    f"{n:02d}"
    for n in (
        # SP
        11, 12, 13, 14, 15, 16, 17, 18, 19,
        # RJ
        21, 22, 24,
        # ES
        27, 28,
        # MG
        31, 32, 33, 34, 35, 37, 38,
        # PR
        41, 42, 43, 44, 45, 46,
        # SC
        47, 48, 49,
        # RS
        51, 53, 54, 55,
        # DF/GO/TO/MT/MS/RO/AC
        61, 62, 63, 64, 65, 66, 67, 68, 69,
        # AM/RR/AP/PA/MA/PI
        71, 73, 74, 75, 77, 79,
        # NE
        81, 82, 83, 84, 85, 86, 87, 88, 89,
        # N
        91, 92, 93, 94, 95, 96, 97, 98, 99,
    )
)


def phone_variants(phone: str) -> list[str]:
    """Retorna todas as variantes de um phone que devem ser tratadas
    como equivalentes em buscas.

    Comportamento:
    - Phone não-brasileiro (não começa com +55) → retorna `[phone]` puro.
    - Phone brasileiro de celular (DDD válido + 9 dígitos começando com 9)
      → retorna `[com_9, sem_9]`.
    - Phone brasileiro sem o 9 (DDD válido + 8 dígitos) → retorna
      `[sem_9, com_9]`.
    - Phone brasileiro fixo (DDD + 8 dígitos não começando com 9 OU 7-digit
      antigo) → retorna `[phone]` (não há variante).
    - Phone vazio/inválido → `[phone]`.

    Sempre inclui o phone original como primeiro item.

    Exemplos:
        phone_variants("+5567996460034") → ["+5567996460034", "+556796460034"]
        phone_variants("+556796460034")  → ["+556796460034", "+5567996460034"]
        phone_variants("+14155238886")   → ["+14155238886"]
        phone_variants("")               → [""]
    """
    if not phone or not phone.startswith("+55"):
        return [phone]

    # Remove "+55" e pega só dígitos
    rest = "".join(ch for ch in phone[3:] if ch.isdigit())
    if len(rest) < 10:  # não cabe DDD+8 dígitos
        return [phone]

    ddd = rest[:2]
    if ddd not in _VALID_BR_DDDS:
        return [phone]

    suffix = rest[2:]
    # Celular moderno: 9 dígitos começando com 9
    if len(suffix) == 9 and suffix.startswith("9"):
        sem_9 = f"+55{ddd}{suffix[1:]}"  # remove o 9 inicial
        return [phone, sem_9]
    # Sem o 9 (8 dígitos) — pode ser celular antigo OU fixo.
    # Pra celular: primeiro dígito do suffix está em 6-9 (faixa móvel).
    # Pra fixo: começa com 2-5. Geramos variante "com 9" apenas pro
    # caso celular antigo, pra cobrir o caso comum.
    if len(suffix) == 8 and suffix[0] in ("6", "7", "8", "9"):
        com_9 = f"+55{ddd}9{suffix}"
        return [phone, com_9]
    return [phone]


def phone_equivalent(a: str, b: str) -> bool:
    """True se dois phones são equivalentes considerando o 9 extra."""
    return a == b or b in phone_variants(a)
