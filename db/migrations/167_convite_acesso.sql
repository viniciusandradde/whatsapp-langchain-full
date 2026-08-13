-- Convite de acesso por WhatsApp: rastro do último envio.
--
-- Ao criar um usuário, o admin pode mandar no WhatsApp dele um link de uso
-- único que expira (o fluxo de reset do Better Auth, mig 025) em vez de
-- repassar a senha à mão. `convite_enviado_at` registra quando o último
-- convite SAIU — a lista de usuários mostra, e o botão "reenviar" ganha
-- contexto ("último convite há 3 dias").
--
-- Só a data. O link NÃO é persistido aqui de propósito: ele já vive em
-- auth.password_reset_pending com expiração de 1h, e duplicá-lo em outra
-- coluna dobraria a superfície de vazamento de um segredo que dá acesso à
-- conta.
--
-- Sem bloco de RLS: auth.* é o schema do Better Auth, fora do FORCE RLS das
-- tabelas de tenant (auth."user" não tem empresa_id — membership vive em
-- empresa_membro).

ALTER TABLE auth."user"
    ADD COLUMN IF NOT EXISTS convite_enviado_at TIMESTAMPTZ;

COMMENT ON COLUMN auth."user".convite_enviado_at IS
    'Quando o último convite de acesso (link de definição de senha) foi '
    'enviado no WhatsApp do usuário. NULL = nunca.';

-- Backfill dos telefones existentes para o formato completo (+55 DDD linha).
-- Em produção há exatamente 2 usuários com telefone; o da empresa 1 está sem
-- DDD (+55996460034) e é INCORRIGÍVEL por UPDATE — não dá para adivinhar o
-- DDD aqui. Normalizamos o que der (10-11 dígitos ganham 55) e deixamos o
-- resto como está: a validação nova só se aplica a escritas novas, e a tela
-- passa a exigir o formato completo na próxima edição.
UPDATE auth."user"
   SET telefone = '+55' || regexp_replace(telefone, '\D', '', 'g')
 WHERE telefone IS NOT NULL
   AND length(regexp_replace(telefone, '\D', '', 'g')) IN (10, 11);
