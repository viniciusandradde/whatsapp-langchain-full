-- Sprint M.4-M.5: popular knowledge base por setor.
--
-- Cria 8 pastas (uma por agente) + ~3 FAQs cada + vincula `agente_ia.base_conhecimento_ids`.
--
-- Idempotente: usa DELETE+INSERT por nome_pasta pra permitir re-runs com conteúdo atualizado.
--
-- Após rodar este script, re-rode o backfill de chunks pra gerar embeddings:
--   docker exec chat-nexus-api python -c "
--     import asyncio
--     from whatsapp_langchain.shared.db import get_pool
--     from whatsapp_langchain.shared.base_conhecimento import backfill_chunks
--     async def m():
--         pool = await get_pool()
--         r = await backfill_chunks(pool)
--         print(r)
--     asyncio.run(m())
--   "

-- ====================================================================
-- 1. CRIAR/ATUALIZAR PASTAS (uma por agente)
-- ====================================================================

INSERT INTO pasta (empresa_id, nome) VALUES
    (1, 'KB Atendimento'),
    (1, 'KB Atendimento Cliente VSA'),
    (1, 'KB Agendamentos'),
    (1, 'KB Exames'),
    (1, 'KB Orçamento'),
    (1, 'KB Ouvidoria'),
    (1, 'KB Recrutamento'),
    (1, 'KB Tesouraria')
ON CONFLICT DO NOTHING;

-- ====================================================================
-- 2. APAGAR DOCS ANTIGOS DAS PASTAS KB (re-run idempotente)
-- ====================================================================

DELETE FROM documento_conhecimento_chunk
 WHERE documento_id IN (
   SELECT id FROM documento_conhecimento
    WHERE empresa_id = 1
      AND pasta_id IN (SELECT id FROM pasta WHERE empresa_id=1 AND nome LIKE 'KB %')
 );

DELETE FROM documento_conhecimento
 WHERE empresa_id = 1
   AND pasta_id IN (SELECT id FROM pasta WHERE empresa_id=1 AND nome LIKE 'KB %');

-- ====================================================================
-- 3. POPULAR DOCS POR SETOR
-- ====================================================================

-- KB Atendimento: dúvidas gerais sobre VSA Tech / produto
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Sobre a VSA Tech',
$texto$
A VSA Tech é uma empresa especializada em automação de atendimento via WhatsApp com agentes de IA.
Nossa solução integra LangGraph + LLMs pra entregar respostas precisas, contextualizadas, com memória de longo prazo.

Principais diferenciais:
- Atendimento 24/7 sem precisar de operador humano pra perguntas simples
- Roteamento automático pro setor correto (Atendimento, Agendamentos, Exames, etc.)
- Memória persistente: lembra do cliente em conversas futuras
- Integração com calendário, CRM e sistemas internos via tools customizadas

Horário do suporte humano: segunda a sexta, 9h às 18h. Fora desse horário, a IA continua atendendo.
$texto$, p.id, TRUE, ARRAY['empresa','sobre']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Atendimento';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Como funciona o atendimento via WhatsApp',
$texto$
Quando o cliente envia uma mensagem, nosso sistema:
1. Identifica o cliente (cadastro automático na primeira mensagem)
2. Mostra menu de opções com 8 setores
3. Encaminha pra IA especialista do setor escolhido
4. Em casos complexos, transfere pra atendente humano qualificado

Posso te ajudar com: agendamento de exames, orçamento, reclamações, contato com setores específicos, e qualquer dúvida sobre nossos serviços.
$texto$, p.id, TRUE, ARRAY['fluxo','atendimento']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Atendimento';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Política de privacidade e LGPD',
$texto$
Seguimos a LGPD (Lei Geral de Proteção de Dados, Lei 13.709/2018):
- Coletamos apenas dados necessários (telefone, nome, histórico de conversas)
- Os dados ficam armazenados no Brasil em servidores criptografados
- Você pode solicitar exclusão de seus dados a qualquer momento via Ouvidoria
- Não compartilhamos seus dados com terceiros sem consentimento

