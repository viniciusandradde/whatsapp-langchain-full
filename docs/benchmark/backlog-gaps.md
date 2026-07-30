# Backlog de gaps — Chatvolt → Chat Nexus

> Derivado da [matriz de paridade](matriz-paridade.md). Ordenado por
> **Impacto ÷ Esforço** (P=1, M=2, G=3). A ordem é ponto de partida mecânico;
> onde a dependência técnica manda outra coisa, o item explica.

## Resumo

| Faixa | Itens | Característica |
|---|---:|---|
| **Faixa 1** — score ≥ 3,0 | 9 | Barato e valioso. Nada aqui leva mais que dias |
| **Faixa 2** — score 2,0–2,9 | 8 | Investimento real, retorno claro |
| **Faixa 3** — score < 2,0 | 11 | Só com demanda de cliente nomeado |
| **Não replicar** | 7 | Avaliados e recusados, com justificativa |

Dois itens da Faixa 1 **não são funcionalidade nova** — são correção de bug
conhecido e uma frase no site. Começar por eles.

---

# Faixa 1 — fazer agora

## G1. Estado de IA explícito por atendimento — score 5,0

**Impacto 5 · Esforço P**

### Problema do usuário

Depois que a IA transfere o atendimento para um departamento, **ela volta a
responder** na mensagem seguinte. O cliente que já foi encaminhado para um humano
continua conversando com o robô. Está registrado em produção (atendimento 506,
2026-07-27) e nenhum ajuste de prompt resolve, porque quem reinvoca o agente é o
worker, antes do agente existir naquele turno.

### Causa

Nosso gate é **derivado**:

```python
# worker/processor.py
atd.status == "em_andamento" and atd.assigned_to_user_id
```

E a transferência para departamento faz:

```sql
SET departamento_id = %s, assigned_to_user_id = NULL, status = 'aguardando'
```

As duas condições falham. O gate só reconhece "humano assumiu", não "está na
fila do setor".

O Chatvolt não tem esse modo de falha porque usa um **booleano persistido**
(`isAiEnabled`), manipulável por API e por botão na Inbox. Estado derivado tem
combinações que ninguém previu; estado explícito não.

### Critério de aceite

- Coluna nova em `atendimento` (`ia_ativa BOOLEAN NOT NULL DEFAULT TRUE`) como
  fonte única de verdade do gate
- Transferência para departamento, transferência para atendente, modo manual e
  whitelist **escrevem** nessa coluna
- Operador liga/desliga pelo drawer de `/atendimento`, e o estado é visível
- Endpoint `PATCH /api/atendimentos/{id}/ia` respeitando `require_permission`
- Cenário ponta a ponta: cliente conversa → IA transfere → **cliente manda outra
  mensagem → IA não responde** → operador assume → operador devolve para IA → IA
  volta a responder
- Testes cobrindo as quatro origens de desligamento e a religação

### Dependências técnicas

`worker/processor.py` (gate ~linha 2255 e os markers), `shared/atendimento.py`
(transferência), `atendimento-drawer.tsx`, migration nova.

Nota de escopo: uma correção alternativa já foi desenhada — ensinar o gate a
reconhecer também "está na fila do departamento"
(`status='aguardando'` + `departamento_id` + sem `assigned`). Resolve o caso
observado com menos código, mas **mantém o estado derivado** e, com ele, a
próxima combinação não prevista. Este item a substitui por atacar a causa.
Se houver urgência, o gate ampliado serve de paliativo — desde que a coluna
explícita continue no plano.

### Diferenciação

**Copiar direto.** É a modelagem certa e não temos nada a ganhar sendo
diferentes. Divergimos só em um ponto: registrar *quem* desligou e *por quê*
(IA, operador, regra, whitelist), porque nossa auditoria é um diferencial e o
histórico de handoff é exatamente o tipo de dado que gestor pede.

---

## G2. Comunicar que o WhatsApp do celular continua funcionando — score 4,0

**Impacto 4 · Esforço P**

### Problema do usuário

A maior objeção de PME ao contratar plataforma de atendimento é achar que vai
"perder o WhatsApp do celular". O Chatvolt trata isso como argumento de venda
principal da integração, com destaque na documentação.

**Nós temos exatamente a mesma propriedade** — é característica do Embedded
Signup que já usamos — e não falamos disso em lugar nenhum.

### Critério de aceite

- Texto explícito na tela de conexão de WhatsApp, no ponto da decisão
- Mesma informação em `docs/WABA_SETUP.md`
- Validação prática documentada: conectar número existente, mandar mensagem pelo
  app do celular, confirmar que aparece no painel — e o contrário

### Dependências técnicas

Nenhuma. `frontend/src/app/connections/` e uma seção na doc.

### Diferenciação

Não é cópia de funcionalidade, é cópia de **posicionamento**. Custa uma tarde e
remove objeção de venda.

---

## G3. Publicar política de privacidade e LGPD — score 4,0

**Impacto 4 · Esforço P**

### Problema do usuário

Cliente com jurídico (rede, franquia, saúde, educação) pede política de
privacidade e termos antes de assinar. O Chatvolt tem oito páginas publicadas,
em versão brasileira e internacional.

Temos infraestrutura de LGPD superior à deles — registro de eventos, auditoria
imutável, tratamento de PII — e **nenhum documento público**. Perdemos venda por
falta de PDF, não por falta de engenharia.

### Critério de aceite

- Política de privacidade, termos de uso e política de cookies publicadas em URL
  estável
- Seção LGPD descrevendo base legal, retenção, subprocessadores e canal do titular
- Link no rodapé do painel e na tela de login
- Revisão jurídica antes de publicar

### Dependências técnicas

Rota estática no Next. O conteúdo técnico já existe: `shared/lgpd.py`,
`cliente_pii.py`, `docs/RLS_OPERATIONS.md`.

### Diferenciação

Aqui dá para **superar com honestidade**: podemos afirmar isolamento por RLS no
banco e trilha de auditoria append-only, coisas que eles não têm. Documento de
compliance que descreve controle real vale mais que boilerplate.

---

## G4. Botão "corrigir resposta" na tela de atendimento — score 4,0

**Impacto 4 · Esforço P**

### Problema do usuário

Quando o agente erra, quem percebe é o operador — que hoje não tem como agir. A
correção mora em `/dashboard/rag`, outra tela, operada por outro perfil. Na
prática, o erro não vira melhoria.

O Chatvolt resolve com um botão "improve" na própria Inbox: o operador escreve a
resposta certa e o sistema gera um datasource Q&A automaticamente.

### Critério de aceite

- Botão na bolha de resposta da IA no drawer de `/atendimento`
- Modal com a pergunta original preenchida e campo para a resposta correta
- Grava em `fewshot_example` com `fonte` marcando origem manual, vinculado ao
  atendimento e ao agente
- Exemplo passa a influenciar respostas futuras do mesmo agente
- Permissão dedicada no catálogo

### Dependências técnicas

`shared/fewshot.py` e `rag_learner.py` já existem (migs 137 e a de auto-dataset).
Falta o gatilho: `atendimento-drawer.tsx` + endpoint em `routes/atendimento.py`.
**É ligação de peças prontas, não construção.**

### Diferenciação

Copiar o gatilho, manter nosso motor. Nosso pipeline de RAG (sugestões,
avaliação, sandbox) é mais sofisticado — o que falta é a porta de entrada onde o
erro acontece.

---

## G5. Expor `query` e `send` na API pública — score 4,0

**Impacto 4 · Esforço P**

### Problema do usuário

Integrador que quer perguntar ao agente ou mandar mensagem a partir do sistema
do cliente não tem como. As duas capacidades **existem** (`routes/agente.py` para
teste, `shared/outbound.py::send_outbound_manual` para o composer), mas só são
alcançáveis pelo nosso painel.

### Critério de aceite

- `POST /api/v1/agentes/{id}/query` — pergunta e resposta, com `thread_id` opcional
- `POST /api/v1/mensagens` — envia por conexão para um número
- Autenticação por `empresa_api_key` com escopos novos (`agent.query`, `message.send`)
- Rate limit por chave, com header de limite restante
- Erros com corpo estável e documentado
- Testes Smoke + E2E no padrão de `tests/integration/test_aba_endpoints.py`

### Dependências técnicas

`shared/api_key.py` já suporta escopo, hash e expiração — falta ampliar
`normalize_scopes` e a dependência de autenticação em `server/dependencies.py`.
**É o primeiro tijolo do G10 (API pública completa)**; fazer estes dois primeiro
valida o padrão com custo baixo.

### Diferenciação

