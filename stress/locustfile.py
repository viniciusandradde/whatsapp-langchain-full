"""Cenários de stress test para a API WhatsApp LangChain.

Suporta dois providers de webhook inbound:

- **Twilio** (`/webhook/twilio`) — payload form-urlencoded com assinatura
  HMAC-SHA1 via header `X-Twilio-Signature`. Validação de assinatura
  controlada por `VALIDATE_TWILIO_SIGNATURE` na API.

- **Evolution API** (`/webhook/evolution`) — payload JSON
  (`event/instance/data.{key,message,pushName,messageTimestamp}`).
  Sem assinatura por padrão; opcionalmente com header `apikey` se
  `EVOLUTION_VALIDATE_APIKEY=true` na API.

Selecione qual provider rodar via `LOCUST_PROVIDER`:

- `twilio` — só usuários Twilio (default, compat com legado)
- `evolution` — só usuários Evolution
- `both` — usuários dos dois providers ao mesmo tempo

Variáveis de ambiente:

| Variável | Default | Descrição |
|---|---|---|
| `LOCUST_PROVIDER` | `twilio` | `twilio` / `evolution` / `both` |
| `TWILIO_AUTH_TOKEN` | `""` | Token Twilio pra assinar requests |
| `TWILIO_WEBHOOK_URL` | `http://localhost:8000` | URL base do webhook Twilio (usado no cálculo da assinatura) |
| `EVOLUTION_INSTANCE_NAME` | `vsa-tecnologia` | Nome da instância no campo `instance` do payload |
| `EVOLUTION_API_KEY` | `""` | Header `apikey` (só usado se a API exigir) |

Uso:

    cd stress
    uv venv && source .venv/bin/activate
    uv pip install -r requirements.txt
    LOCUST_PROVIDER=evolution locust -f locustfile.py --host https://api.vsanexus.com
"""

from dotenv import load_dotenv

load_dotenv()

import base64
import hashlib
import hmac
import json
import os
import random
import time
import uuid

from faker import Faker
from locust import HttpUser, between, task

fake = Faker("pt_BR")

# --- Configuração via ambiente ---

PROVIDER = os.environ.get("LOCUST_PROVIDER", "twilio").lower()
if PROVIDER not in ("twilio", "evolution", "both"):
    raise ValueError(
        f"LOCUST_PROVIDER inválido: {PROVIDER!r}. Use twilio|evolution|both."
    )

# Twilio
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WEBHOOK_URL = os.environ.get("TWILIO_WEBHOOK_URL", "http://localhost:8000")
TWILIO_PATH = "/webhook/twilio?agent=vsa_tech"

# Evolution
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE_NAME", "vsa-tecnologia")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "")
EVOLUTION_PATH = "/webhook/evolution"


# --- Helpers Twilio ---


def generate_twilio_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Gera X-Twilio-Signature válida (HMAC-SHA1 sobre URL + params ordenados)."""
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    signature = hmac.new(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(signature).decode("utf-8")


def build_twilio_url() -> str:
    return f"{TWILIO_WEBHOOK_URL.rstrip('/')}{TWILIO_PATH}"


def make_twilio_payload(body: str, phone: str) -> dict[str, str]:
    """Payload form-urlencoded compatível com webhook Twilio."""
    return {
        "MessageSid": f"SM{uuid.uuid4().hex[:32]}",
        "From": f"whatsapp:{phone}",
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": "0",
    }


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


# --- Twilio: cenário normal ---


class TwilioWebhookUser(HttpUser):
    """Usuário Twilio típico (mensagens curtas + esporádicas longas)."""

    wait_time = between(1, 3)
    weight = 1

    def on_start(self) -> None:
        self.phone = f"+55{fake.msisdn()[4:]}"
        if not TWILIO_AUTH_TOKEN:
            print(
                "[AVISO Twilio] TWILIO_AUTH_TOKEN não configurado — "
                "requests serão rejeitados se VALIDATE_TWILIO_SIGNATURE=true."
            )

    def send_message(self, body: str) -> None:
        url = build_twilio_url()
        params = make_twilio_payload(body, self.phone)
        signature = generate_twilio_signature(url, params, TWILIO_AUTH_TOKEN)
        self.client.post(
            TWILIO_PATH,
            data=params,
            headers={"X-Twilio-Signature": signature},
            name="POST /webhook/twilio (normal)",
        )

    @task(10)
    def send_normal_message(self) -> None:
        body = fake.sentence(nb_words=fake.random_int(min=3, max=15))
        self.send_message(body)

    @task(1)
    def send_long_message(self) -> None:
        body = fake.paragraph(nb_sentences=10)
        self.send_message(body)


class TwilioBurstUser(HttpUser):
    """Twilio com rajadas de 5-20 mensagens em <1s."""

    wait_time = between(5, 15)
    weight = 1

    def on_start(self) -> None:
        self.phone = f"+55{fake.msisdn()[4:]}"

    @task
    def send_burst(self) -> None:
        burst_size = random.randint(5, 20)
        for i in range(burst_size):
            body = fake.sentence(nb_words=fake.random_int(min=2, max=10))
            url = build_twilio_url()
            params = make_twilio_payload(body, self.phone)
            signature = generate_twilio_signature(url, params, TWILIO_AUTH_TOKEN)
            self.client.post(
                TWILIO_PATH,
                data=params,
                headers={"X-Twilio-Signature": signature},
                name="POST /webhook/twilio (burst)",
            )
            if i < burst_size - 1:
                time.sleep(random.uniform(0.1, 0.5))


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


# --- Filtro de classes pelo PROVIDER ---
# Locust pega todas as subclasses concretas de HttpUser; pra "esconder"
# as que não pertencem ao provider selecionado, sobrescrevemos com classe
# abstract (que o Locust ignora ao spawnar usuários).

if PROVIDER == "twilio":
    EvolutionWebhookUser = type("EvolutionWebhookUser", (HttpUser,), {"abstract": True})
    EvolutionBurstUser = type("EvolutionBurstUser", (HttpUser,), {"abstract": True})
elif PROVIDER == "evolution":
    TwilioWebhookUser = type("TwilioWebhookUser", (HttpUser,), {"abstract": True})
    TwilioBurstUser = type("TwilioBurstUser", (HttpUser,), {"abstract": True})
# else "both": deixa as 4 classes ativas
