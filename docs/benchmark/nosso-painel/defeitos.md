# Defeitos encontrados durante a migração shadcn

Registro do que quebrou — ou já estava quebrado e só apareceu — enquanto as
telas eram migradas. Serve pra duas coisas: não reintroduzir, e não confundir
"defeito que eu criei" com "defeito que eu encontrei".

Duas seções: **incidentes** (dano causado pelo trabalho, com causa e conserto)
e **achados** (defeito pré-existente que a migração revelou).

---

## Incidentes

### I1 — Migrations aplicadas no banco de produção por um uvicorn local

**Quando.** 2026-07-31, 01:22 e 03:25 UTC.
**Gravidade.** Alta como processo. Baixa como efeito, medida abaixo.

**O que aconteceu.** Pra testar a busca de contatos com dados reais (19.647
registros), subi um `uvicorn` local com `DATABASE_URL` apontando pro banco de
produção. A API roda o migrator no startup (`server/main.py:189`), então cada
restart aplicou as migrations pendentes **do meu checkout** naquele banco:

| migration | aplicada em | efeito |
|---|---|---|
| `151_drop_wareline.sql` | 01:22:17 | `DROP TABLE wareline_credentials, wareline_sync_log` + `DELETE` da permissão `integracao.wareline.manage` |
| `152_perfis_descricao_pt.sql` | 03:25:13 | `UPDATE` na descrição dos 4 perfis de sistema |

**Por que passou despercebido.** O migrator é silencioso quando dá certo, e eu
tinha verificado que as tabelas estavam vazias *antes* de escrever a migration
— então associei "vazias" a "sem consequência" e parei de olhar. A consequência
não é o dado: é que o **código que roda em produção ainda usa o schema antigo**.

**Efeito medido em produção** (levantado depois, não presumido):

- Fila desde 01:22: **11 mensagens, todas `done`**, zero falha. O worker não
  registrou nenhum erro de `UndefinedTable`.
- `wareline_credentials` tinha **0 linhas** antes do drop. Nada de cliente
  perdido.
- As tools `wareline_*` só entram no agente `agendamentos`, ativo **somente na
  empresa 999** (sandbox). E só consultam a tabela se o LLM chamar a tool.
- **Degradação real, única:** `GET /api/integracoes/wareline` passou de
  "não configurado" pra **403** — a migration apagou a permissão que o código
  em produção ainda exige. O card Wareline em `/settings/integracoes` mostra
  erro.
- `GET /api/integracoes` responde **503**, mas isso é **pré-existente**: o
  container não tem `WARELINE_ENCRYPTION_KEY` e `_check_encryption_key()`
  derruba o módulo inteiro. Não foi este incidente.
- As 4 descrições de perfil mudaram em `/settings/perfis`. Cosmético e
  reversível; é o texto que a migration pretendia entregar, só que antes do
  deploy do resto.

**Conserto aplicado (código, não produção).** `SKIP_MIGRATIONS` — novo campo em
`Settings` (`shared/config.py`) lido por `run_migrations` (`shared/db.py`).
Quando `true`, o migrator loga `migrations_skipped` e retorna sem tocar no
schema. Qualquer processo local apontado pra banco compartilhado sobe com ele
ligado. O deploy deixa em `false`.

**Pendente de decisão do dono.** Restaurar ou não a permissão
`integracao.wareline.manage` em produção, pra o card voltar a "não configurado"
até o deploy que remove o Wareline de vez. É mais um write em produção — por
isso não foi feito sozinho.

**Lição que generaliza.** Remoção de schema tem que ir **depois** do deploy do
código que parou de usar. A ordem inversa é um outage esperando o tráfego
certo; aqui só não foi porque a feature estava morta.

---

## Achados (defeitos pré-existentes que a migração revelou)

### A1 — `.venv` do repositório apontava pro checkout antigo

`__editable__…pth` e os shebangs de `.venv/bin/*` referenciavam
`/home/dev/projetos/whatsapp-langchain`. **Todo `pytest` rodado aqui executava
o código do outro repositório**, então a suíte "passava" sem opinar sobre estas
mudanças. Resolvido com `uv venv --clear` + reinstalação editável.