Nosso modelo de chave é tecnicamente superior ao deles (que é tudo-ou-nada, sem
expiração). Publicar com escopo desde o primeiro endpoint é diferencial real de
segurança, não só paridade.

---

## G6. Variáveis de conversa no prompt — score 3,0

**Impacto 3 · Esforço P**

### Problema do usuário

O prompt não enxerga o estado do atendimento. Não dá para escrever "se a
prioridade for alta, seja mais direto" ou "o cliente está com estas tags".

O Chatvolt expõe 25 variáveis; nós expomos `empresa.*`, `cliente.*` e `var.*`.

### Critério de aceite

- Novas variáveis: `{{atendimento.status}}`, `.prioridade`, `.tags`,
  `.departamento`, `.canal`, `.protocolo`, `.criado_em`, `{{hoje}}`
- Resolvidas no worker antes da invocação, com fallback vazio seguro
- Documentadas na aba de ajuda do editor de agente
- Teste garantindo que variável inexistente não quebra o prompt

### Dependências técnicas

`shared/variavel.py` (resolver) e o ponto de montagem do prompt em
`worker/processor.py`.

### Diferenciação

Copiar o conjunto e **copiar também o detalhe de engenharia**: eles truncam
valores longos e removem quebras de linha "para não poluir o prompt". É cuidado
que só aparece depois de errar — aproveitar de graça.

---

## G7. Horário de atendimento por conexão e por agente — score 3,0

**Impacto 3 · Esforço P**

### Problema do usuário

Empresa com WhatsApp comercial e WhatsApp de plantão precisa de horários
diferentes por número. Hoje `horario_funcionamento` é por empresa.

O Chatvolt tem `inactiveHours` como JSON **por canal**.

### Critério de aceite

- `horario_funcionamento` aceita `conexao_id` e/ou `agente_id` opcionais
- Resolução em cascata: agente → conexão → empresa
- UI em `/settings/horarios` permitindo escolher o escopo
- Migration preservando as janelas existentes como escopo empresa

### Dependências técnicas

`shared/horario.py`, migration, `/settings/horarios`.

### Diferenciação

Cascata com fallback é melhor que o JSON plano deles — configura só a exceção,
não tudo.

---

## G8. Importar lista de contatos por CSV — score 3,0

**Impacto 3 · Esforço P**

### Problema do usuário

Nossa captura de contatos depende da extensão do Chrome lendo o WhatsApp Web.
Cliente que já tem base em planilha ou CRM não consegue subir.

### Critério de aceite

- Upload de CSV com **mapeamento de coluna** para nome e telefone
- Pré-visualização e edição antes de salvar
- Normalização de telefone BR reutilizando `shared/phone_br.py` (variantes com e
  sem nono dígito)
- Relatório de linhas rejeitadas com motivo
- Deduplicação contra contatos existentes

### Dependências técnicas

`routes/disparador.py`, `shared/captura.py`, `/disparador/contatos`. `phone_br.py`
e `validators_br.py` já resolvem a parte difícil.

### Diferenciação

Copiar, e ir além no que já sabemos: cruzar com `opt_out` na importação, para a
lista nascer limpa. Eles não têm opt-out documentado.

---

## G9. Health check de webhook na configuração — score 3,0

**Impacto 3 · Esforço P**

### Problema do usuário

URL de webhook errada só é descoberta quando o evento falha e cai na DLQ. O
cliente configura, acha que está certo, e descobre depois.

O Chatvolt faz `POST` de teste antes de salvar: >5s marca "Slow", >6s ou
inalcançável marca "Unreachable", e falhas consecutivas bloqueiam
automaticamente.

### Critério de aceite

- Ao salvar hook, requisição de teste com timeout de 6s
- Resultado exibido na UI: OK / Lento / Inalcançável
- Salvar mesmo com aviso é permitido, mas o estado fica visível na lista
- Bloqueio automático após N falhas consecutivas, com desbloqueio ao re-salvar
- Contador de falhas em `hook`, alimentado pelo dispatcher

### Dependências técnicas

`shared/hook_dispatcher.py`, `routes/hook.py`, `/hooks`.

### Diferenciação

**As duas abordagens são complementares, não concorrentes.** A deles previne na
configuração; a nossa (retry exponencial + DLQ) recupera na execução. Ter as
duas é estritamente melhor que qualquer uma isolada — e é uma frase de venda:
"validamos antes e recuperamos depois".

