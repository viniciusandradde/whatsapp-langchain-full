package com.vsanexus.atendimento.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * DTOs espelhando as respostas reais da API.
 *
 * Todo campo é opcional com default. A API é um projeto vivo — endpoint ganha
 * coluna sem aviso, e `ignoreUnknownKeys` cobre campo NOVO, não campo AUSENTE.
 * Um `String` não-nulo que vem null derruba a desserialização inteira e o app
 * mostra erro numa tela que deveria só listar conversas.
 */

@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

/**
 * Corpo do sign-in do Better Auth.
 *
 * O que importa não está aqui: o token de sessão vem no HEADER
 * `set-auth-token` (plugin `bearer`), não no corpo. Ver [AuthApi.login].
 */
@Serializable
data class LoginResponse(
    val user: UsuarioDto? = null,
    val redirect: Boolean? = null,
)

@Serializable
data class UsuarioDto(
    val id: String = "",
    val name: String? = null,
    val email: String? = null,
    val image: String? = null,
)

@Serializable
data class AtendimentosResponse(
    val atendimentos: List<AtendimentoDto> = emptyList(),
)

@Serializable
data class AtendimentoDto(
    val id: Long = 0,
    @SerialName("empresa_id") val empresaId: Long = 0,
    @SerialName("cliente_id") val clienteId: Long = 0,
    @SerialName("cliente_nome") val clienteNome: String? = null,
    @SerialName("cliente_telefone") val clienteTelefone: String? = null,
    val status: String = "aguardando",
    @SerialName("agente_atual") val agenteAtual: String? = null,
    @SerialName("assigned_to_user_id") val assignedToUserId: String? = null,
    @SerialName("departamento_id") val departamentoId: Long? = null,
    val prioridade: String? = null,
    val protocolo: String? = null,
    // Triagem que a IA preenche via tools (mig 061). É o que permite decidir o
    // que atender SEM abrir a conversa — o operador lê prioridade, sentimento e
    // categoria direto na lista.
    val classificacao: String? = null,
    val sentimento: String? = null,
    @SerialName("resumo_ia") val resumoIa: String? = null,
    @SerialName("triagem_completa") val triagemCompleta: Boolean? = null,
    /**
     * Situação derivada no servidor (`derivar_situacao`).
     *
     * Default otimista: servidor antigo não manda o campo, e a conversa deve
     * aparecer mesmo assim — lista vazia é pior que selo impreciso.
     */
    val situacao: String = "com_ia",
    @SerialName("nao_lidas") val naoLidas: Int = 0,
    /** Tags do CLIENTE — identificam a pessoa e alimentam as abas. */
    @SerialName("cliente_tags") val clienteTags: List<String> = emptyList(),
    @SerialName("last_message_at") val lastMessageAt: String? = null,
    @SerialName("conexao_nome") val conexaoNome: String? = null,
)

@Serializable
data class MensagensResponse(
    @SerialName("atendimento_id") val atendimentoId: Long = 0,
    val mensagens: List<MensagemDto> = emptyList(),
    /** Cursor pra página anterior (histórico). Null = início da conversa. */
    @SerialName("next_cursor") val nextCursor: Long? = null,
)

@Serializable
data class MensagemDto(
    val id: Long = 0,
    @SerialName("agent_id") val agentId: String? = null,
    @SerialName("incoming_message") val incomingMessage: String? = null,
    @SerialName("media_url") val mediaUrl: String? = null,
    @SerialName("media_type") val mediaType: String? = null,
    @SerialName("normalized_input") val normalizedInput: String? = null,
    val response: String? = null,
    val status: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("processed_at") val processedAt: String? = null,
    /** True quando é nota interna do operador, não mensagem enviada. */
    val interna: Boolean? = null,
    @SerialName("criado_por_user_id") val criadoPorUserId: String? = null,
    /**
     * Mídia enviada PELO OPERADOR (mig 146) — contraparte outbound de
     * [mediaUrl]. Separada porque o lado da bolha vem da origem do campo.
     */
    @SerialName("response_media_url") val responseMediaUrl: String? = null,
    @SerialName("response_media_type") val responseMediaType: String? = null,
    /**
     * Há mídia, mas o conteúdo NÃO veio no payload.
     *
     * O app pede `incluir_midia=false`, então estes booleanos são o que diz se a
     * bolha é de anexo — [mediaUrl] e [responseMediaUrl] vêm nulos, e os bytes
     * são buscados em `/mensagens/{id}/midia`.
     */
    @SerialName("media_disponivel") val mediaDisponivel: Boolean = false,
    @SerialName("response_media_disponivel") val responseMediaDisponivel: Boolean = false,
)

@Serializable
data class ResponderRequest(
    val conteudo: String,
)

@Serializable
data class EmpresaDto(
    val id: Long = 0,
    val nome: String = "",
    @SerialName("nome_exibicao") val nomeExibicao: String? = null,
    @SerialName("logo_path") val logoPath: String? = null,
)

@Serializable
data class EmpresasResponse(
    val empresas: List<EmpresaDto> = emptyList(),
)

// --- Fatia 3: ações da conversa (paridade com o drawer do painel web) ---

@Serializable
data class CloseRequest(
    /** `resolvido` ou `abandonado` — os dois únicos status finais. */
    val status: String,
)

/**
 * Destino da transferência. O backend exige EXATAMENTE um dos dois campos —
 * atendente OU departamento — e o app monta um ou outro, nunca ambos.
 */
@Serializable
data class TransferRequest(
    @SerialName("user_id") val userId: String? = null,
    @SerialName("departamento_id") val departamentoId: Long? = null,
)

@Serializable
data class NotaRequest(
    val texto: String,
)

/** Delta idempotente de tags do atendimento: só o que muda viaja. */
@Serializable
data class ApplyTagsRequest(
    val add: List<Long> = emptyList(),
    val remove: List<Long> = emptyList(),
)

/** Tag do catálogo da empresa (a cor vem como hex, ex. "#F97316"). */
@Serializable
data class TagDto(
    val id: Long = 0,
    val nome: String = "",
    val cor: String? = null,
    val descricao: String? = null,
    val ativo: Boolean = true,
    /** Presentes só em GET tags do atendimento — origem da aplicação. */
    @SerialName("aplicado_por_ia") val aplicadoPorIa: Boolean? = null,
)

@Serializable
data class TagsResponse(
    val items: List<TagDto> = emptyList(),
)

@Serializable
data class DepartamentoDto(
    val id: Long = 0,
    val nome: String = "",
    val ativo: Boolean = true,
)

@Serializable
data class DepartamentosResponse(
    val departamentos: List<DepartamentoDto> = emptyList(),
)

@Serializable
data class AtendenteDto(
    @SerialName("user_id") val userId: String = "",
    val nome: String? = null,
    val email: String? = null,
    @SerialName("is_active") val isActive: Boolean = true,
    /** online | ausente | pausa | offline | null (nunca ficou online). */
    @SerialName("atendente_status") val atendenteStatus: String? = null,
    @SerialName("count_atendimentos_abertos") val atendimentosAbertos: Int = 0,
)

@Serializable
data class AtendentesResponse(
    val atendentes: List<AtendenteDto> = emptyList(),
)

@Serializable
data class ClienteDto(
    val id: Long = 0,
    val nome: String? = null,
    val telefone: String? = null,
    /** Tags do CLIENTE são texto livre — diferente das tags de atendimento. */
    val tags: List<String> = emptyList(),
)

@Serializable
data class ClienteDetailResponse(
    val cliente: ClienteDto = ClienteDto(),
)

@Serializable
data class ClienteTagRequest(
    val tag: String,
)
