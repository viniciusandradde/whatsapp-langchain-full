"""Checagens determinísticas da produção — a análise que NÃO é feita por LLM.

Antes, o relatório diário pedia a análise ao modelo e ele respondia com
conclusões plausíveis. Num dos primeiros dias citou o incidente de 07-31 com
números que não estavam nos dados coletados. Pedir no prompt para não inventar
não resolve: o modelo é bom em escrever, não em garantir.

Aqui a lógica é invertida. **Estas funções decidem o que está errado**; o
modelo, depois, só redige o texto a partir do que elas acharem. Cada checagem é
uma função pura — recebe números, devolve um achado — então tem teste de
unidade, roda no CI sem host e sem rede, e o limiar fica visível em vez de
implícito na cabeça de um modelo.

**Só stdlib, e sintaxe compatível com 3.6**: este módulo é importado pelo
`analise_producao.py`, que roda no host de produção (fora dos containers, onde
não existe o pacote da aplicação nem as dependências dele).
"""

OK = "ok"
ATENCAO = "atencao"
CRITICO = "critico"

#: Ordem de gravidade, para ordenar achados e derivar a severidade do relatório.
_PESO = {OK: 0, ATENCAO: 1, CRITICO: 2}

#: Sem mensagem concluída por mais que isto, COM fila esperando, o worker parou.
#: 30 min é folgado de propósito: o pior caso normal (agente lento + retry) fica
#: bem abaixo, e o incidente de julho durou ~40h.
LIMITE_WORKER_MUDO_MIN = 30

#: Disco. O host tem 169G; a 90% sobram ~17G, que o Postgres come rápido.
DISCO_ATENCAO_PCT = 80
DISCO_CRITICO_PCT = 90

#: Backup diário. 26h em vez de 24h dá margem para o `RandomizedDelaySec` da
#: unit e para um dia em que a máquina estava desligada na hora.
LIMITE_BACKUP_H = 26

#: Saldo do OpenRouter. Abaixo do CRÍTICO a mídia já está falhando: o OpenRouter
#: recusa pelo CUSTO ESTIMADO da requisição, e transcrição de áudio estima mais
#: caro que texto — daí o sintoma clássico ser "áudio parou, texto funciona".
#: Medido no incidente de 2026-09-10: com US$ 0,41 restantes, áudio dava 402 e
#: texto passava. O piso de atenção é relativo ao teto porque o consumo escala
#: com o uso: quem gasta US$ 10/mês não quer ser avisado no mesmo valor absoluto
#: de quem gasta US$ 1.000.
OPENROUTER_CRITICO_USD = 1.00
OPENROUTER_ATENCAO_PCT = 20

#: Tamanho das tabelas que incham silenciosamente (checkpoints do LangGraph,
#: message_queue). O dump de produção dobrou em 11 dias sem ninguém ver até
#: alguém abrir o pg_stat (plano 2026-09-15).
TABELA_ATENCAO_MB = 500
TABELA_CRITICO_MB = 2000

#: Sunset das versões da Graph API (Meta garante 2 anos por versão). Datas
#: públicas e fixas, conferidas na documentação oficial em 2026-08-21.
#: Uma versão fora do ar derruba TODO o WhatsApp oficial de uma vez, e ninguém
#: vai lembrar disso daqui a dois anos — é o mesmo caso do backup: falha
#: anunciada com meses de antecedência que só se descobre no dia.
SUNSET_GRAPH_API = {
    "v20.0": "2026-09-24",
    "v21.0": "2027-01-21",
    "v22.0": "2027-05-20",
    "v23.0": "2027-10-08",
    "v24.0": "2028-02-18",
    "v25.0": "2028-07-29",
}

#: Aviso com 90 dias: dá tempo de subir de versão, testar e deployar sem correria.
DIAS_AVISO_GRAPH_API = 90


