package com.vsanexus.atendimento.di

import android.content.Context
import androidx.room.Room
import com.vsanexus.atendimento.data.local.ConversaDao
import com.vsanexus.atendimento.data.local.NexusDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object BancoModule {
    @Provides
    @Singleton
    fun banco(@ApplicationContext ctx: Context): NexusDatabase =
        Room.databaseBuilder(ctx, NexusDatabase::class.java, "nexus.db")
            // O banco é cache do servidor: recriar do zero custa uma
            // sincronização, não informação. Escrever migração à mão pra isso
            // seria trabalho sem retorno — e migração errada em app publicado
            // trava o usuário numa versão.
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun conversaDao(db: NexusDatabase): ConversaDao = db.conversas()
}
