# Jev (TypeSafe.ai) no Chat Nexus — menu e workflow determinísticos, e onde mais cabe

> Análise de 21/09/2026, a pedido do dono. Fontes: `https://docs.typesafe.ai/llms.txt` (índice completo lido; páginas de primitivas, confiança, estado, padrões, cookbooks, API, modelos e "jaggedness" do jev-1.13), o post *Building a harness with Jev* (LangChain) e o nosso código (`worker/processor.py`, `shared/menu_chatbot.py`, `workflows/`, `shared/guardrails/`, `agents/tools/cliente_atendimento.py`, `agents/catalog/atendimento_router/`). Números de produção medidos hoje no banco (`opc@100.116.235.14`). **Nada foi codificado.**

## 0. Resumo executivo

- **O que o Jev é:** um modelo "System One" — recebe um *estado* (texto ou JSON) e *perguntas tipadas* e devolve **respostas que o código usa direto**: `Choice` (uma opção de um conjunto fechado, com probabilidade por opção e confiança), `Score` (um nível numa escala descrita, com distribuição e confiança) e `Noul` (probabilidade 0–1 de "sim"). Não gera texto. Todas as perguntas de uma chamada são avaliadas **em paralelo** sobre o mesmo estado — "adicionar perguntas quase não muda o tempo de resposta". Preço: **US$ 0,042 por milhão de tokens de entrada, saída grátis**; contexto 64k; 1.200 requisições/min. SDK Python `typesafe-sdk` 0.7.1 (lançado 21/09/2026, Python ≥ 3.10; nós rodamos 3.12) e `langchain-typesafe` com middlewares para o `create_agent` que já usamos (`langchain==1.2.15`).
- **Onde cabe no "menu e workflow determinístico":** hoje o menu (`_try_handle_menu`) e o `ask_choice` do workflow só aceitam **o número da opção** (`parse_numero_opcao`) ou o **valor exato** (`_match_choice`); qualquer frase vira "Opção inválida". O Jev entra como **tradutor de texto livre para uma aresta que já existe** — o fluxo continua sendo a árvore/grafo, o conjunto de saídas continua fechado, o código continua decidindo o que fazer com cada faixa de confiança. É isso que preserva o determinismo: **o Jev não escolhe o caminho, ele diz qual dos caminhos existentes o cliente pediu e com que certeza**; abaixo do limiar, o comportamento é exatamente o de hoje.
- **Escopo (decisão do dono, 22/09): é o padrão do Nexus, não um acessório de canal.** A camada de decisão tipada (`shared/decisao.py`) nasce como **primitiva de plataforma**: vale para Evolution, WABA e para o futuro Canal por API igualmente, e é usada pelo menu, pelo workflow, pela triagem, pelos guardrails e pelo roteamento. O menu que entende texto livre passa a ser **o comportamento padrão do produto** — quem quiser o menu só-numérico desliga, em vez de ligar.
- **Estado atual em produção (contexto, não escopo):** **nenhum menu ou workflow está ativo e nenhum foi usado nunca** (`atendimento_menu_historico` = 0 linhas, `workflow_evento` = 0). Os 9 workflows da HPM (26 nós `ask_choice`, um com 43 opções; 46 `ask_text`; 28 `handover`) estão inativos porque o HPM roda no ZigChat; Luis (1018) e VSA (1) usam IA direta. Ou seja: **hoje o menu/workflow não tem volume nenhum para provar a camada** — quem tem volume é a IA direta (triagem, guardrails, transferência, 850 atendimentos/90 d) e, quando entrar, o HPM (≈ 35 mil msgs/mês por um menu de 43 opções). Por isso a ordem proposta é: a camada padrão primeiro nos pontos que já rodam todo dia, e o menu/workflow ganha o mesmo motor na mesma entrega — o HPM vira o **campo de prova em volume**, não o dono da funcionalidade.
- **Outras frentes (pedido adicional do dono), por valor/esforço:** (1) **triagem determinística** no worker — hoje só 48 % dos atendimentos saem classificados porque depende de o LLM lembrar de chamar `classificar_atendimento`; (2) **guardrails** de entrada/saída (14 regex + juiz `gpt-4o-mini` SAFE/UNSAFE) → perguntas Noul/Score numa chamada, mais barata e com severidade; (3) **roteamento de departamento/agente** pela intenção (o `transfer_to_human` só conhece o departamento padrão do agente); (4) **ações irreversíveis do agente** (fechar, transferir, cancelar consulta) com "trava de confiança" (`AutoModeMiddleware`); (5) **router multi-agente** (`atendimento_router` decide domínios com um LLM) → Nouls por domínio; (6) **roteamento de modelo** barato × forte por turno (`ModelRouterMiddleware`), amarrado aos créditos da ADR-004; (7) RAG (pontuar trechos da base antes de mandar ao agente), juiz calibrado para o dataset de avaliação (o LLM-judge tinha 16 % de viés medido), guarda robô×robô, encerramento por intenção, opt-out do disparador, tags do cliente.
- **Riscos honestos:** português **não é o idioma primário** ("funciona, mas exige teste antes de produção" — docs); sem número de latência publicado; leitura literal das instruções; não extrai, não conta, não compara datas (nome/CPF/data continuam no regex); conteúdo adversarial pode deslocar respostas (regex fica na frente); mensagens de clientes de um hospital vão a um terceiro (LGPD — hoje já vão ao OpenRouter, mas é decisão do dono); SDK novo (0.7.x). Custo do Jev é irrelevante (≈ US$ 1/mês mesmo se todas as 35 mil mensagens do HPM passassem); o custo é engenharia + validação.
- **Recomendação:** **spike de 1–2 dias, sem tocar produção**, com dois conjuntos que já temos: (a) as primeiras mensagens dos 850 atendimentos dos últimos 90 dias contra a triagem que o LLM gravou (409 classificados) e (b) as 26 perguntas de escolha da HPM contra ~50 frases livres em pt-BR. Go/no-go por acerto, confiança e p95. Se passar, Fase 1 = **a camada `shared/decisao.py` como parte do núcleo**, servindo de uma vez o menu, o `ask_choice` e a triagem — **modo sombra em todas as empresas primeiro**, depois ligada como padrão.