class Achado(object):
    """Um problema encontrado, com o dado que o sustenta.

    `evidencia` existe para o relatório poder mostrar o número ao lado da
    conclusão — foi a ausência disso que permitiu ao modelo afirmar coisas sem
    lastro. `acao` é o próximo passo concreto, não conselho genérico.
    """

    def __init__(self, chave, severidade, titulo, evidencia, acao):
        self.chave = chave
        self.severidade = severidade
        self.titulo = titulo
        self.evidencia = evidencia
        self.acao = acao

    def como_dict(self):
        return {
            "chave": self.chave,
            "severidade": self.severidade,
            "titulo": self.titulo,
            "evidencia": self.evidencia,
            "acao": self.acao,
        }

    def __repr__(self):  # pragma: no cover — só para depuração
        return "<Achado {0} {1}>".format(self.chave, self.severidade)


def checar_worker_mudo(minutos_sem_done, fila_esperando):
    """O worker parou de processar enquanto havia fila?

    **É a checagem que teria pego o incidente de julho**, quando o agente ficou
    cerca de 40h sem responder porque a conexão do checkpointer morreu. Nenhum
    alarme disparou: os containers estavam "Up", a API respondia, e a fila só
    crescia.

    Os dois sinais juntos importam. Fila vazia e nada processando é sistema
    ocioso de madrugada — saudável. Fila cheia e nada saindo é o worker morto.
    """
    if fila_esperando <= 0:
        return None
    if minutos_sem_done is None:
        return None
    if minutos_sem_done < LIMITE_WORKER_MUDO_MIN:
        return None
    return Achado(
        chave="worker_mudo",
        severidade=CRITICO,
        titulo="Worker parado com fila esperando",
        evidencia=(
            "{0} mensagens na fila e nenhuma concluída há {1} min".format(
                fila_esperando, int(minutos_sem_done)
            )
        ),
        acao=(
            "Ver `docker logs <prefixo>-worker-1 --tail 200`. Se estiver mudo, "
            "reiniciar o worker e conferir a conexão do checkpointer."
        ),
    )


def checar_disco(percentual_uso):
    """Disco do HOST — não do container.

    Dentro de um container `df` mostra o overlay, não a máquina: o número sai
    plausível e errado. Por isso esta checagem só roda no host.
    """
    if percentual_uso is None:
        return None
    if percentual_uso >= DISCO_CRITICO_PCT:
        sev = CRITICO
    elif percentual_uso >= DISCO_ATENCAO_PCT:
        sev = ATENCAO
    else:
        return None
    return Achado(
        chave="disco",
        severidade=sev,
        titulo="Disco do host em {0}%".format(percentual_uso),
        evidencia="uso da partição raiz: {0}%".format(percentual_uso),
        acao=(
            "Ver `du -sh /var/lib/docker/* | sort -h`. Imagens e logs antigos "
            "costumam ser a maior fatia; `docker system prune` resolve o comum."
        ),
    )


def checar_backup(horas_desde_ultimo_sucesso):
    """Backup que falha calado é o pior tipo de falha.

    Só se descobre no dia em que ele é necessário — e aí já era.
    """
    if horas_desde_ultimo_sucesso is None:
        return Achado(
            chave="backup",
            severidade=CRITICO,
            titulo="Backup sem registro de execução",
            evidencia="não foi possível ler o estado de `chatnexus-backup.service`",
            acao="Conferir `systemctl status chatnexus-backup.service` e o timer.",
        )
    if horas_desde_ultimo_sucesso < LIMITE_BACKUP_H:
        return None
    return Achado(
        chave="backup",
        severidade=CRITICO,
        titulo="Backup não roda há {0}h".format(int(horas_desde_ultimo_sucesso)),
        evidencia="último sucesso de `chatnexus-backup.service` há {0}h".format(
            int(horas_desde_ultimo_sucesso)
        ),
        acao="Rodar `systemctl start chatnexus-backup.service` e ler o journal.",
    )


def checar_backup_offsite(horas_desde_ultimo_upload):
    """O backup existe FORA do host?

    Em 2026-08-19 o servidor sumiu e levou junto o dump em disco e o espelho no
    MinIO — os dois moravam nele. A cópia externa é a única que sobrevive a
    perder a máquina, e ela para de funcionar em silêncio (token revogado, cota,
    rede) exatamente como o backup parava antes de existir esta checagem.

    `None` é silêncio proposital: instalação sem `RCLONE_REMOTE` não tem cópia
    externa por opção, e alarmar todo dia por uma feature desligada treina quem
    lê a ignorar o relatório.
    """
    if horas_desde_ultimo_upload is None:
        return None
    if horas_desde_ultimo_upload < LIMITE_BACKUP_H:
        return None
    return Achado(
        chave="backup_offsite",
        severidade=CRITICO,
        titulo="Backup não sai do host há {0}h".format(int(horas_desde_ultimo_upload)),
        evidencia="último upload externo bem-sucedido há {0}h".format(
            int(horas_desde_ultimo_upload)
        ),
        acao=(
            "Rodar `systemctl start chatnexus-backup.service` e ler o journal; "
            "se o erro for do rclone, conferir o token com `rclone lsd <remoto>:`."
        ),
    )


