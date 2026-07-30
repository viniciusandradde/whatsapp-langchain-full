package com.vsanexus.atendimento

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.vsanexus.atendimento.ui.conversas.ConversasScreen
import com.vsanexus.atendimento.ui.login.LoginScreen
import com.vsanexus.atendimento.ui.login.LoginViewModel
import com.vsanexus.atendimento.ui.theme.NexusAtendimentoTheme
import dagger.hilt.android.AndroidEntryPoint

/**
 * Activity única do app.
 *
 * A raiz decide entre login e app pelo ESTADO DA SESSÃO, não por navegação:
 * quando a API devolve 401 o interceptor limpa a sessão, e a UI cai no login
 * sozinha. Com rotas, seria preciso interceptar navegação de qualquer tela.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            NexusAtendimentoTheme {
                Raiz()
            }
        }
    }
}

@Composable
private fun Raiz(vm: LoginViewModel = hiltViewModel()) {
    val sessao by vm.sessao.collectAsStateWithLifecycle()
    if (sessao.logado && !sessao.precisaEscolherEmpresa) {
        ConversasScreen(
            empresaNome = sessao.empresaNome,
            // Abrir a conversa entra na fatia 4, com a tela de mensagens.
            onAbrirConversa = {},
            onSair = vm::sair,
        )
    } else {
        LoginScreen(vm)
    }
}
