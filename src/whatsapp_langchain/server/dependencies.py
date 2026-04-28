"""FastAPI dependencies para validação e rate limiting.

Dependencies são injetadas automaticamente nas rotas via Depends().
Centralizar aqui mantém as rotas limpas e focadas na lógica de negócio.

Uso:
    from whatsapp_langchain.server.dependencies import check_rate_limit

    @router.post("/webhook/twilio")
    async def webhook(rate_limit: None = Depends(check_rate_limit)):
        ...
"""

import hmac
import time
from collections import defaultdict

import structlog
from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()

# Sliding window de requisições por telefone: {phone: [timestamps]}
request_history: dict[str, list[float]] = defaultdict(list)


def build_validation_url(request: Request) -> str:
    """Reconstrói a URL pública que o Twilio usou para chamar o webhook.

    Atrás de proxy/túnel (cloudflared), request.url mostra localhost.
    TWILIO_WEBHOOK_URL resolve isso definindo a URL pública base.
    Se não configurada, usa a URL do request diretamente.

    Args:
        request: Request HTTP do FastAPI.

    Returns:
        URL completa para validação de assinatura.
    """
    if settings.twilio_webhook_url:
        base = settings.twilio_webhook_url.rstrip("/")
        url = f"{base}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        return url
    return str(request.url)


async def validate_twilio_signature(request: Request) -> None:
    """Valida a assinatura X-Twilio-Signature com HMAC-SHA1 (SDK oficial).

    Usa o RequestValidator do SDK do Twilio para validação criptográfica.
    Quando habilitada (VALIDATE_TWILIO_SIGNATURE=true), rejeita com 403
    qualquer request sem assinatura válida.

    A URL usada na validação é reconstruída via TWILIO_WEBHOOK_URL
    (necessário atrás de proxy/túnel como cloudflared) ou do request.

    Raises:
        HTTPException 403: Se a assinatura é inválida ou ausente.
        HTTPException 500: Se TWILIO_AUTH_TOKEN não está configurado.
    """
    if not settings.validate_twilio_signature:
        return

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        logger.warning("twilio_signature_missing")
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    if not settings.twilio_auth_token:
        logger.error("twilio_auth_token_not_configured")
        raise HTTPException(
            status_code=500,
            detail="Twilio auth token not configured",
        )

    url = build_validation_url(request)

    # Parâmetros POST para validação (Twilio assina URL + params ordenados)
    form_data = await request.form()
    params = {key: str(value) for key, value in form_data.items()}

    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(url, params, signature):
        logger.warning(
            "twilio_signature_invalid",
            url=url,
            params_keys=sorted(params.keys()),
        )
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    logger.debug("twilio_signature_valid")


async def verify_service_token(request: Request) -> None:
    """Verifica o token de serviço interno no header Authorization.

    Rotas administrativas (/api/*) são protegidas por um token compartilhado
    entre o frontend (Next.js) e a API. Não é autenticação de usuário —
    apenas garante que só serviços autorizados acessem endpoints admin.

    O header deve ser: Authorization: Bearer <token>

    Raises:
        HTTPException 401: Se o token está ausente ou inválido.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("service_token_missing", path=str(request.url.path))
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    token = auth_header.removeprefix("Bearer ").strip()

    # Comparacao timing-safe para evitar timing attacks na verificacao do token
    if not hmac.compare_digest(token, settings.internal_service_token):
        logger.warning("service_token_invalid", path=str(request.url.path))
        raise HTTPException(
            status_code=401,
            detail="Invalid service token",
        )

    logger.debug("service_token_valid", path=str(request.url.path))


async def check_rate_limit(phone_number: str) -> None:
    """Verifica rate limit por número de telefone.

    Usa sliding window de 1 hora. Remove timestamps antigos e compara
    a quantidade de requisições com o limite configurado.

    Args:
        phone_number: Número de telefone do remetente.

    Raises:
        HTTPException 429: Se o limite foi atingido.
    """
    now = time.time()
    one_hour_ago = now - 3600

    # Remove timestamps antigos
    timestamps = request_history[phone_number]
    request_history[phone_number] = [t for t in timestamps if t > one_hour_ago]

    if len(request_history[phone_number]) >= settings.rate_limit_per_hour:
        logger.warning(
            "rate_limit_exceeded",
            phone=phone_number,
            count=len(request_history[phone_number]),
            limit=settings.rate_limit_per_hour,
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )

    # Registra nova requisição
    request_history[phone_number].append(now)