---

## 1. O que o Jev é (fatos das docs)

### 1.1 Modelo e contrato

| Item | Fato |
|---|---|
| Endpoint | `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <TYPESAFE_API_KEY>` |
| Entrada | `state` (string, objeto JSON ou lista de textos — **sem imagem/áudio**), `model` (`jev-latest` = `jev-1.13.0`), `questions` (mapa id → pergunta) |
| `Choice` | `instructions` + `criteria` = mapa opção → descrição (string ou objeto `{"what": …, "not_for": …}`); devolve `choice`, `probabilities` por opção, `confidence` |
| `Score` | `instructions` + `criteria` = lista **ordenada** de 2–10 níveis; devolve `score` (pode cair entre níveis), `legend`, `probabilities`, `confidence` |
| `Noul` | `instructions` (+ `criteria {true, false}` opcional); devolve `noul` = P(sim). Perto de 0,5 = **incerto**, não "médio" |
| Confiança | Derivada do formato da distribuição (toda a massa numa opção = 1,0; espalhada = 0). Para 3 opções ≈ `(3·p_max − 1)/2`. **Não comparar limiares entre tipos de pergunta** |
| Paralelismo | Todas as perguntas de uma chamada avaliadas em paralelo, **independentes** (uma resposta não vira contexto da outra); "speculative fan-out": pergunte tudo que o código *pode* precisar |
| Limites | 64k tokens/req (32k para estado + maior pergunta); 250 mil tokens/s; 1.200 req/min |
| Preço | **US$ 0,042 / M tokens de entrada; saída grátis** |
| Idioma | "English is primary; other languages … supported but less accurate. **Portuguese … work but require testing before production use**" |
| Latência | **Não publicada** nas docs. O post da LangChain fala em "até 200× mais rápido e 400× mais barato que LLMs comparáveis em classificação" — afirmação do fornecedor, a medir |
| Dados | Não treina com dados do cliente; "zero data retention available for enterprise" |
| SDK | `typesafe-sdk` 0.7.1 (21/09/2026, Python ≥ 3.10), `TypeSafeClient`/`AsyncTypeSafeClient.system_one(state=, questions=)`, `RetryPolicy` com backoff; erros 401/422/429/529 |
| LangChain | `langchain-typesafe`: `TypeSafeClassifier` (state aceita mensagens LangChain), `ModelRouterMiddleware` e `AutoModeMiddleware` (**experimental**) para `create_agent(middleware=[…])` — o mesmo `create_agent` do nosso `agents/middleware/` |

Resposta de exemplo (quickstart, verbatim):

```json
{"model":"jev-1.13.0","answers":{
  "department":{"type":"choice","choice":"technical","confidence":0.78,
                "probabilities":{"technical":0.85,"sales":0.0,"billing":0.15}},
  "frustration":{"type":"score","score":1.0,"confidence":1.0,
                 "legend":{"0":"Calm…","1":"Frustrated but civil","2":"Very angry…"},
                 "probabilities":{"0":0.0,"1":1.0,"2":0.0}},
  "is_urgent":{"type":"noul","noul":1.0}},
 "usage":{"input_tokens":392,"output_tokens":65}}
```

### 1.2 Filosofia (a que interessa ao pedido de "determinístico")

Da página *How to build with System One*: "**keep code in control and give System One narrow, structured decisions**". Três teses: fluxo e regra de negócio ficam no código; julgamentos amplos viram perguntas atômicas com critérios explícitos; o modelo recebe **só** o contexto que a pergunta precisa. É o oposto do agente autônomo: o modelo interpreta dado não estruturado, o código orquestra.

Padrões documentados que batem com o Nexus: **intent routing** (Choice de intenção + Score de complexidade → código deterministico / LLM especialista / humano; confiança < 0,5 → humano), **confidence-gated routing** ("a resposta diz *o quê*; a confiança diz *se* deve agir" — piso 0,6 para tudo, > 0,85 para ação com consequência, entre os dois pede confirmação), **composite scoring**, **guardrails** (4 Nouls de risco + 1 Score de severidade por mensagem, limiares 0,35 revisão / 0,70 ação), **function calling** (argumentos de conjunto fechado como Choice/Noul; confiança do conjunto = a **menor** das decisões), **skill suggestion** (catálogo de 182 opções numa Choice só, depois re-rank dos 3 melhores; descrições ~60 caracteres na 1ª passada).

### 1.3 Arestas conhecidas do jev-1.13 (página *jaggedness*, o que nos afeta)

- **Leitura literal**: negações, escopo e condições implícitas são lidos ao pé da letra → instruções diretas, sem dupla negação, uma pergunta por julgamento.
- **Não é calculadora**: contar, comparar números, hex/binário → no código. **Datas são texto**, não ordem → extrair partes como Choice e fazer a aritmética no código. Para nós: CPF, data, telefone, e-mail **continuam nos validadores regex** (`workflows/validators.py`).
- **Estado grande e irrelevante degrada** ("context rot") → mandar só as últimas mensagens e as opções, não a conversa inteira.
- **Conteúdo adversarial** pode deslocar respostas → o `input_filter` regex fica **na frente**, o Jev atrás (defesa em profundidade).
- **Não gera texto**: extração é com regex/LLM; o Jev só classifica.
- **Sem invariantes estruturais**: `P(noul)` e `1 − P(não noul)` não são comparáveis; limiares são por pergunta.

---

## 2. Onde o Nexus decide hoje — mapa por ponto

| Ponto | Como decide hoje | Limitação | Primitiva Jev | Volume (prod, 90 d) |
|---|---|---|---|---|
| **Menu** `_try_handle_menu` | `parse_numero_opcao` (regex 1–2 dígitos) ou `trigger_keyword`; resto = "Opção inválida" + reenvia o menu | Cliente que escreve "quero marcar consulta" cai em inválido | `Choice` sobre as opções do nível + Nouls "quer humano" / "quer sair" | **0** (nenhum menu ativo) |
| **Workflow** `ask_choice` | `_match_choice` = valor exato, case-insensitive | Idem; 26 nós na HPM, um com 43 opções | `Choice` no `runner` antes do `Command(resume=…)` — o interrupt já carrega `choices: [{label, value}]` | **0** (9 workflows inativos) |
| **Workflow** `branch` | `vars.x == 'y'` / `!=` / `contains` (regex restrita, sem interpretador) | Só compara o que um `ask_*` gravou | Nó novo `classify` grava `vars.<id>` (rótulo) + `vars.<id>_confianca` (faixa `alta/media/baixa`) — o `branch` atual já lê | — |
| **Workflow** `ask_text` | `validate_with` cpf/cnpj/cep/data_br/email/min_len/regex | Não julga conteúdo ("é um motivo de consulta?") | `Noul` como validador semântico opcional; **nunca** para CPF/data (aresta do modelo) | — |
| **Triagem** | O LLM chama `classificar_atendimento(prioridade, sentimento, classificacao)` quando lembra | **409 de 850** atendimentos classificados (48 %) | 1 chamada por primeira mensagem: `Choice` categoria, `Score` prioridade, `Score` sentimento, `Noul` urgente | 850 atendimentos |
| **Transferência** | `transfer_to_human` → só `agente_ia.departamento_default_id` | Empresa com N departamentos não roteia por assunto | `Choice` departamento com confiança; baixa → fila geral / pergunta | 406 transferências |
| **Guardrail de entrada** | 14 regex (jailbreak EN/PT, extração de prompt, desconto, admin, injeção) | Só pega o que a regex prevê; sem severidade | 4–6 `Noul` + 1 `Score` severidade (cookbook *llm_guardrails*), atrás da regex | toda mensagem |
| **Guardrail de saída** | Juiz `gpt-4o-mini` SAFE/UNSAFE só quando há fato verificável (regex de número/preço/data) + cache 1 h + pula se RAG ≥ 0,5 | Chamada de chat (latência de geração), 1 bit de resposta | `Noul` "a resposta afirma fato que não está no contexto" + `Noul` "promete transferir sem transferir"; ou cookbook *citation_check* | por resposta com fato |
| **Router multi-agente** `atendimento_router` | `ROUTER_PROMPT` (LLM) devolve lista de domínios `midia/crm/calendar/conhecimento` | Chamada de LLM só para rotear | 4 `Noul` (um por domínio) numa chamada — substituição direta | template opcional |
| **Guarda robô×robô** (WIP `feat/guarda-conversa-automatica`) | Sinal `menu` por regex de vocabulário de URA + timing | Vocabulário fixo | `Noul` "mensagem gerada por sistema automático" como 3º sinal, só no empate | — |
| **CSAT** | `parse_nota` 0–10; comentário = texto livre em 60 s | "foi ótimo" não vira nota; comentário não é classificado | `Score` sentimento do comentário; `Noul` "menciona atendente" / "reclama de demora" | — |
| **Encerrar** | 4 strings fixas (`encerrar`, `finalizar`…) | "era só isso, obrigado" não fecha | `Noul` "cliente encerrou a conversa" ≥ 0,9 → fecha; faixa média → pergunta | — |
| **Roteamento de modelo** | Modelo fixo por agente (ADR-004) | Turno trivial paga o modelo caro | `ModelRouterMiddleware` (barato × forte por turno) | todo turno de IA |
| **Ações do agente** | Tools executam quando o LLM chama | `cancel_event`, `close_atendimento`, `update_cliente` sem segunda opinião | `AutoModeMiddleware` / `Noul` "o cliente pediu explicitamente esta ação" antes de executar | — |

Os dois primeiros pontos são o pedido do dono; a seção 4 cobre os demais.

---

## 3. Desenho: "menu que entende" e "workflow que entende", sem perder o determinismo

### 3.1 Princípio

O que torna o menu/workflow "determinístico" não é a ausência de modelo, é: (a) **conjunto fechado de saídas** — cada nível tem N opções, o resultado é uma delas ou "nenhuma"; (b) **política no código** — o que acontece em cada faixa de confiança é uma regra, não um julgamento; (c) **auditável** — cada interpretação fica registrada com as probabilidades. O Jev preserva os três: uma `Choice` sobre as opções do nível **só pode responder uma das opções ou `nenhuma`**, e o código decide navegar / confirmar / reenviar. O modelo em si não é determinístico (é um modelo), mas a **decisão** é tipada e o **fluxo** é o mesmo de hoje — abaixo do limiar, é literalmente o código atual.

### 3.2 Interpretador de opção (uma função, dois clientes)

```python
# shared/decisao.py — contrato; implementação Jev + implementação "LLM estruturado"
# (OpenRouter com JSON schema) para A/B no spike e para desligar sem refazer.
class Interpretacao(NamedTuple):
    opcao: str | None          # value/ordem da opção, ou None
    confianca: float           # 0–1
    probabilidades: dict[str, float]
    quer_humano: float         # Noul
    quer_sair: float           # Noul
    origem: str                # "numero" | "keyword" | "jev" | "nenhuma"

async def interpretar_opcao(texto, opcoes: list[Opcao], contexto: Contexto) -> Interpretacao
```

Ordem dentro de `interpretar_opcao`: **1)** número exato (regex atual) → **2)** `trigger_keyword` → **3)** uma chamada ao Jev (speculative fan-out, tudo junto):

```python
state = {
  "mensagem_do_cliente": texto,                      # PII redigida (redact_pii) antes
  "menu": {"pergunta": prompt, "opcoes": [{"n": "1", "rotulo": "Agendamentos",
            "cobre": "marcar, remarcar, cancelar consulta ou exame"}, …]},
  "ultimas_mensagens": [...]                         # no máximo 3, só texto
}
questions = {
  "opcao": Choice(instructions="Qual opção do menu o cliente está pedindo? Se a mensagem "
                               "não corresponde a nenhuma, responda 'nenhuma'.",
                  criteria={**{o.n: {"what": o.rotulo, "cobre": o.cobre} for o in opcoes},
                            "nenhuma": "Não é uma escolha de opção (saudação, outra coisa, dúvida)"}),
  "quer_humano": Noul(instructions="O cliente pede para falar com uma pessoa/atendente?"),
  "quer_sair":   Noul(instructions="O cliente quer encerrar ou sair do menu?"),
}
```