def checar_saldo_openrouter(saldo_usd, teto_usd=None, origem=None):
    """Ainda há saldo para o agente responder?

    Sem isto, acabar o crédito é uma falha SILENCIOSA e enganosa. Em 2026-09-10
    o teto da chave (US$ 5) esgotou com US$ 11,98 sobrando na conta: o cliente
    mandou áudio e recebeu "estamos com dificuldades em processar imagens/audio"
    por mais de uma hora, sem nenhum alarme. Descobriu-se porque alguém reparou
    na tela.

    O sintoma engana duas vezes. Parece intermitente (o OpenRouter recusa pelo
    custo ESTIMADO, então áudio cai antes do texto) e parece falta de dinheiro
    (quando o que acabou era o teto DA CHAVE). Por isso `origem` entra na ação:
    "chave" se conserta no painel de chaves, "conta" comprando crédito — e
    mandar comprar crédito quando o problema é o teto não resolve nada.

    `None` é silêncio proposital, igual ao backup offsite: chave sem teto e API
    fora do ar são "não sei", não "está tudo bem".
    """
    if saldo_usd is None:
        return None

    onde = {"chave": "teto da chave", "conta": "crédito da conta"}.get(origem, "saldo")
    acao_chave = (
        "Aumentar ou remover o limite da chave em openrouter.ai/settings/keys "
        "(não precisa comprar crédito se a conta tem saldo)."
    )
    acao_conta = "Comprar crédito em openrouter.ai/credits."
    acao = acao_chave if origem == "chave" else acao_conta

    if saldo_usd < OPENROUTER_CRITICO_USD:
        return Achado(
            chave="openrouter_saldo",
            severidade=CRITICO,
            titulo="OpenRouter com US$ {0:.2f} — mídia já falha".format(saldo_usd),
            evidencia=(
                "{0} restante: US$ {1:.2f}. Abaixo de US$ {2:.2f} a transcrição "
                "de áudio e a leitura de imagem passam a receber 402, enquanto "
                "texto ainda funciona — o cliente ouve 'mande mensagem de texto'."
            ).format(onde, saldo_usd, OPENROUTER_CRITICO_USD),
            acao=acao,
        )

    if teto_usd and saldo_usd < (teto_usd * OPENROUTER_ATENCAO_PCT / 100.0):
        return Achado(
            chave="openrouter_saldo",
            severidade=ATENCAO,
            titulo="OpenRouter com US$ {0:.2f} de US$ {1:.2f}".format(
                saldo_usd, teto_usd
            ),
            evidencia="{0} restante: US$ {1:.2f} ({2:.0f}% do teto).".format(
                onde, saldo_usd, saldo_usd / teto_usd * 100.0
            ),
            acao=acao,
        )
    return None


