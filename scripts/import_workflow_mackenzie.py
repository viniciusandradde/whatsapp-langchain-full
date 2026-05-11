"""One-shot importer: cria 9 workflows do Hospital Mackenzie no DB.

Cobre o conjunto completo dos MDs Mackenzie (versionados em
`docs/mackenzie/1_*.md` a `9_*.md`):

- menu_principal: LGPD gate + nome + menu 8 setores (refs wf:menu_<setor>)
- menu_atendimento_cliente: quadro médico, guias, 2ª via (CPF+data_br), falar
- menu_agendamento: marcar, verificar, reagendar, cancelar, cardio
- menu_exames: agendar, resultados (link portal), orçamento, preparo, reagendar
- menu_tesouraria: pagamentos/2ª via, negociação, NF, estimativas, jurídico
- menu_orcamentos: cirurgia, urgência, status, dúvidas convênios
- menu_portaria: visitas+cadastro, localização, achados, PS
- menu_outras: manual, capelania, RH (auto-resp), atendente
- menu_ouvidoria: manifestação, denúncia, prontuário, protocolo

Validators BR aplicados onde os MDs pedem (cpf, data_br, telefone_br).

Uso:
    python scripts/import_workflow_mackenzie.py --empresa-id 1 [--ativo]

Idempotente: ON CONFLICT (empresa_id, slug) atualiza definicao + versao++.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.shared.db import close_pool, get_pool  # noqa: E402

# Workflow principal: boas-vindas → LGPD → nome → menu global 8 setores
MENU_PRINCIPAL = {
    "entry": "boas_vindas",
    "nodes": {
        "boas_vindas": {
            "type": "send_messages",
            "messages": [
                "Olá! Seja bem-vindo ao Hospital Presbiteriano Mackenzie - "
                "Dr. e Sra. Goldsby King.",
                "Sou seu assistente virtual e estou aqui para iniciar seu "
                "atendimento com agilidade.",
            ],
            "next": "lgpd_ask",
        },
        "lgpd_ask": {
            "type": "ask_choice",
            "prompt": (
                "Para continuarmos seu atendimento com segurança e "
                "transparência, precisamos do seu consentimento para "
                "tratamento de dados (LGPD).\n"
                "Política de Privacidade: https://bit.ly/3QJXkWw\n\n"
                "Você declara que leu e CONCORDA com os termos?"
            ),
            "choices": [
                {"label": "Sim, Li e Concordo", "value": "1", "next": "lgpd_log"},
                {
                    "label": "Não concordo / Sair",
                    "value": "2",
                    "next": "encerrar_lgpd_neg",
                },
            ],
            "retry_message": "Por favor, responda 1 ou 2.",
        },
        "lgpd_log": {
            "type": "audit_event",
            "evento": "lgpd_consented",
            "next": "ask_nome",
        },
        "ask_nome": {
            "type": "ask_text",
            "prompt": (
                "Obrigado pela confiança! "
                "Para agilizar, digite seu Nome Completo:"
            ),
            "save_as": "nome_cliente",
            "validate_with": "min_len:2",
            "retry_message": "Por favor, digite seu nome completo.",
            "next": "saudacao",
        },
        "saudacao": {
            "type": "send_messages",
            "messages": ["Seja bem-vindo, {{vars.nome_cliente}}!"],
            "next": "menu_global",
        },
        "menu_global": {
            "type": "ask_choice",
            "prompt": "Selecione o departamento com o qual deseja falar:",
            "choices": [
                {
                    "label": "Atendimento ao Cliente",
                    "value": "1",
                    "next": "wf:menu_atendimento_cliente",
                },
                {
                    "label": "Agendamentos",
                    "value": "2",
                    "next": "wf:menu_agendamento",
                },
                {
                    "label": "Exames e Diagnósticos",
                    "value": "3",
                    "next": "wf:menu_exames",
                },
                {
                    "label": "Tesouraria",
                    "value": "4",
                    "next": "wf:menu_tesouraria",
                },
                {
                    "label": "Orçamentos e Internação",
                    "value": "5",
                    "next": "wf:menu_orcamentos",
                },
                {
                    "label": "Portaria e Recepção",
                    "value": "6",
                    "next": "wf:menu_portaria",
                },
                {
                    "label": "Outras Informações",
                    "value": "7",
                    "next": "wf:menu_outras",
                },
                {
                    "label": "Ouvidoria",
                    "value": "8",
                    "next": "wf:menu_ouvidoria",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 8.",
        },
        "encerrar_lgpd_neg": {
            "type": "send_messages",
            "messages": [
                "Entendemos. Sem o aceite, não podemos prosseguir pelo "
                "canal digital. Agradecemos o contato!"
            ],
            "next": "__end__",
        },
    },
}


# Sub-workflow: Atendimento ao Cliente (5 opções)
MENU_ATENDIMENTO_CLIENTE = {
    "entry": "boas_vindas",
    "nodes": {
        "boas_vindas": {
            "type": "send_messages",
            "messages": [
                "Olá, {{vars.nome_cliente}}! Você está no atendimento digital "
                "do Hospital Mackenzie.",
            ],
            "next": "menu",
        },
        "menu": {
            "type": "ask_choice",
            "prompt": "Selecione como podemos te ajudar:",
            "choices": [
                {
                    "label": "Quadro Médico Plantonista 24h",
                    "value": "1",
                    "next": "quadro_medico",
                },
                {
                    "label": "Guia para Pacientes e Acompanhantes",
                    "value": "2",
                    "next": "guia_pacientes",
                },
                {"label": "Guia Maternidade", "value": "3", "next": "guia_maternidade"},
                {
                    "label": "Segunda Via de Documentos",
                    "value": "4",
                    "next": "ask_doc_medico",
                },
                {
                    "label": "Outras Orientações / Falar com Especialista",
                    "value": "5",
                    "next": "outras",
                },
            ],
            "retry_message": "Por favor, selecione 1 a 5.",
        },
        "quadro_medico": {
            "type": "send_messages",
            "messages": [
                "Especialidades com plantão 24h: *Clínico Geral*, *Pediatria* "
                "e *Obstetrícia*.",
                "Caso precise confirmar a escala de um médico específico, "
                "selecione a opção 5 do menu para falar com nossa equipe.",
            ],
            "next": "__end__",
        },
        "guia_pacientes": {
            "type": "send_link",
            "url": "https://bit.ly/3SWiqnC",
            "text": "Acesse nosso Guia para Pacientes e Acompanhantes:",
            "next": "__end__",
        },
        "guia_maternidade": {
            "type": "send_media",
            "url": "https://hospitalmackenzie.com.br/guias/maternidade.pdf",
            "content_type": "application/pdf",
            "caption": "Seu Guia Maternidade. Boa leitura, {{vars.nome_cliente}}!",
            "next": "__end__",
        },
        # 2ª Via: pergunta 4 dados (médico, data, motivo, CPF) + transbordo
        "ask_doc_medico": {
            "type": "ask_text",
            "prompt": (
                "Você se lembra o Nome do Médico ou a Especialidade "
                "(ex: Cardiologista) que te atendeu? Se não lembrar, "
                "responda 'Não lembro'."
            ),
            "save_as": "doc_nome_medico",
            "validate_with": "min_len:2",
            "next": "ask_doc_data",
        },
        "ask_doc_data": {
            "type": "ask_text",
            "prompt": (
                "Qual foi a data aproximada do atendimento ou por quanto "
                "tempo ficou internado?"
            ),
            "save_as": "doc_data_ref",
            "validate_with": "min_len:2",
            "next": "ask_doc_motivo",
        },
        "ask_doc_motivo": {
            "type": "ask_text",
            "prompt": (
                "O que houve com a 1ª via? (Ex: Esqueceu de pegar, perdeu, "
                "ou precisa para plano de saúde?)"
            ),
            "save_as": "doc_motivo",
            "validate_with": "min_len:2",
            "next": "ask_cpf",
        },
        "ask_cpf": {
            "type": "ask_text",
            "prompt": "Para finalizar, digite o CPF do paciente:",
            "save_as": "cpf_paciente",
            "validate_with": "cpf",
            "retry_message": "CPF inválido. Digite os 11 dígitos.",
            "next": "ask_data_nasc",
        },
        "ask_data_nasc": {
            "type": "ask_text",
            "prompt": "Agora, a Data de Nascimento (dd/mm/aaaa):",
            "save_as": "data_nascimento",
            "validate_with": "data_br",
            "retry_message": "Data inválida. Use o formato dd/mm/aaaa.",
            "next": "doc_handover",
        },
        "doc_handover": {
            "type": "handover",
            "resumo_template": (
                "2ª Via Documento | Cliente: {{vars.nome_cliente}} | "
                "Médico: {{vars.doc_nome_medico}} | "
                "Data ref: {{vars.doc_data_ref}} | "
                "Motivo: {{vars.doc_motivo}} | "
                "CPF: {{vars.cpf_paciente}} | "
                "Nasc: {{vars.data_nascimento}}"
            ),
            "message_to_client": (
                "Obrigado! Já passei tudo para a equipe administrativa. "
                "Aguarde um momento que um atendente vai confirmar a "
                "emissão do seu documento."
            ),
            "next": "__end__",
        },
        "outras": {
            "type": "ask_text",
            "prompt": (
                "Para ganhar tempo enquanto localizo um atendente livre, "
                "por favor, escreva em uma frase qual é sua dúvida ou "
                "necessidade."
            ),
            "save_as": "resumo_assunto",
            "validate_with": "min_len:5",
            "next": "outras_handover",
        },
        "outras_handover": {
            "type": "handover",
            "resumo_template": (
                "Falar com Especialista | Cliente: {{vars.nome_cliente}} | "
                "Assunto: {{vars.resumo_assunto}}"
            ),
            "message_to_client": (
                "Certo, anotei o motivo: '{{vars.resumo_assunto}}'. "
                "Você já está na nossa fila de prioridade. "
                "Aguarde um momento."
            ),
            "next": "__end__",
        },
    },
}


# ============================================================
# MENU AGENDAMENTO (3) — marcar/verificar/reagendar/cancelar/cardio
# ============================================================
MENU_AGENDAMENTO = {
    "entry": "boas_vindas",
    "nodes": {
        "boas_vindas": {
            "type": "send_messages",
            "messages": [
                "Você está na Central de Agendamentos do Hospital "
                "Presbiteriano Mackenzie - Dr. e Sra. Goldsby King.",
            ],
            "next": "menu",
        },
        "menu": {
            "type": "ask_choice",
            "prompt": "Selecione como podemos te ajudar:",
            "choices": [
                {"label": "Marcar Consulta", "value": "1", "next": "marcar_dados"},
                {
                    "label": "Verificar meu agendamento",
                    "value": "2",
                    "next": "verificar_cpf",
                },
                {
                    "label": "Reagendar ou Solicitar Encaixe",
                    "value": "3",
                    "next": "reagendar_cpf",
                },
                {"label": "Cancelar Consulta", "value": "4", "next": "cancelar_cpf"},
                {
                    "label": "Exames Cardiológicos",
                    "value": "5",
                    "next": "cardio_handover",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 5.",
        },
        # 1. Marcar
        "marcar_dados": {
            "type": "ask_text",
            "prompt": (
                "Certo! Para iniciarmos, digite o Nome Completo e a Data "
                "de Nascimento (DD/MM/AAAA) do PACIENTE que será consultado."
            ),
            "save_as": "marcar_paciente",
            "validate_with": "min_len:5",
            "next": "marcar_especialidade",
        },
        "marcar_especialidade": {
            "type": "ask_choice",
            "prompt": "Agora, selecione a Especialidade desejada:",
            "choices": [
                {"label": "Urologia", "value": "1", "next": "marcar_preferencia"},
                {"label": "Ortopedia", "value": "2", "next": "marcar_preferencia"},
                {"label": "Clínico-Geral", "value": "3", "next": "marcar_preferencia"},
                {"label": "Reumatologia", "value": "4", "next": "marcar_preferencia"},
                {"label": "Oncologia", "value": "5", "next": "marcar_preferencia"},
                {
                    "label": "Otorrinolaringologia",
                    "value": "6",
                    "next": "marcar_preferencia",
                },
                {
                    "label": "Exames/Cardiológicos",
                    "value": "7",
                    "next": "cardio_handover",
                },
                {
                    "label": "Gastroenterologia / Cirurgia Geral",
                    "value": "8",
                    "next": "marcar_preferencia",
                },
            ],
            "save_as": "especialidade",
            "retry_message": "Opção inválida. Selecione 1 a 8.",
        },
        "marcar_preferencia": {
            "type": "ask_text",
            "prompt": (
                "Você tem preferência por atendimento pela Manhã ou Tarde? "
                "(Ou digite o nome de um médico específico)."
            ),
            "save_as": "preferencia_horario",
            "validate_with": "min_len:2",
            "next": "marcar_handover",
        },
        "marcar_handover": {
            "type": "handover",
            "resumo_template": (
                "Marcar Consulta | Cliente: {{vars.nome_cliente}} | "
                "Paciente: {{vars.marcar_paciente}} | "
                "Especialidade: {{vars.especialidade}} | "
                "Preferência: {{vars.preferencia_horario}}"
            ),
            "message_to_client": (
                "Perfeito. Transferindo para a central... Um atendente vai "
                "verificar a disponibilidade mais próxima para "
                "{{vars.preferencia_horario}} e confirmar com você agora."
            ),
            "next": "__end__",
        },
        # 2. Verificar
        "verificar_cpf": {
            "type": "ask_text",
            "prompt": "Para localizar seu cadastro, digite o CPF do Paciente:",
            "save_as": "cpf_paciente",
            "validate_with": "cpf",
            "retry_message": "CPF inválido. Digite os 11 dígitos.",
            "next": "verificar_handover",
        },
        "verificar_handover": {
            "type": "handover",
            "resumo_template": (
                "Verificar Agendamento | Cliente: {{vars.nome_cliente}} | "
                "CPF: {{vars.cpf_paciente}}"
            ),
            "message_to_client": (
                "Localizando seu cadastro... Um atendente vai te informar "
                "os agendamentos ativos em instantes."
            ),
            "next": "__end__",
        },
        # 3. Reagendar/Encaixe
        "reagendar_cpf": {
            "type": "ask_text",
            "prompt": (
                "Entendido. Vamos ajustar sua agenda para o melhor momento. "
                "Para localizar seu cadastro, digite o CPF do Paciente:"
            ),
            "save_as": "cpf_paciente",
            "validate_with": "cpf",
            "retry_message": "CPF inválido. Digite os 11 dígitos.",
            "next": "reagendar_tipo",
        },
        "reagendar_tipo": {
            "type": "ask_choice",
            "prompt": "Qual é a sua necessidade atual?",
            "choices": [
                {
                    "label": "Reagendar (já tenho consulta, quero trocar a data)",
                    "value": "1",
                    "next": "reagendar_pref",
                },
                {
                    "label": "Solicitar Encaixe (preciso de horário urgente)",
                    "value": "2",
                    "next": "reagendar_alvo",
                },
            ],
            "save_as": "tipo_solicitacao_agenda",
        },
        "reagendar_pref": {
            "type": "ask_text",
            "prompt": (
                "Para qual dia da semana ou período (manhã/tarde) você "
                "prefere a nova data?"
            ),
            "save_as": "preferencia_nova_data",
            "validate_with": "min_len:3",
            "next": "reagendar_handover",
        },
        "reagendar_alvo": {
            "type": "ask_text",
            "prompt": (
                "Compreendo. Para qual Especialidade ou Médico você "
                "precisa desse encaixe urgente?"
            ),
            "save_as": "alvo_encaixe",
            "validate_with": "min_len:2",
            "next": "reagendar_handover",
        },
        "reagendar_handover": {
            "type": "handover",
            "resumo_template": (
                "{{vars.tipo_solicitacao_agenda}} | "
                "Cliente: {{vars.nome_cliente}} | CPF: {{vars.cpf_paciente}} | "
                "Detalhes: {{vars.preferencia_nova_data}}{{vars.alvo_encaixe}}"
            ),
            "message_to_client": (
                "Anotado. Um atendente vai verificar a disponibilidade e "
                "confirmar com você agora mesmo."
            ),
            "next": "__end__",
        },
        # 4. Cancelar
        "cancelar_cpf": {
            "type": "ask_text",
            "prompt": (
                "Poxa, sentimos muito que você não possa comparecer. "
                "Para darmos baixa no sistema, informe o CPF do Paciente:"
            ),
            "save_as": "cpf_paciente",
            "validate_with": "cpf",
            "retry_message": "CPF inválido. Digite os 11 dígitos.",
            "next": "cancelar_qual",
        },
        "cancelar_qual": {
            "type": "ask_text",
            "prompt": (
                "Qual consulta você deseja cancelar? "
                "(Ex: Cardiologista amanhã, ou Dr. João)."
            ),
            "save_as": "consulta_cancelar",
            "validate_with": "min_len:3",
            "next": "cancelar_motivo",
        },
        "cancelar_motivo": {
            "type": "ask_choice",
            "prompt": "Para nos ajudar a melhorar, qual o motivo do cancelamento?",
            "choices": [
                {
                    "label": "Imprevisto Pessoal",
                    "value": "1",
                    "next": "cancelar_handover",
                },
                {
                    "label": "Já resolvi o problema",
                    "value": "2",
                    "next": "cancelar_handover",
                },
                {
                    "label": "Atendimento demorado",
                    "value": "3",
                    "next": "cancelar_handover",
                },
                {"label": "Outros", "value": "4", "next": "cancelar_handover"},
            ],
            "save_as": "motivo_cancelamento",
        },
        "cancelar_handover": {
            "type": "handover",
            "resumo_template": (
                "Cancelar Consulta | Cliente: {{vars.nome_cliente}} | "
                "CPF: {{vars.cpf_paciente}} | "
                "Consulta: {{vars.consulta_cancelar}} | "
                "Motivo: {{vars.motivo_cancelamento}}"
            ),
            "message_to_client": (
                "Entendido. Estou encaminhando para a central liberar sua "
                "vaga imediatamente. Um atendente vai apenas confirmar a "
                "exclusão com você."
            ),
            "next": "__end__",
        },
        # 5. Cardio (transbordo direto)
        "cardio_handover": {
            "type": "handover",
            "resumo_template": (
                "Exames/Cardiologia | Cliente: {{vars.nome_cliente}} | "
                "Encaminhar para fila Exames/Cardiologia (setor exclusivo)"
            ),
            "message_to_client": (
                "Entendido. Para garantir um atendimento especializado, "
                "o agendamento de Cardiologia e Exames Cardiológicos é "
                "realizado por um setor exclusivo. Estou transferindo "
                "você agora mesmo. Aguarde um momento."
            ),
            "next": "__end__",
        },
    },
}


# ============================================================
# MENU EXAMES (4) — agendar/resultados/orçamento/preparo/reagendar
# ============================================================
MENU_EXAMES = {
    "entry": "boas_vindas",
    "nodes": {
        "boas_vindas": {
            "type": "send_messages",
            "messages": [
                "Você está na Central de Diagnósticos e Exames "
                "(Laboratório e Imagem).",
            ],
            "next": "menu",
        },
        "menu": {
            "type": "ask_choice",
            "prompt": "Para agilizar, selecione o assunto principal:",
            "choices": [
                {
                    "label": "Agendar Exames",
                    "value": "1",
                    "next": "agendar_paciente",
                },
                {
                    "label": "Resultados e Laudos",
                    "value": "2",
                    "next": "resultados_link",
                },
                {
                    "label": "Orçamentos e Valores",
                    "value": "3",
                    "next": "orcamento_exame",
                },
                {
                    "label": "Preparo e Orientações",
                    "value": "4",
                    "next": "preparo_exame",
                },
                {
                    "label": "Reagendar ou Cancelar",
                    "value": "5",
                    "next": "reagendar_cpf",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 5.",
        },
        # 1. Agendar
        "agendar_paciente": {
            "type": "ask_text",
            "prompt": (
                "Vamos iniciar seu agendamento. Primeiro, digite o "
                "Nome Completo do Paciente:"
            ),
            "save_as": "nome_paciente",
            "validate_with": "min_len:3",
            "next": "agendar_exame",
        },
        "agendar_exame": {
            "type": "ask_text",
            "prompt": (
                "Qual exame você precisa realizar? (Escreva o nome ou "
                "digite 'Vários' se tiver foto do pedido)."
            ),
            "save_as": "nome_exame",
            "validate_with": "min_len:2",
            "next": "agendar_modalidade",
        },
        "agendar_modalidade": {
            "type": "ask_choice",
            "prompt": "O atendimento será por qual modalidade?",
            "choices": [
                {
                    "label": "Convênio / Plano de Saúde",
                    "value": "1",
                    "next": "agendar_handover",
                },
                {
                    "label": "Particular / Pagamento Próprio",
                    "value": "2",
                    "next": "agendar_handover",
                },
            ],
            "save_as": "modalidade_pagamento",
        },
        "agendar_handover": {
            "type": "handover",
            "resumo_template": (
                "Agendar Exame | Paciente: {{vars.nome_paciente}} | "
                "Exame: {{vars.nome_exame}} | "
                "Modalidade: {{vars.modalidade_pagamento}}"
            ),
            "message_to_client": (
                "Entendido. Transferindo para a Central de Agendamento... "
                "Um atendente vai verificar a agenda e confirmar o horário "
                "do seu {{vars.nome_exame}} agora mesmo."
            ),
            "next": "__end__",
        },
        # 2. Resultados
        "resultados_link": {
            "type": "send_messages",
            "messages": [
                "Por questões de segurança e sigilo médico, seus resultados "
                "devem ser acessados exclusivamente pelo nosso Portal do "
                "Paciente.",
                "Acesse o link abaixo e digite o Login e Senha entregues "
                "na recepção no dia do seu exame: "
                "https://modulos.conectew.com.br/conecte/laudos/loginPaciente/view.jsf?edc=265",
            ],
            "next": "resultados_check",
        },
        "resultados_check": {
            "type": "ask_choice",
            "prompt": "Você conseguiu acessar seus resultados?",
            "choices": [
                {"label": "Sim, consegui", "value": "1", "next": "resultados_ok"},
                {
                    "label": "Não / Esqueci a Senha / Preciso de Ajuda",
                    "value": "2",
                    "next": "resultados_help_dados",
                },
            ],
        },
        "resultados_ok": {
            "type": "send_messages",
            "messages": [
                "Ótimo! Se precisar de mais alguma coisa, é só chamar. "
                "Tenha um bom dia!",
            ],
            "next": "__end__",
        },
        "resultados_help_dados": {
            "type": "ask_text",
            "prompt": (
                "Entendido. Vamos te ajudar a recuperar seu acesso. "
                "Por favor, digite o Nome Completo e o CPF do Paciente:"
            ),
            "save_as": "resultados_dados",
            "validate_with": "min_len:5",
            "next": "resultados_handover",
        },
        "resultados_handover": {
            "type": "handover",
            "resumo_template": (
                "Suporte Resultados | Cliente: {{vars.nome_cliente}} | "
                "Dados: {{vars.resultados_dados}} | "
                "AJUDAR NO LOGIN, NÃO ENVIAR ARQUIVO"
            ),
            "message_to_client": (
                "Um atendente vai verificar seu cadastro e te orientar "
                "sobre como redefinir sua senha ou retirar o exame "
                "presencialmente."
            ),
            "next": "__end__",
        },
        # 3. Orçamento
        "orcamento_exame": {
            "type": "ask_text",
            "prompt": (
                "Sem problemas. Vamos fazer uma cotação para você. "
                "Por favor, digite o Nome do Exame que deseja orçar:"
            ),
            "save_as": "pedido_orcamento",
            "validate_with": "min_len:2",
            "next": "orcamento_handover",
        },
        "orcamento_handover": {
            "type": "handover",
            "resumo_template": (
                "Orçamento Exame | Cliente: {{vars.nome_cliente}} | "
                "Exame: {{vars.pedido_orcamento}}"
            ),
            "message_to_client": (
                "Recebido. Nossa equipe financeira vai calcular o valor "
                "e te informar as formas de pagamento em instantes."
            ),
            "next": "__end__",
        },
        # 4. Preparo
        "preparo_exame": {
            "type": "ask_text",
            "prompt": (
                "Para garantir o sucesso do seu exame, o preparo correto "
                "é essencial. Para qual exame você precisa de instruções? "
                "(Ex: Ultrassom, Sangue, Tomografia)."
            ),
            "save_as": "exame_preparo",
            "validate_with": "min_len:2",
            "next": "preparo_handover",
        },
        "preparo_handover": {
            "type": "handover",
            "resumo_template": (
                "Preparo Exame | Cliente: {{vars.nome_cliente}} | "
                "Exame: {{vars.exame_preparo}}"
            ),
            "message_to_client": (
                "Certo. Estou acionando a equipe técnica para te passar o "
                "preparo exato do {{vars.exame_preparo}}."
            ),
            "next": "__end__",
        },
        # 5. Reagendar
        "reagendar_cpf": {
            "type": "ask_text",
            "prompt": "Entendido. Digite o CPF do Paciente:",
            "save_as": "cpf_paciente",
            "validate_with": "cpf",
            "retry_message": "CPF inválido. Digite os 11 dígitos.",
            "next": "reagendar_acao",
        },
        "reagendar_acao": {
            "type": "ask_choice",
            "prompt": "Qual é a sua necessidade?",
            "choices": [
                {
                    "label": "Reagendar (Trocar data)",
                    "value": "1",
                    "next": "reagendar_handover",
                },
                {
                    "label": "Cancelar Definitivamente",
                    "value": "2",
                    "next": "reagendar_handover",
                },
            ],
            "save_as": "acao_agenda",
        },
        "reagendar_handover": {
            "type": "handover",
            "resumo_template": (
                "Reagendar/Cancelar Exame | Cliente: {{vars.nome_cliente}} | "
                "CPF: {{vars.cpf_paciente}} | Ação: {{vars.acao_agenda}}"
            ),
            "message_to_client": (
                "Solicitação enviada. Um atendente vai confirmar a "
                "alteração na agenda."
            ),
            "next": "__end__",
        },
    },
}


# ============================================================
# MENU TESOURARIA (5) — pagamentos/negociação/NF/estimativas/jurídico
# ============================================================
MENU_TESOURARIA = {
    "entry": "menu",
    "nodes": {
        "menu": {
            "type": "ask_choice",
            "prompt": (
                "Você está na Tesouraria. Para assuntos financeiros, "
                "selecione uma opção:"
            ),
            "choices": [
                {
                    "label": "Pagamentos, 2ª Via e Pendências",
                    "value": "1",
                    "next": "pag_cpf",
                },
                {
                    "label": "Negociação e Parcelamentos",
                    "value": "2",
                    "next": "neg_pref",
                },
                {
                    "label": "Notas Fiscais e Reembolsos",
                    "value": "3",
                    "next": "nf_dados",
                },
                {
                    "label": "Estimativas e Orçamentos",
                    "value": "4",
                    "next": "est_tipo",
                },
                {
                    "label": "Assuntos Jurídicos e Risco Cirúrgico",
                    "value": "5",
                    "next": "jur_send",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 5.",
        },
        # 1. Pagamento/2via
        "pag_cpf": {
            "type": "ask_text",
            "prompt": (
                "Para localizar seus títulos em aberto, digite o CPF do "
                "Responsável Financeiro:"
            ),
            "save_as": "cpf_financeiro",
            "validate_with": "cpf",
            "retry_message": "CPF inválido. Digite os 11 dígitos.",
            "next": "pag_data",
        },
        "pag_data": {
            "type": "ask_text",
            "prompt": (
                "Confirme a Data de Nascimento do Paciente ou "
                "Responsável (DD/MM/AAAA):"
            ),
            "save_as": "data_nasc_fin",
            "validate_with": "data_br",
            "retry_message": "Data inválida. Use o formato dd/mm/aaaa.",
            "next": "pag_handover",
        },
        "pag_handover": {
            "type": "handover",
            "resumo_template": (
                "Pagamento/2ª Via | Cliente: {{vars.nome_cliente}} | "
                "CPF Financeiro: {{vars.cpf_financeiro}} | "
                "Nasc: {{vars.data_nasc_fin}}"
            ),
            "message_to_client": (
                "Encontrei seu cadastro. Um atendente vai te enviar o "
                "arquivo PDF (Boleto) ou o código Pix Copia-e-Cola agora "
                "mesmo."
            ),
            "next": "__end__",
        },
        # 2. Negociação
        "neg_pref": {
            "type": "ask_choice",
            "prompt": (
                "Vamos ajudar você a regularizar suas pendências. "
                "Como você prefere realizar o pagamento?"
            ),
            "choices": [
                {
                    "label": "Cartão de Crédito (Parcelado)",
                    "value": "1",
                    "next": "neg_handover",
                },
                {
                    "label": "À Vista (Pix/Dinheiro com desconto)",
                    "value": "2",
                    "next": "neg_handover",
                },
                {
                    "label": "Boleto (Entrada + Parcelas)",
                    "value": "3",
                    "next": "neg_handover",
                },
            ],
            "save_as": "preferencia_pagamento",
        },
        "neg_handover": {
            "type": "handover",
            "resumo_template": (
                "Negociação | Cliente: {{vars.nome_cliente}} | "
                "Preferência: {{vars.preferencia_pagamento}}"
            ),
            "message_to_client": (
                "Perfeito. Já registrei sua preferência por "
                "{{vars.preferencia_pagamento}}. Um analista vai verificar "
                "as condições disponíveis e te chamar em instantes."
            ),
            "next": "__end__",
        },
        # 3. NF
        "nf_dados": {
            "type": "ask_text",
            "prompt": (
                "Para emissão de Nota Fiscal ou Recibos, precisamos "
                "confirmar os dados. Por favor, digite o Nome Completo "
                "ou Razão Social para a nota:"
            ),
            "save_as": "dados_nota",
            "validate_with": "min_len:3",
            "next": "nf_doc",
        },
        "nf_doc": {
            "type": "ask_text",
            "prompt": "Agora, digite o CPF ou CNPJ:",
            "save_as": "doc_fiscal",
            "validate_with": "min_len:11",
            "retry_message": "Documento inválido. Digite o CPF (11) ou CNPJ (14).",
            "next": "nf_handover",
        },
        "nf_handover": {
            "type": "handover",
            "resumo_template": (
                "Nota Fiscal | Cliente: {{vars.nome_cliente}} | "
                "Razão: {{vars.dados_nota}} | Doc: {{vars.doc_fiscal}}"
            ),
            "message_to_client": (
                "Solicitação registrada. Nossa equipe enviará o documento "
                "para seu e-mail ou por aqui assim que emitido."
            ),
            "next": "__end__",
        },
        # 4. Estimativas
        "est_tipo": {
            "type": "ask_choice",
            "prompt": (
                "Você deseja saber os custos para Convênio "
                "(Carência/Coparticipação) ou Particular?"
            ),
            "choices": [
                {"label": "Particular", "value": "1", "next": "est_proc"},
                {"label": "Convênio", "value": "2", "next": "est_proc"},
            ],
            "save_as": "tipo_estimativa",
        },
        "est_proc": {
            "type": "ask_text",
            "prompt": "Qual procedimento ou cirurgia você deseja orçar?",
            "save_as": "procedimento_estimativa",
            "validate_with": "min_len:3",
            "next": "est_handover",
        },
        "est_handover": {
            "type": "handover",
            "resumo_template": (
                "Estimativa | Cliente: {{vars.nome_cliente}} | "
                "Tipo: {{vars.tipo_estimativa}} | "
                "Procedimento: {{vars.procedimento_estimativa}}"
            ),
            "message_to_client": (
                "Entendido. Transferindo para a equipe de orçamentos "
                "realizar o cálculo."
            ),
            "next": "__end__",
        },
        # 5. Jurídico
        "jur_send": {
            "type": "send_messages",
            "messages": [
                "Para análise de ofícios ou risco cirúrgico, precisamos "
                "do documento. Por favor, envie uma foto ou PDF do "
                "documento judicial/médico agora.",
            ],
            "next": "jur_handover",
        },
        "jur_handover": {
            "type": "handover",
            "resumo_template": (
                "Jurídico/Compliance | Cliente: {{vars.nome_cliente}} | "
                "AGUARDAR DOCUMENTO ENVIADO"
            ),
            "message_to_client": (
                "Documento será encaminhado para o departamento "
                "Jurídico/Compliance analisar."
            ),
            "next": "__end__",
        },
    },
}


# ============================================================
# MENU ORÇAMENTOS (6) — cirurgia/urgência/status/dúvidas
# ============================================================
MENU_ORCAMENTOS = {
    "entry": "boas_vindas",
    "nodes": {
        "boas_vindas": {
            "type": "send_messages",
            "messages": [
                "Você está na Central de Orçamentos e Internações.",
            ],
            "next": "menu",
        },
        "menu": {
            "type": "ask_choice",
            "prompt": "Para agilizar sua cotação, selecione o assunto:",
            "choices": [
                {
                    "label": "Orçamento de Cirurgias (Eletivos)",
                    "value": "1",
                    "next": "cir_paciente",
                },
                {
                    "label": "Valores de Urgência (Particular)",
                    "value": "2",
                    "next": "urg_aviso",
                },
                {
                    "label": "Acompanhar Status do Orçamento",
                    "value": "3",
                    "next": "status_cpf",
                },
                {
                    "label": "Dúvidas sobre Convênios e Prazos",
                    "value": "4",
                    "next": "duv_tipo",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 4.",
        },
        # 1. Cirurgia
        "cir_paciente": {
            "type": "ask_text",
            "prompt": (
                "Vamos iniciar seu processo de orçamento. Primeiro, digite "
                "o Nome Completo do Paciente:"
            ),
            "save_as": "nome_paciente",
            "validate_with": "min_len:3",
            "next": "cir_pedido",
        },
        "cir_pedido": {
            "type": "ask_text",
            "prompt": (
                "Para orçarmos corretamente, precisamos do pedido médico. "
                "Por favor, digite o nome do procedimento (e envie uma foto "
                "do pedido em seguida, se tiver)."
            ),
            "save_as": "pedido_medico",
            "validate_with": "min_len:3",
            "next": "cir_medico",
        },
        "cir_medico": {
            "type": "ask_text",
            "prompt": (
                "Qual é o nome do Médico solicitante ou Cirurgião? "
                "(Se não tiver médico definido, digite 'Sem médico')."
            ),
            "save_as": "nome_medico",
            "validate_with": "min_len:2",
            "next": "cir_pagador",
        },
        "cir_pagador": {
            "type": "ask_choice",
            "prompt": "O orçamento será via Convênio ou Particular?",
            "choices": [
                {
                    "label": "Convênio (informe o nome do plano ao atendente)",
                    "value": "1",
                    "next": "cir_handover",
                },
                {"label": "Particular", "value": "2", "next": "cir_handover"},
            ],
            "save_as": "tipo_pagamento",
        },
        "cir_handover": {
            "type": "handover",
            "resumo_template": (
                "Orçamento Cirurgia | Cliente: {{vars.nome_cliente}} | "
                "Paciente: {{vars.nome_paciente}} | "
                "Procedimento: {{vars.pedido_medico}} | "
                "Médico: {{vars.nome_medico}} | "
                "Pagamento: {{vars.tipo_pagamento}}"
            ),
            "message_to_client": (
                "Recebido. Encaminhei sua solicitação para a Central de "
                "Orçamentos. Nossa equipe fará a análise técnica "
                "(códigos TUSS/AMB) e retornará com os valores e "
                "autorizações necessárias."
            ),
            "next": "__end__",
        },
        # 2. Urgência
        "urg_aviso": {
            "type": "send_messages",
            "messages": [
                "Os valores de Urgência (Pronto Socorro) variam conforme a "
                "medicação e exames realizados no momento. No entanto, "
                "podemos passar uma estimativa de consulta e taxas iniciais.",
                "⚠️ Se for uma emergência médica grave, dirija-se "
                "diretamente ao nosso Pronto Socorro.",
            ],
            "next": "urg_contato",
        },
        "urg_contato": {
            "type": "ask_text",
            "prompt": "Por favor, digite seu Nome e Telefone:",
            "save_as": "contato_urgencia",
            "validate_with": "min_len:5",
            "next": "urg_handover",
        },
        "urg_handover": {
            "type": "handover",
            "resumo_template": (
                "Urgência Particular | Cliente: {{vars.nome_cliente}} | "
                "Contato: {{vars.contato_urgencia}}"
            ),
            "message_to_client": (
                "Registrado. Um atendente do financeiro vai entrar em "
                "contato para passar a tabela de valores vigente."
            ),
            "next": "__end__",
        },
        # 3. Status
        "status_cpf": {
            "type": "ask_text",
            "prompt": "Para verificar o andamento, digite o CPF do Paciente:",
            "save_as": "cpf_paciente",
            "validate_with": "cpf",
            "retry_message": "CPF inválido. Digite os 11 dígitos.",
            "next": "status_protocolo",
        },
        "status_protocolo": {
            "type": "ask_text",
            "prompt": (
                "Se você já tem um Número de Protocolo, digite abaixo "
                "(ou 'Não tenho'):"
            ),
            "save_as": "protocolo_orcamento",
            "validate_with": "min_len:1",
            "next": "status_handover",
        },
        "status_handover": {
            "type": "handover",
            "resumo_template": (
                "Status Orçamento | Cliente: {{vars.nome_cliente}} | "
                "CPF: {{vars.cpf_paciente}} | "
                "Protocolo: {{vars.protocolo_orcamento}}"
            ),
            "message_to_client": (
                "Localizando... Um analista vai te informar em que etapa "
                "está sua liberação (Análise, Auditoria ou Liberado)."
            ),
            "next": "__end__",
        },
        # 4. Dúvidas
        "duv_tipo": {
            "type": "ask_choice",
            "prompt": "Qual é a sua dúvida específica?",
            "choices": [
                {
                    "label": "Quais Convênios atendemos",
                    "value": "1",
                    "next": "duv_handover",
                },
                {
                    "label": "Formas de Pagamento (Particular)",
                    "value": "2",
                    "next": "duv_handover",
                },
                {
                    "label": "Prazo de validade do Orçamento",
                    "value": "3",
                    "next": "duv_handover",
                },
            ],
            "save_as": "duvida_financeira",
        },
        "duv_handover": {
            "type": "handover",
            "resumo_template": (
                "Dúvidas Financeiras | Cliente: {{vars.nome_cliente}} | "
                "Tipo: {{vars.duvida_financeira}}"
            ),
            "message_to_client": (
                "Certo. Um atendente vai te passar as regras atualizadas "
                "sobre {{vars.duvida_financeira}}."
            ),
            "next": "__end__",
        },
    },
}


# ============================================================
# MENU PORTARIA (7) — visitas/localização/achados/PS
# ============================================================
MENU_PORTARIA = {
    "entry": "menu",
    "nodes": {
        "menu": {
            "type": "ask_choice",
            "prompt": (
                "Você está na Portaria e Recepção Central. "
                "Selecione o assunto:"
            ),
            "choices": [
                {
                    "label": "Visitas, Acompanhantes e Regras de Acesso",
                    "value": "1",
                    "next": "vis_link",
                },
                {
                    "label": "Localização e Estacionamento",
                    "value": "2",
                    "next": "loc_info",
                },
                {
                    "label": "Achados e Perdidos",
                    "value": "3",
                    "next": "ach_descr",
                },
                {
                    "label": "Chegada ao Pronto Socorro (Urgência)",
                    "value": "4",
                    "next": "ps_aviso",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 4.",
        },
        # 1. Visitas
        "vis_link": {
            "type": "send_messages",
            "messages": [
                "Para garantir a segurança e o bem-estar dos pacientes, "
                "seguimos regras estritas de visitação (horários, "
                "vestimenta e itens permitidos).",
                "Acesse o Manual Completo: "
                "https://hospitalmackenzie.com.br/visitantes",
            ],
            "next": "vis_cad",
        },
        "vis_cad": {
            "type": "ask_choice",
            "prompt": (
                "Deseja adiantar seu cadastro de visitante para agilizar "
                "sua entrada?"
            ),
            "choices": [
                {"label": "Sim, quero adiantar", "value": "1", "next": "vis_paciente"},
                {
                    "label": "Não, já tenho cadastro / Só queria o link",
                    "value": "2",
                    "next": "vis_fim_so_link",
                },
            ],
        },
        "vis_paciente": {
            "type": "ask_text",
            "prompt": "Ótimo. Digite o Nome do Paciente que você irá visitar:",
            "save_as": "nome_paciente_visita",
            "validate_with": "min_len:3",
            "next": "vis_parentesco",
        },
        "vis_parentesco": {
            "type": "ask_text",
            "prompt": "Qual seu grau de parentesco? (Ex: Pai, Filho, Amigo):",
            "save_as": "parentesco_visita",
            "validate_with": "min_len:2",
            "next": "vis_fim",
        },
        "vis_fim": {
            "type": "send_messages",
            "messages": [
                "Cadastro prévio iniciado! Apresente seu documento na "
                "recepção para retirar o crachá.",
            ],
            "next": "__end__",
        },
        "vis_fim_so_link": {
            "type": "send_messages",
            "messages": ["Perfeito! Até breve."],
            "next": "__end__",
        },
        # 2. Localização
        "loc_info": {
            "type": "send_messages",
            "messages": [
                "📍 Estamos localizados na Rua Hilda Bergo Duarte, 81 - "
                "Centro, Dourados/MS.",
                "🚗 Sobre Estacionamento: Não dispomos de estacionamento "
                "privativo. Recomendamos estacionar nas vias laterais ou "
                "estacionamentos rotativos próximos.",
            ],
            "next": "__end__",
        },
        # 3. Achados
        "ach_descr": {
            "type": "ask_text",
            "prompt": (
                "Sentimos muito pelo ocorrido. Vamos registrar. "
                "O que foi perdido? (Descreva cor, marca, modelo):"
            ),
            "save_as": "descricao_objeto",
            "validate_with": "min_len:3",
            "next": "ach_local",
        },
        "ach_local": {
            "type": "ask_text",
            "prompt": (
                "Onde e quando você acha que perdeu? "
                "(Ex: Recepção, ontem à tarde):"
            ),
            "save_as": "local_perda",
            "validate_with": "min_len:3",
            "next": "ach_contato",
        },
        "ach_contato": {
            "type": "ask_text",
            "prompt": "Qual telefone podemos contatar caso encontremos?",
            "save_as": "contato_retorno",
            "validate_with": "telefone_br",
            "retry_message": "Telefone inválido. Use DDD + número.",
            "next": "ach_handover",
        },
        "ach_handover": {
            "type": "handover",
            "resumo_template": (
                "Achados/Perdidos | Cliente: {{vars.nome_cliente}} | "
                "Objeto: {{vars.descricao_objeto}} | "
                "Local: {{vars.local_perda}} | "
                "Contato: {{vars.contato_retorno}}"
            ),
            "message_to_client": (
                "Registro criado. Se o item for entregue na recepção, "
                "entraremos em contato."
            ),
            "next": "__end__",
        },
        # 4. PS
        "ps_aviso": {
            "type": "send_messages",
            "messages": [
                "⚠️ Atenção: Se esta é uma emergência médica, NÃO aguarde "
                "atendimento por aqui.",
                "Dirija-se imediatamente à Entrada de Emergência "
                "(Lateral Esquerda).",
            ],
            "next": "__end__",
        },
    },
}


# ============================================================
# MENU OUTRAS INFORMAÇÕES (8) — manual/capelania/RH/atendente
# ============================================================
MENU_OUTRAS = {
    "entry": "menu",
    "nodes": {
        "menu": {
            "type": "ask_choice",
            "prompt": (
                "Você está no Menu de Informações Institucionais. "
                "Selecione o assunto:"
            ),
            "choices": [
                {
                    "label": "Manual do Paciente e Visitante",
                    "value": "1",
                    "next": "manual_link",
                },
                {
                    "label": "Capelania e Apoio Espiritual",
                    "value": "2",
                    "next": "cap_tipo",
                },
                {
                    "label": "Trabalhe Conosco (Currículo)",
                    "value": "3",
                    "next": "rh_resp",
                },
                {
                    "label": "Falar com Atendente (Outros)",
                    "value": "4",
                    "next": "atend_aviso",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 4.",
        },
        # 1. Manual
        "manual_link": {
            "type": "send_messages",
            "messages": [
                "Para consultar as regras de visitas, itens permitidos na "
                "internação e direitos do paciente, acesse nosso Manual "
                "Digital: https://hospitalmackenzie.com.br/manual",
            ],
            "next": "__end__",
        },
        # 2. Capelania
        "cap_tipo": {
            "type": "ask_choice",
            "prompt": (
                "O Hospital Presbiteriano preza pelo cuidado integral. "
                "Como podemos ajudar?"
            ),
            "choices": [
                {
                    "label": "Solicitar Visita do Capelão (Presencial)",
                    "value": "1",
                    "next": "cap_dados",
                },
                {
                    "label": "Deixar um Pedido de Oração",
                    "value": "2",
                    "next": "cap_oracao",
                },
            ],
            "save_as": "tipo_capelania",
        },
        "cap_dados": {
            "type": "ask_text",
            "prompt": (
                "Para qual paciente (nome e quarto) você solicita a "
                "visita?"
            ),
            "save_as": "solicitacao_capelania",
            "validate_with": "min_len:3",
            "next": "cap_handover",
        },
        "cap_oracao": {
            "type": "ask_text",
            "prompt": "Por favor, escreva seu pedido de oração:",
            "save_as": "solicitacao_capelania",
            "validate_with": "min_len:5",
            "next": "cap_handover",
        },
        "cap_handover": {
            "type": "handover",
            "resumo_template": (
                "Capelania | Cliente: {{vars.nome_cliente}} | "
                "Tipo: {{vars.tipo_capelania}} | "
                "Pedido: {{vars.solicitacao_capelania}}"
            ),
            "message_to_client": (
                "Pedido registrado. Enviaremos ao pastor responsável "
                "pelo setor."
            ),
            "next": "__end__",
        },
        # 3. RH (auto-resposta)
        "rh_resp": {
            "type": "send_messages",
            "messages": [
                "Ficamos felizes com seu interesse em fazer parte da nossa "
                "equipe!",
                "Neste canal, não recebemos arquivos de currículo. Por "
                "favor, cadastre-se em nosso banco de talentos no site ou "
                "envie para o e-mail oficial: rh@hospitalmackenzie.com.br",
                "Boa sorte! Esperamos te ver em breve.",
            ],
            "next": "__end__",
        },
        # 4. Atendente
        "atend_aviso": {
            "type": "send_messages",
            "messages": [
                "Vamos te conectar a um especialista. Mas antes, uma "
                "confirmação importante: se o seu assunto for Agendamento "
                "ou Resultado de Exame, por favor volte ao menu principal "
                "para ser atendido mais rápido.",
            ],
            "next": "atend_resumo",
        },
        "atend_resumo": {
            "type": "ask_text",
            "prompt": (
                "Se for outro assunto, escreva abaixo em poucas palavras "
                "o que você precisa:"
            ),
            "save_as": "resumo_outros",
            "validate_with": "min_len:5",
            "next": "atend_handover",
        },
        "atend_handover": {
            "type": "handover",
            "resumo_template": (
                "Outros Assuntos | Cliente: {{vars.nome_cliente}} | "
                "Observação: {{vars.resumo_outros}}"
            ),
            "message_to_client": (
                "Entendido. Estou transferindo você para a Central de "
                "Apoio Administrativo com a observação: "
                "{{vars.resumo_outros}}."
            ),
            "next": "__end__",
        },
    },
}


# ============================================================
# MENU OUVIDORIA (9) — manifestação/denúncia/prontuário/protocolo
# ============================================================
MENU_OUVIDORIA = {
    "entry": "menu",
    "nodes": {
        "menu": {
            "type": "ask_choice",
            "prompt": (
                "Você está na Ouvidoria. Este é o canal oficial para nos "
                "ouvir. Selecione a opção:"
            ),
            "choices": [
                {
                    "label": "Reclamação, Elogio ou Sugestão",
                    "value": "1",
                    "next": "manif_tipo",
                },
                {
                    "label": "Canal de Denúncia (Sigilo/Ética)",
                    "value": "2",
                    "next": "den_tipo",
                },
                {
                    "label": "Solicitar Cópia de Prontuário Médico",
                    "value": "3",
                    "next": "pron_solicitante",
                },
                {
                    "label": "Consultar Andamento de Protocolo",
                    "value": "4",
                    "next": "prot_num",
                },
            ],
            "retry_message": "Opção inválida. Selecione 1 a 4.",
        },
        # 1. Manifestação
        "manif_tipo": {
            "type": "ask_choice",
            "prompt": "Queremos muito saber sua opinião. Do que se trata?",
            "choices": [
                {
                    "label": "Reclamação / Insatisfação",
                    "value": "1",
                    "next": "manif_relato_recl",
                },
                {"label": "Elogio", "value": "2", "next": "manif_relato_elog"},
                {"label": "Sugestão", "value": "3", "next": "manif_relato_sug"},
            ],
            "save_as": "tipo_manifestacao",
        },
        "manif_relato_recl": {
            "type": "ask_text",
            "prompt": (
                "Sinto muito que sua experiência não tenha sido a ideal. "
                "Vamos apurar o ocorrido. Por favor, descreva o que "
                "aconteceu (informe data, setor e nomes se souber):"
            ),
            "save_as": "relato_ouvidoria",
            "validate_with": "min_len:10",
            "next": "manif_handover",
        },
        "manif_relato_elog": {
            "type": "ask_text",
            "prompt": (
                "Que notícia ótima! Ficamos felizes em saber. "
                "Quem ou qual setor você gostaria de elogiar?"
            ),
            "save_as": "relato_ouvidoria",
            "validate_with": "min_len:5",
            "next": "manif_handover",
        },
        "manif_relato_sug": {
            "type": "ask_text",
            "prompt": "Pode mandar! Qual sua sugestão?",
            "save_as": "relato_ouvidoria",
            "validate_with": "min_len:5",
            "next": "manif_handover",
        },
        "manif_handover": {
            "type": "handover",
            "resumo_template": (
                "Ouvidoria - {{vars.tipo_manifestacao}} | "
                "Cliente: {{vars.nome_cliente}} | "
                "Relato: {{vars.relato_ouvidoria}}"
            ),
            "message_to_client": (
                "Registrado. Encaminharemos para a gestão responsável e "
                "você receberá um número de protocolo em breve."
            ),
            "next": "__end__",
        },
        # 2. Denúncia
        "den_tipo": {
            "type": "ask_choice",
            "prompt": (
                "Este canal é seguro e segue as diretrizes de Compliance. "
                "Você deseja se identificar ou prefere fazer uma denúncia "
                "anônima?"
            ),
            "choices": [
                {"label": "Quero me Identificar", "value": "1", "next": "den_relato"},
                {"label": "Quero Anonimato", "value": "2", "next": "den_relato"},
            ],
            "save_as": "tipo_denuncia",
        },
        "den_relato": {
            "type": "ask_text",
            "prompt": (
                "Pode relatar o fato. Se tiver provas (fotos/documentos), "
                "poderá enviar em seguida."
            ),
            "save_as": "relato_denuncia",
            "validate_with": "min_len:10",
            "next": "den_handover",
        },
        "den_handover": {
            "type": "handover",
            "resumo_template": (
                "Denúncia/Ética | Tipo: {{vars.tipo_denuncia}} | "
                "Relato: {{vars.relato_denuncia}}"
            ),
            "message_to_client": (
                "Sua denúncia foi recebida e será tratada pelo Comitê de "
                "Ética com total confidencialidade."
            ),
            "next": "__end__",
        },
        # 3. Prontuário
        "pron_solicitante": {
            "type": "ask_choice",
            "prompt": (
                "O Prontuário é um documento sigiloso. Quem está "
                "solicitando?"
            ),
            "choices": [
                {
                    "label": "Sou o Próprio Paciente",
                    "value": "1",
                    "next": "pron_dados",
                },
                {
                    "label": "Sou Responsável Legal / Parente",
                    "value": "2",
                    "next": "pron_dados",
                },
            ],
            "save_as": "tipo_solicitante",
        },
        "pron_dados": {
            "type": "ask_text",
            "prompt": (
                "Digite o Nome Completo do Paciente e a Data de "
                "Nascimento:"
            ),
            "save_as": "dados_paciente_prontuario",
            "validate_with": "min_len:5",
            "next": "pron_formato",
        },
        "pron_formato": {
            "type": "ask_choice",
            "prompt": (
                "Você prefere receber o arquivo digital (PDF por e-mail) "
                "ou retirar a cópia física?"
            ),
            "choices": [
                {"label": "Digital (E-mail)", "value": "1", "next": "pron_handover"},
                {"label": "Físico (Impresso)", "value": "2", "next": "pron_handover"},
            ],
            "save_as": "formato_prontuario",
        },
        "pron_handover": {
            "type": "handover",
            "resumo_template": (
                "Prontuário | Cliente: {{vars.nome_cliente}} | "
                "Solicitante: {{vars.tipo_solicitante}} | "
                "Paciente: {{vars.dados_paciente_prontuario}} | "
                "Formato: {{vars.formato_prontuario}}"
            ),
            "message_to_client": (
                "Solicitação aberta. Nossa equipe entrará em contato para "
                "conferir seus documentos e liberar o prontuário "
                "(Prazo estimado: 7 a 15 dias)."
            ),
            "next": "__end__",
        },
        # 4. Protocolo
        "prot_num": {
            "type": "ask_text",
            "prompt": "Digite o Número do Protocolo que você recebeu:",
            "save_as": "numero_protocolo_busca",
            "validate_with": "min_len:3",
            "next": "prot_handover",
        },
        "prot_handover": {
            "type": "handover",
            "resumo_template": (
                "Consulta Protocolo | Cliente: {{vars.nome_cliente}} | "
                "Protocolo: {{vars.numero_protocolo_busca}}"
            ),
            "message_to_client": (
                "Localizando seu protocolo... Um atendente vai te "
                "informar o status atual em instantes."
            ),
            "next": "__end__",
        },
    },
}


WORKFLOWS = {
    "menu_principal": ("Menu Principal (LGPD + Setores)", MENU_PRINCIPAL),
    "menu_atendimento_cliente": (
        "Atendimento ao Cliente (Quadro/Guias/2ª Via)",
        MENU_ATENDIMENTO_CLIENTE,
    ),
    "menu_agendamento": ("Agendamentos (Marcar/Reagendar/Cancelar)", MENU_AGENDAMENTO),
    "menu_exames": ("Exames e Diagnósticos", MENU_EXAMES),
    "menu_tesouraria": ("Tesouraria (Pagamentos/NF/Negociação)", MENU_TESOURARIA),
    "menu_orcamentos": ("Orçamentos e Internação", MENU_ORCAMENTOS),
    "menu_portaria": ("Portaria e Recepção (Visitas/Achados)", MENU_PORTARIA),
    "menu_outras": ("Outras Informações (Manual/Capelania/RH)", MENU_OUTRAS),
    "menu_ouvidoria": ("Ouvidoria (Manifestação/Denúncia/Prontuário)", MENU_OUVIDORIA),
}


async def upsert_workflow(
    pool, empresa_id: int, slug: str, nome: str, definicao: dict, ativo: bool
) -> tuple[int, int]:
    """UPSERT em workflow_chatbot. Retorna (workflow_id, versao_ativa_id)."""
    async with pool.connection() as conn:
        # Upsert workflow_chatbot (mutável)
        cur = await conn.execute(
            """
            INSERT INTO workflow_chatbot
                (empresa_id, slug, nome, definicao, versao, ativo)
            VALUES (%s, %s, %s, %s::jsonb, 1, %s)
            ON CONFLICT (empresa_id, slug) DO UPDATE
              SET definicao = EXCLUDED.definicao,
                  nome = EXCLUDED.nome,
                  versao = workflow_chatbot.versao + 1,
                  ativo = EXCLUDED.ativo,
                  updated_at = NOW()
            RETURNING id, versao
            """,
            (
                empresa_id,
                slug,
                nome,
                json.dumps(definicao, ensure_ascii=False),
                ativo,
            ),
        )
        row = await cur.fetchone()
        assert row is not None
        wf_id, versao = int(row[0]), int(row[1])

        # Insere versao imutável correspondente
        cur = await conn.execute(
            """
            INSERT INTO workflow_chatbot_version
                (workflow_id, versao, definicao)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (workflow_id, versao) DO UPDATE
              SET definicao = EXCLUDED.definicao
            RETURNING id
            """,
            (wf_id, versao, json.dumps(definicao, ensure_ascii=False)),
        )
        row = await cur.fetchone()
        assert row is not None
        version_id = int(row[0])

        # Marca versao_ativa_id
        await conn.execute(
            "UPDATE workflow_chatbot SET versao_ativa_id = %s WHERE id = %s",
            (version_id, wf_id),
        )
        await conn.commit()
        return wf_id, version_id


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa-id", type=int, required=True)
    parser.add_argument(
        "--ativo",
        action="store_true",
        help="Marca menu_principal como ativo (entra em produção pra empresa)",
    )
    args = parser.parse_args()

    pool = await get_pool()
    try:
        for slug, (nome, defin) in WORKFLOWS.items():
            ativo = args.ativo and slug == "menu_principal"
            wf_id, version_id = await upsert_workflow(
                pool, args.empresa_id, slug, nome, defin, ativo
            )
            print(
                f"  ✓ {slug:30s} workflow_id={wf_id} version_id={version_id} "
                f"ativo={ativo}"
            )
    finally:
        await close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
