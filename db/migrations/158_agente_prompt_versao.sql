-- Histórico de versões do prompt do agente — append-only, restaurável na UI.
--
-- Até aqui, editar o prompt no painel SOBRESCREVIA o texto anterior e ele
-- sumia. Existia um caminho de versionamento (Langfuse Prompt Management,
-- consultado pelo loader quando `prompt_override` estava vazio), mas ele
-- morreu por duas causas somadas: a mig 155 materializou o SYSTEM_PROMPT de
-- todo agente na coluna (nenhum campo vazio sobrou, o ramo nunca executa) e o
-- Langfuse está desligado desde 2026-07-27. Para um produto onde o prompt é o
-- ativo do cliente — há agente com 29.985 caracteres escritos à mão — isso é
-- perda de trabalho sem rede.
--
-- Semântica: a versão N é o texto COMO FICOU depois da edição N; a versão mais
-- alta é sempre igual ao `agente_ia.prompt_override` vivo. Restaurar a versão
-- K grava o texto de K como versão N+1 (modelo `git revert`) — nenhuma linha
-- é reescrita ou apagada.
--
-- Retenção: guarda tudo. 30 KB x ~50 edições x ~20 agentes fica em dezenas de
-- MB antes da compressão TOAST, e podar histórico é justamente o que frustra
-- quem precisa dele.

CREATE TABLE IF NOT EXISTS agente_prompt_versao (
    id            BIGSERIAL PRIMARY KEY,
    empresa_id    BIGINT NOT NULL REFERENCES empresa(id)   ON DELETE CASCADE,
    agente_id     BIGINT NOT NULL REFERENCES agente_ia(id) ON DELETE CASCADE,
    versao        INT    NOT NULL,
    texto         TEXT,                              -- NULL = prompt vazio
    nota          TEXT,                              -- "mensagem de commit"
    origem        TEXT   NOT NULL DEFAULT 'edicao',
    restaurada_de INT,                               -- só quando origem='restauracao'
    criado_por_user_id TEXT,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agente_prompt_versao_origem_check
        CHECK (origem IN ('edicao', 'restauracao', 'inicial', 'backfill')),
    -- materializa o btree (agente_id, versao) usado pela listagem e pelo
    -- cálculo do próximo número de versão
    UNIQUE (agente_id, versao)
);

COMMENT ON TABLE agente_prompt_versao IS
    'Histórico append-only do prompt de cada agente. Versão N = texto depois '
    'da edição N; a maior versão espelha agente_ia.prompt_override.';
COMMENT ON COLUMN agente_prompt_versao.origem IS
    'edicao = salvou pelo painel; restauracao = voltou a uma versão anterior; '
    'inicial = estado no momento da migration ou da criação do agente; '
    'backfill = reconstruída a partir de audit_log.';

-- RLS uniforme (Sprint A.2 — bloco canônico).
ALTER TABLE agente_prompt_versao ENABLE ROW LEVEL SECURITY;
ALTER TABLE agente_prompt_versao FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON agente_prompt_versao;
CREATE POLICY tenant_isolation ON agente_prompt_versao
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));

-- ---------------------------------------------------------------------------
-- Seed
-- ---------------------------------------------------------------------------
-- A policy é STRICT desde a mig 102: sem `app.empresa_id` setado, retorna
-- FALSE. As migrations rodam no pool da aplicação (`run_migrations` no startup
-- da API e do worker), que em produção conecta como `chat_nexus_app` — papel
-- comum, sujeito a FORCE RLS. Sem o bypass abaixo o INSERT seria silenciosamente
-- barrado em produção e passaria em dev, onde a conexão é superusuário.
-- `is_local = true`: vale só até o fim desta transação.
SELECT set_config('app.bypass_rls', 'true', true);

-- O histórico já existia — só não era visível. `record_audit` grava, em
-- `audit_log.payload_diff`, o valor INTEIRO dos campos alterados (`diff_dicts`
-- em shared/audit.py não faz diff textual). Logo, toda edição de prompt desde
-- a mig 036 deixou o texto anterior completo em
-- `payload_diff->'before'->>'prompt_override'`. Reconstruir dali é a diferença
-- entre "o histórico começa hoje" e "o histórico já está aqui".
--
-- Em DEV isto não recupera nada: `scripts/migrar-dev/sanitizar_dev.sql` faz
-- TRUNCATE em audit_log. Ver um único registro por agente aqui é o esperado.
--
-- A junção usa o slug porque é o que `entity_id` guarda — e ele é READONLY em
-- `update_agente`, então é estável.
WITH hist AS (
    SELECT a.id                                            AS agente_id,
           a.empresa_id                                    AS empresa_id,
           al.at                                           AS quando,
           al.user_id                                      AS user_id,
           al.id                                           AS fonte_id,
           al.payload_diff->'before'->>'prompt_override'   AS texto,
           0                                               AS ordem,
           'backfill'                                      AS origem
      FROM audit_log al
      JOIN agente_ia a
        ON a.empresa_id = al.empresa_id
       AND a.slug       = al.entity_id
     WHERE al.action      = 'agente.update'
       AND al.entity_type = 'agente_ia'
       AND jsonb_exists(al.payload_diff->'before', 'prompt_override')
),
-- Cada linha de `hist` é o texto ANTES daquela edição, ou seja v0..v(n-1).
-- O estado de hoje é o vn e fecha a sequência. `ordem = 1` garante que ele
-- ordene por último: `agente_ia.updated_at` é levemente ANTERIOR ao `at` da
-- última linha de audit (a auditoria grava depois do UPDATE), então ordenar
-- só por tempo colocaria o atual na penúltima posição.
todos AS (
    SELECT agente_id, empresa_id, quando, user_id, fonte_id, texto, ordem, origem
      FROM hist
    UNION ALL
    SELECT a.id, a.empresa_id, a.updated_at, a.created_by_user_id, 0,
           a.prompt_override, 1, 'inicial'
      FROM agente_ia a
),
-- Atribuição: o texto de uma linha foi produzido pela edição ANTERIOR, não
-- pela que o substituiu. Por isso autor e data saem do `lag()`. Vale uniforme:
-- para o estado atual, o lag aponta para a última edição — que é exatamente
-- quem o escreveu. Sem linha anterior, cai na criação do agente.
ordenado AS (
    SELECT t.*,
           LAG(t.texto)   OVER w AS texto_anterior,
           LAG(t.quando)  OVER w AS quando_autor,
           LAG(t.user_id) OVER w AS user_autor
      FROM todos t
    WINDOW w AS (PARTITION BY t.agente_id ORDER BY t.ordem, t.quando, t.fonte_id)
),
distintos AS (
    SELECT * FROM ordenado
     WHERE texto_anterior IS DISTINCT FROM texto
),
numerado AS (
    SELECT d.*,
           ROW_NUMBER() OVER (PARTITION BY d.agente_id
                                  ORDER BY d.ordem, d.quando, d.fonte_id) AS versao
      FROM distintos d
)
INSERT INTO agente_prompt_versao
    (empresa_id, agente_id, versao, texto, origem, criado_por_user_id, criado_em)
SELECT n.empresa_id,
       n.agente_id,
       n.versao,
       n.texto,
       n.origem,
       COALESCE(n.user_autor, a.created_by_user_id),
       COALESCE(n.quando_autor, a.created_at)
  FROM numerado n
  JOIN agente_ia a ON a.id = n.agente_id
ON CONFLICT (agente_id, versao) DO NOTHING;

-- Guard: todo agente precisa ter saído daqui com pelo menos uma versão, e a
-- mais alta tem de espelhar o prompt vivo. Se não bater, a leitura do painel
-- mostraria um histórico que não corresponde ao que o agente responde — falhar
-- aqui é melhor que descobrir depois.
DO $guard$
DECLARE
    sem_versao INT;
    divergente INT;
BEGIN
    SELECT count(*) INTO sem_versao
      FROM agente_ia a
     WHERE NOT EXISTS (SELECT 1 FROM agente_prompt_versao v
                        WHERE v.agente_id = a.id);
    IF sem_versao > 0 THEN
        RAISE EXCEPTION 'mig 158: % agente(s) ficaram sem versão inicial', sem_versao;
    END IF;

    SELECT count(*) INTO divergente
      FROM agente_ia a
      JOIN LATERAL (SELECT texto FROM agente_prompt_versao v
                     WHERE v.agente_id = a.id
                     ORDER BY versao DESC LIMIT 1) topo ON TRUE
     WHERE COALESCE(topo.texto, '') IS DISTINCT FROM COALESCE(a.prompt_override, '');
    IF divergente > 0 THEN
        RAISE EXCEPTION 'mig 158: % agente(s) com versão de topo != prompt vivo', divergente;
    END IF;

    RAISE NOTICE 'mig 158: histórico de prompt semeado para % agente(s)',
                 (SELECT count(*) FROM agente_ia);
END $guard$;
