-- Sub-fase B: Menu chatbot árvore (mapeamento ZigChat).
--
-- ZigChat tem chatbot tradicional em árvore ("digite 1 pra vendas, 2 pra
-- suporte"). Nexus aposta 100% em LLM, mas precisamos do menu pra:
--   1) Triar contato novo antes de gastar token de LLM.
--   2) Permitir escolha explícita ("falar com humano" sem o agente decidir).
--   3) Recuperar contexto via keyword `menu` no meio da conversa.
--
-- Decisão fixada: 5 acao_tipo no MVP (submenu, transferir_dep,
-- chamar_agente, enviar_msg, fechar). Form (acao_tipo='abrir_form')
-- espera Fase 3 plano enterprise.
--
-- Convivência menu+agente: cada item pode 'chamar_agente' passando slug.
-- Agente roda normal a partir daí; cliente digita keyword pra voltar.

-- ---- Menu ----
CREATE TABLE IF NOT EXISTS menu_chatbot (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- conexao_id NULL = se aplica a todas as conexões da empresa.
    -- Útil quando mesma empresa tem N números WhatsApp e quer 1 menu único.
    conexao_id BIGINT REFERENCES conexao(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    mensagem_boas_vindas TEXT NOT NULL,
    -- Cliente diz 'menu'/'opcoes'/'inicio' → reset pra raiz.
    -- Lowercase + trim no worker antes de comparar.
    trigger_keywords TEXT[] NOT NULL DEFAULT ARRAY['menu','opcoes','inicio']::TEXT[],
    -- Quando cliente digita opção que não bate (ex: 'x', 'qualquer texto'),
    -- envia esse texto + reenvia menu atual.
    mensagem_opcao_invalida TEXT NOT NULL DEFAULT
        'Opção inválida. Por favor, escolha um número da lista.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id TEXT
);

-- Índice pra resolver "menu ativo dessa conexão" rapidamente no worker.
-- Inclui menus com conexao_id NULL (qualquer-uma).
CREATE INDEX IF NOT EXISTS idx_menu_chatbot_resolve
    ON menu_chatbot (empresa_id, conexao_id) WHERE ativo;

-- 1 menu ativo por (empresa, conexao_id) — PARTIAL pra permitir múltiplos
-- inativos. NULL conexao_id é tratado como valor único pelo PG (índice
-- partial não considera dois NULLs como duplicados, então cobrimos com
-- COALESCE no índice expressional).
CREATE UNIQUE INDEX IF NOT EXISTS uq_menu_chatbot_ativo_por_conexao
    ON menu_chatbot (empresa_id, COALESCE(conexao_id, 0))
    WHERE ativo;


-- ---- Item ----
CREATE TABLE IF NOT EXISTS menu_item (
    id BIGSERIAL PRIMARY KEY,
    menu_id BIGINT NOT NULL REFERENCES menu_chatbot(id) ON DELETE CASCADE,
    -- Self-FK pra hierarquia árvore. NULL = item raiz.
    parent_id BIGINT REFERENCES menu_item(id) ON DELETE CASCADE,
    -- Ordem de exibição no nível atual (entra como número da opção: 1, 2, 3)
    ordem INT NOT NULL,
    label TEXT NOT NULL,
    -- 5 ações suportadas no MVP:
    --   submenu          — apresenta filhos (filhos vêm via parent_id)
    --   transferir_dep   — atribui departamento e sai do menu
    --   chamar_agente    — atribui agente e sai do menu (próxima msg vai
    --                      pro agente como inbound regular)
    --   enviar_msg       — envia texto livre, opcionalmente volta pro menu
    --   fechar           — encerra atendimento (status='resolvido')
    acao_tipo TEXT NOT NULL CHECK (acao_tipo IN
        ('submenu','transferir_dep','chamar_agente','enviar_msg','fechar')),
    -- Payload conforme acao_tipo (validado em Pydantic no backend):
    --   submenu          {} (filhos descobertos via parent_id)
    --   transferir_dep   {departamento_id: 5, mensagem_pre: 'Vou te conectar com Suporte...'}
    --   chamar_agente    {agente_slug: 'vendas-sp', mensagem_pre: 'Falando com Vendas...'}
    --   enviar_msg       {texto: '...', voltar_menu: true|false}
    --   fechar           {motivo: 'resolvido pelo menu', mensagem_final: 'Até logo!'}
    acao_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- (menu, parent, ordem) único pra evitar duas opções "1" no mesmo nível.
    -- Quando parent_id é NULL (raiz), o NULL precisa ser tratado como valor
    -- consistente — usamos COALESCE pra normalizar.
    UNIQUE (menu_id, parent_id, ordem)
);

CREATE INDEX IF NOT EXISTS idx_menu_item_menu_parent
    ON menu_item (menu_id, parent_id, ordem) WHERE ativo;


-- ---- Histórico de navegação ----
-- Registra cada escolha do cliente na árvore — auditoria + recuperação
-- de "onde o cliente parou" (posicao_atual_item_id é o ponto da árvore
-- de onde a próxima escolha "1, 2, 3" será resolvida).
CREATE TABLE IF NOT EXISTS atendimento_menu_historico (
    id BIGSERIAL PRIMARY KEY,
    atendimento_id BIGINT NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    menu_id BIGINT NOT NULL REFERENCES menu_chatbot(id),
    -- Item escolhido nessa interação. NULL quando é a entrada inicial
    -- (cliente recebe boas-vindas + raiz e ainda não escolheu nada).
    item_id BIGINT REFERENCES menu_item(id) ON DELETE SET NULL,
    -- Onde o cliente está agora. NULL = na raiz do menu.
    -- A próxima escolha "1" será resolvida como ordem=1 com
    -- parent_id = posicao_atual_item_id.
    posicao_atual_item_id BIGINT REFERENCES menu_item(id) ON DELETE SET NULL,
    escolhido_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_menu_historico_atendimento
    ON atendimento_menu_historico (atendimento_id, escolhido_at DESC);