def checar_tamanho_tabela(tamanho_mb, tabela="checkpoints"):
    """Uma tabela cresceu a ponto de ameaçar o dump/o disco?

    Os `checkpoints` do LangGraph chegaram a 65% do banco em produção porque
    a mídia inline (base64) entrava no `configurable` e o `AsyncPostgresSaver`
    copia isso pro `metadata` a cada passo do agente (plano 2026-09-15). Era
    invisível: o dump só ia dobrando. `message_queue` tem a mesma raiz na
    coluna `media_url`. A Fase 1 (PR #123) estanca a fonte; esta checagem é o
    alarme pra ninguém mais descobrir tarde.

    `None` quando não veio medida — coleta parcial não é "está tudo bem".
    """
    if tamanho_mb is None:
        return None
    if tamanho_mb >= TABELA_CRITICO_MB:
        sev = CRITICO
    elif tamanho_mb >= TABELA_ATENCAO_MB:
        sev = ATENCAO
    else:
        return None
    if tabela == "checkpoints":
        acao = (
            "Conferir se a poda de retenção está rodando "
            "(`checkpoint_retencao_ok` no log do worker) e se a Fase 1 "
            "(configurable sem base64) já está em produção. Limpeza única + "
            "VACUUM em `.planning/reports/20260915-checkpoints-langgraph-plano.md` "
            "(Fase 3), nunca VACUUM FULL em horário comercial."
        )
    else:
        acao = (
            "Mesma raiz dos checkpoints (base64 em coluna de mídia). Avaliar "
            "retenção/limpeza de `{0}` — decisão própria, fora do plano dos "
            "checkpoints."
        ).format(tabela)
    return Achado(
        chave="tamanho_" + tabela,
        severidade=sev,
        titulo="Tabela {0} com {1} MB".format(tabela, int(tamanho_mb)),
        evidencia=(
            "pg_total_relation_size({0}) = {1} MB "
            "(ATENÇÃO a partir de {2} MB, CRÍTICO a partir de {3} MB)."
        ).format(tabela, int(tamanho_mb), TABELA_ATENCAO_MB, TABELA_CRITICO_MB),
        acao=acao,
    )


def checar_graph_api_version(versao, hoje):
    """A versão da Graph API do WhatsApp oficial ainda está no ar?

    Meta mantém cada versão por ~2 anos e derruba na data marcada. Quando cai,
    todo envio e todo webhook do WhatsApp oficial param de uma vez — e o aviso
    existe desde o lançamento, dois anos antes, num changelog que ninguém relê.

    Silêncio (None) em três casos, de propósito: sem versão configurada (WABA
    desligado), versão desconhecida (mais nova que esta tabela — quem atualizou
    já sabe o que fez) e data ainda distante.
    """
    if not versao:
        return None
    sunset = SUNSET_GRAPH_API.get(versao)
    if not sunset or not hoje:
        return None

    faltam = _dias_entre(hoje, sunset)
    if faltam is None or faltam > DIAS_AVISO_GRAPH_API:
        return None

    if faltam <= 0:
        return Achado(
            chave="graph_api_version",
            severidade=CRITICO,
            titulo="Graph API {0} fora do ar desde {1}".format(versao, sunset),
            evidencia="WABA_GRAPH_API_VERSION={0}, sunset em {1}".format(
                versao, sunset
            ),
            acao=(
                "Subir `WABA_GRAPH_API_VERSION` para uma versão suportada e "
                "redeployar. Enquanto isso o WhatsApp oficial não envia nem recebe."
            ),
        )
    return Achado(
        chave="graph_api_version",
        severidade=ATENCAO,
        titulo="Graph API {0} sai do ar em {1} dias".format(versao, faltam),
        evidencia="WABA_GRAPH_API_VERSION={0}, sunset em {1}".format(versao, sunset),
        acao="Planejar o bump de `WABA_GRAPH_API_VERSION` antes da data.",
    )


def _dias_entre(inicio, fim):
    """Dias de `inicio` até `fim`, ambos 'AAAA-MM-DD'. None se não der pra ler.

    Conta na mão para não depender de `datetime` — este módulo roda no python do
    host, fora da venv, e a regra do projeto é manter só stdlib básica aqui.
    """
    try:
        import datetime as _dt

        d0 = _dt.date(*[int(x) for x in str(inicio)[:10].split("-")])
        d1 = _dt.date(*[int(x) for x in str(fim)[:10].split("-")])
    except (ValueError, TypeError):
        return None
    return (d1 - d0).days


