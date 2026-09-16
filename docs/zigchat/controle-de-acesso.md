# ZigChat — como o controle de acesso funciona de verdade

Segunda introspecção de `https://dev.zigchat.com.br/api/graphql`, em **2026-09-16**, focada no
**mecanismo** de atribuição de acesso (a primeira extraiu o *catálogo*).

O schema não mudou entre as duas: **326 tipos, 171 queries, 83 mutations, 142 permissões em 34
categorias**. O que muda é o entendimento — e um dos achados **corrige** o que estava escrito no
`README.md` desta pasta e ajusta uma decisão do `ADR-002`.

---

## 1. 🔴 Não existe vínculo usuário ↔ grupo

O `GrupoSistema` **não é um perfil**. É um *preset*.

Evidência (introspecção, não inferência):

- `Usuario` não tem nenhum campo de grupo/perfil/cargo que aponte para `GrupoSistema`.
- `UsuarioInput` também não — ele recebe `permissoes: [Int]`, a **lista achatada de ids de permissão**.
- Varredura do schema inteiro: nenhum campo `grupo_sistema_id` / `grupo_id` / `perfil_id`.
- As **únicas** 4 operações de grupo são CRUD do próprio grupo:
  `listarGruposPermissoes`, `filtrarGrupoSistema`, `buscarGrupoSistemaPorId`, `criarAlterarGrupoSistema`.
  **Nenhuma mutation de vínculo.**

```graphql
input UsuarioInput { permissoes: [Int]   departamentos: [Int]  conexoes: [Int]  canais: [Int] ... }
input GrupoSistemaInput { nome: String   permissoes: [Int] ... }
type  Usuario { permissoes: [Permissao]  departamentos: [...]  conexoes: [...]  admin: String ... }
```

Ou seja: a tela escolhe um grupo, **copia as permissões para a linha do usuário**, e o vínculo acaba ali.

**Consequências (e é por isso que importa):**

| | ZigChat (permissão no usuário) | Nexus (perfil como fonte) |
|---|---|---|
| Mudar a regra de um cargo | edita **usuário por usuário** | edita 1 perfil, vale para todos |
| Responder "quem pode exportar clientes?" | varrer todos os usuários | 1 join |
| Auditar desvio | não tem como — não existe "esperado" | perfil É o esperado |
| Onboarding | `replicarUsuario` (clonar um colega) | atribuir perfil |

Isso **reforça a Decisão 7 do ADR-002** (rejeitar permissão direta no usuário) e **corrige** a leitura
anterior de que o ZigChat teria "perfil + exceção individual": ele tem **só** a exceção individual.
A sensação de completude vem da cobertura do catálogo, não do mecanismo — que é o mais fraco dos dois.

> **`replicarUsuario(usuario_replica_id, nome, email, usuario, senha)`** é a resposta pragmática do
> ZigChat à ausência de vínculo: cria um usuário clonando o acesso de outro. Vale copiar mesmo com
> perfis — "criar usuário a partir de <colega>" resolve o onboarding real, em que o gestor sabe dizer
> "igual ao Fulano" e não sabe dizer quais 12 permissões marcar.

---

## 2. 🟡 Escopo por conexão é lista de **ocultação**, não de permissão

Achado que **muda o desenho** da Decisão 6 do ADR-002 (escopo por conexão).

Eu havia proposto uma *allow-list* reusando `usuario_conexao` (mig 111). O ZigChat faz o oposto:

```graphql
type ConexaoOculta { uuid, conexao_id, usuario_id, contexto: String, motivo: String, data_hora_criacao }
query listarConexoesOcultasUsuario(contexto: String): [ConexaoOculta]
mutation criarAlterarConexaoOculta(data: ConexaoOcultaInput): Boolean
```

Mais a permissão `Atendimento · Visualizar Todas as Conexões`. O modelo é:

1. Default: o usuário vê **todas** as conexões da empresa.
2. `Visualizar Todas as Conexões` ausente → restringe às conexões vinculadas (`Usuario.conexoes[]`).
3. `ConexaoOculta` esconde conexões **específicas**, por usuário **e por `contexto`**, com `motivo` gravado.
4. `Empresa.conexao_usuario` (S/N) liga a segmentação no nível da empresa — é opt-in.

