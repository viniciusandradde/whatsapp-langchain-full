package com.vsanexus.atendimento

import com.vsanexus.atendimento.data.Aba
import com.vsanexus.atendimento.data.ConversasRepository
import com.vsanexus.atendimento.data.Sincronizacao
import com.vsanexus.atendimento.data.local.ConversaDao
import com.vsanexus.atendimento.data.local.ConversaEntity
import com.vsanexus.atendimento.data.local.Credenciais
import com.vsanexus.atendimento.data.local.Sessao
import com.vsanexus.atendimento.data.local.SessaoStore
import com.vsanexus.atendimento.data.remote.ApplyTagsRequest
import com.vsanexus.atendimento.data.remote.AtendentesResponse
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.AtendimentoDto
import com.vsanexus.atendimento.data.remote.AtendimentosResponse
import com.vsanexus.atendimento.data.remote.ClienteDetailResponse
import com.vsanexus.atendimento.data.remote.ClienteTagRequest
import com.vsanexus.atendimento.data.remote.CloseRequest
import com.vsanexus.atendimento.data.remote.DepartamentosResponse
import com.vsanexus.atendimento.data.remote.EmpresasResponse
import com.vsanexus.atendimento.data.remote.MensagensResponse
import com.vsanexus.atendimento.data.remote.NotaRequest
import com.vsanexus.atendimento.data.remote.PushTokenRequest
import com.vsanexus.atendimento.data.remote.ResponderRequest
import com.vsanexus.atendimento.data.remote.TagsResponse
import com.vsanexus.atendimento.data.remote.TransferRequest
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.Response

/**
 * Regras do cache de conversas.
 *
 * O que importa aqui não é "chamou a API": é o comportamento na FALHA. Erro de
 * rede não pode esvaziar a lista, porque no celular a rede cai o tempo todo e
 * uma tela vazia parece que o atendimento sumiu.
 */
class ConversasRepositoryTest {
    private fun repo(api: AtendimentoApi, dao: ConversaDao, empresaId: Long? = 1L) =
        ConversasRepository(api, dao, FakeSessao(empresaId))

    @Test
    fun `sincronizar substitui o conteudo da aba`() =
        runTest {
            val dao = FakeDao()
            val api =
                FakeApi(
                    aoListar = {
                        AtendimentosResponse(
                            listOf(
                                dto(1, "Ana"),
                                dto(2, "Bruno"),
                            ),
                        )
                    },
                )

            val r = repo(api, dao).sincronizar(Aba.NAO_RESOLVIDAS)

            assertTrue(r is Sincronizacao.Ok)
            assertEquals(listOf("Ana", "Bruno"), dao.salvos.map { it.clienteNome })
            // Substituir, não acumular: conversa que saiu da aba tem que sair
            // da lista.
            assertEquals(1, dao.vezesQueLimpou)
        }

    @Test
    fun `falha de rede PRESERVA o cache`() =
        runTest {
            val dao = FakeDao(existentes = listOf(entidade(9, "Já estava aqui")))
            val api = FakeApi(aoListar = { throw java.io.IOException("sem rede") })

            val r = repo(api, dao).sincronizar(Aba.NAO_RESOLVIDAS)

            assertTrue(r is Sincronizacao.Falha)
            // O ponto do teste: NADA foi apagado.
            assertEquals(0, dao.vezesQueLimpou)
            assertEquals(1, dao.observar(1L, "nao_resolvidas").first().size)
        }

    @Test
    fun `sem empresa ativa nao chama a API nem devolve lista`() =
        runTest {
            val dao = FakeDao()
            var chamou = false
            val api = FakeApi(aoListar = { chamou = true; AtendimentosResponse() })

            val r = repo(api, dao, empresaId = null).sincronizar(Aba.NAO_RESOLVIDAS)

            assertTrue(r is Sincronizacao.Falha)
            // Sem empresa a API responderia 403 (get_empresa_context exige
            // membership); chamar seria só gastar rede pra tomar erro.
            assertEquals(false, chamou)
            assertEquals(emptyList<ConversaEntity>(), repo(api, dao, null).observar(Aba.TODAS).first())
        }

    @Test
    fun `situacao e nao lidas do servidor chegam na entidade`() =
        runTest {
            // O app NÃO recalcula a situação: ela vem derivada do servidor, pra
            // web e app dizerem a mesma coisa. Se o mapeamento perder o campo, o
            // cartão mostra "Com a IA" (o default) numa conversa em whitelist —
            // exatamente a confusão que a mudança veio desfazer.
            val dao = FakeDao()
            val api =
                FakeApi(
                    aoListar = {
                        AtendimentosResponse(
                            listOf(
                                AtendimentoDto(
                                    id = 1,
                                    empresaId = 1,
                                    clienteNome = "Ana",
                                    status = "aguardando",
                                    situacao = "sem_automacao",
                                    naoLidas = 3,
                                ),
                            ),
                        )
                    },
                )

            repo(api, dao).sincronizar(Aba.NAO_RESOLVIDAS)

            assertEquals("sem_automacao", dao.salvos.single().situacao)
            assertEquals(3, dao.salvos.single().naoLidas)
        }

    @Test
    fun `payload sem os campos novos nao esconde a conversa`() =
        runTest {
            // Servidor antigo (ou rollback) não manda `situacao`. A conversa tem
            // que aparecer mesmo assim — lista vazia é pior que selo impreciso.
            val dao = FakeDao()
            val api = FakeApi(aoListar = { AtendimentosResponse(listOf(dto(9, "Bruno"))) })

            repo(api, dao).sincronizar(Aba.NAO_RESOLVIDAS)

            assertEquals("com_ia", dao.salvos.single().situacao)
            assertEquals(0, dao.salvos.single().naoLidas)
        }

    @Test
    fun `busca em branco nao vai como parametro pro servidor`() =
        runTest {
            val dao = FakeDao()
            var buscaRecebida: String? = "não-sobrescrito"
            val api =
                FakeApi(
                    aoListar = { AtendimentosResponse() },
                    registraBusca = { buscaRecebida = it },
                )

            repo(api, dao).sincronizar(Aba.TODAS, busca = "   ")

            // `q` vazio no endpoint viraria filtro por string vazia; melhor
            // omitir.
            assertEquals(null, buscaRecebida)
        }
}

private fun dto(id: Long, nome: String) =
    AtendimentoDto(id = id, empresaId = 1, clienteNome = nome, status = "aguardando")

private fun entidade(id: Long, nome: String) =
    ConversaEntity(
        id = id,
        empresaId = 1,
        aba = "nao_resolvidas",
        clienteNome = nome,
        clienteTelefone = null,
        status = "aguardando",
        prioridade = null,
        protocolo = null,
        atribuidoA = null,
        departamentoId = null,
        conexaoNome = null,
        ultimaMensagemEm = null,
    )

private class FakeSessao(private val empresa: Long?) : SessaoStore {
    override val estado: StateFlow<Sessao> = MutableStateFlow(Sessao(token = "t", empresaId = empresa))
    override val token: String? = "t"
    override val empresaId: Long? = empresa

    override fun salvarToken(token: String, nomeUsuario: String?) = Unit

    override fun salvarEmpresa(empresaId: Long, nome: String?) = Unit

    override val credenciais: Credenciais? = null

    override fun salvarCredenciais(email: String, senha: String) = Unit

    override fun limpar() = Unit

    override fun sair() = Unit
}

private class FakeDao(existentes: List<ConversaEntity> = emptyList()) : ConversaDao {
    val salvos = mutableListOf<ConversaEntity>()
    var vezesQueLimpou = 0
    private val conteudo = MutableStateFlow(existentes)

    override fun observar(empresaId: Long, aba: String): Flow<List<ConversaEntity>> = conteudo

    override suspend fun salvar(itens: List<ConversaEntity>) {
        salvos += itens
        conteudo.value = conteudo.value + itens
    }

    override suspend fun limparAba(empresaId: Long, aba: String) {
        vezesQueLimpou++
        conteudo.value = emptyList()
    }

    override suspend fun limparTudo() {
        conteudo.value = emptyList()
    }
}

private class FakeApi(
    private val aoListar: () -> AtendimentosResponse,
    private val registraBusca: (String?) -> Unit = {},
) : AtendimentoApi {
    override suspend fun listar(
        tipo: String,
        limit: Int,
        offset: Int,
        busca: String?,
    ): AtendimentosResponse {
        registraBusca(busca)
        return aoListar()
    }

    override suspend fun detalhe(id: Long) = dto(id, "x")

    override suspend fun mensagens(
        id: Long,
        limit: Int,
        beforeId: Long?,
        incluirMidia: Boolean,
    ) = MensagensResponse()

    override suspend fun midia(
        id: Long,
        mensagemId: Long,
        lado: String,
    ): Response<ResponseBody> = Response.success(ByteArray(0).toResponseBody())

    override suspend fun responder(id: Long, body: ResponderRequest) = vazio()

    // Este fake é da LISTA de conversas, que não envia mídia. Existe só porque
    // implementar a interface obriga — o envio de anexo é exercitado onde ele
    // importa, no mapeamento de bolhas (BolhaTest).
    override suspend fun responderMidia(
        id: Long,
        arquivo: MultipartBody.Part,
        legenda: RequestBody,
    ) = vazio()

    override suspend fun assumir(id: Long) = vazio()

    override suspend fun devolverParaIa(id: Long) = vazio()

    override suspend fun marcarLido(id: Long) = vazio()

    override suspend fun empresas() = EmpresasResponse()

    // Fatia 3 — a lista não usa nenhum destes; existem porque a interface
    // obriga. As ações são exercitadas nos testes do próprio módulo.
    override suspend fun encerrar(id: Long, body: CloseRequest) = vazio()

    override suspend fun transferir(id: Long, body: TransferRequest) = vazio()

    override suspend fun criarNota(id: Long, body: NotaRequest) = vazio()

    override suspend fun tagsDoAtendimento(id: Long) = TagsResponse()

    override suspend fun aplicarTags(id: Long, body: ApplyTagsRequest) = vazio()

    override suspend fun catalogoTags(somenteAtivas: Boolean) = TagsResponse()

    override suspend fun departamentos() = DepartamentosResponse()

    override suspend fun atendentesEmpresa() = AtendentesResponse()

    override suspend fun cliente(id: Long) = ClienteDetailResponse()

    override suspend fun adicionarTagCliente(id: Long, body: ClienteTagRequest) = vazio()

    override suspend fun removerTagCliente(id: Long, tag: String) = vazio()

    override suspend fun atendimentosAnteriores(
        id: Long,
        limit: Int,
        excludeId: Long?,
    ) = AtendimentosResponse()

    override suspend fun registrarPush(body: PushTokenRequest) = vazio()

    override suspend fun removerPush(body: PushTokenRequest) = vazio()

    private fun vazio(): Response<Unit> = Response.success(Unit)
}
