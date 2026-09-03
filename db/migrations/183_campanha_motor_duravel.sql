-- Motor de disparo durável (F2b do projeto Prospecção Enterprise).
--
-- O problema que esta migration prepara o terreno pra resolver: hoje o
-- dispatcher roda como `asyncio.create_task` DENTRO do processo da API
-- (server/main.py:223 + shared/campanha.py:1318). A API reinicia a cada deploy
-- — e neste repo merge É deploy —, então qualquer merge no meio de uma campanha
-- mata o envio. Pior: `claim_scheduled_due` só reivindica 'scheduled', nunca
-- 'running', então a campanha morta fica 'running' PARA SEMPRE e os
-- destinatários 'pendente' para sempre. Não há endpoint de retomada (o TODO
-- está em routes/campanha.py:378). Só SQL manual recupera.
--
-- A saída não inventa mecanismo: é o mesmo padrão do `message_queue`, que já
-- roda no worker com FOR UPDATE SKIP LOCKED + lease + heartbeat e é a parte
-- mais confiável do sistema. Esta migration dá ao `campanha` as colunas que o
-- `message_queue` tem, e ao `campanha_destinatario` o claim que falta.
--
-- Produção está VAZIA (0 campanhas, 0 destinatários em 2026-09-03), então
-- mexer nos CHECKs é barato agora — e só agora.

-- ---------------------------------------------------------------------------
-- 1. Lease na campanha
-- ---------------------------------------------------------------------------
-- `lease_expires_at` no passado + status 'running' = campanha órfã, e é a
-- ÚNICA forma de distinguir "worker vivo trabalhando" de "o dono morreu". Sem
-- isso 'running' é ambíguo e por isso virou estado terminal.

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS lease_owner      TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS heartbeat_at     TIMESTAMPTZ;

COMMENT ON COLUMN campanha.lease_owner IS
    'Id do worker que detém a campanha. NULL = sem dono. Ver mig 183.';
COMMENT ON COLUMN campanha.lease_expires_at IS
    'Fim do lease. status=running com este campo no passado = orfa, '
    'reivindicavel por qualquer worker (é o conserto do estado terminal).';

-- ---------------------------------------------------------------------------
-- 2. Estados novos da campanha: 'queued' e 'paused'
-- ---------------------------------------------------------------------------
--   queued — o usuário mandou disparar e nenhum worker pegou ainda. Hoje o
--            POST /dispatch cria a task DENTRO da API; passa a só marcar
--            'queued'. É esta troca que torna o motor durável: o trabalho
--            deixa de depender do processo que atendeu o HTTP.
--   paused — pausa retomável. Hoje pausar não existe: abort_campanha grava
--            'aborted' + finished_at e o CHECK não deixa voltar, então quem
--            queria só "segura aí" perdia a campanha.

ALTER TABLE campanha DROP CONSTRAINT IF EXISTS campanha_status_check;
ALTER TABLE campanha
    ADD CONSTRAINT campanha_status_check
    CHECK (status IN (
        'draft', 'queued', 'scheduled', 'running', 'paused',
        'done', 'partial', 'aborted'
    ));

-- Índice do claim. As três portas do WHERE (queued / scheduled vencida /
-- running com lease morto) caem todas neste índice parcial.
CREATE INDEX IF NOT EXISTS idx_campanha_claim
    ON campanha (status, scheduled_at, lease_expires_at)
    WHERE status IN ('queued', 'scheduled', 'running');

-- ---------------------------------------------------------------------------
-- 3. Claim por destinatário
-- ---------------------------------------------------------------------------
-- O lote hoje é lido sem FOR UPDATE SKIP LOCKED (shared/campanha.py:1088), então
-- dois motores na mesma campanha enviam TUDO em duplicado. Produção roda dois
-- workers: no destino a corrida é real, não hipotética.
--
-- `provider_chamado_at` existe pra desambiguar o órfão. Sem ele, um
-- destinatário 'enviando' com lease vencido é indecidível entre "nunca saiu"
-- e "pode ter saído", e as duas saídas erradas são simétricas: devolver pra
-- 'pendente' pode mandar duas vezes, marcar 'incerto' pode deixar buraco.
-- Com ele:
--     claimed_at setado + provider_chamado_at NULL → nunca chegou no provedor
--                                                    → volta pra 'pendente'
--     ambos setados, sem resultado                 → pode ter saído
--                                                    → 'incerto', NÃO reenvia
-- A escolha de não reenviar no caso incerto é deliberada: em disparo em massa
-- a duplicata é pior que o buraco (é o sinal de spam que queimou o número na
-- campanha 9), e o buraco é visível e corrigível por reenvio manual.

ALTER TABLE campanha_destinatario
    ADD COLUMN IF NOT EXISTS claimed_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS claimed_by          TEXT,
    ADD COLUMN IF NOT EXISTS provider_chamado_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tentativas          INT NOT NULL DEFAULT 0;