### A2 — `npm run lint` nunca tinha passado

20 erros de ESLint invisíveis porque o Next 16 não roda ESLint no `build`, e o
único build real era o do `docker build` do deploy. 10 corrigidos; os 10
`set-state-in-effect` viraram dívida nomeada com override por arquivo.

### A3 — Glob de config ESLint com `[id]` nunca casava

`src/app/companies/[id]/members/**` — em glob, `[id]` é classe de caracteres
("i", "d"). O override não valia pra rota nenhuma. Corrigido com `*`.

### A4 — `/api/integracoes` responde 503 em produção

`_check_encryption_key()` exige `WARELINE_ENCRYPTION_KEY`, que não existe no
container. O módulo Integrações inteiro está desabilitado em produção — não só
o Wareline. Com o Wareline saindo, a variável foi renomeada pra
`INTEGRACOES_ENCRYPTION_KEY` (com `AliasChoices` mantendo a antiga), mas
**alguém precisa setá-la no deploy** ou o módulo continua 503.

### A5 — Item de menu ativo ficava menos visível que o inativo

Ao derivar `--accent-foreground`/`--sidebar-accent-foreground` da
`cor_secundaria` da empresa, uma empresa com `#ffffff` produzia texto branco
sobre fundo claro. Corrigido tornando superfície e foreground **neutros**:
_cor de marca pode tingir superfície, nunca decidir legibilidade_.

### A6 — Dois itens de menu acendiam ao mesmo tempo

`isItemActive` casava por prefixo, e `/settings` (Segurança) é prefixo de
metade das rotas de configuração. `/settings/perfis` acendia "Perfis de acesso"
e "Segurança". Corrigido: prefixo só vale quando nenhum item mais específico
casa (`nav-catalog.ts:242`).

### A7 — Fatia de 100% no donut sumia

Arco SVG com início e fim idênticos não desenha nada, então o gráfico ficava
vazio exatamente no caso mais comum. Corrigido com dois semicírculos.

### A8 — `Button render={<Link/>}` quebra em runtime, e o padrão antigo é pior

O `ButtonPrimitive` do Base UI assume `nativeButton` e derruba um erro de
console quando o `render` devolve `<a>`: _"A component that acts as a button
expected a native `<button>`"_. `/catalog/models` abria com **"1 Issue"** no
overlay do Next.

O padrão que já estava no código — `<Link><Button/></Link>` — não dispara o
aviso porque nem passa pelo `render`, mas empilha **dois alvos interativos**:
um `<button>` dentro de um `<a>`. Leitor de tela anuncia os dois.

Corrigido com `ButtonLink` (`components/ui/button.tsx`), que fixa
`nativeButton={false}`. **Restam 17 aninhamentos `<Link><Button>` no `src/app`**
— cada tela migrada troca os seus.

### A9 — `SelectValue` do Base UI imprime o valor, não o rótulo

Sem uma função como filho, `Select.Value` renderiza o **valor** do item
selecionado. O filtro de `/usuarios` mostrava `todos` no gatilho e "Todos os
status" na lista; no modal de desativar, teria mostrado o **UUID** do
atendente. Regra: todo `SelectValue` recebe
`{(v) => RÓTULO[v]}` — não existe caso em que imprimir o valor cru está certo.

### A10 — `AlertDialogAction` sai na cor da marca

O primitivo herda `variant="default"` do `Button`, então a confirmação de
**apagar** vinha laranja, igual ao botão de salvar. `ConfirmDestrutivo` ganhou
`tom`: `destrutivo` pinta de vermelho e avisa que não dá pra desfazer;
`serio` (reativar acesso, resetar senha) não pinta — vermelho em tudo é
vermelho em nada.

### A11 — `.env` do repositório diverge dos containers em 3 segredos

Senha do banco, `BETTER_AUTH_SECRET` e `INTERNAL_SERVICE_TOKEN` no `.env` não
são os que os containers usam. Não alterado — mas é a razão pela qual um
processo local "só funciona" quando você copia o valor do container, e isso
convida exatamente ao erro do I1.
