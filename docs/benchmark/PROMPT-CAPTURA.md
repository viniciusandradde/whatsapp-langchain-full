# Prompt para capturar as telas do Chatvolt

Cole o bloco abaixo numa sessão do Claude **no seu PC** (Claude Code no
terminal, ou Claude com a extensão do Chrome). Ele já traz as rotas reais,
extraídas do `_buildManifest.js` do painel.

---

```
Preciso capturar screenshots do painel da Chatvolt (app.chatvolt.ai) para um
benchmark funcional de produto. É a minha própria conta — tenho acesso e a
sessão já está logada no meu Chrome.

CONTEXTO
O Chatvolt é uma plataforma concorrente de agentes de IA para WhatsApp. Já
mapeei a documentação e a API deles; falta a camada visual do painel, que a
documentação não cobre. Cada tela vai virar uma subseção de um documento de
análise.

IMPORTANTE SOBRE LOGIN
A Chatvolt não tem login por senha — é NextAuth: magic link por e-mail, código
de verificação, ou "Continuar com Google". Se você abrir uma janela nova e ela
pedir login, me avise e eu faço o login manualmente; depois você continua.
Se conseguir usar a sessão já aberta no meu Chrome, melhor ainda.

O QUE FAZER
Para cada rota abaixo: navegar, esperar a página carregar por completo
(inclusive dados via XHR — espere uns 4 segundos após o load), tirar
screenshot em viewport 1440x900, e salvar em ./chatvolt-img/ com o nome
indicado.

| arquivo                            | rota                     | o que observar |
|------------------------------------|--------------------------|----------------|
| chatvolt-agents-lista.png          | /agents                  | densidade da lista, ações por agente |
| chatvolt-agent-editor.png          | /agents/create           | abas do editor, ergonomia do campo de prompt |
| chatvolt-datastores.png            | /datastores              | agrupamento de fontes, status de sincronização |
| chatvolt-inbox.png                 | /logs                    | filtros, tags, score de frustração, painel do contato |
| chatvolt-crm.png                   | /crm                     | board kanban, cenários e etapas |
| chatvolt-dispatches.png            | /dispatches              | abas Active/Scheduled/Completed/Listas |
| chatvolt-artifacts.png             | /artifacts               | cadastro de produto e mídia |
| chatvolt-artifact-categories.png   | /artifact-categories     | hierarquia de categorias |
| chatvolt-contacts.png              | /contacts                | campos, variáveis, card de atribuição CTWA, exportação |
| chatvolt-voltapi.png               | /voltapi                 | editor JavaScript e assistente de IA |
| chatvolt-analytics.png             | /analytics               | quais métricas, filtros, aba de auditoria de créditos |
| chatvolt-custom-dashboard.png      | /custom-dashboard        | o cliente monta o próprio dashboard? |
| chatvolt-forms.png                 | /forms                   | o que é esse módulo (não está na documentação) |
| chatvolt-apps.png                  | /apps                    | é marketplace de integrações? |
| chatvolt-partner-set.png           | /partner-set             | programa de parceiro/revenda |
| chatvolt-onboarding.png            | /onboarding              | passos do primeiro acesso |
| chatvolt-settings-billing.png      | /settings/billing        | consumo de crédito em tempo real, alerta de limite |
| chatvolt-settings-api-keys.png     | /settings/api-keys       | tem escopo? tem rotação? |
| chatvolt-settings-llm-keys.png     | /settings/llm-keys       | quais provedores de LLM aceita (modelo BYOK) |
| chatvolt-settings-organization.png | /settings/organization   | modal de permissão por membro e por agente |

Todas as rotas são relativas a https://app.chatvolt.ai

EXTRAS, se der
- Em /settings/organization, abrir o modal de permissões de um membro (ícone de
  engrenagem) e capturar como chatvolt-permissoes-modal.png. É a tela mais
  importante do conjunto: mostra permissão por agente individual.
- Em /agents/create, abrir a aba de Tools e o editor de HTTP Tool, e capturar
  como chatvolt-http-tool.png.
- Repetir /logs e /crm em viewport 390x844 (celular), com sufixo -mobile.

DEPOIS DE CAPTURAR
1. Reduza as imagens para no máximo 1440px de largura e otimize o PNG — não
   quero arquivo de 3 MB no repositório.
2. Me diga quais rotas falharam ou redirecionaram (podem ter mudado desde que
   li o build manifest).
3. Para cada tela, escreva UMA frase sobre o que a escolha de design revela
   sobre a prioridade do produto — não descrição do que está na tela. Exemplo do
   tom que eu quero, da tela de login:

   "Não existe senha, só magic link e Google. Eles abriram mão de gerenciar
   credencial — sem hash, sem recuperação, sem política de complexidade, sem a
   superfície de ataque que vem junto. É decisão de time pequeno que prefere não
   manter o que não é o produto."

ATENÇÃO
As telas de /logs e /contacts têm conversa e contato de cliente real. Depois de
capturar, me mostre essas duas antes de qualquer coisa, para eu decidir se vão
ou não para o repositório.
```

---

## Depois

Mande as imagens para a VPS:

```bash
scp -r chatvolt-img/* opc@204.216.187.206:/home/dev/projetos/whatsapp-langchain/docs/benchmark/plataformas/chatvolt/img/
```

E me mande junto as frases de análise que o Claude do seu PC escreveu — eu
comparo com o que já inferi da documentação e escrevo as subseções de
[`plataformas/chatvolt/04-ux-flows.md`](plataformas/chatvolt/04-ux-flows.md).

## Se preferir sem prompt

O script `scripts/capture_chatvolt_local.py` faz a mesma captura de forma
determinística, sem depender de um agente navegando. Instruções no cabeçalho do
próprio arquivo.

## Como atualizar esta lista de rotas

O painel é Next.js e publica as rotas no manifesto de build, sem exigir login:

```bash
curl -s https://app.chatvolt.ai/auth/signin | grep -oE '"buildId":"[^"]+"'
curl -s https://app.chatvolt.ai/_next/static/<buildId>/_buildManifest.js
```

Rodar isso antes de qualquer captura evita chutar URL — e o diff entre duas
coletas mostra funcionalidade nova antes de qualquer anúncio.