def checar_migrations(arquivos, aplicadas):
    """O repositório e o banco contam a mesma história?

    Esta checagem nasceu de um caso real: a `153_drop_twilio_provider.sql` foi
    aplicada no banco de desenvolvimento e nunca entrou no repositório. O
    resultado foi um teste que passava contra produção e falhava em dev, e
    ninguém sabia por quê — o banco tinha uma restrição que o código não
    declarava.

    Divergência nos dois sentidos importa:

    - **arquivo sem aplicação**: migration esperando um deploy que não veio;
    - **aplicada sem arquivo**: alguém rodou SQL à mão, e nenhum ambiente novo
      vai reproduzir esse estado.
    """
    faltam_aplicar = sorted(set(arquivos) - set(aplicadas))
    sem_arquivo = sorted(set(aplicadas) - set(arquivos))
    if not faltam_aplicar and not sem_arquivo:
        return None

    partes = []
    if faltam_aplicar:
        partes.append(
            "no repositório e não aplicadas: {0}".format(", ".join(faltam_aplicar))
        )
    if sem_arquivo:
        partes.append(
            "aplicadas sem arquivo no repositório: {0}".format(", ".join(sem_arquivo))
        )

    # Aplicada sem arquivo é mais grave: não há como recriar o ambiente.
    sev = CRITICO if sem_arquivo else ATENCAO
    return Achado(
        chave="migrations",
        severidade=sev,
        titulo="Banco e repositório divergem em migrations",
        evidencia="; ".join(partes),
        acao=(
            "Se falta aplicar, conferir se o deploy subiu. Se está aplicada sem "
            "arquivo, alguém rodou SQL à mão — trazer para `db/migrations/`."
        ),
    )


def checar_ia_alertas(alertas_ativos, alertas_resumo=None):
    """Alertas de degradação de IA abertos (mig 180).

    A detecção mora no worker (shared/ia_alertas.py) e já notificou na hora;
    aqui o alerta VIVO entra no resumo do dia para não morrer esquecido —
    mesmo papel da linha de backup: falha que só se descobre quando dói.
    """
    if alertas_ativos is None or alertas_ativos <= 0:
        return None
    return Achado(
        chave="ia_alertas",
        severidade=ATENCAO,
        titulo="{0} alerta(s) de degradacao de IA ativo(s)".format(alertas_ativos),
        evidencia=alertas_resumo or "ver a Visao geral do Catalogo OpenRouter",
        acao=(
            "Abrir /catalog/openrouter no painel. O alerta resolve sozinho "
            "quando a condicao normaliza; ativo ha horas = provedor degradado "
            "de verdade — considerar trocar o modelo do agente."
        ),
    )


LIMITE_MONITOR_CONEXOES_MIN = 20


def checar_conexoes_clientes(caidas, sem_atividade, resumo=None):
    """Episódios de saúde de conexão abertos (mig 196).

    O worker já avisou o canal na hora; aqui o episódio VIVO entra no resumo
    do dia (mesmo papel de `checar_ia_alertas`). Conexão caída é CRITICO — o
    cliente está sem WhatsApp e só ele pode reparear; silêncio com a conexão
    respondendo é ATENCAO — pode ser feriado ou o cliente parado.
    """
    caidas = caidas or 0
    sem_atividade = sem_atividade or 0
    if caidas <= 0 and sem_atividade <= 0:
        return None
    partes = []
    if caidas:
        partes.append("{0} conexao(oes) caida(s)".format(caidas))
    if sem_atividade:
        partes.append("{0} sem mensagens contra a baseline".format(sem_atividade))
    return Achado(
        chave="conexoes_clientes",
        severidade=CRITICO if caidas else ATENCAO,
        titulo="Clientes: " + ", ".join(partes),
        evidencia=resumo or "ver Saude dos clientes no painel",
        acao=(
            "Abrir /monitor/conexoes no painel. Caida = o cliente precisa "
            "reparear o WhatsApp (QR ou codigo em Conexoes); sem mensagens com "
            "a conexao respondendo = cliente parado ou feriado — confirmar com ele."
        ),
    )


def checar_monitor_conexoes_parado(minutos_desde_tick):
    """O monitor de conexões precisa dar sinal de vida: sem tick há mais de
    `LIMITE_MONITOR_CONEXOES_MIN` min, ninguém está olhando os clientes."""
    if minutos_desde_tick is None or minutos_desde_tick <= LIMITE_MONITOR_CONEXOES_MIN:
        return None
    return Achado(
        chave="monitor_conexoes_parado",
        severidade=ATENCAO,
        titulo="Monitor de conexoes sem verificar ha {0} min".format(
            int(minutos_desde_tick)
        ),
        evidencia="ultimo tick de saude_conexoes_estado ha {0} min (esperado a cada 5)".format(
            int(minutos_desde_tick)
        ),
        acao=(
            "Conferir o worker (docker logs ... | grep saude_conexoes). Enquanto o "
            "monitor nao roda, conexao caida ou cliente mudo passam despercebidos."
        ),
    )