**Avaliação para o Nexus:** a deny-list é *fail-open* — conexão nova nasce visível para todo mundo, e
quem esqueceu de ocultar vazou. Mantenho a **allow-list** (fail-closed) da Decisão 6. Mas duas ideias
entram:

- **`contexto`** — a mesma conexão pode ser invisível na fila e visível no histórico/relatório. Um
  booleano "vê/não vê" é grosseiro demais.
- **`motivo`** — restrição de acesso com justificativa gravada é material de auditoria, e custa uma coluna.
- **Interruptor por empresa** (`conexao_usuario`) — ligar segmentação de conexão para todos de uma vez
  quebraria os clientes atuais. O opt-in por empresa é o caminho certo de implantação.

---

## 3. 🔴 Desativar usuário transfere a fila dele — no Nexus, não

```graphql
input UsuarioInput { ... ativo: String, acao_desativacao: Int, transferencia_usuario_id: Int }
query contarAtendimentosAbertosUsuario(usuario_id: Int): AtendimentosAbertosUsuarioResult
mutation alteraStatusUsuario(data: UsuarioInput): Usuario
```

A tela conta os atendimentos abertos **antes** de desativar e obriga a escolher o que fazer com eles
(`acao_desativacao`) e para quem transferir.

No Nexus, `set_user_status(disabled)` (mig 024) mata as sessões em <30s — e **deixa os atendimentos
atribuídos ao usuário desativado**, fora da fila e sem dono vivo. É um gap de produto real,
independente de RBAC, e aparece justamente quando alguém é desligado.

---

## 4. 🟡 Segmentação por **cliente** (carteira), que nem o ADR previu

```graphql
type UsuarioCliente { usuario_id, cliente_id, usuario, cliente }
mutation criarVinculoUsuarioCliente(data: UsuarioClienteInput): UsuarioCliente
query listarVinculoUsuarioCliente(cliente_id: Int): [UsuarioCliente]
```

Terceiro eixo de segmentação, além de departamento e conexão: **carteira de clientes por atendente**.
O ADR-002 mapeou dois eixos (departamento via `.own`, conexão na Decisão 6) — este é um terceiro.
Não proponho adotar agora; registro para não ser redescoberto como surpresa.

---

## 5. Permissões por categoria — as que expõem gaps do Nexus

### `Usuario` (6)
`Visualizar · Cadastrar · Editar · **Editar Regras e Permissões** · Excluir · Ativar/Desativar`

O **"Editar Regras e Permissões" separado de "Editar"** é controle de escalação de privilégio: quem
administra cadastro de usuário não se autoconcede acesso. O Nexus separa só parcialmente
(`empresa.member.role`), e `empresa.member.add` hoje cobre reset de senha (ver C1 do red team).

### `Conexão` (6)
`Criar Nova Conexão · Atualizar · **Limpar Fila** · **Reconectar/Desconectar** · **Tornar Padrão** · Desativar`

Ações **operacionais** separadas de "editar". No Nexus, `conexao.write` cobre tudo: quem pode renomear
a conexão pode derrubar o WhatsApp da empresa inteira.

### `Atendimento` (18) — a maior categoria
`Visualizar Atendimentos · **Visualizar Atendimentos de Outros Usuários** · **Visualizar Todas as
Conexões** · Cadastrar Atendimento · Atualizar Cliente · Transferir Atendimento · **Transferir para
Agente IA** · Ver Histórico Transferência · Ver Resultado de Pesquisas · Cadastrar Anotação ·
{Visualizar,Cadastrar,Excluir} Acompanhamento de Menções · {Visualizar Todos os, Encerrar, Vincular
usuário ao, Remover usuário do, Visualizar Participantes do} Grupo`

- "Visualizar Atendimentos de Outros Usuários" é o `.own`/`.all` do Nexus em forma binária — **o Nexus
  é mais expressivo aqui**.
- **"Transferir para Agente IA"** não tem equivalente: no Nexus, devolver a conversa à IA não é gateado.
- Toda a família **Grupo** é módulo de grupos de WhatsApp que o Nexus não tem.

