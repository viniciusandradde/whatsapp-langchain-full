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

## Recomendação

**Não fazer um merge único dos 52 commits.** O risco não está distribuído por
igual: o backend e as migrations têm teste automatizado e foram exercitados
contra dados reais nesta sessão; as 44 telas não têm nem uma coisa nem outra.

Ordem sugerida:

1. **Rodar o pré-voo** contra produção. É barato e desarma o P0-2.
2. **Backup do banco.**
3. **Subir primeiro backend + migrations** (o que tem teste), em janela de baixo
   tráfego, acompanhando o container novo ficar healthy.
4. **Depois o frontend**, revisado tela a tela contra
   `docs/benchmark/nosso-painel/img/` — que, atenção, **não está nesta máquina**
   (ficou no VPS, sem commit).

Se a preferência for release único, então o mínimo é: pré-voo + backup + janela
de baixo tráfego + alguém olhando as telas principais logo depois.
