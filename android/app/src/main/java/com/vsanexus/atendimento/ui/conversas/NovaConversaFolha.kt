package com.vsanexus.atendimento.ui.conversas

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.foundation.clickable
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.Surface
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Folha "Nova conversa" (mig 170) — o operador inicia contato com um número.
 *
 * Sem seletor de conexão: o servidor usa a PADRÃO da empresa (quem quiser
 * trocar marca outra em /connections no painel). A lista carregada serve só
 * pra saber se existe conexão Evolution utilizável — WABA/Twilio exigem
 * template HSM, fluxo do painel web.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NovaConversaFolha(
    ui: NovaConversaUi,
    onIniciar: (telefone: String, nome: String, mensagem: String) -> Unit,
    /** Cada tecla no campo de contato — o ViewModel faz o debounce. */
    onBuscarContato: (String) -> Unit,
    onLimparSugestoes: () -> Unit,
    onFechar: () -> Unit,
) {
    val telefone = remember { mutableStateOf("") }
    val nome = remember { mutableStateOf("") }
    val mensagem = remember { mutableStateOf("") }

    val pronto =
        !ui.conexoes.isNullOrEmpty() &&
            telefone.value.count { it.isDigit() } >= 8 &&
            mensagem.value.isNotBlank()

    ModalBottomSheet(onDismissRequest = onFechar) {
        Column(Modifier.padding(horizontal = 20.dp).navigationBarsPadding()) {
            Text("Nova conversa", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(12.dp))

            when {
                ui.conexoes == null -> {
                    CircularProgressIndicator()
                }
                ui.conexoes.isEmpty() -> {
                    Text(
                        "Nenhuma conexão disponível para iniciar conversa pelo " +
                            "app. Conexões WABA/Twilio usam o painel web.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                else -> {
                    OutlinedTextField(
                        value = telefone.value,
                        onValueChange = {
                            telefone.value = it
                            onBuscarContato(it)
                        },
                        label = { Text("Nome ou telefone") },
                        placeholder = { Text("Busque um contato ou digite o número") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                    // Contatos que casam com o digitado: tocar preenche número
                    // e nome — é o caminho de quem já falou com a empresa.
                    if (ui.sugestoes.isNotEmpty()) {
                        Spacer(Modifier.height(4.dp))
                        Surface(
                            tonalElevation = 2.dp,
                            shape = MaterialTheme.shapes.medium,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Column {
                                ui.sugestoes.take(6).forEach { c ->
                                    ListItem(
                                        headlineContent = { Text(c.nome ?: "Sem nome") },
                                        supportingContent = { Text(c.telefone ?: "") },
                                        modifier =
                                            Modifier.fillMaxWidth().clickable {
                                                telefone.value = c.telefone ?: ""
                                                nome.value = c.nome ?: ""
                                                onLimparSugestoes()
                                            },
                                    )
                                }
                            }
                        }
                    } else if (ui.buscando) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "Procurando contatos…",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = nome.value,
                        onValueChange = { nome.value = it },
                        label = { Text("Nome (opcional)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = mensagem.value,
                        onValueChange = { mensagem.value = it },
                        label = { Text("Primeira mensagem") },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 2,
                    )
                }
            }

            ui.erro?.let {
                Spacer(Modifier.height(8.dp))
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            Spacer(Modifier.height(12.dp))
            Button(
                onClick = {
                    onIniciar(telefone.value.trim(), nome.value.trim(), mensagem.value.trim())
                },
                enabled = pronto && !ui.enviando,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (ui.enviando) "Enviando…" else "Iniciar conversa")
            }
            Spacer(Modifier.height(20.dp))
        }
    }
}
