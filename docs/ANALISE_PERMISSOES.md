# Permissões, módulos e funções — diagnóstico e plano

Análise de 2026-09-16 combinando três referências: o **ZigChat** (cobertura por módulo/função), o blueprint **one-for-all** (UI de árvore, guard declarativo, telas de inconsistência) e o **modelo já existente do Nexus** (RBAC com escopo `.own`/`.all`).

Conclusão curta: **o Nexus tem o modelo mais granular dos três, e a pior cobertura.** O catálogo promete um controle que a maior parte das rotas não aplica.

---

## 1. Como os três se comparam

Números reais, extraídos por introspecção ao vivo em 2026-09-16 (`docs/zigchat/`):

| | ZigChat | one-for-all | Chat Nexus |
|---|---|---|---|
| **Permissões** | **142** | por rotina | **68** |
| **Módulos/categorias** | **34** | por rotina | **20** |
| Granularidade | all-or-nothing **por módulo** | por rotina × ação (`read/create/update/delete`) | **por função + escopo (`.own`/`.all`)** — o mais fino |
| Cobertura | **toda função do sistema** tem permissão | por rotina cadastrada | **parcial — 44% das rotas** (ver §2) |
| Segmentação | departamento + **conexão/canal** + permissão direta no usuário | — | departamento (`atendimento.scope.departamento`) |
| Bypass global | — | `isUserTi` | `is_superadmin` |
| UI de administração | lista completa por módulo | **árvore** (grupo → módulo → aba → permissão) com seleção em lote | lista simples |
| Auditoria de acesso | — | **telas de inconsistências** (órfãs, duplicadas) + análise de perfis | — |
| Guard no front | — | `<PermissionGuard>` declarativo | `hasPerm()` inline (agora também `<PermissionGuard>`) |

**O que o dono percebe como "ZigChat é muito completo"** não é a granularidade — é a **cobertura e a uniformidade**: 34 categorias cobrem todo módulo do sistema (Dashboard, Log, Histórico, Turno, Galeria de Arquivos, WABA Saldo…), e a maioria tem a mesma matriz de 4 ações (`Visualizar`, `Editar`, `Excluir`, `Cadastrar`) — então a tela de perfil é previsível e nada fica de fora. É exatamente onde o Nexus falha.

Três ideias do ZigChat que valem adotar (detalhe em `docs/zigchat/README.md`):
1. **Escopo por conexão/canal** — o usuário tem `conexoes[]`/`canais[]` e só enxerga o que está vinculado a ele. O Nexus tem conexão *padrão de envio* (mig 111), mas não como *filtro de visibilidade*.
2. **"Editar Regras e Permissões" separado de "Editar" usuário** — impede que quem administra usuários se autoconceda permissão (controle de escalação).
3. **Permissões para ações sensíveis que hoje passam livres no Nexus**: exportar/importar planilha de clientes (LGPD), ocultar telefone do contato, alterar período de retenção, operar conexão (limpar fila, reconectar).

## 2. Diagnóstico medido do Nexus (2026-09-16)

Catálogo: **68 permissões em 20 módulos** (`agendamento`, `atendimento`, `cliente`, `conexao`, `departamento`, `disparador`, `empresa`, `hook`, `perfil`…), com escopo `.own`/`.all` em `atendimento` e `cliente`.

Aplicação nas rotas — **59 arquivos de rota no backend**:

| Situação | Qtd | Observação |
|---|---:|---|
| Usam `require_permission` | **26** | 44% |
| Gateadas por `is_admin_of` (role legado) | **7** | `billing`, `workflows`, `perfil`, `empresa_admin`, `atendimento`, `calendar_integration`, `agendamento_regras` — é o achado **A4** do red team |
| Sem permissão nem superadmin | **~25** | inclui webhooks e health (legítimo) **e ~20 rotas de negócio** |

### 2.1 Permissões órfãs — o catálogo promete o que o backend ignora
Confirmado por leitura do código: `cliente.py`, `variavel.py`, `departamento.py`, `modelo_mensagem.py` (entre outras) exigem **apenas** `verify_service_token` + `get_empresa_context` (isto é: *ser membro da empresa*). Não checam permissão.

Consequência: **qualquer membro da empresa — inclusive um perfil "somente leitura" — pode criar, editar e apagar** cliente, variável, departamento e modelo de mensagem. Enquanto isso, `cliente.write`, `cliente.delete`, `variavel.write`, `departamento.write`, `modelo_mensagem.write` **existem no catálogo e aparecem na tela de perfil**, dando a impressão de que controlam algo.

Mesma família do padrão já registrado no projeto: *a UI promete o que o backend ignora*.

### 2.2 Módulos sem permissão no catálogo
Telas que existem mas não têm permissão própria — e por isso caíram no `is_admin_of` ou em nada:
**workflow**, **billing/plano**, **relatórios/dashboard** (geral), **uso**, **traces**.
~~NPS/qualidade~~ e ~~histórico~~ ganharam cobertura na Etapa 2 (`relatorio.nps.read`;
`historico.py` era gate manual já existente, só invisível ao raio-X antigo).

## 2.3 Resultado do raio-X (`scripts/raio_x_acesso.py`, 2026-09-16)

Script de leitura pura que cruza o código (gates das rotas) com o banco (catálogo, perfis, usuários). Roda em dev e em produção:

```bash
DATABASE_URL=... uv run python scripts/raio_x_acesso.py          # texto
DATABASE_URL=... uv run python scripts/raio_x_acesso.py --json   # máquina
```

**Cobertura das rotas (dev, medição original):** 25 com `require_permission` · 5 no `is_admin_of` · 6 só superadmin · **17 de negócio sem gate nenhum** — entre elas `admin.py` (12 endpoints), `hook.py` (9), `departamento.py` (8), `cliente.py` (7), `historico.py` (7), `lgpd.py` (2).

> ✅ **Etapa 1 executada no dev (2026-09-16):** 35 com `require_permission` · 5 no `is_admin_of` ·
> 6 só superadmin · 2 por chave de API · **5 sem gate**. Órfãs: **11 de 70**. As 5 que sobraram
> (`admin.py`, `historico.py`, `hitl.py`, `relatorios_nps.py`, `dataset_import.py`) dependem de
> permissão que ainda não existia — eram a Etapa 2.
>
> ✅ **Etapa 2 executada no dev (2026-09-16):** 40 com `require_permission` · **0 sem gate**.
> `historico.py` era falso-positivo (já gateava manualmente via `effective_scope`, raio-X corrigido
> pra reconhecer o padrão). As outras 4 reusaram `agente.config`/`atendimento.read` ou ganharam
> permissão nova (`atendimento.hitl.approve`, `relatorio.nps.read` — mig 187). Detalhe em
> `docs/ADR-002-modelo-de-autorizacao.md`.

**Permissões órfãs: 38 de 70 (54%)** — mais da metade do catálogo aparece na tela de perfil e não é exigida por rota alguma. Inclui `cliente.*` inteiro, `variavel.*`, `modelo_mensagem.*`, `hook.*`, `base_conhecimento.*`, `agendamento.*` inteiro, e ações críticas do dia a dia: `atendimento.claim`, `atendimento.close`, `atendimento.transfer`, e **`empresa.update`** (que existe, mas quem manda de fato é o `is_admin_of`).

**Permissões fantasma: 0** — nenhuma rota exige permissão inexistente (bom).

### 🚨 Achado crítico para a Decisão 2 (produção)

| | Produção |
|---|--:|
| Membros (`empresa_membro`) | 11 |
| **Sem nenhum perfil** | **9** |
| **`role='admin'` SEM permissão de admin em perfil** | **8** |
| Perfil de admin sem o role | 0 |

Ou seja: o dono é `admin` em 9 empresas e tem perfil com `empresa.update` **em apenas uma** (empresa 1).

> ⚠️ **Correção de 2026-09-16 (ao implementar a Etapa 0):** esta medição **não olhava `is_superadmin`**, e `is_admin_of` checa superadmin **antes** do role — para um superadmin não existe divergência possível. No dev, o dono é `is_superadmin=true` em todas as empresas, então a divergência real era **1** (um membro não-superadmin da 1018), não 8. O raio-X foi corrigido para separar os vínculos de superadmin; **o número de produção precisa ser remedido** com a versão nova. A conclusão que se mantém: os membros **sem perfil** dependiam do fallback legado, e é isso que a Etapa 0 resolve.

Portanto a Decisão 2 / A4 tem um pré-requisito obrigatório: **migração que conceda aos membros atuais, via perfil, o que o `role` já lhes dá hoje** — e o fallback para role legado deve permanecer até essa migração rodar e ser conferida.

## 3. A feature proposta (combina os três modelos)

### Fase 1 — Fechar a cobertura (backend) · a que importa
1. Aplicar `require_permission` nas ~20 rotas de negócio hoje sem gate, usando as permissões **que já existem** no catálogo.
2. Criar as permissões faltantes para os módulos órfãos (workflow, billing, relatórios, NPS, uso, histórico).
3. Substituir `is_admin_of` por permissão nas 7 rotas legadas — **é a Decisão 2 / A4**, agora com caminho concreto: cada rota ganha a permissão do seu módulo em vez de depender do `role`.

> ⚠️ **Risco que exige decisão do dono:** ligar a checagem pode **tirar acesso de quem hoje usa o sistema**, se os perfis existentes não tiverem as permissões atribuídas. Precisa de migração de dados (conceder aos perfis atuais o que eles já usam na prática) + validação no dev antes de produção. Não é mudança para fazer direto em produção.

### Fase 2 — Tela de perfis em árvore (UI, padrão one-for-all)
Árvore **módulo → função → escopo**, com expandir/recolher em lote e marcar módulo inteiro. Hoje a tela é uma lista simples; com 68 permissões (e mais depois da Fase 1) a lista não escala. O blueprint tem o padrão pronto (`permissions-tree` + `use-tree-navigation`).

### Fase 3 — Raio-X de acesso (o diferencial, que nem ZigChat nem Nexus têm)
Tela de **inconsistências**, inspirada no `wareaudit` do blueprint:
- **Permissões órfãs** — no catálogo mas exigidas por nenhuma rota (hoje: várias).
- **Rotas sem permissão** — endpoint de negócio sem gate (hoje: ~20).
- **Divergência role × perfil** — usuário com `role='admin'` e perfil restritivo, ou o inverso. **É o bug A4 tornado visível**, e o argumento mais forte para a Fase 1.
- **Perfis sem uso** / usuários sem perfil.

## 4. O que já foi entregue nesta linha
- `<PermissionGuard>` (`components/permission-guard.tsx`) — guard declarativo do blueprint, construído sobre o `PermissionsContext` do Nexus, sem duplicar regra. **É UX, não segurança** — quem autoriza é o backend.

## 5. Ordem recomendada
1. **Fase 3 primeiro (raio-X, só leitura)** — mostra o tamanho real do problema sem alterar comportamento nem arriscar travar usuário.
2. **Fase 1** com a migração de dados guiada pelo que o raio-X mostrar.
3. **Fase 2** (árvore) quando o catálogo crescer.

Ver também: `docs/ANALISE_BLUEPRINT_ONE_FOR_ALL.md`, `docs/SEGURANCA.md` (A4, M12), `docs/obsidian-vault/03-Resources/Reference-ZigChat-API.md`.
