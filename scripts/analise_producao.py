#!/usr/bin/env python3.11
"""Analisa a produção com um modelo do OpenRouter e manda o relatório no Telegram.

Roda no python3.11 do host, instalado ao lado do 3.6 do sistema (o dnf do Oracle
Linux 8 depende do 3.6 — não troque o /usr/bin/python3). A sintaxe é mantida
compatível com 3.6 mesmo assim, para o script sobreviver a um host sem o 3.11.

Complementa o `monitor_evolution.sh`. O monitor responde uma pergunta binária —
"o socket está vivo?" — e age. Este script responde a pergunta aberta: o que os
dados de hoje dizem, e o que fazer a respeito.

Roda assim:
  scripts/analise_producao.py --ciclo      # o timer chama; decide se há o que fazer
  scripts/analise_producao.py              # gera e envia agora
  scripts/analise_producao.py --seco       # ensaio: imprime, não envia, não grava
  scripts/analise_producao.py --coleta     # só os dados crus, sem chamar o modelo

Configuração em /etc/chatnexus-monitor.env (mesmo arquivo do monitor):
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...
  OPENROUTER_API_KEY=...        # se ausente, é lido do container da API
  MODELO_ANALISE=...            # default abaixo

**Quem analisa são as CHECAGENS, não o modelo** (`producao_checks.py`). Elas
decidem o que está errado, com limiar visível e teste de unidade; o modelo só
redige o texto a partir do que elas acharem, e é proibido de introduzir fato
novo. A versão anterior pedia a análise ao LLM e num dos primeiros dias ele
relatou um incidente de uma data que não estava nos dados coletados.

Consequência prática: **se o OpenRouter cair ou a chave faltar, o relatório sai
mesmo assim**, em forma de lista. A análise não depende do modelo; só o
acabamento depende.

O `--ciclo` existe para o horário do envio morar no banco (mig 173) em vez de
numa unit do systemd — quem opera muda pelo painel. O timer acorda de minuto em
minuto, e este ramo atende primeiro um pedido de "gerar agora" do painel; se
não houver, checa se é a hora agendada, com claim atômico contra envio duplo.
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

CONFIG = os.environ.get("CONFIG", "/etc/chatnexus-monitor.env")
CONTAINER_API = os.environ.get("CONTAINER_API", "projetos-chatvsanexus-er02mp-api-1")
CONTAINER_DB = os.environ.get("CONTAINER_DB", "projetos-chatvsanexus-er02mp-db-1")
CONTAINER_EVO = os.environ.get(
    "CONTAINER_EVO", "automao-evolutionapi-tp0jdo-evolution-api-1"
)
PREFIXO_PROD = os.environ.get("PREFIXO_PROD", "projetos-chatvsanexus-er02mp")
# Haiku, não Sonnet: depois que a ANÁLISE saiu do modelo, o que sobra é
# redigir ~10 linhas a partir de uma lista pronta de achados. Comparados no
# mesmo input de produção, Haiku 4.5 escreveu um contexto MAIS rico que o
# Sonnet (citou backup, healthchecks e uptime dos containers) por uma fração
# do preço. O gemini-flash-lite também servia, mas chamou de "crítico" um
# achado de "atenção" — e a severidade tem que vir da checagem, não do
# adjetivo. Trocável por `MODELO_ANALISE` no env sem tocar no código.
MODELO = os.environ.get("MODELO_ANALISE", "anthropic/claude-haiku-4.5")
# Checkout do Dokploy: é a cópia do repositório que ACOMPANHA o deploy. O
# `chatnexus-backup.service` já aponta para cá; análise e monitor apontavam
# para `/opt/chatnexus`, cópia manual que ficou um commit atrás sem ninguém
# perceber. Daqui saem as migrations para comparar com o banco.
DIR_REPO = os.environ.get(
    "DIR_REPO", "/etc/dokploy/compose/projetos-chatvsanexus-er02mp/code"
)
# Onde o `backup_prod.sh` grava os dumps e o marcador do último envio externo.
# Precisa bater com o `DESTINO` do drop-in da unit de backup, senão a checagem
# do offsite lê um caminho que ninguém escreve e fica muda para sempre.
DIR_BACKUP = os.environ.get("DIR_BACKUP", "/home/opc/backup")
MARCADOR_OFFSITE = os.environ.get("MARCADOR_OFFSITE", ".ultimo_upload_offsite_ok")

# As checagens vivem ao lado deste arquivo — no host não existe o pacote da
# aplicação, então o import é por caminho, não por instalação.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from producao_checks import (  # noqa: E402
    resumo_texto,
    rodar_checagens,
    severidade_geral,
)


def carregar_config():
    """Lê o .env do monitor sem depender de python-dotenv (roda fora da venv)."""
    try:
        with open(CONFIG) as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def sh(cmd, timeout=60):
    try:
        # `capture_output`/`text` seriam mais limpos, e é o que o ruff pede
        # (UP022/UP021) — mas os dois só existem no 3.7+, e o cabeçalho deste
        # arquivo promete rodar no 3.6 caso o host não tenha o 3.11. Lint não
        # vale quebrar compatibilidade declarada.
        r = subprocess.run(  # noqa: UP022
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # noqa: UP021
            timeout=timeout,
        )
        return (r.stdout or r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as exc:  # noqa: BLE001 — coleta nunca deve derrubar o script
        return f"(erro: {exc})"


def sql(query):
    escapado = query.replace('"', '\\"')
    return sh(
        f'docker exec {CONTAINER_DB} psql -U postgres -d whatsapp_langchain -c "{escapado}"'
    )


def coletar():
    """Fatos, não interpretação. O modelo interpreta depois."""
    return {
        "agora": sh("date -Is"),
        "containers": sh(
            f"docker ps -a --filter name={PREFIXO_PROD} "
            "--format '{{.Names}}\t{{.Status}}'"
        ),
        "recursos_host": sh("free -m | head -2; uptime; df -h / | tail -1"),
        "fila_por_status": sql(
            "select status, count(*), min(created_at)::timestamp(0) as mais_antiga, "
            "max(created_at)::timestamp(0) as mais_nova from message_queue group by status order by 2 desc"
        ),
        "fila_ultimas_24h": sql(
            "select date_trunc('hour', created_at)::timestamp(0) as hora, count(*) "
            "from message_queue where created_at > now() - interval '24 hours' "
            "group by 1 order by 1 desc limit 12"
        ),
        "falhas_recentes": sql(
            "select id, attempts, left(coalesce(error,''), 120) as erro, "
            "created_at::timestamp(0) from message_queue where status='failed' "
            "order by id desc limit 8"
        ),
        "atendimentos_por_situacao": sql(
            "select status, count(*) from atendimento where created_at > now() - interval '7 days' "
            "group by 1 order by 2 desc"
        ),
        "erros_worker": sh(
            f"docker logs {PREFIXO_PROD}-worker-1 --since 24h 2>&1 | "
            'grep -oE \'"event": "[a-z_]+"\' | sort | uniq -c | sort -rn | head -15'
        ),
        "erros_api": sh(
            f"docker logs {PREFIXO_PROD}-api-1 --since 24h 2>&1 | "
            "grep -icE 'error|exception'"
        ),
        "evolution_reconexoes": sh(
            f"docker logs {CONTAINER_EVO} --since 24h 2>&1 | "
            "grep -acE 'CONNECTED TO WHATSAPP|connection.update'"
        ),
        "custo_llm_7d": sql(
            "select date(created_at) as dia, count(*) as execucoes, "
            "round(sum(custo_total)::numeric, 4) as usd from ia_execucao "
            "where created_at > now() - interval '7 days' group by 1 order by 1 desc"
        ),
    }


def analisar(dados, achados, chave):
    """Pede ao modelo a REDAÇÃO — não a análise.

    A análise já foi feita pelas checagens determinísticas e chega aqui pronta
    em `achados`. O modelo escreve o texto em cima delas: ordena, agrupa o que
    tem a mesma causa e explica o próximo passo.

    A versão anterior pedia "analise o estado de produção" e mandava os dados
    crus. O modelo respondia com conclusões plausíveis e, num dos primeiros
    dias, com um incidente de uma data que não estava nos dados. Redigir é o
    que ele faz bem; concluir sob pressão de formato, não.
    """
    resumo_achados = json.dumps(achados, ensure_ascii=False, indent=2)
    prompt = f"""Você redige o relatório de operação deste sistema, em português do Brasil.

