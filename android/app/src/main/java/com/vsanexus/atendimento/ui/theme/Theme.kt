package com.vsanexus.atendimento.ui.theme

import android.app.Activity
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

// Design system da VSA Tecnologia, tema CLEAN — os mesmos tokens de
// `frontend/src/app/vsa-design-tokens.css`, onde `:root` já é o tema claro (o
// obsidian é o `[data-theme="obsidian"]`, e não é o que o app usa).
//
// Laranja é a cor da marca e da AÇÃO; azul é apoio e informação. Nada de barra
// colorida cobrindo o topo: no clean as superfícies são claras e a marca aparece
// em acento — botão de enviar, indicador de aba, etiqueta.

private val Laranja = Color(0xFFF97316) // --brand-primary
private val LaranjaEscuro = Color(0xFFEA580C) // --brand-primary-dark
private val LaranjaClaro = Color(0xFFFFEDD5) // --vsa-orange-100
private val LaranjaTexto = Color(0xFF9A3412) // legível sobre LaranjaClaro

private val Azul = Color(0xFF3B82F6) // --brand-secondary
private val AzulClaro = Color(0xFFDBEAFE) // --vsa-blue-100
private val AzulTexto = Color(0xFF1E40AF) // legível sobre AzulClaro

private val Canvas = Color(0xFFFFFFFF) // --obsidian-950 (no clean: branco)
private val Superficie = Color(0xFFF8FAFC) // --obsidian-900
private val SuperficieAlta = Color(0xFFF1F5F9) // --obsidian-800
private val Borda = Color(0xFFE2E8F0) // --obsidian-700
private val Divisor = Color(0xFFCBD5E1) // --obsidian-600

private val TextoForte = Color(0xFF0F172A) // --text-primary
private val TextoFraco = Color(0xFF475569) // --text-muted

private val Ambar = Color(0xFFD97706)
private val AmbarClaro = Color(0xFFFEF3C7)
private val AmbarTexto = Color(0xFF92400E)

private val Erro = Color(0xFFEF4444) // --vsa-error
private val ErroClaro = Color(0xFFFEE2E2) // --vsa-error-light
private val ErroTexto = Color(0xFF991B1B)

// Paleta escura — o obsidian dos tokens da VSA (`[data-theme="obsidian"]` no
// painel web). Entrou a pedido do dono depois do clean-only original: virou
// ESCOLHA no menu (claro | escuro | sistema), com o claro seguindo default.
private val NoiteCanvas = Color(0xFF0F172A) // --obsidian-950
private val NoiteSuperficie = Color(0xFF1E293B) // --obsidian-800
private val NoiteAlta = Color(0xFF334155) // --obsidian-700
private val NoiteDivisor = Color(0xFF475569)
private val NoiteTextoForte = Color(0xFFF1F5F9)
private val NoiteTextoFraco = Color(0xFF94A3B8)

/** Tema claro (default) — o CLEAN da VSA. */
private val Clean =
    lightColorScheme(
        primary = Laranja,
        onPrimary = Color.White,
        primaryContainer = LaranjaClaro,
        onPrimaryContainer = LaranjaTexto,
        secondary = Azul,
        onSecondary = Color.White,
        secondaryContainer = AzulClaro,
        onSecondaryContainer = AzulTexto,
        tertiary = Ambar,
        onTertiary = Color.White,
        tertiaryContainer = AmbarClaro,
        onTertiaryContainer = AmbarTexto,
        background = Superficie,
        onBackground = TextoForte,
        surface = Canvas,
        onSurface = TextoForte,
        surfaceVariant = SuperficieAlta,
        onSurfaceVariant = TextoFraco,
        outline = Divisor,
        outlineVariant = Borda,
        error = Erro,
        onError = Color.White,
        errorContainer = ErroClaro,
        onErrorContainer = ErroTexto,
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

/**
 * Bolha de saída em azul-100 (é a cor que o painel web usa pro que sai do
 * operador), bolha de entrada em branco.
 *
 * O fundo da conversa é `SuperficieAlta` e não `Superficie`: contra `#f8fafc` a
 * bolha branca `#ffffff` fica indistinguível, e o único jeito de separá-las
 * seria contorná-las. Um degrau de cinza resolve sem borda.
 */
@Composable
fun coresChat(): CoresChat {
    // Deriva do tema ATIVO em vez de receber flag: a luminância do fundo diz
    // se estamos no escuro, e nenhum call site precisa mudar quando o tema
    // muda de lugar.
    val escuro = MaterialTheme.colorScheme.background == NoiteCanvas
    return if (escuro) {
        CoresChat(
            bolhaSaida = Color(0xFF1E3A8A), // azul-900: saída legível no escuro
            bolhaEntrada = NoiteSuperficie,
            fundoConversa = NoiteCanvas,
        )
    } else {
        CoresChat(AzulClaro, Canvas, SuperficieAlta)
    }
}

private val Noite =
    darkColorScheme(
        primary = Laranja,
        onPrimary = Color.White,
        primaryContainer = Color(0xFF7C2D12), // laranja-900
        onPrimaryContainer = LaranjaClaro,
        secondary = Azul,
        onSecondary = Color.White,
        secondaryContainer = Color(0xFF1E3A8A),
        onSecondaryContainer = AzulClaro,
        tertiary = Ambar,
        onTertiary = Color.Black,
        tertiaryContainer = Color(0xFF78350F), // âmbar-900
        onTertiaryContainer = AmbarClaro,
        background = NoiteCanvas,
        onBackground = NoiteTextoForte,
        surface = NoiteSuperficie,
        onSurface = NoiteTextoForte,
        surfaceVariant = NoiteAlta,
        onSurfaceVariant = NoiteTextoFraco,
        outline = NoiteDivisor,
        outlineVariant = NoiteAlta,
        error = Erro,
        onError = Color.White,
        errorContainer = Color(0xFF7F1D1D),
        onErrorContainer = ErroClaro,
    )

@Composable
fun NexusAtendimentoTheme(escuro: Boolean = false, content: @Composable () -> Unit) {
    val view = LocalView.current
    // A Activity é resolvida FORA do SideEffect: dentro dele não há escopo
    // composable, então ler `LocalContext` ali não compila. E o cast é seguro
    // (`as?`) porque no Preview do Android Studio o contexto não é Activity.
    val activity = LocalContext.current as? Activity
    if (!view.isInEditMode && activity != null) {
        SideEffect {
            // Ícones das barras acompanham o tema: escuros sobre superfície
            // clara, claros sobre a escura — senão relógio e botões somem.
            val controlador = WindowCompat.getInsetsController(activity.window, view)
            controlador.isAppearanceLightStatusBars = !escuro
            controlador.isAppearanceLightNavigationBars = !escuro
        }
    }
    MaterialTheme(
        colorScheme = if (escuro) Noite else Clean,
        typography = Typography(),
        content = content,
    )
}
