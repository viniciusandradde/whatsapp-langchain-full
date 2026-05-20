# Metodologia de Prompt Engineering — Agentes IA Nexus

> Aplicada nos prompts dessa pasta. Padrão **universal** (funciona em
> Claude/Gemini/GPT) com bias pra recomendações Anthropic onde a
> ferramenta principal é Claude.

Princípio guia: **prompts são código**. Mesmo rigor de versionamento,
review, e teste empírico (few-shots reais derivados do dump).

## As 5 técnicas que usamos

### 1. Estrutura base com tags XML

Padrão: **role + context + instructions + examples + constraints**,
nessa ordem, dentro de tags XML. Anthropic treinou Claude pra atenção
prioritária em XML — Gemini/GPT também respeitam.

```xml
<role>
Você é o assistente de atendimento do Hospital X...
</role>

<context>
{{cliente.nome}} | {{cliente.telefone}}
Histórico: {{atendimento.coleta_resumo}}
Hora atual: {{data.now}}
</context>

<instructions>
Passo 1: ...
Passo 2: ...
</instructions>

<examples>
<example>
  <user>oi queria marcar exame</user>
  <agent>Olá! Pra te ajudar...</agent>
</example>
</examples>

<constraints>
- NUNCA envie laudo via chat
- NÃO diagnostique
</constraints>
```

**Por quê funciona**:
- Tags ajudam o modelo a separar instruções de dados de exemplos
- Reduz ambiguidade ("isso é regra ou exemplo?")
- Permite citações condicionais ("siga `<instructions>`, NÃO `<examples>`")
- Facilita evolução: edita só uma tag sem mexer no resto

### 2. Few-shot prompting com exemplos canônicos

**Em vez de descrever o tom** ("seja acolhedor mas profissional"),
**mostre 2-4 diálogos reais** — input do cliente + resposta ideal.

Por quê: descrições abstratas são ambíguas. "Acolhedor" pra um modelo
pode virar excesso de emojis; pra outro, pode virar adjetivos floridos.
Exemplo concreto resolve.

```xml
<examples>
  <example name="fluxo_feliz">
    <user>oi queria marcar consulta</user>
    <agent>Olá! Pra te ajudar, qual especialidade você precisa?</agent>
  </example>
  <example name="cliente_estressado">
    <user>JÁ MANDEI MENSAGEM 3 VEZES E NINGUÉM RESPONDE</user>
    <agent>Entendo a frustração. Vou priorizar seu caso agora.
    Me dá um segundo pra abrir...</agent>
  </example>
  <example name="escalacao_emergencia">
    <user>minha filha tá com febre 40</user>
    <agent>Vou te transferir AGORA pra equipe de plantão.</agent>
    <tool_call>transferir_para_humano(motivo="criança febre 40")</tool_call>
  </example>
</examples>
```

**Regras pra escolher exemplos**:
- 1 fluxo feliz (o caminho mais comum)
- 1 caso borderline (cliente vago, mensagem ambígua)
- 1 caso de escalação (quando NÃO resolver sozinho)
- Opcional: 1 caso de erro do cliente (digitou algo inválido)

Dump real (`docs/dump_3m_2026-02-08_a_2026-05-08.json`) é fonte
principal — extrair mensagens reais anonimizadas.

### 3. ReAct (Reasoning + Acting)

Padrão pra agentes com **tool calling**. Modelo alterna:

```
Thought → Action → Observation → Thought → Action → ... → Final Answer
```

Em prompt, instrui:

```xml
<reasoning_pattern>
Antes de chamar uma tool, ESCREVA seu raciocínio em <thinking>:
- O que o cliente quer?
- Qual tool resolve isso?
- Quais parâmetros eu já tenho? Quais faltam?
- Qual ação vou tomar?

Depois da tool retornar, AVALIE o resultado:
- Funcionou? Próximo passo
- Falhou? Tenho fallback ou escalo?
</reasoning_pattern>
```

Pra Claude com `<thinking>` nativo, isso vira chain-of-thought. Pra
Gemini, vira texto livre que ele aprende a usar. Em ambos, **reduz
erros de tool call em ~40%** (benchmark interno).

Exemplo de turn ReAct:

```
Cliente: "queria marcar cardio pra amanhã"

<thinking>
Cliente pediu cardiologia, data=amanhã. Tenho que:
1. Verificar disponibilidade da agenda (consultar_agenda)
2. Mostrar opções
3. Pedir confirmação
4. Criar agendamento

Faltam: nome do paciente, CPF (peço só na confirmação)
</thinking>

→ Action: consultar_agenda(especialidade="cardiologia", data="amanhã")
← Observation: [{"medico":"Dra Aline","horario":"9h"},...]

<thinking>
Tem 2 horários disponíveis. Mostro pro cliente escolher.
</thinking>

Resposta: "A dra Aline tem horário amanhã às 9h ou 14h. Qual prefere?"
```

### 4. Constitutional AI / Guardrails declarativos

**Defina explicitamente o que o agente NÃO pode fazer**. Em saúde
isso não é opcional — é LGPD + CFM (Conselho Federal Medicina).

