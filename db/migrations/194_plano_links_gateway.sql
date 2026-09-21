-- 194: ADR-005 leva F — cobrança por planos hospedados nos gateways (D7/D12).
--
-- O dono cria cada plano no painel da InfinitePay (Cobrança Recorrente —
-- padrão, "Recomendado" no /billing) e do Mercado Pago (Assinaturas —
-- alternativa) e cola o LINK aqui; o Nexus só mostra os links ao cliente.
-- NULL = plano sem venda self-service (Free e Enterprise). Não há API de
-- cobrança: a ativação é o superadmin registrando o pagamento
-- (`POST /api/empresas/{id}/pagamentos`), que grava em `transacao` e
-- estende `empresa.plano_valido_ate` (leva E).
--
-- `transacao.gateway` continua TEXT livre; valores usados a partir daqui:
-- 'mercadopago' | 'infinitepay' | 'manual' ('asaas' fica no histórico).

ALTER TABLE plano
    ADD COLUMN IF NOT EXISTS link_mercadopago TEXT,
    ADD COLUMN IF NOT EXISTS link_infinitepay TEXT;

COMMENT ON COLUMN plano.link_mercadopago IS
    'ADR-005 leva F: link da assinatura hospedada no Mercado Pago (cartão/saldo); NULL = sem venda self-service';
COMMENT ON COLUMN plano.link_infinitepay IS
    'ADR-005 leva F: link da cobrança recorrente hospedada na InfinitePay (Pix ou cartão) — padrão/Recomendado; NULL = sem venda self-service';

-- Links criados pelo dono em 21/09/2026 (F.0). Idempotente; o superadmin
-- pode trocar depois em /billing sem migration.
UPDATE plano SET
    link_infinitepay = 'https://invoice.infinitepay.io/plans/vinicius-souza-z92/D5zAMaUxnL',
    link_mercadopago = 'https://mpago.la/14ot22B',
    updated_at = NOW()
 WHERE slug = 'pessoal';

UPDATE plano SET
    link_infinitepay = 'https://invoice.infinitepay.io/plans/vinicius-souza-z92/VfIOOfHlsd',
    link_mercadopago = 'https://mpago.la/2B1hHVW',
    updated_at = NOW()
 WHERE slug = 'pro';
