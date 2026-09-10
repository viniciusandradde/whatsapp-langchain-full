# Migrar o Chat Nexus para outro servidor

Runbook de corte. O objetivo é levantar produção numa máquina nova **sem
re-parear nenhum número do WhatsApp** — em particular a sessão do Luis, que
atende cliente real.

Complementa `docs/BACKUP.md`: lá é o backup diário do banco da aplicação; aqui é
o conjunto completo que faz um servidor novo virar produção.

## O que precisa viajar

| Item | Onde vive hoje | Sai por |
|---|---|---|
| Banco da aplicação | container `...-db-1` | `pg_dump` (o timer 03:15 já gera) |
| **Sessões WhatsApp** | banco `evolution`, tabela `Session` | `pg_dump` do banco `evolution` |
| **Variáveis de ambiente de produção** | banco do Dokploy | `pg_dump` do banco `dokploy` |
| Definição dos serviços | `/etc/dokploy` | `tar` |
| Envs resolvidos dos containers | só em memória do Docker | `docker inspect` |
| Alertas do Telegram | `/etc/chatnexus-monitor.env` | cópia |
| Credencial do backup offsite | `/root/.config/rclone/rclone.conf` | cópia |
| Timers de backup/monitor/relatório | `/etc/systemd/system/chatnexus-*` | `tar` |

Tudo isso sai de uma vez com:

```bash
./scripts/exportar_producao.sh                       # gera o snapshot no dev
./scripts/exportar_producao.sh --verificar <snapshot> # PROVA que restaura
```

**Não precisa levar:** `/opt/registry` (8,6 GB de imagens — reconstruíveis do
git via CI), os volumes `logos_data` / `avatars_data` / `disparador_media`
(estão vazios) e `evolution_redis` (só cache).

## ⚠️ Cópia de arquivo não substitui `pg_dump`

`evolution_pgdata` e `dokploy-postgres` são volumes de bancos **em execução**.
Copiados a quente por WinSCP, `rsync` ou `cp`, saem rasgados e não restauram —
e o defeito só aparece na hora em que você precisa deles. Os `.dump` do script
saem de dentro do container, com consistência transacional.

## ⚠️ A sessão do WhatsApp: quente × frio

O Baileys guarda as credenciais na tabela `Session`, e elas **rotacionam durante
a conexão**. Isso cria duas qualidades de backup diferentes:

- **Dump a quente** (Evolution rodando) — vale como seguro contra desastre. Se o
  servidor sumir, você recupera; a sessão *pode* estar defasada e custar um
  re-pareamento.
- **Dump a frio** (Evolution parada) — a única forma de **garantir** migração
  sem QR, porque nada mais escreve na `Session` depois do dump.

Migração planejada usa o frio. Sempre.

## ⚠️ Duas Evolutions vivas derrubam a sessão

O WhatsApp aceita **uma** conexão por sessão. Se a Evolution antiga continuar de
pé quando a nova subir com a mesma `Session`, o servidor derruba uma das duas com
`conflict: replaced` — e é aleatório qual. Já aconteceu neste projeto.

Por isso a ordem abaixo não é preferência, é requisito: **a antiga morre antes
de a nova nascer, e não volta.**

---

## Fase A — Preparar o servidor novo (sem janela)

O DNS continua apontando para o servidor antigo; ninguém sente nada.

1. Docker, Dokploy, registry e rclone instalados na máquina nova.
2. Restaurar o banco do Dokploy — é o que devolve as variáveis de ambiente:
   ```bash
   docker exec -i <dokploy-postgres> pg_restore -U dokploy -d dokploy --clean --no-owner < dados/dokploy.dump
   tar xzf config/etc-dokploy.tar.gz -C /etc
   ```
3. Subir a stack `chatnexus` pelo painel do Dokploy (as imagens vêm do registry;
   se ele não viajou, rode o CI para reconstruí-las).
