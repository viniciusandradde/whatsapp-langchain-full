# Agente do Luís: análise dos atendimentos e escolha de modelo

26/09/2026 · empresa 1018 (Luis Fernando Macorini) · agente "Assistente Luis Fernando"
Dados de produção, só leitura, de 20/08 a 16/09/2026. A conexão caiu em 16/09
e segue desconectada desde 21/09. Nomes, telefones e dados de pacientes foram
omitidos dos exemplos.

## Resumo

O relato do Luís procede. A causa principal **não é o modelo**: são quatro
fatores de desenho, que um modelo melhor só atenua.

1. **O agente responde no número do Luís sem se apresentar.** O prompt manda
   abrir só com "Olá, tudo bem? Como posso ajudar?" e se identificar como
   assistente apenas se perguntarem. Colegas do hospital, alunos, amigos e
   família acham que falam com o próprio Luís, então toda resposta curta vira
   uma resposta dele.
2. **O agente não vê o que o Luís responde pelo celular.** Mensagens enviadas
   do próprio aparelho (`fromMe`) são ignoradas pelo webhook da Evolution. O
   agente entra por cima de conversas que o Luís já está conduzindo.
3. **O agente lembra só dos 5 últimos turnos**, e a memória atravessa dias.
   Isso vale para todos os agentes da plataforma: o "tamanho do contexto"
   escolhido na tela nunca chega a valer.
4. **Conversas pessoais e de trabalho no mesmo número.** A lista de bloqueio
   cobre só os números cadastrados; o resto recebe atendimento.

O modelo atual (`google/gemini-3.1-flash-lite`) tem as piores notas de agente
entre os candidatos avaliados e erra onde é preciso entender a intenção, como
distinguir "pode liberar esse exame?" de um aviso. Vale trocar, mas depois de
corrigir os fatores acima e com bancada de conversas reais.

## Números do período

| Medida | Valor |
|---|---|
| Respostas do agente | 2.139, para 297 pessoas, em 490 atendimentos |
| Mensagens de contatos na lista de bloqueio (sem IA) | 1.977 |
| Chamadas ao modelo | 3.621; 30 com erro 404 "sem provedor" na OpenRouter, e nessas o agente ficou calado |
| Tokens de entrada por chamada | mediana 7.177, quase tudo é o prompt de 19,6 mil caracteres |

## O que as respostas mostram

| Padrão | Respostas | Pessoas | Por que é um problema |
|---|---|---|---|
| Resposta curtíssima ("Certo.", "Combinado.", "Fico no aguardo.") | 443 | 171 | Para quem não sabe do assistente, é o Luís respondendo |
| Pedido de decisão respondido com "registrei" sem dizer que o Luís decide | 22 | 13 | Soa como aprovação, inclusive pedido de liberação de exame no hospital |
| Conversa pessoal recebendo resposta de atendimento | 58 | 38 | "Fala mano! Beleza" vira "Como posso ajudar?"; foto de churrasco vira "estamos fora do horário de atendimento" |
| Recomeço no meio da conversa, com menos de 30 min de conversa | 19 | 17 | Perdeu o fio de algo em andamento |
| Resposta dada quando o começo da conversa já saiu da memória, depois do 5º turno | 440 (20%) | — | Pergunta de novo o que já foi dito |
| Retorno depois de mais de 24 h, com a conversa antiga na memória | 254 | — | Mistura o assunto velho com o novo |
| Fala como se fosse o Luís | 1 | 1 | "Está na sua sala?" → "Não estou na sala." |
| Inventa fato sobre o Luís | 1 | 1 | "O Luis Fernando está em atendimento e responderá…" |
| Diz "sou o Luís", assina com o nome dele ou diz ser humano | 0 | 0 | — |

**Exemplo que resume o caso**, de uma colega do hospital em 03/09, numa
conversa de trabalho:

1. Colega: "Pode liberar esse do PS para fazer o exame também!"
   Agente: "Certo, registrei a autorização para a realização do exame."
2. Colega: "Oi, está na sua sala?"
   Agente: "Não estou na sala. Posso ajudar com algo mais?"
3. Colega: "Posso ir lá falar com você?"
   Agente: "Como sou um assistente virtual, não tenho presença física. O Luis
   Fernando está em atendimento e responderá assim que possível."

A colega pode entender que o exame foi autorizado. Na segunda resposta o
agente fala como o Luís. Na terceira ele se revela e inventa onde o Luís está.

**Exemplo do fator 2:** uma colega escreve "Sim, está na chamada, eu avisei
que você ia vir falar com eles", continuando algo que o Luís combinou pelo
celular. O agente, que não viu essa conversa, responde "Olá, tudo bem? Como
posso ajudar?".

## Defeito da plataforma: o tamanho do contexto não vale

- `agents/middleware/trim.py` corta primeiro por turnos e depois por
  caracteres; o menor vence.
- O limite de turnos vem de `agente_ia.janela_memoria`. Salvar o tamanho do
  contexto na tela zera esse campo (ADR-004), e o worker usa o padrão global
  `TRIM_KEEP_TURNS=5`.
- Em produção, os 10 agentes ativos estão sem `janela_memoria`. Todos lembram
  **5 turnos**, qualquer que seja o tamanho escolhido.
- A memória é por telefone (`thread_id = telefone:agente`) e não é zerada
  entre atendimentos.

Correção proposta, de código, passando pelo dev e por PR: com tamanho de
contexto definido, o limite de turnos deixa de cortar e o limite de
caracteres governa. A memória de um atendimento antigo entra marcada como
"conversa anterior" ou é descartada depois de um intervalo longo.

## Mercado de modelos (pesquisa de 26/09/2026)

**Mais usados na OpenRouter** (7 dias até 25/09, por tokens): DeepSeek V4.1
Flash 12,9%, GLM 5.3 Flash 12,8%, Tencent Hy4 preview 7,1%, GPT-5.6 Luna
5,9%. Na categoria "atendimento ao cliente", por gasto, lideram Claude Opus 5,
Claude Sonnet 5 e Gemini 3 Flash. Por tokens, lideram GPT-5.6 Luna e DeepSeek
V4 Flash. O Gemini 3.1 Flash-Lite tem 3,0% nessa categoria.

**Notas relevantes para agente de atendimento**
(Artificial Analysis, τ-bench da Sierra, LMArena):

| Modelo | Índice agêntico AA | τ³-Banking | LMArena não-inglês | Alucinação AA (menor é melhor) | Custo por turno × atual |
|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite (atual) | 1,6 | 9,7% | #95 | 82,7% | 1,0× |
| Gemini 3.5 Flash-Lite | 14,3 | 17,5% | #61 | 34,4% | 1,3× |
| Gemini 3.8 Flash | 40,2 | 33–45% | #13 | 55,2% | 2,9× |
| GLM 5.3 Flash | 50,9 | 47,2% | #35 | 27,6% | 0,2× |
| Qwen3.8 Flash | — | 45,4% | não listado | 45,3% | 0,54× |
| Claude Haiku 4.5 | 8,0 | 9,3% | #144 | 25,7% | 3,9× |
| Claude Sonnet 5 | 43,6 | 15,7–37,3% | #56 | 39–52% | 7,7× |

Custo por turno com 7.000 tokens de entrada e 300 de saída, preços da
OpenRouter conferidos em 26/09. O Google desliga o Gemini 3.1 Flash-Lite em
07/05/2027 e indica o 3.5 Flash-Lite como substituto.

**O que dizem as fontes oficiais**

- **Meta, Termos da Plataforma WhatsApp Business** (23/09/2026): seção 4.1(g)
  proíbe "personificar […] qualquer pessoa ou entidade". IA de propósito
  geral é proibida como produto principal; IA atendendo os próprios clientes
  da empresa é permitida.
- **Meta, Política do WhatsApp Business**: automação exige caminho rápido e
  claro para um humano. Não achamos exigência explícita de avisar que é IA.
- **Anthropic**: identidade explícita do assistente no prompt; a política de
  uso exige que chatbot para o público informe que é IA e proíbe se passar
  por humano. O guia de atendimento sugere metas de 95% de compreensão, de
  aderência ao tema e de acerto no encaminhamento a humano.
- **OpenAI**, "A practical guide to building agents": medir primeiro com o
  modelo mais forte e só depois descer; avaliações automáticas desde o
  início; passar a um humano quando o agente não entende a intenção depois de
  algumas tentativas ou diante de ação de alto risco.
