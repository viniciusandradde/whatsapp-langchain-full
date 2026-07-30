package com.vsanexus.atendimento.ui.conversa

import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.util.Base64
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Mídia inbound vem como DATA-URL base64, não como link.
 *
 * O worker baixa do WhatsApp e embute no `media_url` como
 * `data:audio/ogg;base64,...` — o app não tem credencial pra buscar no Graph da
 * Meta nem na Evolution, então o conteúdo já vem no payload. Consequência: pode
 * ter megabytes, e nada disso pode acontecer na thread principal.
 */
private const val PREFIXO_BASE64 = ";base64,"

/** Extrai os bytes de um data-URL. Null se não for esse formato. */
private fun bytesDoDataUrl(url: String): ByteArray? {
    val i = url.indexOf(PREFIXO_BASE64)
    if (!url.startsWith("data:") || i < 0) return null
    return runCatching {
        Base64.decode(url.substring(i + PREFIXO_BASE64.length), Base64.DEFAULT)
    }.getOrNull()
}

/**
 * Imagem da conversa.
 *
 * Decodifica em thread de I/O e com `inSampleSize` calculado: foto de celular
 * tem 12 megapixels, e um Bitmap desses são ~48 MB em memória. Numa lista com
 * várias imagens isso é OutOfMemory garantido — daí reduzir na decodificação, e
 * não com `Modifier.size` depois (que só encolhe na tela, não na RAM).
 */
@Composable
fun ImagemDaConversa(dataUrl: String, modifier: Modifier = Modifier) {
    val bitmap by
        produceState<ImageBitmap?>(initialValue = null, dataUrl) {
            value =
                withContext(Dispatchers.IO) {
                    val bytes = bytesDoDataUrl(dataUrl) ?: return@withContext null
                    runCatching {
                        // 1ª passada: só as dimensões, sem alocar pixels.
                        val medida =
                            BitmapFactory.Options().apply { inJustDecodeBounds = true }
                        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, medida)

                        var escala = 1
                        while (medida.outWidth / escala > 1080) escala *= 2

                        val opcoes = BitmapFactory.Options().apply { inSampleSize = escala }
                        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opcoes)
                            ?.asImageBitmap()
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
            contentDescription = "Imagem recebida",
            contentScale = ContentScale.Crop,
            modifier = modifier.clip(RoundedCornerShape(8.dp)).heightIn(max = 260.dp),
        )
    }
}

/**
 * Player de áudio.
 *
 * O `MediaPlayer` não toca data-URL, então os bytes vão pra um arquivo no cache
 * e ele toca o arquivo. Arquivo por hash do conteúdo pra não reescrever a cada
 * recomposição, e no `cacheDir` porque é descartável — o sistema limpa quando
 * precisar de espaço, e o áudio pode ser rebaixado do servidor.
 */
@Composable
fun AudioDaConversa(dataUrl: String, modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    var tocando by remember { mutableStateOf(false) }
    var duracaoMs by remember { mutableStateOf(0) }
    var posicaoMs by remember { mutableStateOf(0) }
    var erro by remember { mutableStateOf(false) }

    val player = remember { MediaPlayer() }

    // Prepara uma vez por áudio. `dataUrl` como chave: bolha diferente, arquivo
    // diferente.
    LaunchedEffect(dataUrl) {
        val ok =
            withContext(Dispatchers.IO) {
                runCatching {
                    val bytes = bytesDoDataUrl(dataUrl) ?: return@runCatching false
                    val arquivo = File(ctx.cacheDir, "audio_${dataUrl.hashCode()}.ogg")
                    if (!arquivo.exists() || arquivo.length() != bytes.size.toLong()) {
                        arquivo.writeBytes(bytes)
                    }
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
