-- Plano "Pessoal" — R$97/mês, entre Free e Pro.
--
-- Perfil: pessoa física/MEI com 1 número e 1-2 usuários que quer o inbox
-- organizado + IA leve, sem os módulos de operação (disparador, campanhas,
-- RBAC, calendar). Limites apertados de propósito: quem crescer migra
-- naturalmente pro Pro. Anual = 2 meses grátis (R$970).
--
-- Idempotente (ON CONFLICT/updates absolutos): roda de novo sem efeito.

INSERT INTO plano (nome, slug, descricao,
                   preco_mensal_brl, preco_anual_brl,
                   limite_usuarios, limite_conexoes, limite_atendimentos_mes,
                   limite_orcamento_ia_usd, limite_documentos_kb,
                   features, ativo, ordem)
VALUES ('Pessoal', 'pessoal',
        'Pra uso pessoal ou MEI: 1 número de WhatsApp, inbox organizado e IA com consumo controlado.',
        97.00, 970.00,
        2, 1, 500,
        10.00, 20,
        '{"mcp": false, "rbac": false, "calendar": false, "disparador": false, "menu_moderno": false, "disparador_media": false}'::jsonb,
        TRUE, 2)
ON CONFLICT (slug) DO NOTHING;

-- Reordena os planos acima do novo (Free=1, Pessoal=2, Pro=3, Enterprise=4).
UPDATE plano SET ordem = 3 WHERE slug = 'pro';
UPDATE plano SET ordem = 4 WHERE slug = 'enterprise';
