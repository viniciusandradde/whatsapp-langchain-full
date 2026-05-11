"""One-shot importer: cria 2 workflows do Hospital Mackenzie no DB.

Foco: `menu_principal` (LGPD gate + nome + menu 8 setores) e
`menu_atendimento_cliente` (5 opções: quadro médico, guias, 2ª via, falar).

Os outros 7 setores ficam como SKELETON (placeholder) — admin completa
via UI ou SQL depois.

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
                {"label": "Agendamentos", "value": "2", "next": "stub_agendamentos"},
                {"label": "Exames e Diagnósticos", "value": "3", "next": "stub_exames"},
                {"label": "Tesouraria", "value": "4", "next": "stub_tesouraria"},
                {
                    "label": "Orçamentos e Internação",
                    "value": "5",
                    "next": "stub_orcamentos",
                },
                {"label": "Portaria e Recepção", "value": "6", "next": "stub_portaria"},
                {"label": "Outras Informações", "value": "7", "next": "stub_outras"},
                {"label": "Ouvidoria", "value": "8", "next": "stub_ouvidoria"},
            ],
            "retry_message": "Opção inválida. Selecione 1 a 8.",
        },
        # Setores stub (admin completa depois)
        "stub_agendamentos": {
            "type": "handover",
            "departamento_id": None,
            "resumo_template": "Cliente: {{vars.nome_cliente}} | Setor: Agendamentos",
            "message_to_client": (
                "Você está na fila do setor *Agendamentos*. "
                "Em breve um atendente irá te atender, {{vars.nome_cliente}}."
            ),
            "next": "__end__",
        },
        "stub_exames": {
            "type": "handover",
            "resumo_template": "Cliente: {{vars.nome_cliente}} | Setor: Exames",
            "message_to_client": (
                "Você está na fila do setor *Exames*. "
                "Em breve um atendente irá te atender."
            ),
            "next": "__end__",
        },
        "stub_tesouraria": {
            "type": "handover",
            "resumo_template": "Cliente: {{vars.nome_cliente}} | Setor: Tesouraria",
            "message_to_client": (
                "Você está na fila do setor *Tesouraria*. "
                "Em breve um atendente irá te atender."
            ),
            "next": "__end__",
        },
        "stub_orcamentos": {
            "type": "handover",
            "resumo_template": "Cliente: {{vars.nome_cliente}} | Setor: Orçamentos",
            "message_to_client": (
                "Você está na fila do setor *Orçamentos*. "
                "Em breve um atendente irá te atender."
            ),
            "next": "__end__",
        },
        "stub_portaria": {
            "type": "handover",
            "resumo_template": "Cliente: {{vars.nome_cliente}} | Setor: Portaria",
            "message_to_client": (
                "Você está na fila do setor *Portaria*. "
                "Em breve um atendente irá te atender."
            ),
            "next": "__end__",
        },
        "stub_outras": {
            "type": "handover",
            "resumo_template": (
                "Cliente: {{vars.nome_cliente}} | Setor: Outras Informações"
            ),
            "message_to_client": (
                "Você está na fila. Em breve um atendente irá te atender."
            ),
            "next": "__end__",
        },
        "stub_ouvidoria": {
            "type": "handover",
            "resumo_template": "Cliente: {{vars.nome_cliente}} | Setor: Ouvidoria",
            "message_to_client": (
                "Você está na fila da *Ouvidoria*. "
                "Em breve um atendente irá te atender."
            ),
            "next": "__end__",
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


WORKFLOWS = {
    "menu_principal": ("Menu Principal (LGPD + Setores)", MENU_PRINCIPAL),
    "menu_atendimento_cliente": (
        "Atendimento ao Cliente (Quadro/Guias/2ª Via)",
        MENU_ATENDIMENTO_CLIENTE,
    ),
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