Política (constantes com nome, calibradas no spike; a doc manda "começar conservador e ajustar com os próprios dados"):

| Resultado | Ação | Texto ao cliente |
|---|---|---|
| `opcao ≠ nenhuma` e `confianca ≥ 0,75` | Navega como se tivesse digitado o número; `registrar_historico(resposta=texto)` + detalhe `{interpretado_por: "jev", prob: …}` | o mesmo de quem digitou o número |
| `0,50 ≤ confianca < 0,75` | **Confirmação** (opcional por menu): "Você quer *2. Exames*? Responda 1 para sim ou escolha outra opção" | uma mensagem a mais, sem termo técnico |
| `quer_humano ≥ 0,85` e o menu tem item de transferência | Vai ao item de transferência | idem |
| resto | **Comportamento atual**: "Opção inválida" + menu | inalterado |

Estado enviado é pequeno de propósito (aresta "context rot"): a mensagem, o nível do menu e no máximo 3 mensagens anteriores. Um menu de 43 opções × ~12 tokens + mensagem + perguntas ≈ 700 tokens → **US$ 0,00003 por chamada**; se **todas** as 35 mil mensagens/mês do HPM passassem, ≈ US$ 1/mês.

Onde cada cliente chama:
- **Menu** (`_try_handle_menu`): no lugar de `numero = parse_numero_opcao(text)` → `interp = await interpretar_opcao(text, children, …)`; `numero = int(interp.opcao)` quando houver. O resto do bloco (submenu, chamar_agente, transferir, coleta) **não muda**.
- **Workflow** (`WorkflowRunner._process_inner`): quando `has_state`, o interrupt pendente está em `state_snapshot.tasks[*].interrupts[*].value` e já traz `{"kind": "ask_choice", "choices": [{label, value}]}`. Se `msg` não bate em `value`, `interpretar_opcao` traduz e o resume vira `Command(resume=value)`. **Nenhum nó muda**, o `_match_choice` continua exato. Os nós são síncronos (`def node` com `interrupt()`), então é no runner mesmo que a chamada assíncrona cabe.

Configuração (padrão do repo: **config, não remoção**) — e, por ser padrão do Nexus, **o interruptor é de desligar**: `menu_chatbot.somente_numero` e `empresa.decisao_texto_livre` nascem permitindo a interpretação (a empresa que quer a URA rígida desliga), mais `menu_chatbot.confirmar_quando_incerto`. Três estados por ponto de decisão, governados por `settings.typesafe_modo` (`off` | `sombra` | `ativo`): **sombra** registra o que o Jev *teria* feito (`workflow_evento` `evento='interpretacao_sombra'` / detalhe no `atendimento_menu_historico`) e o cliente vê exatamente o comportamento de hoje; **ativo** passa a agir. Mesma disciplina do `guardrail_output_unsafe_shadow_only`. Nenhuma empresa passa de `sombra` para `ativo` sem número medido.

### 3.3 Nó `classify` no workflow (opcional, depois do interpretador)

```json
{"type": "classify", "questions": {
   "intencao": {"type": "choice", "instructions": "O que o cliente quer?",
                "criteria": {"agendar": "…", "resultado_exame": "…", "outro": "…"}},
   "urgente": {"type": "noul", "instructions": "Há sinal de urgência médica?"}},
 "next": "roteia"}
{"type": "branch", "when": [
   {"condition": "vars.intencao == 'agendar'", "next": "agendamentos"},
   {"condition": "vars.urgente_faixa == 'alta'", "next": "handover_urgente"}],
 "else": "menu_principal"}
```

Grava `vars.intencao`, `vars.intencao_confianca_faixa` (`alta|media|baixa`) e `vars.urgente_faixa` como **strings**, para o `_check_condition` atual (regex `==`/`!=`/`contains`) servir sem mexer no interpretador restrito — que é uma decisão de segurança do motor. `ask_text` ganharia `validate_with: "noul:<pergunta>"` só para validação **semântica** ("a resposta descreve um sintoma?"); CPF/data/e-mail ficam nos validadores locais.

### 3.4 Onde isso se encaixa no roadmap

**É camada de plataforma, não feature de canal.** `shared/decisao.py` fica ao lado de `shared/llm.py`: uma dependência que o worker e a API usam, com `Protocol` e implementação trocável, telemetria própria e disjuntor. Quem chama é o ponto de decisão (menu, `ask_choice`, triagem, guardrail, transferência), não o canal — a mensagem chega igual do Evolution, do WABA ou do Canal por API, e o ponto de decisão é o mesmo código.

Consequências de tratar como padrão:

- **Liga para todos, desliga por exceção.** O interruptor é de **desligar** (`menu_chatbot.interpretar_texto_livre` default **TRUE**, `somente_numero` para quem quiser a URA rígida), ao contrário do `enable_workflow_engine` (opt-in). A migração de estreia liga em todas as empresas depois da validação em sombra.
- **Cobrança: proponho NÃO gatear por plano.** A ADR-005 manda gatear recurso que custa LLM por mensagem — mas aqui o custo medido é **≈ US$ 1/mês para 35 mil mensagens**, ordens de grandeza abaixo de transcrição, visão ou voz. Gatear transformaria o comportamento básico ("o menu entende quem escreve em vez de digitar 3") em item de upgrade, e o Free é exatamente quem mais erra opção. Recomendo **base em todos os planos**, com o teto vindo do teto de IA da empresa (`ia_budget`), como qualquer outro consumo. Decisão do dono (§7).
- **Um só lugar para medir e desligar.** `settings.typesafe_enabled` (global), disjuntor por erro/latência e um painel único com acerto, distribuição de confiança e taxa de sombra × real — se o fornecedor cair ou o pt-BR decepcionar, o Nexus volta ao comportamento de hoje sem tocar em menu, workflow ou agente.

**O HPM/ZigChat é o campo de prova, não o escopo.** Ele entra porque dá volume e **verdade de campo de graça**: o `departamento_id` real do `GET /atendimento/listar` e a opção que o cliente de fato escolheu permitem medir "o que o Jev teria decidido na 1ª frase" contra "onde o atendimento terminou", sem rotular nada à mão. A mesma camada já estará valendo para Luis, VSA e qualquer cliente novo.

---

## 4. Outras frentes (pedido adicional) — ordem por valor ÷ esforço

### 4.1 Triagem determinística (maior valor, esforço baixo)
Hoje a triagem é uma **tool que o LLM chama se quiser**: 409 de 850 atendimentos (48 %) saem com `classificacao`; a faixa de triagem, os chips da fila e o agrupamento dependem disso. Proposta: no worker, **na primeira mensagem** do atendimento (e opcionalmente a cada N turnos), uma chamada Jev com `Choice` categoria (o vocabulário da empresa: `_ROTULO`-like, cadastrável), `Score` prioridade (baixa/média/alta/urgente com descrições), `Score` sentimento (positivo/neutro/negativo/frustrado), `Noul` "quer humano", `Noul` "urgência". Grava via `set_classificacao` só quando `confidence ≥ limiar`; abaixo, deixa como está (o LLM ainda pode classificar). Efeito colateral bom: **remove do prompt do agente a obrigação de classificar** (menos tokens fixos; ver gotcha do cache de prompt). Onde: `worker/processor.py` logo após os gates (modo manual/whitelist/plano), antes do agente — mesmo lugar da transcrição do operador.

### 4.2 Guardrails de entrada e saída (valor alto, esforço médio)
Entrada: manter as 14 regex como 1ª camada (custo zero, cobre o adversarial que o Jev admite não resistir), e atrás uma chamada Jev com `Noul` jailbreak, `Noul` extração de prompt, `Noul` pede dado sensível de terceiro, `Noul` pede desconto/condição indevida, `Noul` **conteúdo médico/dosagem** e `Noul` **risco de autoagressão** (HPM é hospital — o cookbook tem exatamente esse caminho "support"), `Score` severidade 0–3. Política do cookbook: ≥ 0,35 revisão (marca na timeline, não bloqueia), ≥ 0,70 ação (bloqueia/transfere), severidade ≥ 2 promove revisão a bloqueio. Registrar em `guardrail_log` como hoje, **sombra primeiro**.
Saída: `Noul` "a resposta afirma preço/prazo/política que não está no contexto fornecido" com o estado = `{resposta, trechos_da_base, historico_curto}` substitui o juiz `gpt-4o-mini` (chat de geração, US$ 0,15/M entrada + saída, latência de completion) por uma chamada de US$ 0,042/M e sem geração; mais `Noul` "promete transferência" (o `_TRANSFER_RE` atual) e `Noul` "responde em outro idioma/tom". O `should_judge` (só quando há fato verificável + cache + RAG ≥ 0,5) continua valendo.

### 4.3 Roteamento por departamento/agente (valor alto para o HPM, esforço médio)
`transfer_to_human` só conhece `agente_ia.departamento_default_id`. Para empresa com N departamentos (HPM: Atendimento, Agendamentos, Exames, Tesouraria, Orçamentos, Portaria, Ouvidoria…), `Choice` departamento com descrições `{"what", "not_for"}` na primeira mensagem; ≥ 0,85 roteia direto, 0,6–0,85 pergunta ("É sobre *Exames*?"), < 0,6 fila geral. Reusa a `Interpretacao` da 3.2. É o "routing departamento → agente" que o desenho do Canal por API já prevê — o Jev é o motor natural dele.

