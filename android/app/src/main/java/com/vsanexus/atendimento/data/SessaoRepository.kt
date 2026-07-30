package com.vsanexus.atendimento.data

import com.vsanexus.atendimento.data.local.SessaoStore
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.AuthApi
import com.vsanexus.atendimento.data.remote.EmpresaDto
import com.vsanexus.atendimento.data.remote.LoginRequest
import javax.inject.Inject
import javax.inject.Singleton

/** Empresa reduzida ao que a UI precisa. */
data class EmpresaResumo(val id: Long, val nome: String)

sealed interface ResultadoLogin {
    data object Ok : ResultadoLogin

    data class Falha(val mensagem: String) : ResultadoLogin
}

@Singleton
class SessaoRepository
@Inject
constructor(
    private val authApi: AuthApi,
    private val api: AtendimentoApi,
    private val store: SessaoStore,
) {
    val estado = store.estado

    /**
     * Login por email e senha.
     *
     * O token de sessão vem no header `set-auth-token`, não no corpo — é o que
     * o plugin `bearer` do Better Auth faz. Sem esse header não há sessão
     * utilizável, então a ausência dele é falha, mesmo com HTTP 200: seria o
     * caso de o plugin ter saído do servidor, e continuar como se estivesse
     * logado deixaria o app dando 401 em toda tela sem explicar por quê.
     */
    suspend fun login(
        email: String,
        senha: String,
        manterConectado: Boolean = true,
    ): ResultadoLogin =
        try {
            val resp = authApi.login(LoginRequest(email.trim(), senha))
            when {
                resp.code() == 401 || resp.code() == 403 ->
                    ResultadoLogin.Falha("E-mail ou senha incorretos.")
                resp.code() == 429 ->
                    // Better Auth limita a 5 tentativas por 15 min em
                    // /sign-in/email (frontend/src/lib/auth.ts).
                    ResultadoLogin.Falha(
                        "Muitas tentativas. Aguarde alguns minutos e tente de novo.",
                    )
                !resp.isSuccessful ->
                    ResultadoLogin.Falha("Não foi possível entrar. Tente novamente.")
                else -> {
                    val token = resp.headers()["set-auth-token"]
                    if (token.isNullOrBlank()) {
                        ResultadoLogin.Falha(
                            "Login aceito, mas o servidor não devolveu a sessão. " +
                                "Avise o suporte.",
                        )
                    } else {
                        store.salvarToken(token, resp.body()?.user?.name)
                        // Guardadas só depois do servidor aceitar: senha errada
                        // não deve virar credencial salva que o relogin fica
                        // repetindo até o rate limit de 5 tentativas travar.
                        if (manterConectado) store.salvarCredenciais(email.trim(), senha)
                        ResultadoLogin.Ok
                    }
                }
            }
        } catch (e: Exception) {
            // Mensagem amigável na UI; o detalhe técnico fica no log. Mesma
            // regra do painel web (lib/api-error-shared.ts).
            ResultadoLogin.Falha("Sem conexão com o servidor. Verifique a internet.")
        }

    /**
     * Empresas do usuário.
     *
     * Só faz sentido depois do login — usa o token já salvo. Devolve lista
     * vazia em erro; a UI trata como "não conseguiu carregar" e oferece
     * tentar de novo, em vez de travar num spinner.
     */
    suspend fun empresas(): List<EmpresaResumo> =
        try {
            api.empresas().empresas.map { it.toResumo() }
        } catch (e: Exception) {
            emptyList()
        }

    fun escolherEmpresa(empresa: EmpresaResumo) = store.salvarEmpresa(empresa.id, empresa.nome)

    /**
     * Entra de novo com as credenciais salvas, se houver.
     *
     * Chamado na abertura do app quando não há token: a sessão do Better Auth
     * expira, e sem isto o operador voltava pro teclado. Falha em silêncio — a
     * tela de login já é o destino, e um erro na abertura sem ninguém ter pedido
     * nada seria ruído.
     *
     * @return true se entrou.
     */
    /** Há credenciais salvas pra tentar relogin? (não expõe a senha) */
    val temCredenciaisSalvas: Boolean
        get() = store.credenciais != null

    suspend fun tentarReloginAutomatico(): Boolean {
        if (store.token != null) return true
        val c = store.credenciais ?: return false
        return login(c.email, c.senha, manterConectado = false) is ResultadoLogin.Ok
    }

    suspend fun logout() {
        // Invalida no servidor primeiro, best-effort: se falhar (offline), o
        // token local sai de qualquer forma — deixar credencial no aparelho
        // por causa de rede ruim é pior que uma sessão órfã que expira sozinha.
        runCatching { authApi.logout() }
        // `sair`, não `limpar`: logout explícito apaga as credenciais salvas,
        // senão o relogin automático entraria de novo na próxima abertura e o
        // botão "Sair" não sairia de nada.
        store.sair()
    }
}

private fun EmpresaDto.toResumo() =
    EmpresaResumo(
        id = id,
        // `nome_exibicao` é o nome de marca do white-label (mig 115); cai no
        // razão social quando não houver.
        nome = nomeExibicao?.takeIf { it.isNotBlank() } ?: nome,
    )
