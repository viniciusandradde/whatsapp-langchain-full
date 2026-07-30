package com.vsanexus.atendimento.ui.conversas

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vsanexus.atendimento.data.Aba
import com.vsanexus.atendimento.data.ConversasRepository
import com.vsanexus.atendimento.data.Sincronizacao
import com.vsanexus.atendimento.data.local.ConversaEntity
import com.vsanexus.atendimento.data.remote.EventosAtendimento
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
)

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class ConversasViewModel
@Inject
constructor(
    private val repo: ConversasRepository,
    private val eventos: EventosAtendimento,
) : ViewModel() {
    private val _ui = MutableStateFlow(ConversasUiState())
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