- **Google**: persona e restrições na instrução de sistema; a política de uso
  proíbe se passar por uma pessoa sem aviso explícito.
- **LangChain**: atendimento em etapas, cada uma com prompt e ferramentas
  próprias, ferramenta de escalar para humano e inspeção no LangSmith.

As fontes concordam em quatro pontos: o bot se apresenta como assistente e
nunca como o dono; proteções em camadas; encaminhamento a humano; avaliação
contínua.

## Recomendações, em ordem de impacto

1. **Identidade** (só prompt, sem código): o agente se apresenta como
   assistente do Luís na primeira mensagem de cada conversa nova. Fica
   proibida a primeira pessoa sobre lugar, presença, agenda e decisões. Para
   pedido de decisão, a resposta passa a ser "Anotei e vou passar ao Luís
   para ele decidir", nunca "registrei a autorização". Isso também afasta o
   risco da cláusula de personificação da Meta.
2. **Resposta do Luís pelo celular pausa a IA naquela conversa** (código,
   conexão Evolution): tratar a mensagem enviada do próprio aparelho como a
   Coexistência já trata o eco do WhatsApp Business, gravando na conversa e
   pausando o agente até "Devolver à IA". Resolve o fator 2 e boa parte do 4.
3. **Memória** (código, todos os agentes): corrigir o limite de 5 turnos.
4. **Separar pessoal e trabalho**: cadastrar família e amigos na lista de
   bloqueio. Quando a Meta aprovar o Tech Provider, a Coexistência na API
   oficial dá o mesmo resultado do item 2 com o número oficial.
5. **Modelo**: bancada com os casos reais acima como testes, com o atual como
   controle e três candidatos. **GLM 5.3 Flash** tem a melhor nota agêntica e
   a menor alucinação, e custa 0,2× o atual. **Gemini 3.8 Flash** é da mesma
   família e 2,9× o custo. **Claude Sonnet 5** serve de teto de referência, a
   7,7×. Medir: não falar como o dono, dizer "sou o assistente" quando
   perguntado, acerto no encaminhamento, aderência ao tema, custo e tempo de
   resposta. O GLM é de pesos abertos e passa pelo piso de quantização da
   ADR-001. Conferir o provedor efetivo e a latência na bancada.
6. **Reconectar o número**: a conexão está desconectada desde 21/09, então
   hoje o agente não responde ninguém.

## Resposta pelo celular pausa a IA: como o mercado faz

Pesquisa de 26/09/2026 sobre a recomendação 2.

| Sistema | Quando um humano responde | Como a IA volta | Fonte |
|---|---|---|---|
| Meta Business Agent (app WhatsApp Business) | Responder o cliente manualmente pausa o agente naquela conversa. Se o dono já está conversando, o agente só entra depois de 7 dias sem atividade | Quando o dono reativa a conversa | Central de Ajuda do WhatsApp |
| Evolution API (o motor da conexão do Luís) | Opção `stopBotFromMe`: mensagem enviada do próprio número pausa a sessão do robô com aquele contato, e ele passa a ignorar o contato | Reabrindo a sessão pela API (`changeStatus`) | Código aberto, `base-chatbot.controller.ts` e `base-chatbot.service.ts` |
| Chatwoot | Enquanto a IA é dona da conversa, o painel bloqueia a resposta do atendente; ele clica em "Assumir" e a IA sai | Devolvendo a conversa para "pendente" | PR 15438 (25/09/2026) e documentação de agent bots |
| Chatvolt | O atendente clica em "Responder" na caixa de entrada e a IA fica desativada temporariamente; também há API para ligar e desligar a IA por conversa | Botão "Ativar IA" | Documentação oficial, "Human Handoff" e `set-ai-enabled` |
| ChatNexus hoje | API oficial com Coexistência: resposta pelo app pausa a IA (igual à Meta). Painel: atender cala a IA. **Evolution: resposta pelo celular é ignorada** | "Devolver à IA" | `shared/waba_coexistence.py`, `evolution_webhook.py` |

Na Chatvolt não achamos menção à resposta dada pelo celular; o controle documentado é pelo painel e pela API.

