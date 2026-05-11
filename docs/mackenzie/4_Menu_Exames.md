Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

MENU EXAMES (3)

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Triagem Financeira Inteligente (Human-in-the-Loop)

Objetivo Estratégico

Transformar o canal de atendimento em uma ferramenta de Captação e Conversão Financeira. O Assistente Virtual atua para:

Qualificar a Venda: Segrega imediatamente solicitações de Convênio (Foco Administrativo) das Particulares (Foco Comercial).

Garantir Insumos: Bloqueia a entrada de solicitações incompletas, exigindo a foto ou nome do procedimento antes de passar para o humano.

Retenção 24h (Leads): Captura contatos de urgência fora do horário comercial para ação ativa da equipe financeira no primeiro horário útil.

Bot: "Você está na Central de Diagnósticos e Exames (Laboratório e Imagem). 🔬" Bot: "Para agilizar, selecione o assunto principal:"

[1] Agendar Exames

[2] Resultados e Laudos

[3] Orçamentos e Valores

[4] Preparo e Orientações

[5] Reagendar ou Cancelar

[6] Voltar ao Menu Principal

Fluxo 1: Agendar Exames (Triagem Completa)

Consolida agendamentos de Convênio, Particular e Especiais em um único caminho simples.

Identificação:

Bot: "Vamos iniciar seu agendamento. Primeiro, digite o Nome Completo do Paciente:" (Sistema grava dado: {{nome_paciente}})

Necessidade:

Bot: "Qual exame você precisa realizar? (Escreva o nome ou digite 'Vários' se tiver foto do pedido)." (Sistema grava dado: {{nome_exame}})

Modalidade (Filtro Financeiro):

Bot: "O atendimento será por qual modalidade?" [1] Convênio / Plano de Saúde [2] Particular / Pagamento Próprio (Sistema grava dado: {{modalidade_pagamento}})

Transferência Inteligente:

Bot: "Entendido. Transferindo para a Central de Agendamento..." Bot: "Um atendente vai verificar a agenda do convênio/particular e confirmar o horário do seu {{nome_exame}} agora mesmo."

Fluxo 2: Resultados e Laudos

Objetivo: Direcionar o paciente para o Portal Seguro. Proibido envio de arquivos via Chat.

Instrução de Acesso:

Bot: "Por questões de segurança e sigilo médico, seus resultados devem ser acessados exclusivamente pelo nosso Portal do Paciente."

Bot: "Acesse o link abaixo e digite o Login e Senha entregues na recepção no dia do seu exame:"

Link de Acesso:https://modulos.conectew.com.br/conecte/laudos/loginPaciente/view.jsf?edc=265

Verificação de Sucesso:

Bot: "Você conseguiu acessar seus resultados?" [1] Sim, consegui.[2] Não / Esqueci a Senha / Preciso de Ajuda.

Caminhos (Regra de Negócio):

Se [1] Sim:

Bot: "Ótimo! Se precisar de mais alguma coisa, é só chamar. Tenha um bom dia! " (Fim do Atendimento)

Se [2] Não:

Bot: "Entendido. Vamos te ajudar a recuperar seu acesso."

Bot: "Por favor, digite o Nome Completo e o CPF do Paciente:" (Sistema grava variáveis: {{nome_paciente}} e {{cpf_paciente}})

Bot: "Um atendente vai verificar seu cadastro e te orientar sobre como redefinir sua senha ou retirar o exame presencialmente." (Transbordo para Suporte - Nota para Operador: Ajudar no login, não enviar arquivo).

Fluxo 3: Orçamentos e Valores

Foco em conversão de vendas (Exames Particulares).

Bot: "Sem problemas. Vamos fazer uma cotação para você. "

Bot: "Por favor, digite o Nome do Exame que deseja orçar:"

(Sistema grava dado: {{pedido_orcamento}})

Bot: "Recebido. Nossa equipe financeira vai calcular o valor e te informar as formas de pagamento em instantes."

Fluxo 4: Preparo e Orientações

Resolve dúvidas técnicas antes do exame.

Bot: "Para garantir o sucesso do seu exame, o preparo correto é essencial."

Bot: "Para qual exame você precisa de instruções? (Ex: Ultrassom, Sangue, Tomografia)."

(Sistema grava dado: {{exame_preparo}})

Bot: "Certo. Estou acionando a equipe técnica para te passar o preparo exato do {{exame_preparo}}."

Fluxo 5: Reagendar ou Cancelar

Organização de Agenda.

Bot: "Entendido. Digite o CPF do Paciente:"

Bot: "Qual é a sua necessidade?"

[1] Reagendar (Trocar data)

[2] Cancelar Definitivamente(Sistema grava dado: {{acao_agenda}})

Bot: "Solicitação enviada. Um atendente vai confirmar a alteração na agenda."

Fluxo 6: Voltar ao Menu Principal

Bot: "Retornando ao menu inicial... " (Sistema redireciona para o Menu Global de Opções)

Fluxograma

Infográfico:
