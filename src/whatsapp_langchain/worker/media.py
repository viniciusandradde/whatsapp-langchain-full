"""Pré-processamento de mídia (imagem/áudio/documento) antes do agente.

Regra arquitetural:
- O agente sempre recebe texto.
- Arquivo que não dá pra ler — tipo não habilitado no agente, formato sem
  parser, extração quebrada — **também** vira texto: um bloco
  `[Arquivo recebido: …]` que o agente usa pra confirmar o recebimento com as
  próprias palavras. Quem responde ao cliente é sempre o agente.
- Só falha TRANSITÓRIA (download, provedor de visão/transcrição) impede a
  invocação: aí a mensagem volta pra fila e é retentada.
"""

from __future__ import annotations

import base64  # noqa: F401  — preservado caso outros call-sites legacy importem
from dataclasses import dataclass

import structlog
from langchain_core.messages import HumanMessage

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.file_extractor import (
    MAX_FILE_SIZE_BYTES,
    FileExtractionError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    filename_for_media_type,
)
from whatsapp_langchain.shared.midia_processing import (
    _media_kind,  # re-export
)
from whatsapp_langchain.shared.midia_processing import (
    describe_image_bytes as _describe_image,
)
from whatsapp_langchain.shared.midia_processing import (
    transcribe_audio_bytes as _transcribe_audio,
)

# Aliases pra preservar compat interna (alguns lugares ainda usam estas refs)
__all__ = [
    "AUTO_RESPONSE_MEDIA_FAILURE",
    "preprocess_incoming_message",
    "build_human_message",
    "download_media",
]

logger = structlog.get_logger()

# Erros do extrator que NUNCA passam repetindo — separá-los do genérico é o que
# encerra a retentativa inútil (ver `preprocess_incoming_message`).
_ERROS_PERMANENTES = (
    UnsupportedFileTypeError,
    FileTooLargeError,
    FileExtractionError,
)

AUTO_RESPONSE_MEDIA_FAILURE = (
    "Estamos com dificuldades em processar imagens/audio. "
    "Por favor, mande mensagem de texto."
)
AUTO_RESPONSE_IMAGE_DISABLED = (
    "No momento o processamento de imagens está desativado. "
    "Por favor, mande mensagem de texto."
)
AUTO_RESPONSE_AUDIO_DISABLED = (
    "No momento o processamento de áudio está desativado. "
    "Por favor, mande mensagem de texto."
)
AUTO_RESPONSE_UNSUPPORTED_MEDIA = (
    "Este tipo de mídia não é suportado no momento. Por favor, mande mensagem de texto."
)


_ROTULO_POR_KIND = {
    "image": "uma imagem",
    "audio": "um áudio",
    "document": "um documento",
}


def _descricao_arquivo(filename: str | None, kind: str) -> str:
    """Como o arquivo é citado pro agente (e, por tabela, pro cliente).

    Nota de voz e foto do WhatsApp não têm nome — citar `doc.ogg` seria pior que
    dizer "um áudio". Nome real, quando existe, é o que o cliente reconhece.
    """
    nome = (filename or "").strip()
    if nome:
        return nome
    return _ROTULO_POR_KIND.get(kind, "um arquivo")


def _motivo_de(erro: Exception) -> str:
    """Por que este arquivo não foi lido, em uma frase que o agente possa usar.

    O motivo precisa ser ESPECÍFICO. Com um genérico "não foi possível ler o
    conteúdo", o modelo preenche a lacuna sozinho: num teste real, com um PDF de
    13 MB, o agente respondeu "não consigo ler o conteúdo de documentos em PDF"
    — e ele lê PDF; o que não cabia era o tamanho. Motivo vago vira limitação
    inventada, dita ao cliente com toda a confiança.
    """
    if isinstance(erro, FileTooLargeError):
        return (
            f"o arquivo passou do limite de tamanho que consigo abrir "
            f"({MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB)"
        )
    if isinstance(erro, UnsupportedFileTypeError):
        return "não sei abrir arquivos deste formato"
    return "o arquivo veio vazio ou danificado"


