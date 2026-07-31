-- Transforma uma cópia do banco de produção num banco de desenvolvimento.
--
-- Roda SEMPRE sobre uma restauração descartável, nunca contra produção. O
-- `00-exportar.sh` garante isso: ele restaura o dump numa base temporária,
-- aplica este arquivo lá, re-exporta e derruba a base.
--
-- Duas coisas acontecem aqui, e a ordem importa:
--
--   1. APAGA o que não dá pra anonimizar. As tabelas do LangGraph guardam a
--      conversa inteira serializada em binário — não existe UPDATE que limpe
--      isso. Como são regeneráveis (o agente reconstrói o estado na próxima
--      mensagem), vão embora inteiras. São 715 MB dos 1.122 MB do banco.
--
--   2. EMBARALHA o que dá, preservando o formato. Telefone continua com cara
--      de telefone e CPF com cara de CPF, senão o ambiente de dev para de
--      exercitar as validações de `lib/br-validators` e os lookups com/sem o
--      nono dígito (`shared/whitelist.py::candidatos_lookup`).
--
-- O que fica intacto de propósito: empresa, agente_ia, perfil_acesso,
-- permissao, menu_*, workflow_*, documento_conhecimento*, modelo_llm, tag.
-- É configuração do produto, não dado de cliente — e é o que você precisa
-- pra desenvolver.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Estado do LangGraph e fila — apagados, não anonimizados
-- ---------------------------------------------------------------------------

-- `checkpoints*` = histórico de conversa serializado (msgpack/pickle).
-- `store` + `store_vectors` = memória semântica por telefone, namespace
-- (user_id, "memories") — e os embeddings dela, que também derivam do texto
-- original e por isso vazam tanto quanto ele.
TRUNCATE TABLE checkpoints, checkpoint_blobs, checkpoint_writes CASCADE;
TRUNCATE TABLE store, store_vectors CASCADE;

-- 355 MB para 4.182 linhas porque `incoming_message`/`response` carregam
-- mídia em base64. É fila: linha antiga não serve pra nada em dev.
TRUNCATE TABLE message_queue CASCADE;

-- Sessões e tokens vivos. Um dump com estes dados permitiria assumir a
-- sessão de alguém em produção.
TRUNCATE TABLE auth.session CASCADE;
TRUNCATE TABLE auth.password_reset_pending CASCADE;
TRUNCATE TABLE auth_login_event CASCADE;

-- `cliente_pii_audit` NÃO entra aqui: é view agregada sobre `cliente`, sem
-- dado próprio. Sanear `cliente` já a sanea.

-- ---------------------------------------------------------------------------
-- 2. Credenciais — zeradas
-- ---------------------------------------------------------------------------
--
-- Esta seção é a razão de o banco de dev não conseguir falar com a Evolution
-- nem com a Meta mesmo se alguém trocar `EVOLUTION_OUTBOUND_MODE` pra `real`.
-- É a segunda linha de defesa, atrás da trava do `.env`.

-- `payload_json` guarda `instance_name` — o identificador da instância na
-- Evolution (ex.: `empresa1018_luis_fernando_hpm_unigran`). Junto com a chave
-- da API, é o que decide de qual WhatsApp a mensagem sai. Vale tanto quanto
-- a credencial e sai junto.
UPDATE conexao SET
  credentials_encrypted = NULL,
  webhook_verify_token  = NULL,
  qr_code               = NULL,
  qr_expires_at         = NULL,
  sid                   = 'dev-' || id,
  waba_account_id       = NULL,
  waba_phone_id         = NULL,
  waba_app_id           = NULL,
  waba_account_description = NULL,
  from_number           = '+5500' || lpad(id::text, 9, '0'),
  -- `display_name` é escolhido pelo cliente e costuma ser o nome dele
  -- (`luis-fernando-hpm-unigran`). Sai junto.
  display_name          = 'Conexão de desenvolvimento ' || id,
  payload_json          = jsonb_build_object('instance_name', 'dev_conexao_' || id),
  connection_state      = 'disconnected',
  state_message         = 'credenciais removidas na cópia de desenvolvimento',
  ultimo_health_check_at = NULL,
  ultimo_health_check_ok = NULL;

