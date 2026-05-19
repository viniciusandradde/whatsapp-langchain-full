"""Subprojeto do agente `agendamentos` (Sprint Wareline ConecteHub).

Focado em marcar/remarcar/cancelar consultas via integração Wareline.
Set enxuto de ~7 tools (vs ~22 do `atendimento_completo`) — menos ruído
pro LLM, decisões mais rápidas, custo menor.

Tools incluídas:
- 3 Wareline (buscar_paciente, consultar_agenda, criar_agendamento)
- CRM contexto (get_cliente_profile, get_cliente_history)
- Memória (read_memory, save_memory) quando store ativo
- Escalação (transfer_to_human, classificar_atendimento)

Excluídas: multimodais (não precisa), KB (orientação clínica via humano),
calendar Google (Wareline substitui).
"""
