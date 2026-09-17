# ADR-002 — Modelo de autorização: perfis como fonte única e cobertura por módulo/função

- **Status:** aceita — 2026-09-16
- **Decisores:** Vinicius (dono) + red team e raio-X de acesso
- **Código:** `shared/empresa.py::is_admin_of`, `server/dependencies_rbac.py::require_permission`,
  `shared/perfil.py`, tabelas `permissao` / `perfil_acesso` / `perfil_permissao` / `usuario_perfil`
- **Ferramenta:** `scripts/raio_x_acesso.py` (leitura pura, roda em dev e produção)
- **Referências:** `docs/ANALISE_PERMISSOES.md`, `docs/zigchat/` (142 permissões em 34 categorias) e
  `docs/zigchat/controle-de-acesso.md` (o *mecanismo* — 2ª introspecção),
  blueprint `docs/one-for-all-main/` (árvore de permissões, telas de inconsistência)

## Contexto

O Nexus tem **dois modelos de autorização convivendo**:

- `require_permission("x")` — resolve por **perfil** (RBAC granular, com escopo `.own`/`.all`, migs 083/084);
- `is_admin_of()` — lê `empresa_membro.role` **cru** e ignora perfis.

O red team (2026-09-16) classificou isso como **A4 / alto**: perfil Admin com `role='operator'` toma 403;
`role='admin'` sem perfil entra assim mesmo. A direção perigosa é a segunda — o role **sobrepõe** o perfil.

Medição do raio-X (2026-09-16):

| | Dev | Produção |
|---|--:|--:|
| Rotas com `require_permission` | 25 | — |
| Rotas no `is_admin_of` | 5 | — |
| **Rotas de negócio sem gate nenhum** | **17** | — |
| **Permissões órfãs (catálogo sem uso)** | **38 de 70 (54%)** | — |
| Permissões fantasma (código sem catálogo) | 0 | — |
| Membros | — | 11 |
| **Sem nenhum perfil** | — | **9** |
| **`role='admin'` sem permissão equivalente em perfil** | — | **8** |

> ⚠️ **Correção (2026-09-16, ao implementar a Etapa 0):** a linha
> "`role='admin'` sem permissão equivalente em perfil = 8" foi medida por um raio-X que **não olhava
> `is_superadmin`**. Como `is_admin_of` checa superadmin **antes** do role, para um superadmin não existe
> divergência possível — ele passa nos dois modelos. O script foi corrigido para separar esses vínculos,
> e o risco real em produção precisa ser **remedido** com a versão nova. No dev, onde o dono é superadmin
> em todas as empresas, a divergência real era **1** (um membro não-superadmin da empresa 1018) e foi
> zerada pela Etapa 0. Isso **não invalida a Etapa 0** — os membros sem perfil continuavam dependendo do
> fallback legado —, mas reduz a urgência atribuída à Decisão 3.

Duas leituras:

1. **A UI promete o que o backend ignora.** 54% do catálogo aparece na tela de perfil e não é exigido por
   rota alguma — inclui `cliente.*` inteiro, `variavel.*`, `hook.*` e ações do dia a dia
   (`atendimento.claim`, `atendimento.close`, `atendimento.transfer`). Na prática, **qualquer membro da
   empresa cria, edita e apaga** cliente, variável, departamento e modelo de mensagem.
2. **Trocar o gate sem migrar dados quebra produção.** 8 dos 11 membros dependem exclusivamente do `role`.
   O dono é admin em 9 empresas e tem perfil equivalente em **uma**.

Comparação com o ZigChat (extração completa em `docs/zigchat/`): ele tem **142 permissões em 34 categorias**
e é *all-or-nothing por categoria* — **menos granular** que o Nexus, porém com **cobertura total e uniforme**
(quase toda categoria tem `Visualizar/Editar/Excluir/Cadastrar`). É a cobertura, não a granularidade, que
faz o sistema dele parecer completo.

## Decisões

1. **Perfis são a fonte única de autorização.** `is_admin_of` passa a derivar de **permissão**
   (`empresa.update`), não do `role`. A coluna `empresa_membro.role` **continua existindo** por
   compatibilidade (muitas chamadas dependem dela), mas deixa de mandar.

2. **A migração de dados é pré-requisito, não etapa posterior.** Antes de alterar `is_admin_of`, uma
   migração concede via perfil o que o `role` concede hoje. O critério de pronto é objetivo:
   `scripts/raio_x_acesso.py` tem que reportar `role_admin_sem_perm = 0` em produção.
   O fallback para o role legado permanece até isso valer.

