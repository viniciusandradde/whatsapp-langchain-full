"""Circuit breaker anti-zumbi do worker (incidente 2026-07-26).

`process_message` engole a exception e chama `mark_failed`, então o loop do
worker segue rodando alegremente enquanto NENHUM cliente é respondido. No
incidente isso durou ~40h com o container `Up` e `restarts=0`. O contador
`WORKER_HEALTH` é o sinal que o loop usa pra se matar e ser reiniciado.
"""

from whatsapp_langchain.worker.main import MAX_CONSECUTIVE_FAILURES
from whatsapp_langchain.worker.processor import WORKER_HEALTH


def test_falha_incrementa_contador() -> None:
    WORKER_HEALTH.record_success()

    WORKER_HEALTH.record_failure()
    WORKER_HEALTH.record_failure()

    assert WORKER_HEALTH.consecutive_failures == 2


def test_sucesso_zera_contador() -> None:
    """Uma mensagem respondida prova que o worker está vivo."""
    WORKER_HEALTH.record_failure()
    WORKER_HEALTH.record_failure()

    WORKER_HEALTH.record_success()

    assert WORKER_HEALTH.consecutive_failures == 0


def test_teto_dispara_apos_falhas_consecutivas() -> None:
    """O loop só se mata depois de MAX_CONSECUTIVE_FAILURES seguidas."""
    WORKER_HEALTH.record_success()

    for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
        WORKER_HEALTH.record_failure()
    assert WORKER_HEALTH.consecutive_failures < MAX_CONSECUTIVE_FAILURES

    WORKER_HEALTH.record_failure()
    assert WORKER_HEALTH.consecutive_failures >= MAX_CONSECUTIVE_FAILURES

    WORKER_HEALTH.record_success()


def test_teto_nao_reage_a_falha_isolada() -> None:
    """Erro transitório (LLM instável) não pode derrubar o worker."""
    WORKER_HEALTH.record_success()

    WORKER_HEALTH.record_failure()
    WORKER_HEALTH.record_success()
    WORKER_HEALTH.record_failure()

    assert WORKER_HEALTH.consecutive_failures < MAX_CONSECUTIVE_FAILURES

    WORKER_HEALTH.record_success()
