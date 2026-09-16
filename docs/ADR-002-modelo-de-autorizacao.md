# ADR-002 — Modelo de autorização: perfis como fonte única e cobertura por módulo/função

- **Status:** aceita — 2026-09-16
- **Decisores:** Vinicius (dono) + red team e raio-X de acesso
- **Código:** `shared/empresa.py::is_admin_of`, `server/dependencies_rbac.py::require_permission`,
  `shared/perfil.py`, tabelas `permissao` / `perfil_acesso` / `perfil_permissao` / `usuario_perfil`
- **Ferramenta:** `scripts/raio_x_acesso.py` (leitura pura, roda em dev e produção)
- **Referências:** `docs/ANALISE_PERMISSOES.md`, `docs/zigchat/` (142 permissões em 34 categorias),
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
   Dashboard, Histórico (com escopo próprio), Relatórios, exportar/importar planilha de clientes,
   ocultar telefone do contato, alterar período de retenção, operações de conexão
   (reconectar, limpar fila, tornar padrão) e **"editar regras e permissões" separado de "editar usuário"**
   (controle de escalação de privilégio).

6. **Segmentação de acesso por conexão/canal entra no modelo.** Hoje o escopo é `.own`/`.all` +
   departamento. O ZigChat também segmenta por conexão (`Usuario.conexoes[]`). Adotamos como
   `atendimento.scope.conexao`, reusando `usuario_conexao` (mig 111) — que hoje é *default de envio* e
   passa a poder atuar como *filtro de visibilidade*.

7. **Não adotamos permissão direta no usuário.** O ZigChat permite exceção individual fora do perfil.
   Rejeitado: dobra a superfície de auditoria e reintroduz o problema que este ADR resolve (duas fontes
   de verdade). Exceção vira perfil.

## Ordem de implantação

| Etapa | O quê | Risco |
|---|---|---|
| **0** | Migração role→perfil + conferência pelo raio-X | baixo (só concede) |
| **1** | `require_permission` nas 17 rotas sem gate, com as permissões que já existem | **médio — pode tirar acesso**; validar no dev |
| **2** | Permissões novas (lacunas do ZigChat) + aplicar | médio |
| **3** | `is_admin_of` deriva de permissão (fecha o A4) | médio, destravado pela etapa 0 |
| **4** | Escopo por conexão | médio |
| **5** | UI em árvore (a tabela `permissao` **já tem `modulo`**) + raio-X como tela | baixo |

## Consequências

- **Positivas:** uma fonte de verdade; a tela de perfil passa a significar o que mostra; ações sensíveis
  (exportar base de clientes, ver telefone, alterar retenção) ganham controle; o raio-X vira guarda de
  regressão — órfã ou rota sem gate viram achado, não descoberta tardia.
- **Negativas:** o catálogo cresce (mais permissões para administrar) e a etapa 1 pode **tirar acesso de
  quem hoje usa o sistema** se a etapa 0 não for conferida. Nenhuma etapa vai a produção sem passar pelo dev.
- **Dívida aceita:** `empresa_membro.role` permanece na base e no código por compatibilidade. Remover é
  outro ADR, depois que nenhuma leitura de autorização depender dele.
