package com.vsanexus.atendimento

import com.vsanexus.atendimento.data.ResultadoLogin
import com.vsanexus.atendimento.data.SessaoRepository
import com.vsanexus.atendimento.data.local.Sessao
import com.vsanexus.atendimento.data.local.SessaoStore
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.AuthApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * Login contra um servidor de mentira.
 *
 * O ponto sensível é UM: o token de sessão vem no header `set-auth-token`, não
 * no corpo. Se o plugin `bearer` sair do Better Auth, o login passa a devolver
 * 200 sem header — e o app não pode tratar isso como sucesso, senão toda tela
 * seguinte dá 401 sem explicar nada ao usuário.
 *
 * `SessaoStore` é falsificado em memória: o real usa EncryptedSharedPreferences,
 * que precisa do Keystore do Android e não existe em teste de JVM.
 */
class SessaoRepositoryTest {
    private lateinit var server: MockWebServer
    private lateinit var authApi: AuthApi
    private lateinit var api: AtendimentoApi
    private lateinit var store: FakeSessaoStore

    @Before
    fun antes() {
        server = MockWebServer()
        server.start()
        val json = Json { ignoreUnknownKeys = true; coerceInputValues = true; explicitNulls = false }
        val retrofit =
            Retrofit.Builder()
                .baseUrl(server.url("/"))
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                .build()
        authApi = retrofit.create(AuthApi::class.java)
        api = retrofit.create(AtendimentoApi::class.java)
        store = FakeSessaoStore()
    }

    @After
    fun depois() {
        server.shutdown()
    }

    private fun repo() = SessaoRepository(authApi, api, store)

    @Test
    fun `login com header set-auth-token salva a sessao`() =
        runTest {
            server.enqueue(
                MockResponse()
                    .setResponseCode(200)
                    .setHeader("set-auth-token", "token-de-sessao-abc123")
                    .setHeader("Content-Type", "application/json")
                    .setBody("""{"user":{"id":"u1","name":"Luis Fernando"}}"""),
            )

            val r = repo().login("luis@vsanexus.com", "senha123")

            assertTrue(r is ResultadoLogin.Ok)
            assertEquals("token-de-sessao-abc123", store.token)
            assertEquals("Luis Fernando", store.nome)
        }

    @Test
    fun `login 200 SEM o header e tratado como falha`() =
        runTest {
            // Cenário real: alguém remove o plugin bearer do Better Auth. O
            // servidor autentica (cria cookie), mas o app não tem como usar
            // sessão — precisa dizer isso, não fingir que entrou.
            server.enqueue(
                MockResponse()
                    .setResponseCode(200)
                    .setHeader("Content-Type", "application/json")
                    .setBody("""{"user":{"id":"u1"}}"""),
            )

            val r = repo().login("luis@vsanexus.com", "senha123")

            assertTrue(r is ResultadoLogin.Falha)
            assertNull(store.token)
        }

    @Test
    fun `credencial errada devolve mensagem propria`() =
        runTest {
            server.enqueue(MockResponse().setResponseCode(401).setBody("{}"))

            val r = repo().login("luis@vsanexus.com", "errada")

            assertTrue(r is ResultadoLogin.Falha)
            assertEquals("E-mail ou senha incorretos.", (r as ResultadoLogin.Falha).mensagem)
        }

    @Test
    fun `rate limit do Better Auth tem mensagem que orienta esperar`() =
        runTest {
            // /sign-in/email limita a 5 tentativas por 15 min. Sem tratar, o
            // usuário veria "erro" e tentaria mais, piorando o bloqueio.
            server.enqueue(MockResponse().setResponseCode(429).setBody("{}"))

            val r = repo().login("luis@vsanexus.com", "senha123")

            assertTrue((r as ResultadoLogin.Falha).mensagem.contains("Aguarde"))
        }

    @Test
    fun `empresa usa nome de exibicao do white-label quando existe`() =
        runTest {
            server.enqueue(
                MockResponse()
                    .setResponseCode(200)
                    .setHeader("Content-Type", "application/json")
                    .setBody(
                        """{"empresas":[
                          {"id":1,"nome":"VSA Tecnologia LTDA","nome_exibicao":"VSA"},
                          {"id":2,"nome":"Sem Marca"}
                        ]}""",
                    ),
            )

            val lista = repo().empresas()

            assertEquals(2, lista.size)
            assertEquals("VSA", lista[0].nome)
            assertEquals("Sem Marca", lista[1].nome)
        }

    @Test
    fun `campo desconhecido na resposta nao derruba a desserializacao`() =
        runTest {
            // A API ganha coluna sem versionar payload. Já aconteceu:
            // /mensagens ganhou `next_cursor` na Fase 0.
            server.enqueue(
                MockResponse()
                    .setResponseCode(200)
                    .setHeader("Content-Type", "application/json")
                    .setBody(
                        """{"empresas":[{"id":1,"nome":"VSA","campo_novo_do_futuro":42}],
                            "meta_nova":{"x":1}}""",
                    ),
            )

            assertEquals(1, repo().empresas().size)
        }
}

/** Dublê em memória — o real depende do Keystore do Android. */
private class FakeSessaoStore : SessaoStore {
    private val _estado = MutableStateFlow(Sessao())
    override val estado: StateFlow<Sessao> = _estado

    override val token: String? get() = _estado.value.token
    override val empresaId: Long? get() = _estado.value.empresaId

    /** Atalho de leitura pros asserts. */
    val nome: String? get() = _estado.value.nomeUsuario

    override fun salvarToken(token: String, nomeUsuario: String?) {
        _estado.value = _estado.value.copy(token = token, nomeUsuario = nomeUsuario)
    }

    override fun salvarEmpresa(empresaId: Long, nome: String?) {
        _estado.value = _estado.value.copy(empresaId = empresaId, empresaNome = nome)
    }

    override fun limpar() {
        _estado.value = Sessao()
    }
}