3. **Toda rota de negócio tem gate.** Nenhum endpoint de negócio fica apenas com `get_empresa_context`
   (que só prova *ser membro*). Exceções legítimas e explícitas: webhooks (autenticados por
   assinatura/apikey), `health` e o `webhook_sync` (que só existe fora de produção).

4. **Catálogo sem órfã.** Permissão que existe no catálogo é exigida por alguma rota. Órfã é bug de
   produto — promete controle inexistente — e o raio-X é quem verifica.

5. **Adotamos do ZigChat a cobertura, não o modelo.** Mantemos `codigo` estruturado
   (`modulo.acao[.escopo]`) e o escopo `.own`/`.all`. Do ZigChat trazemos as **lacunas de cobertura**:
   Dashboard, Histórico (com escopo próprio de 3 níveis), Relatórios, exportar/importar planilha de
   clientes, ocultar telefone do contato, alterar período de retenção, **transferir para o agente IA**,
   operações de conexão separadas de `conexao.write` (reconectar/desconectar, limpar fila, tornar
   padrão — hoje quem pode renomear a conexão pode derrubar o WhatsApp da empresa) e
   **"editar regras e permissões" separado de "editar usuário"** (controle de escalação de privilégio).

6. **Segmentação de acesso por conexão/canal entra no modelo — como allow-list.** Hoje o escopo é
   `.own`/`.all` + departamento. Adotamos `atendimento.scope.conexao`, reusando `usuario_conexao`
   (mig 111) — que hoje é *default de envio* e passa a poder atuar como *filtro de visibilidade*.
   O ZigChat faz o inverso (deny-list `ConexaoOculta` por usuário + contexto, com default "vê tudo");
   **rejeitamos a deny-list por ser fail-open** — conexão nova nasceria visível para todos. Do desenho
   dele aproveitamos três coisas: **`contexto`** (a mesma conexão pode ser invisível na fila e visível
   no histórico — um booleano é grosseiro demais), **`motivo`** gravado na restrição (material de
   auditoria, custa uma coluna) e **opt-in por empresa** (ligar para todos de uma vez quebraria os
   clientes atuais).

8. **Exigir `X` é satisfeito por `X`, `X.own` ou `X.all`.** Descoberto ao executar a Etapa 1:
   `require_permission` comparava string exata, e **nenhum perfil system concede o código-base** —
   `PERFIS_SYSTEM` dá `atendimento.write.own` ao Operador e `atendimento.write.all` ao Gestor. Toda
   rota gateada no código-base era, na prática, **Admin-only**. **No dev**, o defeito ficou escondido porque
   os perfis da empresa 1 vieram das migs 083/084, que gravaram também os códigos-base (46/23
   permissões, contra 39/17 nas empresas semeadas pelo código) — o ambiente onde se testava era o
   único onde funcionava. **Em produção nem a empresa 1 escapa** (medido 2026-09-16: Gestor 39,
   Operador 17, e nenhuma outra empresa tem perfil system): todo membro não-superadmin que não seja
   Admin toma 403 no envio de mensagem hoje. O painel já usava esta regra (`hasPerm`), então front e backend
   discordavam: a UI mostrava o botão e a API devolvia 403. O portão responde "pode fazer isso em
   algum escopo?"; **quais linhas** o usuário vê continua sendo do handler. A recíproca não vale:
   quem exige `.all` não se contenta com o código-base. Em `dependencies_rbac.py::tem_permissao`.

