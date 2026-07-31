-- Remove o schema da integração Wareline ConecteHub.
--
-- Decisão de produto em 2026-07-31: integração externa passa a ser API REST +
-- webhook genéricos (`api_connection`, migration 091), que cobrem o mesmo caso
-- sem um provider dedicado no código.
--
-- Seguro: as duas tabelas estavam VAZIAS em produção (0 linhas em
-- `wareline_credentials` e `wareline_token_cache`) — nenhuma empresa chegou a
-- configurar a integração. Verificado antes de escrever esta migration.
--
-- O agente `agendamentos`, que usava as 3 tools do Wareline, foi religado nas
-- tools de Google Calendar. A chave de cifra continua a mesma
-- (`WARELINE_ENCRYPTION_KEY` segue aceita como alias de
-- `INTEGRACOES_ENCRYPTION_KEY`) porque protege `api_connection`, que fica.

DROP TABLE IF EXISTS wareline_token_cache;
DROP TABLE IF EXISTS wareline_credentials;

-- A permissão sai junto: nada mais a gerenciar.
DELETE FROM perfil_permissao WHERE permissao_codigo = 'integracao.wareline.manage';
DELETE FROM permissao WHERE codigo = 'integracao.wareline.manage';
