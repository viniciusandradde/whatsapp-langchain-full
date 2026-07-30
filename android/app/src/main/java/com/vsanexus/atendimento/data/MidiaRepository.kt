package com.vsanexus.atendimento.data

import android.content.Context
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Mídia da conversa, baixada sob demanda e guardada em arquivo.
 *
 * **Por que não vem junto com as mensagens:** a coluna do banco guarda data-URL
 * base64 (o worker embute o que baixa do WhatsApp). Medido em produção: um PDF
 * ocupa 5 MB numa linha só. Com `limit=50`, uma conversa com anexos devolvia
 * dezenas de MB numa resposta — no 4G, a conversa não abria. O app pede
 * `incluir_midia=false` e busca cada mídia aqui, quando ela aparece na tela.
 *
 * **Por que arquivo e não memória:** o `MediaPlayer` não toca de `ByteArray`,
 * precisa de caminho. Servindo arquivo, áudio e imagem usam o mesmo cache.
 *
 * `cacheDir` porque é descartável: o sistema limpa quando faltar espaço, e o
 * conteúdo pode ser rebaixado do servidor.
 */
@Singleton
class MidiaRepository
@Inject
constructor(
    private val api: AtendimentoApi,
    @ApplicationContext private val ctx: Context,
) {
    // Uma bolha pode recompor várias vezes antes do download terminar, e a lista
    // pode trazer a mesma mídia em duas posições. Sem trava, dois downloads
    // escreveriam o MESMO arquivo ao mesmo tempo e o leitor pegaria conteúdo
    // truncado. Trava única (não por chave) porque o volume é baixo: só o que
    // está visível na tela.
    private val trava = Mutex()

    /**
     * Arquivo local da mídia, baixando na primeira vez.
     *
     * @param saida true = mídia que o OPERADOR mandou (`response_media_url`,
     *   mig 146); false = a que o cliente mandou. São colunas diferentes, e o
     *   lado errado devolveria a mídia do outro.
     * @return null quando não há mídia, o servidor recusou, ou a rede falhou —
     *   a UI mostra o rótulo de anexo em vez de tentar decodificar nada.
     */
    suspend fun arquivo(atendimentoId: Long, mensagemId: Long, saida: Boolean): File? =
        withContext(Dispatchers.IO) {
            val lado = if (saida) "out" else "in"
            val destino = File(ctx.cacheDir, "midia_${mensagemId}_$lado")

            trava.withLock {
                // Recheca dentro da trava: quem esperou pode ter sido servido
                // pelo download de quem estava na frente.
                if (destino.exists() && destino.length() > 0L) {
                    return@withContext destino
                }
                val ok =
                    runCatching {
                            val resp = api.midia(atendimentoId, mensagemId, lado)
                            val corpo = resp.body()
                            if (!resp.isSuccessful || corpo == null) return@runCatching false
                            // Streaming do corpo pro arquivo: uma foto de 8 MB
                            // não passa inteira pela memória.
                            corpo.byteStream().use { entrada ->
                                destino.outputStream().use { saidaArq ->
                                    entrada.copyTo(saidaArq)
                                }
                            }
                            destino.length() > 0L
                        }
                        .getOrDefault(false)

                if (!ok) {
                    // Arquivo parcial de download interrompido enganaria a
                    // próxima chamada, que o encontraria "existente".
                    destino.delete()
                    return@withContext null
                }
                destino
            }
        }
}