### 4.4 Trava de confiança em ações irreversíveis do agente (valor alto, esforço baixo)
`AutoModeMiddleware` (ou um `before_tool` nosso com `Noul`): antes de `close_atendimento`, `transfer_to_human`, `cancel_event`, `update_cliente`, `add_cliente_tag`, perguntar "o cliente pediu explicitamente esta ação nas últimas mensagens?" com estado = últimas 3 mensagens + a chamada de tool. Abaixo do limiar, a tool devolve ao agente "confirme com o cliente antes" em vez de executar. Cobre o padrão do incidente "IA fechou/transferiu sem o cliente pedir".

### 4.5 Router multi-agente (`atendimento_router`) (valor médio, esforço baixo)
O `ROUTER_PROMPT` gasta uma chamada de LLM para devolver uma lista de domínios. Quatro `Noul` (midia/crm/calendar/conhecimento) numa chamada Jev, limiar 0,5, "lista vazia" quando nenhum passa — substituição direta, mais barata e sem parsing de saída.

### 4.6 Roteamento de modelo por turno (valor médio, esforço baixo, depende de política)
`ModelRouterMiddleware` (experimental): `Choice` "menor modelo que resolve este turno" entre o modelo do agente e um barato (ex.: flash-lite) — saudação/confirmação/pergunta simples vai ao barato. Medido: IA custa US$ 0,0113/atendimento; a fração de turnos triviais é alta em WhatsApp. Precisa de política: respeitar o tier/plano da ADR-004 (o barato nunca sobe de plano; só desce), registrar em `ia_execucao` qual modelo respondeu.

### 4.7 Frentes menores (baixo esforço cada, valor pontual)
- **RAG**: cookbook *classifying_rag_passages* — `Score` relevância por trecho da base numa chamada, e só os ≥ limiar entram no prompt (menos tokens, resposta mais ancorada; `RAG_SCORE_THRESHOLD` já existe como conceito). *Citation check* para "a resposta é sustentada pelo trecho X".
- **Dataset e avaliação** (`docs/LANGSMITH.md`, dataset do Luis): o LLM-as-judge mediu **16 % de viés**; `Score` de qualidade calibrado como juiz alternativo/ensemble ("ensemble labeling" da doc) para rotular traces e selecionar `fewshot_example`.
- **Guarda robô×robô**: `Noul` "mensagem gerada por sistema automático (URA, menu, robô)" como 3º sinal só quando os dois sinais atuais empatam — mantém a regex de custo zero.
- **Encerrar por intenção**: `Noul` "cliente encerrou" ≥ 0,9 fecha (dispara CSAT como hoje); 0,6–0,9 pergunta "Posso encerrar?". Substitui o conjunto de 4 strings.
- **CSAT**: `Score` sentimento do comentário livre e `Noul` "reclama de demora" / "elogia atendente" → ranking de operadores ganha texto classificado, não só a nota.
- **Tags do cliente**: `Choice` sobre as tags existentes da empresa (o gotcha "cliente_tag é texto livre") — sugestão no painel, não automática.
- **Disparador** (engavetado, mas barato): `Noul` "pede para não receber mais mensagens" além do STOP literal — o opt-out por palavra exata é frágil e a Meta pontua qualidade a partir de 1º/10.
- **Monitor/saúde**: **não** — as decisões ali são de código sobre sinais numéricos; o Jev não acrescenta nada.

---

## 5. Riscos, limites e como mitigar

| Risco | Mitigação |
|---|---|
| **Português não é o idioma primário** do jev-1.13 | O spike mede em pt-BR com mensagens reais (gírias, transcrição de áudio, erro de digitação). Sem número ≥ 90 % de acerto no menu, não avança |
| Latência não publicada; dependência externa no caminho crítico do worker | Timeout curto (2 s), 1 tentativa, **fallback = comportamento atual** (menu inválido / sem triagem / juiz atual); disjuntor igual ao `WORKER_HEALTH`; nunca segura a fila |
| LGPD — mensagens de pacientes a um terceiro | Hoje já vão ao OpenRouter (mesma classe). Mesmo assim: `redact_pii` **antes** de montar o estado (CPF/telefone/e-mail já são mascarados), só as últimas 3 mensagens, e DPA / zero-retention com a TypeSafe antes do HPM em produção — decisão do dono |
| Leitura literal / adversarial / não extrai | Instruções diretas, uma pergunta por julgamento, opção `nenhuma` sempre; regex de injeção na frente; extração (nome, CPF, data) continua onde está |
| Limiares errados | Constantes nomeadas por ponto (menu 0,75; departamento 0,85; encerrar 0,90; guardrail 0,35/0,70), calibradas no spike; **modo sombra** antes de agir; painel mostra a distribuição |
| SDK 0.7.x, modelo 1.13, fornecedor novo | `shared/decisao.py` com `Protocol` e duas implementações (Jev e "LLM estruturado" via OpenRouter JSON schema) — dá para comparar no spike e desligar por env sem refazer o menu |
| Teto de 1.200 req/min por chave | HPM ≈ 1,2 msg/min em média; pico medido do worker 89 msg/min/réplica → folga; `RetryPolicy` do SDK trata 429/529 |
| Custo | Irrelevante (≈ US$ 1/mês no HPM inteiro); o custo é engenharia + validação |