-- Chave de API da extensão do Chrome: o hash permite ataque offline.
UPDATE empresa_api_key SET
  key_hash     = md5(random()::text),
  key_prefix   = 'devkey',
  last_used_ip = NULL,
  revoked_at   = COALESCE(revoked_at, now());

-- Senha (bcrypt) e tokens OAuth do Google.
UPDATE auth.account SET
  password                = NULL,
  "accessToken"           = NULL,
  "refreshToken"          = NULL,
  "idToken"               = NULL,
  "accessTokenExpiresAt"  = NULL,
  "refreshTokenExpiresAt" = NULL;

-- Vínculo de cobrança com o Asaas — dev não pode tocar assinatura real.
UPDATE empresa SET
  asaas_customer_id     = NULL,
  asaas_subscription_id = NULL;

-- ---------------------------------------------------------------------------
-- 3. PII — embaralhada com o formato preservado
-- ---------------------------------------------------------------------------
--
-- `id` é a semente: o mesmo registro gera sempre o mesmo valor falso, então
-- as junções continuam fazendo sentido e um bug de duplicidade continua
-- reproduzível. Nada aqui é reversível — não é criptografia, é descarte.

CREATE OR REPLACE FUNCTION pg_temp.fake_telefone(semente bigint)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  -- 55 + DDD 11 + 9 + 8 dígitos derivados do id. Passa nas validações de BR
  -- e nas variantes com/sem nono dígito.
  SELECT '55119' || lpad((abs(hashtext(semente::text)) % 100000000)::text, 8, '0');
$$;

CREATE OR REPLACE FUNCTION pg_temp.fake_nome(semente bigint)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT (ARRAY['Ana','Bruno','Carla','Diego','Elisa','Fábio','Gabi','Heitor',
                'Íris','João','Kelly','Lucas','Marina','Nuno','Olívia','Pedro'])
           [1 + abs(hashtext('n' || semente)) % 16]
      || ' ' ||
         (ARRAY['Silva','Souza','Costa','Pereira','Almeida','Ferreira','Rocha',
                'Lima','Cardoso','Barbosa','Teixeira','Moraes'])
           [1 + abs(hashtext('s' || semente)) % 12];
$$;

CREATE OR REPLACE FUNCTION pg_temp.fake_cpf(semente bigint)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT lpad((abs(hashtext('c' || semente)) % 100000000000)::text, 11, '0');
$$;

-- Cliente. Não é só telefone e nome: a tabela virou CRM completo, com
-- endereço, documento, data de nascimento, redes sociais e cinco campos
-- livres onde cabe qualquer coisa que o operador tenha digitado.
--
-- `numero` aqui é o número do ENDEREÇO, não telefone — apesar de
-- `numero_verificado`, logo ao lado, ser sobre o WhatsApp. Errei nisso na
-- primeira versão e o ensaio pegou.
UPDATE cliente SET
  nome                 = pg_temp.fake_nome(id),
  razao_social         = CASE WHEN razao_social IS NOT NULL
                              THEN pg_temp.fake_nome(id) || ' LTDA' END,
  nome_fantasia        = CASE WHEN nome_fantasia IS NOT NULL
                              THEN pg_temp.fake_nome(id) || ' ME' END,
  telefone             = pg_temp.fake_telefone(id),
  telefone_alternativo = CASE WHEN telefone_alternativo IS NOT NULL
                              THEN pg_temp.fake_telefone(id * 7 + 1) END,
  email                = CASE WHEN email IS NOT NULL
                              THEN 'cliente' || id || '@exemplo.invalid' END,
  email_alternativo    = CASE WHEN email_alternativo IS NOT NULL
                              THEN 'alt' || id || '@exemplo.invalid' END,
  -- Documentos, em claro e cifrados.
  cpf                  = CASE WHEN cpf IS NOT NULL THEN pg_temp.fake_cpf(id) END,
  cnpj                 = CASE WHEN cnpj IS NOT NULL THEN pg_temp.fake_cpf(id * 3) END,
  rg                   = CASE WHEN rg IS NOT NULL
                              THEN lpad((abs(hashtext('r' || id)) % 1000000000)::text, 9, '0') END,
  doc                  = CASE WHEN doc IS NOT NULL THEN pg_temp.fake_cpf(id) END,
  cpf_encrypted             = NULL,
  cnpj_encrypted            = NULL,
  rg_encrypted              = NULL,
  data_nascimento           = CASE WHEN data_nascimento IS NOT NULL
                                   THEN DATE '1980-01-01'
                                        + (abs(hashtext('d' || id)) % 14600) END,
  data_nascimento_encrypted = NULL,
  -- Endereço completo.
  cep         = CASE WHEN cep         IS NOT NULL THEN '01001000' END,
  logradouro  = CASE WHEN logradouro  IS NOT NULL THEN 'Rua de Desenvolvimento' END,
  numero      = CASE WHEN numero      IS NOT NULL
                     THEN (abs(hashtext('e' || id)) % 2000)::text END,
  complemento = NULL,
  bairro      = CASE WHEN bairro      IS NOT NULL THEN 'Centro' END,
  cidade      = CASE WHEN cidade      IS NOT NULL THEN 'São Paulo' END,
  uf          = CASE WHEN uf          IS NOT NULL THEN 'SP' END,
  -- Redes sociais, foto e identificadores do WhatsApp.
  instagram   = NULL,
  linkedin    = NULL,
  facebook    = NULL,
  website     = NULL,
  avatar_url  = NULL,
  whatsapp_lid = NULL,
  remote_id    = NULL,
  -- Texto livre: anotação do operador e os cinco campos personalizados, que
  -- por definição podem conter qualquer coisa.
  notes   = CASE WHEN notes IS NOT NULL THEN 'Nota removida na cópia de desenvolvimento.' END,
  field_1 = NULL, field_2 = NULL, field_3 = NULL, field_4 = NULL, field_5 = NULL;