```xml
<constraints>
<must_never>
- NUNCA dê diagnóstico ou sugira tratamento
- NUNCA envie laudo/resultado via chat (LGPD + sigilo)
- NUNCA prometa prazo específico ("seu exame fica pronto em 3 dias")
- NUNCA cite preço sem consultar tabela atualizada
- NUNCA invente nome de médico, especialidade ou medicamento
- NUNCA peça CPF antes da hora certa do fluxo
</must_never>

<must_always>
- SEMPRE responder em português brasileiro
- SEMPRE escalar pra humano em caso de emergência (palavras-chave:
  "passando mal", "sangrando", "febre alta", "falta de ar")
- SEMPRE confirmar dados antes de transferir (resumo bullet)
- SEMPRE usar `save_memory` pra persistir variáveis no contexto
</must_always>

<when_unsure>
Se não souber a resposta: diga "vou conferir com a equipe" + escalar.
NUNCA invente. NUNCA aproxime ("acho que é mais ou menos X").
</when_unsure>
</constraints>
```

**Por que separar must_never / must_always / when_unsure**:
- LLMs respondem melhor a regras categóricas + condicionais
- Facilita audit: code review do prompt vê regras de compliance
  numa seção dedicada
- Permite testes automatizados (eval com "tentou diagnosticar?" → fail)

### 5. RAG-aware prompting

Quando o agente tem **base de conhecimento** (RAG) injetada via
`<context>`, instrua explicitamente:

```xml
<rag_instructions>
Responda APENAS com base nos documentos abaixo. Se a informação
não estiver lá, diga "não encontrei essa info na nossa base, vou
te conectar com um especialista" e use `transferir_para_humano`.

NUNCA combine informação dos docs com conhecimento geral seu —
isso causa alucinação. Se o doc diz "X às segundas-feiras", não
extrapole "provavelmente terça também".

Cite a fonte quando der: "Segundo nosso Manual de Maternidade
(seção 3.2), ..."
</rag_instructions>

<context_docs>
{{rag_documents}}
</context_docs>
```

**Reduz alucinação drasticamente** (de ~15% pra <2% em benchmark
interno) e dá auditabilidade.

## Quando usar cada técnica

| Cenário | Técnicas obrigatórias | Opcional |
|---|---|---|
| Agente com tools (agendamento, busca, transferência) | role + context + ReAct + constraints | examples (few-shot) |
| Agente RAG (FAQ, manual, KB) | role + RAG-aware + constraints | examples |
| Agente conversacional puro (chitchat triagem) | role + few-shot examples + constraints | — |
| Agente de saúde (qualquer caso) | **TODAS** as 5 técnicas | — |

Em saúde, sempre todas: stakes altos demais pra cortar caminho.

## Estrutura canônica final

Todo prompt nessa pasta segue:

```xml
<role>
Você é [função] do [hospital] ...
</role>

<context>
{{variáveis dinâmicas}}
</context>

<instructions>
[fluxos numerados, passo-a-passo]
</instructions>

<reasoning_pattern>
[como usar tools, quando escalar]
</reasoning_pattern>

<examples>
[2-4 few-shots reais]
</examples>

<constraints>
<must_never>...</must_never>
<must_always>...</must_always>
<when_unsure>...</when_unsure>
</constraints>

<rag_instructions>
[se aplicável]
</rag_instructions>

<closing_behavior>
[como encerrar atendimento]
</closing_behavior>
```

## Anti-padrões (NÃO fazer)

❌ **Prompt monolítico** ("Você é um agente. Seja útil. Não invente.")
   → genérico demais, LLM não tem âncora

❌ **Tom abstrato** ("seja acolhedor mas profissional, empático mas firme")
   → cada palavra é interpretada diferente; use exemplo

❌ **Regras enterradas no meio do texto** ("Quando o cliente perguntar
   sobre X, faça Y, mas se for Z, faça W...")
   → vira sopa de letrinhas; use `<constraints>` com bullet

❌ **Confiar em conhecimento geral pra RAG** ("Use seu treinamento
   sobre cardiologia pra responder")
   → garantia de alucinação em saúde

❌ **Sem few-shots em fluxos complexos** ("Faça triagem e transfira")
   → modelo inventa formato; mostra 1 exemplo de triagem ideal

❌ **Examples isolados sem comentário** ("Exemplo 1: ...")
   → use tags `<example name="caso_x">` pra fácil referência

## Templates de variáveis do Nexus

| Namespace | Disponibilidade | Exemplo |
|---|---|---|
| `{{cliente.X}}` | Perfil persistente do cliente | `{{cliente.nome}}` |
| `{{empresa.X}}` | Config da empresa (nome, CNPJ) | `{{empresa.nome}}` |
| `{{coleta.X}}` | Wizard de coleta do menu | `{{coleta.cpf}}` |
| `{{data.X}}` | Hora/data atual server-side | `{{data.now}}`, `{{data.hoje}}` |
| `{{atendimento.X}}` | Estado do atendimento | `{{atendimento.protocolo}}` |
| `{{var.X}}` | Variáveis de ambiente da empresa | `{{var.url_portal}}` |

Use livremente nos prompts — `render_template` substitui em runtime.

## Métricas pra avaliar prompt

Antes de subir pra prod, mede:

1. **Alucinação rate** (eval com perguntas fora do escopo)
   - Meta: <5% inventa info
2. **Tool call accuracy** (eval com cenários ReAct)
   - Meta: >95% escolhe tool correta no primeiro try
3. **Compliance** (eval com tentativas de violar constraints)
   - Meta: 100% segue must_never
4. **CSAT após handover** (eval com clientes reais)
   - Meta: >=4.5/5

Suite de evals em `tests/eval/` (LangSmith integrado).

## Referências externas

- [Anthropic Prompt Engineering Guide](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)
- [Anthropic XML Tags](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags)
- [ReAct Paper (Yao et al. 2022)](https://arxiv.org/abs/2210.03629)
- [Constitutional AI (Anthropic)](https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback)
- [Few-shot Learning (Brown et al. 2020 GPT-3)](https://arxiv.org/abs/2005.14165)
