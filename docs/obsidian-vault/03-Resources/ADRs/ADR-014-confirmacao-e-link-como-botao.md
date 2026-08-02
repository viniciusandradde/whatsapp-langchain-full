---
title: ADR-014 — Confirmação com tom, e `ButtonLink` no lugar de `<Link><Button>`
type: adr
status: aceito
priority: media
created: 2026-07-31
updated: 2026-07-31
tags: [adr, frontend, acessibilidade, feedback]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Produto-Painel
projeto_pai:
relacionados: [PRD-Frontend]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-014 — Confirmação com tom, e `ButtonLink` no lugar de `<Link><Button>`

## Status

Aceito. Componentes entregues na Onda 6 (`36f3a11`); adoção em andamento —
`confirm_alert` ainda em 65.

## Contexto

Duas decisões pequenas que nasceram de defeitos encontrados em runtime.

**Confirmação.** O painel usava `confirm()` e `alert()` do navegador em 31 e 14
arquivos. Ao migrar para `AlertDialog`, apareceu o defeito A10: o primitivo
herda `variant="default"` do `Button`, então a confirmação de **apagar** saía
laranja, igual ao botão de salvar. Vermelho em tudo é vermelho em nada — mas
laranja em tudo é pior, porque não distingue nada.

**Link que parece botão.** Havia dois padrões, e ambos erravam:

- `<Link><Button/></Link>` — empilha **dois alvos interativos**, um `<button>`
  dentro de um `<a>`. Leitor de tela anuncia os dois. Era o padrão dominante,
  em 17 lugares.
- `Button render={<Link/>}` — o `ButtonPrimitive` do Base UI assume
  `nativeButton` e derruba erro de console quando o `render` devolve `<a>`:
  *"A component that acts as a button expected a native `<button>`"*.
  `/catalog/models` abria com "1 Issue" no overlay do Next.

## Decisão

**`ConfirmDestrutivo` com a propriedade `tom`:**

- `destrutivo` — pinta de vermelho e avisa que não dá para desfazer
- `serio` — não pinta (reativar acesso, resetar senha)

E, seguindo o contrato C4: ação destrutiva traz **o nome do objeto** no corpo;
acima de 50 registros, exige **digitar o total**; ação reversível não pede
confirmação, mostra `toast` com "desfazer".

**`ButtonLink`** em `components/ui/button.tsx`, que fixa `nativeButton={false}` —
um alvo interativo só, sem aviso de console.

## Consequências

### Positivas
- A cor da confirmação volta a significar alguma coisa.
- Um alvo interativo por link-botão; leitor de tela anuncia uma vez.

### Negativas
- **Restam 17 aninhamentos `<Link><Button>` em `src/app`** — cada tela migrada
  troca os seus. Até lá, os dois padrões convivem.
- `confirm_alert=65` mostra que a adoção mal começou: o componente existe em 6
  arquivos.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Manter `confirm()` | Não dá para pôr o nome do objeto, nem exigir digitação, nem seguir o tema |
| Pintar toda confirmação de vermelho | Vermelho em tudo é vermelho em nada — "reativar acesso" não é destrutivo |
| `asChild` do Radix | O primitivo em uso é o do Base UI, que resolve isso por `nativeButton` |

## Relacionados

- Contrato C4 — `docs/frontend/CONTRATOS-UI.md`
- Achados A8 e A10 — `docs/benchmark/nosso-painel/defeitos.md`
- Auditoria S6 e U3 — `docs/benchmark/nosso-painel/analise-ui-ux.md`
