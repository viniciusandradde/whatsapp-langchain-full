-- 202: timeline mostra o texto do modelo (HSM) enviado, não "[template x]"
--
-- `send_template_by_id` gravava na timeline `[template <nome>] no variables`
-- — o operador não via o que o cliente recebeu (conversa 878 da empresa 1025,
-- 24/09/2026). O código passa a gravar cabeçalho + corpo + rodapé com as
-- variáveis trocadas (`integrations/waba/templates.py::texto_do_template`).
--
-- Este UPDATE corrige as linhas antigas SEM variáveis (em 24/09 eram as 3 do
-- estoque em produção, todas "no variables"): mesmo formato do código, pelo
-- modelo da própria conexão com o mesmo nome. Linhas com variáveis ficam como
-- estão — o valor enviado não está guardado em forma recuperável.

SELECT set_config('app.bypass_rls', 'true', true);

UPDATE message_queue mq
   SET response = concat_ws(
           E'\n\n',
           (SELECT '*' || (c->>'text') || '*'
              FROM jsonb_array_elements(t.componentes_json) c
             WHERE upper(c->>'type') = 'HEADER'
               AND upper(coalesce(c->>'format', 'TEXT')) = 'TEXT'
               AND coalesce(c->>'text', '') <> ''
             LIMIT 1),
           (SELECT c->>'text'
              FROM jsonb_array_elements(t.componentes_json) c
             WHERE upper(c->>'type') = 'BODY'
             LIMIT 1),
           (SELECT '_' || (c->>'text') || '_'
              FROM jsonb_array_elements(t.componentes_json) c
             WHERE upper(c->>'type') = 'FOOTER'
               AND coalesce(c->>'text', '') <> ''
             LIMIT 1)
       )
  FROM waba_template t
 WHERE mq.response = '[template ' || t.nome || '] no variables'
   AND t.conexao_id = mq.conexao_id
   AND EXISTS (
       SELECT 1 FROM jsonb_array_elements(t.componentes_json) c
        WHERE upper(c->>'type') = 'BODY' AND coalesce(c->>'text', '') <> ''
   );
