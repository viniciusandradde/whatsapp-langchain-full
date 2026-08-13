package com.vsanexus.atendimento.push

import com.google.firebase.messaging.FirebaseMessaging
import com.vsanexus.atendimento.data.local.SessaoStore
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.PushTokenRequest
import kotlinx.coroutines.suspendCancellableCoroutine
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

/**
 * Registro do aparelho no backend (mig 168).
 *
 * Best-effort em tudo: push é conforto, não função vital — falha de registro
 * não pode quebrar login nem lista. O backend faz UPSERT por token trocando o
 * dono, então registrar de novo a cada abertura da lista é barato e cobre
 * troca de usuário e de empresa no mesmo aparelho.
 */
@Singleton
class PushRepository
@Inject
constructor(
    private val api: AtendimentoApi,
    private val sessao: SessaoStore,
) {
    /** Token atual do FCM. Null quando o Play Services não responde. */
    private suspend fun tokenAtual(): String? =
        suspendCancellableCoroutine { cont ->
            FirebaseMessaging.getInstance().token.addOnCompleteListener { tarefa ->
                cont.resume(if (tarefa.isSuccessful) tarefa.result else null)
            }
        }

    /** Registra o aparelho para a empresa ATIVA da sessão. */
    suspend fun registrar() {
        if (sessao.token == null || sessao.empresaId == null) return
        val t = tokenAtual() ?: return
        runCatching { api.registrarPush(PushTokenRequest(t)) }
    }

    /** O FCM girou o token — o serviço repassa pra cá. */
    suspend fun registrarToken(token: String) {
        if (sessao.token == null || sessao.empresaId == null) return
        runCatching { api.registrarPush(PushTokenRequest(token)) }
    }

    /**
     * Sair: o aparelho para de receber conversa da empresa. Chamado ANTES de
     * limpar a sessão — depois dela não há mais como autenticar a remoção.
     */
    suspend fun remover() {
        if (sessao.token == null || sessao.empresaId == null) return
        val t = tokenAtual() ?: return
        runCatching { api.removerPush(PushTokenRequest(t)) }
    }
}

/**
 * Qual conversa está na tela AGORA. O serviço de push consulta pra não
 * notificar a conversa que o operador já está lendo — o SSE cobre essa.
 */
@Singleton
class ConversaAtual @Inject constructor() {
    @Volatile var id: Long? = null
}
