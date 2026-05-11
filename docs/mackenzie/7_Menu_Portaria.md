MENU PORTARIA/RECEPÇÃO (6) (Modelo Human‑in‑the‑Loop)
Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Concierge Digital e Controle de Acesso

Objetivo Estratégico

Melhorar a experiência de chegada e segurança física do hospital. O Assistente Virtual atua para:

Regras Claras (Manual Digital): Disponibiliza o Link Oficial de Visitas para evitar barrar pessoas na entrada por falta de informação (roupas, horários).

Agilidade no Credenciamento: Coleta antecipadamente os dados dos visitantes, reduzindo filas na recepção física.

Centralização Logística: Entrega endereço, mapa e regras de estacionamento em um único bloco.

Estrutura do Menu Principal (Portaria)

Bot: "Você está na Portaria e Recepção Central. Selecione o assunto:"

[1] Visitas, Acompanhantes e Regras de Acesso-(Link do Manual e Credenciamento)

[2] Localização e Estacionamento-(Endereço, Mapas e Onde Parar)

[3] Achados e Perdidos - (Registrar ou Buscar objetos)

[4] Chegada ao Pronto Socorro - (Urgência)(Orientações de Entrada)

[5] Voltar ao Menu Principal

Detalhamento dos Fluxos (Regras de Negócio)

Fluxo 1: Visitas, Acompanhantes e Regras

Regra: Entrega do Link Institucional Obrigatório + Opção de Cadastro.

Entrega de Informação (O Link):

Bot: "Para garantir a segurança e o bem-estar dos pacientes, seguimos regras estritas de visitação (horários, vestimenta e itens permitidos)."

Bot: "Acesse o Manual Completo no link abaixo:"

Informações aos Visitantes / Acompanhantes:[Inserir Link do Site Aqui]

Ação de Credenciamento (Pré-Cadastro):

Bot: "Deseja adiantar seu cadastro de visitante para agilizar sua entrada?"

[1] Sim, quero adiantar.

[2] Não, já tenho cadastro / Só queria o link.

Se [1] (Coleta de Dados):

Bot: "Ótimo. Digite o Nome do Paciente que você irá visitar:" (Sistema grava: {{nome_paciente_visita}})

Bot: "Qual seu grau de parentesco? (Ex: Pai, Filho, Amigo):" (Sistema grava: {{parentesco_visita}})

Bot: "Cadastro prévio iniciado! Apresente seu documento na recepção para retirar o crachá."

Fluxo 2: Localização e Estacionamento

Regra: Entrega de valor logístico.

Endereço e Mapa:

Bot: "Estamos localizados na Rua Hilda Bergo Duarte, 81 - Centro, Dourados/MS." (Sistema envia o Card de Localização/Google Maps nativo do WhatsApp)

Estacionamento (Gestão de Expectativa):

Bot: "Sobre Estacionamento: Não dispomos de estacionamento privativo. Recomendamos estacionar nas vias laterais ou estacionamentos rotativos próximos."

Fluxo 3: Achados e Perdidos

Regra: Registro estruturado para a segurança.

Identificação do Objeto:

Bot: "Sentimos muito pelo ocorrido. Vamos registrar."

Bot: "O que foi perdido? (Descreva cor, marca, modelo):" (Sistema grava: {{descricao_objeto}})

Contexto:

Bot: "Onde e quando você acha que perdeu? (Ex: Recepção, ontem à tarde):" (Sistema grava: {{local_perda}})

Contato de Retorno:

Bot: "Qual telefone podemos contatar caso encontremos?" (Sistema grava: {{contato_retorno}})

Encerramento:

Bot: "Registro criado. Se o item for entregue na recepção, entraremos em contato."

Fluxo 4: Chegada ao Pronto Socorro

Regra: Aviso de que Chat NÃO é para emergência médica.

Alerta de Segurança:

Bot: " Atenção: Se esta é uma emergência médica, não aguarde atendimento por aqui."

Bot: "Dirija-se imediatamente à Entrada de Emergência (Lateral Esquerda)."

Fluxo 5: Voltar ao Menu Principal

Bot: "Retornando ao menu inicial... "

Requisitos para Configuração (TI)

Para o funcionamento correto, configurar as seguintes variáveis de entrada no ZigChat:

Link no Fluxo 1: Configurar o botão ou texto com a URL correta do site do Hospital Mackenzie.

{{nome_paciente_visita}}: Texto livre.

{{parentesco_visita}}: Texto livre.

{{descricao_objeto}}: Texto livre.

{{local_perda}}: Texto livre.

Fluxograma:

Infográfico:
