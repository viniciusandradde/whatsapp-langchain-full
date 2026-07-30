package com.vsanexus.atendimento.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

// Paleta inspirada no WhatsApp, que é a referência de UX pedida — o operador
// alterna entre os dois apps o dia inteiro e a troca precisa passar batido.
// Os tons NÃO são copiados pixel a pixel: verde-teal do cabeçalho, bolha de
// saída em verde claro, bolha de entrada em branco/cinza.
private val VerdeTeal = Color(0xFF075E54)
private val VerdeTealClaro = Color(0xFF128C7E)
private val VerdeAcao = Color(0xFF25D366)
private val BolhaSaida = Color(0xFFDCF8C6)
private val BolhaEntrada = Color(0xFFFFFFFF)
private val FundoConversa = Color(0xFFECE5DD)

private val BolhaSaidaEscura = Color(0xFF005C4B)
private val BolhaEntradaEscura = Color(0xFF202C33)
private val FundoConversaEscuro = Color(0xFF0B141A)

private val Claro =
    lightColorScheme(
        primary = VerdeTeal,
        onPrimary = Color.White,
        primaryContainer = VerdeTealClaro,
        secondary = VerdeAcao,
        onSecondary = Color.White,
        background = Color(0xFFF7F8FA),
        surface = Color.White,
        surfaceVariant = FundoConversa,
    )

private val Escuro =
    darkColorScheme(
        primary = VerdeTealClaro,
        onPrimary = Color.White,
        primaryContainer = VerdeTeal,
        secondary = VerdeAcao,
        onSecondary = Color.Black,
        background = Color(0xFF111B21),
        surface = BolhaEntradaEscura,
        surfaceVariant = FundoConversaEscuro,
    )

/**
 * Cores das bolhas de mensagem.
 *
 * Ficam fora do [androidx.compose.material3.ColorScheme] porque não existe slot
 * semântico do Material 3 pra "bolha de chat" — encaixar em `surfaceVariant` ou
 * `tertiaryContainer` faria a cor mudar junto com componentes que não têm nada
 * a ver.
 */
data class CoresChat(
    val bolhaSaida: Color,
    val bolhaEntrada: Color,
    val fundoConversa: Color,
)

@Composable
fun coresChat(escuro: Boolean = isSystemInDarkTheme()): CoresChat =
    if (escuro) {
        CoresChat(BolhaSaidaEscura, BolhaEntradaEscura, FundoConversaEscuro)
    } else {
        CoresChat(BolhaSaida, BolhaEntrada, FundoConversa)
    }

@Composable
fun NexusAtendimentoTheme(
    escuro: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val scheme = if (escuro) Escuro else Claro
    val view = LocalView.current
    // A Activity é resolvida FORA do SideEffect: dentro dele não há escopo
    // composable, então ler `LocalContext` ali não compila. E o cast é seguro
    // (`as?`) porque no Preview do Android Studio o contexto não é Activity.
    val activity = LocalContext.current as? Activity
    if (!view.isInEditMode && activity != null) {
        SideEffect {
            // Status bar sempre com ícones claros: o cabeçalho é verde escuro
            // nos dois temas, como no WhatsApp.
            WindowCompat.getInsetsController(activity.window, view)
                .isAppearanceLightStatusBars = false
        }
    }
    MaterialTheme(colorScheme = scheme, typography = Typography(), content = content)
}