O sistema é um atendimento de WhatsApp: uma API FastAPI recebe webhooks da Evolution API,
enfileira em `message_queue` no Postgres, e workers processam com um agente LangGraph e
respondem.

A ANÁLISE JÁ ESTÁ FEITA. Estes são os problemas encontrados por checagens automáticas,
cada um com a evidência que o sustenta e a ação sugerida:

{resumo_achados}

Os dados brutos de onde tudo saiu (use só para dar contexto ao que já está acima):
{json.dumps(dados, ensure_ascii=False, indent=2)}

Responda EXATAMENTE neste formato, sem preâmbulo:

SITUAÇÃO: <uma linha, coerente com a gravidade dos achados acima. Se a lista de achados
estiver vazia, diga que nenhuma checagem encontrou problema — não procure um.>

O QUE FAZER:
1. <o achado mais grave, explicado em uma frase, com a ação>
2. <...>
(um item por achado, na ordem em que vieram; se não houver achados, escreva "Nada a fazer.")

CONTEXTO ÚTIL:
- <no máximo 3 observações dos dados brutos que ajudem a entender os achados>
- <se não houver achados, use este espaço para o que os números mostram do dia>

Regras — a primeira versão deste relatório violou as três primeiras:
- NÃO invente problema que não esteja na lista de achados. Você redige, não diagnostica.
- Cite APENAS datas e números que aparecem acima. Se um dia não está lá, ele não existe
  para você.
