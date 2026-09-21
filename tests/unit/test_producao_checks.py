"""Checagens determinísticas do relatório de produção.

Este arquivo é o motivo de a análise ter saído do LLM. Cada regra que antes
vivia como instrução num prompt ("avalie a saúde do sistema") agora é uma
função com caso de borda testável, rodando no CI sem host e sem rede.

O módulo mora em `scripts/` porque é importado pelo `analise_producao.py`, que
roda no host de produção — fora dos containers, onde o pacote da aplicação não
existe.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from producao_checks import (  # noqa: E402
    ATENCAO,
    CRITICO,
    OK,
    checar_backup,
    checar_backup_offsite,
    checar_conexoes_clientes,
    checar_disco,
    checar_graph_api_version,
    checar_ia_alertas,
    checar_migrations,
    checar_monitor_conexoes_parado,
    checar_saldo_openrouter,
    checar_tamanho_tabela,
    checar_worker_mudo,
    linha_backup,
    resumo_texto,
    rodar_checagens,
    severidade_geral,
)


class TestWorkerMudo:
    """A checagem que teria pego o incidente de julho (~40h de silêncio)."""

    def test_fila_parada_e_nada_processando_e_critico(self) -> None:
        a = checar_worker_mudo(minutos_sem_done=45, fila_esperando=12)
        assert a is not None
        assert a.severidade == CRITICO
        assert "12" in a.evidencia and "45" in a.evidencia

    def test_fila_vazia_nao_acusa_nada(self) -> None:
        # Madrugada sem movimento: nada processando é o esperado, não falha.
        # Sem esta guarda a checagem gritaria todo dia de madrugada e viraria
        # ruído — e alerta que sempre dispara deixa de ser lido.
        assert checar_worker_mudo(minutos_sem_done=600, fila_esperando=0) is None

    def test_dentro_da_janela_nao_acusa(self) -> None:
        assert checar_worker_mudo(minutos_sem_done=29, fila_esperando=5) is None

    def test_na_borda_exata_acusa(self) -> None:
        assert checar_worker_mudo(minutos_sem_done=30, fila_esperando=1) is not None

    def test_sem_dado_nao_inventa(self) -> None:
        # "Não sei" tem que ser diferente de "está tudo bem".
        assert checar_worker_mudo(minutos_sem_done=None, fila_esperando=5) is None


class TestDisco:
    def test_abaixo_do_limiar_nao_acusa(self) -> None:
        assert checar_disco(79) is None

    def test_oitenta_e_um_e_atencao(self) -> None:
        # O valor real medido em produção hoje.
        a = checar_disco(81)
        assert a is not None and a.severidade == ATENCAO

    def test_noventa_e_critico(self) -> None:
        assert checar_disco(90).severidade == CRITICO

    def test_sem_dado_nao_acusa(self) -> None:
        assert checar_disco(None) is None


class TestBackup:
    def test_recente_nao_acusa(self) -> None:
        assert checar_backup(3) is None

    def test_folga_de_26h_cobre_o_atraso_do_timer(self) -> None:
        # A unit tem RandomizedDelaySec; 25h ainda é execução normal.
        assert checar_backup(25) is None

    def test_atrasado_e_critico(self) -> None:
        a = checar_backup(30)
        assert a is not None and a.severidade == CRITICO

    def test_sem_registro_e_critico_e_nao_silencioso(self) -> None:
        # Não conseguir LER o estado do backup é pior que backup atrasado:
        # é o caso em que ninguém descobre até precisar restaurar.
        a = checar_backup(None)
        assert a is not None and a.severidade == CRITICO


class TestBackupOffsite:
    """Nasceu do incidente de 2026-08-19: o host sumiu com dump e MinIO dentro."""

    def test_upload_recente_nao_acusa(self) -> None:
        assert checar_backup_offsite(5) is None

    def test_mesma_folga_do_backup_local(self) -> None:
        assert checar_backup_offsite(25) is None

    def test_parou_de_subir_e_critico(self) -> None:
        a = checar_backup_offsite(40)
        assert a is not None and a.severidade == CRITICO
        assert "40" in a.evidencia

    def test_sem_marcador_fica_em_silencio(self) -> None:
        # Diferente do backup local: aqui `None` significa "cópia externa não
        # configurada". Alarmar todo dia por feature desligada treina quem lê a
        # ignorar o relatório inteiro.
        assert checar_backup_offsite(None) is None


class TestMigrations:
    """Nasceu de um caso real: a 153 aplicada em dev e ausente do repositório."""

    def test_iguais_nao_acusam(self) -> None:
        assert checar_migrations(["001.sql", "002.sql"], ["001.sql", "002.sql"]) is None

    def test_ordem_diferente_nao_acusa(self) -> None:
        assert checar_migrations(["002.sql", "001.sql"], ["001.sql", "002.sql"]) is None

    def test_falta_aplicar_e_atencao(self) -> None:
        a = checar_migrations(["001.sql", "173.sql"], ["001.sql"])
        assert a is not None
        assert a.severidade == ATENCAO
        assert "173.sql" in a.evidencia

    def test_aplicada_sem_arquivo_e_critico(self) -> None:
        # É o caso da 153: o banco tem uma restrição que o código não declara,
        # então nenhum ambiente novo reproduz o estado.
        a = checar_migrations(["001.sql"], ["001.sql", "153_drop_twilio.sql"])
        assert a is not None
        assert a.severidade == CRITICO
        assert "153_drop_twilio.sql" in a.evidencia

    def test_divergencia_nos_dois_sentidos_reporta_as_duas(self) -> None:
        a = checar_migrations(["001.sql", "173.sql"], ["001.sql", "153.sql"])
        assert "173.sql" in a.evidencia and "153.sql" in a.evidencia
        assert a.severidade == CRITICO


class TestConjunto:
    def test_sem_problemas_devolve_lista_vazia_e_ok(self) -> None:
        achados = rodar_checagens(
            {
                "minutos_sem_done": 2,
                "fila_esperando": 0,
                "disco_pct": 40,
                "backup_horas": 5,
                "migrations_arquivos": ["001.sql"],
                "migrations_aplicadas": ["001.sql"],
            }
        )
        assert achados == []
        assert severidade_geral(achados) == OK

    def test_coleta_vazia_nao_quebra(self) -> None:
        # Coleta parcial acontece (timeout de `docker`, host sem `df`). O
        # relatório precisa sair mesmo assim.
        achados = rodar_checagens({})
        # Só o backup acusa, porque não conseguir ler o estado dele é achado.
        assert [a.chave for a in achados] == ["backup"]

    def test_ordena_critico_antes_de_atencao(self) -> None:
        achados = rodar_checagens(
            {
                "minutos_sem_done": 1,
                "fila_esperando": 0,
                "disco_pct": 82,  # atenção
                "backup_horas": 40,  # crítico
                "migrations_arquivos": [],
                "migrations_aplicadas": [],
            }
        )
        assert [a.severidade for a in achados] == [CRITICO, ATENCAO]

    def test_severidade_geral_e_a_do_pior(self) -> None:
        achados = rodar_checagens({"disco_pct": 82, "backup_horas": 1})
        assert severidade_geral(achados) == ATENCAO

    def test_relatorio_sai_sem_llm(self) -> None:
        # É o contrato que garante que o alerta não depende do modelo: se a
        # chave faltar ou o OpenRouter cair, o texto sai assim.
        achados = rodar_checagens({"disco_pct": 95, "backup_horas": 1})
        texto = resumo_texto(achados)
        assert "CRITICO" in texto
        assert "95" in texto
        assert "ação:" in texto

    def test_texto_sem_achados_diz_que_nao_achou(self) -> None:
        assert "Nenhum problema" in resumo_texto([])


class TestDollarQuote:
    """O empacotamento do SQL do script do host.

    Vale testar apesar de o módulo ser de operação: este código roda como root
    no host, com psql superusuário, e recebe o texto ESCRITO PELO MODELO mais
    mensagens de erro cujo conteúdo pode vir do que um cliente mandou.
    """

    @staticmethod
    def _quote(valor):
        import importlib.util

        caminho = _SCRIPTS / "analise_producao.py"
        spec = importlib.util.spec_from_file_location("analise_producao", caminho)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod._dollar_quote(valor)

    def test_texto_comum_usa_a_tag_padrao(self) -> None:
        assert self._quote("olá") == "$rel$olá$rel$"

    def test_valor_vazio_e_none_viram_string_vazia(self) -> None:
        assert self._quote("") == "$rel$$rel$"
        assert self._quote(None) == "$rel$$rel$"

    def test_conteudo_com_a_tag_padrao_nao_encerra_o_literal(self) -> None:
        # A tentativa de injeção: fechar o literal e emendar SQL.
        malicioso = "x$rel$; DROP TABLE relatorio_producao; --"
        saida = self._quote(malicioso)
        # A tag escolhida não pode aparecer no meio do conteúdo, senão o
        # Postgres encerraria o literal ali.
        tag = saida[: saida.index("$", 1) + 1]
        assert saida.count(tag) == 2
        assert saida.startswith(tag) and saida.endswith(tag)
        assert malicioso in saida

    def test_escala_para_varias_tags_ocupadas(self) -> None:
        malicioso = "$rel$ $rel1$ $rel2$ fim"
        saida = self._quote(malicioso)
        tag = saida[: saida.index("$", 1) + 1]
        assert saida.count(tag) == 2
        assert malicioso in saida


class TestGraphApiVersion:
    """Versão da Graph API tem data de morte anunciada com 2 anos.

    Quando cai, todo envio e todo webhook do WhatsApp oficial param juntos — e
    o aviso está num changelog que ninguém relê.
    """

    def test_data_distante_nao_acusa(self) -> None:
        assert checar_graph_api_version("v25.0", "2026-08-21") is None

    def test_noventa_dias_antes_vira_atencao(self) -> None:
        # v22.0 morre em 2027-05-20; 60 dias antes.
        a = checar_graph_api_version("v22.0", "2027-03-21")
        assert a is not None and a.severidade == ATENCAO
        assert "2027-05-20" in a.evidencia

    def test_depois_do_sunset_e_critico(self) -> None:
        a = checar_graph_api_version("v20.0", "2026-10-01")
        assert a is not None and a.severidade == CRITICO
        assert "fora do ar" in a.titulo

    def test_versao_nao_configurada_fica_em_silencio(self) -> None:
        # WABA desligado: não existe versão para vencer.
        assert checar_graph_api_version("", "2026-08-21") is None
        assert checar_graph_api_version(None, "2026-08-21") is None

    def test_versao_mais_nova_que_a_tabela_nao_alarma(self) -> None:
        # Quem subiu para uma versão que este módulo ainda não conhece sabe o
        # que fez; alarmar seria ruído.
        assert checar_graph_api_version("v26.0", "2026-08-21") is None

    def test_data_ilegivel_nao_quebra(self) -> None:
        assert checar_graph_api_version("v25.0", "ontem") is None


class TestLinhaBackup:
    """A linha que prova que o backup RODOU — não só que falhou.

    As checagens só falam quando algo quebra, então backup saudável era
    silêncio: o dono perguntou "não vi o backup rodando" com ele rodando havia
    dias e subindo para o Drive.
    """

    BASE = {
        "backup_arquivo": "prod-2026-08-21.dump.zst",
        "backup_arquivo_hora": "03:18",
        "backup_arquivo_tamanho": "2,1M",
    }

    def test_backup_do_dia_com_copia_externa(self) -> None:
        linha = linha_backup(dict(self.BASE, backup_offsite_horas=2))
        assert "prod-2026-08-21.dump.zst" in linha
        assert "03:18" in linha
        assert "2,1M" in linha
        assert "Drive" in linha

    def test_sem_copia_externa_configurada_diz_isso(self) -> None:
        linha = linha_backup(dict(self.BASE, backup_offsite_horas=None))
        assert "só neste host" in linha

    def test_upload_atrasado_aparece_na_linha(self) -> None:
        linha = linha_backup(dict(self.BASE, backup_offsite_horas=40))
        assert "NAO subiu" in linha and "40h" in linha

    def test_sem_arquivo_nenhum_e_explicito(self) -> None:
        assert "sem arquivo" in linha_backup({})


class TestChecarIaAlertas:
    def test_sem_alertas_nao_acha_nada(self) -> None:
        assert checar_ia_alertas(0) is None
        assert checar_ia_alertas(None) is None

    def test_alerta_vivo_vira_achado_atencao(self) -> None:
        achado = checar_ia_alertas(
            2, "uptime google/gemini-2.5-flash; latencia openai/gpt-audio-mini"
        )
        assert achado is not None
        assert achado.severidade == ATENCAO
        assert "2" in achado.titulo
        assert "uptime google/gemini-2.5-flash" in achado.evidencia

    def test_sem_resumo_aponta_o_painel(self) -> None:
        achado = checar_ia_alertas(1, None)
        assert achado is not None
        assert "Catalogo OpenRouter" in achado.evidencia

    def test_entra_no_rodar_checagens(self) -> None:
        achados = rodar_checagens({"ia_alertas_ativos": 1})
        assert any(a.chave == "ia_alertas" for a in achados)


class TestChecarConexoesClientes:
    """Mig 196 — o que teria aparecido no relatório de 17/09 se existisse."""

    def test_sem_episodio_nao_acha_nada(self) -> None:
        assert checar_conexoes_clientes(0, 0) is None
        assert checar_conexoes_clientes(None, None) is None

    def test_conexao_caida_e_critico(self) -> None:
        achado = checar_conexoes_clientes(
            1, 0, "Luis Fernando Macorini (1018) conexao_caida"
        )
        assert achado is not None
        assert achado.severidade == CRITICO
        assert "1 conexao(oes) caida(s)" in achado.titulo
        assert "1018" in achado.evidencia
        assert "/monitor/conexoes" in achado.acao

    def test_silencio_nao_pesa(self) -> None:
        """mig 198: silêncio não é alerta (38 silêncios ≥ 1 h/mês saudáveis na
        VSA) — só conexão caída entra no relatório."""
        assert checar_conexoes_clientes(0, 2) is None
        achado = checar_conexoes_clientes(1, 2)
        assert achado is not None and achado.severidade == CRITICO
        assert "sem mensagens" not in achado.titulo

    def test_monitor_parado(self) -> None:
        assert checar_monitor_conexoes_parado(None) is None
        assert checar_monitor_conexoes_parado(5) is None
        achado = checar_monitor_conexoes_parado(25)
        assert achado is not None
        assert achado.severidade == ATENCAO
        assert "25 min" in achado.titulo

    def test_entra_no_rodar_checagens(self) -> None:
        achados = rodar_checagens({"conexoes_caidas": 1, "monitor_conexoes_min": 30})
        chaves = {a.chave for a in achados}
        assert {"conexoes_clientes", "monitor_conexoes_parado"} <= chaves


class TestSaldoOpenRouter:
    """A checagem que teria pego o incidente de 2026-09-10.

    O cliente mandou áudio e ouviu "estamos com dificuldades em processar
    imagens/audio" por mais de uma hora. Nada alarmou: o teto DA CHAVE (US$ 5)
    tinha esgotado enquanto a conta ainda tinha US$ 11,98.
    """

    def test_numeros_reais_do_incidente_sao_criticos(self) -> None:
        a = checar_saldo_openrouter(0.4154, 5, "chave")
        assert a is not None
        assert a.severidade == "critico"
        assert a.chave == "openrouter_saldo"

    def test_manda_arrumar_o_TETO_quando_o_limite_e_da_chave(self) -> None:
        """Distinção que custou a investigação: mandar comprar crédito quando o
        problema é o teto da chave não conserta nada — havia US$ 11,98 na conta."""
        a = checar_saldo_openrouter(0.4154, 5, "chave")
        assert a is not None
        assert "openrouter.ai/settings/keys" in a.acao
        assert "credits" not in a.acao

    def test_manda_comprar_credito_quando_o_limite_e_da_conta(self) -> None:
        a = checar_saldo_openrouter(0.80, 25, "conta")
        assert a is not None
        assert "credits" in a.acao

    def test_depois_do_conserto_cala(self) -> None:
        assert checar_saldo_openrouter(5.3821, 10, "chave") is None

    def test_avisa_antes_de_doer(self) -> None:
        a = checar_saldo_openrouter(1.50, 10, "chave")
        assert a is not None
        assert a.severidade == "atencao"

    def test_sem_dado_fica_em_silencio(self) -> None:
        """Chave sem teto ou API fora do ar é "não sei", não "está tudo bem" —
        mesmo contrato do backup offsite."""
        assert checar_saldo_openrouter(None) is None
        assert checar_saldo_openrouter(None, None, None) is None

    def test_sem_teto_conhecido_ainda_pega_o_critico(self) -> None:
        """Sem `teto` não dá pra calcular a faixa de atenção, mas o piso
        absoluto continua valendo — é o que dispara com a mídia já falhando."""
        assert checar_saldo_openrouter(0.40, None, "conta") is not None
        assert checar_saldo_openrouter(3.00, None, "conta") is None


class TestTamanhoTabela:
    """Fase 4 do plano dos checkpoints: o crescimento silencioso vira alarme."""

    def test_checkpoints_acima_de_2gb_e_critico(self) -> None:
        a = checar_tamanho_tabela(1885, "checkpoints")  # medido antes do conserto
        # 1885 MB fica na faixa de ATENÇÃO (>= 500), não CRÍTICO (>= 2000).
        assert a is not None
        assert a.severidade == ATENCAO
        assert "checkpoints" in a.evidencia and "1885" in a.evidencia

    def test_estouro_de_2gb_e_critico(self) -> None:
        a = checar_tamanho_tabela(2048, "checkpoints")
        assert a is not None
        assert a.severidade == CRITICO

    def test_abaixo_de_500mb_cala(self) -> None:
        assert checar_tamanho_tabela(90, "checkpoints") is None

    def test_sem_medida_fica_em_silencio(self) -> None:
        assert checar_tamanho_tabela(None, "checkpoints") is None

    def test_message_queue_tem_acao_propria(self) -> None:
        a = checar_tamanho_tabela(718, "message_queue")
        assert a is not None
        assert a.severidade == ATENCAO
        assert "message_queue" in a.acao and a.chave == "tamanho_message_queue"

    def test_checkpoints_aponta_a_retencao(self) -> None:
        a = checar_tamanho_tabela(600, "checkpoints")
        assert a is not None and "retenção" in a.acao.lower()

    def test_entra_no_rodar_checagens(self) -> None:
        achados = rodar_checagens({"checkpoints_mb": 2048, "message_queue_mb": 40})
        chaves = {x.chave for x in achados}
        assert "tamanho_checkpoints" in chaves
        assert "tamanho_message_queue" not in chaves  # 40 MB não alarma
