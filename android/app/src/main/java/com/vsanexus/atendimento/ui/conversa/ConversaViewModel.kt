package com.vsanexus.atendimento.ui.conversa

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vsanexus.atendimento.data.ApoioRepository
import com.vsanexus.atendimento.data.MensagensRepository
import com.vsanexus.atendimento.data.MidiaRepository
import com.vsanexus.atendimento.data.remote.AtendenteDto
import com.vsanexus.atendimento.data.remote.ClienteDto
import com.vsanexus.atendimento.data.remote.DepartamentoDto
import com.vsanexus.atendimento.data.remote.EventosAtendimento
import com.vsanexus.atendimento.data.remote.TagDto
import com.vsanexus.atendimento.push.ConversaAtual
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * Opções carregadas ao abrir a folha de transferência.
 * Null nas listas = ainda carregando; vazio = carregou e não há.
 */
data class OpcoesTransferencia(
    val departamentos: List<DepartamentoDto>? = null,
    val atendentes: List<AtendenteDto>? = null,
    val falhou: Boolean = false,
)

/** Estado da folha de tags do atendimento. */
data class EstadoTags(
    val catalogo: List<TagDto>? = null,
    /** Ids atualmente aplicados no atendimento. */
    val aplicadas: Set<Long> = emptySet(),
    val salvando: Boolean = false,
    val falhou: Boolean = false,
)

/** Estado do painel do cliente. */
data class EstadoCliente(
    val cliente: ClienteDto? = null,
    val anteriores: List<com.vsanexus.atendimento.data.remote.AtendimentoDto> = emptyList(),
    val carregando: Boolean = true,
)