- Use o campo `agora` para calcular "há quanto tempo". Uptime de container NÃO é a hora
  do último incidente.
- NUNCA sugira UPDATE, DELETE, TRUNCATE ou qualquer escrita em massa no banco. Ações são
  de investigação (SELECT, ler log, olhar tela) ou de operação (reiniciar serviço).
- Se um campo veio vazio ou com erro, diga que a coleta falhou em vez de inferir.
- Escreva toda data no formato AAAA-MM-DD, nunca abreviada.
- Seja específico e não repita a descrição do sistema."""

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(
            {
                "model": MODELO,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200,
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {chave}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        corpo = json.load(r)

    # O OpenRouter devolve 200 com envelope de erro — checar antes de indexar.
    if "error" in corpo:
        raise RuntimeError(f"OpenRouter recusou: {corpo['error']}")
    if not corpo.get("choices"):
        raise RuntimeError(f"resposta sem choices: {str(corpo)[:200]}")
    return corpo["choices"][0]["message"]["content"].strip()


def datas_inventadas(relatorio, dados):
    """Datas citadas no relatório que não aparecem em lugar nenhum na coleta.

    Pedir no prompt "não invente datas" não basta: nos dois primeiros testes o
    modelo citou 2026-07-24 e 2026-07-25 com números específicos de execuções,
    e nenhum dos dois dia estava nos dados. Aqui a checagem é determinística —
    se citou o que não existe, o leitor é avisado em vez de acreditar.
    """
    MESES = {
        "jan": "01",
        "fev": "02",
        "mar": "03",
        "abr": "04",
        "mai": "05",
        "jun": "06",
        "jul": "07",
        "ago": "08",
        "set": "09",
        "out": "10",
        "nov": "11",
        "dez": "12",
    }

    def dias(texto):
        """Normaliza para MM-DD: o modelo alterna entre ISO, 24/07 e 24/jul."""
        achados = set()
        for d in re.findall(r"\d{4}-(\d{2}-\d{2})", texto):
            achados.add(d)
        for dia, mes in re.findall(r"\b(\d{1,2})/(\d{1,2})\b", texto):
            achados.add(f"{int(mes):02d}-{int(dia):02d}")
        for dia, mes in re.findall(
            r"\b(\d{1,2})/(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)",
            texto.lower(),
        ):
            achados.add(f"{MESES[mes]}-{int(dia):02d}")
        return achados

    presentes = dias(json.dumps(dados, ensure_ascii=False))
    return sorted(d for d in dias(relatorio) if d not in presentes)


def telegram(texto):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("(Telegram não configurado — não enviei)", file=sys.stderr)
        return False
    # 4096 é o limite do Telegram; corta com folga pro aviso caber.
    if len(texto) > 3900:
        texto = texto[:3900] + "\n\n[...cortado]"
    dados = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=dados, timeout=30
        ) as r:
            return bool(json.load(r).get("ok"))
    except Exception as exc:  # noqa: BLE001
        print(f"(falha ao enviar: {exc})", file=sys.stderr)
        return False


def sql_stdin(texto):
    """Roda SQL pelo STDIN do psql, sem passar pelo shell.

    O `sql()` acima monta a query dentro de uma string de shell e escapa aspas
    na mão — serve para SELECT curto, mas quebra com JSON, que é justamente o
    que precisamos gravar. Aqui o SQL vai por stdin: o shell não vê o conteúdo.
    """
    cmd = [
        "docker",
        "exec",
        "-i",
        CONTAINER_DB,
        "psql",
        "-U",
        "postgres",
        "-d",
        "whatsapp_langchain",
        "-v",
        "ON_ERROR_STOP=1",
        "-t",
        "-A",
    ]
    try:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # noqa: UP021
        )
        saida, erro = p.communicate(texto, timeout=60)
    except Exception as exc:  # noqa: BLE001 — coleta nunca deve derrubar o script
        return "", str(exc)
    return (saida or "").strip(), (erro or "").strip()


def _dollar_quote(valor):
    """Empacota texto para o psql sem escapar nada.

    `$tag$...$tag$` é literal cru no Postgres: aspas, barras e acentos passam
    inteiros. Mas o delimitador é literal, então conteúdo que CONTENHA o
    delimitador o encerra no meio e o resto vira SQL.

    Uma versão anterior fixava a tag em `$rel$` supondo que isso "não acontece
    com JSON nem com texto de relatório". Acontece: aqui entram o texto escrito
    pelo MODELO e os dados coletados, que incluem `left(error, 120)` de
    `message_queue` — mensagem de erro cujo conteúdo pode ter origem no que um
    cliente mandou. E este script roda como root, com psql superusuário. Bastava
    um cliente conseguir a string certa num erro, ou induzir o modelo a
    escrevê-la, para injetar SQL.

    Agora a tag é escolhida para não existir no valor. O laço termina sempre: a
    cada volta o candidato é maior, e um texto finito não contém infinitas tags.
    """
    v = valor or ""
    tag = "rel"
    i = 0
    while ("$" + tag + "$") in v:
        i += 1
        tag = "rel%d" % i
    return "$" + tag + "$" + v + "$" + tag + "$"


def coletar_para_checagens():
    """Números estruturados — o que as CHECAGENS consomem.

    Separado do `coletar()`, que devolve texto tabular para o modelo ler. As
    checagens precisam de valor, não de tabela formatada: comparar limiar com
    string é como o erro entra sem ninguém ver.
    """

    def num(saida, default=None):
        try:
            return int(str(saida).strip().splitlines()[0])
        except Exception:  # noqa: BLE001
            return default

    minutos, _ = sql_stdin(
        "SELECT COALESCE(EXTRACT(EPOCH FROM (NOW()-MAX(processed_at)))/60, -1)::int "
        "FROM message_queue WHERE status='done';"
    )
    fila, _ = sql_stdin("SELECT count(*) FROM message_queue WHERE status='queued';")
    aplicadas, _ = sql_stdin("SELECT name FROM _migrations ORDER BY name;")

    disco = num(sh("df -h / | tail -1 | awk '{print $5}' | tr -d %"))

    # Horas desde o último sucesso do backup, pelo systemd.
    backup_horas = None
    epoch = num(
        sh(
            "systemctl show chatnexus-backup.service "
            "-p ExecMainExitTimestampMonotonic --value"
        )
    )
    ts = sh("systemctl show chatnexus-backup.service -p ExecMainExitTimestamp --value")
    if ts and not ts.startswith("("):
        segundos = num(sh('date -d "%s" +%%s' % ts.replace('"', "")))
        agora = num(sh("date +%s"))
        if segundos and agora:
            backup_horas = (agora - segundos) / 3600.0
    elif epoch:
        backup_horas = None

    # Horas desde o último upload do backup para fora do host. A fonte é o
    # marcador que o `backup_prod.sh` toca só quando o envio se confirmou no
    # destino — o exit do systemd não serve aqui, porque a falha de upload é
    # best-effort e não derruba a unit.
    backup_offsite_horas = None
    mtime = num(
        sh('stat -c %%Y "%s" 2>/dev/null' % (DIR_BACKUP + "/" + MARCADOR_OFFSITE))
    )
    agora_epoch = num(sh("date +%s"))
    if mtime and agora_epoch:
        backup_offsite_horas = (agora_epoch - mtime) / 3600.0

    arquivos = sh(
        "ls %s/db/migrations/*.sql 2>/dev/null | xargs -n1 basename" % DIR_REPO
    )

    m = num(minutos, None)
    return {
        # -1 é o "nunca processou nada" do COALESCE; vira None para a checagem
        # tratar como "não sei" em vez de "zero minutos".
        "minutos_sem_done": None if m is None or m < 0 else m,
        "fila_esperando": num(fila, 0),
        "disco_pct": disco,
        "backup_horas": backup_horas,
        "backup_offsite_horas": backup_offsite_horas,
        "migrations_arquivos": [x for x in arquivos.splitlines() if x.endswith(".sql")],
        "migrations_aplicadas": [
            x.strip() for x in aplicadas.splitlines() if x.strip().endswith(".sql")
        ],
    }


def salvar_no_banco(origem, solicitado_por, severidade, achados, texto, erro, dados):
    """Publica o relatório para o painel ler.

    O host é quem tem acesso à máquina; o painel só consome o que ele grava.
    Falha de gravação NÃO derruba o envio ao Telegram — o alerta chegar importa
    mais que ficar registrado.
    """
    sql = (
        "INSERT INTO relatorio_producao "
        "(origem, solicitado_por, severidade, achados, texto, modelo, dados, erro) "
        "VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s) RETURNING id;"
        % (
            _dollar_quote(origem),
            "NULL" if not solicitado_por else _dollar_quote(solicitado_por),
            _dollar_quote(severidade),
            _dollar_quote(json.dumps(achados, ensure_ascii=False)),
            "NULL" if texto is None else _dollar_quote(texto),
            _dollar_quote(MODELO) if texto else "NULL",
            _dollar_quote(json.dumps(dados, ensure_ascii=False)),
            "NULL" if not erro else _dollar_quote(erro),
        )
    )
    saida, err = sql_stdin(sql)
    if err:
        print(
            "aviso: não consegui gravar o relatório no banco: " + err, file=sys.stderr
        )
        return None
    try:
        return int(saida.splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def pedido_pendente():
    """Alguém clicou "gerar agora" no painel?"""
    saida, _ = sql_stdin(
        "SELECT id, solicitado_por FROM relatorio_producao_pedido "
        "WHERE atendido_at IS NULL ORDER BY criado_at LIMIT 1;"
    )
    linha = saida.splitlines()[0] if saida else ""
    if "|" not in linha:
        return None
    pid, quem = linha.split("|", 1)
    return {"id": int(pid), "solicitado_por": quem}


def fechar_pedido(pedido_id, relatorio_id):
    sql_stdin(
        "UPDATE relatorio_producao_pedido SET atendido_at = NOW(), relatorio_id = %s "
        "WHERE id = %s;"
        % ("NULL" if relatorio_id is None else str(relatorio_id), int(pedido_id))
    )


def claim_agendado():
    """É a hora configurada e ainda não rodou hoje?

    O UPDATE condicional é o claim: quem consegue a linha roda. Mesmo desenho
    de `shared/resumo_diario.py`, e pelo mesmo motivo — sem isso, dois ciclos
    do timer no mesmo minuto mandariam dois relatórios.
    """
    saida, _ = sql_stdin(
        "UPDATE relatorio_producao_config SET last_run_date = "
        "(NOW() AT TIME ZONE tz)::date "
        "WHERE id = 1 AND ativo "
        "AND (NOW() AT TIME ZONE tz)::time >= horario "
        "AND (last_run_date IS NULL OR last_run_date < (NOW() AT TIME ZONE tz)::date) "
        "RETURNING 1;"
    )
    return saida.strip() == "1"


def main():
    carregar_config()
    args = sys.argv[1:]

    # Modo daemon: o timer acorda de minuto em minuto e este ramo decide se há
    # o que fazer. Sem ele, mudar o horário exigiria editar unit do systemd.
    origem = "manual" if "--forcar" in args or "--seco" in args else None
    solicitado_por = None
    pedido = None
    if "--ciclo" in args:
        pedido = pedido_pendente()
        if pedido is not None:
            origem, solicitado_por = "manual", pedido["solicitado_por"]
        elif claim_agendado():
            origem = "agendado"
        else:
            return 0
    elif origem is None:
        origem = "agendado"

    dados = coletar()
    medidas = coletar_para_checagens()
    dados["medidas"] = medidas

    # A ANÁLISE acontece aqui, sem modelo nenhum.
    achados = [a.como_dict() for a in rodar_checagens(medidas)]
    severidade = severidade_geral(rodar_checagens(medidas))

    if "--coleta" in args:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0

    chave = os.environ.get("OPENROUTER_API_KEY") or sh(
        f"docker exec {CONTAINER_API} printenv OPENROUTER_API_KEY"
    )

    relatorio = None
    erro_llm = None
    if not chave or chave.startswith("("):
        erro_llm = "sem OPENROUTER_API_KEY"
    else:
        try:
            relatorio = analisar(dados, achados, chave)
        except Exception as exc:  # noqa: BLE001
            erro_llm = str(exc)

    # O relatório sai mesmo sem o modelo: a análise está nos achados, e só a
    # redação depende do LLM. Antes, falha do OpenRouter significava nenhum
    # aviso — justamente no dia em que algo pode estar errado.
    if relatorio is None:
        relatorio = resumo_texto(rodar_checagens(medidas))
        if erro_llm:
            relatorio += "\n\n(sem redação por IA: %s)" % erro_llm

    # `--seco` é ensaio: imprime e não deixa rastro. Gravar no banco a partir
    # dele encheria o histórico do painel de relatórios que ninguém pediu, e
    # ainda mexeria no claim do agendamento.
    if "--seco" not in args:
        relatorio_id = salvar_no_banco(
            origem, solicitado_por, severidade, achados, relatorio, erro_llm, dados
        )
        if pedido is not None:
            fechar_pedido(pedido["id"], relatorio_id)

    inventadas = datas_inventadas(relatorio, dados)
    aviso = ""
    if inventadas:
        aviso = (
            "\n\nATENÇÃO: o relatório cita datas que NÃO estão nos dados coletados: "
            + ", ".join(inventadas)
            + ". Trate as conclusões sobre esses dias como invenção do modelo."
        )

    fila = dados["fila_por_status"].replace("\n", " | ")[:200]
    # A severidade vem das checagens, não do texto: o relatório de antes abria
    # com "Sistema saudável" e listava três problemas logo abaixo.
    cabecalho = "Chat Nexus — produção [%s]" % severidade.upper()
    achados_txt = ""
    if achados:
        achados_txt = "\nAchados (checagem automática):\n" + "\n".join(
            "  [%s] %s — %s" % (a["severidade"].upper(), a["titulo"], a["evidencia"])
            for a in achados
        )
    texto = (
        f"{cabecalho}\n"
        f"modelo: {MODELO}\n"
        f"{'-' * 32}\n{relatorio}\n{'-' * 32}"
        f"{achados_txt}\n"
        f"Achados são determinísticos; o texto acima é redação por IA.\n"
        f"Fila: {fila}{aviso}"
    )

    if "--seco" in args:
        print(texto)
        return 0

    return 0 if telegram(texto) else 1


if __name__ == "__main__":
    sys.exit(main())
