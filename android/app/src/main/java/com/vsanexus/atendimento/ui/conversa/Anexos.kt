package com.vsanexus.atendimento.ui.conversa

import android.content.Context
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import java.io.File

/**
 * Android mínimo para GRAVAR nota de voz.
 *
 * O WhatsApp só aceita OGG/Opus como nota de voz (a bolha com player e forma de
 * onda); qualquer outro formato chega como arquivo anexado. E `OutputFormat.OGG`
 * com `AudioEncoder.OPUS` só existe a partir da API 29.
 *
 * O app roda desde a 26, então nas duas versões abaixo disso o botão de microfone
 * fica desabilitado — melhor que gravar em AAC e o cliente receber um documento
 * que ele não consegue tocar no chat.
 */
const val API_MINIMA_GRAVACAO = Build.VERSION_CODES.Q

/** MIME da gravação. Precisa casar com o container que o MediaRecorder escreve. */
const val MIME_NOTA_DE_VOZ = "audio/ogg"

/** Gravações mais curtas que isto são toque acidental no botão, não mensagem. */
private const val MIN_DURACAO_MS = 700L

/**
 * Gravador de nota de voz.
 *
 * Uma instância por tela. Não é thread-safe e não precisa ser: só a UI mexe
 * nele, sempre na thread principal.
 */
class Gravador(private val ctx: Context) {
    private var recorder: MediaRecorder? = null
    private var arquivo: File? = null
    private var inicioMs = 0L

    val gravando: Boolean
        get() = recorder != null

    /** @return false se o aparelho ou o microfone não deixaram começar. */
    fun iniciar(): Boolean {
        if (Build.VERSION.SDK_INT < API_MINIMA_GRAVACAO) return false
        cancelar()

        val destino = File(ctx.cacheDir, "voz_${System.nanoTime()}.ogg")
        val rec =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(ctx)
            } else {
                @Suppress("DEPRECATION") MediaRecorder()
            }

        return runCatching {
                rec.setAudioSource(MediaRecorder.AudioSource.MIC)
                rec.setOutputFormat(MediaRecorder.OutputFormat.OGG)
                rec.setAudioEncoder(MediaRecorder.AudioEncoder.OPUS)
                // 48 kHz é a taxa nativa do Opus, e 24 kbps é o suficiente pra
                // voz — o arquivo fica pequeno o bastante pra subir no 4G sem
                // espera perceptível.
                rec.setAudioSamplingRate(48_000)
                rec.setAudioEncodingBitRate(24_000)
                rec.setOutputFile(destino.absolutePath)
                rec.prepare()
                rec.start()
                recorder = rec
                arquivo = destino
                inicioMs = System.currentTimeMillis()
                true
            }
            .getOrElse {
                runCatching { rec.release() }
                destino.delete()
                false
            }
    }

    /**
     * Encerra e devolve o arquivo pronto pra enviar.
     *
     * @return null quando falhou ou quando foi curto demais — nos dois casos o
     *   arquivo é apagado, pra não deixar lixo no cache nem enviar um clique.
     */
    fun parar(): File? {
        val rec = recorder ?: return null
        val destino = arquivo
        recorder = null
        arquivo = null

        val duracao = System.currentTimeMillis() - inicioMs
        val ok = runCatching { rec.stop() }.isSuccess
        runCatching { rec.release() }

        if (!ok || destino == null || duracao < MIN_DURACAO_MS || destino.length() == 0L) {
            destino?.delete()
            return null
        }
        return destino
    }

    /** Aborta sem enviar. Seguro chamar quando não há gravação em curso. */
    fun cancelar() {
        val rec = recorder ?: return
        recorder = null
        // `stop()` numa gravação de zero frame lança; o que importa aqui é
        // liberar o microfone, então a falha é ignorada de propósito.
        runCatching { rec.stop() }
        runCatching { rec.release() }
        arquivo?.delete()
        arquivo = null
    }
}

/** Um anexo já copiado pro cache, pronto pra subir. */
data class AnexoEscolhido(val arquivo: File, val mime: String)

/**
 * Copia o conteúdo escolhido no seletor do sistema pra um arquivo no cache.
 *
 * A cópia é necessária, não preguiça: o seletor devolve um `content://` cuja
 * permissão de leitura é temporária e que não é um arquivo — o OkHttp não
 * consegue fazer streaming dele, e a permissão pode expirar antes do upload
 * terminar. Copiar resolve os dois de uma vez.
 *
 * Roda em thread de I/O (o chamador garante): pode ser dezenas de MB.
 *
 * @return null se o conteúdo não pôde ser lido.
 */
fun copiarParaCache(ctx: Context, uri: Uri): AnexoEscolhido? {
    val resolver = ctx.contentResolver
    val mime = resolver.getType(uri) ?: "application/octet-stream"
    val nome = nomeDoConteudo(ctx, uri) ?: "anexo_${System.nanoTime()}"
    val destino = File(ctx.cacheDir, "anexo_${System.nanoTime()}_$nome")

    return runCatching {
            resolver.openInputStream(uri)?.use { entrada ->
                destino.outputStream().use { saida -> entrada.copyTo(saida) }
            } ?: return null
            AnexoEscolhido(destino, mime)
        }
        .getOrElse {
            destino.delete()
            null
        }
}

/**
 * Nome de exibição do conteúdo.
 *
 * Importa porque é o nome do arquivo que o cliente vê no WhatsApp: sem ele um
 * PDF chegaria como "anexo_84719232", que não diz nada a quem recebe.
 */
private fun nomeDoConteudo(ctx: Context, uri: Uri): String? =
    runCatching {
            ctx.contentResolver
                .query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { cursor ->
                    val col = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (col >= 0 && cursor.moveToFirst()) cursor.getString(col) else null
                }
        }
        .getOrNull()
        // Barra no nome viraria diretório inexistente no caminho do cache.
        ?.replace('/', '_')
