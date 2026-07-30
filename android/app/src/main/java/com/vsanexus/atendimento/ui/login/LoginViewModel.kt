package com.vsanexus.atendimento.ui.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vsanexus.atendimento.data.EmpresaResumo
import com.vsanexus.atendimento.data.ResultadoLogin
import com.vsanexus.atendimento.data.SessaoRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LoginUiState(
    val email: String = "",
    val senha: String = "",
    /**
     * Guardar as credenciais no aparelho pra entrar sozinho depois.
     *
     * Ligado por default porque é o pedido: não digitar de novo. Ficam no
     * `EncryptedSharedPreferences` (chave no Keystore), o que impede outro app
     * de ler — não protege aparelho rooteado ou desbloqueado por terceiro. Quem
     * não quiser, desmarca; e "Sair" apaga.
     */
    val manterConectado: Boolean = true,
    val carregando: Boolean = false,
    val erro: String? = null,
    /** Empresas a escolher. Vazio = etapa de empresa ainda não começou. */
    val empresas: List<EmpresaResumo> = emptyList(),
    val carregandoEmpresas: Boolean = false,
) {
    val podeEntrar: Boolean
        get() = email.isNotBlank() && senha.length >= 4 && !carregando
}

@HiltViewModel
class LoginViewModel
@Inject
constructor(private val repo: SessaoRepository) : ViewModel() {
    private val _ui = MutableStateFlow(LoginUiState())
    val ui: StateFlow<LoginUiState> = _ui.asStateFlow()

    val sessao = repo.estado

    init {
        // Pré-preenche o e-mail e tenta entrar sozinho com o que está salvo.
        //
        // A sessão do Better Auth expira, e o app fala com a API (que valida o
        // token direto no banco) em vez de com o endpoint que renova — então
        // mesmo usando o app todo dia o operador caía na tela de login. Isso foi
        // corrigido no servidor (sessão deslizante), mas ainda há revogação,
        // reinstalação e primeira abertura em aparelho novo.
        _ui.value = _ui.value.copy(email = repo.estado.value.email ?: "")
        viewModelScope.launch {
            if (repo.estado.value.token == null && repo.temCredenciaisSalvas) {
                _ui.value = _ui.value.copy(carregando = true)
                repo.tentarReloginAutomatico()
                _ui.value = _ui.value.copy(carregando = false)
            }
        }
    }

    fun onEmail(v: String) {
        _ui.value = _ui.value.copy(email = v, erro = null)
    }

    fun onSenha(v: String) {
        _ui.value = _ui.value.copy(senha = v, erro = null)
    }

    fun onManterConectado(v: Boolean) {
        _ui.value = _ui.value.copy(manterConectado = v)
    }

    fun entrar() {
        val s = _ui.value
        if (!s.podeEntrar) return
        _ui.value = s.copy(carregando = true, erro = null)
        viewModelScope.launch {
            when (val r = repo.login(s.email, s.senha, s.manterConectado)) {
                is ResultadoLogin.Ok -> {
                    _ui.value = _ui.value.copy(carregando = false)
                    // Login OK não termina o fluxo: sem empresa ativa a API
                    // ainda recusaria as chamadas (get_empresa_context exige
                    // membership). Já busca a lista pro próximo passo.
                    carregarEmpresas()
                }
                is ResultadoLogin.Falha ->
                    _ui.value = _ui.value.copy(carregando = false, erro = r.mensagem)
            }
        }
    }

    fun carregarEmpresas() {
        _ui.value = _ui.value.copy(carregandoEmpresas = true)
        viewModelScope.launch {
            val lista = repo.empresas()
            _ui.value = _ui.value.copy(carregandoEmpresas = false, empresas = lista)
            // Uma empresa só: escolher é cerimônia inútil. Entra direto.
            if (lista.size == 1) escolher(lista.first())
        }
    }

    fun escolher(empresa: EmpresaResumo) = repo.escolherEmpresa(empresa)

    fun sair() {
        viewModelScope.launch { repo.logout() }
    }
}
