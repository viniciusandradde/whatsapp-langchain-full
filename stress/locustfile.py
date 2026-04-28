"""Cenarios de stress test para a API WhatsApp LangChain.

Usa Locust para simular multiplos usuarios enviando mensagens via webhook
do Twilio. Cada request e assinado com HMAC-SHA1 para passar pela validacao
de seguranca da API (mesma logica que o Twilio usa em producao).

Variaveis de ambiente necessarias:
    TWILIO_AUTH_TOKEN: Token de autenticacao do Twilio (mesmo configurado na API).
    TWILIO_WEBHOOK_URL: URL base para computo da assinatura.
                        Ex: http://localhost:8000 ou URL do Railway.

Uso:
    cd stress
    uv venv && source .venv/bin/activate
    uv pip install -r requirements.txt
    locust
"""

from dotenv import load_dotenv

# Carrega .env do diretório stress/ (se existir)
load_dotenv()

import base64
import hashlib
import hmac
import os
import random
import time
import uuid

from faker import Faker
from locust import HttpUser, between, task

# Faker com locale pt_BR para gerar dados realistas em portugues
fake = Faker("pt_BR")

# --- Configuracao via variaveis de ambiente ---

# Token de autenticacao do Twilio — necessario para gerar assinaturas validas.
# Deve ser o MESMO token configurado na API (TWILIO_AUTH_TOKEN).
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")

# URL base do webhook — usada para montar a URL completa na assinatura.
# Atras de proxy/tunel, a URL publica difere do host interno do Locust.
WEBHOOK_URL = os.environ.get("TWILIO_WEBHOOK_URL", "http://localhost:8000")

# Endpoint do webhook com o agente padrao
WEBHOOK_PATH = "/webhook/twilio?agent=rhawk_assistant"


def generate_twilio_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Gera assinatura X-Twilio-Signature valida para testes de stress.

    O algoritmo segue exatamente o que o Twilio faz em producao:
    1. Comeca com a URL completa do webhook (incluindo query params)
    2. Ordena os parametros POST alfabeticamente por chave
    3. Concatena cada par chave+valor a URL (sem separadores)
    4. Assina a string resultante com HMAC-SHA1 usando o auth token
    5. Codifica o resultado em Base64

    Isso permite que nossos testes passem pela validacao de assinatura
    sem precisar desativa-la, simulando trafego realista.

    Args:
        url: URL completa do webhook (ex: http://localhost:8000/webhook/twilio?agent=rhawk_assistant).
        params: Parametros POST do formulario (Body, From, To, etc.).
        auth_token: Token de autenticacao do Twilio.

    Returns:
        Assinatura Base64 compativel com X-Twilio-Signature.
    """
    # Monta a string de dados: URL + params ordenados concatenados
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]

    # HMAC-SHA1 com o auth token como chave
    # Twilio usa SHA1 por razoes historicas — suficiente para validacao de webhook
    signature = hmac.new(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    return base64.b64encode(signature).decode("utf-8")


def build_webhook_url() -> str:
    """Monta a URL completa do webhook para computo da assinatura.

    A URL deve incluir o path E os query params, pois o Twilio
    inclui tudo isso no calculo da assinatura.

    Returns:
        URL completa (ex: http://localhost:8000/webhook/twilio?agent=rhawk_assistant).
    """
    base = WEBHOOK_URL.rstrip("/")
    return f"{base}{WEBHOOK_PATH}"


def make_twilio_payload(body: str, phone: str) -> dict[str, str]:
    """Cria payload no formato que o Twilio envia para webhooks.

    Simula os campos que o Twilio inclui em cada POST ao webhook:
    - MessageSid: ID unico da mensagem (geramos um UUID)
    - From: Numero do remetente no formato whatsapp:+XXXXXXXXXXX
    - To: Numero do bot (fixo para testes)
    - Body: Texto da mensagem
    - NumMedia: Quantidade de midias anexas (sempre 0 nos testes de texto)

    Args:
        body: Texto da mensagem.
        phone: Numero de telefone no formato E.164 (ex: +5511999999999).

    Returns:
        Dicionario com os campos do formulario Twilio.
    """
    return {
        "MessageSid": f"SM{uuid.uuid4().hex[:32]}",
        "From": f"whatsapp:{phone}",
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": "0",
    }


class TwilioWebhookUser(HttpUser):
    """Simula um usuario do WhatsApp enviando mensagens via webhook Twilio.

    Cada instancia representa um numero de telefone unico (gerado via Faker)
    que envia mensagens com intervalos de 1 a 3 segundos.

    Dois cenarios com pesos diferentes:
    - Mensagem normal (peso 10): frases curtas, simula conversa casual
    - Mensagem longa (peso 1): paragrafos extensos, testa limites de texto

    A base esta preparada para ser estendida com cenarios adicionais:
    - INT-187: cenario assincrono (webhook async)
    - INT-188: cenario sincrono (webhook sync)
    - INT-189: cenario de burst (rajada de mensagens)
    """

    # Intervalo entre requisicoes: 1 a 3 segundos (simula digitacao humana)
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Configuracao inicial de cada usuario virtual.

        Gera um numero de telefone brasileiro unico para este usuario,
        garantindo que cada instancia do Locust simule um remetente diferente.
        """
        # Gera numero brasileiro unico no formato E.164
        self.phone = f"+55{fake.msisdn()[4:]}"

        if not AUTH_TOKEN:
            # Alerta visivel no log — sem token, a API vai rejeitar com 403
            print(
                "[AVISO] TWILIO_AUTH_TOKEN nao configurado. "
                "Requests serao rejeitados se a validacao de assinatura estiver ativa."
            )

    def send_message(self, body: str) -> None:
        """Envia uma mensagem para o webhook com assinatura Twilio valida.

        Monta o payload, gera a assinatura HMAC-SHA1 e faz o POST.
        Esse metodo centraliza a logica de envio para todos os cenarios.

        Args:
            body: Texto da mensagem a enviar.
        """
        url = build_webhook_url()
        params = make_twilio_payload(body, self.phone)
        signature = generate_twilio_signature(url, params, AUTH_TOKEN)

        self.client.post(
            WEBHOOK_PATH,
            data=params,
            headers={"X-Twilio-Signature": signature},
        )

    @task(10)
    def send_normal_message(self) -> None:
        """Envia mensagem curta — simula conversa casual do dia a dia.

        Peso 10: este e o cenario mais comum. Gera frases de 3 a 15 palavras,
        representando perguntas rapidas ou respostas curtas tipicas do WhatsApp.
        """
        word_count = fake.random_int(min=3, max=15)
        body = fake.sentence(nb_words=word_count)
        self.send_message(body)

    @task(1)
    def send_long_message(self) -> None:
        """Envia mensagem longa — testa processamento de textos extensos.

        Peso 1: cenario menos frequente. Gera paragrafo com ~10 frases,
        simulando usuarios que enviam textos longos de uma vez.
        Util para testar limites de tamanho e tempo de processamento.
        """
        body = fake.paragraph(nb_sentences=10)
        self.send_message(body)


# --- Cenario de rajada (burst) ---


class BurstUser(HttpUser):
    """Simula rajadas de mensagens rapidas no webhook async.

    Testa o comportamento do sistema quando um usuario envia muitas mensagens
    em sequencia rapida (ex: copia e cola varias linhas, ou envia mensagens
    freneticas). Esse padrao e comum no WhatsApp e estressa especificamente:

    - Rate limiting: o sistema deve rejeitar ou enfileirar sem perder mensagens
    - Crescimento da fila: muitas mensagens entram de uma vez, o worker precisa
      drenar a fila sem acumular backlog indefinidamente
    - Debounce: se houver logica de agrupamento, ela deve funcionar sob pressao
    - Estabilidade do banco: muitas escritas simultaneas no PostgreSQL

    O padrao e: rajada de 5-20 mensagens rapidas (0.1-0.5s entre cada),
    depois pausa de 5-15 segundos antes da proxima rajada.
    """

    # Pausa ENTRE rajadas: 5 a 15 segundos para o sistema respirar
    wait_time = between(5, 15)

    # Peso padrao — gera trafego comparavel ao TwilioWebhookUser
    weight = 1

    def on_start(self) -> None:
        """Gera numero de telefone unico para este usuario virtual."""
        self.phone = f"+55{fake.msisdn()[4:]}"

        if not AUTH_TOKEN:
            print(
                "[AVISO] TWILIO_AUTH_TOKEN nao configurado. "
                "Requests do BurstUser serao rejeitados se a validacao estiver ativa."
            )

    @task
    def send_burst(self) -> None:
        """Envia rajada de 5-20 mensagens com intervalo minimo entre elas.

        Cada mensagem e assinada individualmente (assim como o Twilio faria).
        O intervalo entre mensagens dentro da rajada e de 0.1 a 0.5 segundos,
        simulando um usuario digitando/colando rapidamente.

        Apos a rajada, o Locust aplica o wait_time (5-15s) automaticamente
        antes de chamar send_burst novamente.
        """
        burst_size = random.randint(5, 20)

        for i in range(burst_size):
            word_count = fake.random_int(min=2, max=10)
            body = fake.sentence(nb_words=word_count)

            url = build_webhook_url()
            params = make_twilio_payload(body, self.phone)
            signature = generate_twilio_signature(url, params, AUTH_TOKEN)

            self.client.post(
                WEBHOOK_PATH,
                data=params,
                headers={"X-Twilio-Signature": signature},
            )

            # Pequena pausa entre mensagens da rajada (0.1 a 0.5s)
            # Simula a velocidade de digitacao/colagem rapida
            if i < burst_size - 1:
                time.sleep(random.uniform(0.1, 0.5))
