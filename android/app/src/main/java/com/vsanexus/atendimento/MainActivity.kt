package com.vsanexus.atendimento

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.vsanexus.atendimento.ui.theme.NexusAtendimentoTheme

/**
 * Activity única do app (single-activity + Navigation Compose).
 *
 * Nesta fatia só existe pra provar que o pipeline compila e gera APK instalável
 * no CI — a máquina de desenvolvimento é aarch64 e não tem `aapt2`, então
 * "compila" só se prova lá. As telas de conversa entram nas fatias seguintes.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            NexusAtendimentoTheme {
                PlaceholderScreen()
            }
        }
    }
}

@Composable
private fun PlaceholderScreen() {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Nexus Atendimento") },
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
            Text("Build OK", style = MaterialTheme.typography.headlineSmall)
            Text(
                "Estrutura do projeto validada no CI. " +
                    "Login e lista de conversas chegam na próxima fatia.",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun PlaceholderPreview() {
    NexusAtendimentoTheme { PlaceholderScreen() }
}
