package com.vsanexus.atendimento.data.remote

import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
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
        /**
         * O app pede SEM mídia: a coluna guarda data-URL base64, e uma página de
         * 50 mensagens com anexos passava de dezenas de MB (medido em produção:
         * PDF de 5 MB numa linha). Com `false` vem só `media_disponivel`, e cada
         * mídia é buscada em [midia] quando aparece na tela.
         */
        @Query("incluir_midia") incluirMidia: Boolean = false,
    ): MensagensResponse

    /**
     * Bytes de UMA mídia da conversa.
     *
     * Devolve [ResponseBody] cru, não um DTO: é binário, e o corpo é lido em
     * streaming pro arquivo de cache sem materializar duas vezes na memória.
     *
     * `lado`: `in` é o que o cliente mandou, `out` o que o operador mandou —
     * colunas diferentes no banco (mig 146).
     */
    @GET("api/atendimentos/{id}/mensagens/{mensagemId}/midia")
    suspend fun midia(
        @Path("id") id: Long,
        @Path("mensagemId") mensagemId: Long,
        @Query("lado") lado: String = "in",
    ): Response<ResponseBody>

    @POST("api/atendimentos/{id}/responder")
    suspend fun responder(
        @Path("id") id: Long,
        @Body body: ResponderRequest,
    ): Response<Unit>

    /**
     * Envia anexo ou nota de voz do operador.
     *
     * Multipart e não JSON com base64: o corpo carrega o arquivo bruto, sem o
     * inchaço de 33% da codificação, e o OkHttp faz streaming a partir do
     * arquivo em vez de montar a coisa toda na memória — o que importa quando é
     * uma foto de 8 MB num aparelho apertado.
     *
     * Só conexões Evolution suportam mídia hoje; nas outras a API devolve 400
     * com o motivo, em vez de aceitar e não entregar.
     */
    @Multipart
    @POST("api/atendimentos/{id}/responder-midia")
    suspend fun responderMidia(
        @Path("id") id: Long,
        @Part arquivo: MultipartBody.Part,
        @Part("legenda") legenda: RequestBody,
    ): Response<Unit>

    /**
     * "Atender": tira da fila da IA e vira `em_andamento` com dono.
     *
     * Enquanto tem dono, o worker **cala o agente** — é justamente o objetivo.
     * Atenção: o backend também envia ao cliente "Você foi transferido para o
     * atendente X" (mesmo comportamento do painel web).
     */
    @POST("api/atendimentos/{id}/claim")
    suspend fun assumir(@Path("id") id: Long): Response<Unit>

    /**
     * Devolve pra fila da IA — desfaz o [assumir].
     *
     * **Nada é enviado ao cliente.** Existe porque assumir era irreversível: as
     * saídas eram fechar (dispara a pesquisa de satisfação) ou transferir (avisa
     * o cliente), e nenhuma serve pra corrigir um toque errado na tela.
     */
    @POST("api/atendimentos/{id}/devolver-ia")
    suspend fun devolverParaIa(@Path("id") id: Long): Response<Unit>

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

    // --- Fatia 3: ações da conversa ---

    /**
     * Encerra o atendimento como `resolvido` ou `abandonado`.
     *
     * Resolvido pode disparar a pesquisa de satisfação no WhatsApp do cliente
     * (config da empresa) — por isso a tela SEMPRE confirma antes.
     */
    @POST("api/atendimentos/{id}/close")
    suspend fun encerrar(
        @Path("id") id: Long,
        @Body body: CloseRequest,
    ): Response<Unit>

    /**
     * Transfere para um atendente OU um departamento (exatamente um).
     *
     * Departamento: limpa o dono, volta pra `aguardando` e o backend AVISA o
     * cliente da mudança de setor. Atendente: mantém `em_andamento` com o novo
     * dono, sem aviso.
     */
    @POST("api/atendimentos/{id}/transfer")
    suspend fun transferir(
        @Path("id") id: Long,
        @Body body: TransferRequest,
    ): Response<Unit>

    /**
     * Nota interna: entra na timeline mas NUNCA sai pro cliente (gate no
     * backend). Exige a permissão `atendimento.nota_interna.criar` — 403 vira
     * aviso legível na tela.
     */
    @POST("api/atendimentos/{id}/nota")
    suspend fun criarNota(
        @Path("id") id: Long,
        @Body body: NotaRequest,
    ): Response<Unit>

    /** Tags aplicadas neste atendimento (com origem humano/IA). */
    @GET("api/atendimentos/{id}/tags")
    suspend fun tagsDoAtendimento(@Path("id") id: Long): TagsResponse

    /** Aplica o delta de tags. Exige `atendimento.tag.aplicar`. */
    @POST("api/atendimentos/{id}/tags")
    suspend fun aplicarTags(
        @Path("id") id: Long,
        @Body body: ApplyTagsRequest,
    ): Response<Unit>

    /** Catálogo de tags da empresa — leitura liberada a qualquer membro. */
    @GET("api/tags")
    suspend fun catalogoTags(
        @Query("only_ativos") somenteAtivas: Boolean = true,
    ): TagsResponse

    /** Departamentos da empresa — destinos possíveis de transferência. */
    @GET("api/departamentos")
    suspend fun departamentos(): DepartamentosResponse

    /**
     * Atendentes da empresa com status de presença e carga — o seletor de
     * transferência mostra só os online e ativos, com o count pra ajudar a
     * escolher (mesma regra do popover web).
     */
    @GET("api/atendentes/empresa-status")
    suspend fun atendentesEmpresa(): AtendentesResponse

    /** Ficha do cliente — nome, telefone e as tags de CLIENTE (texto livre). */
    @GET("api/clientes/{id}")
    suspend fun cliente(@Path("id") id: Long): ClienteDetailResponse

    /** Marca uma tag no cliente. Idempotente (204 mesmo se já existia). */
    @POST("api/clientes/{id}/tags")
    suspend fun adicionarTagCliente(
        @Path("id") id: Long,
        @Body body: ClienteTagRequest,
    ): Response<Unit>

    /**
     * Desmarca uma tag do cliente. DELETE com corpo não é universal no HTTP —
     * aqui a tag viaja no PATH, URL-encoded pelo Retrofit.
     */
    @DELETE("api/clientes/{id}/tags/{tag}")
    suspend fun removerTagCliente(
        @Path("id") id: Long,
        @Path("tag") tag: String,
    ): Response<Unit>

    /**
     * Atendimentos anteriores do mesmo cliente — contexto pro painel.
     * `exclude_id` tira o atual da lista.
     */
    @GET("api/clientes/{id}/atendimentos-anteriores")
    suspend fun atendimentosAnteriores(
        @Path("id") id: Long,
        @Query("limit") limit: Int = 3,
        @Query("exclude_id") excludeId: Long? = null,
    ): AtendimentosResponse
}
