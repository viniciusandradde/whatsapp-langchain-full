"""Helper que simula jornada completa de um cliente em 1 setor com 1 modalidade.

Sprint K.2 — base dos testes E2E parametrizados (`test_jornadas_setores.py`).

Sequência:
    1. POST webhook texto curto (`oi`) → recebe welcome menu
    2. POST webhook `"{opcao_numero}"` → recebe transferência + posição na fila +
       agente proativo (via [NOVO_ATENDIMENTO_TRIAGEM] sentinel)
    3. POST webhook com mensagem da modalidade (texto livre OU mídia
       servida pelo media_server local)
    4. Aguarda agente processar — retorna dict com latências, normalized_input
       (transcrição/descrição/extração), response final, agente_atual,
       departamento_id

Cada turno usa MessageSid distinto pra `wait_terminal_status` correlacionar.
Telefones via `unique_phone()` evitam colisão entre runs paralelos.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field

import httpx
import psycopg

from tests.integration.helpers import (
    API_BASE_URL,
    unique_phone,
    unique_sid,
    wait_terminal_status,
)


@dataclass
class TurnoInfo:
    sid: str
    body: str
    inicio: float
    fim: float | None = None
    response: str | None = None
    media_type: str | None = None

    @property
    def latencia_s(self) -> float:
        return (self.fim - self.inicio) if self.fim else -1.0


@dataclass
class JornadaResult:
    """Saída completa da simular_jornada_setor — agregado pra assertivas."""

    setor: dict
    modalidade: str
    phone: str
    turnos: list[TurnoInfo] = field(default_factory=list)
    atendimento_id: int | None = None
    agente_atual: str | None = None
    departamento_id: int | None = None
    normalized_input_modalidade: str | None = None
    response_proativa: str | None = None
    response_final: str | None = None
    erros: list[str] = field(default_factory=list)

    @property
    def latencia_total_s(self) -> float:
        return sum(t.latencia_s for t in self.turnos if t.latencia_s > 0)

    @property
    def passou(self) -> bool:
        return not self.erros

    def to_dict(self) -> dict:
        return {
            "setor": self.setor["slug"],
            "modalidade": self.modalidade,
            "phone": self.phone,
            "atendimento_id": self.atendimento_id,
            "agente_atual": self.agente_atual,
            "departamento_id": self.departamento_id,
            "normalized_input_chars": (
                len(self.normalized_input_modalidade)
                if self.normalized_input_modalidade
                else 0
            ),
            "response_final": (self.response_final or "")[:500],
            "latencia_total_s": round(self.latencia_total_s, 2),
            "turnos": [
                {
                    "sid": t.sid,
                    "body": t.body[:80],
                    "latencia_s": round(t.latencia_s, 2),
                    "response": (t.response or "")[:200],
                }
                for t in self.turnos
            ],
            "erros": self.erros,
        }


def _twilio_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """HMAC-SHA1 do Twilio: URL + sorted(key+value).

    Match exato do que o backend faz via TwilioRequestValidator (oficial).
    """
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    sig = hmac.new(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(sig).decode("utf-8")


def _post_webhook(
    *,
    phone: str,
    body: str,
    sid: str,
    media_url: str | None = None,
    media_content_type: str | None = None,
    timeout: int = 10,
) -> httpx.Response:
    """POST /webhook/twilio com ou sem mídia.

    Em prod, VALIDATE_TWILIO_SIGNATURE=true → exige header X-Twilio-Signature
    HMAC-SHA1 válido. Quando TWILIO_AUTH_TOKEN está setado, gera signature.
    Em dev (TWILIO_AUTH_TOKEN ausente), posta sem header (validation off).
    """
    data: dict[str, str] = {
        "MessageSid": sid,
        "From": f"whatsapp:{phone}",
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": "1" if media_url else "0",
    }
    if media_url:
        data["MediaUrl0"] = media_url
        data["MediaContentType0"] = media_content_type or "image/png"

    url = f"{API_BASE_URL}/webhook/twilio"
    headers: dict[str, str] = {}
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if auth_token:
        headers["X-Twilio-Signature"] = _twilio_signature(url, data, auth_token)

    return httpx.post(url, data=data, headers=headers, timeout=timeout)


def _query_atendimento(db_url: str, phone: str) -> dict | None:
    """Busca último atendimento aberto/fechado do telefone (após menu)."""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.agente_atual, a.departamento_id, a.status,
                   a.classificacao, a.prioridade, a.sentimento, a.resumo_ia
              FROM atendimento a
              JOIN cliente c ON c.id = a.cliente_id
             WHERE c.telefone = %s
               AND a.empresa_id = 1
             ORDER BY a.id DESC LIMIT 1
            """,
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "agente_atual": row[1],
        "departamento_id": row[2],
        "status": row[3],
        "classificacao": row[4],
        "prioridade": row[5],
        "sentimento": row[6],
        "resumo_ia": row[7],
    }


def _query_normalized_input(db_url: str, sid: str) -> tuple[str | None, str | None]:
    """Retorna (normalized_input, media_type) da row do MessageSid."""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT normalized_input, media_type FROM message_queue "
            "WHERE message_id = %s ORDER BY id DESC LIMIT 1",
            (sid,),
        )
        row = cur.fetchone()
    return (row[0] if row else None, row[1] if row else None)


def _query_response_after(db_url: str, phone: str, after_id: int) -> str | None:
    """Pega `response` da row mais nova depois de `after_id` (msg proativa)."""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT response FROM message_queue
             WHERE phone_number = %s AND id > %s AND status = 'done'
             ORDER BY id ASC LIMIT 1
            """,
            (phone, after_id),
        )
        row = cur.fetchone()
    return row[0] if row else None


def simular_jornada_setor(
    setor: dict,
    modalidade: str,
    media_urls: dict[str, str],
    db_url: str,
    *,
    timeout_seconds: int = 90,
) -> JornadaResult:
    """Simula a jornada completa do cliente em 1 setor com 1 modalidade.

    Args:
        setor: dict do SETORES (`slug, opcao, agente, depto`)
        modalidade: 'texto' | 'imagem' | 'audio' | 'pdf'
        media_urls: dict do fixture media_server_urls
        db_url: conexão psycopg
        timeout_seconds: timeout máx por turno
    """
    phone = unique_phone("11")
    result = JornadaResult(setor=setor, modalidade=modalidade, phone=phone)

    # --- Turno 1: cliente novo manda "oi" (welcome) ---
    sid1 = unique_sid()
    t1 = TurnoInfo(sid=sid1, body="oi", inicio=time.time())
    try:
        r = _post_webhook(phone=phone, body=t1.body, sid=sid1)
        if r.status_code != 200:
            result.erros.append(f"turno1 webhook {r.status_code}")
            return result
        wait_terminal_status(db_url, sid1, timeout_seconds=timeout_seconds)
        t1.fim = time.time()
        # Pega response (welcome message)
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT response FROM message_queue WHERE message_id = %s",
                (sid1,),
            )
            row = cur.fetchone()
            t1.response = row[0] if row else None
        result.turnos.append(t1)
    except Exception as e:
        result.erros.append(f"turno1: {e!s:.200}")
        return result

    # --- Turno 2: cliente escolhe "{opcao}" ---
    sid2 = unique_sid()
    t2 = TurnoInfo(sid=sid2, body=str(setor["opcao"]), inicio=time.time())
    try:
        r = _post_webhook(phone=phone, body=t2.body, sid=sid2)
        if r.status_code != 200:
            result.erros.append(f"turno2 webhook {r.status_code}")
            return result
        wait_terminal_status(db_url, sid2, timeout_seconds=timeout_seconds)
        t2.fim = time.time()
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT response, id FROM message_queue WHERE message_id = %s",
                (sid2,),
            )
            row = cur.fetchone()
            t2.response = row[0] if row else None
        result.turnos.append(t2)
    except Exception as e:
        result.erros.append(f"turno2: {e!s:.200}")
        return result

    # Aguarda agente proativo (sentinel [NOVO_ATENDIMENTO_TRIAGEM] enfileirado)
    # processar em ~2-5s. wait_terminal_status do sid2 retorna quando o menu
    # processou; o sentinel é uma row separada que entra depois.
    time.sleep(4)

    # Pega resposta proativa do agente
    if t2.response and "id" in str(t2.response).lower():
        pass  # já tem
    atd = _query_atendimento(db_url, phone)
    if atd:
        result.atendimento_id = atd["id"]
        result.agente_atual = atd["agente_atual"]
        result.departamento_id = atd["departamento_id"]
        # Pega a resposta proativa: row do agente após o turno 2
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT response FROM message_queue
                 WHERE phone_number = %s
                   AND incoming_message LIKE '%%NOVO_ATENDIMENTO_TRIAGEM%%'
                   AND status = 'done'
                 ORDER BY id DESC LIMIT 1
                """,
                (phone,),
            )
            row = cur.fetchone()
            result.response_proativa = row[0] if row else None

    # --- Turno 3: cliente envia mensagem da modalidade ---
    sid3 = unique_sid()
    body_modalidade = {
        "texto": "Preciso de ajuda. Pode me orientar?",
        "imagem": "Olha essa imagem.",
        "audio": "Escuta esse audio.",
        "pdf": "Veja este documento.",
    }[modalidade]
    media_url = None
    media_content_type = None
    if modalidade == "imagem":
        media_url = media_urls["image_url"]
        media_content_type = "image/png"
    elif modalidade == "audio":
        media_url = media_urls["audio_url"]
        media_content_type = "audio/ogg"
    elif modalidade == "pdf":
        media_url = media_urls["pdf_url"]
        media_content_type = "application/pdf"

    t3 = TurnoInfo(
        sid=sid3,
        body=body_modalidade,
        inicio=time.time(),
        media_type=media_content_type,
    )
    try:
        r = _post_webhook(
            phone=phone,
            body=body_modalidade,
            sid=sid3,
            media_url=media_url,
            media_content_type=media_content_type,
        )
        if r.status_code != 200:
            result.erros.append(f"turno3 webhook {r.status_code}")
            return result
        wait_terminal_status(db_url, sid3, timeout_seconds=timeout_seconds)
        t3.fim = time.time()
        ni, mt = _query_normalized_input(db_url, sid3)
        result.normalized_input_modalidade = ni
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT response FROM message_queue WHERE message_id = %s "
                "ORDER BY id DESC LIMIT 1",
                (sid3,),
            )
            row = cur.fetchone()
            t3.response = row[0] if row else None
            result.response_final = t3.response
        result.turnos.append(t3)
    except Exception as e:
        result.erros.append(f"turno3: {e!s:.200}")
        return result

    return result