def bloco_arquivo_recebido(nome: str, motivo: str) -> str:
    """Texto que substitui o conteúdo quando o arquivo não foi lido.

    Vai para o AGENTE, não para o cliente: quem responde é o agente, com as
    próprias palavras. Antes disso o worker mandava uma frase fixa ("estamos com
    dificuldades em processar imagens/audio") que era errada para documento, não
    dizia o que fazer, e — pior — saía por fora dos portões de fila, modo manual
    e whitelist, falando com cliente que aguardava atendente humano.

    A instrução é explícita sobre não inventar conteúdo porque o modelo, vendo
    só o nome do arquivo, tende a supor o que havia dentro.
    """
    return (
        f"[Arquivo recebido: {nome} — {motivo}. "
        "Confirme ao cliente que o arquivo chegou, citando o nome, e diga esse "
        "motivo. NÃO invente nem suponha o conteúdo: você não o leu. E não "
        "generalize o motivo para todo o formato — a limitação é deste arquivo.]"
    )


@dataclass
class MediaPreprocessResult:
    """Resultado do pré-processamento de entrada antes do agente."""

    should_invoke_agent: bool
    normalized_text: str | None
    media_processing_status: str
    media_processing_error: str | None = None
    auto_response: str | None = None


async def download_media(url: str) -> bytes:
    """Wrapper compat — delega pro shared.midia_processing.download_media
    que suporta data: URLs (mig 2026-05-07 fix Evolution mídia)."""
    from whatsapp_langchain.shared.midia_processing import (
        download_media as _shared_download,
    )

    body, _ctype = await _shared_download(url)
    return body


# _media_kind, _audio_format_from_media_type, _extract_text,
# _chat_completion_media, _describe_image, _transcribe_audio
# ↑ todos reexportados de shared/midia_processing.py (refator 2026-05-07)


async def preprocess_incoming_message(
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
    midia_model: str | None = None,
    filename: str | None = None,
    aceita_imagem: bool = True,
    aceita_audio: bool = True,
    aceita_documento: bool = True,
    transcricao_previa: str | None = None,
) -> MediaPreprocessResult:
    """Normaliza entrada para texto antes da chamada ao agente.

    Quando a mídia não pode ser lida — porque o agente não aceita aquele tipo,
    porque não há parser, ou porque a extração falhou de forma definitiva — o
    resultado **ainda invoca o agente**, com um bloco `[Arquivo recebido: …]` no
    lugar do conteúdo. Só falha transitória (download, provedor) devolve
    `should_invoke_agent=False`, que é o caminho de retentativa.

    Isso é deliberado: até 2026-08-05 essas situações disparavam uma frase fixa
    direto para o cliente, por fora dos portões de fila do departamento, modo
    manual e whitelist — cliente que esperava atendente humano recebia "estamos
    com dificuldades em processar imagens/audio" do nada.

    Args:
        body: Texto recebido (pode ser vazio quando é só mídia).
        media_url: URL da mídia, ou `data:` URL já baixada (None = sem mídia).
        media_type: MIME type da mídia.
        midia_model: Override do modelo multimodal.
                     None = usa settings.openrouter_midia_model.
        filename: Nome real do arquivo, quando o provedor manda
                  (`documentMessage.fileName`). É mais confiável que o mime pra
                  escolher o parser, e é o que o cliente reconhece na resposta.
        aceita_imagem/aceita_audio/aceita_documento: permissões do agente
                  (`agente_ia.aceita_*`). Combinam com o desligamento global por
                  env — basta um dos dois estar desligado pra não ler.
    """
    if not media_url and not media_type:
        return MediaPreprocessResult(
            should_invoke_agent=True,
            normalized_text=body,
            media_processing_status="none",
        )

    kind = _media_kind(media_type)
    descricao = _descricao_arquivo(filename, kind)

    def _recebido_sem_ler(motivo: str, status: str) -> MediaPreprocessResult:
        partes = [
            p for p in [body.strip(), bloco_arquivo_recebido(descricao, motivo)] if p
        ]
        return MediaPreprocessResult(
            should_invoke_agent=True,
            normalized_text="\n".join(partes),
            media_processing_status=status,
            media_processing_error=motivo,
        )

    # Payload de mídia incompleto — sabemos que veio arquivo, não dá pra buscar.
    if not media_url or not media_type:
        return _recebido_sem_ler("não foi possível baixar o arquivo", "unsupported")

    permitido = {
        "image": aceita_imagem and settings.media_image_enabled,
        "audio": aceita_audio and settings.media_audio_enabled,
        "document": aceita_documento and settings.media_document_enabled,
    }.get(kind, False)

    if kind == "unsupported":
        return _recebido_sem_ler("este tipo de arquivo não é lido", "unsupported")

    if not permitido:
        return _recebido_sem_ler(
            "a leitura deste tipo não está habilitada para este agente",
            "disabled",
        )

    try:
        media_bytes = await download_media(media_url)

        if kind == "image":
            description = await _describe_image(
                media_bytes, media_type, model=midia_model
            )
            parts = [
                p for p in [body.strip(), f"[Descrição de imagem]: {description}"] if p
            ]
            normalized = "\n".join(parts)

        elif kind == "audio":
            # `transcricao_previa`: o gancho de transcrição automática do
            # worker (mig 169) pode já ter transcrito este áudio pro painel —
            # reusar evita pagar a MESMA chamada de LLM duas vezes.
            transcription = transcricao_previa or await _transcribe_audio(
                media_bytes, media_type, model=midia_model
            )
            parts = [
                p
                for p in [body.strip(), f"[Transcrição de áudio]: {transcription}"]
                if p
            ]
            normalized = "\n".join(parts)

        elif kind == "document":
            # PDF/DOCX/DOC/XLSX/TXT/MD via shared/file_extractor (com OCR
            # fallback via Vision pra escaneados).
            from whatsapp_langchain.shared.file_extractor import extract_text

            # Nome real quando o provedor mandou; senão, inferido do mime. O
            # parser é escolhido pela extensão, então o nome real importa: era
            # a inferência que mandava planilha pra `doc.bin` e a recusava.
            nome_arquivo = filename or filename_for_media_type(media_type)

            doc_text = await extract_text(nome_arquivo, media_bytes)
            if not doc_text:
                doc_text = "(documento sem texto extraível)"
            # Trunca em ~10k chars no input pro agente — ele pode chamar
            # extract_document tool pra texto completo se precisar.
            if len(doc_text) > 10_000:
                doc_text = (
                    doc_text[:10_000]
                    + "\n[... documento truncado, use tool extract_document pro texto completo]"
                )

            parts = [
                p
                for p in [
                    body.strip(),
                    f"[Conteúdo do documento ({nome_arquivo})]:\n{doc_text}",
                ]
                if p
            ]
            normalized = "\n".join(parts)

        else:
            # Guard-rail: só entra aqui em caso inesperado
            return _recebido_sem_ler("este tipo de arquivo não é lido", "unsupported")

        return MediaPreprocessResult(
            should_invoke_agent=True,
            normalized_text=normalized,
            media_processing_status="processed",
        )

    except _ERROS_PERMANENTES as e:
        # Arquivo que este código nunca vai conseguir ler: extensão sem parser,
        # arquivo grande demais, conteúdo corrompido. Repetir dá o mesmo
        # resultado — e era exatamente isso que acontecia, 5 vezes, porque tudo
        # caía no `failed` genérico abaixo (atendimento 1018-000664).
        logger.info(
            "media_nao_legivel",
            media_type=media_type,
            filename=filename,
            error=str(e),
        )
        return _recebido_sem_ler(_motivo_de(e), "unsupported")

    except Exception as e:
        # Transitório: download, provedor de transcrição/visão, rede. Aqui a
        # retentativa vale — foi o que recuperou os áudios que falharam por
        # segundos. Ver o ramo `media_transitoria` em worker/processor.py.
        logger.error(
            "media_preprocessing_failed",
            media_type=media_type,
            error=str(e),
        )
        return MediaPreprocessResult(
            should_invoke_agent=False,
            normalized_text=None,
            media_processing_status="failed",
            media_processing_error=str(e),
            auto_response=AUTO_RESPONSE_MEDIA_FAILURE,
        )


async def build_human_message(
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
) -> HumanMessage:
    """Compatibilidade: retorna HumanMessage de texto (sem multimodal)."""
    pre = await preprocess_incoming_message(
        body=body,
        media_url=media_url,
        media_type=media_type,
    )
    text = pre.normalized_text or body or pre.auto_response or ""
    return HumanMessage(content=text)
