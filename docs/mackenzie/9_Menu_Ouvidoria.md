MENU OUVIDORIA (8) (Modelo Human‑in‑the‑Loop)
Hospital Presbiteriano Mackenzie Evangélico Dr. e Sra. Goldsby King

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Escuta Ativa e Compliance

Objetivo Estratégico

Transformar a Ouvidoria em um canal de Resolução de Conflitos e Inteligência de Qualidade.

Acolhimento Imediato: O bot valida o sentimento do usuário (agradece o elogio ou lamenta a reclamação) antes de pedir dados, gerando empatia.

Segurança Jurídica (Prontuários): Estrutura a solicitação de documentos médicos exigindo a identificação correta (Titular vs Representante).

Canal de Ética: Separa "Reclamação de Atendimento" de "Denúncia de Irregularidade", garantindo o sigilo necessário.

Estrutura do Menu Principal (Ouvidoria)

Bot: "Você está na Ouvidoria. Este é o canal oficial para nos ouvir. Selecione a opção:"

[1] Deixar uma Reclamação, Elogio ou Sugestão(Manifestações sobre atendimento e estrutura)

[2] Canal de Denúncia (Sigilo/Ética)(Relatar irregularidades ou conduta inadequada)

[3] Solicitar Cópia de Prontuário Médico(Documentação do paciente)

[4] Consultar Andamento de Protocolo(Verificar status de uma solicitação anterior)

[5] Voltar ao Menu Principal

Detalhamento dos Fluxos (Regras de Negócio)

Fluxo 1: Reclamação, Elogio ou Sugestão (Experiência)

Regra: Triagem do "Sentimento" do usuário.

Classificação:Bot: "Queremos muito saber sua opinião. Do que se trata?"

[A] Reclamação / Insatisfação

[B] Elogio

[C] Sugestão (Sistema grava: {{tipo_manifestacao}})

Cenário A (Reclamação):

Bot: "Sinto muito que sua experiência não tenha sido a ideal.  Vamos apurar o ocorrido."

Bot: "Por favor, descreva o que aconteceu (informe data, setor e nomes se souber):" (Sistema grava: {{relato_ouvidoria}})

Cenário B (Elogio):

Bot: "Que notícia ótima! Ficamos felizes em saber. "

Bot: "Quem ou qual setor você gostaria de elogiar?" (Sistema grava: {{relato_ouvidoria}})

Encerramento:

Bot: "Registrado. Seu protocolo é {{novo_protocolo}}. Encaminharemos para a gestão responsável."

Fluxo 2: Canal de Denúncia (Ética)

Regra: Garantia de Anonimato (Compliance).

Aviso de Sigilo:

Bot: "Este canal é seguro e segue as diretrizes de Compliance. "

Bot: "Você deseja se identificar ou prefere fazer uma denúncia anônima?"

[1] Quero me Identificar

[2] Quero Anonimato(Sistema grava: {{tipo_denuncia}})

Relato:Bot: "Pode relatar o fato. Se tiver provas (fotos/documentos), poderá enviar em seguida." (Sistema grava: {{relato_denuncia}})

Encerramento:Bot: "Sua denúncia foi recebida e será tratada pelo Comitê de Ética com total confidencialidade."

Fluxo 3: Solicitar Prontuário Médico

Regra: Validação de Legitimidade (LGPD/CFM).

Identificação do Solicitante:Bot: "O Prontuário é um documento sigiloso. Quem está solicitando?"

[1] Sou o Próprio Paciente

[2] Sou Responsável Legal / Parente(Sistema grava: {{tipo_solicitante}})

Dados do Paciente:Bot: "Digite o Nome Completo do Paciente e a Data de Nascimento:" (Sistema grava: {{dados_paciente_prontuario}})

Formato:Bot: "Você prefere receber o arquivo digital (PDF por e-mail) ou retirar a cópia física?"

[A] Digital (E-mail)

[B] Físico (Impresso)(Sistema grava: {{formato_prontuario}})

Encerramento:Bot: "Solicitação aberta. Nossa equipe entrará em contato para conferir seus documentos e liberar o prontuário (Prazo estimado: 7 a 15 dias)."

Fluxo 4: Consultar Andamento

Regra: Transparência.

Identificação:Bot: "Digite o Número do Protocolo que você recebeu:" (Sistema grava: {{numero_protocolo_busca}})

Ação:

Bot: "Localizando... "

Bot: "Status atual: Em Análise / Concluído. [Inserir resposta do sistema se houver integração]." (Se não houver integração, transbordo para humano informar).

Fluxo 5: Voltar ao Menu Principal

Bot: "Retornando ao menu inicial... "

Requisitos para Configuração (TI)

Para o funcionamento correto, configurar as seguintes variáveis de entrada no ZigChat:

{{tipo_manifestacao}}: Botões (Reclamação/Elogio/Sugestão).

{{relato_ouvidoria}}: Texto livre (Longo).

{{tipo_denuncia}}: Botões (Identificado/Anônimo).

{{tipo_solicitante}}: Botões (Crítico para a equipe jurídica saber quais documentos pedir depois).

Fluxograma:

Infográfico:
