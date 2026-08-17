package com.vsanexus.atendimento.ui.conversa

import android.os.Build
import android.widget.Toast
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString

/**
 * Uma entrada do menu de contexto da bolha, além de "Copiar".
 *
 * Existe pra Editar e Apagar entrarem sem que este arquivo precise conhecer
 * regra de negócio nenhuma — quem decide se a ação aparece é a timeline.
 */
data class AcaoDaBolha(
    val rotulo: String,
    val destrutiva: Boolean = false,
    val onClick: () -> Unit,
)

/**
 * Envolve uma bolha com o menu de toque longo, como no WhatsApp.
 *
 * Regras de comportamento:
 *
 * - **Toque curto não faz nada** e não pinta ripple: a bolha não é botão. Os
 *   controles que existem DENTRO dela (play do áudio, "Transcrever") continuam
 *   recebendo o toque normalmente, porque o clique deles é tratado antes de
 *   chegar aqui.
 * - **Toque longo vibra** antes de abrir o menu. É o retorno que substitui o
 *   ripple e o que faz o gesto parecer familiar.
 * - **Bolha sem texto e sem ação não ganha gesto nenhum** — abrir um menu
 *   vazio sobre uma foto seria ruído.
 *
 * O aviso de "copiado" só aparece até o Android 12: do 13 em diante o próprio
 * sistema mostra a confirmação de área de transferência, e o Toast viraria
 * mensagem repetida na tela.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun BolhaComMenu(
    textoCopiavel: String?,
    acoes: List<AcaoDaBolha> = emptyList(),
    conteudo: @Composable () -> Unit,
) {
    if (textoCopiavel.isNullOrBlank() && acoes.isEmpty()) {
        conteudo()
        return
    }

    val contexto = LocalContext.current
    val area = LocalClipboardManager.current
    val vibracao = LocalHapticFeedback.current
    var aberto by remember { mutableStateOf(false) }

    Box {
        Box(
            Modifier.combinedClickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onLongClick = {
                    vibracao.performHapticFeedback(HapticFeedbackType.LongPress)
                    aberto = true
                },
                onClick = {},
            ),
        ) {
            conteudo()
        }

        DropdownMenu(expanded = aberto, onDismissRequest = { aberto = false }) {
            if (!textoCopiavel.isNullOrBlank()) {
                DropdownMenuItem(
                    text = { Text("Copiar") },
                    onClick = {
                        area.setText(AnnotatedString(textoCopiavel))
                        aberto = false
                        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
                            Toast.makeText(contexto, "Mensagem copiada", Toast.LENGTH_SHORT)
                                .show()
                        }
                    },
                )
            }
            acoes.forEach { acao ->
                DropdownMenuItem(
                    text = {
                        Text(
                            acao.rotulo,
                            color =
                                if (acao.destrutiva) {
                                    MaterialTheme.colorScheme.error
                                } else {
                                    Color.Unspecified
                                },
                        )
                    },
                    onClick = {
                        aberto = false
                        acao.onClick()
                    },
                )
            }
        }
    }
}
