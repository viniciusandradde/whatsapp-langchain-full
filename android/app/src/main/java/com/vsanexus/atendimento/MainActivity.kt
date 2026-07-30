package com.vsanexus.atendimento

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
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
        PlaceholderConversas(empresa = sessao.empresaNome, onSair = vm::sair)
    } else {
        LoginScreen(vm)
    }
}

// TopAppBar e TopAppBarDefaults ainda são @ExperimentalMaterial3Api no Compose
// BOM 2024.10.01 — sem o opt-in o build FALHA (o projeto trata warning de API
// experimental como erro). Vale pra toda tela com barra superior daqui pra
// frente.
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlaceholderConversas(empresa: String?, onSair: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(empresa ?: "Nexus Atendimento") },
                colors =
                    TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.primary,
                        titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    ),
            )
        },
    ) { inner ->
        Column(
            modifier = Modifier.fillMaxSize().padding(inner).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Sessão ativa", style = MaterialTheme.typography.headlineSmall)
            Text(
                "Login e empresa funcionando. A lista de conversas entra na " +
                    "próxima fatia.",
                style = MaterialTheme.typography.bodyMedium,
            )
            TextButton(onClick = onSair) { Text("Sair") }
        }
    }
}
