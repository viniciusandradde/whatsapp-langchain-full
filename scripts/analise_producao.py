#!/usr/bin/env python3.11
"""Analisa a produção com um modelo do OpenRouter e manda o relatório no Telegram.

Roda no python3.11 do host, instalado ao lado do 3.6 do sistema (o dnf do Oracle
Linux 8 depende do 3.6 — não troque o /usr/bin/python3). A sintaxe é mantida
compatível com 3.6 mesmo assim, para o script sobreviver a um host sem o 3.11.

Complementa o `monitor_evolution.sh`. O monitor responde uma pergunta binária —
"o socket está vivo?" — e age. Este script responde a pergunta aberta: o que os
dados de hoje dizem, e o que fazer a respeito.

Roda de duas formas:
  scripts/analise_producao.py              # relatório e envio pro Telegram
  scripts/analise_producao.py --seco       # imprime no terminal, não envia
  scripts/analise_producao.py --coleta     # só os dados crus, sem chamar o modelo

Configuração em /etc/chatnexus-monitor.env (mesmo arquivo do monitor):
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...
  OPENROUTER_API_KEY=...        # se ausente, é lido do container da API
  MODELO_ANALISE=...            # default abaixo

O relatório é gerado por LLM e pode errar. Por isso os números coletados vão
junto no Telegram: dá pra conferir a conclusão contra o dado que a produziu.
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
MODELO = os.environ.get("MODELO_ANALISE", "anthropic/claude-sonnet-4.5")


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
        r = subprocess.run(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=timeout
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
            "grep -oE '\"event\": \"[a-z_]+\"' | sort | uniq -c | sort -rn | head -15"
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


def analisar(dados, chave):
    prompt = f"""Você é o SRE deste sistema. Analise o estado de produção abaixo e produza
um relatório curto e acionável, em português do Brasil.

O sistema é um atendimento de WhatsApp: uma API FastAPI recebe webhooks da Evolution API,
enfileira em `message_queue` no Postgres, e workers processam com um agente LangGraph e
respondem. Hoje (2026-07-31) houve um incidente: as instâncias da Evolution ficaram ~13h
com o socket morto reportando "open", e foi preciso reiniciar o container.

DADOS COLETADOS:
{json.dumps(dados, ensure_ascii=False, indent=2)}

Responda EXATAMENTE neste formato, sem preâmbulo:

SAÚDE: <uma linha — está saudável, degradado ou em incidente, e por quê>

O QUE OS DADOS MOSTRAM:
- <no máximo 5 itens, cada um citando o número que o sustenta>

AÇÕES RECOMENDADAS:
1. <ação concreta, com o comando ou arquivo quando fizer sentido>
2. <...>
(no máximo 4, ordenadas por urgência; se não houver nada urgente, diga isso)

RISCOS QUE NINGUÉM ESTÁ OLHANDO:
- <no máximo 3>

Regras (a primeira versão deste relatório violou as três):
- Cite APENAS datas e números que aparecem em DADOS COLETADOS. Se um dia não está lá,
  ele não existe para você — não conclua nada sobre ele.
- Use o campo `agora` para calcular "há quanto tempo". Uptime de container NÃO é a hora
  do último incidente.
- NUNCA sugira UPDATE, DELETE, TRUNCATE ou qualquer escrita em massa no banco. Ações são
  de investigação (consultas SELECT, ler logs, olhar uma tela) ou de operação
  (reiniciar serviço). Se achar que dados precisam ser corrigidos, diga o que investigar
  e deixe a decisão para o humano.
- Confira o nome das tabelas contra os dados; não invente plural nem singular.
- Se um campo veio vazio ou com erro, diga que a coleta falhou em vez de inferir.
- Escreva toda data no formato AAAA-MM-DD, nunca abreviada.\n- Seja específico, cite números, e não repita a descrição do sistema."""

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
    MESES = {"jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05",
             "jun": "06", "jul": "07", "ago": "08", "set": "09", "out": "10",
             "nov": "11", "dez": "12"}

    def dias(texto):
        """Normaliza para MM-DD: o modelo alterna entre ISO, 24/07 e 24/jul."""
        achados = set()
        for d in re.findall(r"\d{4}-(\d{2}-\d{2})", texto):
            achados.add(d)
        for dia, mes in re.findall(r"\b(\d{1,2})/(\d{1,2})\b", texto):
            achados.add("%02d-%02d" % (int(mes), int(dia)))
        for dia, mes in re.findall(r"\b(\d{1,2})/(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto.lower()):
            achados.add("%s-%02d" % (MESES[mes], int(dia)))
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


def main():
    carregar_config()
    args = sys.argv[1:]

    dados = coletar()
    if "--coleta" in args:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0

    chave = os.environ.get("OPENROUTER_API_KEY") or sh(
        f"docker exec {CONTAINER_API} printenv OPENROUTER_API_KEY"
    )
    if not chave or chave.startswith("("):
        print("sem OPENROUTER_API_KEY — configure em " + CONFIG, file=sys.stderr)
        return 1

    try:
        relatorio = analisar(dados, chave)
    except Exception as exc:  # noqa: BLE001
        msg = f"Chat Nexus — a análise falhou\n\n{exc}\n\nOs dados foram coletados; rode com --coleta para vê-los."
        telegram(msg)
        print(msg, file=sys.stderr)
        return 1

    inventadas = datas_inventadas(relatorio, dados)
    aviso = ""
    if inventadas:
        aviso = (
            "\n\nATENÇÃO: o relatório cita datas que NÃO estão nos dados coletados: "
            + ", ".join(inventadas)
            + ". Trate as conclusões sobre esses dias como invenção do modelo."
        )

    fila = dados["fila_por_status"].replace("\n", " | ")[:200]
    texto = (
        f"Chat Nexus — análise de produção\n"
        f"modelo: {MODELO}\n"
        f"{'-' * 32}\n{relatorio}\n{'-' * 32}\n"
        f"Gerado por LLM: confira contra os dados.\nFila: {fila}{aviso}"
    )

    if "--seco" in args:
        print(texto)
        return 0

    return 0 if telegram(texto) else 1


if __name__ == "__main__":
    sys.exit(main())
