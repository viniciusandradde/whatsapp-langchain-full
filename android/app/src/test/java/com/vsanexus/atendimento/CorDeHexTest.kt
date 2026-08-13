package com.vsanexus.atendimento

import androidx.compose.ui.graphics.Color
import com.vsanexus.atendimento.ui.conversa.corDeHex
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * A cor da tag vem do catálogo como hex ("#F97316") digitado por admin no
 * painel web — ou seja, entrada de gente. Hex quebrado não pode derrubar a
 * folha de tags: vira o cinza neutro e a tag continua utilizável.
 */
class CorDeHexTest {
    @Test
    fun `hex valido vira a cor certa`() {
        assertEquals(Color(0xFFF97316), corDeHex("#F97316"))
        assertEquals(Color(0xFF16A34A), corDeHex("16A34A"))
    }

    @Test
    fun `entrada quebrada cai no cinza neutro`() {
        val cinza = Color(0xFF9CA3AF)
        assertEquals(cinza, corDeHex(null))
        assertEquals(cinza, corDeHex(""))
        assertEquals(cinza, corDeHex("#FFF"))
        assertEquals(cinza, corDeHex("laranja"))
        assertEquals(cinza, corDeHex("#GGGGGG"))
    }
}
