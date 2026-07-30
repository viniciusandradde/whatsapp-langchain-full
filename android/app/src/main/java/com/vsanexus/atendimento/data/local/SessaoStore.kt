package com.vsanexus.atendimento.data.local

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class Sessao(
    val token: String? = null,
    val nomeUsuario: String? = null,
    val empresaId: Long? = null,
    val empresaNome: String? = null,
) {
    val logado: Boolean get() = token != null

    /** Logado mas sem empresa escolhida — precisa passar pelo seletor. */
    val precisaEscolherEmpresa: Boolean get() = logado && empresaId == null
}

/**
 * Onde a sessão vive.
 *
 * É interface, não classe, por dois motivos: o repositório não tem por que
 * saber de `EncryptedSharedPreferences`, e a implementação real depende do
 * Keystore do Android — que não existe em teste de JVM, então sem abstração o
 * login ficaria sem cobertura justo na parte mais delicada.
 */
interface SessaoStore {
    val estado: StateFlow<Sessao>

    /** Leitura direta pro interceptor do OkHttp, que não pode suspender. */
    val token: String?

    val empresaId: Long?

    fun salvarToken(token: String, nomeUsuario: String?)

    fun salvarEmpresa(empresaId: Long, nome: String?)

    fun limpar()
}

/**
 * Implementação real, com a chave no Keystore do Android.
 *
 * O token é credencial: com ele, quem lesse o arquivo agiria como o operador
 * dentro da empresa dele. Em aparelho com root o Keystore não é blindagem
 * absoluta, mas texto puro no disco é convite.
 */
class SessaoStoreCriptografado(context: Context) : SessaoStore {
    private val prefs: SharedPreferences =
        EncryptedSharedPreferences.create(
            context,
            "sessao",
            MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )

    private val _estado = MutableStateFlow(leDoDisco())
    override val estado: StateFlow<Sessao> = _estado.asStateFlow()

    override val token: String? get() = _estado.value.token
    override val empresaId: Long? get() = _estado.value.empresaId

    override fun salvarToken(token: String, nomeUsuario: String?) {
        prefs.edit().putString(K_TOKEN, token).putString(K_NOME, nomeUsuario).apply()
        _estado.value = _estado.value.copy(token = token, nomeUsuario = nomeUsuario)
    }

    override fun salvarEmpresa(empresaId: Long, nome: String?) {
        prefs.edit().putLong(K_EMPRESA, empresaId).putString(K_EMPRESA_NOME, nome).apply()
        _estado.value = _estado.value.copy(empresaId = empresaId, empresaNome = nome)
    }

    /**
     * Apaga tudo.
     *
     * Chamado no logout explícito E quando a API devolve 401 — sessão revogada
     * no servidor (`set_user_status` apaga `auth.session`) tem que derrubar o
     * app, não deixá-lo tentando com token morto pra sempre.
     */
    override fun limpar() {
        prefs.edit().clear().apply()
        _estado.value = Sessao()
    }

    private fun leDoDisco() =
        Sessao(
            token = prefs.getString(K_TOKEN, null),
            nomeUsuario = prefs.getString(K_NOME, null),
            empresaId = prefs.getLong(K_EMPRESA, 0L).takeIf { it > 0L },
            empresaNome = prefs.getString(K_EMPRESA_NOME, null),
        )

    private companion object {
        const val K_TOKEN = "token"
        const val K_NOME = "nome_usuario"
        const val K_EMPRESA = "empresa_id"
        const val K_EMPRESA_NOME = "empresa_nome"
    }
}