Em caso de incidente de segurança, notificamos a ANPD e os titulares afetados em até 72h.
$texto$, p.id, TRUE, ARRAY['lgpd','privacidade','politica']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Atendimento';

-- KB Atendimento Cliente VSA
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Suporte VIP — clientes VSA',
$texto$
Clientes da plataforma VSA Tech têm canal exclusivo:
- SLA de 2h em horário comercial pra primeira resposta
- Acesso direto a engenheiros sêniores em problemas técnicos
- Atualizações de roadmap antes do release público
- Treinamento mensal gratuito sobre novas features

Pra abrir chamado VIP, mande "ABRIR TICKET" + descrição do problema.
$texto$, p.id, TRUE, ARRAY['vip','cliente']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Atendimento Cliente VSA';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Como atualizar plano',
$texto$
Pra atualizar (upgrade ou downgrade) seu plano:
1. Mande "ATUALIZAR PLANO" + plano desejado (Starter, Pro, Enterprise)
2. Receba a proposta com diferença de valor pro-rata
3. Confirme o pagamento via PIX ou cartão
4. A mudança é efetivada em até 24h

Dúvidas sobre features dos planos: consulte vsanexus.com/planos
$texto$, p.id, TRUE, ARRAY['plano','financeiro']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Atendimento Cliente VSA';

-- KB Agendamentos
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Como agendar uma consulta',
$texto$
Pra agendar:
1. Informe o tipo de consulta (clínico geral, especialista, exame)
2. Eu mostro horários disponíveis nos próximos 14 dias
3. Você escolhe data e horário
4. Confirmo o agendamento e envio comprovante por WhatsApp

Lembretes automáticos: 1 dia antes e 2h antes da consulta.
Cancelamento gratuito: até 24h antes do horário marcado.
$texto$, p.id, TRUE, ARRAY['agendamento','consulta']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Agendamentos';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Política de cancelamento',
$texto$
Cancelamentos:
- Até 24h antes: gratuito, valor estornado em até 5 dias úteis
- Entre 24h e 2h antes: cobrança de 50% do valor
- Menos de 2h antes ou no-show: cobrança integral

Pra cancelar, mande "CANCELAR AGENDAMENTO" + número do agendamento.
$texto$, p.id, TRUE, ARRAY['cancelamento','politica']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Agendamentos';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Reagendamento',
$texto$
Reagendar é simples:
1. Mande "REAGENDAR" + número do agendamento
2. Mostro novos horários disponíveis
3. Confirme a nova data
4. Sem custo adicional se feito com 24h de antecedência

Limite: 2 reagendamentos por consulta.
$texto$, p.id, TRUE, ARRAY['reagendar']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Agendamentos';

-- KB Exames
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Tipos de exame disponíveis',
$texto$
Realizamos os seguintes exames:
- Sangue: hemograma, glicemia, lipidograma, função tireoidiana
- Imagem: raio-X, ultrassom, ressonância, tomografia
- Cardiológicos: ECG, ecocardiograma, MAPA, Holter
- Específicos: PSA, mamografia, papanicolau

Preparo varia por exame — pergunte sobre o seu antes de comparecer.
$texto$, p.id, TRUE, ARRAY['exame','tipos']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Exames';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Como receber resultado de exame',
$texto$
Resultados ficam disponíveis:
- Sangue: 24-48h após coleta
- Imagem (raio-X, US): no mesmo dia (laudo em até 24h)
- Ressonância/Tomografia: 24-72h
- Anatomopatológicos: 5-10 dias úteis

Você recebe notificação por WhatsApp com link seguro pro PDF.
Resultado também disponível no portal do paciente em vsa.com.br/resultados
$texto$, p.id, TRUE, ARRAY['resultado','exame']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Exames';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Preparo para exames de jejum',
$texto$
Para exames que exigem jejum:
- Glicemia, lipidograma: 12h de jejum (água permitida)
- TSH, T3, T4: jejum não obrigatório, mas preferível
- Cortisol: coleta entre 7h e 9h, sem jejum
- Endoscopia: 8h jejum sólido + 4h líquidos claros

