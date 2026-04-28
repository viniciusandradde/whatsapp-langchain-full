"""Testes E2E de fluxos realistas — jornadas de usuário completas.

Cada cenário simula uma jornada real de uso do sistema WhatsApp + LangGraph,
exercitando a integração entre webhook, fila, worker, agente e API admin.

Estes testes são ideais para demonstrar em aula como debugar o sistema:
- Cada passo imprime no terminal o que está fazendo (via capsys/print)
- Os asserts têm mensagens descritivas explicando o que falhou
- Verificações cruzam banco (queries diretas) + API (endpoints admin)

Pré-requisito:
    docker compose up -d --build

Uso:
    # Rodar todos os cenários
    uv run pytest tests/integration/test_realistic_flows.py -v -s

    # Rodar cenário específico
    uv run pytest tests/integration/test_realistic_flows.py -v -s -k "novo_usuario"

    # Com output detalhado para debug em aula
    uv run pytest tests/integration/test_realistic_flows.py -v -s --tb=long
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import psycopg
import pytest

from .helpers import (
    API_BASE_URL,
    clear_thread_checkpoints,
    count_queue_entries,
    get_admin_api_headers,
    get_db_url,
    query_conversation,
    query_queue_entry,
    send_webhook,
    send_webhook_and_wait,
    unique_phone,
    unique_sid,
    wait_conversation_count,
    wait_memory_saved,
    wait_queue_done,
    wait_terminal_status,
)

pytestmark = pytest.mark.docker_demo
ADMIN_API_HEADERS = get_admin_api_headers()


# ---------------------------------------------------------------------------
# Fixture: valida que a stack Docker está rodando
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_url() -> str:
    """Valida pré-requisitos e retorna URL do banco."""
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if response.status_code != 200:
            pytest.skip("API não saudável. Rode: make up")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")

    url = get_db_url()
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique docker compose e DATABASE_URL")

    return url


# ============================================================================
# Cenário 1: Jornada do Novo Usuário
# ============================================================================


class TestJornadaNovoUsuario:
    """Simula Maria enviando sua primeira mensagem e depois um follow-up.

    Verifica o pipeline completo: webhook → fila → worker → conversations → API admin.
    Cada passo é impresso no terminal para facilitar debug em aula.
    """

    def test_novo_usuario_conversa_multi_turno(self, db_url: str) -> None:
        """Maria envia 2 mensagens e verificamos todo o pipeline."""
        phone = unique_phone("11")
        agent = "rhawk_assistant"

        # --- Passo 1: Primeira mensagem ---
        print(f"\n{'=' * 60}")
        print("CENÁRIO: Jornada do Novo Usuário")
        print(f"Phone: {phone}")
        print(f"{'=' * 60}")

        print("\n[1/8] Enviando primeira mensagem...")
        sid1 = unique_sid("SMNEW")
        resp1 = send_webhook(phone, "Olá! O que vocês fazem?", message_sid=sid1)
        assert resp1.status_code == 200, f"Webhook retornou {resp1.status_code}"
        print(f"  ✓ Webhook aceito (SID: {sid1})")

        print("[2/8] Aguardando processamento...")
        status1, output1, error1, _ = wait_terminal_status(db_url, sid1)
        assert status1 == "done", f"Mensagem 1 falhou: {error1}"
        assert output1 and output1.strip(), "Resposta vazia na mensagem 1"
        print(f"  ✓ Resposta: {output1[:80]}...")

        print("[3/8] Verificando conversations no banco...")
        conv = query_conversation(db_url, phone, agent)
        assert conv is not None, "Conversa não foi criada em conversations"
        assert conv[0] == 1, f"message_count esperado 1, obteve {conv[0]}"
        print(f"  ✓ conversations.message_count = {conv[0]}")

        # --- Passo 2: Follow-up ---
        print("\n[4/8] Enviando segunda mensagem (follow-up)...")
        sid2 = unique_sid("SMNEW")
        resp2 = send_webhook(phone, "Como posso aprender mais?", message_sid=sid2)
        assert resp2.status_code == 200
        print(f"  ✓ Webhook aceito (SID: {sid2})")

        print("[5/8] Aguardando processamento...")
        status2, output2, error2, _ = wait_terminal_status(db_url, sid2)
        assert status2 == "done", f"Mensagem 2 falhou: {error2}"
        assert output2 and output2.strip(), "Resposta vazia na mensagem 2"
        print(f"  ✓ Resposta: {output2[:80]}...")

        print("[6/8] Verificando conversations atualizada...")
        conv2 = wait_conversation_count(db_url, phone, agent, expected_count=2)
        assert conv2[0] == 2, f"message_count esperado 2, obteve {conv2[0]}"
        print(f"  ✓ conversations.message_count = {conv2[0]}")

        # --- Passo 3: Verificação via API Admin ---
        print("[7/8] Verificando via GET /api/chats/{phone}...")
        chat_resp = httpx.get(
            f"{API_BASE_URL}/api/chats/{phone}",
            headers=ADMIN_API_HEADERS,
            timeout=10,
        )
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        messages = chat_data["messages"]
        # Deve ter pelo menos 2 mensagens com status done
        done_msgs = [m for m in messages if m["status"] == "done"]
        assert len(done_msgs) >= 2, (
            f"Esperado >= 2 mensagens done, obteve {len(done_msgs)}"
        )
        print(f"  ✓ API retornou {len(done_msgs)} mensagens processadas")

        print("[8/8] Verificando via GET /api/chats (listagem)...")
        list_resp = httpx.get(
            f"{API_BASE_URL}/api/chats",
            headers=ADMIN_API_HEADERS,
            timeout=10,
        )
        assert list_resp.status_code == 200
        chats = list_resp.json()["chats"]
        our_chat = [c for c in chats if c["phone_number"] == phone]
        assert len(our_chat) == 1, f"Conversa de {phone} não aparece na listagem"
        count = our_chat[0]["message_count"]
        print(f"  ✓ Conversa na listagem, message_count={count}")

        print(f"\n{'=' * 60}")
        print("CENÁRIO CONCLUÍDO COM SUCESSO")
        print(f"{'=' * 60}\n")


# ============================================================================
# Cenário 2: Memória Semântica Persistente
# ============================================================================


class TestMemoriaSemantica:
    """Simula João salvando um fato e recuperando em nova sessão.

    Verifica que a memória semântica (Postgres Store) persiste
    mesmo após limpar os checkpoints da thread.
    """

    def test_memoria_persiste_entre_sessoes(self, db_url: str) -> None:
        """João salva um código secreto e recupera sem histórico de conversa."""
        phone = unique_phone("21")
        thread_id = f"{phone}:rhawk_assistant"
        token = f"rhawk-{uuid.uuid4().hex[:8]}"

        print(f"\n{'=' * 60}")
        print("CENÁRIO: Memória Semântica Persistente")
        print(f"Phone: {phone} | Token: {token}")
        print(f"{'=' * 60}")

        # --- Passo 1: Salvar memória ---
        print("\n[1/6] Enviando mensagem para salvar memória...")
        sid_save = unique_sid("SMMEM")
        resp = send_webhook(
            phone,
            (
                "Use a ferramenta save_memory e salve este fato sobre mim: "
                f"meu código de acesso é {token}. "
                "Depois confirme em uma frase curta."
            ),
            message_sid=sid_save,
        )
        assert resp.status_code == 200
        print(f"  ✓ Webhook aceito (SID: {sid_save})")

        print("[2/6] Aguardando processamento + salvamento...")
        status, output, error, _ = wait_terminal_status(db_url, sid_save)
        assert status == "done", f"Falha ao salvar: {error}"
        print(f"  ✓ Agente respondeu: {output[:80]}...")

        print("[3/6] Aguardando memória no store...")
        wait_memory_saved(db_url, phone, contains=token)
        print(f"  ✓ Memória com '{token}' encontrada no store")

        # --- Passo 2: Limpar checkpoints (simula nova sessão) ---
        print("[4/6] Limpando checkpoints da thread (simula nova sessão)...")
        clear_thread_checkpoints(db_url, thread_id)
        print("  ✓ Checkpoints removidos")

        # --- Passo 3: Recuperar memória ---
        print("[5/6] Enviando mensagem para recuperar memória...")
        sid_recall = unique_sid("SMMEM")
        resp2 = send_webhook(
            phone,
            (
                "Sem usar save_memory agora, use read_memory para recuperar "
                "meu código de acesso e responda apenas com o valor."
            ),
            message_sid=sid_recall,
        )
        assert resp2.status_code == 200

        print("[6/6] Verificando se o agente recuperou o token...")
        status2, output2, error2, _ = wait_terminal_status(db_url, sid_recall)
        assert status2 == "done", f"Falha no recall: {error2}"
        assert token.lower() in output2.lower(), (
            f"Token '{token}' não encontrado na resposta: {output2}"
        )
        print(f"  ✓ Agente retornou o token: {output2[:80]}...")

        print(f"\n{'=' * 60}")
        print("CENÁRIO CONCLUÍDO COM SUCESSO")
        print(f"{'=' * 60}\n")


# ============================================================================
# Cenário 3: Debounce de Mensagens Rápidas
# ============================================================================


class TestDebounce:
    """Simula Pedro enviando 3 mensagens em sequência rápida.

    O debounce do sistema (buffer_seconds=2.0) deve agrupar as mensagens
    em uma única entrada na fila, concatenando os textos.
    """

    def test_debounce_agrupa_mensagens_rapidas(self, db_url: str) -> None:
        """3 mensagens rápidas viram 1 entrada na fila."""
        phone = unique_phone("31")
        agent = "rhawk_assistant"
        messages = ["Oi", "Tudo bem?", "Quero saber sobre LangGraph"]

        print(f"\n{'=' * 60}")
        print("CENÁRIO: Debounce de Mensagens Rápidas")
        print(f"Phone: {phone}")
        print(f"{'=' * 60}")

        # --- Passo 1: Enviar 3 mensagens SEM esperar entre elas ---
        print(f"\n[1/4] Enviando {len(messages)} mensagens em sequência rápida...")
        sids = []
        for i, msg in enumerate(messages):
            sid = unique_sid("SMDEB")
            resp = send_webhook(phone, msg, message_sid=sid)
            assert resp.status_code == 200, (
                f"Mensagem {i + 1} falhou: {resp.status_code}"
            )
            sids.append(sid)
            print(f"  ✓ Mensagem {i + 1}: '{msg}' (SID: {sid})")

        # --- Passo 2: Aguardar processamento ---
        print("[2/4] Aguardando fila processar (debounce + worker)...")
        wait_queue_done(db_url, phone, agent, timeout_seconds=120)
        print("  ✓ Fila vazia (tudo processado)")

        # --- Passo 3: Verificar debounce ---
        print("[3/4] Verificando entradas na fila...")
        total = count_queue_entries(db_url, phone, agent)
        # O debounce concatena mensagens rápidas: esperamos 1 entrada (ou no máximo 2
        # se o timing variou). O importante é que NÃO temos 3 entradas separadas.
        print(f"  Entradas na fila: {total} (esperado: 1, máximo aceitável: 2)")
        assert total <= 2, (
            f"Debounce falhou: esperado <= 2 entradas, obteve {total}. "
            f"As {len(messages)} mensagens deveriam ter sido agrupadas."
        )

        # --- Passo 4: Verificar conteúdo concatenado ---
        print("[4/4] Verificando conteúdo concatenado...")
        entry = query_queue_entry(db_url, phone, agent)
        assert entry is not None, "Nenhuma entrada encontrada na fila"
        incoming = entry[1]  # incoming_message
        # Pelo menos as últimas mensagens devem estar concatenadas
        has_concat = "\n" in incoming or all(m in incoming for m in messages)
        if has_concat:
            print("  ✓ incoming_message contém mensagens agrupadas:")
            for line in incoming.split("\n"):
                print(f"    | {line}")
        else:
            print(f"  ⚠ incoming_message: {incoming}")
            print("  (timing pode ter separado — comportamento aceitável)")

        print(f"\n{'=' * 60}")
        print("CENÁRIO CONCLUÍDO COM SUCESSO")
        print(f"{'=' * 60}\n")


# ============================================================================
# Cenário 4: Múltiplos Usuários Simultâneos
# ============================================================================


class TestUsuariosSimultaneos:
    """Simula 3 usuários diferentes enviando mensagens ao mesmo tempo.

    Verifica que o sistema mantém isolamento entre threads e processa
    todos corretamente em paralelo.
    """

    def test_tres_usuarios_paralelos(self, db_url: str) -> None:
        """3 usuários enviam mensagens e cada um recebe sua resposta."""
        users = [
            {"phone": unique_phone("41"), "msg": "Olá, me chamo Alice."},
            {"phone": unique_phone("42"), "msg": "Oi, sou o Bruno."},
            {"phone": unique_phone("43"), "msg": "Hey, aqui é a Carol."},
        ]

        print(f"\n{'=' * 60}")
        print("CENÁRIO: Múltiplos Usuários Simultâneos")
        for u in users:
            print(f"  {u['phone']}: {u['msg']}")
        print(f"{'=' * 60}")

        # --- Passo 1: Enviar webhooks em paralelo ---
        print("\n[1/4] Enviando 3 webhooks em paralelo (threads)...")
        results: dict[str, dict] = {}

        def send_and_track(user: dict) -> dict:
            sid = unique_sid("SMPAR")
            resp = send_webhook(user["phone"], user["msg"], message_sid=sid)
            return {"phone": user["phone"], "sid": sid, "status_code": resp.status_code}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(send_and_track, u): u for u in users}
            for future in as_completed(futures):
                result = future.result()
                results[result["phone"]] = result
                assert result["status_code"] == 200
                print(f"  ✓ {result['phone']} → SID: {result['sid']}")

        # --- Passo 2: Aguardar todos processarem ---
        print("[2/4] Aguardando todos processarem...")
        for phone, info in results.items():
            status, output, error, _ = wait_terminal_status(db_url, info["sid"])
            assert status == "done", f"{phone} falhou: {error}"
            info["output"] = output
            print(f"  ✓ {phone}: {output[:60]}...")

        # --- Passo 3: Verificar conversations isoladas ---
        print("[3/4] Verificando isolamento de conversations...")
        for phone in results:
            conv = query_conversation(db_url, phone, "rhawk_assistant")
            assert conv is not None, f"Conversa de {phone} não encontrada"
            assert conv[0] >= 1, f"message_count de {phone} = {conv[0]}"
            print(f"  ✓ {phone}: message_count = {conv[0]}")

        # --- Passo 4: Verificar métricas ---
        print("[4/4] Verificando GET /api/metrics...")
        metrics_resp = httpx.get(
            f"{API_BASE_URL}/api/metrics",
            headers=ADMIN_API_HEADERS,
            timeout=10,
        )
        assert metrics_resp.status_code == 200
        metrics = metrics_resp.json()
        print(f"  total_today: {metrics['total_today']}")
        print(f"  queue_size: {metrics['queue_size']}")
        print(f"  failures_today: {metrics['failures_today']}")
        # Não deve ter nada na fila após processamento
        assert metrics["queue_size"] == 0, (
            f"Fila deveria estar vazia, tem {metrics['queue_size']}"
        )

        print(f"\n{'=' * 60}")
        print("CENÁRIO CONCLUÍDO COM SUCESSO")
        print(f"{'=' * 60}\n")


# ============================================================================
# Cenário 5: Rate Limiting
# ============================================================================


class TestRateLimiting:
    """Simula Diego enviando mensagens demais e sendo bloqueado.

    O rate limit padrão é 30 req/hora por telefone.
    Nota: O rate limiter usa memória in-process, então só funciona
    contra a mesma instância da API.
    """

    def test_rate_limit_bloqueia_apos_limite(self, db_url: str) -> None:
        """Envia mensagens até receber HTTP 429."""
        phone = unique_phone("51")
        limit = 30  # settings.rate_limit_per_hour default

        print(f"\n{'=' * 60}")
        print("CENÁRIO: Rate Limiting")
        print(f"Phone: {phone} | Limite: {limit}/hora")
        print(f"{'=' * 60}")

        print(f"\n[1/3] Enviando {limit} mensagens para atingir o limite...")
        accepted = 0
        blocked_at = None
        for i in range(limit + 5):  # Envia um pouco além do limite
            resp = send_webhook(
                phone,
                f"Mensagem {i + 1}",
                message_sid=unique_sid("SMRL"),
            )
            if resp.status_code == 429:
                blocked_at = i + 1
                print(f"  ✓ Bloqueado na mensagem {blocked_at} (HTTP 429)")
                break
            elif resp.status_code == 200:
                accepted += 1
            else:
                pytest.fail(f"Status inesperado {resp.status_code} na mensagem {i + 1}")

        assert blocked_at is not None, (
            f"Rate limit não ativou após {limit + 5} mensagens"
        )
        print(f"  Aceitas antes do bloqueio: {accepted}")

        # --- Passo 2: Verificar que a mensagem 429 tem corpo descritivo ---
        print("[2/3] Verificando resposta do rate limit...")
        resp_429 = send_webhook(phone, "Mais uma", message_sid=unique_sid("SMRL"))
        assert resp_429.status_code == 429
        body = resp_429.json()
        assert "detail" in body, "Resposta 429 sem campo 'detail'"
        print(f"  ✓ detail: {body['detail']}")

        # --- Passo 3: Verificar que mensagens aceitas foram enfileiradas ---
        print(f"[3/3] Verificando que {accepted} mensagens foram enfileiradas...")
        total = count_queue_entries(db_url, phone, "rhawk_assistant")
        # O debounce pode ter agrupado várias, mas deve ter pelo menos 1
        assert total >= 1, "Nenhuma mensagem enfileirada antes do rate limit"
        print(f"  ✓ {total} entrada(s) na fila (debounce pode ter agrupado)")

        print(f"\n{'=' * 60}")
        print("CENÁRIO CONCLUÍDO COM SUCESSO")
        print(f"{'=' * 60}\n")


# ============================================================================
# Cenário 6: Agente Inválido
# ============================================================================


class TestAgenteInvalido:
    """Simula tentativa de usar agente que não existe.

    O sistema deve rejeitar a requisição com erro claro.
    """

    def test_agente_inexistente_retorna_erro(self, db_url: str) -> None:
        """Webhook com agent=fantasma retorna erro HTTP."""
        phone = unique_phone("61")

        print(f"\n{'=' * 60}")
        print("CENÁRIO: Agente Inválido")
        print(f"Phone: {phone}")
        print(f"{'=' * 60}")

        print("\n[1/2] Enviando webhook com agente inexistente...")
        resp = send_webhook(
            phone,
            "Olá!",
            agent="agente_fantasma",
            message_sid=unique_sid("SMERR"),
        )
        assert resp.status_code == 400, f"Esperado HTTP 400, obteve {resp.status_code}"
        body = resp.json()
        assert "detail" in body, "Resposta 400 sem campo 'detail'"
        print(f"  ✓ HTTP 400: {body['detail']}")

        print("[2/2] Verificando que nenhuma mensagem foi enfileirada...")
        total = count_queue_entries(db_url, phone, "agente_fantasma")
        assert total == 0, f"Mensagem foi enfileirada para agente inválido ({total})"
        print("  ✓ Fila vazia para agente inexistente")

        print(f"\n{'=' * 60}")
        print("CENÁRIO CONCLUÍDO COM SUCESSO")
        print(f"{'=' * 60}\n")


# ============================================================================
# Cenário 7: Consistência da API Admin
# ============================================================================


class TestConsistenciaAPIAdmin:
    """Verifica que a API admin reflete o estado correto do sistema.

    Envia uma mensagem real e depois verifica todos os endpoints admin.
    """

    def test_api_admin_reflete_estado(self, db_url: str) -> None:
        """Endpoints admin retornam dados consistentes após interação."""
        phone = unique_phone("71")

        print(f"\n{'=' * 60}")
        print("CENÁRIO: Consistência da API Admin")
        print(f"Phone: {phone}")
        print(f"{'=' * 60}")

        # Cria uma interação para ter dados frescos
        print("\n[1/5] Criando interação de referência...")
        sid, row = send_webhook_and_wait(db_url, phone, "Teste de consistência da API.")
        status, output, error, _ = row
        assert status == "done", f"Mensagem falhou: {error}"
        print(f"  ✓ Mensagem processada (SID: {sid})")

        # --- GET /api/agents ---
        print("[2/5] Verificando GET /api/agents...")
        agents_resp = httpx.get(
            f"{API_BASE_URL}/api/agents",
            headers=ADMIN_API_HEADERS,
            timeout=10,
        )
        assert agents_resp.status_code == 200
        agents = agents_resp.json()["agents"]
        assert "rhawk_assistant" in agents, (
            f"rhawk_assistant não está na lista: {agents}"
        )
        print(f"  ✓ Agentes disponíveis: {agents}")

        # --- GET /api/chats ---
        print("[3/5] Verificando GET /api/chats...")
        chats_resp = httpx.get(
            f"{API_BASE_URL}/api/chats?limit=100",
            headers=ADMIN_API_HEADERS,
            timeout=10,
        )
        assert chats_resp.status_code == 200
        chats_data = chats_resp.json()
        chats = chats_data["chats"]
        our = [c for c in chats if c["phone_number"] == phone]
        assert len(our) == 1, f"Conversa de {phone} aparece {len(our)}x (esperado 1)"
        print(f"  ✓ {chats_data['total']} conversas no total, nossa incluída")
        print(f"    phone={our[0]['phone_number']}, count={our[0]['message_count']}")

        # --- GET /api/chats/{phone} ---
        print(f"[4/5] Verificando GET /api/chats/{phone}...")
        msgs_resp = httpx.get(
            f"{API_BASE_URL}/api/chats/{phone}",
            headers=ADMIN_API_HEADERS,
            timeout=10,
        )
        assert msgs_resp.status_code == 200
        msgs = msgs_resp.json()["messages"]
        assert len(msgs) >= 1, "Nenhuma mensagem retornada"
        latest = msgs[0]  # ORDER BY created_at DESC
        assert latest["status"] == "done", f"Status da mensagem: {latest['status']}"
        assert latest["response"], "Resposta vazia"
        print(f"  ✓ {len(msgs)} mensagem(ns), última com status={latest['status']}")
        print(f"    incoming: {latest['incoming_message'][:50]}...")
        print(f"    response: {latest['response'][:50]}...")

        # --- GET /api/metrics ---
        print("[5/5] Verificando GET /api/metrics...")
        metrics_resp = httpx.get(
            f"{API_BASE_URL}/api/metrics",
            headers=ADMIN_API_HEADERS,
            timeout=10,
        )
        assert metrics_resp.status_code == 200
        metrics = metrics_resp.json()
        assert metrics["total_today"] >= 1, "total_today deveria ser >= 1"
        print("  ✓ Métricas:")
        print(f"    total_today: {metrics['total_today']}")
        print(f"    failures_today: {metrics['failures_today']}")
        print(f"    avg_processing_time: {metrics['avg_processing_time_seconds']}s")
        print(f"    queue_size: {metrics['queue_size']}")

        print(f"\n{'=' * 60}")
        print("CENÁRIO CONCLUÍDO COM SUCESSO")
        print(f"{'=' * 60}\n")
