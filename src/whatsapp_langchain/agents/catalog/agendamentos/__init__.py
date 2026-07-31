"""Subprojeto do agente `agendamentos`.

Focado em marcar/remarcar/cancelar consultas. Set enxuto de tools (vs ~22 do
`atendimento_completo`) — menos ruído pro LLM, decisões mais rápidas, custo
menor.

Tools incluídas:
- Agenda (8, quando a empresa tem Google Calendar conectado): horário atual,
  listar agendas, definir agenda ativa, listar eventos, achar horário livre,
  criar, remarcar e cancelar
- CRM contexto (get_cliente_profile, get_cliente_history)
- Memória (read_memory, save_memory) quando store ativo
- Escalação (transfer_to_human, classificar_atendimento)

Excluídas: multimodais (não precisa) e base de conhecimento (orientação clínica
sai por humano).

Até 2026-07-31 as tools de agenda vinham da integração Wareline ConecteHub, que
saiu do produto — integração externa passou a ser API + webhook genéricos, pelo
conector de `/settings/integracoes`.
"""
