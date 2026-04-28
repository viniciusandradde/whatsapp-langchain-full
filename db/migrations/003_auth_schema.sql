-- Cria o schema "auth" para separação lógica das tabelas do Better Auth.
-- O Better Auth usa este schema via search_path na connection string do frontend.
-- As tabelas da aplicação (message_queue, conversations, etc.) permanecem no schema "public".
CREATE SCHEMA IF NOT EXISTS auth;
