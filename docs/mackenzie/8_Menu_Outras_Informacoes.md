MENU Outras Informações (7) (Modelo Human‑in‑the‑Loop)
Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Hub Institucional e Apoio Humanizado

Objetivo Estratégico

Centralizar informações institucionais que não geram receita direta, mas são essenciais para a imagem e funcionamento do hospital.

Acolhimento Espiritual: Facilita o acesso à Capelania (identidade Presbiteriana).

Desvio de Demanda (RH): Automatiza a resposta sobre envio de currículos, liberando os atendentes.

Rede de Segurança: Serve como última opção para assuntos não listados nos menus anteriores.

Estrutura do Menu Principal (Outras Informações)

Bot: "Você está no Menu de Informações Institucionais. Selecione o assunto:"

[1] Manual do Paciente e Visitante(Regras, O que levar, Normas)

[2] Capelania e Apoio Espiritual(Solicitar visita pastoral ou oração)

[3] Trabalhe Conosco (Envio de Currículo)(Informações do RH)

[4] Falar com Atendente (Outros Assuntos)(Demandas não listadas)

[5] Voltar ao Menu Principal

Detalhamento dos Fluxos (Regras de Negócio)

Fluxo 1: Manual do Paciente e Visitante

Regra: Entrega de Informação Estática (Link).

Ação:

Bot: "Para consultar as regras de visitas, itens permitidos na internação e direitos do paciente, acesse nosso Manual Digital:"

Link Oficial: [Inserir Link do Site Aqui]

Bot: "Deseja algo mais sobre este tema?"

[1] Voltar ao Menu

[2] Encerrar

Fluxo 2: Capelania e Apoio Espiritual

Regra: Acolhimento Humanizado (Diferencial do Hospital).

Contexto:

Bot: "O Hospital Presbiteriano preza pelo cuidado integral. Nossa equipe de Capelania está disponível para oferecer apoio espiritual e emocional aos pacientes e familiares. "

Solicitação:

Bot: "Como podemos ajudar?"

[1] Solicitar Visita do Capelão (Presencial)

[2] Deixar um Pedido de Oração

Se [1] (Visita):

Bot: "Para qual paciente (nome e quarto) você solicita a visita?" (Sistema grava: {{solicitacao_capelania}})

Bot: "Pedido registrado. Enviaremos ao pastor responsável pelo setor."

Fluxo 3: Trabalhe Conosco (RH)

Regra: Automatização total (Evitar humano).

Resposta Automática:

Bot: "Ficamos felizes com seu interesse em fazer parte da nossa equipe!"

Bot: "Neste canal, não recebemos arquivos de currículo."

Bot: "Por favor, cadastre-se em nosso banco de talentos no site ou envie para o e-mail oficial:"

rh@hospitalmackenzie.com.br (Exemplo - Ajustar)

Encerramento:

Bot: "Boa sorte! Esperamos te ver em breve."

Fluxo 4: Falar com Atendente (Outros Assuntos)

Regra: Triagem final para evitar erro de roteamento.

Validação de Assunto (O Filtro):

Bot: "Vamos te conectar a um especialista. Mas antes, uma confirmação importante:"

Bot: "Se o seu assunto for Agendamento ou Resultado de Exame, por favor volte ao menu principal para ser atendido mais rápido."

Bot: "Se for outro assunto, escreva abaixo em poucas palavras o que você precisa:" (Sistema aguarda input de texto: {{resumo_outros}})

Handover:

Bot: "Entendido. Estou transferindo você para a Central de Apoio Administrativo com a observação: {{resumo_outros}}."

Fluxo 5: Voltar ao Menu Principal

Bot: "Retornando ao menu inicial... "

Requisitos para Configuração (TI)

Para o funcionamento correto, configurar as seguintes variáveis de entrada no ZigChat:

Link no Fluxo 1: URL do Manual.

{{solicitacao_capelania}}: Texto livre (Nome/Quarto).

{{resumo_outros}}: Texto livre (Input do usuário).

E-mail no Fluxo 3: Confirmar o e-mail correto do RH.

Fluxograma:

Infográfico:
