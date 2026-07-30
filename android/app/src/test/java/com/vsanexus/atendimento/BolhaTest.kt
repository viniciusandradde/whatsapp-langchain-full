package com.vsanexus.atendimento

import com.vsanexus.atendimento.data.remote.MensagemDto
import com.vsanexus.atendimento.domain.Bolha
import com.vsanexus.atendimento.domain.Lado
import com.vsanexus.atendimento.domain.MARCADORES_INTERNOS
import com.vsanexus.atendimento.domain.paraBolhas
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A regra mais importante da timeline: marcador interno NÃO é bolha.
 *
 * Se vazar, o operador vê "[resposta superada — cliente escreveu de novo]" como
 * se tivesse sido enviado ao cliente, e pode responder por cima achando que a
 * IA já falou. Eu mesmo quase deixei esse marcador vazar no painel web quando
 * o criei — daí o teste ser por marcador, um a um.
 */
class BolhaTest {
    @Test
    fun `mensagem do cliente vira bolha de entrada`() {
        val b = MensagemDto(id = 1, incomingMessage = "Bom dia").paraBolhas()

        assertEquals(1, b.size)
        val t = b.first() as Bolha.Texto
        assertEquals(Lado.ENTRADA, t.lado)
        assertEquals("Bom dia", t.texto)
    }

    @Test
    fun `uma row com pergunta e resposta vira DUAS bolhas`() {
        // É o caso normal: o worker grava a inbound e depois o `response` na
        // MESMA row. Tratar como uma bolha esconderia metade da conversa.
        val b =
            MensagemDto(
                id = 1,
                incomingMessage = "Quando abre a rematrícula?",
                response = "As datas ainda não foram divulgadas.",
            ).paraBolhas()

        assertEquals(2, b.size)
        assertEquals(Lado.ENTRADA, (b[0] as Bolha.Texto).lado)
        assertEquals(Lado.SAIDA, (b[1] as Bolha.Texto).lado)
    }

    @Test
    fun `cada marcador interno NAO gera bolha de saida`() {
        // Um teste por marcador: se o backend criar um sexto e alguém esquecer
        // de adicionar na lista, é aqui que aparece.
        MARCADORES_INTERNOS.forEach { marcador ->
            val b =
                MensagemDto(
                    id = 1,
                    incomingMessage = "Oi",
                    response = "$marcador — texto interno]",
                ).paraBolhas()

            assertEquals(
                "marcador $marcador não deveria virar bolha",
                1,
                b.size,
            )
            assertEquals(Lado.ENTRADA, (b.first() as Bolha.Texto).lado)
        }
    }

    @Test
    fun `sao exatamente cinco marcadores, sincronizados com o worker`() {
        // Trava de consciência: mexer nesta lista sem mexer em
        // worker/processor.py (ou vice-versa) quebra o teste e obriga olhar.
        assertEquals(5, MARCADORES_INTERNOS.size)
        assertTrue(MARCADORES_INTERNOS.contains("[handoff humano"))
        assertTrue(MARCADORES_INTERNOS.contains("[modo manual"))
        assertTrue(MARCADORES_INTERNOS.contains("[whitelist"))
        assertTrue(MARCADORES_INTERNOS.contains("[fila do departamento"))
        assertTrue(MARCADORES_INTERNOS.contains("[resposta superada"))
    }

    @Test
    fun `midia absorve o texto como legenda`() {
        // Desde a mig 144 o worker junta texto e mídia na mesma row.
        val b =
            MensagemDto(
                id = 1,
                incomingMessage = "olha isso",
                mediaUrl = "https://x/a.jpg",
                mediaType = "image/jpeg",
            ).paraBolhas()

        assertEquals(1, b.size)
        val m = b.first() as Bolha.Midia
        assertEquals("olha isso", m.legenda)
    }

    @Test
    fun `midia do operador fica do lado da SAIDA`() {
        // Mig 146: o app manda foto e nota de voz. Se isso caísse em `media_url`
        // (inbound), a timeline mostraria a foto do operador como se o cliente
        // tivesse enviado — daí o campo separado e o lado explícito.
        val b =
            MensagemDto(
                id = 1,
                incomingMessage = "manda a foto do orçamento",
                response = "segue em anexo",
                responseMediaUrl = "data:image/jpeg;base64,AAAA",
                responseMediaType = "image/jpeg",
            ).paraBolhas()

        assertEquals(2, b.size)
        val entrada = b.first() as Bolha.Texto
        assertEquals(Lado.ENTRADA, entrada.lado)

        val saida = b[1] as Bolha.Midia
        assertEquals(Lado.SAIDA, saida.lado)
        assertEquals("image/jpeg", saida.tipo)
        // `response` é a legenda da mídia, não uma bolha de texto separada:
        // duas bolhas seriam o mesmo conteúdo contado duas vezes.
        assertEquals("segue em anexo", saida.legenda)
    }

    @Test
    fun `nota de voz sem legenda vira uma bolha so`() {
        val b =
            MensagemDto(
                id = 1,
                response = "",
                responseMediaUrl = "data:audio/ogg;base64,AAAA",
                responseMediaType = "audio/ogg",
            ).paraBolhas()

        assertEquals(1, b.size)
        val saida = b.first() as Bolha.Midia
        assertEquals(Lado.SAIDA, saida.lado)
        assertEquals(null, saida.legenda)
    }

    @Test
    fun `nota interna nao vira bolha de saida`() {
        val b =
            MensagemDto(
                id = 1,
                response = "cliente parece irritado, cuidado",
                interna = true,
                criadoPorUserId = "u1",
            ).paraBolhas()

        assertEquals(1, b.size)
        assertTrue(b.first() is Bolha.NotaInterna)
    }

    @Test
    fun `falha mostra frase fixa, nunca o detalhe tecnico`() {
        val b = MensagemDto(id = 1, incomingMessage = "oi", status = "failed").paraBolhas()

        val erro = b.filterIsInstance<Bolha.Erro>().single()
        // O operador não age sobre "EvolutionSendError"; expor stack de
        // servidor na tela é ruído e vazamento.
        assertEquals("Esta mensagem não pôde ser processada.", erro.texto)
    }

    @Test
    fun `row sem conteudo algum nao gera bolha`() {
        // Acontece: gate de whitelist grava só o marcador, sem inbound.
        val b = MensagemDto(id = 1, response = "[whitelist — numero com IA desativada]").paraBolhas()

        assertEquals(0, b.size)
    }
}
