package com.vsanexus.atendimento.ui.conversas

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vsanexus.atendimento.data.Aba
import com.vsanexus.atendimento.data.ConversasRepository
import com.vsanexus.atendimento.data.Sincronizacao
import com.vsanexus.atendimento.data.local.ConversaEntity
import com.vsanexus.atendimento.data.remote.EventosAtendimento
import com.vsanexus.atendimento.push.PushRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ConversasUiState(
    val aba: Aba = Aba.NAO_RESOLVIDAS,
    val busca: String = "",
    val sincronizando: Boolean = false,
    val avisoSincronizacao: String? = null,
    /** Folha "Nova conversa" aberta (mig 170). Null = fechada. */
    val novaConversa: NovaConversaUi? = null,
    /** Conversa recém-criada aguardando a tela abrir (consumir depois). */
    val conversaCriada: ConversaCriada? = null,
)

data class NovaConversaUi(
    val conexoes: List<com.vsanexus.atendimento.data.remote.ConexaoDto>? = null,
    val enviando: Boolean = false,
    val erro: String? = null,
)

data class ConversaCriada(val id: Long, val titulo: String)

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class ConversasViewModel
@Inject
constructor(
    private val repo: ConversasRepository,
    private val eventos: EventosAtendimento,
    private val push: PushRepository,
    private val apoio: com.vsanexus.atendimento.data.ApoioRepository,
) : ViewModel() {
    private val _ui = MutableStateFlow(ConversasUiState())

    init {
        // Registrar o aparelho toda vez que a lista nasce é barato (UPSERT no
        // backend) e cobre relogin, troca de empresa e token girado — sem
        // depender de acertar cada um desses eventos individualmente.
        viewModelScope.launch { push.registrar() }
    }
    val ui: StateFlow<ConversasUiState> = _ui.asStateFlow()

    private val abaSelecionada = MutableStateFlow(Aba.NAO_RESOLVIDAS)
    private val textoBusca = MutableStateFlow("")

    /**
     * Lista exibida.
     *
     * `flatMapLatest` porque trocar de aba precisa CANCELAR a observação da
     * anterior — sem isso duas queries do Room emitiriam intercaladas e a lista
     * piscaria entre abas.
     *
     * A busca filtra localmente sobre o que já está em cache, e em paralelo
     * dispara sincronização com `q` no servidor. Assim digitar responde no
     * primeiro caractere, sem esperar rede.
     */
    val conversas: StateFlow<List<ConversaEntity>> =
        combine(abaSelecionada, textoBusca.debounce(120)) { aba, busca -> aba to busca }
            .flatMapLatest { (aba, busca) ->
                repo.observar(aba).map { lista ->
                    if (busca.isBlank()) lista else lista.filter { it.combina(busca) }
                }
            }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        sincronizar()
        ouvirEventos()
    }

    /**
     * Tempo real da lista.
     *
     * O evento do SSE não traz a conversa inteira, só diz que algo mudou —
     * então a reação é RESSINCRONIZAR a aba, não remendar a lista em memória.
     * Assim o RBAC e a ordenação continuam sendo do servidor: montar a linha no
     * cliente a partir do evento significaria reimplementar aqui quem pode ver
     * o quê.
     *
     * `debounce` porque uma rajada de mensagens dispara um evento por mensagem,
     * e cada um viraria um GET. Silencioso porque isto acontece sozinho: piscar
     * o indicador de carregamento a cada mensagem recebida seria ruído.
     */
    // --- Nova conversa (mig 170) ---

    fun abrirNovaConversa() {
        _ui.value = _ui.value.copy(novaConversa = NovaConversaUi())
        viewModelScope.launch {
            val cxs = apoio.conexoesParaIniciar()
            val atual = _ui.value.novaConversa ?: return@launch
            _ui.value =
                _ui.value.copy(
                    novaConversa =
                        atual.copy(
                            conexoes = cxs ?: emptyList(),
                            erro =
                                if (cxs == null) {
                                    "Não foi possível carregar as conexões."
                                } else {
                                    null
                                },
                        ),
                )
        }
    }

    fun fecharNovaConversa() {
        _ui.value = _ui.value.copy(novaConversa = null)
    }

    fun iniciarConversa(telefone: String, nome: String, mensagem: String) {
        val atual = _ui.value.novaConversa ?: return
        if (atual.enviando) return
        _ui.value = _ui.value.copy(novaConversa = atual.copy(enviando = true, erro = null))
        viewModelScope.launch {
            when (val r = apoio.iniciarConversa(telefone, nome, mensagem)) {
                is com.vsanexus.atendimento.data.ResultadoIniciar.Criada -> {
                    val atd = r.atendimento
                    _ui.value =
                        _ui.value.copy(
                            novaConversa = null,
                            conversaCriada =
                                ConversaCriada(
                                    atd.id,
                                    atd.clienteNome ?: atd.clienteTelefone ?: "Conversa",
                                ),
                        )
                }
                is com.vsanexus.atendimento.data.ResultadoIniciar.Falha -> {
                    val aberta = _ui.value.novaConversa ?: return@launch
                    _ui.value =
                        _ui.value.copy(
                            novaConversa = aberta.copy(enviando = false, erro = r.mensagem),
                        )
                }
            }
        }
    }

    /** A tela chama depois de navegar pra conversa criada. */
    fun consumirConversaCriada() {
        _ui.value = _ui.value.copy(conversaCriada = null)
    }

    private fun ouvirEventos() {
        viewModelScope.launch {
            eventos.eventos
                .filter { it.mudouConversa }
                .debounce(400)
                .collect { sincronizar(silencioso = true) }
        }
    }

    fun trocarAba(aba: Aba) {
        abaSelecionada.value = aba
        _ui.value = _ui.value.copy(aba = aba)
        sincronizar()
    }

    fun onBusca(texto: String) {
        textoBusca.value = texto
        _ui.value = _ui.value.copy(busca = texto)
    }

    /**
     * @param silencioso sincronização disparada por evento, não pelo operador —
     *   não mostra indicador nem aviso de falha. Falhar aqui só deixa a lista um
     *   momento desatualizada, e um banner de erro que aparece sozinho sem
     *   ninguém ter pedido nada é pior que isso.
     */
    fun sincronizar(silencioso: Boolean = false) {
        if (!silencioso) {
            _ui.value = _ui.value.copy(sincronizando = true, avisoSincronizacao = null)
        }
        viewModelScope.launch {
            val r = repo.sincronizar(abaSelecionada.value, textoBusca.value)
            _ui.value =
                when {
                    // Silencioso e deu certo: limpa aviso antigo, se havia.
                    silencioso && r is Sincronizacao.Ok ->
                        _ui.value.copy(avisoSincronizacao = null)
                    // Silencioso e falhou: não mexe em nada.
                    silencioso -> _ui.value
                    else ->
                        _ui.value.copy(
                            sincronizando = false,
                            avisoSincronizacao = (r as? Sincronizacao.Falha)?.mensagem,
                        )
                }
        }
    }
}

/** Busca local: nome, telefone e protocolo, sem diferenciar maiúsculas. */
private fun ConversaEntity.combina(termo: String): Boolean {
    val t = termo.trim()
    return clienteNome?.contains(t, ignoreCase = true) == true ||
        clienteTelefone?.contains(t, ignoreCase = true) == true ||
        protocolo?.contains(t, ignoreCase = true) == true
}
