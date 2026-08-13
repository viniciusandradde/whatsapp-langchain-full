package com.vsanexus.atendimento.data

import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.AtendimentoDto
import com.vsanexus.atendimento.data.remote.CloseRequest
import com.vsanexus.atendimento.data.remote.MensagemDto
import com.vsanexus.atendimento.data.remote.NotaRequest
import com.vsanexus.atendimento.data.remote.ResponderRequest
import com.vsanexus.atendimento.data.remote.TransferRequest
import com.vsanexus.atendimento.domain.Bolha
import com.vsanexus.atendimento.domain.Lado
import com.vsanexus.atendimento.domain.paraBolhas
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.Response
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/** Content-type da parte de texto do multipart (a legenda). */
private val TEXTO_SIMPLES = "text/plain; charset=utf-8".toMediaType()

/** Usado quando o seletor do sistema declara um MIME que não parseia. */
private val OCTET_STREAM = "application/octet-stream".toMediaType()

data class EstadoConversa(
    val bolhas: List<Bolha> = emptyList(),
    val carregando: Boolean = false,
    val carregandoHistorico: Boolean = false,
    /** Null = início da conversa alcançado, não há mais o que carregar. */
    val cursor: Long? = null,
    val aviso: String? = null,
    /**
     * `aguardando` | `em_andamento` | `resolvido` | `abandonado`.
     *
     * Decide qual ação a tela oferece: em `aguardando` cabe "Atender" (que cala
     * a IA), em `em_andamento` cabe "Devolver para a IA".
     */
    val status: String? = null,
    /** Ação de assumir/devolver em curso — desabilita os botões. */
    val mudandoDono: Boolean = false,
    /**
     * Detalhe completo do atendimento — alimenta o cartão de triagem
     * (resumo da IA, prioridade, sentimento, categoria) e o painel do cliente
     * (id e nome). Vem da mesma chamada que já buscava o status.
     */
    val detalhe: AtendimentoDto? = null,
    /** Confirmação curta de ação concluída (transferido, encerrado, nota). */
    val confirmacao: String? = null,
) {
    val podeAtender: Boolean
        get() = status == "aguardando"

    val podeDevolverParaIa: Boolean
        get() = status == "em_andamento"

    /** Encerrar e transferir só fazem sentido com o atendimento aberto. */
    val aberto: Boolean
        get() = status == "aguardando" || status == "em_andamento"
}

/**
 * Mensagens de UMA conversa aberta.
 *
 * Estado em memória, não em Room, por decisão: a conversa aberta é efêmera —
 * dura o tempo da tela. O cache que importa (a LISTA) já está no banco, e
 * persistir a timeline inteira exigiria reconciliar id do servidor com id local
 * pra cada mensagem pendente, complexidade que só se paga se o operador
 * precisar ler conversa offline. Se isso aparecer, entra depois.
 *
 * A exceção são mensagens PENDENTES de envio, que vivem só aqui — perder o app
 * antes de subir perde a mensagem. Aceitável porque a janela é de segundos e o
 * texto continua no campo até o envio confirmar.
 */