def rodar_checagens(dados):
    """Roda todas as checagens sobre os dados coletados.

    Campo ausente não quebra nada: cada checagem devolve `None` quando não tem
    como decidir. Isso é deliberado — o relatório precisa sair mesmo com coleta
    parcial, e "não sei" é diferente de "está tudo bem".
    """
    achados = []
    for achado in (
        checar_worker_mudo(
            dados.get("minutos_sem_done"), dados.get("fila_esperando", 0)
        ),
        checar_disco(dados.get("disco_pct")),
        checar_backup(dados.get("backup_horas")),
        checar_backup_offsite(dados.get("backup_offsite_horas")),
        checar_saldo_openrouter(
            dados.get("openrouter_saldo"),
            dados.get("openrouter_teto"),
            dados.get("openrouter_origem"),
        ),
        checar_tamanho_tabela(dados.get("checkpoints_mb"), "checkpoints"),
        checar_tamanho_tabela(dados.get("message_queue_mb"), "message_queue"),
        checar_graph_api_version(dados.get("graph_api_version"), dados.get("hoje")),
        checar_migrations(
            dados.get("migrations_arquivos") or [],
            dados.get("migrations_aplicadas") or [],
        ),
        checar_ia_alertas(
            dados.get("ia_alertas_ativos"), dados.get("ia_alertas_resumo")
        ),
        checar_conexoes_clientes(
            dados.get("conexoes_caidas"),
            dados.get("conexoes_sem_atividade"),
            dados.get("conexoes_resumo"),
        ),
        checar_monitor_conexoes_parado(dados.get("monitor_conexoes_min")),
    ):
        if achado is not None:
            achados.append(achado)
    achados.sort(key=lambda a: -_PESO[a.severidade])
    return achados


def severidade_geral(achados):
    """A severidade do relatório é a do pior achado — não uma opinião.

    O relatório de hoje abre com "Sistema saudável" e logo abaixo lista disco em
    81%, 45 reconexões e falhas. Narrativa de modelo tende a suavizar; aqui o
    título passa a ser consequência aritmética do que foi encontrado.
    """
    if not achados:
        return OK
    return max(achados, key=lambda a: _PESO[a.severidade]).severidade


def linha_backup(dados):
    """Uma linha dizendo que o backup rodou — inclusive quando deu tudo certo.

    As checagens só falam quando algo quebrou, então backup saudável era
    silêncio absoluto: o dono perguntou "não vi o backup rodando" com o backup
    rodando havia dias. Alarme prova falha; esta linha prova funcionamento, que
    é o que dá sossego para quem só quer saber se está protegido.
    """
    arquivo = (dados.get("backup_arquivo") or "").strip()
    if not arquivo:
        return "Backup: sem arquivo no diretório configurado."

    quando = (dados.get("backup_arquivo_hora") or "").strip()
    tamanho = (dados.get("backup_arquivo_tamanho") or "").strip()
    partes = ["Backup: {0}".format(arquivo)]
    if quando:
        partes.append("às {0}".format(quando))
    if tamanho:
        partes.append("({0})".format(tamanho))

    offsite = dados.get("backup_offsite_horas")
    if offsite is None:
        partes.append("— só neste host (sem cópia externa configurada)")
    elif offsite < LIMITE_BACKUP_H:
        partes.append("— no Google Drive tambem")
    else:
        partes.append("— NAO subiu para o Drive ha {0}h".format(int(offsite)))
    return " ".join(partes)


def resumo_texto(achados):
    """Relatório em lista, sem LLM.

    É o que sai quando o modelo falha ou a chave não está configurada. Feio,
    porém correto — e a correção é o que importa num alerta.
    """
    if not achados:
        return "Nenhum problema encontrado pelas checagens automáticas."
    linhas = []
    for a in achados:
        linhas.append("[{0}] {1}".format(a.severidade.upper(), a.titulo))
        linhas.append("    evidência: {0}".format(a.evidencia))
        linhas.append("    ação: {0}".format(a.acao))
    return "\n".join(linhas)
