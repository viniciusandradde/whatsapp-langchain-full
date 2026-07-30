#!/usr/bin/env python3
"""Verificações locais do app Android, onde o compilador não roda.

Esta máquina é aarch64 e o `aapt2` não tem build para Linux ARM64, então o app
compila **somente no CI** — cada erro custa uma volta de ~2 minutos. Duas dessas
voltas foram gastas no MESMO erro: um fake de teste que deixou de casar com a
interface depois de eu mexer nela.

O que este script pega, sem toolchain nenhuma:

1. **Fake fora de sintonia com a interface.** Para cada `class X : Interface` em
   `src/test`, compara os métodos e os NOMES DOS PARÂMETROS de cada `override`
   com a declaração da interface em `src/main`. Comparar só o nome do método não
   bastaria — o que quebrou foi `mensagens` GANHAR um parâmetro.

2. **Comentário de bloco desbalanceado.** Em Kotlin `/* */` **aninha**, ao
   contrário de Java: um `/*` a mais dentro de KDoc abre um comentário que nunca
   fecha, e o compilador acusa "Unclosed comment" no FIM do arquivo, longe da
   causa.

Uso:  python3 android/scripts/checar_antes_de_subir.py
Saída: 0 = pode subir; 1 = tem problema, com arquivo e motivo.

Não substitui o CI: é regex, não parser. Serve pra pegar barato o que já
custou caro.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "app" / "src"

RE_FUN = re.compile(r"\bfun\s+(\w+)\s*\(")
RE_OVERRIDE = re.compile(r"\boverride\s+(?:suspend\s+)?fun\s+(\w+)\s*\(")


def bloco_parametros(texto: str, abre: int) -> tuple[str, int]:
    """Conteúdo entre parênteses BALANCEADOS e o índice depois do fecha.

    Regex simples (`[^)]*`) não serve: as anotações do Retrofit carregam os
    próprios parênteses (`@Query("tipo") tipo: String`), e parar no primeiro `)`
    devolvia lista de parâmetros vazia — foi assim que este verificador comparou
    tudo contra `[]` e não acusou nada.
    """
    profundidade = 0
    for i in range(abre, len(texto)):
        if texto[i] == "(":
            profundidade += 1
        elif texto[i] == ")":
            profundidade -= 1
            if profundidade == 0:
                return texto[abre + 1 : i], i + 1
    return "", len(texto)


def funcoes(corpo: str, regex: re.Pattern[str]) -> list[tuple[str, list[str], int]]:
    """`[(nome, [params], fim_da_assinatura)]` para cada `fun` encontrada."""
    achadas = []
    for m in regex.finditer(corpo):
        bloco, fim = bloco_parametros(corpo, m.end() - 1)
        achadas.append((m.group(1), params(bloco), fim))
    return achadas


RE_INTERFACE = re.compile(r"\binterface\s+(\w+)\s*\{", re.S)
RE_CLASSE = re.compile(r"\bclass\s+(\w+)\b")


def supertipos(texto: str, depois_do_nome: int) -> tuple[str, int]:
    """O que vem depois dos dois pontos da declaração, e onde o corpo começa.

    Precisa varrer com contagem de parênteses em vez de regex: o construtor
    carrega os PRÓPRIOS dois pontos (`aoListar: () -> Resposta`), e parar no
    primeiro `:` fazia a lista de supertipos sair vazia — o verificador dava
    verde em fake nenhum, que foi como ele passou nos dois erros que devia pegar.
    """
    i = depois_do_nome
    profundidade = 0
    while i < len(texto):
        ch = texto[i]
        # Conta SÓ parênteses. Contar `<` e `>` como generics quebrava em
        # `() -> Unit`: o `>` da seta era lido como fechamento e a profundidade
        # ficava negativa, então o `:` da herança nunca era visto no nível zero.
        if ch == "(":
            profundidade += 1
        elif ch == ")":
            profundidade -= 1
        elif profundidade == 0:
            if ch == "{":
                return "", i
            if ch == ":":
                fim = texto.find("{", i)
                return texto[i + 1 : fim], fim
        i += 1
    return "", len(texto)


def params(bloco: str) -> list[str]:
    """Nomes dos parâmetros, ignorando tipos e valores default."""
    # Comentário DENTRO do bloco de parâmetros primeiro: há KDoc documentando
    # parâmetro individual, e frases em português levam dois pontos ("medido em
    # produção:"), que o separador abaixo leria como `nome: tipo` e inventaria
    # parâmetros chamados "produção".
    bloco = re.sub(r"/\*.*?\*/", "", bloco, flags=re.S)
    bloco = re.sub(r"//[^\n]*", "", bloco)

    nomes = []
    profundidade = 0
    atual = ""
    for ch in bloco:
        if ch in "<(":
            profundidade += 1
        elif ch in ">)":
            profundidade -= 1
        if ch == "," and profundidade == 0:
            nomes.append(atual)
            atual = ""
        else:
            atual += ch
    nomes.append(atual)

    limpos = []
    for n in nomes:
        # Descarta anotação, modificador e o tipo; sobra o nome antes dos dois
        # pontos.
        n = re.sub(r"@\w+\s*(\([^)]*\))?", "", n).strip()
        if not n or ":" not in n:
            continue
        limpos.append(n.split(":")[0].split()[-1].strip())
    return limpos


def corpo_de(texto: str, inicio: int) -> str:
    """Trecho entre chaves balanceadas a partir de `inicio`."""
    profundidade = 0
    for i in range(inicio, len(texto)):
        if texto[i] == "{":
            profundidade += 1
        elif texto[i] == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio : i + 1]
    return texto[inicio:]


def tem_corpo(corpo: str, fim_da_assinatura: int) -> bool:
    """True se o método já traz implementação na própria interface.

    Kotlin permite corpo default em interface, e o DAO do Room usa isso
    (`substituirAba` chama `limparAba` + `salvar`). Método assim é OPCIONAL para
    quem implementa — cobrar seria falso positivo.
    """
    resto = corpo[fim_da_assinatura:].lstrip()
    # Pode haver o tipo de retorno antes do corpo: `): Foo = ...` ou `): Foo {`.
    if resto.startswith(":"):
        for i, ch in enumerate(resto):
            if ch in "{=" or ch == "\n":
                resto = resto[i:]
                break
    return resto.startswith("{") or resto.startswith("=")


def coletar_interfaces() -> dict[str, dict[str, list[str]]]:
    """`{Interface: {metodo: [params]}}` a partir de src/main.

    Só métodos ABSTRATOS: os que já têm corpo não obrigam ninguém.
    """
    tudo: dict[str, dict[str, list[str]]] = {}
    for arq in (RAIZ / "main").rglob("*.kt"):
        texto = arq.read_text(encoding="utf-8")
        for m in RE_INTERFACE.finditer(texto):
            corpo = corpo_de(texto, m.end() - 1)
            metodos = {}
            for nome, ps, fim in funcoes(corpo, RE_FUN):
                if tem_corpo(corpo, fim):
                    continue
                metodos[nome] = ps
            tudo[m.group(1)] = metodos
    return tudo


def checar_fakes(interfaces: dict[str, dict[str, list[str]]]) -> list[str]:
    problemas = []
    for arq in (RAIZ / "test").rglob("*.kt"):
        texto = arq.read_text(encoding="utf-8")
        for m in RE_CLASSE.finditer(texto):
            classe = m.group(1)
            heranca, inicio_corpo = supertipos(texto, m.end())
            alvos = [
                nome for nome in interfaces if re.search(rf"\b{nome}\b", heranca)
            ]
            if not alvos:
                continue
            corpo = corpo_de(texto, inicio_corpo)
            feitos = {nome: ps for nome, ps, _ in funcoes(corpo, RE_OVERRIDE)}
            for nome in alvos:
                for metodo, esperados in interfaces[nome].items():
                    if metodo not in feitos:
                        problemas.append(
                            f"{arq.relative_to(RAIZ.parent.parent)}: "
                            f"'{classe}' não implementa '{metodo}' de {nome}"
                        )
                    elif feitos[metodo] != esperados:
                        problemas.append(
                            f"{arq.relative_to(RAIZ.parent.parent)}: "
                            f"'{classe}.{metodo}' tem parâmetros {feitos[metodo]}, "
                            f"{nome} declara {esperados}"
                        )
    return problemas


def checar_comentarios() -> list[str]:
    problemas = []
    for arq in RAIZ.rglob("*.kt"):
        texto = arq.read_text(encoding="utf-8")
        abre, fecha = texto.count("/*"), texto.count("*/")
        if abre != fecha:
            problemas.append(
                f"{arq.relative_to(RAIZ.parent.parent)}: comentário de bloco "
                f"desbalanceado ({abre} abrem, {fecha} fecham) — em Kotlin /* */ ANINHA"
            )
    return problemas


def main() -> int:
    interfaces = coletar_interfaces()
    problemas = checar_fakes(interfaces) + checar_comentarios()
    if problemas:
        print("PROBLEMAS (o CI falharia nisto):\n")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print(f"ok — {len(interfaces)} interfaces conferidas, fakes em sintonia")
    return 0


if __name__ == "__main__":
    sys.exit(main())