---

# Faixa 2 — próximo trimestre

## G10. Mensagens interativas do WhatsApp — score 2,5

**Impacto 5 · Esforço M**

### Problema do usuário

Nossos menus são numéricos ("digite 1"). Cliente erra, digita texto livre, manda
áudio. Cada erro é um turno perdido e uma chance de abandono.

O WhatsApp suporta botões, listas, CTA, pedido de localização e cartão de
contato nativamente. O Chatvolt expõe os seis tipos.

### Critério de aceite

- `shared/outbound.py` aceita mensagem interativa, com fallback automático para
  texto numerado quando o provider não suporta
- `menu_chatbot` renderiza como botão (≤3 opções) ou lista (≤10)
- Webhook interpreta `button_reply` e `list_reply` e casa com o item do menu
- Workflow node `ask_choice` usa o formato nativo
- Testado nos dois providers (WABA e Evolution)

### Dependências técnicas

`shared/outbound.py`, `worker/outbound_client.py`, `routes/webhook_waba.py`,
`routes/evolution_webhook.py`, `shared/menu_chatbot.py`, `workflows/nodes.py`.
**O fallback é obrigatório** — Evolution e WABA divergem no suporte.

### Diferenciação

Copiar a capacidade, divergir na entrega: eles expõem só por API, deixando o
cliente montar. Nós já temos menu e workflow declarativos — **fazer o menu
existente virar botão automaticamente**, sem reconfiguração. Ganho para toda a
base instalada no dia do deploy.

---

## G11. Ferramenta HTTP genérica no agente — score 2,5

**Impacto 5 · Esforço M**

### Problema do usuário

Toda integração com sistema do cliente hoje exige código nosso. Consultar
pedido, checar estoque, validar CPF num ERP — cada caso vira desenvolvimento.
Não escala, e trava venda para quem tem sistema próprio.

O slug `chamar_webhook` está no nosso `BACKLOG_SLUGS` — **a UI já promete e o
backend ignora**, exatamente o padrão de `gotcha_ui_promete_o_que_backend_ignora`.

### Critério de aceite

- Nova entidade `agente_http_tool`: nome, descrição, URL, método, headers,
  parâmetros
- Parâmetro marca `fornecido_pelo_usuario` (o LLM extrai da conversa) ou valor fixo
- Registrada dinamicamente em `resolve_tools` quando o slug está marcado
- **Proteção SSRF obrigatória**: bloquear IP privado, loopback, metadata de nuvem,
  redirect para host interno
- Timeout, limite de tamanho de resposta e retry configuráveis
- Execução registrada em `ia_execucao` para custo e auditoria
- Segredos de header cifrados em repouso

### Dependências técnicas

`agents/tools/registry.py` (hoje o mapa é estático — precisa aceitar tools
dinâmicas por agente), `shared/agente_ia.py`, migration, aba Tools do editor.
A cifragem de credencial já existe em `routes/integracoes_api.py`.

### Diferenciação

Copiar o conceito; **divergir com firmeza na segurança**. Eles têm proteção SSRF
no VoltAPI mas não documentam nada equivalente na HTTP Tool. Nosso agente roda
com credencial de empresa dentro de rede com Postgres e RLS — SSRF aqui é
incidente de multi-tenancy, não bug de feature. Tratar como requisito de
segurança desde o primeiro commit, e dizer isso na venda.

---

## G12. API pública completa com portal — score 2,5

**Impacto 5 · Esforço M**

### Problema do usuário

Temos 330 endpoints e nenhum contrato externo. Integrador, agência e parceiro não
conseguem construir nada. O Chatvolt expõe 112 endpoints documentados e é isso
que permite o ecossistema deles (app no Make, automações de cliente).

### Critério de aceite

- Superfície `/api/v1/` estável cobrindo: agentes, atendimentos, mensagens,
  contatos, tags, base de conhecimento, campanhas
- Escopos por recurso e verbo em `empresa_api_key`
- Paginação **uniforme** em toda a superfície (cursor), diferente da inconsistência
  deles
- Portal público com OpenAPI gerado do FastAPI
- Rate limit por chave, com headers `X-RateLimit-*`
- Erros com corpo estável e código documentado
- Versionamento no path desde o primeiro endpoint
- Suite E2E por recurso

### Dependências técnicas