### `Cliente` (7)
`Visualizar · Cadastrar · Editar · Excluir · **Exportar para Planilha** · **Importar de Planilha** · Vincular Tags`

Exportar a base de clientes é a ação mais sensível do sistema em LGPD e no Nexus **não tem gate nenhum**
(rota sem `require_permission` — ver raio-X).

### `Restrição` (1)
`**Ocultar Telefone dos Contatos**` — mascaramento de PII como permissão, não como config.

### `Empresa` (6) e `Departamento` (5)
Ambas têm `**Alterar Período de Retenção**`. O Nexus ganhou retenção na mig 185 (por empresa/agente)
**sem** permissão própria — e retenção é a configuração que apaga dados do cliente.
O ZigChat ainda tem retenção **por departamento** (`Departamento.retencao_msg`), granularidade que o
Nexus não tem.

### `Dashboard` (1), `Log` (1), `Histórico` (3), `Relatório` (2)
`Histórico` tem escopo próprio de 3 níveis (`Visualizar` / `do Departamento` / `Todos os Históricos`) —
o Nexus não gateia o módulo Histórico de forma alguma.
`Relatório · Auditoria de Arquivos Enviados e Recebidos` e `· Visualizar Pesquisa de Satisfação`
(o Nexus tem o módulo NPS, sem permissão).

---

## 6. Fora de RBAC — configurações da `Empresa` que valem registrar

Campos de `Empresa` sem equivalente no Nexus, relevantes a plano e governança de IA:

| Campo ZigChat | Observação |
|---|---|
| `max_usuario`, `max_conexao` | teto de plano **na empresa** (o Nexus tem em `plano`, e só conexões bloqueiam) |
| `limite_custo_ia_mensal` | equivale ao `ia_budget.limite_usd` |
| **`limite_custo_ia_por_atendimento`** | **teto por atendimento** — o Nexus não tem; é o freio que impede um único atendimento patológico de consumir o mês |
| `habilitar_ia` (S/N) | interruptor de IA por empresa |
| `status_bloqueio` | estado de bloqueio comercial (inadimplência) |
| `departamento_obrigatorio` | força departamento no atendimento |
| `retencao_msg` | retenção por empresa (+ por departamento) |

---

## 7. O que ficou sem resposta

A introspecção mostra o **contrato**, não a semântica. Ficaram sem determinar (precisariam de dados
reais, e não há token machine-to-machine — ver `README.md`):

- `Usuario.tipo: Int` e `Usuario.cargos: Int` — dois eixos além de `admin: String` e `permissoes[]`.
  Existe também `Funcionario.cargos`, o que sugere um módulo de RH separado. **Não sei** o que
  `tipo`/`cargos` decidem, e não vou inferir.
- `ConexaoOculta.contexto` — os valores aceitos (a query recebe `contexto: String` livre).
- `acao_desativacao: Int` — o conjunto de ações possíveis ao desativar o usuário.

---

## Impacto no que já está decidido

| Documento | Ajuste |
|---|---|
| `README.md` (esta pasta) | "GrupoSistema (= perfil)" e "permissão no usuário **além** do grupo" estavam **errados**: não há vínculo; a permissão no usuário é o **único** mecanismo. Corrigido. |
| `ADR-002` Decisão 6 (escopo por conexão) | Mantida a allow-list (fail-closed), mas o desenho ganha `contexto` e `motivo`, e implantação opt-in por empresa. |
| `ADR-002` Decisão 7 (sem permissão direta no usuário) | **Reforçada** — o ZigChat é a demonstração do custo dessa escolha, não um contra-exemplo. |
| `ADR-002` Decisão 5 (lacunas de cobertura) | Somam-se: `Transferir para Agente IA`, `Limpar Fila`/`Reconectar`/`Tornar Padrão` como permissões separadas de `conexao.write`, e escopo de 3 níveis no Histórico. |
| Fora do ADR (backlog de produto) | desativar usuário sem transferir a fila; teto de IA por atendimento; retenção por departamento; carteira `usuario↔cliente`. |