ALTER TABLE campanha_destinatario
    DROP CONSTRAINT IF EXISTS campanha_destinatario_status_check;
ALTER TABLE campanha_destinatario
    ADD CONSTRAINT campanha_destinatario_status_check
    CHECK (status IN ('pendente', 'enviando', 'enviado', 'falhou', 'incerto'));

COMMENT ON COLUMN campanha_destinatario.provider_chamado_at IS
    'Marcado imediatamente ANTES da chamada ao provedor. Desambigua o orfao: '
    'NULL = nunca saiu (volta pra pendente); setado sem resultado = incerto '
    '(nao reenvia). Ver mig 183.';

-- Varredura de órfãos: 'enviando' com claimed_at velho.
CREATE INDEX IF NOT EXISTS idx_campanha_dest_enviando
    ON campanha_destinatario (claimed_at)
    WHERE status = 'enviando';

-- ---------------------------------------------------------------------------
-- 4. campanha_evento — trilha em vez de string concatenada
-- ---------------------------------------------------------------------------
-- Hoje o histórico da campanha é CONCATENADO no campo `descricao`
-- (_mark_finished:1273, _reagendar_warmup:1305): motivo de abort e nota de
-- warm-up viram texto solto no campo que o usuário escreveu. Não dá pra
-- consultar, ordenar nem exibir.
--
-- `lease_expirada` e `retomada_apos_orfa` são o que torna o conserto do §4.3
-- OBSERVÁVEL: sem eles, "a campanha se recuperou sozinha" é indistinguível de
-- "nunca quebrou".
--
-- Nasce sob RLS — lição da mig 182, onde a tabela ficou 5 meses de fora por ter
-- só FK pro tenant em vez de coluna própria.

CREATE TABLE IF NOT EXISTS campanha_evento (
    id          BIGSERIAL PRIMARY KEY,
    campanha_id BIGINT      NOT NULL REFERENCES campanha(id) ON DELETE CASCADE,
    empresa_id  BIGINT      NOT NULL REFERENCES empresa(id)  ON DELETE CASCADE,
    tipo        TEXT        NOT NULL,
    payload     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT campanha_evento_tipo_check CHECK (tipo IN (
        'criada', 'enfileirada', 'iniciada', 'pausada', 'retomada',
        'reagendada_warmup', 'conexao_fora_do_pool', 'kill_switch',
        'lease_expirada', 'retomada_apos_orfa', 'finalizada'
    ))
);

CREATE INDEX IF NOT EXISTS idx_campanha_evento_campanha
    ON campanha_evento (campanha_id, created_at DESC);

ALTER TABLE campanha_evento ENABLE ROW LEVEL SECURITY;
ALTER TABLE campanha_evento FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON campanha_evento;
CREATE POLICY tenant_isolation ON campanha_evento
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

-- Sem bloco de GRANT: a mig 100 deixou `ALTER DEFAULT PRIVILEGES IN SCHEMA
-- public` para os 4 roles, então tabela nova já nasce com privilégio. É o que
-- as migs 178-181 fizeram (nenhuma tem GRANT) e o que o painel prova em
-- produção. A validação no fim confere que a policy pegou.

-- ---------------------------------------------------------------------------
-- 5. Validação: se algo não pegou, o deploy para AQUI e não num vazamento
--    silencioso semanas depois (mesmo contrato da mig 182).
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tem_rls    BOOLEAN;
    tem_policy BOOLEAN;
    n_cols     INT;
BEGIN
    SELECT c.relrowsecurity AND c.relforcerowsecurity INTO tem_rls
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'campanha_evento';

    SELECT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'campanha_evento'
           AND policyname = 'tenant_isolation'
    ) INTO tem_policy;

    IF NOT COALESCE(tem_rls, FALSE) OR NOT tem_policy THEN
        RAISE EXCEPTION
            'Migration 183: RLS nao ficou ativo em campanha_evento '
            '(force=%, policy=%).', tem_rls, tem_policy;
    END IF;

    SELECT count(*) INTO n_cols
      FROM information_schema.columns
     WHERE table_name = 'campanha'
       AND column_name IN ('lease_owner', 'lease_expires_at', 'heartbeat_at');
    IF n_cols <> 3 THEN
        RAISE EXCEPTION 'Migration 183: lease incompleto em campanha (% de 3).', n_cols;
    END IF;

    SELECT count(*) INTO n_cols
      FROM information_schema.columns
     WHERE table_name = 'campanha_destinatario'
       AND column_name IN ('claimed_at', 'claimed_by', 'provider_chamado_at', 'tentativas');
    IF n_cols <> 4 THEN
        RAISE EXCEPTION
            'Migration 183: claim incompleto em campanha_destinatario (% de 4).', n_cols;
    END IF;

    RAISE NOTICE 'Migration 183: motor duravel preparado (lease + claim + eventos).';
END $$;
