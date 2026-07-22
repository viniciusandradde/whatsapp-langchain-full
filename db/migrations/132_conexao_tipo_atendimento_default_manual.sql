-- Conexão nova nasce com IA DESLIGADA (tipo_atendimento = 'manual').
--
-- Incidente 2026-07-22 (empresa Luis Fernando): empresa recém-criada +
-- WhatsApp conectado → bot respondia imediatamente com o agente legacy do
-- catálogo, antes de qualquer configuração. A partir daqui o admin configura
-- o agente e liga a IA explicitamente no select da tela de conexões.
--
-- Só muda o DEFAULT — rows existentes ficam como estão (empresas em produção
-- continuam com 'ia' e nada muda pra elas).

ALTER TABLE conexao
    ALTER COLUMN tipo_atendimento SET DEFAULT 'manual';
