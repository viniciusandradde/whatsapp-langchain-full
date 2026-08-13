package com.vsanexus.atendimento.ui.conversas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
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
    /** id + título: o título vem da lista pra a conversa não precisar de um GET. */
    onAbrirConversa: (Long, String) -> Unit,
    onSair: () -> Unit,
    temaAtual: String = "claro",
    onMudarTema: (String) -> Unit = {},
    vm: ConversasViewModel = hiltViewModel(),
) {
    var menuConfig by androidx.compose.runtime.remember {
        androidx.compose.runtime.mutableStateOf(false)
    }
    val ui by vm.ui.collectAsStateWithLifecycle()
    val conversas by vm.conversas.collectAsStateWithLifecycle()

    // Android 13+ exige permissão de runtime pra NOTIFICAÇÃO. A lista é o
    // primeiro lugar onde ela faz falta (push de mensagem nova) — pedir no
    // login seria cedo demais pra pessoa entender o porquê. Uma vez só:
    // negou, o app não insiste (o sistema para de perguntar de qualquer
    // forma na segunda negativa).
    val pedirNotificacao =
        androidx.activity.compose.rememberLauncherForActivityResult(
            androidx.activity.result.contract.ActivityResultContracts.RequestPermission(),
        ) { }
    androidx.compose.runtime.LaunchedEffect(Unit) {
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            pedirNotificacao.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = { Text(empresaNome ?: "Conversas") },
                    actions = {
                        TextButton(onClick = onSair) {
                            Text("Sair", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        // Configurações do app — por ora, o tema. É o lugar
                        // pra onde novas preferências devem ir, em vez de
                        // espalhar botões pelo topo.
                        androidx.compose.material3.IconButton(onClick = { menuConfig = true }) {
                            androidx.compose.material3.Icon(
                                androidx.compose.material.icons.Icons.Filled.MoreVert,
                                contentDescription = "Configurações",
                            )
                        }
                        androidx.compose.material3.DropdownMenu(
                            expanded = menuConfig,
                            onDismissRequest = { menuConfig = false },
                        ) {
                            listOf(
                                "claro" to "Tema claro",
                                "escuro" to "Tema escuro",
                                "sistema" to "Seguir o sistema",
                            ).forEach { (modo, rotulo) ->
                                androidx.compose.material3.DropdownMenuItem(
                                    text = { Text(rotulo) },
                                    trailingIcon = {
                                        if (temaAtual == modo) {
                                            androidx.compose.material3.Icon(
                                                androidx.compose.material.icons.Icons.Filled.Check,
                                                contentDescription = "Tema atual",
                                            )
                                        }
                                    },
                                    onClick = {
                                        menuConfig = false
                                        onMudarTema(modo)
                                    },
                                )
                            }
                        }
                    },
                    // Tema clean: topo é superfície clara com texto escuro. O
                    // laranja da marca fica no indicador da aba ativa, que é
                    // onde ele informa algo.
                    colors =
                        TopAppBarDefaults.topAppBarColors(
                            containerColor = MaterialTheme.colorScheme.surface,
                            titleContentColor = MaterialTheme.colorScheme.onSurface,
                            actionIconContentColor = MaterialTheme.colorScheme.onSurface,
                        ),
                )
                androidx.compose.material3.ScrollableTabRow(
                    selectedTabIndex = Aba.entries.indexOf(ui.aba),
                    containerColor = MaterialTheme.colorScheme.surface,
                    contentColor = MaterialTheme.colorScheme.primary,
                    // Zero: a primeira aba encosta na margem como no TabRow.
                    // Com 5 abas em 360dp o TabRow fixo dava ~72dp por aba e
                    // "Resolvidas" virava "Resolvida" — visto em aparelho real.
                    edgePadding = androidx.compose.ui.unit.Dp(0f),
                ) {
                    Aba.entries.forEach { aba ->
                        Tab(
                            selected = aba == ui.aba,
                            onClick = { vm.trocarAba(aba) },
                            text = {
                                // maxLines=1 + softWrap=false: "Aguardando" não
                                // cabia em 13sp na largura de 1/4 de tela e
                                // quebrava como "Aguardand / o".
                                Text(
                                    aba.titulo,
                                    fontSize = 12.sp,
                                    maxLines = 1,
                                    softWrap = false,
                                )
                            },
                        )
                    }
                }
            }
        },
    ) { inner ->
        Column(modifier = Modifier.fillMaxSize().padding(inner).navigationBarsPadding()) {
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
                            CartaoConversa(c, onClick = { onAbrirConversa(c.id, tituloDe(c)) })
                        }
                    }
            }
        }
    }
}

/**
 * Cartão da conversa, com o RESUMO DA TRIAGEM visível antes de abrir.
 *
 * Espelha o cartão do painel web de propósito. O operador precisa decidir o que
 * atender sem entrar em cada conversa: prioridade, sentimento e categoria na
 * lista transformam a fila numa fila triada em vez de uma pilha de nomes. Numa
 * fila de 76 aguardando — o número real medido em produção — abrir uma por uma
 * pra descobrir o que é urgente é inviável.
 */