Continue tomando seus medicamentos contínuos a menos que orientado o contrário pelo médico.
$texto$, p.id, TRUE, ARRAY['preparo','jejum']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Exames';

-- KB Orçamento
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Como solicitar orçamento',
$texto$
Pra fazer orçamento:
1. Mande os exames/procedimentos desejados (com código TUSS se tiver)
2. Informe se tem convênio (e qual)
3. Recebo orçamento detalhado em até 30min em horário comercial

Orçamento válido por 30 dias. Aceita PIX, cartão (até 12x), boleto.
Desconto de 5% no PIX à vista.
$texto$, p.id, TRUE, ARRAY['orcamento','solicitar']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Orçamento';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Convênios aceitos',
$texto$
Atendemos os convênios:
- Unimed, Bradesco Saúde, SulAmérica, Amil
- Hapvida, NotreDame Intermédica
- Cassi, GEAP, ASEFAZ (federais)
- Particular (com 5% desconto à vista)

Algumas modalidades de plano podem ter coparticipação. Verifique antes de agendar.
$texto$, p.id, TRUE, ARRAY['convenio']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Orçamento';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Formas de pagamento',
$texto$
Aceitamos:
- PIX (5% desconto à vista)
- Cartão de crédito: até 12x sem juros (acima de R$ 500)
- Cartão de débito
- Boleto: vencimento 3 dias após emissão
- Convênio (verificar lista de aceitos)

Para parcelamentos longos (acima de 12x), oferecemos parceria com financeira (sujeito a análise de crédito).
$texto$, p.id, TRUE, ARRAY['pagamento','parcelamento']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Orçamento';

-- KB Ouvidoria
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Como abrir reclamação',
$texto$
Sua reclamação é importante. Pra registrar:
1. Descreva o ocorrido com data, horário, e nome da pessoa envolvida (se souber)
2. Informe o número de protocolo se já houver
3. Anexe fotos/vídeos relevantes via WhatsApp

Resposta em até 5 dias úteis. Casos urgentes (saúde) são tratados em 24h.

Em caso de não resolução, encaminhamos pro Procon ou ANS conforme aplicável.
$texto$, p.id, TRUE, ARRAY['reclamacao','ouvidoria']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Ouvidoria';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Sugestões e elogios',
$texto$
Sua opinião melhora nosso serviço!
- Sugestões: enviadas pra equipe responsável e analisadas mensalmente
- Elogios: encaminhamos pro colaborador citado e equipe gestora
- Críticas construtivas: viram oportunidade de melhoria

Todo feedback é tratado com confidencialidade e gera resposta em até 3 dias.
$texto$, p.id, TRUE, ARRAY['sugestao','elogio']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Ouvidoria';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'LGPD — direitos do titular',
$texto$
Pela LGPD você tem direito a:
- Confirmar se temos seus dados
- Acessar seus dados
- Corrigir dados incorretos
- Solicitar anonimização ou exclusão (quando aplicável)
- Revogar consentimento
- Portar seus dados pra outro fornecedor

Pra exercer qualquer desses direitos, mande "EXERCER DIREITO LGPD" + qual direito + seu CPF.
Resposta em até 15 dias.
$texto$, p.id, TRUE, ARRAY['lgpd','direitos']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Ouvidoria';

-- KB Recrutamento
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Vagas abertas',
$texto$
Vagas atualmente em aberto:
- Engenheiro de Software (Senior, Pleno) — São Paulo, remoto OK
- Atendente de Suporte (Junior) — São Paulo, presencial
- Designer UX/UI (Pleno) — Remoto
- Analista de Dados (Junior, Pleno) — Híbrido

