# PATCH Pattern — Como permitir "limpar" um campo

> **Problema sistêmico identificado em 5+ features** (2026-05-20).
> Esta doc é a regra do projeto pra novos endpoints PATCH.

## Sintoma

User clica "Apagar" num campo opcional via UI (ex: limpar lista de
`coleta_perguntas` de um menu_item, ou apagar `prompt_override` de um
agente). Salva. Refresca. **Valor antigo volta.**

Frontend tá certo (envia `null` ou `[]`). Backend trata `null` como
"não tocar". Impossível limpar via API.

## Causa raiz

Ambiguidade do `None` em Pydantic. Quando user envia:

```json
{ "coleta_perguntas": null }
```

vs não envia nada (`{}`), **ambos viram `None` no model**. Sem
distinguir, código fica obrigado a escolher 1 dos 2 comportamentos:

- Tratar `None` como "não tocar" → impossível limpar
- Tratar `None` como "limpar" → impossível PATCH parcial

Pattern errado em uso (anti-padrão):

```python
# ❌ ERRADO — perde o caso "user quer limpar"
fields = {k: v for k, v in body.model_dump().items() if v is not None}
await update_resource(pool, id, **fields)

# ❌ ERRADO no shared também — mesma armadilha
async def update_resource(pool, id, **fields):
    for k, v in fields.items():
        if v is None:  # ← bug aqui
            continue
        sets.append(f"{k} = %s")
```

## ✅ Solução — `model_dump(exclude_unset=True)`

Pydantic distingue corretamente quando o user **explicitamente setou**
um campo (mesmo que pra `None`) vs quando omitiu. O atributo
`model_fields_set` lista campos explícitos. `model_dump(exclude_unset=True)`
retorna só esses.

### Regra do projeto

**1. No `route` (FastAPI endpoint):**

```python
# ✅ CERTO
@router.patch("/{id}")
async def update_endpoint(id: int, body: UpdateInput):
    fields = body.model_dump(exclude_unset=True)
    # fields contém SÓ os campos que user enviou — null incluso
    await update_resource(pool, id, **fields)
```

**2. No `shared` (helper que faz UPDATE):**

```python
# ✅ CERTO
async def update_resource(pool, id, **fields):
    READONLY = {"id", "created_at", "updated_at"}
    sets = []
    params = []
    for k, v in fields.items():
        if k in READONLY:
            continue
        # NÃO filtrar v is None — agora None significa "limpar"
        if k == "lista_jsonb":
            sets.append(f"{k} = %s::jsonb")
            # `v if v else None` — array vazio vira NULL no DB
            params.append(json.dumps(v, ensure_ascii=False) if v else None)
        else:
            sets.append(f"{k} = %s")
            params.append(v)
    # ... resto do UPDATE
```

**3. No `frontend` (Server Actions / form submit):**

Pra LIMPAR um campo, envia `null` explicitamente:

```ts
// ✅ CERTO — limpa coleta_perguntas
await updateItem(itemId, { coleta_perguntas: null });

// ✅ CERTO — limpa prompt_override
await updateAgente(slug, { prompt_override: null });

// Pra LISTA vazia (≠ apagar), depende da semântica:
// - Se backend trata [] como NULL → tanto faz
// - Se backend diferencia → envie o que quer
await updateItem(itemId, { coleta_perguntas: [] });
```

## Por que NÃO usar sentinelas (`"__DELETE__"`, etc)

Já vi propostas tipo "envia string `__DELETE__` pra limpar". Anti-padrão:

- ❌ Vaza no JSON da API pública
- ❌ Diferentes campos têm diferentes sentinelas
- ❌ Type-check fica errado
- ❌ Pydantic não ajuda

`exclude_unset` é o padrão idiomático do ecossistema.

## Por que NÃO usar `Optional[Field()] = ...` com factory

Pydantic permite default factory custom:

```python
class UpdateInput(BaseModel):
    # ❌ Não resolve — ainda vira None se user mandar null
    coleta_perguntas: list[dict] | None = Field(default=None)
```

O default só ajuda na criação. PATCH precisa do `model_fields_set` que
é populado pelo Pydantic em runtime independente do default.

## Lista de lugares corrigidos (commit `<hash>`)

| Arquivo | Linha original do bug | Fix |
|---|---|---|
| `shared/menu_chatbot.py::update_item` | L450 `or v is None` | Removido filtro None |
| `shared/menu_chatbot.py::update_menu` | L288 idem | Removido filtro None |
| `shared/agente.py::update_agente` | L272 idem | Removido filtro None |
| `shared/catalogo.py::update_modelo_llm` | L144 idem | Removido filtro None |
| `shared/catalogo.py::update_mcp_server` | L303 idem | Removido filtro None |
| `routes/menu_chatbot.py::update_item_endpoint` | L508 `if v is not None` | `exclude_unset=True` |
| `routes/menu_chatbot.py::update_menu_endpoint` | L269 idem | `exclude_unset=True` |
| `routes/agente.py::update_endpoint` | L216 idem | `exclude_unset=True` |
| `routes/catalogo.py::update_modelo_endpoint` | L144 idem | `exclude_unset=True` |
| `routes/catalogo.py::update_mcp_endpoint` | L287 idem | `exclude_unset=True` |

## Checklist pra novos endpoints PATCH

Ao criar novo endpoint PATCH, **antes de commitar**:

- [ ] Route usa `body.model_dump(exclude_unset=True)` (NÃO filtra `is None`)
- [ ] Shared helper NÃO tem `if v is None: continue`
- [ ] Shared helper trata `None` corretamente (vira `NULL` no SQL ou comportamento explícito)
- [ ] Pydantic field é `field: T | None = None` (permite null no JSON)
- [ ] Teste E2E cobre cenário "limpar campo" (PATCH com `{campo: null}` → GET retorna `null`)
- [ ] Frontend: action pra limpar envia `null` explícito (não `undefined`)

## Caso especial: JSONB null vs `[]` vs `{}`

Pra colunas JSONB nullable, definir convenção por campo:

| Campo | NULL = | `[]` = | `{}` = |
|---|---|---|---|
| `coleta_perguntas` (list) | sem wizard | sem wizard (idem) | inválido |
| `payload_json` (dict) | nunca (default `{}`) | nunca | sem extras |
| `componentes_json` (list) | inválido | sem componentes | inválido |

Documentar no docstring do campo qual é o tratamento.

## Anti-patterns que ainda vou pegar (search do projeto)

```bash
# Pattern problemático em UPDATE helpers
grep -rn "if k in READONLY or v is None" src/whatsapp_langchain/shared/

# Pattern problemático em routes
grep -rn "items() if v is not None" src/whatsapp_langchain/server/routes/
```

Se encontrar, aplicar o pattern desta doc.

## Por que isso é IMPORTANTE pro projeto

User reclamou explicitamente: "não consigo apagar, volta novamente —
tem várias features com esse problema, não é pra repetir". Esse pattern
afeta confiança no produto. Toda feature de admin/config sofre. Cumprir
essa regra evita 100% das reclamações futuras desse tipo.

## Referências

- [Pydantic docs — model_dump exclude_unset](https://docs.pydantic.dev/latest/concepts/serialization/#modelmodel_dump)
- [Pydantic docs — model_fields_set](https://docs.pydantic.dev/latest/concepts/models/#fields-set)
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396) (motivação semelhante)
