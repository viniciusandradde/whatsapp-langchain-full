package com.vsanexus.atendimento

import android.app.Application

/**
 * Application do app.
 *
 * Existe desde a primeira fatia mesmo sem fazer nada: declarar `android:name`
 * no manifest depois obrigaria mexer no manifest de novo, e é aqui que Hilt
 * (`@HiltAndroidApp`) e a inicialização do Firebase vão entrar.
 */
class NexusApp : Application()
