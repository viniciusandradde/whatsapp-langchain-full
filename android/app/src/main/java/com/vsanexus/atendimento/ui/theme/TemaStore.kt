package com.vsanexus.atendimento.ui.theme

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Preferência de tema: `claro` (default) | `escuro` | `sistema`.
 *
 * SharedPreferences comum, não criptografado — é gosto visual, não segredo.
 * Separado do SessaoStore de propósito: sair da conta não pode resetar o
 * tema que a pessoa escolheu.
 */
@Singleton
class TemaStore
@Inject
constructor(@ApplicationContext ctx: Context) {
    private val prefs = ctx.getSharedPreferences("tema", Context.MODE_PRIVATE)

    private val _estado = MutableStateFlow(prefs.getString("modo", "claro") ?: "claro")
    val estado: StateFlow<String> = _estado.asStateFlow()

    fun mudar(modo: String) {
        if (modo !in setOf("claro", "escuro", "sistema")) return
        prefs.edit().putString("modo", modo).apply()
        _estado.value = modo
    }
}
