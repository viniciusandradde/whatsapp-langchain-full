package com.vsanexus.atendimento.ui.conversa

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.vsanexus.atendimento.domain.Bolha
import com.vsanexus.atendimento.domain.Lado
import com.vsanexus.atendimento.ui.theme.CoresChat
import com.vsanexus.atendimento.ui.theme.coresChat
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter

/**
 * Tela de conversa.
 *
 * `reverseLayout = true` no LazyColumn: a lista cresce de baixo pra cima, o
 * conteúdo novo entra embaixo e a rolagem já começa no fim — sem isso seria
 * preciso rolar programaticamente a cada mensagem, o que briga com o gesto do
 * usuário. Em troca, a lista de bolhas é consumida invertida.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConversaScreen(
    atendimentoId: Long,
    titulo: String,
    onVoltar: () -> Unit,
    vm: ConversaViewModel = hiltViewModel(),
) {
    val estado by vm.estado.collectAsStateWithLifecycle()
    val rascunho by vm.rascunho.collectAsStateWithLifecycle()
    val cores = coresChat()
    val listState = rememberLazyListState()

    LaunchedEffect(atendimentoId) { vm.abrir(atendimentoId) }

    // Carregar histórico ao chegar perto do topo. Com reverseLayout, "topo
    // visual" é o FIM dos índices — daí comparar com o total.
    LaunchedEffect(listState, estado.cursor) {
        snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
            .distinctUntilChanged()
            .filter { ultimo -> estado.cursor != null && ultimo >= estado.bolhas.size - 3 }
            .collect { vm.carregarHistorico() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(titulo, maxLines = 1) },
                navigationIcon = {
                    IconButton(onClick = onVoltar) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Voltar")
                    }
                },
                colors =
                    TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.primary,
                        titleContentColor = MaterialTheme.colorScheme.onPrimary,
                        navigationIconContentColor = MaterialTheme.colorScheme.onPrimary,
                    ),
            )
        },
        bottomBar = {
            Composer(
                texto = rascunho,
                onTexto = vm::onRascunho,
                onEnviar = vm::enviar,
            )
        },
    ) { inner ->
        Box(
            modifier =
                Modifier.fillMaxSize()
                    .padding(inner)
                    .background(cores.fundoConversa),
        ) {
            when {
                estado.carregando && estado.bolhas.isEmpty() ->
                    CircularProgressIndicator(Modifier.align(Alignment.Center))
                estado.bolhas.isEmpty() ->
                    Text(
                        "Nenhuma mensagem nesta conversa.",
                        modifier = Modifier.align(Alignment.Center),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                else -> {
                    val invertidas = remember(estado.bolhas) { estado.bolhas.reversed() }
                    LazyColumn(
                        state = listState,
                        reverseLayout = true,
                        modifier = Modifier.fillMaxSize().padding(horizontal = 8.dp),
                    ) {
                        items(invertidas, key = { it.id }) { b -> BolhaItem(b, cores) }
                        if (estado.carregandoHistorico) {
                            item {
                                Box(
                                    Modifier.fillMaxWidth().padding(12.dp),
                                    contentAlignment = Alignment.Center,
                                ) { CircularProgressIndicator(Modifier.height(20.dp)) }
                            }
                        }
                    }
                }
            }

            if (estado.aviso != null) {
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth(),
                ) {
                    Text(
                        estado.aviso!!,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        modifier = Modifier.padding(8.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun BolhaItem(b: Bolha, cores: CoresChat) {
    when (b) {
        is Bolha.Texto -> {
            val entrada = b.lado == Lado.ENTRADA
            Row(
                Modifier.fillMaxWidth().padding(vertical = 2.dp),
                horizontalArrangement = if (entrada) Arrangement.Start else Arrangement.End,
            ) {
                Surface(
                    color = if (entrada) cores.bolhaEntrada else cores.bolhaSaida,
                    shape =
                        RoundedCornerShape(
                            topStart = 12.dp,
                            topEnd = 12.dp,
                            // Canto "rabinho" do lado de quem fala, como no
                            // WhatsApp: sem isso as bolhas viram cartões
                            // genéricos e a tela perde a familiaridade.
                            bottomStart = if (entrada) 2.dp else 12.dp,
                            bottomEnd = if (entrada) 12.dp else 2.dp,
                        ),
                    modifier = Modifier.widthIn(max = 300.dp),
                ) {
                    Column(Modifier.padding(horizontal = 10.dp, vertical = 6.dp)) {
                        Text(b.texto, style = MaterialTheme.typography.bodyMedium)
                        Row(
                            Modifier.align(Alignment.End),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                if (b.pendente) "enviando…" else horaCurta(b.quandoIso),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
        is Bolha.Midia ->
            Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                Surface(
                    color = cores.bolhaEntrada,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.widthIn(max = 300.dp),
                ) {
                    Column(Modifier.padding(10.dp)) {
                        // Áudio e imagem tocam/aparecem aqui mesmo. O conteúdo
                        // vem como data-URL base64 no `media_url` — decodificar
                        // e reduzir acontece fora da thread principal, em
                        // `Midia.kt`. Documento continua como rótulo: abrir
                        // arquivo pede FileProvider e visualizador externo.
                        when {
                            b.tipo?.startsWith("audio") == true ->
                                AudioDaConversa(b.url, Modifier.width(240.dp))
                            b.tipo?.startsWith("image") == true ->
                                ImagemDaConversa(b.url, Modifier.fillMaxWidth())
                            else ->
                                Text(
                                    rotuloMidia(b.tipo),
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Medium,
                                )
                        }
                        if (b.legenda != null) {
                            Spacer(Modifier.height(4.dp))
                            Text(b.legenda, style = MaterialTheme.typography.bodyMedium)
                        }
                        Text(
                            horaCurta(b.quandoIso),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        is Bolha.NotaInterna ->
            Surface(
                color = MaterialTheme.colorScheme.tertiaryContainer,
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            ) {
                Column(Modifier.padding(10.dp)) {
                    Text(
                        "Nota interna · ${b.autor ?: "—"} · não enviada ao cliente",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(b.texto, style = MaterialTheme.typography.bodyMedium)
                }
            }
        is Bolha.Erro ->
            Box(Modifier.fillMaxWidth().padding(vertical = 4.dp), Alignment.Center) {
                Text(
                    b.texto,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }
    }
}

@Composable
private fun Composer(texto: String, onTexto: (String) -> Unit, onEnviar: () -> Unit) {
    // `imePadding` sobe o composer com o teclado; `navigationBarsPadding` o
    // mantém ACIMA dos botões do Android. Com `enableEdgeToEdge()` o app desenha
    // sob as barras do sistema, e sem o segundo padding o campo de texto fica
    // atrás dos botões de navegação — foi o que aconteceu no primeiro teste em
    // aparelho real: dava pra ver a caixa, não pra usar.
    Surface(
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.imePadding().navigationBarsPadding(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(8.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            OutlinedTextField(
                value = texto,
                onValueChange = onTexto,
                placeholder = { Text("Mensagem") },
                maxLines = 5,
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(6.dp))
            IconButton(
                onClick = onEnviar,
                enabled = texto.isNotBlank(),
                modifier =
                    Modifier.clip(RoundedCornerShape(24.dp))
                        .background(MaterialTheme.colorScheme.secondary),
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.Send,
                    contentDescription = "Enviar",
                    tint = MaterialTheme.colorScheme.onSecondary,
                )
            }
        }
    }
}

private fun rotuloMidia(tipo: String?): String =
    when {
        tipo == null -> "Anexo"
        tipo.startsWith("audio") -> "Áudio recebido"
        tipo.startsWith("image") -> "Imagem recebida"
        tipo.startsWith("video") -> "Vídeo recebido"
        else -> "Documento recebido"
    }

/** Só a hora, como nas bolhas do WhatsApp. Formato inesperado devolve vazio. */
private fun horaCurta(iso: String?): String =
    if (iso == null || iso.length < 16) "" else runCatching { iso.substring(11, 16) }.getOrDefault("")
