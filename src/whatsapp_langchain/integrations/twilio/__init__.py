"""Integração Twilio Content API (templates HSM via BSP).

Submódulos:
- `content`: criação/submissão/sync/listagem de templates via Content API
  (content.twilio.com). Twilio é Business Solution Provider — templates vão
  pra aprovação Meta por baixo dos panos e viram um ContentSid (HX...).

Diferente de `integrations/waba` (Meta Cloud API direto), aqui o submit é
em 2 passos: cria o Content, depois submete o ApprovalRequest/whatsapp.
"""
