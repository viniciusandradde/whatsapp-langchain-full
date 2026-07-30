package com.vsanexus.atendimento.data

import com.vsanexus.atendimento.data.local.ConversaDao
import com.vsanexus.atendimento.data.local.ConversaEntity
import com.vsanexus.atendimento.data.local.SessaoStore
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.AtendimentoDto
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import javax.inject.Inject
import javax.inject.Singleton

/**
 * As abas da lista — as mesmas cinco do painel web, espelhando o Chatvolt.
 *
 * "Grupos" saiu: o servidor sempre devolveu lista vazia pra ela
 * (`shared/atendimento.py` faz short-circuit), então era uma aba que só
 * mostrava "nenhuma conversa" e ocupava um quinto da barra no celular.
 *
 * Títulos curtos de propósito: na largura de um telefone, cinco abas só cabem
 * com rótulo enxuto — "Humano Solicitado" viraria duas linhas.
 */
enum class Aba(val valor: String, val titulo: String) {
    NAO_RESOLVIDAS("nao_resolvidas", "Abertas"),
    NAO_LIDAS("nao_lidas", "Não lidas"),
    HUMANO_SOLICITADO("humano_solicitado", "Humano"),
    RESOLVIDAS("resolvidas", "Resolvidas"),
    TODAS("todas", "Todas"),
}

sealed interface Sincronizacao {
    data object Ok : Sincronizacao

    /** Falhou, mas há cache — a UI mostra a lista antiga com um aviso. */
    data class Falha(val mensagem: String) : Sincronizacao
}

@Singleton
class ConversasRepository
@Inject
constructor(
    private val api: AtendimentoApi,
    private val dao: ConversaDao,
    private val sessao: SessaoStore,
) {
    /**
     * Lista observada do BANCO, nunca da rede.
     *
     * É o que dá a sensação de app nativo: abrir a tela mostra a última lista
     * conhecida no primeiro frame, e a sincronização atualiza por baixo. Se a
     * UI lesse da rede, cada abertura teria spinner.
     */
    fun observar(aba: Aba): Flow<List<ConversaEntity>> {
        val empresaId = sessao.empresaId ?: return flowOf(emptyList())
        return dao.observar(empresaId, aba.valor)
    }

    /**
     * Busca no servidor e substitui o conteúdo da aba.
     *
     * Erro NÃO limpa o cache: perder a lista por causa de rede instável é pior
     * que mostrar dado de um minuto atrás. A UI recebe [Sincronizacao.Falha] e
     * decide se avisa.
     */
    suspend fun sincronizar(aba: Aba, busca: String? = null): Sincronizacao {
        val empresaId = sessao.empresaId ?: return Sincronizacao.Falha("Sem empresa ativa.")
        return try {
            val resp = api.listar(tipo = aba.valor, limit = 100, busca = busca?.ifBlank { null })
            dao.substituirAba(
                empresaId = empresaId,
                aba = aba.valor,
                itens = resp.atendimentos.map { it.toEntity(empresaId, aba.valor) },
            )
            Sincronizacao.Ok
        } catch (e: Exception) {
            Sincronizacao.Falha("Não foi possível atualizar a lista.")
        }
    }

    /** Chamado no logout e na troca de empresa — cache de outro tenant não fica. */
    suspend fun limparCache() = dao.limparTudo()
}

private fun AtendimentoDto.toEntity(empresaId: Long, aba: String) =
    ConversaEntity(
        id = id,
        empresaId = empresaId,
        aba = aba,
        clienteNome = clienteNome,
        clienteTelefone = clienteTelefone,
        status = status,
        prioridade = prioridade,
        protocolo = protocolo,
        agenteAtual = agenteAtual,
        classificacao = classificacao,
        sentimento = sentimento,
        resumoIa = resumoIa,
        triagemCompleta = triagemCompleta == true,
        atribuidoA = assignedToUserId,
        departamentoId = departamentoId,
        conexaoNome = conexaoNome,
        ultimaMensagemEm = lastMessageAt,
        situacao = situacao,
        naoLidas = naoLidas,
    )
