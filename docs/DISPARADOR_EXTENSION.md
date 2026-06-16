# Disparador — guia de integração da extensão Chrome

A extensão Chrome captura contatos/grupos do WhatsApp Web do usuário e os envia
ao ChatNexus. Ela **só** conhece a API key da empresa e os endpoints
`/api/captura/*` (escopo `capture`) — nunca o `INTERNAL_SERVICE_TOKEN`.

> A extensão em si (código MV3) é um artefato separado, em quarentena (fora do
> `make ci`, distribuída como zip standalone, **nunca** proxiada por
> `/uploads/*`). Este guia define o **contrato** que ela consome.

## 1. Obter a API key

No painel: **Disparador → API keys → Nova chave**. O segredo
(`nxs_<empresa_id>_<32hex>`) é exibido **uma única vez** — copie e cole nas
opções da extensão. Guardamos só o hash; se perder, gere outra e revogue a antiga.

## 2. Autenticação

Toda request usa:

```
Authorization: Bearer nxs_<empresa_id>_<32hex>
```

A empresa é resolvida pela própria chave (não precisa header de empresa). Valide
a conexão com:

```
GET /api/disparador/status
→ 200 { "ok": true, "empresa_id": 42, "scopes": ["capture"], "rate_limit_per_minute": 60 }
→ 401 se a chave for inválida/revogada/expirada
```

## 3. Enviar contatos/grupos capturados

A estratégia recomendada de captura é **hookar o store interno** do WhatsApp Web
(`window.Store.Contact`/`Chat`/`GroupMetadata` via moduleRaid) em vez de raspar
o DOM (classes CSS mudam toda semana). Isole todos os seletores/keys num único
arquivo versionado com self-test ("scrape health"). Aguarde `Store.Chat`
hidratar antes da primeira leitura.

Envie em lotes (cap ~2000/request). Use `wa_jid` como identidade — telefone é
opcional (membros multi-device só têm `@lid`).

```
POST /api/captura/contatos
{ "contatos": [
    { "wa_jid": "5511999999999@s.whatsapp.net", "push_name": "João",
      "is_business": false },
    { "wa_jid": "1234567890@lid", "push_name": "Maria" }
] }

POST /api/captura/grupos
{ "grupos": [ { "wa_group_id": "12036…@g.us", "nome": "Clientes VIP" } ] }

POST /api/captura/grupos/{wa_group_id}/membros
{ "membros": [ { "wa_jid": "5511…@s.whatsapp.net", "is_admin": false } ] }
```

> Nota de implementação: os endpoints `/api/captura/*` consomem
> `verify_api_key`/`require_scope("capture")` e a camada `shared/captura.py`
> (upsert idempotente por `wa_jid`, auditoria em `captura_lote`). A captura
> server-side equivalente (sem extensão) é
> `POST /api/conexoes/{id}/captura/{contatos|grupos}` no painel.

## 4. Fluxo no painel após captura

1. **Disparador → Contatos**: navega o staging, "Promover p/ CRM" (vira `cliente`).
2. **Campanhas → Nova**: escolhe origem (`grupos`/`contatos`/`janela_24h`),
   clica **Preparar** (`POST /api/disparador/preview` → contagem +
   válidos/inválidos/opt-out/duplicados), depois **ENVIAR**.

## 5. Risco de ToS / banimento (leia)

Capturar e disparar a partir de uma sessão pessoal do WhatsApp Web viola os
Termos do WhatsApp e pode **banir o número**. Mitigações do produto:

- intervalo **aleatório** entre envios (jitter), validação de números, opt-out,
  kill-switch, caps conservadores;
- preferir o **canal oficial (WABA)** para volume.

Não há volume "seguro" garantido. O uso é responsabilidade do operador
(consentimento/LGPD). A 1ª campanha por conexão Evolution deve exigir aceite
explícito desse risco.

## 6. Erros comuns

| Código | Causa | Ação |
|--------|-------|------|
| 401 | chave ausente/inválida/revogada/expirada | gerar nova no painel |
| 403 | chave sem escopo (`capture`) | criar chave com o escopo certo |
| 429 | rate-limit por chave estourado | espaçar requests / aumentar limite |
| 400/422 | payload malformado (faltou `wa_jid`) | validar shape antes de enviar |
