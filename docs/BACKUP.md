# Backup do banco de produção

O backup roda **no host**, não dentro do container: é um script + timer do
systemd (`scripts/backup_prod.sh`), independente do deploy da aplicação.

Três cópias, com propósitos diferentes:

| Cópia | Onde | Protege contra | Retenção |
|---|---|---|---|
| Dump local | `$DESTINO` no host (hoje `/home/opc/backup`) | erro humano, migration ruim, `DROP TABLE` | `RETENCAO_DIAS` (14) |
| Espelho externo | Google Drive via rclone | **perder o servidor inteiro** | `RCLONE_RETENCAO_DIAS` (90) |
| Espelho de dev | `~/backups/chatnexus-prod/` (cron rsync 04:30) | conveniência para restaurar em dev | 30 dias |

A cópia externa existe por causa do incidente de **2026-08-19**: o host sumiu e
levou junto o dump em disco e o espelho no MinIO — os dois moravam nele.

## O que o script faz

1. `pg_dump -Fc` de dentro do container → comprime (zstd/pigz/gzip, o que houver)
2. **Verifica a integridade** com `pg_restore -l`: menos de 100 objetos no índice
   = truncado, o arquivo é apagado e o script falha (não existe backup falso)
3. Espelha no MinIO, se `MINIO_ALIAS` estiver definido
4. **Envia para fora do host**, se `RCLONE_REMOTE` estiver definido
5. Aplica retenção local e remota

Ordem importa: só sobe o que já se provou restaurável.

## Variáveis (todas via env / drop-in da unit)

| Var | Default | Para quê |
|---|---|---|
| `CONTAINER_DB` | `projetos-chatvsanexus-er02mp-db-1` | container do Postgres |
| `BANCO` | `whatsapp_langchain` | base a dumpar |
| `DESTINO` | `/home/dev/backup` | diretório dos dumps |
| `RETENCAO_DIAS` | `14` | corte da retenção local |
| `RCLONE_REMOTE` | *(vazio = desligado)* | destino externo, ex. `gdrive:chatnexus-backups` |
| `RCLONE_RETENCAO_DIAS` | `90` | corte da retenção remota |
| `CONFIG_ALERTA` | `/etc/chatnexus-monitor.env` | de onde saem `TELEGRAM_BOT_TOKEN`/`CHAT_ID` |

A unit gerada por `--instalar` **não carrega EnvironmentFile** — os valores vêm
de um drop-in em `/etc/systemd/system/chatnexus-backup.service.d/override.conf`.

## Falha de upload é barulhenta, mas não derruba o backup

Se o envio externo falhar, o dump local continua válido e o script termina com
sucesso — mas dispara alerta no Telegram na hora, no mesmo canal do
`monitor_evolution.sh` (WhatsApp não serve: quando o host cai, ele cai junto).

Além disso, o relatório diário de produção tem a checagem
`checar_backup_offsite` (`scripts/producao_checks.py`): mais de 26h sem upload
bem-sucedido vira **CRÍTICO**. A fonte é o marcador
`$DESTINO/.ultimo_upload_offsite_ok`, tocado só quando o arquivo é confirmado no
destino — o exit code do systemd não serve, porque a falha de upload é
best-effort e não reprova a unit.

Instalação sem `RCLONE_REMOTE` fica em silêncio nessa checagem: cópia externa
desligada é opção, e alarme que dispara todo dia treina quem lê a ignorar.

## Setup do Google Drive (uma vez)

O timer roda como root, então o remoto tem que estar no rclone **do root**.

1. **Instalar o rclone no host**
   ```bash
   curl -fsSL https://rclone.org/install.sh | sudo bash
   ```

2. **Autorizar numa máquina com navegador** (o host não tem):
   ```bash
   rclone authorize "drive" -- --scope drive.file
   ```
   Faz login na conta Google destino e devolve um JSON de token no terminal.

   `drive.file` é proposital: o rclone só enxerga o que ele mesmo criou. Se o
   `rclone.conf` vazar, o resto do Drive continua fora de alcance.

3. **Criar o remoto no host**, colando o token:
   ```bash
   sudo rclone config     # n) new remote → nome: gdrive → tipo: drive
                          # scope: 3 (drive.file) → advanced: n
                          # auto config: n → colar o JSON do passo 2
   sudo chmod 600 /root/.config/rclone/rclone.conf
   sudo rclone lsd gdrive:          # confere que autenticou
   ```

4. **Ligar no drop-in da unit**:
   ```ini
   # /etc/systemd/system/chatnexus-backup.service.d/override.conf
   [Service]
   Environment=CONTAINER_DB=chatnexus-hatvsanexus-nfcfwu-db-1
   Environment=DESTINO=/home/opc/backup
   Environment=RCLONE_REMOTE=gdrive:chatnexus-backups
   ```
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start chatnexus-backup.service
   journalctl -u chatnexus-backup -n 30 --no-pager
   ```

5. **Conferir**: `sudo rclone lsf gdrive:chatnexus-backups` lista o dump do dia,
   e `stat /home/opc/backup/.ultimo_upload_offsite_ok` mostra a hora do envio.

### Serviço de conta (service account) não serve aqui

Service account do Google não tem cota de storage própria, e conta Gmail comum
não tem Shared Drive — o upload falha com `storageQuotaExceeded`. É limitação do
Google, não configuração. Por isso o caminho é OAuth de usuário com refresh
token.

## Restaurar

Sempre numa base **nova**; trocar a produção pela restaurada é decisão humana,
depois de conferir:

```bash
scripts/backup_prod.sh --restaurar /home/opc/backup/prod-AAAA-MM-DD.dump.zst
# cria a base restaurado_AAAAMMDD_HHMM e imprime como conferir e como descartar
```

Baixar um backup do Drive para restaurar:
```bash
sudo rclone copy gdrive:chatnexus-backups/prod-AAAA-MM-DD.dump.zst /home/opc/backup/
```
