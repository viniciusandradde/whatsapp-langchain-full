package com.vsanexus.atendimento.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Better Auth, que vive no Next.js — host DIFERENTE da API.
 *
 * `chat.vsanexus.com/api/auth/…` (frontend) contra `api.vsanexus.com/api/…`
 * (FastAPI). Não é escolha de arquitetura, é onde cada um está: o Better Auth é
 * um handler do Next e não existe no FastAPI.
 *
 * Nota pra quem editar: NÃO escreva barra seguida de asterisco dentro de
 * comentário. Diferente de Java, comentário de bloco em Kotlin ANINHA — um
 * caminho como "api/auth/" terminado em asterisco abre um comentário que nunca
 * fecha, e o compilador acusa "Unclosed comment" no FIM do arquivo, longe da
 * causa. Foi assim que a fatia 2 falhou no primeiro build.
 */
interface AuthApi {
    /**
     * Login por email e senha.
     *
     * Devolve [Response] cru de propósito: o token de sessão vem no HEADER
     * `set-auth-token` (plugin `bearer` do Better Auth), não no corpo. Com
     * `LoginResponse` direto não haveria como ler header algum.
     */
    @POST("api/auth/sign-in/email")
    suspend fun login(@Body body: LoginRequest): Response<LoginResponse>

    @POST("api/auth/sign-out")
    suspend fun logout(): Response<Unit>
}

/**
 * API de atendimento (FastAPI).
 *
 * Autenticação pelo token de sessão no `Authorization: Bearer`, injetado pelo
 * interceptor — nunca por header de identidade. O backend valida o token em
 * `auth.session` e deriva o usuário do banco; um `X-User-Id` divergente é
 * ignorado (ver `server/dependencies.py::get_user_id_from_request`).
 *
 * `X-Empresa-Id` continua sendo enviado porque a API precisa saber a empresa
 * ATIVA, mas ela valida membership — o app não escolhe tenant à vontade.
 */
interface AtendimentoApi {
    /**
     * Lista atendimentos da aba pedida.
     *
     * O filtro por permissão (`atendimento.read.own` vs `.all`) é aplicado no
     * SERVIDOR. O app não reimplementa RBAC: pede a aba e recebe o que o
     * usuário tem direito de ver.
     */
    @GET("api/atendimentos")
    suspend fun listar(
        @Query("tipo") tipo: String = "aguardando",
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0,
        @Query("q") busca: String? = null,
    ): AtendimentosResponse

    @GET("api/atendimentos/{id}")
    suspend fun detalhe(@Path("id") id: Long): AtendimentoDto

    /**
     * Mensagens da conversa, das mais RECENTES pra trás.
     *
     * Sem [beforeId] vêm as últimas `limit`; com ele, a página anterior. É o
     * cursor que a Fase 0 adicionou — antes o endpoint devolvia as mais antigas
     * e conversas longas escondiam justamente as mensagens novas.
     */
    @GET("api/atendimentos/{id}/mensagens")
    suspend fun mensagens(
        @Path("id") id: Long,
        @Query("limit") limit: Int = 50,
        @Query("before_id") beforeId: Long? = null,
    ): MensagensResponse

    @POST("api/atendimentos/{id}/responder")
    suspend fun responder(
        @Path("id") id: Long,
        @Body body: ResponderRequest,
    ): Response<Unit>

    @POST("api/atendimentos/{id}/claim")
    suspend fun assumir(@Path("id") id: Long): Response<Unit>

    @POST("api/atendimentos/{id}/marcar-lido")
    suspend fun marcarLido(@Path("id") id: Long): Response<Unit>

    /**
     * Empresas às quais o usuário tem acesso — alimenta o seletor.
     *
     * Verificado contra produção: `{"empresas": [...]}`, e cada item traz muito
     * mais que id/nome (endereço fiscal, cores de white-label, config). O DTO
     * pega só o que a UI usa; `ignoreUnknownKeys` descarta o resto.
     */
    @GET("api/empresas")
    suspend fun empresas(): EmpresasResponse
}
