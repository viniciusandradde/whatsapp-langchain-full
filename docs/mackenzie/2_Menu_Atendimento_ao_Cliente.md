Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

MENU ATENDIMENTO CLIENTE (1)

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Triagem Inteligente (Human-in-the-Loop)

Objetivo Estratégico

Reduzir o volume de chamados na recepção resolvendo dúvidas frequentes de forma automática e estruturando o contato humano. O Assistente Virtual atua para:

Autoatendimento: Entrega informações estáticas (Escalas, Guias e Manuais) sem ocupar um atendente humano.

Triagem Administrativa: Coleta dados completos para solicitações de documentos (2ª Via), evitando o "ping-pong" de perguntas.

Gestão de Expectativa: Gerencia a fila de espera com mensagens de conforto e coleta prévia do motivo do contato.

Etapa 1: Recepção e Identificação (Obrigatória)

Fluxo Submenu

Mensagem 1: Informação para agilizar o atendimento.

Passo 1: Coleta de Dados (Obrigatória)

Bot: " Olá! Seja bem-vindo ao atendimento digital do Hospital Presbiteriano Mackenzie. 🤝"

Bot: "Para agilizar o seu atendimento e direcionarmos para o setor correto, por favor, escreva seu Nome Completo e a Cidade de onde está falando."

Bot: aguarda a resposta do cliente (input de texto livre) (Clientes Responde)

Bot:  "Obrigado, {{nome_cliente}}! Selecione abaixo como podemos te ajudar hoje:"

[Botões do Menu 1 a 5]

Passo 2: Exibição do Menu (Apenas após a resposta)

Bot: "Obrigado, Agora, selecione as opções a qual deseja obter informações:”

Quadro Médico (Clínico Geral, Pediatria e Obstetrícia)

Guia de Pacientes

Guia Maternidade

Segunda Via de Documentos e Declarações

Outras Orientações e Informações

1. Informações do Quadro Médico Plantonista 24h

Descrição: Fornece detalhes sobre os médicos plantonistas disponíveis 24 horas por especialidade.

Conteúdo/Fluxo: Exibe as especialidades disponíveis: "Clínico Geral, Pediatria e Obstetrícia".

Expansão opcional: Ao selecionar uma especialidade, o sistema pode listar os nomes dos médicos em plantão ou direcionar para uma página atualizada em tempo real com essa informação.

Resposta Bot:"Especialidades com plantão 24h: Clínico Geral, Pediatria e Obstetrícia."

Bot: "Caso precise confirmar a escala de um médico específico, digite 5 para falar com nossa equipe "

2. Guia para Pacientes e Acompanhantes

Descrição: Oferece um guia completo com informações importantes para pacientes e acompanhantes durante a estadia no hospital (regras de visita, horários, serviços disponíveis, etc.).

Conteúdo/Fluxo: Link direto para acesso imediato ao guia digital.

Resposta Automatizada:"Acesse nosso Guia para Pacientes e Acompanhantes aqui:
https://bit.ly/3SWiqnC?zc-numeroTel=556792469894&zc-msgVerify=019bffa2-0f19-70fd-b7a2-f12d   cac8bb5a"

3. Guia Maternidade

Descrição: Guia específico para gestantes e acompanhantes, com informações sobre processo de parto, internação, cuidados com o recém-nascido, documentos necessários e orientações pós-parto.

Conteúdo/Fluxo: Envio automático do arquivo PDF em anexo ou link para download direto.

Resposta Automatizada:"Segue o Guia Maternidade em formato PDF para download."

4. Segunda Via de Documentos e Declarações

Descrição: Solicitação automatizada de documentos administrativos e clínicos já emitidos pelo hospital.

Conteúdo/Fluxo: O sistema exibe as categorias disponíveis e solicita dados de identificação (CPF e data de nascimento) para validar a solicitação.

Resposta Automatizada Bot: "Oferecemos segunda via dos seguintes documentos”

• Atestados médicos
• Recibos de pagamento
• Relatórios médicos
• Declarações diversas"

4.1 .Pergunta sobre o Médico/Atendimento:

Bot: "Você se lembra o Nome do Médico ou a Especialidade (ex: Cardiologista) que te atendeu?" (Cliente digita. Ex: "Foi o Dr. Silva" ou "Não lembro")(Sistema grava na variável {{nome_medico}})

4.2. Pergunta sobre Data/Internação:

Bot: "Qual foi a data aproximada do atendimento ou por quanto tempo ficou internado?" (Cliente digita. Ex: "Semana passada, dia 10" ou "Fiquei 3 dias em janeiro")(Sistema grava na variável {{data_ref}})

4.3. Pergunta sobre o Motivo (Contexto):

Bot: "O que houve com a 1ª via? (Ex: Esqueceu de pegar na saída, perdeu o papel, ou precisa para o plano de saúde?)" (Cliente digita. Ex: "Esqueci de pegar na recepção")(Sistema grava na variável {{motivo_solicitacao}})

4.4. Coleta de Dados Finais (Identificação):

Bot: "Perfeito! Já anotei os detalhes. Para finalizar, digite o CPF do paciente:" (Cliente digita)

Bot: "Agora, a Data de Nascimento (dia/mês/ano):" (Cliente digita)

4.5. Fechamento e Transbordo:

Bot: "Obrigado! Já passei tudo para a equipe administrativa. Aguarde um momento que um atendente já vai confirmar a emissão do seu documento." (Transfere para a fila. O atendente recebe um resumo: "Cliente quer atestado do Dr. Silva, de jan/26, pq esqueceu de pegar. CPF X, Nasc Y".)

5. Outras Orientações e Informações (Falar com Especialista)

Descrição: Canal dedicado a demandas complexas não resolvidas no menu automático. O Assistente Virtual realiza uma pré-triagem para agilizar o trabalho do atendente humano.

Lógica de Atendimento e Fila: Ao selecionar a opção 5, o sistema inicia o protocolo de transferência. Como não há busca automática de histórico, o Robô solicita o motivo do contato para criar um "Resumo do Chamado" para o operador.

Script e Gatilhos:

Gatilho Imediato (Acolhimento + Triagem):

Bot: "Compreendido. Vou direcionar você para um de nossos especialistas."

Bot: "Para ganhar tempo enquanto localizo um atendente livre, por favor, escreva em uma frase qual é a sua dúvida ou necessidade." (Sistema aguarda input do cliente e grava na variável {{resumo_assunto}})

Confirmação de Fila:

Bot: "Certo, anotei o motivo: '{{resumo_assunto}}'. Você já está na nossa fila de prioridade. Aguarde um momento. "

Gestão Inteligente de Espera: O sistema monitora a posição do cliente na fila em tempo real (Tempo máximo sugerido de permanência na fila: 15 minutos).

Gatilho de 5 Minutos (Retenção): Caso o atendimento não inicie nos primeiros 5 minutos, o sistema envia automaticamente a mensagem de conforto para evitar abandono:

Mensagem 1.1: "Ainda estou por aqui monitorando sua vez! Nossos atendentes estão finalizando os casos atuais." Mensagem 1.2: "Sua posição estimada na fila é: número {{posicao_fila}}. Logo será você."

Conexão (Handover): Assim que o operador puxar o chamado:

Bot: "Conexão estabelecida! ✅ Você agora está sendo atendido por {{nome_atendente}}." (O atendente recebe na tela: Nome, Cidade e o Resumo do Assunto que o cliente digitou).

Fluxograma:

Infográfico:
