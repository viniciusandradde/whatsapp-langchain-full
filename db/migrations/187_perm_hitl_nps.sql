-- ADR-002, Etapa 2 — 2 permissões novas para as rotas que ficaram sem gate
-- na Etapa 1 por dependerem de código inexistente no catálogo.
--
-- `atendimento.hitl.approve` — aprovar/rejeitar ação do agente pendente de
-- revisão humana (`routes/hitl.py`, tools transfer_to_human/
-- cancelar_agendamento/criar_agendamento). É supervisão sobre o agente, não
-- operação de linha: vai pro Admin e pro Gestor, NÃO pro Operador.
--
-- `relatorio.nps.read` — dashboards de NPS/CSAT (`routes/relatorios_nps.py`,
-- `/dashboard/qualidade`). Leitura de acompanhamento: vai pro Admin, Gestor
-- e Leitura (o perfil já existe pra "auditoria e acompanhamento").
--
-- Admin recebe as duas automaticamente (perfil "all" no código — não precisa
-- de INSERT aqui, só as empresas que JÁ semearam Admin explicitamente no
-- banco precisam do grant direto, senão o card older fica esperando redeploy).

INSERT INTO permissao (codigo, descricao, modulo)
VALUES
    ('atendimento.hitl.approve',
        'Aprovar/rejeitar ação do agente pendente de revisão humana (HITL)',
        'atendimento'),
    ('relatorio.nps.read', 'Ver dashboards de NPS/CSAT', 'relatorio')
ON CONFLICT (codigo) DO NOTHING;

-- Admin: todas as permissões (perfil "all" no código, mas o perfil já criado
-- no banco tem snapshot fixo de linhas em perfil_permissao — sem este INSERT,
-- só ganharia as novas rodando o script de migração/seed de novo).
INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, p.codigo
  FROM perfil_acesso pa
 CROSS JOIN permissao p
 WHERE pa.is_system = TRUE
   AND pa.nome = 'Admin'
   AND p.codigo IN ('atendimento.hitl.approve', 'relatorio.nps.read')
ON CONFLICT DO NOTHING;

-- Gestor: as duas.
INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, p.codigo
  FROM perfil_acesso pa
 CROSS JOIN permissao p
 WHERE pa.is_system = TRUE
   AND pa.nome = 'Gestor'
   AND p.codigo IN ('atendimento.hitl.approve', 'relatorio.nps.read')
ON CONFLICT DO NOTHING;

-- Leitura: só a de leitura (NPS é dashboard; HITL é ação).
INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, 'relatorio.nps.read'
  FROM perfil_acesso pa
 WHERE pa.is_system = TRUE
   AND pa.nome = 'Leitura'
ON CONFLICT DO NOTHING;

-- Operador: nenhuma das duas (linha de frente, não supervisão/dashboard).
