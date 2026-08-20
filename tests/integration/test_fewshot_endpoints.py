"""Smoke da mig 163 — few-shot em uso: curadoria + opt-in por agente.

O contrato que importa fixar aqui:
1. Todos os endpoints novos de curadoria (/api/admin/rag/fewshot*) exigem
   auth — a invariante da casa é que endpoint novo sem permissão é bug
   ([[gotcha_endpoint_novo_exige_permissao]]).
2. O PATCH do agente aceita `fewshot_enabled` no schema (sem isso a tela
   liga o switch e o backend ignora em silêncio — a armadilha clássica de
   "UI promete o que o backend ignora").

O comportamento de INJEÇÃO (worker antepõe exemplos quando ligado) é coberto
em tests/unit/test_fewshot_injecao.py, sem rede.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeCuradoria:
    def test_listar_sem_auth_401(self) -> None:
        assert _client().get("/api/admin/rag/fewshot").status_code == 401

    def test_orfaos_sem_auth_401(self) -> None:
        assert _client().get("/api/admin/rag/fewshot/orfaos").status_code == 401

    def test_atualizar_sem_auth_401(self) -> None:
        r = _client().patch("/api/admin/rag/fewshot/1", json={"status": "ready"})
        assert r.status_code == 401

    def test_mover_slug_sem_auth_401(self) -> None:
        r = _client().patch("/api/admin/rag/fewshot/mover-slug/a", json={"para": "b"})
        assert r.status_code == 401

    def test_deletar_sem_auth_401(self) -> None:
        assert _client().delete("/api/admin/rag/fewshot/1").status_code == 401


class TestContratoPatchAgente:
    def test_fewshot_enabled_esta_no_schema_do_patch(self) -> None:
        """Se o campo sumir do modelo de input, a tela liga e nada acontece."""
        from whatsapp_langchain.server.routes.agente import UpdateAgenteInput

        campos = UpdateAgenteInput.model_fields
        assert "fewshot_enabled" in campos
