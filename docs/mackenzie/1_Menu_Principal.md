MENU Principal (1) (Modelo Human‑in‑the‑Loop)
Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Navegação Centralizada (Hub de Atendimento)

Objetivo Estratégico

Garantir segurança jurídica desde o primeiro "Olá". O fluxo segue a ordem estrita:

Saudação: O cliente recebe o "Oi" institucional.

Barreira LGPD: O cliente recebe o Link de Privacidade e deve aceitar para continuar.

Liberação: Somente após o aceite, o sistema pede o Nome e libera o Menu.

Etapa 1: Boas-Vindas e Identificação

Regra: Acolhimento imediato e Compliance (LGPD).

Etapa 1: Boas-Vindas (Imediato)Gatilho: Cliente envia a primeira mensagem.

Bot: "Olá! Seja bem-vindo ao Hospital Presbiteriano Mackenzie - Dr. e Sra. Goldsby King."

Bot: "Sou seu assistente virtual e estou aqui para iniciar seu atendimento com agilidade."

Etapa 2: Privacidade e Consentimento (LGPD)

Regra: O atendimento pára aqui até o cliente interagir. Nenhuma informação é coletada antes disso.

Bot: "Para continuarmos seu atendimento com segurança e transparência, precisamos do seu consentimento para tratamento de dados, conforme a Lei Geral de Proteção de Dados (LGPD)."

Bot: "Por favor, leia nossa Política de Privacidade no link abaixo:" Link Oficial: https://bit.ly/3QJXkWw

Bot: "Você declara que leu e CONCORDA com os termos para prosseguir?"

[1] Sim, Li e Concordo.

[2] Não concordo / Sair. ❌

Regra de Sistema:

Se [1]: O sistema avança para a Etapa 3.

Se [2]: O sistema envia mensagem de encerramento: "Entendemos. Sem o aceite, não podemos prosseguir pelo canal digital. Agradecemos o contato!" e finaliza a sessão.

Etapa 3: Identificação, Protocolo e Menu Principal (Pós-Consentimento)

Regra: Agora que temos permissão, capturamos o dado.

Bot: "Obrigado pela confiança! "

Bot: "Para agilizar, por favor digite seu Nome Completo:" (Sistema grava variável global: {{nome_cliente}})

Bot: "Seja bem-vindo, {{nome_cliente}}!"

Etapa 4: Menu Global (O Hub)

Fluxo Pós-Consentimento (Ao clicar em "Sim")

Regra: Exibição das opções de atendimento.

Bot: "Selecione o departamento com o qual deseja falar:"

[1] Atendimento ao Cliente-(Informações Gerais, Guias, Quadro Médico)

[2] Agendamentos-(Marcar, Verificar, Reagendar, Cancelar)

[3] Exames e Diagnósticos-(Resultados, Preparos, Agendamento de Exames)

[4] Tesouraria-(Financeiro, Pagamentos, Notas Fiscais)

[5] Orçamentos e Internação(Cirurgias, Procedimentos, Valores Particulares)

[6] Portaria e Recepção(Visitas, Localização, Informações do PS)

[7] Outras Informações(Manual do Paciente, Dúvidas Técnicas)

[8] Ouvidoria(Elogios, Sugestões, Reclamações)

Requisitos para Configuração (TI)

Prioridade do Link: O link https://bit.ly/3QJXkWw deve ser clicável e enviado na mensagem da Etapa 2.

Travamento de Sessão: O sistema não deve permitir que o usuário pule para a Etapa 3 digitando texto livre. Ele deve forçar o clique no botão "Sim, concordo" ou a digitação do número "1".

Log de Aceite: O sistema deve registrar internamente que o usuário {{telefone}} deu o aceite na {{data_hora}} (para fins de auditoria jurídica).

Fluxograma:

Infográfico:

Seguem algumas referências de Sistema de Atendimento pelo WhatsApp.

LInk: https://hnsn.com.br/   (PB)                               Link: https://www.cerdil.com.br/  (MS)

Link: https://hospitalsiriolibanes.org.br/unidades/bela-vista/  (SP)

Link: https://www2.hapvida.com.br/boas-vindas (MS)

Link: Home - Hospital Santa Júlia
