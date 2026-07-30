package com.vsanexus.atendimento.data.local

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

/**
 * Conversa em cache local.
 *
 * O banco é um CACHE, não a fonte de verdade — o servidor é. Isso é decisão de
 * projeto e simplifica muito: perder este arquivo (limpar dados, migração
 * destrutiva) custa uma sincronização, não informação. Por isso não há
 * versionamento de schema nem migração escrita à mão.
 *
 * A única exceção é mensagem PENDENTE de envio, que só existe aqui até subir —
 * daí o cuidado de nunca apagar a tabela de mensagens em bloco.
 *
 * `empresaId` faz parte da chave lógica de leitura: o app troca de empresa e a
 * lista não pode misturar tenants. Não guardo em bancos separados porque a troca
 * é frequente e reabrir conexão a cada troca seria pior.
 */
@Entity(
    tableName = "conversa",
    indices = [Index("empresaId", "aba", "ultimaMensagemEm")],
)
data class ConversaEntity(
    @PrimaryKey val id: Long,
    val empresaId: Long,
    /**
     * Qual aba trouxe esta conversa (`meus`, `aguardando`, `grupos`, `outros`).
     *
     * Guardado porque o servidor decide o pertencimento aplicando RBAC
     * record-level — o app não tem como recalcular. Uma conversa pode aparecer
     * em mais de uma aba em momentos diferentes; a última sincronização vence.
     */
    val aba: String,
    val clienteNome: String?,
    val clienteTelefone: String?,
    val status: String,
    val prioridade: String?,
    val protocolo: String?,
    val agenteAtual: String?,
    /** Triagem da IA (mig 061) — mostrada na lista pra decidir o que abrir. */
    val classificacao: String?,
    val sentimento: String?,
    val resumoIa: String?,
    val triagemCompleta: Boolean,
    val atribuidoA: String?,
    val departamentoId: Long?,
    val conexaoNome: String?,
    /** ISO-8601 do servidor, guardado como texto pra evitar conversor. */
    val ultimaMensagemEm: String?,
    /** Prévia da última mensagem, quando conhecida. Preenchida ao abrir. */
    val previa: String? = null,
    /** Momento da sincronização — usado pra decidir se vale refazer. */
    val sincronizadoEm: Long = System.currentTimeMillis(),
)

@Dao
interface ConversaDao {
    /**
     * Conversas de uma aba, mais recentes primeiro.
     *
     * `ultimaMensagemEm DESC` com `NULLS LAST` emulado por `IS NULL`: SQLite
     * ordena NULL antes de tudo em DESC, e conversa sem timestamp iria pro topo
     * empurrando as reais pra baixo.
     */
    @Query(
        """
        SELECT * FROM conversa
         WHERE empresaId = :empresaId AND aba = :aba
         ORDER BY ultimaMensagemEm IS NULL, ultimaMensagemEm DESC, id DESC
        """,
    )
    fun observar(empresaId: Long, aba: String): Flow<List<ConversaEntity>>

    @Upsert
    suspend fun salvar(itens: List<ConversaEntity>)

    @Query("DELETE FROM conversa WHERE empresaId = :empresaId AND aba = :aba")
    suspend fun limparAba(empresaId: Long, aba: String)

    /**
     * Troca o conteúdo da aba por um novo, em transação.
     *
     * Substituir em vez de só fazer upsert é o que remove conversa que saiu da
     * aba (foi atribuída a outro, foi fechada). Sem isso a lista só cresceria.
     * A transação evita a lista aparecer vazia por um instante.
     */
    @Transaction
    suspend fun substituirAba(empresaId: Long, aba: String, itens: List<ConversaEntity>) {
        limparAba(empresaId, aba)
        salvar(itens)
    }

    @Query("DELETE FROM conversa")
    suspend fun limparTudo()
}

@Database(
    entities = [ConversaEntity::class],
    // v2: campos de triagem (classificação, sentimento, resumo da IA). Cache
    // descartável, então a migração é destrutiva e recria a tabela.
    version = 2,
    // Cache descartável: não exporto schema porque não haverá migração escrita
    // à mão — ver o comentário de ConversaEntity.
    exportSchema = false,
)
abstract class NexusDatabase : RoomDatabase() {
    abstract fun conversas(): ConversaDao
}