**Conclusão:** o padrão é que a resposta humana pause a IA **naquela conversa**. A volta
é manual (botão ou reativar) e às vezes por tempo. A lacuna do ChatNexus está só na
conexão Evolution.

**Desenho proposto** (espelho da Coexistência, código na conexão Evolution):

1. A mensagem que sai do celular do dono entra na conversa como "WhatsApp (celular)" e
   no histórico do agente, para ele saber o que o dono já disse.
2. A IA pausa naquela conversa, com o mesmo mecanismo da Coexistência.
3. A IA volta pelo botão "Devolver à IA" ou, opcionalmente, depois de um tempo sem
   resposta do dono, configurável por conexão. O tempo padrão é decisão do dono.
4. Ficam fora: grupos, status, o eco de saúde da conexão e as mensagens que o próprio
   ChatNexus envia (a Evolution v2 não reemite essas, conferido no dev em 21/09).

Fontes desta seção:
- https://faq.whatsapp.com/291930066973116 e https://faq.whatsapp.com/1326310392254030
- https://github.com/EvolutionAPI/evolution-api (src/api/integrations/chatbot/base-chatbot.controller.ts)
- https://github.com/chatwoot/chatwoot/pull/15438 e https://www.chatwoot.com/hc/user-guide/articles/1677497472-how-to-use-agent-bots
- https://docs.chatvolt.ai/agent/human-handoff e https://docs.chatvolt.ai/api-reference/endpoint/conversation/set-ai-enabled

## Viabilidade por canal e pontuação do recurso

Pergunta do dono (26/09): é viável na pilha futura (Z-API, Evolution e Meta) e
quanto esse recurso pesa para concorrer com Chatvolt, Chatwoot e Meta?

### Viabilidade por canal

| Canal | O sinal existe? | Como distinguir celular de API | Esforço | Situação |
|---|---|---|---|---|
| **Evolution** (Luís, VSA hoje) | Sim: `messages.upsert` com `key.fromMe = true` chega ao webhook; hoje o ChatNexus descarta, exceto o eco de saúde | A Evolution v2 não reemite o que ela mesma envia (conferido no dev em 21/09); o payload traz `source` (android, ios, web) para conferência extra; o eco de saúde já é reconhecido pelo prefixo | Baixo a médio: espelhar `registrar_eco` da Coexistência (linha de saída "WhatsApp (celular)", pausa por dono sentinela, "Devolver à IA"), mais tempo opcional de retorno por conexão. Uma PR, 2 a 3 dias com testes | Viável agora |
| **Z-API** (futuro) | Sim: o webhook "Ao receber" também dispara para mensagens enviadas pelo dono quando a instância tem "notificar enviadas por mim" ligado | Campos `fromMe` e `fromApi` no payload: `fromMe = true` com `fromApi = false` é o celular; `fromApi = true` é o que saiu pela API | O provedor Z-API ainda não existe no ChatNexus (cliente, webhook, QR, envio). O recurso em si é mais um dia dentro desse projeto | Viável, junto com o provedor |
| **Meta Cloud API** (número dedicado) | Não há celular: o número sai do aplicativo ao entrar na API | Não se aplica | Zero: o "humano" é o painel, que já pausa a IA ao atender | Já coberto |
| **Meta Coexistência** | Sim: `smb_message_echoes` | A Meta separa por desenho | Zero | Feito (mig 200), inerte até a aprovação do Tech Provider |

Três canais, um só comportamento no painel: a mensagem do dono aparece na
conversa como "WhatsApp (celular)", entra na memória do agente e pausa a IA
naquela conversa até "Devolver à IA" ou até o tempo configurado.

### Como os concorrentes estão

| | Resposta pelo celular pausa a IA? | Resposta pelo painel pausa? |
|---|---|---|
| Meta (agente do app) | Sim, até reativar | Não se aplica |
| Evolution (robôs nativos) | Sim, com `stopBotFromMe`, até reabrir por API | Não há painel |
| Chatwoot | **Não documentado**; um fork (Mega) abriu em 23/09/2026 a falha exata: com uazapi, 1.338 mensagens do celular em 141 conversas em duas semanas e o robô seguiu respondendo junto com o atendente | Sim, "Assumir" (desde 25/09/2026) |
| Chatvolt | **Não documentado** (só painel e API) | Sim, "Responder" e "Ativar IA" |
| ChatNexus | Só na Coexistência da Meta | Sim, "Atender" |

