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
import random
import time
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import AsyncConnectionPool
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from whatsapp_langchain.shared.api_key import (
    ApiKeyContext,
    has_scope,
    resolve_api_key,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import (
    get_default_empresa_id,
    get_empresa_membership,
    is_superadmin,
)
from whatsapp_langchain.shared.rate_limit import enforce_bucket_limit
from whatsapp_langchain.shared.rls_context import empresa_scope, set_request_context

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


# Esquema Bearer do FastAPI: faz o OpenAPI declarar `securitySchemes.ServiceToken`
# e marcar `security` em CADA rota que depende de `verify_service_token` (botão
# "Authorize" no Swagger). `auto_error=False` pra mantermos as mesmas mensagens
# de 401 abaixo em vez do erro padrão do HTTPBearer.
_service_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="ServiceToken",
    description="Token de serviço interno (INTERNAL_SERVICE_TOKEN).",
)


async def _resolve_session_user(token: str) -> str | None:
    """Resolve o user_id de um token de sessão do Better Auth, ou None.

    Cliente móvel não pode usar o caminho do service token: embarcar o
    `INTERNAL_SERVICE_TOKEN` num APK deixaria qualquer um extrair o segredo e
    mandar `X-User-Id`/`X-Empresa-Id` arbitrários, lendo e escrevendo em TODOS
    os tenants (o header é confiado justamente por causa do service token).

    Em vez de introduzir infra de JWT, valida direto em `auth.session`, que já
    é o registro canônico de sessão e vive no mesmo Postgres. Efeito colateral
    desejável: a revogação existente passa a valer no app de graça —
    `shared/usuarios.py::set_user_status` apaga as sessões pra matar login em
    <30s, e aqui o token simplesmente deixa de resolver.

    Devolve None (em vez de levantar) pra que o caller decida o 401 — assim a
    mensagem de erro continua a mesma pro Next.js.
    """
    if len(token) < 16:  # nada em auth.session é tão curto; evita query inútil
        return None
    try:
        pool = await get_pool()
        with empresa_scope(None, bypass=True):
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT s."userId" FROM auth.session s
                     JOIN auth."user" u ON u.id = s."userId"
                     WHERE s.token = %s
                       AND s."expiresAt" > NOW()
                       AND u.status = 'active'
                     LIMIT 1
                    """,
                    (token,),
                )
                row = await cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — falha de lookup não autentica
        logger.warning("session_lookup_failed", error=str(exc))
        return None
    return str(row[0]) if row else None


async def verify_service_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_service_bearer),
) -> None:
    """Autentica a request administrativa pelo header Authorization.

    Aceita DOIS tipos de Bearer, nesta ordem:

    1. **Service token** (`INTERNAL_SERVICE_TOKEN`) — o frontend Next.js.
       Não é autenticação de usuário: prova apenas que a chamada vem de um
       serviço autorizado, e a identidade vem do header `X-User-Id`.
    2. **Token de sessão do Better Auth** — cliente móvel. Aqui a identidade
       vem do BANCO (`auth.session`), nunca de header, e é gravada em
       `request.state.session_user_id` pra `get_user_id_from_request` usar.

    O caminho 2 existe porque app nativo não pode carregar o service token
    (ver `_resolve_session_user`). Empresa continua validada por
    `get_empresa_context`, que exige membership — o app não escolhe tenant.

    Usa `HTTPBearer` apenas pra que o FastAPI documente o esquema no OpenAPI;
    a validação continua sendo nossa, timing-safe no caso 1.

    Raises:
        HTTPException 401: header ausente, ou token que não é nem service
            token nem sessão válida.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("service_token_missing", path=str(request.url.path))
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    token = credentials.credentials.strip()

    # Comparacao timing-safe para evitar timing attacks na verificacao do token
    if hmac.compare_digest(token, settings.internal_service_token):
        logger.debug("service_token_valid", path=str(request.url.path))
        return

    # Não é o service token — tenta sessão de usuário (app móvel).
    user_id = await _resolve_session_user(token)
    if user_id is not None:
        request.state.session_user_id = user_id
        logger.debug("session_token_valid", path=str(request.url.path), user_id=user_id)
        return

    logger.warning("service_token_invalid", path=str(request.url.path))
    raise HTTPException(
        status_code=401,
        detail="Invalid service token",
    )


_RATE_LIMIT_CLEANUP_PROBABILITY = 0.01  # 1% das requisições limpam buckets antigos
_RATE_LIMIT_DETAIL_TEMPLATE = (
    "Rate limit excedido ({limit}/hora). Tente novamente em alguns minutos."
)


async def _check_rate_limit_db(
    pool: AsyncConnectionPool,
    phone_number: str,
    *,
    limit: int,
) -> None:
    """Sliding window por hora cheia em Postgres.

    Compartilha estado entre réplicas via tabela rate_limit_buckets.
    Cleanup inline probabilístico (~1% das requisições) apaga buckets
    com mais de 24h, evitando dependência de cron.

    Args:
        pool: Pool de conexões assíncrono do psycopg.
        phone_number: Telefone do remetente (E.164).
        limit: Máximo de mensagens por telefone por hora.

    Raises:
        HTTPException: 429 quando o telefone excede o limite na hora atual.
    """
    hour_start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO rate_limit_buckets (phone_number, hour_start, request_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (phone_number, hour_start)
            DO UPDATE SET request_count = rate_limit_buckets.request_count + 1
            RETURNING request_count
            """,
            (phone_number, hour_start),
        )
        row = await cursor.fetchone()
        await conn.commit()
        count = row[0] if row else 1

        if random.random() < _RATE_LIMIT_CLEANUP_PROBABILITY:
            await conn.execute(
                "DELETE FROM rate_limit_buckets"
                " WHERE hour_start < NOW() - INTERVAL '24 hours'"
            )
            await conn.commit()

    if count > limit:
        logger.warning(
            "rate_limit_exceeded",
            phone=phone_number,
            count=count,
            limit=limit,
        )
        raise HTTPException(
            status_code=429,
            detail=_RATE_LIMIT_DETAIL_TEMPLATE.format(limit=limit),
        )


def _check_rate_limit_inmemory(phone_number: str) -> None:
    """Rate limit in-memory por número de telefone (modo legado, single-process).

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
            detail=_RATE_LIMIT_DETAIL_TEMPLATE.format(
                limit=settings.rate_limit_per_hour
            ),
        )

    # Registra nova requisição
    request_history[phone_number].append(now)


def get_user_id_from_request(request: Request) -> str:
    """Resolve o user_id da request.

    Duas origens, e a ordem importa:

    1. `request.state.session_user_id` — gravado por `verify_service_token`
       quando a request veio com token de sessão (cliente móvel). Vem do
       BANCO, então tem precedência absoluta: se a sessão identifica o
       usuário, um header `X-User-Id` divergente é ignorado, não obedecido.
    2. Header `X-User-Id` — o frontend Next.js deriva o id da session Better
       Auth e envia em todas as chamadas pra /api/*. A API confia no header
       porque a request já passou pelo `verify_service_token` com o token
       compartilhado de rede interna.

    Raises:
        HTTPException 401: sem sessão e sem header.
    """
    from_session = getattr(request.state, "session_user_id", None)
    if from_session:
        return str(from_session)

    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="X-User-Id header ausente — frontend deve injetar via session.",
        )
    return user_id


async def get_empresa_context(request: Request) -> int:
    """Resolve empresa_id ativo da request (header ou default do user).

    Ordem:
    1. Header `X-Empresa-Id` — se presente, valida membership do user.
    2. Empresa default do user (is_default=TRUE em empresa_membro).
    3. Superadmins podem usar header sem ser membros (acesso cross-tenant).

    Raises:
        HTTPException 401: X-User-Id ausente.
        HTTPException 403: user não tem nenhuma empresa OU header pra
            empresa que não é membro (e não é superadmin).
    """
    user_id = get_user_id_from_request(request)
    pool = await get_pool()

    raw = request.headers.get("X-Empresa-Id", "").strip()
    if raw:
        try:
            empresa_id = int(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="X-Empresa-Id deve ser inteiro."
            ) from exc

        # Superadmins entram em qualquer empresa.
        if await is_superadmin(pool, user_id):
            return empresa_id

        membership = await get_empresa_membership(pool, empresa_id, user_id)
        if membership is None:
            logger.warning(
                "empresa_membership_denied", user=user_id, empresa=empresa_id
            )
            raise HTTPException(
                status_code=403,
                detail=f"Sem acesso à empresa {empresa_id}.",
            )
        return empresa_id

    default = await get_default_empresa_id(pool, user_id)
    if default is None:
        raise HTTPException(
            status_code=403,
            detail="Usuário não pertence a nenhuma empresa.",
        )
    return default


async def check_rate_limit(
    phone_number: str, pool: AsyncConnectionPool | None = None
) -> None:
    """Dispatcher: usa Postgres se RATE_LIMIT_DISTRIBUTED=true, senão in-memory.

    Args:
        phone_number: Número de telefone do remetente.
        pool: Pool de conexões Postgres (obrigatório quando distribuído).

    Raises:
        HTTPException 429: Se o limite foi atingido.
    """
    if settings.rate_limit_distributed:
        if pool is None:
            from whatsapp_langchain.shared.db import get_pool

            pool = await get_pool()
        await _check_rate_limit_db(
            pool, phone_number, limit=settings.rate_limit_per_hour
        )
    else:
        _check_rate_limit_inmemory(phone_number)


# Esquema Bearer da API key por empresa (Disparador). Separado do ServiceToken
# pra o OpenAPI documentar os dois e a extensão Chrome usar APENAS este.
_api_key_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="ApiKey",
    description="API key por empresa do Disparador (formato nxs_<empresa_id>_<hex>).",
)


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_api_key_bearer),
) -> ApiKeyContext:
    """Autentica a extensão via API key por empresa e ativa o contexto RLS.

    Diferente de `verify_service_token` (token global), aqui a empresa é
    DESCOBERTA a partir da própria chave. Após resolver, chamamos
    `set_request_context(empresa_id)` — sem isso, todo INSERT/SELECT nas tabelas
    do tenant quebra com `InsufficientPrivilege` sob a policy RLS estrita
    (mesmo padrão de `evolution_webhook.py`).

    Aplica também rate limit por chave (bucket `apikey:<id>:disparador`).

    Raises:
        HTTPException 401: chave ausente, malformada, inválida, revogada ou
            expirada (mensagem genérica — não vaza qual condição falhou).
        RateLimitExceeded (429): chave excedeu `rate_limit_per_minute`.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("api_key_missing", path=str(request.url.path))
        raise HTTPException(status_code=401, detail="API key ausente ou malformada")

    pool = await get_pool()
    ctx = await resolve_api_key(pool, credentials.credentials.strip())
    if ctx is None:
        logger.warning("api_key_invalid", path=str(request.url.path))
        raise HTTPException(status_code=401, detail="API key inválida")

    # Rate limit por chave (janela de 60s). RateLimitExceeded é HTTPException 429.
    await enforce_bucket_limit(
        pool,
        f"apikey:{ctx.key_id}:disparador",
        limit=ctx.rate_limit_per_minute,
        window_seconds=60,
    )

    # CRÍTICO: ativa o contexto RLS pra empresa resolvida.
    set_request_context(ctx.empresa_id)
    logger.debug("api_key_valid", empresa_id=ctx.empresa_id, key_id=ctx.key_id)
    return ctx


def require_scope(scope: str):
    """Factory de dependency que exige um escopo específico na API key.

    Uso:
        @router.post("/api/captura/contatos",
                     dependencies=[Depends(require_scope("capture"))])
    """

    async def _checker(ctx: ApiKeyContext = Depends(verify_api_key)) -> ApiKeyContext:
        if not has_scope(ctx.scopes, scope):
            raise HTTPException(
                status_code=403,
                detail=f"API key sem escopo necessário: {scope}",
            )
        return ctx

    return _checker
