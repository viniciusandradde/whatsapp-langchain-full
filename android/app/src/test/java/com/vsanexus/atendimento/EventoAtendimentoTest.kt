package com.vsanexus.atendimento

import com.vsanexus.atendimento.data.remote.EventoAtendimento
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Contrato do payload que o Postgres publica em `atendimento_event`.
 *
 * Os JSONs abaixo são os que os triggers da migration 145 realmente montam, com
 * as chaves na mesma grafia. Este teste existe porque o app decide o que
 * atualizar a partir desse payload: um `atendimento_id` que deixasse de casar
 * faria a conversa aberta parar de receber mensagem em tempo real sem nenhum
 * erro visível — nada quebra, só silencia.
 */
class EventoAtendimentoTest {
    private val json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
        explicitNulls = false
    }

    @Test
    fun `mensagem inbound casa atendimento e pede atualizacao`() {
        val evt =
            json.decodeFromString<EventoAtendimento>(
                """
                {"event":"mensagem","empresa_id":1,"atendimento_id":446,
                 "message_id":98765,"kind":"inbound"}
                """
            )

        assertEquals("mensagem", evt.event)
        assertEquals(446L, evt.atendimentoId)
        assertTrue(evt.mudouConversa)
    }

    @Test
    fun `status_changed tambem pede atualizacao`() {
        val evt =
            json.decodeFromString<EventoAtendimento>(
                """{"event":"status_changed","empresa_id":1,"atendimento_id":9}"""
            )

        assertEquals(9L, evt.atendimentoId)
        assertTrue(evt.mudouConversa)
    }

    /**
     * O `connected` é do nosso próprio gerador, não de trigger, e vem sem
     * `atendimento_id`. Tratar como mudança faria o app ressincronizar a lista a
     * cada reconexão — inclusive nas reconexões em rajada de rede instável.
     */
    @Test
    fun `connected nao e mudanca de conversa`() {
        val evt =
            json.decodeFromString<EventoAtendimento>("""{"event":"connected","empresa_id":1}""")

        assertNull(evt.atendimentoId)
        assertFalse(evt.mudouConversa)
    }

    /**
     * Chave nova no payload não pode derrubar o app: o backend evolui os
     * triggers sem versionar o evento.
     */
    @Test
    fun `campo desconhecido no payload e ignorado`() {
        val evt =
            json.decodeFromString<EventoAtendimento>(
                """{"event":"mensagem","atendimento_id":7,"campo_do_futuro":"x"}"""
            )

        assertEquals(7L, evt.atendimentoId)
        assertTrue(evt.mudouConversa)
    }
}