@Composable
private fun CartaoConversa(c: ConversaEntity, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 5.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(
                        c.clienteNome ?: c.clienteTelefone ?: "Sem nome",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (c.clienteTelefone != null) {
                        Text(
                            c.clienteTelefone,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Contador ANTES do selo: é ele que decide se o operador
                        // abre a conversa agora.
                        if (c.naoLidas > 0) {
                            MarcaNaoLida(c.naoLidas)
                            Spacer(Modifier.width(6.dp))
                        }
                        Etiqueta(rotuloSituacao(c.situacao), corDeSituacao(c.situacao))
                    }
                    if (c.prioridade != null) {
                        Spacer(Modifier.height(4.dp))
                        Etiqueta(c.prioridade, corDePrioridade(c.prioridade))
                    }
                }
            }

            Spacer(Modifier.height(10.dp))
            if (c.protocolo != null) LinhaInfo("Atendimento", c.protocolo)
            if (c.agenteAtual != null) LinhaInfo("Agente", c.agenteAtual)
            LinhaInfo("Última mensagem", tempoRelativo(c.ultimaMensagemEm))

            // Resumo que a IA escreveu na triagem. É a informação mais densa do
            // cartão: em duas linhas o operador sabe do que se trata.
            if (!c.resumoIa.isNullOrBlank()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    c.resumoIa.trim(),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            // Tags do CLIENTE — identificam a pessoa (instituição, turma) e são
            // o que alimenta as abas. Vêm antes das da triagem porque não mudam
            // a cada conversa.
            if (c.clienteTags.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Row {
                    c.clienteTags.split("|").filter { it.isNotBlank() }.forEach {
                        Etiqueta(it, MaterialTheme.colorScheme.primaryContainer)
                        Spacer(Modifier.width(6.dp))
                    }
                }
            }

            val marcadores = listOfNotNull(c.classificacao, c.sentimento)
            if (marcadores.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Row {
                    marcadores.forEach {
                        Etiqueta(it, MaterialTheme.colorScheme.surfaceVariant, monoespaçada = true)
                        Spacer(Modifier.width(6.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun LinhaInfo(rotulo: String, valor: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 1.dp)) {
        Text(
            rotulo,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text(valor, style = MaterialTheme.typography.bodySmall, maxLines = 1)
    }
}

@Composable
private fun Etiqueta(texto: String, cor: Color, monoespaçada: Boolean = false) {
    Surface(color = cor, shape = RoundedCornerShape(6.dp)) {
        Text(
            texto,
            style =
                if (monoespaçada) {
                    MaterialTheme.typography.labelSmall.copy(fontFamily = FontFamily.Monospace)
                } else {
                    MaterialTheme.typography.labelSmall
                },
            modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp),
        )
    }
}

/**
 * Bolinha com o número de mensagens novas do cliente.
 *
 * Vermelho é o único uso dessa cor na lista, de propósito: é o sinal que compete
 * pela atenção. O selo de situação usa tons suaves justamente pra não disputar.
 */
@Composable
private fun MarcaNaoLida(quantidade: Int) {
    Surface(
        color = MaterialTheme.colorScheme.error,
        shape = RoundedCornerShape(10.dp),
    ) {
        Text(
            if (quantidade > 99) "99+" else "$quantidade",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onError,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

/**
 * Rótulo da situação — o MESMO texto do painel web.
 *
 * Antes vinha de `status` cru, e as telas divergiam: o app dizia "Em
 * atendimento" onde o web dizia "Em andamento" para o mesmo estado. Agora o
 * servidor manda `situacao` pronta (`shared/atendimento.py::derivar_situacao`).
 */
private fun rotuloSituacao(situacao: String) =
    when (situacao) {
        "resposta_perdida" -> "Não enviada"
        "com_ia" -> "Com a IA"
        "aguardando_humano" -> "Aguardando humano"
        "em_atendimento" -> "Em atendimento"
        "sem_automacao" -> "Sem automação"
        "resolvida" -> "Resolvida"
        "abandonada" -> "Abandonada"
        else -> situacao
    }

/**
 * Cor do selo.
 *
 * `sem_automacao` fica NEUTRO e não em vermelho: não é erro, é configuração
 * (whitelist ou conexão em modo manual). Vermelho faria o operador tentar
 * consertar o que está como foi pedido — e competiria com a marca de não lida,
 * que é o sinal que de fato pede ação.
 */
@Composable
private fun corDeSituacao(situacao: String): Color =
    when (situacao) {
        // Único vermelho entre as situações: cliente sem retorno por falha
        // nossa. Divide o tom com a marca de não lida de propósito — as duas
        // pedem ação, e nenhuma outra situação usa vermelho.
        "resposta_perdida" -> MaterialTheme.colorScheme.errorContainer
        "com_ia" -> MaterialTheme.colorScheme.secondaryContainer
        "aguardando_humano" -> MaterialTheme.colorScheme.tertiaryContainer
        "em_atendimento" -> MaterialTheme.colorScheme.primaryContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }

@Composable
private fun corDePrioridade(p: String): Color =
    when (p) {
        // Urgente tem cor de erro porque é o único que exige ação agora; dar
        // destaque a todos seria o mesmo que não destacar nenhum.
        "urgente" -> MaterialTheme.colorScheme.errorContainer
        "alta" -> MaterialTheme.colorScheme.tertiaryContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }

/**
 * "2h atrás", como no painel web.
 *
 * Mais útil que hora absoluta numa fila: o que importa é há quanto tempo a
 * pessoa espera, não em que minuto escreveu.
 */
private fun tempoRelativo(iso: String?): String {
    if (iso == null || iso.length < 19) return "—"
    return try {
        val quando = java.time.Instant.parse(if (iso.endsWith("Z")) iso else iso + "Z")
        val minutos = java.time.Duration.between(quando, java.time.Instant.now()).toMinutes()
        when {
            minutos < 1 -> "agora"
            minutos < 60 -> "${minutos}min atrás"
            minutos < 1440 -> "${minutos / 60}h atrás"
            else -> "${minutos / 1440}d atrás"
        }
    } catch (e: Exception) {
        "—"
    }
}

/** Título da conversa: nome do cliente, telefone como reserva. */
private fun tituloDe(c: ConversaEntity): String =
    c.clienteNome ?: c.clienteTelefone ?: "Conversa ${c.id}"
