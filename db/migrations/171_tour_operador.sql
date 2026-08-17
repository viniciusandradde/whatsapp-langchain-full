-- 171 — Marca de "já vi o guia de primeiro acesso", por USUÁRIO.
--
-- Motivo: quem recebe a senha pelo convite entra e não sabe onde atender. O
-- wizard existente (`/onboarding`, mig 160) NÃO serve: o estado dele é da
-- EMPRESA ("já configurou?"), então operador em empresa configurada nunca o
-- vê, e em empresa nova ele cai numa tela de botões de admin.
--
-- Precisa ser por usuário e no BANCO: localStorage não atravessa aparelho
-- nem navegador, e o operador entra do celular e do desktop.
--
-- `last_login_at` (mig 106) não serve de proxy — o trigger preenche no
-- próprio login, então na primeira leitura já está preenchido.
ALTER TABLE auth."user"
  ADD COLUMN IF NOT EXISTS tour_operador_at TIMESTAMPTZ;

COMMENT ON COLUMN auth."user".tour_operador_at IS
  'Quando o usuário viu (ou dispensou) o guia de primeiro acesso até a Fila de atendimento (mig 171). NULL = ainda não viu.';
