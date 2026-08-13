package com.vsanexus.atendimento

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.setValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.vsanexus.atendimento.ui.conversa.ConversaScreen
import com.vsanexus.atendimento.ui.conversas.ConversasScreen
import com.vsanexus.atendimento.ui.login.LoginScreen
import com.vsanexus.atendimento.ui.login.LoginViewModel
import com.vsanexus.atendimento.ui.theme.NexusAtendimentoTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * Activity única do app.
 *
 * A raiz decide entre login e app pelo ESTADO DA SESSÃO, não por navegação:
 * quando a API devolve 401 o interceptor limpa a sessão, e a UI cai no login
 * sozinha. Com rotas, seria preciso interceptar navegação de qualquer tela.
 *
 * A troca lista ↔ conversa também é por estado, não por Navigation Compose:
 * são dois destinos, e um grafo de navegação aqui seria cerimônia. Quando
 * entrarem perfil do cliente, tags e notas — cada um com argumento próprio —
 * vale trocar; hoje não paga.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    /**
     * Pedido de abertura vindo da NOTIFICAÇÃO de push. Flow e não estado do
     * Compose porque chega por duas portas: `onCreate` (app estava fechado) e
     * `onNewIntent` (app aberto, activity é singleTop) — e a segunda vive
     * fora da composição.
     */
    private val pedidoDoPush = MutableStateFlow<ConversaAberta?>(null)

    private fun lerIntent(i: Intent?) {
        val id = i?.getLongExtra("atendimento_id", -1L) ?: -1L
        if (id > 0) {
            pedidoDoPush.value = ConversaAberta(id, i?.getStringExtra("titulo") ?: "")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        lerIntent(intent)
        setContent {
            NexusAtendimentoTheme {
                Raiz(pedidoDoPush)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        lerIntent(intent)
    }
}

/** Conversa aberta, quando houver. O título vem da lista pra evitar um GET. */
private data class ConversaAberta(val id: Long, val titulo: String)

@Composable
private fun Raiz(
    pedidoDoPush: MutableStateFlow<ConversaAberta?>,
    vm: LoginViewModel = hiltViewModel(),
) {
    val sessao by vm.sessao.collectAsStateWithLifecycle()
    var aberta by remember { mutableStateOf<ConversaAberta?>(null) }
    val pedido by pedidoDoPush.collectAsStateWithLifecycle()

    // Toque na notificação abre a conversa. Consumir (zerar o flow) impede
    // reabrir a mesma conversa numa recomposição futura.
    LaunchedEffect(pedido) {
        val pdd = pedido
        if (pdd != null && sessao.logado) {
            aberta = pdd
            pedidoDoPush.value = null
        }
    }

    // Sessão caiu (logout ou 401) com conversa aberta: fecha, senão a tela
    // ficaria por cima do login.
    if (!sessao.logado && aberta != null) aberta = null

    val conversaAberta = aberta
    when {
        !sessao.logado || sessao.precisaEscolherEmpresa -> LoginScreen(vm)

        conversaAberta != null -> {
            // Sem isto o botão voltar do Android sairia do app em vez de
            // fechar a conversa — errado e irritante.
            BackHandler { aberta = null }
            ConversaScreen(
                atendimentoId = conversaAberta.id,
                titulo = conversaAberta.titulo,
                onVoltar = { aberta = null },
            )
        }

        else ->
            ConversasScreen(
                empresaNome = sessao.empresaNome,
                onAbrirConversa = { id, titulo -> aberta = ConversaAberta(id, titulo) },
                onSair = vm::sair,
            )
    }
}