### Pontuação

Escala de 0 a 10 por critério, com peso.

| Critério | Peso | Nota | Justificativa |
|---|---|---|---|
| Dor real do cliente | 30% | 9 | O Luís conduz conversas pelo celular e o agente entra por cima; o mesmo padrão derrubou negociações no fork do Chatwoot (1.338 mensagens em 141 conversas) |
| Presença nos concorrentes | 20% | 7 | Meta e Evolution têm nativo; Chatwoot e Chatvolt, os concorrentes de painel, não documentam para celular. Ter nos três canais é paridade com a Meta e vantagem sobre os dois painéis |
| Alinhamento com a estratégia | 20% | 10 | É exatamente o modelo "IA co-piloto, não handoff" decidido pelo dono: a IA responde, a pessoa entra e sai sem apertar botão |
| Esforço e reuso | 15% | 8 | Evolution reaproveita a Coexistência; Z-API entra junto com o provedor; Meta dedicado não precisa |
| Risco | 15% | 7 | Falsos positivos a tratar: eco de saúde, grupos, status, WhatsApp Web do dono (deve contar como dono), mensagens do painel (não voltam pelo webhook). Retorno por tempo precisa de padrão bem escolhido |

**Nota final: 8,4 de 10. Recurso importante, recomendado.** Ordem sugerida:
Evolution primeiro (é o canal do Luís e da maioria dos clientes de hoje),
Z-API quando o provedor entrar, Coexistência já pronta.

Decisões que ficam com o dono: o tempo padrão de retorno da IA depois da
resposta pelo celular (a Meta pausa até reativar; a Evolution pausa até reabrir
por API; a proposta é "até Devolver à IA", com tempo opcional por conexão) e se
a mensagem do celular entra na memória do agente como fala do operador, que é
o desenho da Coexistência e o recomendado.

Fontes desta seção:
- https://developer.z-api.io/en/webhooks/on-message-received-notify-fromme e https://developer.z-api.io/webhooks/on-message-received-examples
- https://github.com/EvolutionAPI/evolution-api (src/api/integrations/channel/whatsapp/whatsapp.baileys.service.ts, campo `source`)
- https://github.com/megaapp977/stack/issues/673 (fork do Chatwoot, 23/09/2026)
- https://github.com/chatwoot/chatwoot/pull/15438
- https://docs.chatvolt.ai/agent/human-handoff

## Fontes (acessadas em 26/09/2026)

- OpenRouter rankings: https://openrouter.ai/rankings e preços https://openrouter.ai/api/v1/models
- Artificial Analysis: https://artificialanalysis.ai/models/gemini-3-1-flash-lite-preview (e páginas dos demais modelos)
- τ-bench (Sierra): https://taubench.com · https://github.com/sierra-research/tau2-bench
- LMArena: https://arena.ai/leaderboard/text
- Berkeley Function Calling Leaderboard: https://gorilla.cs.berkeley.edu/leaderboard.html
- Vectara hallucination leaderboard: https://github.com/vectara/hallucination-leaderboard
- Google, descontinuação de modelos: https://ai.google.dev/gemini-api/docs/deprecations
- Meta, Termos da Plataforma WhatsApp Business: https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform
- Meta, provedores de IA: https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers
- WhatsApp Business Policy: https://whatsappbusiness.com/policy/
- OpenAI, guia de agentes: https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
- OpenAI Model Spec: https://model-spec.openai.com/2026-08-18.html
- Anthropic, Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, guia de atendimento: https://platform.claude.com/docs/en/about-claude/use-case-guides/customer-support-chat
- Anthropic, consistência de persona: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/increase-consistency
- Anthropic, política de uso: https://www.anthropic.com/legal/aup
- Google, estratégias de prompt: https://ai.google.dev/gemini-api/docs/prompting-strategies
- Google, política de uso de IA generativa: https://policies.google.com/terms/generative-ai/use-policy
- LangChain, atendimento com handoffs: https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs-customer-support
