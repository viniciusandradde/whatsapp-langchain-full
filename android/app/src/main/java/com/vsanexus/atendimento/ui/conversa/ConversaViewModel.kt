package com.vsanexus.atendimento.ui.conversa

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vsanexus.atendimento.data.MensagensRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ConversaViewModel
@Inject
constructor(private val repo: MensagensRepository) : ViewModel() {
    val estado = repo.estado

    private val _rascunho = MutableStateFlow("")
    val rascunho: StateFlow<String> = _rascunho.asStateFlow()

    private var abertoId: Long? = null

    fun abrir(id: Long) {
        // Guard porque a recomposição do Compose chama isto de novo a cada
        // frame se não houver controle — e cada chamada refaria a busca.
        if (abertoId == id) return
        abertoId = id
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
        viewModelScope.launch { repo.enviar(texto) }
    }

    override fun onCleared() {
        repo.fechar()
        super.onCleared()
    }
}