`server/dependencies.py`, `shared/api_key.py`, `shared/permissoes.py` (mapear
escopo de API para permissão). Deve vir **depois** do G5, que valida o padrão em
dois endpoints.

### Diferenciação

Fazer certo o que eles fizeram apressado: eles misturam `/api/agents/...` com
`/agents/...`, têm três estilos de paginação e chave sem escopo. Um contrato
consistente e versionado é argumento técnico legítimo para integrador — o
público que mais nota esse tipo de coisa.

---

## G13. Funil de vendas kanban — score 1,7 (prioridade elevada)

**Impacto 5 · Esforço G**

> Score puro colocaria na Faixa 3. **Sobe por dependência**: G14 e boa parte do
> valor de campanha dependem dele, e é o item que separa "plataforma de
> atendimento" de "plataforma de vendas".

### Problema do usuário

Somos ótimos em atender e cegos em vender. Não há onde ver "quantos leads estão
em negociação", nem como fazer a conversa avançar por etapas com comportamento
diferente em cada uma.

O Flux CRM deles junta kanban, máquina de estados e automação de atribuição.

### Critério de aceite

- Entidades `funil` e `funil_etapa`, com atendimento posicionado em uma etapa
- Board kanban em `/funil`: arrastar atendimento entre etapas, reordenar etapas
- Por etapa: agente responsável, **prompt extra**, mensagem de entrada, condição
  de entrada, tags a adicionar/remover, status e prioridade padrão, controle de
  IA, lógica de atribuição
- **Avanço automático por tempo** (G14)
- Evento `funil.etapa_entrou` no dispatcher de hooks
- Atendimento ativo em um funil por vez, com histórico preservado
- Limites por plano
- Suite E2E completa

### Dependências técnicas

Migration grande. `shared/atendimento.py`, `workflows/` (reusar o avaliador de
condição), `shared/hook_dispatcher.py`, tela nova. Reusar `pick_best_atendente`
e `shared/turno.py` para a atribuição — **nossa distribuição já é melhor que a
deles**, que sorteia aleatoriamente enquanto a nossa considera carga e jornada.

### Diferenciação

Copiar a estrutura, divergir em dois pontos:

1. **Condição de entrada híbrida.** Eles avaliam linguagem natural por LLM —
   flexível e caro, uma chamada extra por mensagem, sem determinismo. Oferecer
   condição determinística (tag, variável, valor) **e** linguagem natural como
   opção, deixando o custo visível na UI.
2. **Distribuição com turno e carga**, não sorteio.

Não copiar o limite artificial de "5 cenários × 20 etapas" por plano.

---

## G14. Avanço automático de etapa por tempo — score 2,0

**Impacto 4 · Esforço M**

### Problema do usuário

Conversa parada não avança sozinha. Lead que não respondeu há dois dias fica
parado; atendimento aguardando há horas não escala para ninguém.

### Critério de aceite

- Por etapa: tempo (min/horas/dias) e etapa destino
- Job periódico move o que venceu, respeitando horário de funcionamento
- Mensagem opcional ao mover
- Registrado em auditoria
- Movimentação em massa não estoura rate limit nem teto diário da conexão

### Dependências técnicas

Depende do G13. Loop do worker (padrão de `shared/resumo_diario.py`, que já faz
claim atômico 1×/dia), `shared/horario.py`, `shared/conexao_quota.py`.

### Diferenciação

Copiar, e respeitar horário comercial e teto anti-ban — proteções que já temos e
eles não. Follow-up automático que dispara de madrugada ou queima o número é
pior que não ter.

---

## G15. Follow-up automático de conversa parada — score 2,0

**Impacto 4 · Esforço M**

### Problema do usuário

Cliente para de responder no meio e ninguém reengaja. Perda silenciosa.

### Critério de aceite

- Por agente: ativar follow-up, tempo de inatividade, até N tentativas, mensagens
- Respeita horário de funcionamento, opt-out, whitelist de bloqueio e janela de
  24h do WhatsApp
- Para ao receber resposta ou ao fechar o atendimento
- Contabilizado em `ia_execucao`

### Dependências técnicas

Mesmo motor do G14; se G13/G14 saírem primeiro, isto vira configuração. Gates
existentes: `shared/opt_out.py`, `shared/whitelist.py`, `shared/horario.py`.

### Diferenciação