-- Conteúdo escrito por humano sobre humano: anotação e memória do cliente.
-- Não dá pra preservar formato sem preservar o conteúdo, então substitui.
--
-- O `id` entra no texto porque `cliente_memoria` tem índice único em
-- `md5(conteudo)` por (empresa, cliente, categoria) — texto idêntico em duas
-- linhas viola a restrição e derruba o saneamento inteiro.
UPDATE cliente_anotacao SET
  conteudo = 'Anotação removida na cópia de desenvolvimento #' || id
             || ' (' || length(conteudo) || ' caracteres no original).';

-- O `embedding` é um vetor derivado do texto original. Apagar o texto e
-- manter o vetor não resolve nada: dá pra medir similaridade contra frases
-- candidatas e recuperar aproximadamente o que estava escrito.
UPDATE cliente_memoria SET
  conteudo  = 'Memória removida na cópia de desenvolvimento #' || id || '.',
  embedding = NULL;

-- Resumo da última mensagem, exibido na lista de conversas.
--
-- `thread_id` é `"{telefone}:{agente}"` (contrato do checkpointer, ver
-- CLAUDE.md) — carrega o telefone dentro de si. Sanear só `phone_number`
-- deixava o número original no dump; foi o grep que pegou.
UPDATE conversations SET
  phone_number = pg_temp.fake_telefone(id),
  thread_id    = pg_temp.fake_telefone(id) || ':' || COALESCE(agent_id, 'dev'),
  last_message = 'Mensagem removida na cópia de desenvolvimento.';

-- Atendimento. Além do snapshot do canal (mig 129), a linha carrega três
-- campos escritos pela IA a partir da conversa: `resumo_ia`, `coleta_resumo`
-- e `classificacao`. São resumo de conversa real — "Dúvida sobre quantidade
-- de pacientes para aula prática" — e nenhum deles casa com busca por
-- "telefone" ou "mensagem". Quem pegou foi o grep.
UPDATE atendimento SET
  conexao_numero = CASE WHEN conexao_numero IS NOT NULL
                        THEN pg_temp.fake_telefone(id) END,
  conexao_nome   = CASE WHEN conexao_nome IS NOT NULL
                        THEN 'Conexão de desenvolvimento' END,
  resumo_ia      = CASE WHEN resumo_ia IS NOT NULL
                        THEN 'Resumo removido na cópia de desenvolvimento.' END,
  -- jsonb, não texto: guarda os campos que o menu de coleta capturou.
  coleta_resumo  = CASE WHEN coleta_resumo IS NOT NULL
                        THEN '{"removido": "cópia de desenvolvimento"}'::jsonb END;

