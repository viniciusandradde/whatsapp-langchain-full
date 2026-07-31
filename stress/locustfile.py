"""Cenários de stress test para a API WhatsApp LangChain.

Bate no webhook inbound da **Evolution API** (`/webhook/evolution`) — payload
JSON (`event/instance/data.{key,message,pushName,messageTimestamp}`). Sem
assinatura por padrão; opcionalmente com header `apikey` se
`EVOLUTION_VALIDATE_APIKEY=true` na API.

Havia um segundo alvo, o `/webhook/twilio`, que saiu junto com o Twilio (ver
migration 153). Se um dia entrar outro provider, o molde é este arquivo: um
par de classes (normal + rajada) e um `_PATH` próprio.

Variáveis de ambiente:

| Variável | Default | Descrição |
|---|---|---|
| `EVOLUTION_INSTANCE_NAME` | `vsa-tecnologia` | Nome da instância no campo `instance` do payload |
| `EVOLUTION_API_KEY` | `""` | Header `apikey` (só usado se a API exigir) |

Uso:

    cd stress
    uv venv && source .venv/bin/activate
    uv pip install -r requirements.txt
    locust -f locustfile.py --host https://api.vsanexus.com
"""

from dotenv import load_dotenv

load_dotenv()

import json
import os
import random
import time
import uuid

from faker import Faker
from locust import HttpUser, between, task

fake = Faker("pt_BR")

# --- Configuração via ambiente ---

EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE_NAME", "vsa-tecnologia")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "")
EVOLUTION_PATH = "/webhook/evolution"


# --- Helpers Evolution ---


def make_evolution_payload(body: str, phone: str) -> dict:
    """Payload JSON compatível com webhook Evolution v2 (MESSAGES_UPSERT)."""
    digits = phone.lstrip("+")
    return {
        "event": "messages.upsert",
        "instance": EVOLUTION_INSTANCE,
        "data": {
            "key": {
                "remoteJid": f"{digits}@s.whatsapp.net",
                "fromMe": False,
                "id": f"STRESS-{uuid.uuid4().hex[:24]}",
            },
            "message": {"conversation": body},
            "pushName": "Stress Test",
            "messageTimestamp": int(time.time()),
        },
    }


def evolution_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if EVOLUTION_API_KEY:
        headers["apikey"] = EVOLUTION_API_KEY
    return headers


# --- Evolution: cenário normal ---


class EvolutionWebhookUser(HttpUser):
    """Usuário Evolution típico (MESSAGES_UPSERT JSON, mensagens variadas)."""

    wait_time = between(1, 3)
    weight = 1

    def on_start(self) -> None:
        self.phone = f"+55{fake.msisdn()[4:]}"

    def send_message(self, body: str) -> None:
        payload = make_evolution_payload(body, self.phone)
        self.client.post(
            EVOLUTION_PATH,
            data=json.dumps(payload),
            headers=evolution_headers(),
            name="POST /webhook/evolution (normal)",
        )

    @task(10)
    def send_normal_message(self) -> None:
        body = fake.sentence(nb_words=fake.random_int(min=3, max=15))
        self.send_message(body)

    @task(1)
    def send_long_message(self) -> None:
        body = fake.paragraph(nb_sentences=10)
        self.send_message(body)


class EvolutionBurstUser(HttpUser):
    """Evolution com rajadas (testa debounce e crescimento da fila)."""

    wait_time = between(5, 15)
    weight = 1

    def on_start(self) -> None:
        self.phone = f"+55{fake.msisdn()[4:]}"

    @task
    def send_burst(self) -> None:
        burst_size = random.randint(5, 20)
        for i in range(burst_size):
            body = fake.sentence(nb_words=fake.random_int(min=2, max=10))
            payload = make_evolution_payload(body, self.phone)
            self.client.post(
                EVOLUTION_PATH,
                data=json.dumps(payload),
                headers=evolution_headers(),
                name="POST /webhook/evolution (burst)",
            )
            if i < burst_size - 1:
                time.sleep(random.uniform(0.1, 0.5))