@Singleton
class MensagensRepository
@Inject
constructor(private val api: AtendimentoApi) {
    private val _estado = MutableStateFlow(EstadoConversa())
    val estado: StateFlow<EstadoConversa> = _estado.asStateFlow()

    private var atendimentoId: Long? = null
    private var recebidas: List<MensagemDto> = emptyList()

    /** Abre a conversa: limpa o estado anterior e busca as últimas mensagens. */
    suspend fun abrir(id: Long) {
        atendimentoId = id
        recebidas = emptyList()
        _estado.value = EstadoConversa(carregando = true)
        buscar(beforeId = null)
        // Status vem do detalhe, não da lista: a lista pode estar em cache de
        // minutos atrás, e é o status que decide se a tela oferece "Atender" ou
        // "Devolver para a IA". Errar isso mostraria a ação errada.
        // Best-effort nos dois: falhar aqui não impede LER a conversa.
        recarregarDetalhe()
        runCatching { api.marcarLido(id) }
    }

    /** Relê o detalhe (status + triagem) — best-effort. */
    private suspend fun recarregarDetalhe() {
        val id = atendimentoId ?: return
        runCatching { api.detalhe(id) }
            .getOrNull()
            ?.let { _estado.value = _estado.value.copy(status = it.status, detalhe = it) }
    }

    /**
     * "Atender": tira da fila da IA.
     *
     * A IA para de responder este cliente enquanto o atendimento tiver dono — é
     * o objetivo da ação. O backend também avisa o cliente que um atendente
     * assumiu (mesmo comportamento do painel web).
     */
    suspend fun assumir(): Boolean = trocarDono { api.assumir(it) }

    /**
     * Devolve pra fila da IA. **Nada é enviado ao cliente.**
     *
     * O par de [assumir]: sem isto, um toque errado em "Atender" deixaria aquela
     * conversa sem IA para sempre, porque as outras saídas falam com o cliente
     * (fechar dispara a pesquisa de satisfação, transferir anuncia o setor).
     */
    suspend fun devolverParaIa(): Boolean = trocarDono { api.devolverParaIa(it) }

    private suspend fun trocarDono(chamada: suspend (Long) -> Response<Unit>): Boolean {
        val id = atendimentoId ?: return false
        _estado.value = _estado.value.copy(mudandoDono = true, aviso = null)
        return try {
            val r = chamada(id)
            if (r.isSuccessful) {
                // Relê o status do servidor em vez de assumir o resultado: o
                // claim pode ser recusado por capacidade (409) e o status real é
                // o que decide qual botão a tela mostra a seguir.
                recarregarDetalhe()
                _estado.value = _estado.value.copy(mudandoDono = false)
                atualizar()
                true
            } else {
                _estado.value =
                    _estado.value.copy(mudandoDono = false, aviso = avisoDonoDe(r.code()))
                false
            }
        } catch (e: Exception) {
            _estado.value =
                _estado.value.copy(mudandoDono = false, aviso = "Sem conexão. Tente de novo.")
            false
        }
    }

    /** 409 no claim é limite de atendimentos simultâneos, não erro de rede. */
    private fun avisoDonoDe(codigo: Int) =
        when (codigo) {
            409 -> "Não foi possível: o atendimento já foi fechado ou você atingiu o limite."
            403 -> "Você não tem permissão para isso."
            404 -> "Atendimento não encontrado."
            else -> "Não foi possível concluir a ação."
        }

    /**
     * Encerra como `resolvido` ou `abandonado`.
     *
     * Resolvido pode disparar a pesquisa de satisfação no WhatsApp do cliente
     * — decisão que o operador confirma na tela ANTES de chegar aqui. Depois
     * do encerramento os botões de ação somem sozinhos: o status novo vem do
     * servidor e `aberto` vira false.
     */
    suspend fun encerrar(statusFinal: String): Boolean {
        val id = atendimentoId ?: return false
        _estado.value = _estado.value.copy(mudandoDono = true, aviso = null)
        return try {
            val r = api.encerrar(id, CloseRequest(statusFinal))
            if (r.isSuccessful) {
                recarregarDetalhe()
                _estado.value =
                    _estado.value.copy(
                        mudandoDono = false,
                        confirmacao =
                            if (statusFinal == "resolvido") "Atendimento resolvido."
                            else "Atendimento marcado como abandonado.",
                    )
                true
            } else {
                _estado.value =
                    _estado.value.copy(mudandoDono = false, aviso = avisoDonoDe(r.code()))
                false
            }
        } catch (e: Exception) {
            _estado.value =
                _estado.value.copy(mudandoDono = false, aviso = "Sem conexão. Tente de novo.")
            false
        }
    }

    /**
     * Transfere para atendente OU departamento (exatamente um).
     *
     * Departamento avisa o cliente da mudança de setor (comportamento do
     * backend, igual ao web); atendente não avisa. Nos dois casos o status
     * novo vem do servidor — a tela se reorganiza a partir dele.
     */
    suspend fun transferir(userId: String?, departamentoId: Long?, nomeDestino: String): Boolean {
        val id = atendimentoId ?: return false
        _estado.value = _estado.value.copy(mudandoDono = true, aviso = null)
        return try {
            val r = api.transferir(id, TransferRequest(userId = userId, departamentoId = departamentoId))
            if (r.isSuccessful) {
                recarregarDetalhe()
                _estado.value =
                    _estado.value.copy(
                        mudandoDono = false,
                        confirmacao = "Transferido para $nomeDestino.",
                    )
                atualizar()
                true
            } else {
                _estado.value =
                    _estado.value.copy(mudandoDono = false, aviso = avisoDonoDe(r.code()))
                false
            }
        } catch (e: Exception) {
            _estado.value =
                _estado.value.copy(mudandoDono = false, aviso = "Sem conexão. Tente de novo.")
            false
        }
    }

    /**
     * Nota interna: entra na timeline, nunca sai pro cliente.
     *
     * Sem bolha otimista: a nota real chega no `atualizar()` logo em seguida,
     * e a janela é curta demais pra valer a complexidade de reconciliar.
     */
    suspend fun criarNota(texto: String): Boolean {
        val id = atendimentoId ?: return false
        val corpo = texto.trim()
        if (corpo.isEmpty()) return false
        return try {
            val r = api.criarNota(id, NotaRequest(corpo))
            if (r.isSuccessful) {
                atualizar()
                true
            } else {
                val aviso =
                    if (r.code() == 403) "Você não tem permissão para criar nota interna."
                    else avisoDe(r.code())
                _estado.value = _estado.value.copy(aviso = aviso)
                false
            }
        } catch (e: Exception) {
            _estado.value =
                _estado.value.copy(aviso = "Sem conexão. A nota não foi salva.")
            false
        }
    }

    /** A tela chama depois de exibir a confirmação — evita reexibição. */
    fun limparConfirmacao() {
        _estado.value = _estado.value.copy(confirmacao = null)
    }

    /** Carrega a página anterior do histórico usando o cursor. */
    suspend fun carregarHistorico() {
        val id = atendimentoId ?: return
        val cursor = _estado.value.cursor ?: return
        if (_estado.value.carregandoHistorico) return
        _estado.value = _estado.value.copy(carregandoHistorico = true)
        buscar(beforeId = cursor)
    }

    /** Recarrega a página mais recente — usado quando chega evento de SSE/push. */
    suspend fun atualizar() {
        if (atendimentoId == null) return
        buscar(beforeId = null, preservandoHistorico = true)
    }

    private suspend fun buscar(beforeId: Long?, preservandoHistorico: Boolean = false) {
        val id = atendimentoId ?: return
        try {
            val resp = api.mensagens(id, limit = 50, beforeId = beforeId)
            recebidas =
                when {
                    beforeId != null -> resp.mensagens + recebidas
                    preservandoHistorico -> mesclar(recebidas, resp.mensagens)
                    else -> resp.mensagens
                }
            _estado.value =
                _estado.value.copy(
                    bolhas = recebidas.flatMap { it.paraBolhas() },
                    carregando = false,
                    carregandoHistorico = false,
                    // Cursor só avança quando é página de histórico; a página
                    // mais recente não deve zerar o cursor já conhecido.
                    cursor = if (beforeId == null && !preservandoHistorico) resp.nextCursor else _estado.value.cursor,
                    aviso = null,
                )
        } catch (e: Exception) {
            _estado.value =
                _estado.value.copy(
                    carregando = false,
                    carregandoHistorico = false,
                    aviso = "Não foi possível carregar as mensagens.",
                )
        }
    }

    /**
     * Envia mensagem do operador.
     *
     * A bolha aparece na tela ANTES da rede responder, marcada como pendente —
     * é o que faz o envio parecer instantâneo. Se falhar, a bolha sai e o texto
     * volta pro campo (a UI cuida disso), porque bolha fantasma que nunca
     * chegou é pior que erro visível.
     */
    suspend fun enviar(texto: String): Boolean {
        val id = atendimentoId ?: return false
        val corpo = texto.trim()
        if (corpo.isEmpty()) return false

        val pendente =
            Bolha.Texto(
                id = "pendente-${System.nanoTime()}",
                quandoIso = null,
                lado = Lado.SAIDA,
                texto = corpo,
                pendente = true,
            )
        _estado.value = _estado.value.copy(bolhas = _estado.value.bolhas + pendente)

        return try {
            val r = api.responder(id, ResponderRequest(corpo))
            if (r.isSuccessful) {
                // Recarrega pra trocar a bolha pendente pela real do servidor,
                // que traz o texto com `{{cliente.nome}}` já resolvido — o
                // backend renderiza variáveis no envio.
                atualizar()
                true
            } else {
                removerPendente(pendente.id, avisoDe(r.code()))
                false
            }
        } catch (e: Exception) {
            removerPendente(pendente.id, "Sem conexão. A mensagem não foi enviada.")
            false
        }
    }

    /**
     * Envia anexo ou nota de voz.
     *
     * Recebe [arquivo] em vez de bytes para o OkHttp fazer streaming do disco:
     * uma foto de celular passa de 8 MB, e carregar isso em `ByteArray` só pra
     * repassar ao corpo do request dobraria o pico de memória sem ganho.
     *
     * A bolha otimista é de TEXTO ("enviando…"), não uma prévia da mídia:
     * decodificar o arquivo aqui só pra mostrar por dois segundos custaria uma
     * segunda decodificação: `atualizar()` já troca pela bolha real, que vem do
     * servidor com a mídia.
     *
     * O arquivo é apagado no fim, em qualquer desfecho — é uma cópia em cache
     * (gravação ou anexo escolhido) e nada mais lê depois disto.
     */
    suspend fun enviarMidia(arquivo: File, mime: String, legenda: String = ""): Boolean {
        val id = atendimentoId ?: return false
        if (!arquivo.exists() || arquivo.length() == 0L) {
            _estado.value = _estado.value.copy(aviso = "O arquivo está vazio.")
            return false
        }

        val rotulo = if (mime.startsWith("audio/")) "Enviando áudio…" else "Enviando anexo…"
        val pendente =
            Bolha.Texto(
                id = "pendente-${System.nanoTime()}",
                quandoIso = null,
                lado = Lado.SAIDA,
                texto = rotulo,
                pendente = true,
            )
        _estado.value = _estado.value.copy(bolhas = _estado.value.bolhas + pendente)

        return try {
            // `toMediaType()` LANÇA em MIME malformado, e o seletor do sistema
            // devolve o que o app de origem declarou — não necessariamente algo
            // válido. A exceção cairia no catch de rede e o operador leria "sem
            // conexão" para um problema que não é de conexão.
            val tipo = mime.toMediaTypeOrNull() ?: OCTET_STREAM
            val corpo = arquivo.asRequestBody(tipo)
            val parte = MultipartBody.Part.createFormData("arquivo", arquivo.name, corpo)
            val r = api.responderMidia(id, parte, legenda.toRequestBody(TEXTO_SIMPLES))
            if (r.isSuccessful) {
                atualizar()
                true
            } else {
                removerPendente(pendente.id, avisoMidiaDe(r.code()))
                false
            }
        } catch (e: Exception) {
            removerPendente(pendente.id, "Sem conexão. O arquivo não foi enviado.")
            false
        } finally {
            arquivo.delete()
        }
    }

    /**
     * 400 aqui quase sempre é provider sem suporte a mídia (WABA/Twilio) ou tipo
     * recusado — casos em que o operador precisa saber que NÃO adianta repetir.
     */
    private fun avisoMidiaDe(codigo: Int) =
        when (codigo) {
            400 -> "Esta conexão não aceita envio de arquivo."
            409 -> "Este atendimento já foi fechado."
            404 -> "Atendimento não encontrado."
            403 -> "Você não tem permissão para responder aqui."
            413 -> "O arquivo é grande demais."
            else -> "Não foi possível enviar o arquivo."
        }

    private fun removerPendente(id: String, aviso: String) {
        _estado.value =
            _estado.value.copy(
                bolhas = _estado.value.bolhas.filterNot { it.id == id },
                aviso = aviso,
            )
    }

    /**
     * Transcreve a nota de voz de uma mensagem (mig 169) e injeta o texto na
     * própria bolha — sem round-trip da lista inteira. O servidor é
     * idempotente: repetir o toque devolve o texto salvo, sem custo novo.
     */
    suspend fun transcrever(mensagemId: Long) {
        val id = atendimentoId ?: return
        val resp =
            try {
                api.transcrever(id, mensagemId)
            } catch (_: Exception) {
                _estado.value = _estado.value.copy(aviso = "Sem conexão. Tente de novo.")
                return
            }
        if (!resp.isSuccessful) {
            _estado.value = _estado.value.copy(aviso = avisoTranscricaoDe(resp.code()))
            return
        }
        val texto = resp.body()?.transcricao ?: return
        recebidas =
            recebidas.map { if (it.id == mensagemId) it.copy(transcricao = texto) else it }
        _estado.value = _estado.value.copy(bolhas = recebidas.flatMap { it.paraBolhas() })
    }

    private fun avisoTranscricaoDe(codigo: Int) =
        when (codigo) {
            400 -> "Esta mensagem não tem áudio para transcrever."
            404 -> "Mensagem não encontrada."
            403 -> "Você não tem permissão neste atendimento."
            else -> "Não foi possível transcrever agora. Tente novamente."
        }

    /** O endpoint mapeia erro lógico pra 4xx; traduz o que o operador pode agir. */
    private fun avisoDe(codigo: Int) =
        when (codigo) {
            409 -> "Este atendimento já foi fechado."
            404 -> "Atendimento não encontrado."
            403 -> "Você não tem permissão para responder aqui."
            else -> "Não foi possível enviar a mensagem."
        }

    fun fechar() {
        atendimentoId = null
        recebidas = emptyList()
        _estado.value = EstadoConversa()
    }
}

/**
 * Junta a página nova com o que já havia, sem duplicar.
 *
 * `distinctBy(id)` mantendo a versão NOVA: a mesma row pode voltar com
 * `response` preenchido que antes era null (o worker respondeu no meio), e a
 * versão antiga esconderia a resposta.
 */
private fun mesclar(antigas: List<MensagemDto>, novas: List<MensagemDto>): List<MensagemDto> {
    val porId = LinkedHashMap<Long, MensagemDto>()
    antigas.forEach { porId[it.id] = it }
    novas.forEach { porId[it.id] = it }
    return porId.values.sortedBy { it.id }
}
