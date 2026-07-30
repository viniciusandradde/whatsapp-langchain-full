package com.vsanexus.atendimento.ui.conversa

import android.graphics.BitmapFactory
import android.media.MediaPlayer
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Mídia da conversa, buscada sob demanda.
 *
 * O conteúdo NÃO vem com a lista de mensagens: o banco guarda data-URL base64 na
 * própria linha (um PDF de 5 MB, medido em produção), e uma página de 50
 * mensagens com anexos passava de dezenas de MB — no 4G a conversa não abria. A
 * lista vem com `media_disponivel`, e estes composables pedem o arquivo quando
 * de fato aparecem na tela.
 *
 * `carregar` devolve o arquivo já em cache (ver `MidiaRepository`) ou null se não
 * deu — e null vira aviso, não tela em branco.
 */
private typealias CarregarMidia = suspend () -> File?

/**
 * Imagem da conversa.
 *
 * Decodifica em thread de I/O e com `inSampleSize` calculado: foto de celular
 * tem 12 megapixels, e um Bitmap desses são ~48 MB em memória. Numa lista com
 * várias imagens isso é OutOfMemory garantido — daí reduzir na decodificação, e
 * não com `Modifier.size` depois (que só encolhe na tela, não na RAM).
 */
@Composable
fun ImagemDaConversa(chave: String, carregar: CarregarMidia, modifier: Modifier = Modifier) {
    val bitmap by
        produceState<ImageBitmap?>(initialValue = null, chave) {
            value =
                withContext(Dispatchers.IO) {
                    val arquivo = carregar() ?: return@withContext null
                    runCatching {
                        val caminho = arquivo.absolutePath

                        // 1ª passada: só as dimensões, sem alocar pixels.
                        val medida =
                            BitmapFactory.Options().apply { inJustDecodeBounds = true }
                        BitmapFactory.decodeFile(caminho, medida)

                        var escala = 1
                        while (medida.outWidth / escala > 1080) escala *= 2

                        val opcoes = BitmapFactory.Options().apply { inSampleSize = escala }
                        BitmapFactory.decodeFile(caminho, opcoes)?.asImageBitmap()
                    }.getOrNull()
                }
        }

    val bmp = bitmap
    if (bmp == null) {
        Row(modifier.height(140.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Carregando imagem…", style = MaterialTheme.typography.bodySmall)
        }
    } else {
        Image(
            bitmap = bmp,
            contentDescription = "Imagem da conversa",
            contentScale = ContentScale.Crop,
            modifier = modifier.clip(RoundedCornerShape(8.dp)).heightIn(max = 260.dp),
        )
    }
}

/**
 * Player de áudio.
 *
 * O `MediaPlayer` toca de CAMINHO, não de bytes — por isso a mídia é servida como
 * arquivo em cache em vez de `ByteArray`.
 */
@Composable
fun AudioDaConversa(chave: String, carregar: CarregarMidia, modifier: Modifier = Modifier) {
    var tocando by remember { mutableStateOf(false) }
    var duracaoMs by remember { mutableStateOf(0) }
    var posicaoMs by remember { mutableStateOf(0) }
    var erro by remember { mutableStateOf(false) }

    val player = remember { MediaPlayer() }

    // Prepara uma vez por áudio. `chave` identifica a bolha: bolha diferente,
    // arquivo diferente.
    LaunchedEffect(chave) {
        val ok =
            withContext(Dispatchers.IO) {
                runCatching {
                    val arquivo = carregar() ?: return@runCatching false
                    player.reset()
                    player.setDataSource(arquivo.absolutePath)
                    player.prepare()
                    true
                }.getOrDefault(false)
            }
        if (ok) {
            duracaoMs = player.duration.coerceAtLeast(0)
            player.setOnCompletionListener {
                tocando = false
                posicaoMs = 0
                it.seekTo(0)
            }
        } else {
            erro = true
        }
    }

    // Libera o MediaPlayer ao sair: cada instância segura um codec do sistema, e
    // vazar isso numa lista de conversas esgota o pool de decoders do aparelho.
    DisposableEffect(Unit) {
        onDispose {
            runCatching {
                if (player.isPlaying) player.stop()
                player.release()
            }
        }
    }

    // Atualiza a barra só enquanto toca — polling sempre ligado gastaria bateria
    // com a tela aberta e nada tocando.
    LaunchedEffect(tocando) {
        while (tocando) {
            posicaoMs = runCatching { player.currentPosition }.getOrDefault(posicaoMs)
            kotlinx.coroutines.delay(200)
        }
    }

    if (erro) {
        Text("Áudio não pôde ser carregado.", style = MaterialTheme.typography.bodySmall)
        return
    }

    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        IconButton(
            onClick = {
                runCatching {
                    if (player.isPlaying) {
                        player.pause()
                        tocando = false
                    } else {
                        player.start()
                        tocando = true
                    }
                }
            },
            modifier = Modifier.size(36.dp),
        ) {
            Icon(
                if (tocando) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                contentDescription = if (tocando) "Pausar" else "Tocar",
            )
        }
        Spacer(Modifier.width(6.dp))
        Column(Modifier.weight(1f)) {
            LinearProgressIndicator(
                progress = {
                    if (duracaoMs > 0) (posicaoMs.toFloat() / duracaoMs).coerceIn(0f, 1f) else 0f
                },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(2.dp))
            Text(
                "${tempo(posicaoMs)} / ${tempo(duracaoMs)}",
                style = MaterialTheme.typography.labelSmall,
            )
        }
    }
}

private fun tempo(ms: Int): String {
    val total = ms / 1000
    return "%d:%02d".format(total / 60, total % 60)
}
