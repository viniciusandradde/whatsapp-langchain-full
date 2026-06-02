-- WABA-first: marca o Twilio como LEGADO (não destrutivo).
--
-- O Twilio segue funcionando (provider ainda no CHECK; conexões existentes
-- intactas), mas deixa de ser o caminho recomendado — o WhatsApp oficial
-- (Meta Cloud API / WABA) é o default. A remoção do Twilio fica pro futuro.
--
-- Aqui só marcamos a conexão bootstrap `twilio_sandbox` (+14155238886, criada
-- na mig 009) com `payload_json.legacy=true` pra a UI poder sinalizar e pra
-- não tratá-la como conexão "de verdade" em telas novas.

UPDATE conexao
   SET payload_json = COALESCE(payload_json, '{}'::jsonb)
                      || jsonb_build_object('legacy', true),
       updated_at = NOW()
 WHERE provider = 'twilio_sandbox'
   AND payload_json->>'bootstrap' = 'true'
   AND COALESCE(payload_json->>'legacy', 'false') <> 'true';
