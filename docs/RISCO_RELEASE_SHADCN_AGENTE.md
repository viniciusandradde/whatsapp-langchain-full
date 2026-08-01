# Avaliação de risco — release `feat/shadcn-onda-0` → produção

> Levantado em 2026-08-01, com a branch em `52ec8e2` e `origin/master` em
> `00f08fb`. **`origin/master` não andou** desde que a branch saiu — não há
> rebase pendente nem conflito a resolver.

## Escopo

| medida | valor |
|---|---|
| commits à frente do master | **52** |
| arquivos alterados | 248 (+19.809 / −7.364) |
| migrations novas | **8** (151, 152, 154–159) |
| telas do painel tocadas | **44** |
| primitivos de UI (`components/ui/`) | ~25 arquivos, quase todos novos |
| alterações em `docker-compose*` / `Dockerfile*` | **nenhuma** |
| variáveis de ambiente novas exigidas | **nenhuma** |

Não é uma entrega — são cinco, empilhadas: migração do ambiente de dev,
remoção do Wareline, migração shadcn (Ondas 0–6), colapso/rename dos templates
de agente, e versionamento de prompt com bateria.

---

## Resultado do pré-voo (medido em produção, 2026-08-01)

Rodado com `scripts/prod_readonly.sh` — leitura imposta em duas camadas, ver o
próprio script. Acesso por Tailscale (`opc@vps-docker03`).

| # | pergunta | resposta | veredito |
|---|---|---|---|
| 1 | templates existentes | `atendimento_completo` (16), `vsa_tech` (3) | **desarmado** — os dois são tratados por 156/157; nenhum desconhecido |
| 2 | agentes com prompt vazio | 8, **todos** `atendimento_completo` | **desarmado** — a mig 155 cobre exatamente esse template |
| 3 | volume do backfill da 158 | 13 linhas; `audit_log` inteiro tem 329 linhas / 608 kB | **irrelevante** — sem custo de startup |
| 4 | dados do Wareline | zero tabelas `wareline%` em qualquer schema | **no-op** — já foram removidas (ver abaixo) |
| 5 | escopo da mig 154 | 16 agentes | conforme esperado |

Confirmações extras, contra produção, das decisões que eu havia tomado com
dados de dev: **0** MCP servers, **0** agentes com `mcp_server_ids`, **0**
`api_connection`, **16 de 19** agentes com base de conhecimento, 9 empresas.
Dev é cópia fiel — as decisões de priorização se sustentam.

### Só 6 das 8 migrations vão rodar

`151_drop_wareline.sql` e `152_perfis_descricao_pt.sql` **já estão aplicadas em
produção** desde 31/07 — e não por deploy. Foram aplicadas por um uvicorn de
desenvolvimento apontado para o banco de produção, incidente documentado em
`ede70f0`, que introduziu `SKIP_MIGRATIONS` justamente para fechar essa porta.

Consequências:

- O `_migrations` vai pular as duas. Rodam **154, 155, 156, 157, 158, 159**.
- O `DROP TABLE` do Wareline **já aconteceu**. O risco P1-4 não existe mais —
  não porque foi avaliado, mas porque já foi consumado sem revisão.
- Produção está com schema à frente do `origin/master` em duas migrations. O
  release recoloca as duas coisas em sincronia.

### Correção ao que eu disse antes

O bug que achei e corrigi hoje (`52ec8e2`, agente sem prompt ficando sem versão
inicial na mig 158) **não teria disparado neste deploy**: os 8 agentes com
prompt vazio são todos `atendimento_completo`, e a mig 155 roda antes e preenche
todos. O conserto continua certo — é mina latente para qualquer agente criado
com o campo vazio fora daquele template — mas eu apresentei como iminente e não
era.

---

## O que dispara o quê

- `.github/workflows/deploy.yml` roda **só em push para `master`**. Push de
  branch **não** deploya.
- As migrations rodam no **startup da API e do worker**, os dois em paralelo,
  serializados apenas pelo advisory lock `8_642_000`. **Migration que falha =
  processo que não sobe**, não erro de dado.

---

## Riscos

### P0 — derruba a produção

**1. Agente sem prompt derrubaria o startup (CORRIGIDO em `52ec8e2`)**

A dedup do seed da mig 158 usava `texto_anterior IS DISTINCT FROM texto`, e na
primeira linha da partição o `LAG` devolve NULL. Com `prompt_override` nulo a
comparação vira `NULL IS DISTINCT FROM NULL` = FALSO: a linha inicial era
descartada, o agente ficava sem versão, e o guard levantava.

Não apareceu em dev porque os 19 agentes daqui têm prompt preenchido. Em
produção o cenário existe: a mig 155 só materializa `atendimento_completo` e
`agendamentos`. Conferido em transação revertida com agentes sintéticos
(prompt `NULL` e `''`): 21 agentes → 21 versões, guard passa.

**2. Template desconhecido derruba a mig 157 — NÃO VERIFICADO**

`157_template_agente.sql:47` levanta se sobrar qualquer agente com
`template_catalog NOT IN ('agente', 'atendimento_router')`. A mig 156 converte
`atendimento_completo` e `agendamentos`; a 157 renomeia `vsa_tech`. **Se
produção tiver um template fora desses quatro, a migration falha e a API não
sobe.** Não dá para verificar daqui — o ambiente de dev saiu do VPS. Ver
pré-voo abaixo.

**3. Guard de divergência da 158 — NÃO VERIFICADO**

Levanta se a versão de topo não for idêntica ao `prompt_override` vivo. A
lógica garante isso por construção, mas depende de o backfill de `audit_log`
não produzir uma linha final inesperada. O pré-voo mede o volume envolvido.

### P1 — quebra funcionalidade sem derrubar

