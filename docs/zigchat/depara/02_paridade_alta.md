# 02 — Paridade alta (✅) — entidades já bem alinhadas

[← Voltar ao índice](./README.md)

> Entidades onde Nexus já cobre o essencial do ZigChat. Gaps são triviais (campos extras opcionais).

## ModeloMensagem ↔ `modelo_mensagem` (mig 011)

✅ Equivalente direto. Ambos têm: id, empresa_id, titulo, conteudo, atalho, audit fields.

**Gaps menores:**
- ZigChat pode ter `tipo` (HSM aprovado vs free-form). Não confirmado pelos campos públicos.

**Recomendação:** sem ALTER por enquanto. Se virar necessidade WABA HSM, adicionar `tipo TEXT CHECK (tipo IN ('hsm', 'freeform'))`.

---

## VariavelAmbiente ↔ `variavel_ambiente` (mig 016)

✅ Equivalente direto. Ambos têm: id, empresa_id, nome, valor, descricao, ativo, audit fields.

**Recomendação:** sem ALTER necessário.

---

## Pasta ↔ `pasta` (mig 033)

✅ Equivalente. Folder/categoria de documentos de conhecimento.

**Recomendação:** sem ALTER.

---

## Hook (parcial) ↔ `hook` (mig 012)

✅ Estrutura básica equivalente: id, empresa_id, nome, evento, url, ativo, secret.

**Gaps menores:**
- ZigChat pode ter `headers` customizáveis (mandar Authorization/etc).
- ZigChat pode ter `metodo` (GET/POST/PUT).
- ZigChat pode ter `timeout_ms`.

**Mig sugerida (042 ou 048):**

```sql
ALTER TABLE hook
  ADD COLUMN metodo TEXT NOT NULL DEFAULT 'POST'
    CHECK (metodo IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')),
  ADD COLUMN headers JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN timeout_ms INT NOT NULL DEFAULT 5000;
```

**Recomendação:** opcional — só fazer se cliente real pedir. Headers customizáveis é o mais útil.

---

## Feriado ↔ `feriado` (mig 017)

✅ Equivalente. Datas que bloqueiam atendimento.

**Recomendação:** sem ALTER.

---

## EmpresaMembro ↔ `empresa_membro` (mig 003)

✅ Vínculo user × empresa. Equivalente.

**Recomendação:** sem ALTER.

---

## Permissao ↔ `permissao` (mig 031)

✅ Catálogo de permissões. Estrutura similar (`codigo`, `descricao`, `modulo`).

**Recomendação:** sem ALTER. Catálogo é mantido em código (`shared/permissoes.py::CATALOGO`).

---

## Grupo (Perfil) ↔ `perfil_acesso` (mig 031)

✅ Roles RBAC. Estrutura similar.

**Recomendação:** sem ALTER. Sistema RBAC do Nexus é mais granular (perfil_permissao many-to-many) que o do ZigChat.

---

## CampanhaDestinatario ↔ `campanha_destinatario` (mig 034)

✅ Equivalente.

**Recomendação:** sem ALTER.

---

## LoginEvent ↔ `auth_login_event` (mig 026)

✅ Audit de login (IP, user agent, timestamp).

**Recomendação:** sem ALTER.
