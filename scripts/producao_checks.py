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
        checar_migrations(
            dados.get("migrations_arquivos") or [],
            dados.get("migrations_aplicadas") or [],
        ),
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