---

## 6. Plano proposto (nenhum passo executado)

**Fase 0 — spike (1–2 dias, sem tocar produção, código descartável).** Conta em `console.typesafe.ai/keys`, `TYPESAFE_API_KEY` em `~/.secrets`. Script `scripts/spike_jev.py`:
1. **Triagem**: primeiras mensagens dos 850 atendimentos dos últimos 90 dias (PII redigida, lidas do dump do dev), Jev responde categoria/prioridade/sentimento; compara com os 409 que o LLM gravou (concordância, confiança média, onde diverge e quem tem razão em 30 amostras lidas à mão).
2. **Menu HPM**: as 26 `ask_choice` do `scripts/import_workflow_mackenzie.py`; ~50 frases livres em pt-BR (metade escritas, metade da amostra de conversas do HPM que já temos no `tools/relatorios-hpm/`, sem a chave), incluindo 10 "nenhuma" e 10 ambíguas; mede acerto, confiança na resposta certa vs. errada (a separação é o que importa), p50/p95 de latência, tokens/custo.
3. **Idioma**: as mesmas 50 frases traduzidas para inglês como controle — quantifica a perda em pt-BR.
4. Go/no-go: acerto ≥ 90 % com confiança ≥ 0,75 nas certas e < 0,75 na maioria das erradas; p95 < 1,5 s. Relatório em `.planning/reports/`.

**Fase 1 — a camada, como núcleo (não como feature de canal)**: `shared/decisao.py` (Protocol + implementação Jev + implementação "LLM estruturado" de reserva), `settings.typesafe_modo`/`typesafe_timeout`, disjuntor e telemetria (`decisao_log`: ponto, pergunta, resposta, confiança, latência, sombra/ativo). Três consumidores na MESMA entrega, todos em **sombra para todas as empresas**: menu (`_try_handle_menu`), `ask_choice` (`WorkflowRunner`) e **triagem** (o ponto que tem volume hoje). Migração com `menu_chatbot.somente_numero`/`confirmar_quando_incerto` + `empresa.decisao_texto_livre`. E2E no molde `test_aba_endpoints.py`.

**Fase 2 — ligar como padrão**, ponto a ponto, lendo o `decisao_log` da sombra: primeiro a triagem (compara com os 409 que o LLM classificou), depois menu/`ask_choice`. Painel de acerto e distribuição de confiança em `/monitor`. A partir daqui, empresa nova nasce com a camada ligada.

**Fase 3 — guardrails Jev em sombra → ativo** (`guardrail_log` já existe) e **departamento por intenção** no `transfer_to_human` (vale para todos os canais; o HPM, quando entrar, dá a verdade de campo do `departamento_id` real do ZigChat para calibrar).

**Fase 4 (opcional)** — `AutoModeMiddleware` nas tools irreversíveis, router multi-agente, roteamento de modelo, RAG.

## 7. Decisões do dono antes de qualquer código

1. **Autoriza o spike** (conta, chave, poucos dólares)?
2. **LGPD/HPM**: mensagens de pacientes podem ir à TypeSafe (mesma classe do OpenRouter, mas fornecedor novo; zero-retention é "enterprise")? Se não, o spike usa só dados da VSA/1018 + frases sintéticas.
3. **Confirmação em confiança média** ("Você quer *2. Exames*?") é aceitável ou o menu só navega/reenvia?
4. **Cobrança**: por ser padrão do Nexus e custar ≈ US$ 1/mês em 35 mil mensagens, proponho **não** criar feature de plano — entra como comportamento base em todos os planos, com o consumo caindo no teto de IA da empresa. Confirma, ou quer o gate no padrão da ADR-005?
5. **Ordem**: spike agora (1–2 dias) → Fase 1 (camada + menu + `ask_choice` + triagem em sombra) → ligar como padrão. O Canal por API/HPM segue no seu próprio trilho e **consome** a camada quando chegar, em vez de ser dono dela.
