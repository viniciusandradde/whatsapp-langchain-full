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
   rota gateada no código-base era, na prática, **Admin-only**. O defeito ficou escondido porque os
   perfis da empresa 1 vieram das migs 083/084, que gravaram também os códigos-base (46/23
   permissões, contra 39/17 nas empresas semeadas pelo código) — ou seja, o ambiente onde se testava
   era o único onde funcionava. O painel já usava esta regra (`hasPerm`), então front e backend
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
| **2** | Permissões novas (lacunas do ZigChat) + aplicar | médio |
| **3** | `is_admin_of` deriva de permissão (fecha o A4) | médio, destravado pela etapa 0 |
| **4** | Escopo por conexão | médio |
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
