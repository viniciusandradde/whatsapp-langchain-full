-- Sprint 6 — Paridade ZigChat (PushDevice — notificações mobile pra atendentes).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md
--
-- Atendentes em apps mobile registram device tokens (FCM/APNS).
-- Backend manda push quando atendimento novo entra na fila do depto deles.

CREATE TABLE IF NOT EXISTS push_device (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,                 -- Better Auth user
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    device_token TEXT NOT NULL,
    device_type TEXT NOT NULL
        CHECK (device_type IN ('ios', 'android', 'web')),
    device_name TEXT,                      -- "iPhone 15 Pro", "Pixel 8"
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_uso_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (device_token)
);

CREATE INDEX IF NOT EXISTS idx_push_device_user
    ON push_device (user_id, empresa_id) WHERE ativo;