Ponto de cuidado: follow-up é a funcionalidade que mais rápido vira spam e
queima número. Nosso conhecimento de anti-ban
(`docs/DISPARO_MASSA_BEST_PRACTICES.md`, incidente da campanha 9) deve ser
requisito de projeto, não observação.

---

## G16. Webhook de entrada para enriquecer contato — score 2,0

**Impacto 4 · Esforço M**

### Problema do usuário

O operador vê nome e telefone. Os dados que importam (pedidos, plano, matrícula,
inadimplência) estão no sistema do cliente e não aparecem.

O Chatvolt chama uma URL configurável e mostra o retorno na Inbox.

### Critério de aceite

- Por empresa ou conexão: URL, headers, timeout, cache TTL
- Chamada ao abrir atendimento; retorno exibido no painel do cliente
- Falha degrada em silêncio (painel sem enriquecimento, sem erro visível)
- Mesmas proteções SSRF do G11
- Retorno disponível como variável de prompt

### Dependências técnicas

`shared/cliente.py`, `atendimento-drawer.tsx`, painel do cliente (já existe da
fase UX 1.1→1.4).

### Diferenciação

**Este é um padrão que vale adotar como filosofia, não como recurso isolado.**
Buscar sob demanda em vez de sincronizar elimina o problema de dado
desatualizado e nos tira da posição de reter dado de terceiro — o que é
argumento de LGPD, não só de arquitetura.

---

## G17. Leitura de site como fonte de conhecimento — score 2,0

**Impacto 4 · Esforço M**

### Problema do usuário

No onboarding, o cliente tem o conteúdo no próprio site e precisa recortar em
PDF para subir. Fricção no momento em que ele está decidindo se a ferramenta
presta.

### Critério de aceite

- Informar URL e profundidade; sistema rastreia respeitando `robots.txt`
- Limite de páginas por plano
- Extração de texto sem menu, rodapé e script
- Chunking com o pipeline existente
- Re-rastreio manual, com diff de páginas alteradas
- Progresso visível e cancelável

### Dependências técnicas

`shared/file_extractor.py`, `chunking.py`, worker assíncrono (o rastreio não pode
segurar request). Biblioteca nova de crawl → lembrar de `uv lock`.

### Diferenciação

Copiar. Divergir em uma coisa: mostrar **quais páginas** entraram, com data e
possibilidade de excluir individualmente. Crawler que engole o site inteiro sem
transparência gera resposta ruim que ninguém sabe de onde veio — e o nosso
diferencial é justamente rastreabilidade de RAG.

---

# Faixa 3 — só com demanda nomeada

Itens com score < 2,0. Não são ruins; são caros demais para o retorno **hoje**.
Cada um lista o gatilho que o promoveria.

| # | Item | Imp | Esf | Score | Gatilho para subir |
|---|---|---:|---:|---:|---|
| G18 | Score de frustração do cliente | 3 | M | 1,5 | Cliente pedir priorização de fila por risco |
| G19 | Resumo da conversa persistido e visível | 3 | M | 1,5 | Operadores reclamarem de ler histórico longo |
| G20 | ACL por instância de agente | 3 | M | 1,5 | Empresa com agentes de times distintos na mesma conta |
| G21 | Retenção de dados configurável por empresa | 3 | M | 1,5 | Exigência contratual de cliente maior |
| G22 | Integração Make / n8n | 3 | M | 1,5 | n8n primeiro — mais forte no Brasil |
| G23 | Resposta em áudio (TTS) | 3 | M | 1,5 | Nicho de baixa alfabetização digital |
| G24 | Widget de chat no site | 3 | G | 1,0 | Decisão de entrar em canal web (ver "Não replicar") |
| G25 | Instagram (DM + comentários) | 3 | G | 1,0 | Cliente de varejo/moda com operação em IG |
| G26 | Mercado Livre | 3 | G | 1,0 | Vertical de e-commerce virar foco |
| G27 | Google Drive com sync | 3 | G | 1,0 | Cliente com base viva em Drive |
| G28 | Telegram | 2 | M | 1,0 | Praticamente nunca no nosso ICP |

Itens de baixo custo que cabem em qualquer sprint com folga, sem virar projeto:
`assign` com 409 e `force` (P/2), allow-list de números (P/2),
`message-register` (P/3), citação de fonte clicável (P/2), variáveis KV por
contato (P/3), versionamento de path da API (P/3 — **fazer junto do G5**),
exibir consumo como "créditos" na UI de billing (P/3).

