-- 195: corrige o seed dos links da InfinitePay (ADR-005 leva F).
--
-- A mig 194 semeou os links da conta `vinicius-souza-z92`; logo após o
-- merge o dono migrou os planos para a conta `vsa-tecnologia` (o Pessoal
-- ganhou id novo; Pro e Enterprise mantiveram o id). Em produção e no dev
-- a troca já foi feita pelo editor do superadmin (`PUT
-- /api/billing/planos/{slug}/links`), então aqui é no-op — a migration
-- existe para uma instalação nova não nascer com link morto.
--
-- Só substitui o seed antigo: link trocado à mão pelo /billing fica como
-- está (o WHERE casa apenas o prefixo da conta antiga). Mercado Pago não
-- muda.

UPDATE plano SET
    link_infinitepay = 'https://invoice.infinitepay.io/plans/vsa-tecnologia/y3lpTMjINF',
    updated_at = NOW()
 WHERE slug = 'pessoal'
   AND link_infinitepay LIKE 'https://invoice.infinitepay.io/plans/vinicius-souza-z92/%';

UPDATE plano SET
    link_infinitepay = 'https://invoice.infinitepay.io/plans/vsa-tecnologia/VfIOOfHlsd',
    updated_at = NOW()
 WHERE slug = 'pro'
   AND link_infinitepay LIKE 'https://invoice.infinitepay.io/plans/vinicius-souza-z92/%';

UPDATE plano SET
    link_infinitepay = 'https://invoice.infinitepay.io/plans/vsa-tecnologia/oPYQeXNaNw',
    updated_at = NOW()
 WHERE slug = 'enterprise'
   AND link_infinitepay LIKE 'https://invoice.infinitepay.io/plans/vinicius-souza-z92/%';
