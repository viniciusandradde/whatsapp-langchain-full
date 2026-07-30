package com.vsanexus.atendimento.data.remote

import com.vsanexus.atendimento.BuildConfig
import com.vsanexus.atendimento.data.local.SessaoStore
import com.vsanexus.atendimento.di.SseClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.flow.retryWhen
import kotlinx.coroutines.flow.shareIn
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Evento do canal `atendimento_event` do Postgres, repassado por SSE.
 *
 * Os triggers (mig 035, com `empresa_id` desde a 145) emitem dois nomes:
 * `mensagem` e `status_changed`. O servidor ainda manda um `connected` na
 * abertura e comentários de heartbeat, que o parser do OkHttp descarta.
 */
@Serializable
data class EventoAtendimento(
    val event: String = "",
    @SerialName("atendimento_id") val atendimentoId: Long? = null,
) {
    val mudouConversa: Boolean
        get() = event == "mensagem" || event == "status_changed"
}

/**
 * Stream de eventos da empresa ativa.
 *
 * **Um stream para todo o app, não um por tela.** Cada SSE aberto consome no
 * servidor uma conexão psycopg dedicada e fora do pool — `LISTEN` bloqueia a
 * conexão para outros usos. Por isso este objeto é `@Singleton` e expõe um
 * [SharedFlow]: a lista e a conversa aberta observam o MESMO stream e filtram
 * localmente pelo `atendimento_id`. Um stream por conversa gastaria uma conexão
 * de banco por tela aberta.
 *
 * `WhileSubscribed` desliga o stream quando ninguém observa (app em background) e
 * o religa na volta: reabrir custa um request, e manter aberto sem ninguém lendo
 * é uma conexão de banco parada no servidor.
 */
@Singleton
class EventosAtendimento
@Inject
constructor(
    @SseClient private val client: OkHttpClient,
    private val sessao: SessaoStore,
    private val json: Json,
) {
    private val escopo = CoroutineScope(SupervisorJob())

    private val _conectado = MutableStateFlow(false)

    /** Só para diagnóstico na UI; nada depende disto para funcionar. */
    val conectado: StateFlow<Boolean> = _conectado.asStateFlow()

    val eventos: SharedFlow<EventoAtendimento> =
        fluxo()
            // Reconexão é responsabilidade nossa: o EventSource do OkHttp não
            // reconecta sozinho. Sem isto, perder o sinal do celular por um
            // segundo deixaria o app sem tempo real até reabrir a tela.
            //
            // Só chega aqui quem fechou COM exceção. Os casos terminais
            // (deslogado, 401) fecham limpo e simplesmente encerram o fluxo —
            // insistir neles seria marretar o servidor com credencial inválida.
            .retryWhen { _, tentativa ->
                _conectado.value = false
                // Backoff com teto: o operador está olhando a tela, e um request
                // a cada poucos segundos não pesa no servidor.
                delay(minOf(2_000L * (tentativa + 1), 15_000L))
                true
            }
            // Rede de segurança: exceção que escapasse daqui subiria pro
            // `escopo`, e um SupervisorJob sem handler derruba o processo. Tempo
            // real quebrado é aceitável; app fechando na cara do operador não.
            .catch { }
            .onCompletion { _conectado.value = false }
            .shareIn(escopo, SharingStarted.WhileSubscribed(5_000), replay = 0)

    private fun fluxo(): Flow<EventoAtendimento> = callbackFlow {
        // Sem sessão não há o que ouvir. Fecha LIMPO para não entrar em laço de
        // reconexão deslogado.
        if (sessao.token == null) {
            close()
            return@callbackFlow
        }

        // Authorization e X-Empresa-Id NÃO são montados aqui: o interceptor do
        // OkHttpClient já os injeta, e é ele também que limpa a sessão no 401.
        // Repetir aqui criaria um segundo lugar para esquecer de atualizar.
        val req =
            Request.Builder()
                .url("${BuildConfig.API_BASE_URL}api/atendimentos/events")
                .build()

        val listener =
            object : EventSourceListener() {
                override fun onOpen(eventSource: EventSource, response: Response) {
                    _conectado.value = true
                }

                override fun onEvent(
                    eventSource: EventSource,
                    id: String?,
                    type: String?,
                    data: String,
                ) {
                    val evt =
                        runCatching { json.decodeFromString<EventoAtendimento>(data) }
                            .getOrNull() ?: return
                    // O nome vem no campo `event` do payload e também no `type`
                    // do SSE. Prefere o payload, e cai no `type` se faltar.
                    trySend(evt.copy(event = evt.event.ifBlank { type ?: "" }))
                }

                override fun onClosed(eventSource: EventSource) {
                    _conectado.value = false
                    // Fim normal do stream (deploy, timeout de proxy). Fecha COM
                    // exceção de propósito: é o `retryWhen` que reabre, e um
                    // close limpo encerraria o tempo real de vez.
                    close(StreamCaiu())
                }

                override fun onFailure(
                    eventSource: EventSource,
                    t: Throwable?,
                    response: Response?,
                ) {
                    _conectado.value = false
                    if (response?.code == 401) {
                        // Sessão morta. Reconectar não resolve, e o interceptor
                        // já limpou a sessão: a UI cai no login sozinha.
                        close()
                    } else {
                        close(t ?: StreamCaiu())
                    }
                }
            }

        val fonte = EventSources.createFactory(client).newEventSource(req, listener)
        awaitClose { fonte.cancel() }
    }
}

/** Queda de stream que DEVE ser retentada. */
private class StreamCaiu : Exception("stream de eventos caiu")