**4. Remoção do Wareline é irreversível.** A mig 151 dá `DROP TABLE` em
`wareline_token_cache` e `wareline_credentials` e apaga a permissão
`integracao.wareline.manage`. Sem backup, não volta.

**5. Janela do rename de template.** Coberta pelo shim em `catalog/vsa_tech/`
(ver `gotcha_deploy_com_shim_de_template`). **A etapa 4 — remover o shim — NÃO
pode entrar neste release**; só depois de um deploy estável com a coluna já
migrada.

**6. Mudança de comportamento na criação de agente.** Agente novo passa a
nascer com o `SYSTEM_PROMPT` do template escrito no campo. É intencional, mas é
diferente do que existe hoje.

### P2 — visual, e é o de maior probabilidade

**7. 44 telas alteradas e o conjunto de primitivos de UI trocado por inteiro.**

Este é o item sem evidência. `feedback_ui_global_precisa_validacao_visual`
registra exatamente esta forma: *"6 mudanças responsivas num PR = revert total,
inclusive a parte certa"*. Aqui são 44 telas. Só uma fração foi vista em tela
real nesta sessão (`/agents`, editor de agente).

Um defeito de layout não derruba a API — mas atinge todo cliente ao mesmo
tempo, e o custo de reverter é o release inteiro.

### Operacional

**8. `.github/workflows/frontend.yml` é arquivo novo.** Push de `.github/`
exige token com escopo `workflow` (`checkpoint_cicd_github_actions`).

**9. Deploy sob carga se cancela sozinho.** Pausar o que estiver pesado antes
(`gotcha_deploy_sob_carga`).

**10. Deploy verde ≠ migration aplicada.** Esperar o container **NOVO** (id
diferente) ficar healthy — o antigo segue healthy e dá falso negativo
(`gotcha_deploy_success_nao_e_migration_aplicada`).

---

## Pré-voo: rodar contra o banco de PRODUÇÃO antes do merge

```sql
-- 1. P0-2: algum template fora do conjunto que 156/157 tratam?
--    Esperado: só vsa_tech, atendimento_completo, agendamentos, atendimento_router
SELECT template_catalog, count(*) FROM agente_ia GROUP BY 1 ORDER BY 2 DESC;

-- 2. P0-1/3: agentes que chegam na 158 com prompt vazio (agora suportado,
--    mas mede o quanto o caminho corrigido é exercitado)
SELECT template_catalog, count(*) FROM agente_ia
 WHERE prompt_override IS NULL OR btrim(prompt_override) = ''
 GROUP BY 1;

-- 3. Volume do backfill: quanto a 158 vai ler de audit_log no startup
SELECT count(*) AS linhas_com_prompt
  FROM audit_log
 WHERE action = 'agente.update'
   AND entity_type = 'agente_ia'
   AND jsonb_exists(payload_diff->'before', 'prompt_override');

-- 4. P1-4: o Wareline ainda tem dado que alguém queira?
SELECT to_regclass('wareline_credentials') IS NOT NULL AS existe,
       (SELECT count(*) FROM wareline_credentials) AS linhas;

-- 5. Sanidade: a 154 vai materializar tools em quantos agentes?
SELECT count(*) FROM agente_ia WHERE template_catalog = 'atendimento_completo';
```

**Se a consulta 1 devolver qualquer valor fora dos quatro esperados, PARE** — a
migration 157 vai falhar e a API não sobe. O conserto é acrescentar o valor ao
mapeamento da 156 antes de subir.

## Plano de rollback

O caminho de volta **não é simétrico**: as migrations não têm `down`.

- **Código**: `git revert` do merge + push → o CI/CD reconstrói e o Dokploy faz
  pull da imagem anterior.
- **Banco**: 154/155/158/159 são aditivas — o código antigo ignora colunas e
  tabela novas, então reverter só o código funciona. **156, 157 e 151 não**:
  o rename de template e o `DROP` do Wareline exigem restore de backup.
- **Consequência prática**: tirar backup do banco imediatamente antes, e tratar
  o release como ponto sem retorno para 151/156/157.

## Recomendação (revisada após o pré-voo)

**O lado do banco está muito melhor do que eu temia.** Todos os P0 foram
medidos e desarmados: nenhum template desconhecido, nenhum agente que chegue
vazio na 158, backfill de 13 linhas, Wareline já removido. As 6 migrations que
restam são previsíveis e o volume é pequeno.

**O risco concentrou-se todo no frontend.** 44 telas e o conjunto de primitivos
de UI trocado por inteiro, sem teste automatizado e com validação visual apenas
parcial. `feedback_ui_global_precisa_validacao_visual` registra exatamente esta
forma causando revert total.

Ordem sugerida:

1. **Backup do banco** — 156 e 157 continuam sem caminho de volta sem restore.
2. **Subir backend + migrations primeiro**, em janela de baixo tráfego,
   esperando o container **novo** ficar healthy
   (`gotcha_deploy_success_nao_e_migration_aplicada`). O shim de template cobre
   a janela entre código novo e migration aplicada.
3. **Conferir na hora**: `SELECT template_catalog, count(*) FROM agente_ia
   GROUP BY 1` deve devolver só `agente`; e `SELECT origem, count(*) FROM
   agente_prompt_versao GROUP BY 1` deve mostrar 19 `inicial` + até 13
   `backfill`.
4. **Frontend depois**, tela a tela. As capturas de referência
   (`docs/benchmark/nosso-painel/img/`) **ficaram no VPS, sem commit** — sem
   elas a revisão é de memória.

Se for release único, o mínimo é backup + janela de baixo tráfego + alguém
olhando as telas principais logo depois do deploy.

**Não incluir neste release:** a etapa 4 do rename (remover o shim
`catalog/vsa_tech/`). Só depois de um deploy estável com a coluna já migrada.