9. **Não adotamos permissão direta no usuário.** *Reforçada pela 2ª introspecção:* o ZigChat **não tem
   perfil nenhum** — não existe vínculo usuário↔grupo no schema; `GrupoSistema` é um preset que a tela
   copia para `Usuario.permissoes[]`. Logo ele não é um contra-exemplo, é a demonstração do custo:
   mudar a regra de um cargo vira edição usuário a usuário, "quem pode exportar clientes?" vira
   varredura, e não existe "esperado" contra o qual auditar desvio. Exceção vira perfil.
   Do ZigChat copiamos só o atalho de onboarding (`replicarUsuario` → "criar usuário a partir de
   &lt;colega&gt;"), porque o gestor sabe dizer "igual ao Fulano" e não sabe marcar 12 permissões.

## Ordem de implantação

| Etapa | O quê | Risco |
|---|---|---|
| **0** | Migração role→perfil + conferência pelo raio-X — `scripts/migrar_role_para_perfil.py` (dry-run padrão). **FEITA no dev 2026-09-16:** divergência 0, membros sem perfil 0 | baixo (só concede) |
| **1** | `require_permission` nas rotas sem gate, com as permissões que já existem. **FEITA no dev 2026-09-16:** rotas de negócio sem gate 17 → **5**, órfãs 38 → **11**. Ver "Resultado da Etapa 1" abaixo | **médio — pode tirar acesso**; validado no dev |
| **2** | Permissões novas para as rotas sem catálogo. **FEITA no dev 2026-09-16:** rotas de negócio sem gate 5 → **0**. Ver "Resultado da Etapa 2" abaixo | médio |
| **3** | `is_admin_of` deriva de permissão (fecha o A4). **FEITA no dev 2026-09-17.** Ver "Resultado da Etapa 3" abaixo | médio, destravado pela etapa 0 |
| **4** | Escopo por conexão. **FEITA no dev 2026-09-17.** Ver "Resultado da Etapa 4" abaixo | médio |
| **5** | UI em árvore (a tabela `permissao` **já tem `modulo`**) + raio-X como tela | baixo |

## Resultado da Etapa 1 (dev, 2026-09-16)

Portões aplicados usando **só permissões que já existiam** no catálogo:
`cliente`, `variavel`, `departamento`, `modelo_mensagem`, `hook` (+ `hook.dlq.retry`),
`base_conhecimento`, `pasta` (organiza a base — mesma permissão do conteúdo), `agendamento`,
`lgpd.audit.read`, `horario.write` nas escritas, os GETs de `conexao` e — o que mais importava —
`claim` / `close` / `transfer` / `reset-thread` do atendimento, que tinham permissão própria no
catálogo e **nenhum portão na rota**.

| | Antes | Depois |
|---|--:|--:|
| Rotas de negócio sem gate | 17 | **5** |
| Permissões órfãs | 38 de 70 (54%) | **11 de 70 (16%)** |

Duas correções de medição, ambas no `scripts/raio_x_acesso.py`: `disparador.py` e `captura.py` são
autenticados por **chave de API da empresa** (`verify_api_key` / `require_scope`), não por sessão —
não há `user_id` para resolver perfil, então são exceção legítima como os webhooks, e contá-los
inflava o número.

Sobraram 5, todas dependendo de permissão que **ainda não existe** (Etapa 2): `admin.py`,
`historico.py`, `hitl.py`, `relatorios_nps.py`, `dataset_import.py`.

Uma permissão precisou ser concedida para não tirar acesso: **`conexao.read` ao Operador**
(mig `186`). O modal "Nova conversa" lê `GET /api/conexoes` para saber se a primeira mensagem é
texto livre ou template — sem o grant, a Etapa 1 derrubaria o operador. Não alarga nada: hoje ele já
lê a lista sem portão nenhum; restringir de verdade é a Etapa 4.

Conferido no dev pela API, com um Operador da empresa 900 (perfil **sem** os códigos-base):
200 em conexões/clientes/atendimentos/departamentos/modelos/base/pastas/agendamentos,
403 em variáveis, hooks, LGPD e em toda escrita fora do escopo dele.


## Resultado da Etapa 2 (dev, 2026-09-16)

Das 5 rotas que sobraram sem gate: **1 era falso-positivo do raio-X** (`historico.py` já resolve
`atendimento.read` manualmente via `effective_scope()` para aplicar escopo `.own`/`.all` — o raio-X
só reconhecia `require_permission(...)`; corrigido para reconhecer os dois padrões). Das 4 restantes:

- **`admin.py`** — 9 endpoints legados de agente/chat/métrica sem gate nenhum. Os 5 de config de
  agente (`GET/PUT /agents/{id}/config`, `GET/PUT/DELETE /agents/{id}/agente-ia-config`) **reusam
  `agente.config`**, a mesma permissão que `agente.py`/`catalogo.py` já usam para o mesmo conceito —
  esses endpoints são a versão antiga do CRUD, ainda consumida pelo frontend (`lib/api.ts`). Os 4 de
  dump/observabilidade (`/chats`, `/chats/{phone}`, `/metrics`, `/queue`) reusam `atendimento.read`
  — conteúdo de conversa é dado de atendimento, mesmo sem o filtro por departamento que
  `historico.py` aplica (gap de escopo registrado, não desta etapa). `/agents`, `/models` e
  `/empresas` ficam **sem gate de propósito**: catálogo global sem `empresa_id`, ou auto-escopado
  por `user_id` (documentado inline no arquivo).
- **`hitl.py`** — 4 endpoints de aprovação humana (HITL: `transfer_to_human`, `cancelar_agendamento`,
  `criar_agendamento`) sem gate nenhum. Permissão **nova**: `atendimento.hitl.approve` — Admin +
  Gestor, **não** Operador (é supervisão sobre o agente, não atendimento de linha).
- **`relatorios_nps.py`** — 4 endpoints de dashboard NPS/CSAT sem gate. Permissão **nova**:
  `relatorio.nps.read` (abre o módulo `relatorio` no catálogo) — Admin + Gestor + Leitura (é
  acompanhamento, o propósito do perfil Leitura), **não** Operador.
- **`dataset_import.py`** — o `POST /import` (mutador) reusa `agente.config` (mesmo domínio de
  `rag_stats.py`/`catalogo.py`: alimenta few-shot do agente). O `GET /template` fica sem gate —
  é conteúdo estático de documentação, sem `empresa_id`.

Migração `187`: cria as 2 permissões e concede a Admin/Gestor/Leitura dos perfis system já
existentes no banco (o código sozinho não alcança quem já foi semeado antes do deploy).

Conferido no dev pela API: Operador (sem as 2 perms) toma 403 em HITL e NPS; usuário promovido a
Gestor na hora (perfil real, não simulado) passa nos dois; Leitura passa em NPS e toma 403 em HITL.

## Resultado da Etapa 3 (dev, 2026-09-17)

`shared/empresa.py::is_admin_of` deixou de ler `empresa_membro.role`. Agora: superadmin (bypass,
ordem preservada) → `get_user_permissions` → `tem_permissao(perms, "empresa.update")` — a MESMA
resolução do `require_permission`, então perfil é, de fato, a fonte única; role fica só de
compatibilidade em quem lê a coluna direto. `tem_permissao` migrou de `dependencies_rbac.py` para
`shared/perfil.py` (ao lado de `get_user_permissions`) porque `shared/` não importa de `server/` —
`dependencies_rbac.py` agora importa de lá.

**Pré-condição, verificável em código, não só em prosa:** o raio-X ganhou a seção 8 — lista toda
empresa com membro e **sem** perfil system "Admin". Nessas empresas, o fallback legado de
`get_user_permissions` (passo 3) procura o perfil pelo nome e não acha: devolve conjunto vazio, e
`role='admin'` não-superadmin vira 403 no lugar de passar. `scripts/migrar_role_para_perfil.py --apply`
resolve — mesmo sem atribuir ninguém, **só semear o perfil já conserta o fallback** (a mesma
consequência contraintuitiva documentada na Etapa 0).

No dev: 1 empresa bloqueada (1012 — o conflito de nome já conhecido da Etapa 0). Conferido que não
há regressão viva ali: o único `role='admin'` da 1012 é o dono, `is_superadmin=true`, passa pelo
bypass de qualquer forma. O guard fica mesmo assim — é estrutural, não específico deste caso.

**Em produção, a seção 8 do raio-X é a pergunta que decide se pode deployar.** Com só a empresa 1
tendo perfil system (medido nesta sessão), e ela em 39/17 sem código-base mas COM o perfil "Admin"
existindo, a pré-condição desta etapa especificamente (existir o perfil, não ter o código-base) já
está satisfeita para a empresa 1 — mas nenhuma outra empresa tem o perfil, então rodar a Etapa 3
em produção **hoje** derrubaria `is_admin_of` para todo `role='admin'` fora da empresa 1. **Etapa 0
`--apply` em produção continua pré-requisito de fato, não só de papel.**

Conferido no dev pela API (`PUT /api/calendar/regras`, mesmo `is_admin_of` de billing/workflows/
empresa_admin/perfil): perfil Admin explícito não-superadmin passa na empresa certa (200) e toma
403 na empresa onde não é membro — confirma que a checagem continua por empresa, não global.
Operador e usuário sem perfil algum tomam 403. `tests/unit/test_is_admin_of.py` cobre a composição
(bypass de superadmin, código exato, variante `.own`/`.all`, ausência de `empresa.update` mesmo com
outras permissões no set).
`tests/unit/test_permissoes_etapa2.py` trava a intenção de cada grant contra `PERFIS_SYSTEM`.

## Resultado da Etapa 4 (dev, 2026-09-17)

Escopo por conexão, decidido com o dono ao começar a etapa: **só afeta `atendimento.read.own`**,
mesmo padrão do escopo por departamento — Gestor/Admin (`.all`) continuam vendo a empresa inteira,
sem filtro de conexão. Rejeitado o eixo independente (afetar até `.all`) por replicar um mecanismo
já testado em vez de abrir superfície nova.

**Correção ao texto original da Decisão 6**: não foi criada a permissão `atendimento.scope.conexao`
cogitada ali. `atendimento.scope.departamento` já existe no catálogo com essa forma — permissão só
documentando o conceito, nunca checada em código (a própria descrição dela diz "deprecated, use
.own") — e o escopo de departamento de fato deriva de `.own`/`.all`, não checa essa permissão.
Repetir o padrão descontinuado aqui readicionaria outra permissão órfã, o oposto do que as Etapas 1-2
vieram consertar.

Mecanismo (mig 188): `empresa.conexao_scope_ativo` (opt-in, default `FALSE` — zero mudança de
comportamento até a empresa ligar). Ligado, `usuario_conexao` (mig 111, hoje só "conexão padrão de
envio") passa a valer também como allow-list de visibilidade, via as colunas novas `contexto`
(`{fila,historico}`, pode divergir entre os dois — a mesma conexão visível na fila e invisível no
histórico, ou o inverso) e `motivo` (auditoria — por que esta atribuição existe). Fail-closed:
`.own` sem nenhuma conexão atribuída pro contexto vê zero, não "vê tudo por omissão" (a deny-list do
ZigChat é o contra-exemplo rejeitado na Decisão 6).

Tocado: `shared/atendimento.py::list_atendimentos` (`scope_conexao_ids`, mesma semântica None/vazio/
IDs de `scope_departamento_ids`), `shared/historico.py::_build_where`,
`shared/historico_relatorios.py::_scope` (as 4 funções de relatório: resumo/por-operador/
por-departamento/por-canal) e o contador da sidebar (`routes/atendimento.py::list_contadores`) — sem
espelhar o contador o badge divergiria da lista de verdade
(`gotcha_contagem_por_endpoint_permissao`). Resolução em `shared/permissoes.py::get_user_conexao_ids`
(mesmo formato de `get_user_departamento_ids`) e `shared/empresa.py::is_conexao_scope_ativo` — query
dedicada de 1 coluna, não `get_empresa_by_id` inteiro, porque roda em toda listagem/poll da fila.

**Fora do escopo desta etapa, de propósito**: `cliente.py` continua só com escopo de departamento.
Cliente não tem `conexao_id` direto — o vínculo é "tem atendimento num depto do user", relação
indireta que não mapeia 1:1 pra conexão (um cliente pode ter atendimentos em conexões diferentes ao
longo do tempo). Estender pra lá é decisão de design própria, não uma extensão mecânica desta.

Conferido no dev pela API, empresa 900 (2 conexões, 900 e 901): com o opt-in desligado, operador vê
atendimentos das duas conexões (baseline). Ligado e sem nenhuma atribuição em `usuario_conexao`, vê
zero (fail-closed). Atribuído só à conexão 900 com `contexto={fila}`: vê só o atendimento dessa
conexão na fila E ZERO no histórico — confirma que os contextos são independentes. Adicionado
`historico` ao array, passa a ver o mesmo atendimento nos dois. Superadmin (`.all` implícito)
continuou vendo as duas conexões o tempo todo, sem filtro. `tests/unit/test_atendimento_scope_
conexao.py` e `test_empresa_conexao_scope.py` cobrem a montagem do SQL/params e o guard de set vazio
sem tocar o banco.

## Consequências

- **Positivas:** uma fonte de verdade; a tela de perfil passa a significar o que mostra; ações sensíveis
  (exportar base de clientes, ver telefone, alterar retenção) ganham controle; o raio-X vira guarda de
  regressão — órfã ou rota sem gate viram achado, não descoberta tardia.
- **Negativas:** o catálogo cresce (mais permissões para administrar) e a etapa 1 pode **tirar acesso de
  quem hoje usa o sistema** se a etapa 0 não for conferida. Nenhuma etapa vai a produção sem passar pelo dev.
- **Dívida aceita:** `empresa_membro.role` permanece na base e no código por compatibilidade. Remover é
  outro ADR, depois que nenhuma leitura de autorização depender dele.
- **Fora do escopo deste ADR** (achados da 2ª introspecção, viraram backlog de produto):
  desativar usuário **deixa os atendimentos dele órfãos** (o ZigChat conta os abertos e obriga a
  escolher para quem transferir); teto de IA **por atendimento**; retenção **por departamento**;
  carteira `usuario↔cliente` como terceiro eixo de segmentação.