@HiltViewModel
class ConversaViewModel
@Inject
constructor(
    private val repo: MensagensRepository,
    private val midias: MidiaRepository,
    private val eventos: EventosAtendimento,
    private val apoio: ApoioRepository,
    private val conversaAtual: ConversaAtual,
) : ViewModel() {
    val estado = repo.estado

    private val _rascunho = MutableStateFlow("")
    val rascunho: StateFlow<String> = _rascunho.asStateFlow()

    /** Composer em modo NOTA INTERNA: o texto vai pra timeline, não pro cliente. */
    private val _modoNota = MutableStateFlow(false)
    val modoNota: StateFlow<Boolean> = _modoNota.asStateFlow()

    private val _transferencia = MutableStateFlow<OpcoesTransferencia?>(null)
    val transferencia: StateFlow<OpcoesTransferencia?> = _transferencia.asStateFlow()

    private val _tags = MutableStateFlow<EstadoTags?>(null)
    val tags: StateFlow<EstadoTags?> = _tags.asStateFlow()

    private val _cliente = MutableStateFlow<EstadoCliente?>(null)
    val cliente: StateFlow<EstadoCliente?> = _cliente.asStateFlow()

    private var abertoId: Long? = null

    init {
        ouvirEventos()
    }

    /**
     * Tempo real da conversa aberta.
     *
     * Filtra o stream da EMPRESA pelo `atendimento_id` local em vez de abrir um
     * SSE só desta conversa: no servidor cada stream aberto ocupa uma conexão de
     * banco dedicada (`LISTEN` bloqueia a conexão), então o app mantém um único
     * stream e distribui os eventos internamente.
     *
     * `abertoId` é lido dentro do filtro, não capturado: trocar de conversa sem
     * recriar o ViewModel passa a valer no próximo evento.
     */
    private fun ouvirEventos() {
        viewModelScope.launch {
            eventos.eventos
                .filter { it.mudouConversa && it.atendimentoId == abertoId }
                .debounce(250)
                .collect { repo.atualizar() }
        }
    }

    fun abrir(id: Long) {
        // Guard porque a recomposição do Compose chama isto de novo a cada
        // frame se não houver controle — e cada chamada refaria a busca.
        if (abertoId == id) return
        abertoId = id
        // O serviço de push consulta isto pra NÃO notificar a conversa que o
        // operador já está lendo.
        conversaAtual.id = id
        viewModelScope.launch { repo.abrir(id) }
    }

    fun onRascunho(v: String) {
        _rascunho.value = v
    }

    fun carregarHistorico() {
        viewModelScope.launch { repo.carregarHistorico() }
    }

    fun enviar() {
        val texto = _rascunho.value
        if (texto.isBlank()) return
        // Limpa o campo já: o operador espera poder digitar a próxima. Se o
        // envio falhar, a UI mostra o aviso e o texto pode ser reescrito — o
        // caso de falha é raro e recuperável, e travar o campo em toda mensagem
        // pra cobrir isso deixaria o app lento no caso comum.
        _rascunho.value = ""
        if (_modoNota.value) {
            // O modo nota NÃO desliga sozinho após enviar: quem registra uma
            // nota costuma registrar outra em seguida (resumo em partes), e
            // religar o toggle a cada linha seria atrito. Desligar é gesto
            // explícito — e o composer inteiro muda de cor enquanto ativo,
            // então não há como esquecer sem ver.
            viewModelScope.launch { repo.criarNota(texto) }
        } else {
            viewModelScope.launch { repo.enviar(texto) }
        }
    }

    fun alternarModoNota() {
        _modoNota.value = !_modoNota.value
    }

    // --- Encerrar / transferir ---

    fun encerrar(statusFinal: String) {
        viewModelScope.launch { repo.encerrar(statusFinal) }
    }

    /** Carrega destinos ao abrir a folha de transferência. */
    fun carregarTransferencia() {
        _transferencia.value = OpcoesTransferencia()
        viewModelScope.launch {
            val deps = apoio.departamentos()
            val atds = apoio.atendentesOnline()
            _transferencia.value =
                OpcoesTransferencia(
                    departamentos = deps,
                    atendentes = atds,
                    falhou = deps == null && atds == null,
                )
        }
    }

    fun fecharTransferencia() {
        _transferencia.value = null
    }

    fun transferirParaDepartamento(dep: DepartamentoDto) {
        _transferencia.value = null
        viewModelScope.launch { repo.transferir(null, dep.id, dep.nome) }
    }

    fun transferirParaAtendente(atd: AtendenteDto) {
        _transferencia.value = null
        viewModelScope.launch {
            repo.transferir(atd.userId, null, atd.nome ?: atd.email ?: "atendente")
        }
    }

    // --- Tags do atendimento ---

    fun abrirTags() {
        val id = abertoId ?: return
        _tags.value = EstadoTags()
        viewModelScope.launch {
            val catalogo = apoio.catalogoTags()
            val aplicadas = apoio.tagsDoAtendimento(id)
            _tags.value =
                EstadoTags(
                    catalogo = catalogo,
                    aplicadas = aplicadas?.map { it.id }?.toSet() ?: emptySet(),
                    falhou = catalogo == null,
                )
        }
    }

    fun fecharTags() {
        _tags.value = null
    }

    /**
     * Alterna uma tag e SALVA na hora (delta de um item). Otimista com
     * rollback: a marca muda no toque; se o servidor recusar, volta e o
     * motivo aparece no aviso da conversa.
     */
    fun alternarTag(tagId: Long) {
        val id = abertoId ?: return
        val atual = _tags.value ?: return
        val marcada = tagId in atual.aplicadas
        val novas = if (marcada) atual.aplicadas - tagId else atual.aplicadas + tagId
        _tags.value = atual.copy(aplicadas = novas, salvando = true)
        viewModelScope.launch {
            val erro =
                apoio.aplicarTags(
                    id,
                    add = if (marcada) emptyList() else listOf(tagId),
                    remove = if (marcada) listOf(tagId) else emptyList(),
                )
            val depois = _tags.value
            if (erro != null && depois != null) {
                _tags.value = depois.copy(aplicadas = atual.aplicadas, salvando = false)
            } else if (depois != null) {
                _tags.value = depois.copy(salvando = false)
            }
        }
    }

    // --- Painel do cliente ---

    fun abrirCliente() {
        val clienteId = estado.value.detalhe?.clienteId ?: return
        val atendimentoId = abertoId ?: return
        _cliente.value = EstadoCliente()
        viewModelScope.launch {
            val ficha = apoio.cliente(clienteId)
            val anteriores = apoio.atendimentosAnteriores(clienteId, atendimentoId)
            _cliente.value =
                EstadoCliente(
                    cliente = ficha,
                    anteriores = anteriores ?: emptyList(),
                    carregando = false,
                )
        }
    }

    fun fecharCliente() {
        _cliente.value = null
    }

    /** Toggle otimista de tag do CLIENTE, com rollback em falha. */
    fun alternarTagCliente(tag: String) {
        val atual = _cliente.value?.cliente ?: return
        val marcada = tag in atual.tags
        val novas = if (marcada) atual.tags - tag else atual.tags + tag
        _cliente.value = _cliente.value?.copy(cliente = atual.copy(tags = novas))
        viewModelScope.launch {
            val ok = apoio.alternarTagCliente(atual.id, tag, marcar = !marcada)
            if (!ok) {
                val depois = _cliente.value?.cliente ?: return@launch
                _cliente.value =
                    _cliente.value?.copy(cliente = depois.copy(tags = atual.tags))
            }
        }
    }

    fun limparConfirmacao() {
        repo.limparConfirmacao()
    }

    /** "Atender": tira da fila da IA (e a IA para de responder este cliente). */
    fun assumir() {
        viewModelScope.launch { repo.assumir() }
    }

    /** Devolve pra fila da IA. Nada é enviado ao cliente. */
    fun devolverParaIa() {
        viewModelScope.launch { repo.devolverParaIa() }
    }

    /** Transcreve a nota de voz de uma mensagem (mig 169). */
    fun transcrever(mensagemId: Long) {
        viewModelScope.launch { repo.transcrever(mensagemId) }
    }

    /** Inclui o número do cliente nos "números sem IA" (bloqueio, mig 133). */
    fun incluirSemIa() {
        viewModelScope.launch { repo.incluirSemIa() }
    }

    /**
     * Arquivo local de uma mídia da conversa, baixando na primeira vez.
     *
     * A lista de mensagens vem SEM o conteúdo das mídias (o banco guarda
     * data-URL base64 na linha, e isso inflava a resposta a dezenas de MB), então
     * cada bolha de anexo pede o arquivo por aqui quando aparece na tela.
     *
     * @param saida true quando a mídia é a que o OPERADOR mandou — coluna
     *   diferente no banco (mig 146).
     */
    suspend fun arquivoDeMidia(mensagemId: Long, saida: Boolean): File? {
        val id = abertoId ?: return null
        return midias.arquivo(id, mensagemId, saida)
    }

    /**
     * Envia anexo ou nota de voz.
     *
     * O rascunho vira LEGENDA do anexo e é limpo — como no WhatsApp, onde a foto
     * sai com o texto que estava escrito. Mas não para áudio: nota de voz não
     * tem legenda, e apagar o texto do operador que ele ainda vai mandar seria
     * perder o que ele escreveu.
     */
    fun enviarMidia(arquivo: File, mime: String) {
        val audio = mime.startsWith("audio/")
        val legenda = if (audio) "" else _rascunho.value.trim()
        if (!audio) _rascunho.value = ""
        viewModelScope.launch { repo.enviarMidia(arquivo, mime, legenda) }
    }

    override fun onCleared() {
        conversaAtual.id = null
        repo.fechar()
        super.onCleared()
    }
}
