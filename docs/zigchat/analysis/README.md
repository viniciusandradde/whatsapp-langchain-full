# Análises do schema ZigChat

> Saída do `_process.py` rodando sobre `../_schema_full.json`.
> Reproduzir: `cd docs/zigchat/analysis && python3 _process.py`

## Artefatos

1. [01_overview.md](./01_overview.md) — métricas brutas, distribuição, naming patterns
2. [02_relationships.md](./02_relationships.md) — FKs detectadas + types mais referenciados
3. [03_enums_and_strings.md](./03_enums_and_strings.md) — enums formais + boolean-em-string + enums semânticos
4. [04_field_frequency.md](./04_field_frequency.md) — top 50 campos + convenções universais
5. [05_parity_matrix.md](./05_parity_matrix.md) — comparativo field-by-field das 4 entidades core
6. [06_migrations_roadmap.md](./06_migrations_roadmap.md) — sequência sugerida de migrations 041-045 pra paridade
7. [07_conventions.md](./07_conventions.md) — patterns ZigChat: o que adotar, adaptar, ignorar

## Quando regerar

- Se baixar nova versão do schema ZigChat (atualiza `_schema_full.json`).
- Se mudar a heurística de categorização ou parity matrix manual.