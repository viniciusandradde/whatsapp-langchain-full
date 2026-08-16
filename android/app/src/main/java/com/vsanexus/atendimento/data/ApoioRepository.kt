package com.vsanexus.atendimento.data

import com.vsanexus.atendimento.data.remote.ApplyTagsRequest
import com.vsanexus.atendimento.data.remote.AtendenteDto
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.AtendimentoDto
import com.vsanexus.atendimento.data.remote.ClienteDto
import com.vsanexus.atendimento.data.remote.ClienteTagRequest
import com.vsanexus.atendimento.data.remote.ConexaoDto
import com.vsanexus.atendimento.data.remote.DepartamentoDto
import com.vsanexus.atendimento.data.remote.IniciarConversaRequest
import com.vsanexus.atendimento.data.remote.TagDto
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Catálogos e ficha do cliente — o que as folhas de ação da conversa
 * consomem (transferir, tags, painel do cliente).
 *
 * Stateless de propósito: cada folha busca ao abrir e descarta ao fechar.
 * São listas pequenas (departamentos, atendentes, tags) e mudam pouco, mas
 * mudam — cachear aqui envelheceria o seletor de transferência, que é
 * exatamente onde presença importa (atendente que ficou offline não deve
 * receber conversa).
 *
 * Todos os métodos devolvem null em falha; a folha mostra "não deu para
 * carregar" e oferece tentar de novo. Nenhuma dessas buscas merece derrubar
 * a conversa aberta.
 */
@Singleton
class ApoioRepository
@Inject
constructor(private val api: AtendimentoApi) {
    suspend fun catalogoTags(): List<TagDto>? =
        runCatching { api.catalogoTags().items }.getOrNull()

    suspend fun tagsDoAtendimento(id: Long): List<TagDto>? =
        runCatching { api.tagsDoAtendimento(id).items }.getOrNull()

    /**
     * Aplica o delta. Devolve mensagem de erro legível ou null no sucesso —
     * invertido dos demais porque aqui o motivo importa (403 de permissão é
     * acionável; falha de rede é retentável).
     */
    suspend fun aplicarTags(id: Long, add: List<Long>, remove: List<Long>): String? =
        try {
            val r = api.aplicarTags(id, ApplyTagsRequest(add = add, remove = remove))
            when {
                r.isSuccessful -> null
                r.code() == 403 -> "Você não tem permissão para alterar tags."
                else -> "Não foi possível salvar as tags."
            }
        } catch (e: Exception) {
            "Sem conexão. As tags não foram salvas."
        }

    suspend fun departamentos(): List<DepartamentoDto>? =
        runCatching { api.departamentos().departamentos.filter { it.ativo } }.getOrNull()

    /**
     * Atendentes elegíveis pra receber transferência: ativos e ONLINE — a
     * mesma regra do popover do painel web. Quem está em pausa/ausente/offline
     * não aparece; transferir para quem não está lá é perder o cliente de novo.
     */
    suspend fun atendentesOnline(): List<AtendenteDto>? =
        runCatching {
            api.atendentesEmpresa().atendentes.filter {
                it.isActive && it.atendenteStatus == "online"
            }
        }.getOrNull()

    suspend fun cliente(id: Long): ClienteDto? =
        runCatching { api.cliente(id).cliente }.getOrNull()

    /** Marca/desmarca tag do CLIENTE (texto livre). True = sucesso. */
    suspend fun alternarTagCliente(id: Long, tag: String, marcar: Boolean): Boolean =
        runCatching {
            val r =
                if (marcar) api.adicionarTagCliente(id, ClienteTagRequest(tag))
                else api.removerTagCliente(id, tag)
            r.isSuccessful
        }.getOrDefault(false)

    suspend fun atendimentosAnteriores(clienteId: Long, excludeId: Long): List<AtendimentoDto>? =
        runCatching {
            api.atendimentosAnteriores(clienteId, limit = 3, excludeId = excludeId).atendimentos
        }.getOrNull()

    /**
     * Conexões onde o app consegue INICIAR conversa: ativas e Evolution
     * (texto livre). WABA/Twilio exigem template HSM com variáveis — fluxo
     * do painel web, fora do escopo do app por ora.
     */
    suspend fun conexoesParaIniciar(): List<ConexaoDto>? =
        runCatching {
            api.conexoes().conexoes.filter {
                it.status == "active" && it.provider == "evolution"
            }
        }.getOrNull()

    /**
     * Conversa ativa (mig 170). Sucesso devolve o atendimento criado/anexado;
     * falha devolve a frase acionável do backend (409 opt-out/teto, 403 sem
     * permissão) ou uma genérica.
     */
    suspend fun iniciarConversa(
        telefone: String,
        nome: String?,
        mensagem: String,
    ): ResultadoIniciar {
        val resp =
            try {
                api.iniciarConversa(
                    IniciarConversaRequest(
                        telefone = telefone,
                        mensagem = mensagem,
                        nome = nome?.takeIf { it.isNotBlank() },
                    ),
                )
            } catch (_: Exception) {
                return ResultadoIniciar.Falha("Sem conexão. Tente de novo.")
            }
        if (!resp.isSuccessful) {
            val detalhe =
                runCatching { resp.errorBody()?.string() }.getOrNull()?.let { corpo ->
                    Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"")
                        .find(corpo)?.groupValues?.get(1)
                }
            return ResultadoIniciar.Falha(
                detalhe
                    ?: when (resp.code()) {
                        403 -> "Você não tem permissão para iniciar conversas."
                        else -> "Não foi possível iniciar a conversa. Tente novamente."
                    },
            )
        }
        val atd = resp.body()?.atendimento
            ?: return ResultadoIniciar.Falha("Resposta inesperada do servidor.")
        return ResultadoIniciar.Criada(atd)
    }
}

/** Resultado do [ApoioRepository.iniciarConversa]. */
sealed interface ResultadoIniciar {
    data class Criada(val atendimento: AtendimentoDto) : ResultadoIniciar

    data class Falha(val mensagem: String) : ResultadoIniciar
}
