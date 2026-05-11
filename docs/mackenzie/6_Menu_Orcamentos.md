Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

MENU ORÇAMENTOS (5)

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Triagem Financeira Inteligente (Human-in-the-Loop)

Objetivo Estratégico

Transformar o canal de atendimento em uma ferramenta de Captação e Conversão Financeira. O Assistente Virtual deve qualificar a venda segregando imediatamente Convênio (Autorização) de Particular (Comercial), garantir insumos bloqueando solicitações sem a foto do pedido médico para eliminar retrabalho, e capturar leads de urgência fora do horário comercial para ação ativa da equipe financeira.

1. Menu Principal de Orçamentos

Cenário: Cliente selecionou Opção 5 (Orçamentos) no Menu Global.

Bot: "Você está na Central de Orçamentos e Internações. "

Bot: "Para agilizar sua cotação, selecione o assunto:"

[1] Orçamento de Cirurgias e Procedimentos (Eletivos)

[2] Valores de Urgência/Emergência (Particular)

[3] Acompanhar Status do Orçamento

[4] Dúvidas sobre Convênios e Prazos

[5] Voltar ao Menu Principal

Fluxo 1: Cirurgias e Procedimentos (Quebrado em Etapas)

Objetivo: Garantir que o paciente envie a foto do pedido e os dados do médico.

Identificação:

Bot: "Vamos iniciar seu processo de orçamento. Primeiro, digite o Nome Completo do Paciente:" (Sistema grava dado: {{nome_paciente}})

Envio do Pedido (Crucial):

Bot: "Para orçarmos corretamente, precisamos do pedido médico." Bot: "Por favor, digite o nome do procedimento OU envie uma foto do pedido agora." (Sistema grava dado: {{pedido_medico_anexo}})

Detalhes do Médico:

Bot: "Qual é o nome do Médico solicitante ou Cirurgião? (Se não tiver médico definido, digite 'Sem médico')." (Sistema grava dado: {{nome_medico}})

Pagador (Filtro):

Bot: "O orçamento será via Convênio ou Particular?" [A] Convênio (Digite o nome do plano) [B] Particular (Sistema grava dado: {{tipo_pagamento}})

Handover (Passagem de Bastão):

Bot: "Recebido. Encaminhei sua solicitação para a Central de Orçamentos." Bot: "Nossa equipe fará a análise técnica (códigos TUSS/AMB) e retornará com os valores e autorizações necessárias."

Fluxo 2: Urgência/Emergência (Particular)

Resolve o problema do horário. O robô atende 24h, o humano responde no horário comercial.

Aviso de Contexto:

Bot: "Os valores de Urgência (Pronto Socorro) variam conforme a medicação e exames realizados no momento."

Bot: "No entanto, podemos passar uma estimativa de consulta e taxas iniciais."

Coleta de Contato:

Bot: "Por favor, digite seu Nome e Telefone:" (Sistema grava dado: {{contato_urgencia}})

Gestão de Expectativa (Horário):

Regra de Negócio: O robô envia a mesma mensagem sempre, gerenciando a ansiedade.

Bot: "Registrado. Um atendente do financeiro vai entrar em contato para passar a tabela de valores vigente."

Bot: (Obs: Se for uma emergência médica grave, dirija-se diretamente ao nosso Pronto Socorro).

Fluxo 3: Acompanhar Status

Para quem já pediu e está ansioso.

Bot: "Para verificar o andamento, digite o CPF do Paciente:"

(Sistema grava dado: {{cpf_paciente}})

Bot: "Se você já tem um Número de Protocolo, digite abaixo (ou 'Não tenho'):"

(Sistema grava dado: {{protocolo_orcamento}})

Bot: "Localizando..Um analista vai te informar em que etapa está sua liberação (Análise, Auditoria ou Liberado)."

Fluxo 4: Dúvidas sobre Convênios e Prazos

Filtra perguntas repetitivas.

Bot: "Qual é a sua dúvida específica?"

[1] Quais Convênios atendemos

[2] Formas de Pagamento (Particular)

[3] Prazo de validade do Orçamento (Sistema grava dado: {{duvida_financeira}})

Bot: "Certo. Um atendente vai te passar as regras atualizadas sobre {{duvida_financeira}}."

Fluxo 5: Voltar

(Retorna ao Menu Global)

Fluxograma:

Infográfico:
