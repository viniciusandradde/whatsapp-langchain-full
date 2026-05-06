"""Processamento profundo do _schema_full.json — gera análises em Markdown.

Reproduzir:
    cd docs/zigchat/analysis && python3 _process.py

Lê: ../_schema_full.json
Escreve: 01_overview.md, 02_relationships.md, 03_enums_and_strings.md,
         04_field_frequency.md, 05_parity_matrix.md, 06_migrations_roadmap.md,
         07_conventions.md
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
SCHEMA_PATH = HERE.parent / '_schema_full.json'
schema = json.load(SCHEMA_PATH.open())['data']['__schema']
TYPES = {t['name']: t for t in schema['types']}
QUERIES = next(t['fields'] for t in schema['types'] if t['name'] == 'Query')
MUTATIONS = next(t['fields'] for t in schema['types'] if t['name'] == 'Mutation')


def render_type(tp):
    if not tp:
        return '?'
    k = tp.get('kind')
    n = tp.get('name')
    if k == 'NON_NULL':
        return render_type(tp['ofType']) + '!'
    if k == 'LIST':
        return '[' + render_type(tp['ofType']) + ']'
    return n or k or '?'


def base_typename(tp):
    """Tira NON_NULL/LIST e retorna o nome do tipo base."""
    while tp:
        n = tp.get('name')
        if n:
            return n
        tp = tp.get('ofType')
    return None


def is_user_type(name):
    if not name:
        return False
    if name.startswith('__'):
        return False
    if name in ('Query', 'Mutation', 'Subscription'):
        return False
    t = TYPES.get(name)
    return t is not None and t['kind'] not in ('SCALAR',)


# =============================================================================
# 01 — Overview
# =============================================================================

def gen_overview():
    user_types = [t for t in TYPES.values()
                  if is_user_type(t['name'])]
    by_kind = Counter(t['kind'] for t in user_types)

    # Distribuição de tamanho de tipos (qtde campos)
    sizes = []
    for t in user_types:
        fields = t.get('fields') or t.get('inputFields') or []
        if fields:
            sizes.append((t['name'], len(fields), t['kind']))
    sizes.sort(key=lambda x: -x[1])

    # Naming patterns nas operações
    q_prefixes = Counter()
    for q in QUERIES:
        m = re.match(r'^([a-z]+)', q['name'])
        if m:
            q_prefixes[m.group(1)] += 1
    m_prefixes = Counter()
    for m in MUTATIONS:
        mat = re.match(r'^([a-z]+)', m['name'])
        if mat:
            m_prefixes[mat.group(1)] += 1

    out = [
        '# 01 — Overview do schema GraphQL ZigChat',
        '',
        '> Métricas brutas extraídas via introspection em **2026-05-06** de `https://dev.zigchat.com.br/api/graphql`.',
        '',
        '## Totais',
        '',
        f'- **Types totais (excluindo built-ins, Query, Mutation):** {len(user_types)}',
        f'- **Queries:** {len(QUERIES)}',
        f'- **Mutations:** {len(MUTATIONS)}',
        f'- **Subscriptions:** {sum(1 for t in TYPES.values() if t["name"] == "Subscription")}',
        '',
        '## Distribuição por kind',
        '',
        '| Kind | Quantidade | % |',
        '|---|---:|---:|',
    ]
    total = sum(by_kind.values())
    for k, n in by_kind.most_common():
        out.append(f'| `{k}` | {n} | {100*n/total:.1f}% |')
    out += ['', '## Naming patterns nas Queries (top prefixos)', '',
            '| Prefixo | Qtde | Semântica esperada |', '|---|---:|---|']
    semantica = {
        'listar': 'Lista completa sem filtro/paginação',
        'filtrar': 'Lista paginada + filtro (retorna `XDataTable`)',
        'buscar': 'Single record por ID/chave',
        'admin': 'Operação cross-tenant (super admin)',
        'carregar': 'Load custom (ex: histórico de mensagens)',
        'limite': 'Verificações de quota/limite',
        'decrypt': 'Decrypt de arquivo encriptado',
        'exportar': 'Geração de export',
        'gerar': 'Geração on-demand (ex: tokens)',
        'disparar': 'Disparo de campanha/evento',
    }
    for p, n in q_prefixes.most_common():
        out.append(f'| `{p}` | {n} | {semantica.get(p, "—")} |')
    out += ['', '## Naming patterns nas Mutations (top prefixos)', '',
            '| Prefixo | Qtde | Semântica esperada |', '|---|---:|---|']
    sem_m = {
        'criar': 'INSERT puro (em geral combinado com `criarAlterar`)',
        'criarAlterar': 'UPSERT — cria se id null, edita se preenchido (padrão dominante)',
        'alterar': 'UPDATE puro',
        'deletar': 'DELETE',
        'remover': 'Remoção lógica (ativo=N)',
        'duplicar': 'Clone (ex: `duplicarMenu`)',
        'testar': 'Health check (ex: `testarMcpServer`)',
        'enviar': 'Outbound (ex: `enviarMensagem`)',
        'aprovar': 'State machine (aprovar/rejeitar)',
        'aceitar': 'State machine',
        'finalizar': 'Encerrar fluxo',
        'transferir': 'Atribuição de owner',
    }
    for p, n in m_prefixes.most_common():
        out.append(f'| `{p}` | {n} | {sem_m.get(p, "—")} |')

    out += ['', '## Top 25 types por número de campos', '',
            '| Type | Kind | Campos |', '|---|---|---:|']
    for name, n_fields, kind in sizes[:25]:
        out.append(f'| `{name}` | {kind} | {n_fields} |')

    out += ['', '## Padrões estruturais detectados', '',
            f'- **`XDataTable`:** {sum(1 for t in user_types if t["name"].endswith("DataTable"))} tipos. Wrapper de paginação `{{ rows: [X], total, ... }}`.',
            f'- **`XInput`:** {sum(1 for t in user_types if t["name"].endswith("Input") and not t["name"].endswith("ListInput") and not t["name"].endswith("FilterInput"))} tipos. Payload de mutation.',
            f'- **`XListInput`:** {sum(1 for t in user_types if t["name"].endswith("ListInput"))} tipos. Filtro + paginação pra `filtrarX`.',
            f'- **`XFilterInput`:** {sum(1 for t in user_types if t["name"].endswith("FilterInput"))} tipos. Sub-objeto de filtro.',
            f'- **Enums:** {sum(1 for t in user_types if t["kind"] == "ENUM")} tipos.',
            ]
    return '\n'.join(out)


# =============================================================================
# 02 — Relationships (FKs implícitas via campos `*_id` + LIST<X>)
# =============================================================================

def gen_relationships():
    # Pra cada type OBJECT, lista os campos FK (X_id) e os campos LIST<Y>
    # FK se field name termina em `_id` E o type base é Int/Float
    # e existe Type Y onde Y tem essa convenção (ex: cliente_id → Cliente)

    fk_map = defaultdict(list)   # type -> [(field_name, target_type_guess)]
    list_map = defaultdict(list)  # type -> [(field_name, list_type)]
    inverse = defaultdict(list)   # target_type -> [(source_type, field_name)]

    for tname, t in TYPES.items():
        if t['kind'] != 'OBJECT':
            continue
        if not is_user_type(tname):
            continue
        fields = t.get('fields') or []
        for f in fields:
            base = base_typename(f['type'])
            kind_tree = f['type']
            # Detect LIST
            curr = kind_tree
            is_list = False
            while curr:
                if curr.get('kind') == 'LIST':
                    is_list = True
                    break
                curr = curr.get('ofType')
            if is_list and is_user_type(base):
                list_map[tname].append((f['name'], base))
                inverse[base].append((tname, f['name'], 'LIST'))
            # Detect FK by suffix _id (campos numéricos)
            if f['name'].endswith('_id') and base in ('Int', 'Float'):
                # Tenta inferir target type
                snake = f['name'][:-3]  # remove _id
                # camelize: cliente_atendente -> ClienteAtendente
                guesses = [''.join(s.capitalize() for s in snake.split('_'))]
                # Casos especiais
                special = {
                    'aba': 'Aba',
                    'agente_ia': 'AgenteIA',
                    'cliente': 'Cliente',
                    'cidade': 'Cidade',
                    'departamento': 'Departamento',
                    'usuario': 'Usuario',
                    'menu': 'Menu',
                    'item': 'Item',
                    'menu_id': 'Menu',
                    'item_id': 'Item',
                    'conexao': 'Conexao',
                    'empresa': 'Empresa',
                    'campanha': 'Campanha',
                    'tag': 'Tag',
                    'turno': 'Turno',
                    'pasta': 'Pasta',
                    'modelo_mensagem': 'ModeloMensagem',
                    'mcp_server': 'McpServer',
                    'base_conhecimento': 'BaseConhecimento',
                    'conta_externa': 'ContaExterna',
                    'canal': 'CanalExterno',
                    'cliente_atendente': 'Usuario',
                    'criacao_usuario': 'Usuario',
                    'alteracao_usuario': 'Usuario',
                    'atendimento': 'Atendimento',
                    'hook': 'Hook',
                    'aviso': 'Aviso',
                    'plano': 'Plano',
                    'turno': 'Turno',
                    'feriado': 'Feriado',
                    'horario': 'Horario',
                    'produto': 'Produto',
                    'categoria_produto': 'CategoriaProduto',
                    'modelo_ia': 'ModeloIA',
                    'variavel_ambiente': 'VariavelAmbiente',
                    'form_padrao': 'FormPadrao',
                    'transferencia': 'AtendimentoTransferencia',
                    'atendente_usuario': 'Usuario',
                    'criacao_usuario': 'Usuario',
                    'alteracao_usuario': 'Usuario',
                    'cidade': 'Cidade',
                    'estado': 'Estado',
                    'limite_menu': 'Menu',
                    'coleta_menu': 'Menu',
                    'menu_coleta': 'Menu',
                    'auto_navegar_para_item': 'Item',
                    'contato_cliente': 'Cliente',
                    'notifica_cliente': 'Cliente',
                    'usuario_atendente': 'Usuario',
                }
                target = special.get(snake) or guesses[0]
                if target not in TYPES:
                    target = '?'
                fk_map[tname].append((f['name'], target))
                if target != '?':
                    inverse[target].append((tname, f['name'], 'FK'))

    # Top 30 mais referenciados
    most_referenced = sorted(inverse.items(), key=lambda x: -len(x[1]))[:30]

    out = [
        '# 02 — Relacionamentos entre types',
        '',
        '> FKs detectadas pela convenção `xxx_id` (Int/Float) + listas `[Y!]` em campos.',
        '> Não enxerga FKs com nome custom (ex: `usuario_atendente_id` → Usuario).',
        '',
        '## Top 30 types mais referenciados (entrando)',
        '',
        '| Type | Refs entrando | Origem (sample 5) |',
        '|---|---:|---|',
    ]
    for tname, refs in most_referenced:
        sample = ', '.join(f'`{src}.{field}`' for src, field, _ in refs[:5])
        if len(refs) > 5:
            sample += f' (+{len(refs)-5} mais)'
        out.append(f'| `{tname}` | {len(refs)} | {sample} |')

    out += ['', '## Detalhe completo (saindo)', '',
            'Para cada `OBJECT`, lista FKs detectadas + LIST<X>.', '',
            ]
    for tname in sorted(set(list(fk_map.keys()) + list(list_map.keys()))):
        fks = fk_map.get(tname, [])
        lists = list_map.get(tname, [])
        if not fks and not lists:
            continue
        out.append(f'### `{tname}`')
        if fks:
            out.append('')
            out.append('**FKs:**')
            for fname, target in fks:
                out.append(f'- `{fname}` → `{target}`')
        if lists:
            out.append('')
            out.append('**Listas:**')
            for fname, target in lists:
                out.append(f'- `{fname}: [{target}]`')
        out.append('')
    return '\n'.join(out)


# =============================================================================
# 03 — Enums + boolean-as-string fields
# =============================================================================

def gen_enums():
    out = [
        '# 03 — Enums + booleans-em-string',
        '',
        '> ZigChat tem POUCOS enums GraphQL — quase tudo é string com convenção.',
        '> O padrão dominante é boolean-em-string `"S"`/`"N"` (ativo, principal, etc).',
        '',
        '## Enums GraphQL formais',
        '',
    ]
    enums = [t for t in TYPES.values() if t['kind'] == 'ENUM' and not t['name'].startswith('__')]
    if not enums:
        out.append('_Nenhum enum formal no schema._')
    else:
        out.append('| Enum | Valores |')
        out.append('|---|---|')
        for t in enums:
            vals = ', '.join(f'`{v["name"]}`' for v in t.get('enumValues', []))
            out.append(f'| `{t["name"]}` | {vals} |')

    out += ['', '## Boolean-em-string (campos `"S"`/`"N"`)', '',
            'Identificados por nome (`ativo`, `principal`, `padrao`, etc) com `String` ou `String!`.',
            'Lista de campos detectados em todos os OBJECT types:', '']

    bool_string_names = {
        'ativo', 'principal', 'padrao', 'solicitar_nome', 'coleta_informacao',
        'enviar_msg_final_coleta', 'menu_moderno', 'confirmar_coleta',
        'menu_ia', 'numero_verificado', 'desconsiderar_turno_cliente',
        'ignora_inatividade', 'mudar_para_manual', 'iniciado_cliente',
        'finalizacao_usuario', 'enviar_fila_atendimento', 'encerra_atendimento',
        'lida', 'informa_nome', 'cliente_em_atendimento', 'atendimento_automatico',
        'aceita_imagem', 'aceita_audio', 'aceita_documento',  # mas esses são bool nosso
        'resposta_confidencial', 'exibir_comando_menu_item',
    }

    field_occurrences = defaultdict(list)  # field name -> [type names]
    for tname, t in TYPES.items():
        if t['kind'] != 'OBJECT' or not is_user_type(tname):
            continue
        for f in (t.get('fields') or []):
            if f['name'] in bool_string_names:
                base = base_typename(f['type'])
                field_occurrences[f['name']].append((tname, render_type(f['type'])))

    out.append('| Campo | Em N types | Tipo predominante | Sample types (3) |')
    out.append('|---|---:|---|---|')
    for name in sorted(field_occurrences.keys(), key=lambda x: -len(field_occurrences[x])):
        occs = field_occurrences[name]
        types_set = Counter(t for _, t in occs).most_common(1)[0][0]
        sample = ', '.join(f'`{t}`' for t, _ in occs[:3])
        out.append(f'| `{name}` | {len(occs)} | `{types_set}` | {sample} |')

    out += ['', '## "Enums" semânticos descobertos por análise de naming', '',
            'Campos numéricos com semântica de enum (ex: `acao` em Item, `tipo` em vários):', '']

    enum_like = {
        'acao': 'Ação do menu_item — provável enum numérico (1=submenu, 2=transferir_dep, 3=chamar_agente, ...). Comparar com nosso CHECK acao_tipo string.',
        'tipo': 'Múltiplas semânticas. Em `Conexao` provavelmente engine (twilio/evolution/waba); em `Atendimento` é canal_id; em `ModeloIA` é "chat"/"embedding"/"midia".',
        'tipo_atendimento': 'Em Conexao + Cliente. Provável: 1=manual, 2=ia, 3=hibrido.',
        'tipo_memoria': 'Em AgenteIA. Provável: "buffer"/"summary"/"window".',
        'acao_limite_custo': 'Em AgenteIA. Provável: "menu"/"encerrar"/"continuar"/"bloquear" (alinhado com nosso `limite_custo_acao`).',
        'engine': 'Em Conexao. Twilio/Evolution/WABA/etc.',
        'tipo_conexao': 'Em McpServer. stdio/sse/http.',
        'modelo_provedor': 'Em AgenteIA + ModeloIA. openai/anthropic/google/openrouter.',
        'state': 'Em Cliente + Conexao. Estado WhatsApp Web (CONNECTED/DISCONNECTED/QR).',
        'status': 'Genérico — significado varia por contexto (open/closed/pending/etc).',
    }
    out.append('| Campo | Semântica provável |')
    out.append('|---|---|')
    for name, sem in enum_like.items():
        out.append(f'| `{name}` | {sem} |')

    return '\n'.join(out)


# =============================================================================
# 04 — Field frequency
# =============================================================================

def gen_field_frequency():
    field_count = Counter()
    field_types = defaultdict(Counter)

    for tname, t in TYPES.items():
        if t['kind'] not in ('OBJECT', 'INPUT_OBJECT') or not is_user_type(tname):
            continue
        for f in (t.get('fields') or t.get('inputFields') or []):
            field_count[f['name']] += 1
            field_types[f['name']][render_type(f['type'])] += 1

    out = [
        '# 04 — Frequência de campos (todos os OBJECT + INPUT)',
        '',
        '> Quais nomes de campo aparecem com mais frequência. Identifica padrões e convenções.',
        '',
        '## Top 50 campos por frequência',
        '',
        '| Campo | Freq | Tipo dominante |',
        '|---|---:|---|',
    ]
    for name, n in field_count.most_common(50):
        dominant = field_types[name].most_common(1)[0][0]
        out.append(f'| `{name}` | {n} | `{dominant}` |')

    out += ['', '## Convenções universais detectadas', '',
            '- **`id`** — sempre `Float!` (BIGINT) ou `Int!` em types mais novos. Algumas tabelas usam `nanoid: String!` (ex: `AtendimentoMenuHistorico`).',
            '- **`empresa_id`** — multi-tenancy: presente em quase todo type principal. Tipo `Float` (NULL permitido em alguns? — verificar).',
            '- **`ativo`** — soft delete via string `"S"`/`"N"`. NÃO é boolean nativo.',
            '- **`data_cadastro` / `data_criacao` / `data_hora_criacao`** — timestamps DDL inconsistentes no naming.',
            '- **`criacao_usuario_id` + `alteracao_usuario_id`** — auditoria de quem criou/alterou (Usuario FK).',
            '- **`descricao`** — campo "label/nome" em muitos types onde nosso modelo usa `nome`. Em outros é descrição extra.',
            '- **`nanoid`** — chave alternativa string (NanoID) em tabelas de log/histórico (mensagens, histórico menu).',
            ]

    out += ['', '## Campos triviais / derivados (alta frequência mas pouco semântico)', '',
            '_Ignorar nesses no comparativo de paridade — são bookkeeping comum._', '',
            '- `id`, `ativo`, `empresa_id`, `data_cadastro`, `data_criacao`, `data_hora_criacao`',
            '- `criacao_usuario_id`, `alteracao_usuario_id`, `criacaoUsuario`, `alteracaoUsuario`',
            '- `data_atualizacao`, `data_hora_atualizacao`, `updated_at`',
            ]
    return '\n'.join(out)


# =============================================================================
# 05 — Parity matrix vs whatsapp-langchain (mig 039 + 040)
# =============================================================================

def gen_parity_matrix():
    """Compara campos lado a lado pra: AgenteIA, Menu, Item, AtendimentoMenuHistorico"""

    # Snapshot das nossas migrations (manual — não introspecta)
    OUR_MODEL = {
        'AgenteIA': {
            'id': 'BIGSERIAL',
            'empresa_id': 'BIGINT NOT NULL FK',
            'slug': 'TEXT NOT NULL',
            'nome': 'TEXT NOT NULL',
            'descricao': 'TEXT',
            'template_catalog': 'TEXT NOT NULL DEFAULT vsa_tech',
            'prompt_override': 'TEXT',
            'modelo': 'TEXT',
            'estilo_resposta': "TEXT NOT NULL DEFAULT equilibrado (CHECK 4 valores)",
            'temperatura_override': 'NUMERIC(3,2)',
            'max_tokens': 'INT',
            'top_p_override': 'NUMERIC(3,2)',
            'tools_enabled': 'TEXT[] DEFAULT []',
            'tools_config': 'JSONB DEFAULT {}',
            'aceita_imagem': 'BOOLEAN DEFAULT TRUE',
            'aceita_audio': 'BOOLEAN DEFAULT TRUE',
            'aceita_documento': 'BOOLEAN DEFAULT TRUE',
            'base_conhecimento_ids': 'BIGINT[] DEFAULT []',
            'variavel_ids': 'BIGINT[] DEFAULT []',
            'mcp_server_ids': 'BIGINT[] DEFAULT []',
            'limite_custo_acao': "TEXT DEFAULT solicitar_humano (CHECK 4 valores)",
            'ativo': 'BOOLEAN DEFAULT TRUE',
            'is_default': 'BOOLEAN DEFAULT FALSE',
            'created_by_user_id': 'TEXT',
            'created_at': 'TIMESTAMPTZ',
            'updated_at': 'TIMESTAMPTZ',
        },
        'Menu (menu_chatbot)': {
            'id': 'BIGSERIAL',
            'empresa_id': 'BIGINT NOT NULL FK',
            'conexao_id': 'BIGINT FK (NULL = todas)',
            'nome': 'TEXT NOT NULL',
            'ativo': 'BOOLEAN DEFAULT TRUE',
            'mensagem_boas_vindas': 'TEXT NOT NULL',
            'trigger_keywords': "TEXT[] DEFAULT [menu, opcoes, inicio]",
            'mensagem_opcao_invalida': 'TEXT DEFAULT "Opção inválida..."',
            'created_at': 'TIMESTAMPTZ',
            'updated_at': 'TIMESTAMPTZ',
            'created_by_user_id': 'TEXT',
        },
        'Item (menu_item)': {
            'id': 'BIGSERIAL',
            'menu_id': 'BIGINT NOT NULL FK',
            'parent_id': 'BIGINT FK self (NULL=raiz)',
            'ordem': 'INT NOT NULL',
            'label': 'TEXT NOT NULL',
            'acao_tipo': "TEXT CHECK (5 valores: submenu, transferir_dep, chamar_agente, enviar_msg, fechar)",
            'acao_payload': 'JSONB DEFAULT {}',
            'ativo': 'BOOLEAN DEFAULT TRUE',
            'created_at': 'TIMESTAMPTZ',
            'updated_at': 'TIMESTAMPTZ',
        },
        'AtendimentoMenuHistorico': {
            'id': 'BIGSERIAL',
            'atendimento_id': 'BIGINT FK',
            'menu_id': 'BIGINT FK',
            'item_id': 'BIGINT FK SET NULL',
            'posicao_atual_item_id': 'BIGINT FK SET NULL',
            'escolhido_at': 'TIMESTAMPTZ',
        },
    }

    ZIG_TYPES = {
        'AgenteIA': 'AgenteIA',
        'Menu (menu_chatbot)': 'Menu',
        'Item (menu_item)': 'Item',
        'AtendimentoMenuHistorico': 'AtendimentoMenuHistorico',
    }

    out = [
        '# 05 — Matriz de paridade ZigChat × whatsapp-langchain',
        '',
        '> Comparação field-by-field das 4 entidades core que tem equivalente direto.',
        '> Marcadores: ✅ presente nos dois | 🟡 presente nos dois mas semântica/tipo diferente | ❌ só em um lado.',
        '',
    ]
    for our_label, zig_name in ZIG_TYPES.items():
        z = TYPES.get(zig_name)
        if not z:
            continue
        zig_fields = {f['name']: render_type(f['type']) for f in (z.get('fields') or [])}
        our_fields = OUR_MODEL[our_label]

        # Mapeamento manual per-type pra evitar colisão de nome (`descricao`
        # significa coisas diferentes em AgenteIA vs Menu vs Item).
        EQUIV = {
            'AgenteIA': {
                'id': 'id',
                'nome': 'nome',
                'descricao': 'descricao',
                'modelo_provedor': 'modelo (parte)',
                'modelo_nome': 'modelo (parte)',
                'temperatura': 'temperatura_override',
                'max_tokens': 'max_tokens',
                'prompt_sistema': 'prompt_override',
                'tipo_memoria': None,        # gap
                'janela_memoria': None,
                'timeout_minutos': None,
                'acao_limite_custo': 'limite_custo_acao',
                'acao_limite_menu_id': None,  # gap (governança)
                'base_conhecimentos': 'base_conhecimento_ids',
                'mcp_servers': 'mcp_server_ids',
                'tool_configs': 'tools_config',
                'empresa_id': 'empresa_id',
                'ativo': 'ativo',
                'data_criacao': 'created_at',
                'data_hora_atualizacao': 'updated_at',
                'criacao_usuario': 'created_by_user_id',
                'alteracao_usuario': None,
            },
            'Menu': {
                'id': 'id',
                'descricao': 'nome (ZigChat usa "descricao" como label)',
                'atalho': None,                    # nosso é trigger_keywords (array)
                'conexao_id': 'conexao_id',
                'conexao': 'conexao_id (nested)',
                'mensagem': 'mensagem_boas_vindas',
                'arquivo': None,                   # gap (anexo nas boas-vindas)
                'principal': 'is_default (parcial — uq partial nosso)',
                'solicitar_nome': None,            # gap (wizard de coleta)
                'coleta_informacao': None,
                'enviar_msg_final_coleta': None,
                'menu_moderno': None,              # gap (botões WhatsApp)
                'confirmar_coleta': None,
                'menu_ia': None,                   # gap (menu por IA)
                'qtde_acesso': None,               # gap (counter analytics)
                'auto_navegar_para_item_id': None,
                'exibir_comando_menu_item': None,
                'resposta_confidencial': None,
                'ativo': 'ativo',
                'empresa_id': 'empresa_id',
                'empresa': 'empresa_id (nested)',
                'data_cadastro': 'created_at',
                'criacao_usuario_id': 'created_by_user_id',
                'alteracao_usuario_id': None,
                'criacaoUsuario': 'created_by_user_id (nested)',
                'alteracaoUsuario': None,
                'items': 'items (via menu_item)',
            },
            'Item': {
                'id': 'id',
                'descricao': 'label',              # ZigChat usa "descricao" como label
                'comando': None,                   # gap (alias texto)
                'mensagem': None,                  # gap (parcial em acao_payload nosso)
                'menu_id': 'menu_id',
                'menu': 'menu_id (nested)',
                'empresa_id': None,                # nosso herda via menu
                'empresa': None,
                'acao': 'acao_tipo',               # 🟡 semântica diferente: numérica vs string
                'acao_modelo_mensagem_id': None,   # gap
                'acao_menu_id': 'parent_id (parcial — só submenu)',
                'acao_departamento_id': 'acao_payload.departamento_id (JSONB)',
                'acao_atendente_id': None,         # gap
                'acao_agente_ia_id': 'acao_payload.agente_slug (JSONB)',
                'acao_setar_nome': None,           # gap
                'webhook_url': None,               # gap
                'hook_id': None,                   # gap
                'link': None,                      # gap
                'nota_min': None,                  # gap (CSAT)
                'nota_max': None,
                'nota_escolha_msg': None,
                'mudar_para_manual': None,         # gap
                'grupo': None,                     # gap (agrupador visual)
                'item_fim_coleta': None,
                'ordem': 'ordem',
                'enviar_contato_transf_depto': None,
                'contato_cliente_id': None,
                'contatoCliente': None,
                'data_cadastro': 'created_at',
                'criacao_usuario_id': None,
                'alteracao_usuario_id': None,
                'criacaoUsuario': None,
                'alteracaoUsuario': None,
                'acao_agente_ia': 'acao_payload (nested)',
                'acao_menu': 'parent (nested)',
                'acao_departamento': 'acao_payload (nested)',
                'acao_atendente': None,
                'acao_modelo_mensagem': None,
            },
            'AtendimentoMenuHistorico': {
                'nanoid': 'id (🟡 nanoid string vs nosso bigserial)',
                'resposta': None,                  # gap (texto cru)
                'data_hora': 'escolhido_at',
                'atendimento_id': 'atendimento_id',
                'atendimento': 'atendimento_id (nested)',
                'cliente_id': None,                # nosso resolve via atendimento
                'cliente': None,
                'menu_id': 'menu_id',
                'menu': 'menu_id (nested)',
                'item_id': 'item_id',
                'item': 'item_id (nested)',
            },
        }
        equiv = EQUIV.get(zig_name, {})

        out += [
            f'## `{our_label}` — ZigChat `{zig_name}`',
            '',
            f'| ZigChat campo | Tipo | → Nosso campo | Status |',
            '|---|---|---|---|',
        ]
        seen = set()
        for zname, ztype in zig_fields.items():
            target = equiv.get(zname)
            if target is None:
                if zname in ('id', 'data_cadastro', 'criacao_usuario_id',
                             'alteracao_usuario_id', 'empresa_id', 'ativo',
                             'data_criacao', 'data_hora_atualizacao',
                             'data_atualizacao', 'criacaoUsuario', 'alteracaoUsuario',
                             'empresa', 'data_hora', 'usuario_id'):
                    target_str = '_(bookkeeping comum, ignorar)_'
                    status = '✅'
                else:
                    target_str = '—'
                    status = '❌ só ZigChat'
            elif isinstance(target, str):
                target_str = f'`{target}`'
                if 'parcial' in target or 'parte' in target or 'diferente' in target:
                    status = '🟡 semântica diferente'
                else:
                    status = '✅'
                seen.add(target)
            out.append(f'| `{zname}` | `{ztype}` | {target_str} | {status} |')

        # Campos só nossos
        only_ours = [k for k in our_fields if k not in seen]
        if only_ours:
            out += ['', '**Campos extras só nossos:**', '']
            for k in only_ours:
                out.append(f'- `{k}` ({our_fields[k]})')
        out.append('')
    return '\n'.join(out)


# =============================================================================
# 06 — Migrations roadmap pra paridade
# =============================================================================

def gen_migrations_roadmap():
    out = [
        '# 06 — Migrations roadmap pra paridade ZigChat',
        '',
        '> Sequência sugerida de migrations a partir de **041** pra reduzir o gap entre nosso modelo e o ZigChat.',
        '> Cada migration é independente (pode ser aplicada isoladamente). Prioridade por valor de produto, não por dificuldade.',
        '',
        '## Estratégia geral',
        '',
        '- **ALTER TABLE** > nova migration toda — adicionar colunas opcionais é seguro com NULL/DEFAULT.',
        '- **NÃO converter** boolean/string entre formatos — manter nosso `boolean` nativo (ZigChat usa `S/N` por legado).',
        '- **NÃO copiar IDs** — usar nossas BIGSERIAL.',
        '- **Backfill idempotente** quando relevante (UPDATE com WHERE field IS NULL).',
        '',
        '## Mig 041 — Expandir menu_chatbot (baixo risco, alto valor UX)',
        '',
        '```sql',
        'ALTER TABLE menu_chatbot',
        '  ADD COLUMN atalho TEXT,                              -- "/start" / "menu"',
        '  ADD COLUMN solicitar_nome BOOLEAN DEFAULT FALSE,     -- pergunta nome se cliente novo',
        '  ADD COLUMN menu_moderno BOOLEAN DEFAULT FALSE,       -- usa botões WhatsApp em vez de "1, 2, 3"',
        '  ADD COLUMN auto_navegar_para_item_id BIGINT REFERENCES menu_item(id) ON DELETE SET NULL,',
        '  ADD COLUMN arquivo_url TEXT,                         -- anexo na boas-vindas',
        '  ADD COLUMN qtde_acesso BIGINT DEFAULT 0;             -- counter analytics',
        '',
        '-- Wizard de coleta (3 passos sequenciais)',
        'ALTER TABLE menu_chatbot',
        '  ADD COLUMN mensagem_coleta TEXT,                     -- pergunta de coleta',
        '  ADD COLUMN mensagem_confirmar_coleta TEXT,           -- "confirme: ..."',
        '  ADD COLUMN mensagem_final_coleta TEXT;               -- depois de confirmar',
        '```',
        '',
        '## Mig 042 — Expandir menu_item com 6 ações novas (alto valor)',
        '',
        '```sql',
        '-- Novos campos (compatível: NULL pra MVP)',
        'ALTER TABLE menu_item',
        '  ADD COLUMN comando TEXT,                             -- alias texto da escolha (ex: "vendas")',
        '  ADD COLUMN acao_atendente_id TEXT,                   -- transferir pra usuário específico',
        '  ADD COLUMN acao_modelo_mensagem_id BIGINT REFERENCES modelo_mensagem(id),',
        '  ADD COLUMN webhook_url TEXT,                         -- chamar URL externa',
        '  ADD COLUMN link_url TEXT,                            -- enviar link',
        '  ADD COLUMN nota_min INT,                             -- pesquisa CSAT (escala)',
        '  ADD COLUMN nota_max INT,',
        '  ADD COLUMN nota_pergunta TEXT,',
        '  ADD COLUMN grupo TEXT;                               -- agrupador visual',
        '',
        '-- Expandir CHECK acao_tipo',
        'ALTER TABLE menu_item DROP CONSTRAINT menu_item_acao_tipo_check;',
        'ALTER TABLE menu_item ADD CONSTRAINT menu_item_acao_tipo_check CHECK (',
        '  acao_tipo IN (',
        '    -- MVP',
        '    \'submenu\', \'transferir_dep\', \'chamar_agente\', \'enviar_msg\', \'fechar\',',
        '    -- Novos',
        '    \'transferir_atendente\', \'enviar_template\', \'chamar_webhook\',',
        '    \'enviar_link\', \'pesquisa_csat\', \'mudar_manual\', \'setar_nome\'',
        '  )',
        ');',
        '```',
        '',
        '## Mig 043 — Expandir agente_ia (governança custo + memória configurável)',
        '',
        '```sql',
        'ALTER TABLE agente_ia',
        '  -- Quando estoura limite custo, redireciona pro menu específico',
        '  ADD COLUMN acao_limite_menu_id BIGINT REFERENCES menu_chatbot(id) ON DELETE SET NULL,',
        '  -- Memória configurável (sobrescreve LangGraph store global)',
        '  ADD COLUMN tipo_memoria TEXT DEFAULT \'window\'',
        '    CHECK (tipo_memoria IN (\'buffer\', \'window\', \'summary\', \'none\')),',
        '  ADD COLUMN janela_memoria INT,                       -- N mensagens anteriores',
        '  ADD COLUMN timeout_minutos INT;                      -- TTL conversa idle',
        '',
        '-- Separar modelo em provedor + nome (preserva coluna antiga via deprecated)',
        'ALTER TABLE agente_ia',
        '  ADD COLUMN modelo_provedor TEXT,                     -- openai/anthropic/google/openrouter',
        '  ADD COLUMN modelo_nome TEXT;                         -- gpt-4o-mini etc',
        '',
        '-- Backfill: split do modelo único',
        'UPDATE agente_ia',
        '   SET modelo_provedor = SPLIT_PART(modelo, \'/\', 1),',
        '       modelo_nome = SPLIT_PART(modelo, \'/\', 2)',
        ' WHERE modelo IS NOT NULL AND POSITION(\'/\' IN modelo) > 0;',
        '',
        '-- Deprecar modelo único depois de UI/loader migrarem',
        'COMMENT ON COLUMN agente_ia.modelo IS \'DEPRECATED — use modelo_provedor + modelo_nome (mig 043). Removido em mig 050+.\';',
        '```',
        '',
        '## Mig 044 — Catálogo `modelo_llm` (custos + governança)',
        '',
        '```sql',
        'CREATE TABLE modelo_llm (',
        '  id BIGSERIAL PRIMARY KEY,',
        '  empresa_id BIGINT REFERENCES empresa(id) ON DELETE CASCADE,  -- NULL = global',
        '  provedor TEXT NOT NULL,                  -- openai/anthropic/google/openrouter/...',
        '  nome TEXT NOT NULL,                      -- gpt-4o-mini',
        '  descricao TEXT,',
        '  tipo TEXT NOT NULL                       -- chat/embedding/midia/audio',
        '    CHECK (tipo IN (\'chat\',\'embedding\',\'midia\',\'audio\')),',
        '  custo_input_mtok NUMERIC(10,4),         -- USD por 1M tokens input',
        '  custo_output_mtok NUMERIC(10,4),',
        '  janela_contexto INT,                    -- max tokens contexto',
        '  ativo BOOLEAN NOT NULL DEFAULT TRUE,',
        '  created_at TIMESTAMPTZ DEFAULT NOW(),',
        '  updated_at TIMESTAMPTZ DEFAULT NOW(),',
        '  UNIQUE (COALESCE(empresa_id, 0), provedor, nome)',
        ');',
        '',
        '-- Seed mínimo (pode ser ampliado por empresa via UI)',
        'INSERT INTO modelo_llm (empresa_id, provedor, nome, tipo, custo_input_mtok, custo_output_mtok, janela_contexto)',
        'VALUES',
        '  (NULL, \'openai\', \'gpt-4o-mini\', \'chat\', 0.15, 0.60, 128000),',
        '  (NULL, \'openai\', \'gpt-4o\', \'chat\', 2.50, 10.00, 128000),',
        '  (NULL, \'google\', \'gemini-2.5-flash\', \'chat\', 0.075, 0.30, 1000000),',
        '  (NULL, \'anthropic\', \'claude-haiku-4-5\', \'chat\', 1.00, 5.00, 200000),',
        '  (NULL, \'anthropic\', \'claude-sonnet-4-6\', \'chat\', 3.00, 15.00, 200000),',
        '  (NULL, \'openai\', \'whisper-1\', \'audio\', 0, 6.00, NULL),',
        '  (NULL, \'openai\', \'text-embedding-3-small\', \'embedding\', 0.02, 0, 8191)',
        'ON CONFLICT DO NOTHING;',
        '```',
        '',
        '## Mig 045 — Coluna `nanoid` em histórico (paridade ZigChat)',
        '',
        '```sql',
        '-- ZigChat usa nanoid em logs/histórico — facilita anti-enum/anti-guess.',
        '-- Mantemos BIGSERIAL como PK (performance index), só adicionamos nanoid pra exposição externa.',
        'ALTER TABLE atendimento_menu_historico',
        '  ADD COLUMN nanoid TEXT,',
        '  ADD COLUMN resposta TEXT;                            -- texto cru do cliente',
        'CREATE UNIQUE INDEX uq_atendimento_menu_historico_nanoid',
        '  ON atendimento_menu_historico (nanoid)',
        '  WHERE nanoid IS NOT NULL;',
        '',
        '-- Backfill: gera nanoid pra rows existentes (manual via app)',
        '```',
        '',
        '## Não precisa migrar (ZigChat tem mas é redundante pro nosso)',
        '',
        '- `qtde_resposta_invalida` no Atendimento — temos audit_log já.',
        '- `boolean as string "S"/"N"` — herança ZigChat. Manter nosso `BOOLEAN` nativo.',
        '- `descricao` como nome de menu — confuso, manter `nome`.',
        '- `Float` como BIGINT — ZigChat usa por convenção GraphQL. Continuar `BIGINT`/`Int`.',
        '',
        '## Sequência ideal',
        '',
        '1. **Sub-fase B** (atual MVP) — shippar, validar em prod, capturar UX feedback.',
        '2. **Mig 041 + UI** — atalho + solicitar_nome + auto_navegar (UX wins primeiro).',
        '3. **Mig 042 + worker** — 7 ações novas (transferir_atendente é a mais pedida).',
        '4. **Mig 043 + 044** — governança custo via catalogo modelo_llm + acao_limite_menu_id.',
        '5. **Mig 045** — nanoid em histórico (paridade observabilidade).',
        '',
        'Cada uma é ~1 sprint. Total: ~5 sprints pra paridade core.',
    ]
    return '\n'.join(out)


# =============================================================================
# 07 — Conventions
# =============================================================================

def gen_conventions():
    out = [
        '# 07 — Convenções e patterns adotados pelo ZigChat',
        '',
        '> O que faz sentido **adotar**, **adaptar** ou **ignorar** no nosso lado.',
        '',
        '## ✅ Adotar (já estamos fazendo, ou deveríamos)',
        '',
        '### Multi-tenancy via `empresa_id`',
        'ZigChat: `empresa_id` em quase todo OBJECT principal. **Nosso:** idem (Etapa 1 garantiu).',
        '',
        '### Soft delete via flag (`ativo`)',
        'ZigChat: `ativo: String` ("S"/"N"). **Nosso:** `ativo: BOOLEAN` (mais idiomático). Mesma semântica.',
        '',
        '### Audit fields (`criacao_usuario_id` / `alteracao_usuario_id`)',
        'ZigChat: tem nos types principais. **Nosso:** temos `created_by_user_id` em algumas tabelas + `audit_log` global. **Gap:** padronizar par created+updated_by.',
        '',
        '### UPSERT mutations padrão',
        'ZigChat: `criarAlterarX(data: XInput)` — single endpoint pra POST e PUT. **Nosso:** separamos em `POST` + `PUT`. **Decisão:** manter REST tradicional (mais explícito, melhor pra audit por verb).',
        '',
        '## 🟡 Adaptar (boa ideia, mas implementar do nosso jeito)',
        '',
        '### `XDataTable` wrapper de paginação',
        'ZigChat: `{ rows: [X], total: Int, ... }`. **Nosso:** alguns endpoints retornam `{items: []}`, outros `{rows, total, page}`. **Recomendação:** padronizar `{rows: [], total: int, page: int, page_size: int}` em todos `GET /list`.',
        '',
        '### `XInput` separado de `X` (input distinct from output)',
        'ZigChat: tem `MenuInput` separado de `Menu` (write-only fields, não retorna FKs). **Nosso:** Pydantic `CreateXInput` + `UpdateXInput`. **Mantém.**',
        '',
        '### `XListInput` + `XFilterInput` pra paginação tipada',
        'ZigChat: separa filtro + paginação. **Nosso:** query params soltos. **Recomendação:** Pydantic `XListQuery` quando endpoint cresce (ex: `cliente?segmento=...&tag=...&page=...`).',
        '',
        '### Operações em lote',
        'ZigChat: `criarAlterarItemLote(data: [ItemInput])`. **Nosso:** temos `reorder_items` mas não bulk upsert. **Recomendação:** adicionar `POST /api/v1/menus/{id}/itens/bulk` pra UI editor (drag-drop salva tudo de uma vez).',
        '',
        '## ❌ Não adotar',
        '',
        '### `boolean` em string `"S"`/`"N"`',
        'Herança Oracle/legacy. Postgres tem boolean nativo, idiomático e tipado.',
        '',
        '### `Float` pra IDs',
        'Convenção GraphQL ZigChat (Float comporta BIGINT). Em REST `integer` é mais correto. Mantém `int`.',
        '',
        '### `id` como `Float!`',
        'Idem. Nosso Pydantic + asyncpg → `int`.',
        '',
        '### `nome` vs `descricao` ambiguidade',
        'ZigChat usa `descricao` ora pra "label/nome", ora pra "descrição complementar". Inconsistente. Nosso modelo tem `nome` + `descricao` separados.',
        '',
        '## 📌 Padrões nossos que ZigChat NÃO tem',
        '',
        '- **JSONB tipado** (`tools_config`, `acao_payload`) — ZigChat usa colunas separadas (`acao_*_id`, `acao_setar_nome`, `nota_min`, `nota_max`...). **Trade-off:** colunas separadas são tipadas + indexáveis; JSONB é flexível pra evolução. Nosso JSONB é melhor pra ações compostas.',
        '- **Array Postgres** (`trigger_keywords TEXT[]`, `tools_enabled TEXT[]`) — ZigChat tem `atalho` singular + `tool_configs` lista de rows. Array é mais simples pra leitura.',
        '- **Audit log global** (`audit_log` table) — ZigChat tem `GeralLog` mas espalhado. Nosso é centralizado.',
        '- **Better Auth + RBAC granular** — ZigChat parece ter `Permissao + Grupo` mas estrutura desconhecida. Nosso `permissoes.CATALOGO` + `perfil` é explícito.',
        '- **Hooks com retry + DLQ** (`hook_dispatcher`) — ZigChat tem `Hook` mas sem indício de retry/DLQ. Nosso é production-ready.',
    ]
    return '\n'.join(out)


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    artifacts = {
        '01_overview.md':            gen_overview,
        '02_relationships.md':       gen_relationships,
        '03_enums_and_strings.md':   gen_enums,
        '04_field_frequency.md':     gen_field_frequency,
        '05_parity_matrix.md':       gen_parity_matrix,
        '06_migrations_roadmap.md':  gen_migrations_roadmap,
        '07_conventions.md':         gen_conventions,
    }
    for fname, fn in artifacts.items():
        path = HERE / fname
        path.write_text(fn())
        print(f'  {fname:35s} {path.stat().st_size:>7d} bytes')

    # README do dir analysis
    readme = HERE / 'README.md'
    readme.write_text('\n'.join([
        '# Análises do schema ZigChat',
        '',
        '> Saída do `_process.py` rodando sobre `../_schema_full.json`.',
        '> Reproduzir: `cd docs/zigchat/analysis && python3 _process.py`',
        '',
        '## Artefatos',
        '',
        '1. [01_overview.md](./01_overview.md) — métricas brutas, distribuição, naming patterns',
        '2. [02_relationships.md](./02_relationships.md) — FKs detectadas + types mais referenciados',
        '3. [03_enums_and_strings.md](./03_enums_and_strings.md) — enums formais + boolean-em-string + enums semânticos',
        '4. [04_field_frequency.md](./04_field_frequency.md) — top 50 campos + convenções universais',
        '5. [05_parity_matrix.md](./05_parity_matrix.md) — comparativo field-by-field das 4 entidades core',
        '6. [06_migrations_roadmap.md](./06_migrations_roadmap.md) — sequência sugerida de migrations 041-045 pra paridade',
        '7. [07_conventions.md](./07_conventions.md) — patterns ZigChat: o que adotar, adaptar, ignorar',
        '',
        '## Quando regerar',
        '',
        '- Se baixar nova versão do schema ZigChat (atualiza `_schema_full.json`).',
        '- Se mudar a heurística de categorização ou parity matrix manual.',
    ]))
    print(f'  README.md{"":<26} {readme.stat().st_size:>7d} bytes')
