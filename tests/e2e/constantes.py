"""Ids fixos da bateria E2E, em um lugar só.

Espelham `tests/e2e/fixtures/seed.sql`. Ficam aqui, e não no `conftest.py`,
porque `fixtures/jornada.py` também precisa deles — e módulo de fixture
importando `conftest` é caminho curto para import circular.

**Por que 900 e não 1:** até 2026-08-05 o seed escrevia na empresa 1 com
`ON CONFLICT DO UPDATE`. Como a bateria roda no mesmo banco do ambiente de
desenvolvimento, cada execução renomeava para "VSA Tech (test)" a empresa que o
painel estava usando e reescrevia os agentes dela. O produto já isola por
tenant; o teste passa a usar o mesmo mecanismo.
"""

from __future__ import annotations

EMPRESA_E2E = 900

#: Conexão das jornadas de setor. `twilio_sandbox` + `TWILIO_OUTBOUND_MODE=mock`
#: é o que impede a bateria de mandar WhatsApp de verdade para os números
#: inventados dos testes.
CONEXAO_SANDBOX = 900

#: Conexão das jornadas de documento. Precisa ser `evolution` porque
#: `get_conexao_by_evolution_instance` filtra por provider — e o webhook
#: Evolution é o único que carrega `documentMessage.fileName`, o nome de arquivo
#: que a migration 164 passou a guardar.
CONEXAO_EVOLUTION = 901
INSTANCIA_EVOLUTION = "e2e-docs"

#: Agente usado nas jornadas de documento: é o que o seed aponta na conexão 901.
AGENTE_DOCUMENTOS = "atendimento-cliente"
