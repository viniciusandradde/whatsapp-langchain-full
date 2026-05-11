Hospital Presbiteriano Mackenzie Dr. e Sra. Goldsby King

MENU Agendamento (2) (Modelo Human‑in‑the‑Loop)

Projeto: Otimização ZigChat - Hospital Presbiteriano Mackenzie Modelo: Triagem Inteligente (Human-in-the-Loop)

Objetivo Estratégico

Otimizar a ocupação da agenda médica e reduzir o tempo operacional da recepção. O Assistente Virtual atua para:

Entregar o Paciente Pronto: Coleta previamente Nome, Especialidade e Preferência de Horário, eliminando a triagem manual.

Rota Expressa de Cardiologia: Desvia pacientes de exames específicos para o setor correto (Ambulatório), desafogando a fila geral.

Retenção de Receita: Diferencia proativamente quem quer Cancelar (libera vaga) de quem pode Reagendar (mantém o faturamento).

1. Menu de Entrada (Agendamento)

Gatilho: Seleção da opção de agendamento no Menu Principal.

Bot: "Você está na Central de Agendamentos do Hospital Presbiteriano Mackenzie - Dr. e Sra. Goldsby King. "

Bot: "Selecione como podemos te ajudar:"

[1] Marcar Consulta

[2] Verificar meu agendamento

[3] Reagendar ou Solicitar Encaixe

[4] Cancelar Consulta

[5] Exames Cardiológicos

[6] Retornar ao Menu Principal

2. Fluxo – Marcar Consulta (Opção 1)

Passo 1.1 – Coleta de Dados: Solicitar Nome, CPF e Data de Nascimento.

"Certo! Para iniciarmos, por favor digite o Nome Completo e a Data de Nascimento (DD/MM/AAAA) do PACIENTE que será consultado."

Passo 1.2 – Especialidades disponíveis:

Bot: "Agora, selecione a Especialidade desejada:"

(Lista botões 1 a 8. Grava em {{especialidade}})

[1] Urologia

[2] Ortopedia

[3] Clínico-Geral

[4] Reumatologia

[5] Oncologia

[6] Otorrinolaringologia

[7] Exames/Cardiologicos

Exames/Cardiologia (Quebrado em Etapas)

Bot: "Entendido. Para garantir um atendimento especializado, o agendamento de Cardiologia e Exames Cardiológicos é realizado por um setor exclusivo. "

Bot: "Estou transferindo você agora mesmo para a fila de Exames/Cardiologia. Aguarde um momento que um especialista já vai te atender."

(Ação do Sistema: Transbordo Imediato para a Fila "Cardiologia/Exames")

Obs: Cenário: O cliente entrou em "Marcar Consulta" e, na lista de especialidades, escolheu [7] Cardiologia. Lógica: Transferência imediata para o setor de "Exames/Cardiologia", pois eles têm uma agenda separada/específica porém sugiro o menu exclusivo para apontar para atendente do setor correto (logado)

[8] Gastroenterologia / Cirurgia Geral

[9] Voltar ao Menu Principal

Bot: "Você tem preferência por atendimento pela Manhã ou Tarde? (Ou digite o nome de um médico específico."

(Grava em {{preferencia_horario}})

Bot: "Perfeito. Transferindo para a central... Um atendente vai verificar a disponibilidade mais próxima para {{preferencia_horario}} e confirmar com você agora."

(Handover: O atendente recebe: "João quer Urologia, prefere Manhã".)

3. Fluxo – Reagendamento e Encaixe (Foco em Retenção)

Cenário: O paciente precisa mudar a data ou tem urgência para ser atendido em uma agenda cheia.

Passo 1: Identificação e Triagem

Bot: "Entendido. Vamos ajustar sua agenda para o melhor momento. 🗓️" Bot: "Para localizar seu cadastro, digite o CPF do Paciente:" (Sistema grava em {{cpf_paciente}})

Passo 2: Definição da Necessidade (O Filtro)