4. Restaurar o banco da aplicação:
   ```bash
   zstd -d dados/whatsapp_langchain.dump.zst -o /tmp/app.dump
   docker exec -i <db> pg_restore -U postgres -d whatsapp_langchain --clean --no-owner < /tmp/app.dump
   ```
5. Subir a Evolution **com o banco vazio** (só schema). Não restaure a sessão
   ainda — restaurar agora e deixar o container conectar disputaria a sessão com
   o servidor antigo, que ainda está no ar.
6. Fumaça interna por IP/porta: `/health` responde, painel abre, migrations
   aplicadas. Sem tráfego real.

## Fase B — Janela de corte (ordem obrigatória)

A partir daqui há indisponibilidade. Mensagens que chegarem no intervalo ficam
represadas no WhatsApp e são entregues na reconexão.

1. **Parar a Evolution ANTIGA.** Congela a `Session`; ninguém mais escreve nela.
   ```bash
   docker stop <evolution-api-antiga>
   ```
2. **Dump a frio** do banco da Evolution:
   ```bash
   docker exec <evolution-postgres-antiga> pg_dump -U evolution -Fc evolution > evolution-frio.dump
   ```
3. Parar a aplicação antiga e fazer o dump final do banco (pega o delta desde a
   Fase A).
4. Restaurar os dois no servidor novo.
5. **Repontar o DNS** no Cloudflare para o IP novo: `evolutionapi`, `api`, `chat`.
   Os webhooks gravados apontam para `https://api.vsanexus.com/webhook/evolution`
   e a aplicação fala com a Evolution por `EVOLUTION_API_URL` — os dois por nome,
   não por IP. Repontar o DNS basta; **não edite URL no banco.**
6. Subir a Evolution NOVA. Ela reconecta com a sessão restaurada, **sem QR**.
7. **Desabilitar a stack antiga para não voltar sozinha** — reboot do host
   antigo com `restart: always` religa a Evolution e derruba o Luis:
   ```bash
   docker update --restart=no $(docker ps -aq)   # no servidor ANTIGO
   systemctl disable --now chatnexus-backup.timer chatnexus-monitor.timer chatnexus-relatorio.timer
   ```

## Fase C — Conferir (antes de dizer que acabou)

1. As duas instâncias voltaram conectadas:
   ```bash
   docker exec <evolution-postgres> psql -U evolution -d evolution -t -A \
     -c 'SELECT name, "connectionStatus" FROM "Instance"'
   ```
   Esperado: `empresa1_luis_prod|open` e `empresa1_vinicius_pessoal|open`.
2. Nenhum `conflict: replaced` em `docker logs <evolution-api>`.
3. **Mensagem real de ida e volta** no número do Luis — é o único teste que
   prova a sessão. Estado `open` no banco não garante socket vivo.
4. Webhook chegando: uma mensagem recebida vira linha em `message_queue`.
5. Backup de volta em pé no servidor novo: restaurar `rclone.conf`, as units
   systemd, e rodar `chatnexus-backup.service` na mão uma vez.
6. Só então apagar qualquer coisa do servidor antigo.

## Se a sessão cair mesmo assim

Sintoma: `connectionStatus` vira `close`, log com `conflict` ou
`loggedOut`.

- **`conflict: replaced`** — outra Evolution conectou com a mesma sessão.
  Confirme que a antiga está parada e não tem `restart: always`.
- **`loggedOut` (código 401)** — a sessão foi invalidada e não há volta: só
  re-parear pelo painel. É o custo de ter usado dump a quente numa migração
  planejada.
- Sessão restaurada mas sem conectar: confira se `Session.creds` tem conteúdo
  (a verificação do script cobre isso) e se o `AUTHENTICATION_API_KEY` da
  Evolution nova é o mesmo — a aplicação autentica com ele.

## Referências

- `scripts/exportar_producao.sh` — export, verificação, cifra e envio offsite
- `docs/BACKUP.md` — backup diário do banco da aplicação
- `reference_acesso_producao` (memória) — IDs de compose, containers e acessos