-- `motivo` da transferência é escrito por quem transferiu e resume o caso.
UPDATE atendimento_transferencia SET
  motivo = CASE WHEN motivo IS NOT NULL
                THEN 'Motivo removido na cópia de desenvolvimento.' END;

-- `audit_log.payload_diff` guarda o antes/depois de cada alteração em JSON —
-- ou seja, replica o conteúdo de todas as outras tabelas, inclusive o que
-- acabamos de limpar. Não dá pra sanear em pedaços; vai inteiro.
TRUNCATE TABLE audit_log CASCADE;

-- Disparador.
--
-- O JID do WhatsApp (`5567...@s.whatsapp.net`) embute o telefone e o
-- `push_name` é o nome que a pessoa escolheu exibir. Nenhum dos dois casa com
-- as buscas por "telefone", e por isso os dois passaram batido na primeira
-- versão — quem pegou foi o grep no dump inteiro.
UPDATE contato_capturado SET
  telefone      = pg_temp.fake_telefone(id),
  wa_jid        = pg_temp.fake_telefone(id) || '@s.whatsapp.net',
  wa_lid        = NULL,
  push_name     = pg_temp.fake_nome(id),
  verified_name = CASE WHEN verified_name IS NOT NULL THEN pg_temp.fake_nome(id) END;

-- O `erro` guarda a resposta crua da Evolution, e ela devolve o número
-- consultado dentro do JSON: `{"jid":"5518...@s.whatsapp.net"}`. Sanear só
-- a coluna `telefone` deixava o original no dump.
UPDATE campanha_destinatario SET
  telefone            = pg_temp.fake_telefone(id),
  mensagem_id_externo = NULL,
  erro                = CASE WHEN erro IS NOT NULL
                             THEN regexp_replace(erro, '[0-9]{12,13}', '55119XXXXXXXX', 'g') END;

UPDATE disparador_opt_out SET
  telefone = pg_temp.fake_telefone(id),
  wa_jid   = CASE WHEN wa_jid IS NOT NULL
                  THEN pg_temp.fake_telefone(id) || '@s.whatsapp.net' END;

-- Membros de grupo capturados pela extensão. É o dado mais sensível do
-- disparador: são terceiros que nunca falaram com a empresa e cujo número foi
-- lido de um grupo de WhatsApp.
UPDATE grupo_membro SET
  telefone  = pg_temp.fake_telefone(id),
  wa_jid    = pg_temp.fake_telefone(id) || '@s.whatsapp.net',
  push_name = pg_temp.fake_nome(id);

-- Grupos e lotes de captura guardam o JID de origem.
UPDATE captura_lote SET
  origem_jid = CASE WHEN origem_jid IS NOT NULL
                    THEN 'dev-lote-' || id || '@g.us' END;

-- Grupos capturados. O `wa_group_id` é `{telefone-do-criador}-{ts}@g.us` — o
-- número está dentro do identificador. E o NOME do grupo é o pior pedaço:
-- vieram coisas como "Somos FAMÍLIA!" e "Primos Amados, CONFRATERNIZAÇÕES
-- semestrais" — grupos pessoais, capturados junto com os de trabalho.
UPDATE grupo SET
  wa_group_id = pg_temp.fake_telefone(id) || '-' || id || '@g.us',
  nome        = 'Grupo de desenvolvimento ' || id,
  descricao   = CASE WHEN descricao IS NOT NULL
                     THEN 'Descrição removida na cópia de desenvolvimento.' END,
  invite_link = NULL;

-- `guardrail_log.sample` guarda o trecho que disparou o bloqueio — texto
-- literal do cliente, com telefone e link dentro.
UPDATE guardrail_log SET
  sample          = CASE WHEN sample IS NOT NULL
                         THEN 'Trecho removido na cópia de desenvolvimento.' END,
  pattern_matched = CASE WHEN pattern_matched ~ '[0-9]{10,}'
                         THEN 'padrao_removido' ELSE pattern_matched END,
  metadata        = NULL;

-- Telefone de quem aprova agendamento — é pessoa da equipe do cliente.
UPDATE agendamento_aprovacao   SET gestor_telefone    = pg_temp.fake_telefone(id);
UPDATE empresa_calendar_config SET aprovador_telefone =
  CASE WHEN aprovador_telefone IS NOT NULL THEN pg_temp.fake_telefone(empresa_id) END;

-- Contadores de rate limit chaveados por telefone. São efêmeros; zera.
TRUNCATE TABLE rate_limit_buckets CASCADE;

-- Resposta livre do cliente na pesquisa de satisfação.
UPDATE atendimento_avaliacao SET
  comentario = CASE WHEN comentario IS NOT NULL
                    THEN 'Comentário removido na cópia de desenvolvimento.' END;

-- `rag_query_log.query_text` é a pergunta do cliente, literal — 6.627 linhas
-- delas. O `thread_id` ao lado carrega o telefone. As métricas (hits, score,
-- duração, outcome) ficam, porque é o que faz a tela de qualidade das
-- respostas ter sentido; o texto vai embora.
UPDATE rag_query_log SET
  query_text = 'Pergunta removida na cópia de desenvolvimento #' || id,
  hyde_query = CASE WHEN hyde_query IS NOT NULL
                    THEN 'Reescrita removida na cópia de desenvolvimento.' END,
  thread_id  = CASE WHEN thread_id IS NOT NULL
                    THEN pg_temp.fake_telefone(id) || ':dev' END;

-- `fewshot_example` guarda a mensagem do cliente e a resposta do agente,
-- promovidas a exemplo — é conteúdo de conversa por definição. O `embedding`
-- deriva do texto e vaza tanto quanto ele.
UPDATE fewshot_example SET
  cliente_msg     = 'Mensagem de exemplo removida na cópia de desenvolvimento #' || id,
  agente_resposta = 'Resposta de exemplo removida na cópia de desenvolvimento #' || id,
  embedding       = NULL,
  metadata        = NULL;

-- Usuários do painel. O admin vira um login previsível pra você entrar; os
-- demais viram nomes falsos com email inválido de propósito (`.invalid` é
-- reservado pela RFC 2606 e nunca resolve).
UPDATE auth."user" SET
  name     = pg_temp.fake_nome(abs(hashtext(id))),
  email    = 'user' || abs(hashtext(id)) || '@exemplo.invalid',
  telefone = CASE WHEN telefone IS NOT NULL
                  THEN pg_temp.fake_telefone(abs(hashtext(id))) END,
  image    = NULL;

-- Dados fiscais e o telefone que recebe o resumo diário.
UPDATE empresa SET
  razao_social               = nome || ' LTDA (dev)',
  doc                        = pg_temp.fake_cpf(id),
  inscricao_estadual         = NULL,
  endereco_fiscal_cep        = '01001000',
  endereco_fiscal_logradouro = 'Rua de Desenvolvimento',
  endereco_fiscal_numero     = '100',
  endereco_fiscal_complemento = NULL,
  endereco_fiscal_bairro     = 'Centro',
  endereco_fiscal_cidade     = 'São Paulo',
  endereco_fiscal_uf         = 'SP',
  resumo_diario_telefone     = CASE WHEN resumo_diario_telefone IS NOT NULL
                                    THEN pg_temp.fake_telefone(id) END,
  resumo_diario_ativo        = false;

-- Lista de bloqueio da IA (mig 133). Apesar do nome, número aqui é contato
-- pessoal do dono — mãe, esposa — que chama no número comercial. É
-- exatamente o tipo de dado que não pode viajar.
UPDATE whitelist_numero SET
  telefone = pg_temp.fake_telefone(id),
  nome     = 'Contato removido na cópia de desenvolvimento';

-- ---------------------------------------------------------------------------
-- 3b. Telefone escondido em coluna de autor — varredura genérica
-- ---------------------------------------------------------------------------
--
-- Quando quem age é a IA e não uma pessoa, o sistema grava o autor como
-- `agente:+5567...` em colunas que se chamam `user_id`. Achei isso em
-- `cliente_memoria.created_by_user_id`, `cliente_anotacao.user_id` e
-- `atendimento_transferencia.iniciado_por_user_id` — três nomes diferentes,
-- nenhum com "telefone" no nome.
--
-- Listar coluna por coluna ia falhar de novo na próxima que aparecesse, então
-- a varredura é genérica: percorre toda coluna de texto do schema e troca
-- qualquer valor com essa cara. Roda uma vez, custa segundos nesse volume.

DO $$
DECLARE
  col RECORD;
  n   bigint;
BEGIN
  FOR col IN
    SELECT c.table_name, c.column_name
      FROM information_schema.columns c
      JOIN information_schema.tables t
        ON t.table_schema = c.table_schema AND t.table_name = c.table_name
     WHERE c.table_schema = 'public'
       AND t.table_type = 'BASE TABLE'
       AND c.data_type IN ('text','character varying')
  LOOP
    EXECUTE format(
      'UPDATE public.%I SET %I = ''agente:dev''
        WHERE %I ~ ''^agente:\+?[0-9]{10,}$''',
      col.table_name, col.column_name, col.column_name);
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n > 0 THEN
      RAISE NOTICE '  telefone em autor: %.% (% linhas)',
        col.table_name, col.column_name, n;
    END IF;
  END LOOP;
END $$;

COMMIT;

-- ---------------------------------------------------------------------------
-- 4. Conferência — falha alto se sobrou PII
-- ---------------------------------------------------------------------------
--
-- Não basta rodar os UPDATEs: se uma migration futura criar coluna nova de
-- telefone e ninguém lembrar deste arquivo, o dump vaza. Estas checagens são
-- o alarme. `ON_ERROR_STOP` faz o script inteiro falhar.

DO $$
DECLARE
  vazou int;
  detalhe text;
BEGIN
  -- Telefone brasileiro real tem DDD entre 11 e 99. Tudo que sobrou aqui
  -- nasce com DDD 11 e prefixo 9 fixo, então qualquer outro padrão é original.
  SELECT count(*) INTO vazou FROM cliente
   WHERE telefone IS NOT NULL AND telefone NOT LIKE '55119%';
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % telefones originais em cliente', vazou;
  END IF;

  SELECT count(*) INTO vazou FROM contato_capturado
   WHERE telefone IS NOT NULL AND telefone NOT LIKE '55119%';
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % telefones originais em contato_capturado', vazou;
  END IF;

  SELECT count(*) INTO vazou FROM whitelist_numero
   WHERE telefone IS NOT NULL AND telefone NOT LIKE '55119%';
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % telefones originais em whitelist_numero', vazou;
  END IF;

  SELECT count(*) INTO vazou FROM store_vectors;
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % embeddings de memória sobraram', vazou;
  END IF;

  SELECT count(*) INTO vazou FROM conexao WHERE credentials_encrypted IS NOT NULL;
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % conexões ainda têm credencial', vazou;
  END IF;

  SELECT count(*) INTO vazou FROM auth.account WHERE password IS NOT NULL;
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % contas ainda têm hash de senha', vazou;
  END IF;

  SELECT count(*) INTO vazou FROM checkpoints;
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % checkpoints do LangGraph sobraram', vazou;
  END IF;

  -- Coluna de telefone que apareceu depois deste arquivo ser escrito.
  --
  -- Sem âncora `^` de propósito: quatro colunas escaparam da primeira versão
  -- desta checagem por serem sufixadas — `gestor_telefone`,
  -- `aprovador_telefone`. A lista de exceção é explícita, então schema novo
  -- falha alto em vez de vazar em silêncio.
  SELECT count(*), string_agg(table_name || '.' || column_name, ', ')
    INTO vazou, detalhe
    FROM information_schema.columns
   WHERE table_schema = 'public'
     AND column_name ~* '(telefone|phone|celular|whatsapp)'
     AND table_name NOT IN ('cliente','contato_capturado','conversations',
                            'campanha_destinatario','disparador_opt_out',
                            'whitelist_numero','conexao','atendimento',
                            'empresa','message_queue','grupo_membro',
                            'agendamento_aprovacao','empresa_calendar_config',
                            'rate_limit_buckets');
  IF vazou > 0 THEN
    RAISE EXCEPTION
      'SANEAMENTO INCOMPLETO: coluna de telefone não tratada (%). '
      'Alguém adicionou schema novo — trate aqui antes de exportar.', detalhe;
  END IF;

  SELECT count(*) INTO vazou FROM grupo_membro
   WHERE telefone IS NOT NULL AND telefone NOT LIKE '55119%';
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % telefones originais em grupo_membro', vazou;
  END IF;

  -- JID do WhatsApp embute o telefone antes do `@`. Escapou da primeira
  -- versão porque o nome da coluna é `wa_jid`, não "telefone".
  SELECT count(*) INTO vazou FROM contato_capturado
   WHERE wa_jid IS NOT NULL AND wa_jid NOT LIKE '55119%';
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % JIDs originais em contato_capturado', vazou;
  END IF;

  SELECT count(*) INTO vazou FROM grupo_membro
   WHERE wa_jid IS NOT NULL AND wa_jid NOT LIKE '55119%';
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % JIDs originais em grupo_membro', vazou;
  END IF;

  -- `thread_id` é "{telefone}:{agente}" — carrega o número dentro.
  SELECT count(*) INTO vazou FROM conversations
   WHERE thread_id IS NOT NULL AND thread_id NOT LIKE '55119%';
  IF vazou > 0 THEN
    RAISE EXCEPTION 'SANEAMENTO FALHOU: % thread_id com telefone original', vazou;
  END IF;

  -- Coluna de JID nova que apareça depois deste arquivo.
  SELECT count(*), string_agg(table_name || '.' || column_name, ', ')
    INTO vazou, detalhe
    FROM information_schema.columns
   WHERE table_schema = 'public'
     AND column_name ~* '(jid|thread_id)'
     AND table_name NOT IN ('contato_capturado','grupo_membro','disparador_opt_out',
                            'captura_lote','conversations','checkpoints',
                            'checkpoint_blobs','checkpoint_writes',
                            -- truncadas mais acima, então vazias
                            'message_queue',
                            'rag_query_log');
  IF vazou > 0 THEN
    RAISE EXCEPTION
      'SANEAMENTO INCOMPLETO: coluna de JID/thread não tratada (%).', detalhe;
  END IF;

  RAISE NOTICE 'Saneamento conferido: nenhum dado identificável sobrou.';
END $$;

-- ---------------------------------------------------------------------------
-- 5. OPCIONAL — base de conhecimento
-- ---------------------------------------------------------------------------
--
-- O que fica de propósito, e por quê:
--
--   `empresa.nome`, `agente_ia.prompt_override`, `menu_chatbot`, `tag`,
--   `workflow_chatbot`, `documento_conhecimento*`.
--
-- É a configuração do produto, e é ela que faz o ambiente de desenvolvimento
-- servir pra alguma coisa: sem documento na base, não dá pra mexer no RAG;
-- sem prompt real, o agente responde diferente do que responde em produção.
--
-- MAS: `documento_conhecimento` é o material que o CLIENTE subiu. No caso do
-- Hospital Mackenzie, são documentos de hospital. Não é PII de usuário final,
-- é material confidencial de empresa — e é decisão sua se ele viaja.
--
-- Se preferir que NÃO viaje, descomente o bloco abaixo. O custo é perder a
-- capacidade de testar busca semântica com conteúdo real.
--
-- BEGIN;
--   UPDATE documento_conhecimento SET
--     titulo   = 'Documento de desenvolvimento ' || id,
--     conteudo = 'Conteúdo removido na cópia de desenvolvimento.';
--   UPDATE documento_conhecimento_chunk SET
--     conteudo  = 'Trecho removido na cópia de desenvolvimento #' || id,
--     embedding = NULL;
-- COMMIT;

-- Relatório final, impresso no log da exportação.
SELECT 'empresas'   AS tabela, count(*) AS linhas FROM empresa
UNION ALL SELECT 'clientes',          count(*) FROM cliente
UNION ALL SELECT 'contatos',          count(*) FROM contato_capturado
UNION ALL SELECT 'atendimentos',      count(*) FROM atendimento
UNION ALL SELECT 'conversas',         count(*) FROM conversations
UNION ALL SELECT 'agentes',           count(*) FROM agente_ia
UNION ALL SELECT 'usuarios',          count(*) FROM auth."user"
UNION ALL SELECT 'fila (zerada)',     count(*) FROM message_queue
UNION ALL SELECT 'checkpoints (zerados)', count(*) FROM checkpoints
ORDER BY 1;