Bot: "Qual é a sua necessidade atual? Escolha uma opção:" [1] Reagendar: Já tenho consulta, mas quero trocar a data. [2] Solicitar Encaixe: Preciso de um horário urgente/mais próximo. (Sistema grava em {{tipo_solicitacao_agenda}})

Passo 3 (Cenário A): Se escolheu REAGENDAR

Bot: "Certo. Para qual dia da semana ou período (manhã/tarde) você prefere a nova data?" (Cliente digita: "Próxima terça à tarde")(Sistema grava em {{preferencia_nova_data}})

Bot: "Anotado. Vou transferir para a equipe verificar a disponibilidade nessa data e confirmar a troca agora mesmo."

Passo 3 (Cenário B): Se escolheu ENCAIXE

Bot: "Compreendo. Vamos tentar priorizar seu caso." Bot: "Para qual Especialidade ou Médico você precisa desse encaixe urgente?" (Cliente digita: "Dra. Ana, Pediatria")(Sistema grava em {{alvo_encaixe}})

Bot: "Registrado como prioridade. Um atendente vai verificar a lista de espera e te informar as possibilidades agora."

Fluxo 4: Cancelar Consulta (Foco em Liberação de Vaga)

Cenário: O paciente decidiu não ir. O objetivo é ser rápido para liberar a vaga no sistema.

Passo 1: Identificação

Bot: "Poxa, sentimos muito que você não possa comparecer. " Bot: "Para darmos baixa no sistema, informe o CPF do Paciente:" (Sistema grava em {{cpf_paciente}})

Passo 2: Qualificação (Importante para o Hospital)

Bot: "Qual consulta você deseja cancelar? (Ex: Cardiologista amanhã, ou Dr. João)." (Cliente digita)(Sistema grava em {{consulta_cancelar}})

Passo 3: Motivo ( Relatório/Indicadores )

Bot: "Para nos ajudar a melhorar, qual o motivo do cancelamento?" [1] Imprevisto Pessoal [2] Já resolvi o problema [3] Atendimento demorado [4] Outros (Sistema grava em {{motivo_cancelamento}})

Passo 4: Handover (Passagem de Bastão)

Bot: "Entendido. Estou encaminhando para a central liberar sua vaga imediatamente." Bot: "Um atendente vai apenas confirmar a exclusão com você. Aguarde um instante."

5. Voltar ao Menu Principal (Opção 5)

Acessado via Opção 5 do Menu Principal OU Opção 7 do Menu "Marcar Consulta".

Cenário: O setor de Cardiologia fica fisicamente no Ambulatório e possui agenda separada.

Script de Transbordo:

Bot: "Entendido. Para garantir um atendimento especializado, o agendamento de Cardiologia e Exames (ECG, Holter, etc) é realizado por um setor exclusivo."

Bot: "Estou transferindo você agora mesmo para a fila de Exames/Cardiologia. Aguarde um momento que um especialista já vai te atender."

Obs: Configuração Técnica no ZigChat (Observação Crítica):

Destino: Esta opção deve apontar o transbordo diretamente para o Departamento/Usuário: "Exames/Cardiologia".

Não misturar: O cliente NÃO deve cair na fila "Recepção Geral". Isso garante que quem atenderá será o funcionário que já está logado no setor do Ambulatório.

6. Fluxo – Voltar ao Menu Principal (Loop de Retorno)

Cenário: O cliente entrou em Agendamento, mas decidiu tratar de outro assunto (ex: Financeiro ou Portaria).

Script de Transição:

(Cliente seleciona opção 6)

Bot: "Entendido. Retornando ao menu inicial... " Bot: "Aqui estão todas as opções de atendimento do Hospital Presbiteriano Mackenzie. Por favor, escolha o setor desejado:"

Ação do Sistema:

O Bot encerra o fluxo de "Agendamento".

O Bot dispara imediatamente o Menu Global (Root) abaixo.

Fluxograma:

Infográfico:
