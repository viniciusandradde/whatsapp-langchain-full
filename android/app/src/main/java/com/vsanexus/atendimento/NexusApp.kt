package com.vsanexus.atendimento

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/**
 * Application do app.
 *
 * `@HiltAndroidApp` gera o container de injeção — sem ele, todo
 * `@AndroidEntryPoint` e `@HiltViewModel` falha em RUNTIME, não em build.
 */
@HiltAndroidApp
class NexusApp : Application()
