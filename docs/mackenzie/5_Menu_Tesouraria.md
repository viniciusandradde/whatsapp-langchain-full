MENU Tesouraria (4) (Modelo Human‑in‑the‑Loop)
Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie

Modelo: Triagem Financeira e Gestão de Receita (RCM)

Objetivo Estratégico

Otimizar o Ciclo de Receita do Hospital, facilitando o pagamento e reduzindo a inadimplência. O Assistente Virtual atua para:

Agilidade no Recebimento: Entrega automática de 2ª Via de Boletos e Pix, reduzindo o atrito para quem quer pagar.

Segregação de Fluxos: Separa quem quer Pagar (Receita) de quem quer Reembolso/Notas (Administrativo), direcionando para as filas corretas.

Pré-Negociação: Coleta a intenção de pagamento (Parcelado/À Vista) antes do atendente humano,

Estrutura do Menu Principal (Tesouraria)

Bot: "Você está na Tesouraria. Para assuntos financeiros, selecione uma opção:"

[1] Pagamentos, 2ª Via e Pendências(Boletos, Pix, Quitar débitos atuais)

[2] Negociação e Parcelamentos(Acordos de dívidas antigas, Cartão de Crédito)

[3] Notas Fiscais e Reembolsos(Emissão de NF, Recibos para IR)

[4] Estimativas e Orçamentos(Custos de Internação, Procedimentos Particulares)

[5] Assuntos Jurídicos e Risco Cirúrgico(Ofícios, Liminares)

[6] Voltar ao Menu Principal

Detalhamento dos Fluxos (Regras de Negócio)

Fluxo 1: Pagamentos e 2ª Via (Foco em Recebimento)

Regra: Facilitar o pagamento imediato.

Identificação Financeira:

Bot: "Para localizar seus títulos em aberto, digite o CPF do Responsável Financeiro:" (Sistema grava: {{cpf_financeiro}})

Validação de Segurança:

Bot: "Confirme a Data de Nascimento do Paciente ou Responsável (DD/MM/AAAA):" (Sistema grava: {{data_nasc_fin}})

Ação:

Bot: "Localizando... "

Bot: "Encontrei seu cadastro. Um atendente vai te enviar o arquivo PDF (Boleto) ou o código Pix Copia-e-Cola agora mesmo."

Fluxo 2: Negociação e Parcelamentos (Recuperação de Crédito)

Regra: Coleta da proposta do cliente para agilizar o acordo.

Contexto:

Bot: "Vamos ajudar você a regularizar suas pendências. 🤝"

Proposta do Cliente (Triagem):

Bot: "Como você prefere realizar o pagamento?"

Opção A: Cartão de Crédito (Parcelado)

Opção B: À Vista (Pix/Dinheiro com desconto)

Opção C: Boleto (Entrada + Parcelas)(Sistema grava: {{preferencia_pagamento}})

Handover:

Bot: "Perfeito. Já registrei sua preferência por {{preferencia_pagamento}}. Um analista vai verificar as condições disponíveis e te chamar em instantes."

Fluxo 3: Notas Fiscais e Reembolsos (Administrativo)

Regra: Garantia de dados fiscais corretos.

Coleta de Dados Fiscais:

Bot: "Para emissão de Nota Fiscal ou Recibos, precisamos confirmar os dados."

Bot: "Por favor, digite o Nome Completo ou Razão Social para a nota:" (Sistema grava: {{dados_nota}})

Documento (CPF/CNPJ):

Bot: "Agora, digite o CPF ou CNPJ:" (Sistema grava: {{doc_fiscal}})

Encerramento:

Bot: "Solicitação registrada. Nossa equipe enviará o documento para seu e-mail ou por aqui assim que emitido."

Fluxo 4: Estimativas e Orçamentos

Regra: Triagem entre Particular e Convênio (Semelhante ao Menu Orçamentos).

Triagem:

Bot: "Você deseja saber os custos para Convênio (Carência/Coparticipação) ou Particular?"

[1] Particular

[2] Convênio (Sistema grava: {{tipo_estimativa}})

Especificação:

Bot: "Qual procedimento ou cirurgia você deseja orçar?" (Sistema grava: {{procedimento_estimativa}})

Encerramento:

Bot: "Entendido. Transferindo para a equipe de orçamentos realizar o cálculo."

Fluxo 5: Assuntos Jurídicos e Risco Cirúrgico

Regra: Upload de documentos obrigatório.

Solicitação de Arquivo:

Bot: "Para análise de ofícios ou risco cirúrgico, precisamos do documento."

Bot: "Por favor, envie uma foto ou PDF do documento judicial/médico agora." (Sistema aguarda anexo e grava em: {{anexo_juridico}})

Encerramento:

Bot: "Documento recebido. Vamos encaminhar para o departamento Jurídico/Compliance analisar."

Fluxo 6: Voltar ao Menu Principal

Bot: "Retornando ao menu inicial... " (Redireciona para Menu Global)

Requisitos para Configuração (TI)

Para o funcionamento correto, configurar as seguintes variáveis de entrada no ZigChat:

{{cpf_financeiro}}: Input numérico (chave de busca no ERP).

{{preferencia_pagamento}}: Botões ou Lista (Crítico para o operador saber se oferece maquininha ou boleto).

{{anexo_juridico}}: Input de Mídia (Deve aceitar Imagem e PDF).

{{doc_fiscal}}: Input de texto (CPF ou CNPJ).

Fluxograma:

Infográfico:
