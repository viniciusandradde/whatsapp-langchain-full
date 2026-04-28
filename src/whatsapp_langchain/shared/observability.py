"""Configuração de logging estruturado com structlog.

Centraliza a configuração de logging do projeto.
Em dev, mostra logs coloridos e legíveis (pretty).
Em prod (LOG_JSON=true), emite JSON para ferramentas de observabilidade.

Uso:
    from whatsapp_langchain.shared.observability import setup_logging

    setup_logging(log_level="info", json_output=False)

    # Depois, em qualquer módulo:
    import structlog
    logger = structlog.get_logger()
    logger.info("mensagem_processada", phone="+55...", agent="rhawk")
"""

import logging
import sys

import structlog


def setup_logging(log_level: str = "info", json_output: bool = False) -> None:
    """Configura structlog para o projeto.

    Args:
        log_level: Nível de log (debug, info, warning, error). Default: "info".
        json_output: Se True, emite JSON (para prod). Se False, formato colorido (dev).
    """
    # Processadores compartilhados entre dev e prod
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        # Prod: JSON limpo para ferramentas de observabilidade
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Dev: formato colorido e legível
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configura o logging padrão do Python para capturar logs de libs externas
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # Reduz ruído de libs externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
