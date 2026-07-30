# Chatvolt — leitura de produto a partir do painel

Captura de 2026-07-28, build `fclnaS2B_QQynYrcJqYl0`, painel v4.3.19.
Conta do operador, **plano Discover (Free), 2/200 créditos**.

> **Leia primeiro: o plano limita o que estas imagens provam.** Boa parte do
> produto pago não foi observada — foi observado o *paywall* dela. Onde isso
> acontece, está marcado. Um benchmark funcional escrito só com estas telas
> descreve o que a Chatvolt vende, não o que ela entrega.

---

## Uma frase por tela

**`/agents` — lista de agentes**
O card carrega o diagnóstico na cara — modelo em uso, "Sem base de
conhecimento", e `Prompt: 8594 / 6k` em vermelho — então a lista não é índice,
é painel de saúde: eles assumem que o jeito normal de errar é configurar o
agente mal, não deixar de criá-lo.

**`/agents/create` — editor de agente** *(redireciona para `/agents`)*
Não existe rota de criação: "Novo Agente" abre modal sobre a lista, o que
denuncia que criar agente foi tratado como formulário, não como espaço de
trabalho — e faz o editor de prompt nascer dentro de uma caixa, competindo com
o fundo.

**`/datastores` — bases de conhecimento**
O card mostra "Privado" e "0 agentes" antes de mostrar conteúdo: a base é
recurso compartilhado que agentes assinam, e a pergunta que anteciparam não é
"o que tem aqui" e sim "quem está usando isto".

**`/logs` — Inbox** *(5 abas: Não Resolvidas · Não Lidas · Humano Solicitado ·
Resolvidas · Todas)*
A aba de entrada é "Não Resolvidas" e "Humano Solicitado" tem contador próprio
— a caixa é fila de trabalho com estado de resolução, não histórico; quem
desenhou isso esperava um humano de plantão, não um dono conferindo o bot.

**`/dispatches` — disparos** ⚠️ *totalmente bloqueado no Free*
Modal de upgrade em tela cheia sobre a página **desfocada** — deixam você ver o
formato do que não tem sem poder tocar, que é a decisão de quem trata disparo
em massa como o gatilho de conversão, não como funcionalidade.

**`/artifacts` — artefatos**
Cota "0 / 50" com barra de progresso no cabeçalho e o texto separando "dados
estruturados" da base de conhecimento: eles racharam RAG e registro consultável
em dois produtos, e cobram pelo segundo por unidade.

**`/artifact-categories` — categorias**
"Controle quais categorias seus agentes podem acessar" transforma a árvore de
categorias em fronteira de permissão de dados — a hierarquia não é organização,
é autorização.

**`/contacts` — contatos**
Cabeçalho com "Exportar Contatos" e "Disparar p/ Filtrados" lado a lado: a
lista de contatos foi desenhada como origem de campanha, não como cadastro —
o caminho curto sai da tabela direto para o disparo.

**`/analytics` — métricas** *(8 abas, entre elas Créditos e Anúncios)*
Aba de "Créditos" ao lado de "Anúncios" e o aviso de retenção de 90 dias no
topo: medem o que você gasta e o que a mídia paga trouxe, com a mesma
prioridade que medem conversa — é analytics de quem cobra por uso e vende para
quem compra tráfego.

**`/custom-dashboard` — dashboard customizado**
"Nenhum Dashboard Configurado — entre em contato com o administrador", e a URL
mora no perfil da organização: não é construtor, é moldura de iframe, escrita
para quem *recebe* o painel de uma agência em vez de montá-lo.

**`/forms` — formulários**
Módulo completo, com rota e listagem de envios, **ausente da barra lateral** —
construíram e não deram porta de entrada, que é o rastro de funcionalidade
entregue para um cliente específico e nunca promovida a produto.

**`/apps` — apps**
Dois cards, um vazio e quebrado, o outro um "Slack Bot" descrito em inglês como
*"ChatGPT Bot trained on company data"* no meio de um painel em português:
herança de base de código anterior que ninguém removeu nem traduziu.

**`/onboarding` — primeiro acesso** *(redireciona para `/agents`)*
Não há onboarding: jogam o usuário direto na lista de agentes, apostando que o
tutorial embutido em cada tela ("TUTORIAL", cards "DICA", chat do Frank) resolve
melhor que um passo-a-passo inicial.

**`/settings/billing` — assinatura**
É tabela de preços, não painel de consumo — o consumo real (2/200) vive fixo na
barra lateral em toda tela, o que revela onde eles querem seu olho: no medidor
o tempo todo, e na oferta só quando você vier procurar.

**`/settings/api-keys` — chaves de API**
Criar, revelar, excluir — **sem escopo, sem nome, sem validade, sem rotação, sem
último uso**: a chave é tudo-ou-nada e a única operação de ciclo de vida é
destruir, o que empurra o risco de vazamento inteiro para o cliente.

**`/settings/llm-keys` — chaves de LLM (BYOK)**
A tela mostra só Groq e ElevenLabs, ambos travados no Premium — mas o objeto da
organização carrega **seis** campos de chave (`keyOpenai`, `keyOpenrouter`,
`keyMaritaca`, `keyGroq`, `keyElevenlabs`, `keyXai`), então BYOK amplo existe no
modelo de dados e é a *interface* que o esconde: a régua de plano está na tela,
não no backend.

> Corrigido após extração de API. A leitura anterior — "BYOK é só para voz e
> inferência rápida, o modelo principal não abre" — vinha só da screenshot e
> estava errada. Ver `chatvolt-dom/settings-llm-keys.api.json`.

**`/settings/organization` — organização**
Quatro abas de topo e cinco sub-abas, com "Resumo da Empresa — usado como
contexto pelos agentes" e a URL do dashboard do cliente no mesmo formulário:
a organização é objeto de configuração de primeira classe, desenhada para quem
opera várias contas, não para quem tem uma.

---

## Rotas que falharam ou desviaram

| rota | resultado | consequência |
|------|-----------|--------------|
| `/agents/create` | → `/agents` | criação é modal; imagem é a lista de agentes |
| `/onboarding` | → `/agents` | não há fluxo de onboarding; imagem é a lista |
| `/dispatches` | modal de paywall | conteúdo real inacessível no Free |
| `/artifacts` | *falso positivo* | só acrescentou query (`?tab=…`); tela correta |

As rotas existem no `_buildManifest.js`; as falhas acima são de runtime
(gate de plano, rota que virou modal), não de URL errada.

## Fora de escopo

`/crm` (Flux CRM), `/voltapi` e `/partner-set` foram removidos desta análise —
não são recursos que vamos usar. As capturas e os dumps continuam em disco
(`chatvolt-img/`, `chatvolt-dom/`) caso a decisão mude; só não entram no
benchmark.

## Extras

- `chatvolt-permissoes-modal.png` — **não capturado** na primeira tentativa: o
  modal fica sob a sub-aba "Membros da Equipe", e a página abre em "Perfil da
  Organização". Coberto pela varredura profunda.
- `chatvolt-http-tool.png` — **não capturado**: dependia de `/agents/create`,
  que é modal. Coberto pela varredura profunda (`abre-26-ferramentas`).

## Privacidade

Não há dado de cliente terceiro. A conta tem **1 contato — o próprio operador**
(`viniciusandradde@gmail.com`) e **1 conversa de teste**. O e-mail do operador
aparece no cabeçalho de **todas** as imagens, e o ID da organização
(`cms4tdvc201ohwvczxs4zti7v`) aparece em `settings-organization`.
