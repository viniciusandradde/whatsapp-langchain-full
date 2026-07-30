# Superfície de API do Chatvolt

43 endpoints distintos, observados em 18 rotas do painel.

Coletado do tráfego XHR do próprio painel — não é documentação oficial.

| endpoint | forma da resposta | visto em |
|---|---|---|
| `/_next/data/fclnaS2B_QQynYrcJqYl0/pt-BR/apps.json` | `obj{pageProps, __N_SSP}` | 1 rotas |
| `/api/accounts/api-keys` | `lista[1]` | 2 rotas |
| `/api/agents` | `lista[1]` | 8 rotas |
| `/api/agents/{id}/public` | `obj{id, name, description, visibility, interfaceConfig, icon` | 18 rotas |
| `/api/analytics` | `obj{total_conversations, total_messages, new_conversations, ` | 1 rotas |
| `/api/analytics/crm-scenarios` | `lista[0]` | 1 rotas |
| `/api/artifact-categories` | `lista[0]` | 2 rotas |
| `/api/artifacts` | `obj{data, total}` | 1 rotas |
| `/api/auth/session` | `obj{authType, user, expires, roles, organization}` | 18 rotas |
| `/api/banner/en-US/{id}` | `NoneType` | 4 rotas |
| `/api/banner/pt-BR/{id}` | `NoneType` | 18 rotas |
| `/api/contacts` | `obj{contacts, count, hasMore, nextCursor}` | 1 rotas |
| `/api/contacts/available-variables` | `obj{variables}` | 1 rotas |
| `/api/contacts/ctwa-ads` | `lista[0]` | 3 rotas |
| `/api/crm/scenario` | `lista[0]` | 4 rotas |
| `/api/custom-filters` | `lista[0]` | 1 rotas |
| `/api/datastores` | `lista[1]` | 1 rotas |
| `/api/dispatches` | `obj{dispatches, count}` | 1 rotas |
| `/api/dispatches/contacts/lists` | `obj{lists, count}` | 1 rotas |
| `/api/forms` | `lista[0]` | 1 rotas |
| `/api/heartbeat` | `obj{ok}` | 18 rotas |
| `/api/logs` | `obj{total_conversations, distinct_agents, distinct_channels}` | 18 rotas |
| `/api/logs/count-unread` | `int` | 18 rotas |
| `/api/memberships` | `lista[1]` | 6 rotas |
| `/api/memberships/get-user-permissions` | `lista[1]` | 18 rotas |
| `/api/negative-messages` | `obj{data, hasMore, nextCursor, totalCount}` | 2 rotas |
| `/api/organizations` | `lista[1]` | 18 rotas |
| `/api/organizations/credits-status` | `obj{exhausted, used, remaining}` | 18 rotas |
| `/api/organizations/{id}` | `obj{id, name, iconUrl, description, website, keyOpenai}` | 3 rotas |
| `/api/organizations/{id}/avulso-credits` | `obj{agentCredit, whatsappDispatch}` | 18 rotas |
| `/api/organizations/{id}/get-google-credentials` | `obj{googleClientId, googleClientSecret}` | 1 rotas |
| `/api/organizations/{id}/next-renewal` | `obj{nextRenewalDate}` | 18 rotas |
| `/api/organizations/{id}/verify-subscription` | `obj{hasSubscription, hasIncompleteSubscription, hasScheduled` | 1 rotas |
| `/api/service-providers` | `lista[0]` | 1 rotas |
| `/api/status` | `obj{status, db, vectorDb, openAI, isMaintenance, latestVersi` | 18 rotas |
| `/api/system-logs` | `lista[1]` | 18 rotas |
| `/api/tags/get-visible-tags` | `lista[0]` | 3 rotas |
| `/api/teams` | `lista[0]` | 1 rotas |
| `/api/user-agent-permissions/get-visible-agents` | `NoneType` | 5 rotas |
| `/api/user-agent-permissions/get-visible-datastores` | `lista[1]` | 1 rotas |
| `/api/voltapi` | `lista[0]` | 1 rotas |
| `/api/zapi/hasZapiProvider` | `obj{hasProvider, integrations, message}` | 1 rotas |
| `/api/zapper/integrations` | `obj{hasProvider, integrations, message}` | 1 rotas |
