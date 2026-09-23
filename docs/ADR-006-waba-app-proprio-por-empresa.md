# ADR-006 — API oficial do WhatsApp com o App da Meta da própria empresa

- **Status:** PROPOSTA (23/09/2026), aguardando o dono.
- **Contexto de negócio:** o dono quer que cada empresa possa conectar o
  WhatsApp oficial **com o próprio App da Meta**, como no Chatwoot, além do
  caminho de Tech Provider (cadastro incorporado pelo App do ChatNexus).
- **Fontes oficiais** (consultadas em 23/09/2026):
  - Meta, [Webhooks — Getting Started](https://developers.facebook.com/docs/graph-api/webhooks/getting-started)
  - Meta, [WhatsApp webhooks — Overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview)
  - Meta, [Subscribed Apps API](https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-account/subscribed-apps-api)
  - Meta, [Webhook overrides](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/override/)
  - Meta, [Access tokens](https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens)
  - Meta, [Register a business phone number](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/registration)
  - Meta, [Onboard WhatsApp Business app users](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users)
  - Chatwoot, [WhatsApp channel — manual flow](https://www.chatwoot.com/hc/user-guide/articles/1756799850-how-to-setup-a-whats_app-channel-manual-flow)

## 1. O que a documentação estabelece

| Fato | Fonte | Consequência para o ChatNexus |
|---|---|---|
| O webhook é configurado **no App** (App Dashboard → WhatsApp → Configuration): URL de callback, verify token e campos assinados. | Webhooks overview | Cada App da Meta tem a própria URL e os próprios campos. Um App de cliente precisa apontar para uma URL do ChatNexus. |
| Toda notificação é assinada com **HMAC-SHA256 usando o App Secret do App** que recebe (`X-Hub-Signature-256: sha256=…`), e a Meta recomenda validar. | Webhooks getting started | Com App próprio, a assinatura vem com o segredo **do cliente**. O `/webhook/waba` de hoje confere só com o segredo do App do ChatNexus e recusaria essa mensagem. |
| `POST /{waba}/subscribed_apps` inscreve **o App dono do token** usado na chamada. | Subscribed Apps API | O token do cliente inscreve o App do cliente, e não o nosso. |
| Vários Apps podem estar inscritos na mesma WABA, e a Meta manda (e repete) o webhook para **todos**. | Webhooks overview ("retries to all apps that have subscribed") | O mesmo `wamid` pode chegar por dois caminhos. O livro de idempotência por wamid (mig 200) já cobre isso. |
| A Meta repete a entrega por até **7 dias**, e o conteúdo pode ter até **3 MB**. | Webhooks overview | A idempotência é obrigatória, e o proxy precisa aceitar corpo de 3 MB ou mais. |
| Empresa que usa o próprio App deve usar **token de usuário do sistema** (permanente). Tech Provider usa "Business Integration System User". | Access tokens | O formulário pede um token de usuário do sistema com validade "Nunca". |
| O registro do número exige **PIN de 6 dígitos**, e um novo registro exige o mesmo PIN. | Register a business phone number | O número conectado manualmente já está registrado: o ChatNexus **não** registra (evita gastar as 10 tentativas por 72 h). |
| O onboarding do app WhatsApp Business (Coexistência) é pelo **cadastro incorporado** e exige **Tech Provider/Solution Partner**. | Onboard WhatsApp Business app users | Com App próprio, a Coexistência depende do App do cliente ser Tech Provider. Na prática, App próprio = Cloud API. |
| O Chatwoot, na configuração manual, pede **número, ID do número, ID da conta e token**, e mostra uma **URL de webhook e um verify token por caixa** (`/webhooks/whatsapp/{phone_number}`). Não pede App Secret. | Chatwoot manual flow | Seguimos o mesmo modelo, com uma diferença de segurança: **pedimos o App Secret e validamos a assinatura**, como a Meta recomenda. |

## 2. Decisão proposta

Dois jeitos de conectar a API oficial, lado a lado:

| | App do ChatNexus (hoje) | App da própria empresa (novo) |
|---|---|---|
| Como conecta | Botão "Conectar com Meta" (cadastro incorporado) **ou** formulário manual | Formulário manual com "Usar o App da Meta da própria empresa" |
| Webhook | `POST /webhook/waba` (URL do nosso App) | `POST /webhook/waba/{phone_number_id}` (URL exclusiva da conexão) |
| Verify token | O global (`WABA_WEBHOOK_VERIFY_TOKEN`) | **Gerado por conexão** (coluna `conexao.webhook_verify_token`, que já existe) |
| Assinatura conferida com | `META_APP_SECRET` | **App Secret da empresa**, guardado cifrado nas credenciais |
| Coexistência | Sim (quando o App do ChatNexus for Tech Provider) | Só se o App do cliente for Tech Provider |

### Webhook exclusivo `/{phone_number_id}`
- **GET (handshake):** localiza a conexão ativa pelo `phone_number_id` do caminho e compara `hub.verify_token` com o token **daquela conexão** (comparação em tempo constante).
- **POST:**
  1. localiza a conexão e decifra o App Secret;
  2. valida `X-Hub-Signature-256` com esse segredo (sem segredo ou assinatura inválida → rejeita, como hoje);
  3. **todo item do payload tem de ser do mesmo `phone_number_id` do caminho**. O que for de outro número é descartado com log. Assim, o App de uma empresa não consegue injetar mensagem em outra;
  4. daí em diante, **o mesmo processamento** do `/webhook/waba` (mensagens, eco, histórico, contatos, status de modelos, idempotência por wamid). O corpo do POST atual vira uma função compartilhada, sem duplicar código.
- `account_update` chega sem `phone_number_id` (só `entry.id` = WABA): aceito só se a WABA for a da conexão do caminho.

### Formulário manual (já implementado na branch `feat/waba-conexao-manual` para o App do ChatNexus)
- Campos: ID do número, ID da conta, token de acesso (senha) e nome.
- Validação na Meta antes de gravar: `GET /{phone}` e `GET /{waba}/phone_numbers` (o número tem de pertencer à conta). Número já conectado em outra empresa → 409.
- **Novo:** a caixa "Usar o App da Meta da própria empresa" pede também **App Secret** (obrigatório) e **App ID** (opcional, só para exibição).
- Depois de criar, a página da conexão mostra **URL do webhook + verify token** com botão de copiar, e os 6 campos a assinar no App do cliente. O verify token é visível para quem tem `integracao.manage`; o App Secret nunca volta na tela.
- `POST /{waba}/subscribed_apps` com o token do cliente (inscreve o App dele na WABA).

### Segurança
- App Secret e token cifrados em `conexao.credentials_encrypted`. Nunca em log, resposta ou auditoria.
- Rota nova com o mesmo contrato de erro do webhook atual: 200 com `rejected*` para assinatura ausente ou inválida; 5xx só em falha interna, para a Meta reentregar.
- Tenant: sempre pela conexão do caminho mais a checagem do `phone_number_id` do conteúdo. Nenhum `empresa_id` vem do payload.

### O que NÃO muda
- Nenhuma migração: `webhook_verify_token` e `credentials_encrypted` já existem.
- Envio (`WabaClient`), modelos de mensagem, eco, pausa da IA e histórico: iguais. O token já é por conexão.
- O `/webhook/waba` e o cadastro incorporado do App do ChatNexus (caminho de Tech Provider).

## 3. Alternativas consideradas
- **URL única com escolha do segredo pelo `phone_number_id` do conteúdo:** exigiria ler o JSON **antes** de validar a assinatura e tentar o segredo de cada empresa. Descartada: processar conteúdo não autenticado para decidir o segredo abre espaço para abuso. A URL por conexão resolve antes de ler o corpo.
- **Não validar assinatura, como o Chatwoot:** descartada. A Meta recomenda validar, e o webhook público do ChatNexus já recusa payload sem assinatura desde o hardening da Sprint D.
- **URL alternativa automática (`override_callback_uri`) na WABA do cliente:** possível, mas os campos continuam sendo assinados no App do cliente, então ele precisa entrar no painel da Meta de qualquer jeito. Fica para depois, se simplificar.

## 4. Entrega proposta (dev primeiro, como sempre)
1. **PR A — conexão manual pelo App do ChatNexus** (pronto na branch): destrava os vídeos da revisão com o número de teste.
2. **PR B — App próprio por empresa:** rota `/webhook/waba/{phone_number_id}`, App Secret no formulário, bloco "Webhook desta conexão" na página, testes unitários e E2E no dev:
   - webhook assinado com **outro** segredo aceito no caminho da conexão;
   - o mesmo payload recusado no `/webhook/waba`;
   - assinatura errada recusada;
   - `phone_number_id` de outra conexão descartado;
   - handshake com o token da conexão.
3. Documentação: seção "App próprio" em `WHATSAPP_COEXISTENCE.md`/`WABA_SETUP.md` e o passo a passo para o cliente (criar App, usuário do sistema, token "Nunca", registrar o número com PIN, colar URL e token, assinar os campos).

## 5. Riscos
- O cliente esquecer de assinar os campos no App dele: a conexão "funciona" para enviar, mas não recebe. Mitigação: o monitor de saúde já avisa por silêncio e pela sonda; a página mostra a lista de campos.
- Um mesmo número inscrito no App do ChatNexus e no do cliente recebe o webhook em duas URLs. A idempotência por wamid descarta a segunda entrega.
- O App do cliente em modo de desenvolvimento só fala com números de teste/admins do App dele. Isso é responsabilidade do cliente, e o passo a passo avisa.
