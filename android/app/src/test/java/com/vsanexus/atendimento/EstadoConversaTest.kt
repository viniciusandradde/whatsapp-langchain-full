package com.vsanexus.atendimento

import com.vsanexus.atendimento.data.EstadoConversa
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Qual ação a tela de conversa oferece.
 *
 * Importa acertar porque as duas ações são opostas e ambas têm efeito visível
 * pro cliente: "Atender" cala a IA E avisa o cliente que um atendente assumiu;
 * "Devolver à IA" religa a IA em silêncio. Oferecer a errada num toque só é o
 * tipo de erro que o operador não desfaz sem ajuda.
 */
class EstadoConversaTest {
    @Test
    fun `aguardando oferece Atender e nao Devolver`() {
        val e = EstadoConversa(status = "aguardando")
        assertTrue(e.podeAtender)
        assertFalse(e.podeDevolverParaIa)
    }

    @Test
    fun `em_andamento oferece Devolver e nao Atender`() {
        val e = EstadoConversa(status = "em_andamento")
        assertTrue(e.podeDevolverParaIa)
        assertFalse(e.podeAtender)
    }

    @Test
    fun `conversa fechada nao oferece nenhuma das duas`() {
        for (s in listOf("resolvido", "abandonado")) {
            val e = EstadoConversa(status = s)
            assertFalse("status=$s", e.podeAtender)
            assertFalse("status=$s", e.podeDevolverParaIa)
        }
    }

    @Test
    fun `status desconhecido nao oferece nada`() {
        // O detalhe é best-effort: se a chamada falhar o status fica nulo, e
        // mostrar botão nesse caso ofereceria ação sem saber o estado real.
        val e = EstadoConversa(status = null)
        assertFalse(e.podeAtender)
        assertFalse(e.podeDevolverParaIa)
    }
}