Pra se candidatar, mande "CANDIDATAR" + nome da vaga + currículo (PDF).
Processo: triagem (3 dias) → entrevista RH (1 semana) → técnica → cultural.
$texto$, p.id, TRUE, ARRAY['vagas','recrutamento']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Recrutamento';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Benefícios oferecidos',
$texto$
Pacote padrão para todos os colaboradores:
- Plano de saúde Bradesco Top Plus + odontológico
- Vale-refeição R$ 35/dia útil
- Vale-transporte ou auxílio home-office (R$ 200/mês)
- Day off no aniversário
- 30 dias de férias + 13º salário
- Stock options após 1 ano de empresa
- Subsídio em cursos/conferências (R$ 5.000/ano)
$texto$, p.id, TRUE, ARRAY['beneficios','rh']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Recrutamento';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Processo seletivo',
$texto$
Como funciona nosso processo:
1. Inscrição via WhatsApp ou portal vagas.vsa.com.br
2. Triagem de currículo (3 dias úteis)
3. Entrevista comportamental com RH (50min, online)
4. Desafio técnico (3-5 dias pra resolver)
5. Entrevista técnica (1h, com líder e tech lead)
6. Entrevista cultural (45min, com fundadora)
7. Proposta + onboarding

Tempo médio total: 3 a 4 semanas.
$texto$, p.id, TRUE, ARRAY['processo','etapas']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Recrutamento';

-- KB Tesouraria
INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Segunda via de boleto',
$texto$
Pra emitir 2ª via de boleto:
1. Informe seu CPF/CNPJ
2. Confirmo identidade com nome e data de nascimento
3. Envio o boleto atualizado em PDF

Boletos vencidos: o sistema gera nova data com correção (multa 2% + juros 1%/mês).
Após 60 dias de atraso, o título é encaminhado pra cobrança terceirizada.
$texto$, p.id, TRUE, ARRAY['boleto','segunda-via']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Tesouraria';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Negociação de débitos',
$texto$
Tem débito em aberto? Podemos negociar:
- Parcelamento em até 12x no boleto
- Desconto de até 30% pra pagamento à vista
- Carência de até 30 dias dependendo do valor

Pra iniciar, mande "NEGOCIAR" + valor aproximado da dívida.
Atendimento financeiro: segunda a sexta, 9h às 17h.
$texto$, p.id, TRUE, ARRAY['negociacao','divida']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Tesouraria';

INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo, pasta_id, ativo, tags)
SELECT 1, 'Reembolso',
$texto$
Solicitação de reembolso:
1. Mande "REEMBOLSO" + nota fiscal/recibo + motivo
2. Análise em até 5 dias úteis
3. Aprovado: crédito em até 7 dias na conta cadastrada
4. Reprovado: justificativa por escrito com base em contrato

Reembolso total: cancelamento até 7 dias após emissão da nota (CDC art. 49).
Reembolso parcial: caso a caso, conforme política comercial.
$texto$, p.id, TRUE, ARRAY['reembolso','financeiro']
FROM pasta p WHERE p.empresa_id=1 AND p.nome='KB Tesouraria';

-- ====================================================================
-- 4. VINCULAR CADA AGENTE À SUA PASTA
-- ====================================================================

UPDATE agente_ia ai
   SET base_conhecimento_ids = ARRAY[p.id]::bigint[]
  FROM pasta p
 WHERE ai.empresa_id = 1
   AND p.empresa_id = 1
   AND (
     (ai.slug = 'atendimento'             AND p.nome = 'KB Atendimento') OR
     (ai.slug = 'atendimento-cliente'     AND p.nome = 'KB Atendimento Cliente VSA') OR
     (ai.slug = 'agendamentos'            AND p.nome = 'KB Agendamentos') OR
     (ai.slug = 'exames'                  AND p.nome = 'KB Exames') OR
     (ai.slug = 'orcamento'               AND p.nome = 'KB Orçamento') OR
     (ai.slug = 'ouvidoria'               AND p.nome = 'KB Ouvidoria') OR
     (ai.slug = 'rh-recrutamento-selecao' AND p.nome = 'KB Recrutamento') OR
     (ai.slug = 'tesouraria'              AND p.nome = 'KB Tesouraria')
   );

-- Verificação final
SELECT ai.slug, ai.base_conhecimento_ids,
       (SELECT COUNT(*) FROM documento_conhecimento dc
         WHERE dc.empresa_id=1 AND dc.pasta_id = ANY(ai.base_conhecimento_ids)) as docs_vinculados
  FROM agente_ia ai
 WHERE ai.empresa_id = 1
 ORDER BY ai.slug;
