package com.vsanexus.atendimento.ui.conversas

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.vsanexus.atendimento.data.Aba
import com.vsanexus.atendimento.data.local.ConversaEntity

/**
 * Lista de conversas, no formato do WhatsApp.
 *
 * As quatro abas são as `TipoVisualizacao` da API (`meus`, `aguardando`,
 * `grupos`, `outros`) — o servidor decide o que entra em cada uma aplicando
 * RBAC record-level, então o app pede a aba e mostra o que vem.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConversasScreen(
    empresaNome: String?,
    onAbrirConversa: (Long) -> Unit,
    onSair: () -> Unit,
    vm: ConversasViewModel = hiltViewModel(),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val conversas by vm.conversas.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = { Text(empresaNome ?: "Conversas") },
                    actions = {
                        TextButton(onClick = onSair) {
                            Text("Sair", color = MaterialTheme.colorScheme.onPrimary)
                        }
                    },
                    colors =
                        TopAppBarDefaults.topAppBarColors(
                            containerColor = MaterialTheme.colorScheme.primary,
                            titleContentColor = MaterialTheme.colorScheme.onPrimary,
                            actionIconContentColor = MaterialTheme.colorScheme.onPrimary,
                        ),
                )
                TabRow(
                    selectedTabIndex = Aba.entries.indexOf(ui.aba),
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ) {
                    Aba.entries.forEach { aba ->
                        Tab(
                            selected = aba == ui.aba,
                            onClick = { vm.trocarAba(aba) },
                            text = { Text(aba.titulo, fontSize = 13.sp) },
                        )
                    }
                }
            }
        },
    ) { inner ->
        Column(modifier = Modifier.fillMaxSize().padding(inner)) {
            OutlinedTextField(
                value = ui.busca,
                onValueChange = vm::onBusca,
                placeholder = { Text("Buscar nome, telefone ou protocolo") },
                leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            )

            if (ui.avisoSincronizacao != null) {
                // Falha de rede não esconde a lista: mostra o cache com aviso.
                // Esvaziar a tela por causa de rede instável seria pior.
                Text(
                    ui.avisoSincronizacao!!,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }

            when {
                conversas.isEmpty() && ui.sincronizando ->
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                conversas.isEmpty() ->
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            if (ui.busca.isBlank()) {
                                "Nenhuma conversa em ${ui.aba.titulo.lowercase()}."
                            } else {
                                "Nada encontrado para \"${ui.busca}\"."
                            },
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                else ->
                    LazyColumn(Modifier.fillMaxSize()) {
                        items(conversas, key = { it.id }) { c ->
                            LinhaConversa(c, onClick = { onAbrirConversa(c.id) })
                            HorizontalDivider(
                                modifier = Modifier.padding(start = 76.dp),
                                thickness = 0.5.dp,
                            )
                        }
                    }
            }
        }
    }
}

@Composable
private fun LinhaConversa(c: ConversaEntity, onClick: () -> Unit) {
    Row(
        modifier =
            Modifier.fillMaxWidth()
                .clickable(onClick = onClick)
                .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(c.clienteNome ?: c.clienteTelefone ?: "?")
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    c.clienteNome ?: c.clienteTelefone ?: "Sem nome",
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                if (c.prioridade == "urgente") {
                    Spacer(Modifier.width(6.dp))
                    Text(
                        "URGENTE",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
            Spacer(Modifier.height(2.dp))
            Text(
                c.previa ?: descricaoStatus(c),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Spacer(Modifier.width(8.dp))
        Text(
            horaCurta(c.ultimaMensagemEm),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Iniciais em círculo.
 *
 * Sem foto porque a API não expõe avatar de cliente — inventar um placeholder
 * genérico deixaria a lista toda igual, e inicial ao menos diferencia.
 */
@Composable
private fun Avatar(nome: String) {
    val iniciais =
        nome.trim().split(" ").filter { it.isNotBlank() }.take(2)
            .joinToString("") { it.first().uppercase() }
            .ifBlank { "?" }
    Box(
        modifier =
            Modifier.size(48.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primaryContainer),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            iniciais,
            color = MaterialTheme.colorScheme.onPrimary,
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

private fun descricaoStatus(c: ConversaEntity): String =
    when {
        c.status == "aguardando" && c.departamentoId != null -> "Na fila do departamento"
        c.status == "aguardando" -> "Aguardando atendimento"
        c.status == "em_andamento" && c.atribuidoA != null -> "Em atendimento"
        c.status == "em_andamento" -> "Em andamento"
        c.status == "resolvido" -> "Resolvido"
        else -> c.status
    }

/**
 * Hora no estilo WhatsApp: `14:32` hoje, `dd/MM` antes.
 *
 * O timestamp vem como ISO-8601 do servidor. Corto a string em vez de usar
 * parser de data: o formato é conhecido e estável, e trazer `java.time` com
 * desugaring pra formatar uma hora seria peso desproporcional. Se o formato
 * mudar, a função devolve string vazia em vez de estourar.
 */
private fun horaCurta(iso: String?): String {
    if (iso == null || iso.length < 16) return ""
    return try {
        val data = iso.substring(0, 10)
        val hora = iso.substring(11, 16)
        val hojeIso = java.time.LocalDate.now().toString()
        if (data == hojeIso) hora else "${data.substring(8, 10)}/${data.substring(5, 7)}"
    } catch (e: Exception) {
        ""
    }
}