---

# Não replicar

Tão importante quanto a lista do que fazer. Cada item foi avaliado e **recusado
com justificativa** — se alguém quiser reabrir, precisa mostrar o que mudou.

## NR1. VoltAPI — sandbox JavaScript no produto

**O que é:** editor de JS dentro da plataforma, executado em sandbox, com
assistente de IA embutido.

**Por que não:** é uma plataforma de execução de código dentro do nosso produto.
Traz superfície de ataque (SSRF, escape de sandbox, exaustão de recurso),
necessidade de isolamento por tenant, cotas de CPU e memória, e suporte a código
de cliente que não escrevemos. Os próprios autores marcam como **experimental**.

O caso de uso legítimo — "transformar dado antes de mandar para um sistema" — é
resolvido pelo **G11 (HTTP tool)** com uma fração do risco. Quem precisa de
lógica complexa já tem n8n, Make ou o próprio backend.

**Reabriria se:** aparecer demanda repetida que a HTTP tool comprovadamente não
resolve — e ainda assim, avaliar antes uma integração n8n.

## NR2. Slack como canal de atendimento

Slack é ferramenta interna. Nosso ICP atende **cliente final** por WhatsApp; o
cliente final não está no Slack do fornecedor.

**Reabriria se:** entrarmos em suporte B2B/TI, o que seria outro produto.

## NR3. Twilio SMS

SMS no Brasil é caro, tem entrega ruim e é hostil a conversa. Já marcamos o
Twilio como legado (migration 114) por decisão consciente.

**Reabriria se:** cliente com necessidade de OTP/2FA — e mesmo assim, provedor
brasileiro, não Twilio.

## NR4. "Delayed responses" como recurso do agente

Atraso artificial para "parecer humano". Nosso debounce
(`MESSAGE_BUFFER_SECONDS`) resolve o problema real — agrupar mensagens
fragmentadas — sem simular digitação.

Fingir humanidade é escolha de produto que preferimos não fazer: o indicador de
digitação nativo do WhatsApp já dá o feedback necessário, honestamente.

## NR5. Sugestões de mensagem clicáveis

Recurso de widget web. Sem widget, sem uso. No WhatsApp, o equivalente correto
são botões nativos — que estão no **G10**.

**Reabriria se:** fizermos o widget (G24).

## NR6. Residência de dados / multi-região

Nenhum cliente pediu. Custo de infraestrutura e operação desproporcional ao ICP.
Nem o Chatvolt oferece.

**Reabriria se:** cliente público ou de saúde com exigência contratual explícita.

## NR7. Limites artificiais de estrutura por plano

Eles limitam "5 cenários de até 20 etapas" no Pro, "15 × 30" no Pro-Max.
Limitar a **forma** que o cliente modela o negócio dele gera frustração
desproporcional à receita que protege.

Nossa alavanca já é melhor: usuários, conexões, atendimentos e **orçamento de
IA** — recursos que têm custo real para nós. Cobrar pelo que custa é mais
defensável que cobrar por linha de configuração.

**Reabriria se:** algum limite estrutural virar problema real de capacidade — e
aí é limite técnico com nome honesto, não degrau comercial.

---

# Sequência sugerida

Respeita dependências e concentra valor cedo.

```
Sprint 1  (dias)      G1 · G2 · G3 · G4
                      Corrige bug conhecido, remove objeção de venda,
                      publica compliance, fecha o loop de qualidade.

Sprint 2  (1-2 sem)   G5 · G6 · G7 · G8 · G9  (+ versionamento de path)
                      Primeiros endpoints públicos validam o padrão do G12.

Sprint 3  (2-3 sem)   G10 · G11
                      Botões nativos e HTTP tool: o maior salto de percepção
                      de produto por unidade de esforço.

Sprint 4  (3-4 sem)   G12
                      API pública completa, sobre o padrão já validado.

Sprint 5+ (mês+)      G13 → G14 → G15 → G16 → G17
                      Funil e o que depende dele.
```

**A pergunta que fecha este benchmark:** os Sprints 1 e 2 somam onze itens, quase
todos de esforço P, e nenhum deles é cópia de funcionalidade nova — são bug,
posicionamento, documento jurídico, ligação de peças que já existem e exposição
de contrato. O gap real com o Chatvolt não está em capacidade de engenharia.
Está em **acabamento e comunicação do que já construímos**.
