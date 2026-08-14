package com.vsanexus.atendimento.ui.conversa

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.vsanexus.atendimento.domain.Bolha
import com.vsanexus.atendimento.domain.Lado
import com.vsanexus.atendimento.ui.theme.CoresChat
import com.vsanexus.atendimento.ui.theme.coresChat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

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
    val modoNota by vm.modoNota.collectAsStateWithLifecycle()
    val transferencia by vm.transferencia.collectAsStateWithLifecycle()
    val tags by vm.tags.collectAsStateWithLifecycle()
    val cliente by vm.cliente.collectAsStateWithLifecycle()
    val cores = coresChat()
    val listState = rememberLazyListState()
    var menuAberto by remember { mutableStateOf(false) }
    // Qual encerramento está aguardando confirmação: "resolvido"/"abandonado".
    var confirmandoEncerrar by remember { mutableStateOf<String?>(null) }
    var confirmandoSemIa by remember { mutableStateOf(false) }

    // A confirmação de ação some sozinha — é um aceno, não um estado.
    LaunchedEffect(estado.confirmacao) {
        if (estado.confirmacao != null) {
            delay(3_000)
            vm.limparConfirmacao()
        }
    }

    LaunchedEffect(atendimentoId) { vm.abrir(atendimentoId) }

    // Acompanhar a mensagem nova. Com `reverseLayout`, o índice 0 é a mais
    // recente, e inserir ali NÃO rola sozinho: o LazyColumn preserva o item que
    // estava visível, então a mensagem que acabou de chegar nasce fora da tela.
    //
    // Só rola se o operador já estava no fim (índice <= 2). Se ele subiu pra ler
    // histórico, puxar a tela pra baixo no meio da leitura seria pior que não
    // atualizar — o caso que ele reclamou é chegar mensagem enquanto olha o fim.
    val idMaisRecente = estado.bolhas.lastOrNull()?.id
    LaunchedEffect(idMaisRecente) {
        if (idMaisRecente != null && listState.firstVisibleItemIndex <= 2) {
            listState.animateScrollToItem(0)
        }
    }

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
                // "Atender" tira da fila da IA e a cala nesta conversa;
                // "Devolver à IA" desfaz. Só um dos dois aparece, pelo status —
                // e enquanto a chamada está em curso os dois ficam desabilitados,
                // porque tocar duas vezes assumiria e devolveria em sequência.
                actions = {
                    if (estado.podeAtender) {
                        TextButton(onClick = vm::assumir, enabled = !estado.mudandoDono) {
                            Text("Atender")
                        }
                    }
                    if (estado.podeDevolverParaIa) {
                        TextButton(
                            onClick = vm::devolverParaIa,
                            enabled = !estado.mudandoDono,
                        ) {
                            Text("Devolver à IA")
                        }
                    }
                    IconButton(onClick = { menuAberto = true }) {
                        Icon(Icons.Filled.MoreVert, contentDescription = "Mais ações")
                    }
                    DropdownMenu(
                        expanded = menuAberto,
                        onDismissRequest = { menuAberto = false },
                    ) {
                        DropdownMenuItem(
                            text = { Text("Ficha do cliente") },
                            onClick = {
                                menuAberto = false
                                vm.abrirCliente()
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("Tags do atendimento") },
                            onClick = {
                                menuAberto = false
                                vm.abrirTags()
                            },
                        )
                        if (estado.detalhe?.clienteTelefone != null) {
                            DropdownMenuItem(
                                text = { Text("Incluir em números sem IA") },
                                onClick = {
                                    menuAberto = false
                                    confirmandoSemIa = true
                                },
                            )
                        }
                        if (estado.aberto) {
                            DropdownMenuItem(
                                text = { Text("Transferir…") },
                                onClick = {
                                    menuAberto = false
                                    vm.carregarTransferencia()
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("Resolver atendimento") },
                                onClick = {
                                    menuAberto = false
                                    confirmandoEncerrar = "resolvido"
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("Marcar como abandonado") },
                                onClick = {
                                    menuAberto = false
                                    confirmandoEncerrar = "abandonado"
                                },
                            )
                        }
                    }
                },
                // Barra clara com texto escuro, não uma faixa laranja: no tema
                // clean da VSA a marca aparece em acento (botão de enviar, aba
                // ativa), e o topo é superfície.
                colors =
                    TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface,
                        titleContentColor = MaterialTheme.colorScheme.onSurface,
                        navigationIconContentColor = MaterialTheme.colorScheme.onSurface,
                    ),
            )
        },
        bottomBar = {
            Composer(
                texto = rascunho,
                onTexto = vm::onRascunho,
                onEnviar = vm::enviar,
                onEnviarMidia = vm::enviarMidia,
                modoNota = modoNota,
                onAlternarModoNota = vm::alternarModoNota,
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
                    Column(Modifier.fillMaxSize()) {
                    estado.detalhe?.let { TriagemCard(it) }
                    LazyColumn(
                        state = listState,
                        reverseLayout = true,
                        modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 8.dp),
                    ) {
                        items(invertidas, key = { it.id }) { b ->
                            BolhaItem(b, cores, vm::arquivoDeMidia, vm::transcrever)
                        }
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
            if (estado.confirmacao != null) {
                Surface(
                    color = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth(),
                ) {
                    Text(
                        estado.confirmacao!!,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.padding(8.dp),
                    )
                }
            }
        }
    }

    // Diálogos e folhas — fora do Scaffold pra flutuarem sobre tudo.
    confirmandoEncerrar?.let { statusFinal ->
        DialogoEncerrar(
            statusFinal = statusFinal,
            onConfirmar = {
                confirmandoEncerrar = null
                vm.encerrar(statusFinal)
            },
            onCancelar = { confirmandoEncerrar = null },
        )
    }
    if (confirmandoSemIa) {
        DialogoSemIa(
            telefone = estado.detalhe?.clienteTelefone ?: "",
            onConfirmar = {
                confirmandoSemIa = false
                vm.incluirSemIa()
            },
            onCancelar = { confirmandoSemIa = false },
        )
    }
    transferencia?.let {
        FolhaTransferencia(
            opcoes = it,
            onDepartamento = vm::transferirParaDepartamento,
            onAtendente = vm::transferirParaAtendente,
            onFechar = vm::fecharTransferencia,
        )
    }
    tags?.let {
        FolhaTags(estado = it, onAlternar = vm::alternarTag, onFechar = vm::fecharTags)
    }
    cliente?.let {
        FolhaCliente(
            estado = it,
            onAlternarTag = vm::alternarTagCliente,
            onFechar = vm::fecharCliente,
        )
    }
}

@Composable
private fun BolhaItem(
    b: Bolha,
    cores: CoresChat,
    /** `(mensagemId, éSaída) -> arquivo local`, baixando na primeira vez. */
    carregarMidia: suspend (Long, Boolean) -> File?,
    /** Transcreve a nota de voz da mensagem (mig 169). */
    transcrever: (Long) -> Unit,
) {
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
        is Bolha.Midia -> {
            // Mídia também tem lado: o operador manda foto e nota de voz pelo
            // app (mig 146), e alinhar tudo à esquerda faria o que ELE enviou
            // parecer que veio do cliente.
            val entrada = b.lado == Lado.ENTRADA
            Row(
                Modifier.fillMaxWidth().padding(vertical = 2.dp),
                horizontalArrangement = if (entrada) Arrangement.Start else Arrangement.End,
            ) {
                Surface(
                    color = if (entrada) cores.bolhaEntrada else cores.bolhaSaida,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.widthIn(max = 300.dp),
                ) {
                    Column(Modifier.padding(10.dp)) {
                        // Áudio e imagem tocam/aparecem aqui mesmo, mas o
                        // conteúdo NÃO vem na lista: é buscado por mensagem em
                        // `/mensagens/{id}/midia` quando a bolha aparece na tela.
                        // Decodificar e reduzir acontece fora da thread
                        // principal, em `Midia.kt`. Documento continua como
                        // rótulo: abrir arquivo pede FileProvider e visualizador
                        // externo.
                        val buscar: suspend () -> File? = { carregarMidia(b.mensagemId, !entrada) }
                        when {
                            b.tipo?.startsWith("audio") == true -> {
                                AudioDaConversa(b.id, buscar, Modifier.width(240.dp))
                                // Transcrição pro operador (mig 169): texto se
                                // já existe (automática ou toque anterior);
                                // senão o botão. Só entrada — o backend só
                                // transcreve áudio do cliente.
                                if (entrada && b.transcricao != null) {
                                    Spacer(Modifier.height(4.dp))
                                    Text(
                                        b.transcricao,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                } else if (entrada) {
                                    TextButton(
                                        onClick = { transcrever(b.mensagemId) },
                                        contentPadding = PaddingValues(horizontal = 8.dp),
                                    ) {
                                        Text("Transcrever")
                                    }
                                }
                            }
                            b.tipo?.startsWith("image") == true ->
                                ImagemDaConversa(b.id, buscar, Modifier.fillMaxWidth())
                            else ->
                                Text(
                                    rotuloMidia(b.tipo, entrada),
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
private fun Composer(
    texto: String,
    onTexto: (String) -> Unit,
    onEnviar: () -> Unit,
    onEnviarMidia: (File, String) -> Unit,
    /** Modo nota interna: o texto vai pra timeline da equipe, não pro cliente. */
    modoNota: Boolean = false,
    onAlternarModoNota: () -> Unit = {},
) {
    val ctx = LocalContext.current
    val escopo = rememberCoroutineScope()
    val gravador = remember { Gravador(ctx) }
    var gravando by remember { mutableStateOf(false) }
    var segundos by remember { mutableIntStateOf(0) }
    var avisoLocal by remember { mutableStateOf<String?>(null) }

    // Sair da tela gravando tem que DEVOLVER o microfone. Sem isto o
    // MediaRecorder segue segurando o mic depois da conversa fechar, e nenhum
    // outro app (nem esta tela de novo) consegue gravar até o processo morrer.
    DisposableEffect(Unit) { onDispose { gravador.cancelar() } }

    LaunchedEffect(gravando) {
        segundos = 0
        while (gravando) {
            delay(1_000)
            segundos++
        }
    }

    fun comecarGravacao() {
        if (Build.VERSION.SDK_INT < API_MINIMA_GRAVACAO) {
            avisoLocal = "Gravar áudio exige Android 10 ou superior."
            return
        }
        avisoLocal = null
        gravando = gravador.iniciar()
        if (!gravando) avisoLocal = "Não foi possível acessar o microfone."
    }

    val pedirMicrofone =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
            if (ok) {
                comecarGravacao()
            } else {
                avisoLocal = "Sem permissão de microfone."
            }
        }

    val escolherAnexo =
        rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
            if (uri == null) return@rememberLauncherForActivityResult
            escopo.launch {
                // Copiar fora da thread principal: pode ser um PDF de dezenas
                // de MB, e travar a UI por isso seria visível.
                val anexo = withContext(Dispatchers.IO) { copiarParaCache(ctx, uri) }
                if (anexo == null) {
                    avisoLocal = "Não foi possível ler o arquivo."
                } else {
                    onEnviarMidia(anexo.arquivo, anexo.mime)
                }
            }
        }

    // `imePadding` sobe o composer com o teclado; `navigationBarsPadding` o
    // mantém ACIMA dos botões do Android. Com `enableEdgeToEdge()` o app desenha
    // sob as barras do sistema, e sem o segundo padding o campo de texto fica
    // atrás dos botões de navegação — foi o que aconteceu no primeiro teste em
    // aparelho real: dava pra ver a caixa, não pra usar.
    Surface(
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.imePadding().navigationBarsPadding(),
    ) {
        Column {
            if (avisoLocal != null) {
                Text(
                    avisoLocal!!,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }

            if (gravando) {
                LinhaGravando(
                    segundos = segundos,
                    onCancelar = {
                        gravador.cancelar()
                        gravando = false
                    },
                    onEnviar = {
                        val arquivo = gravador.parar()
                        gravando = false
                        if (arquivo == null) {
                            avisoLocal = "Áudio curto demais."
                        } else {
                            onEnviarMidia(arquivo, MIME_NOTA_DE_VOZ)
                        }
                    },
                )
                return@Column
            }

            if (modoNota) {
                Surface(color = MaterialTheme.colorScheme.tertiaryContainer) {
                    Text(
                        "Nota interna — não será enviada ao cliente",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onTertiaryContainer,
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                    )
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(8.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                // Alterna o modo nota. Fica ao lado do anexo porque é uma
                // segunda forma de "conteúdo diferente de mensagem comum".
                IconButton(onClick = onAlternarModoNota) {
                    Icon(
                        Icons.Filled.EditNote,
                        contentDescription =
                            if (modoNota) "Sair do modo nota interna" else "Escrever nota interna",
                        tint =
                            if (modoNota) MaterialTheme.colorScheme.tertiary
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                IconButton(onClick = { escolherAnexo.launch("*/*") }) {
                    Icon(
                        Icons.Filled.AttachFile,
                        contentDescription = "Anexar arquivo",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                OutlinedTextField(
                    value = texto,
                    onValueChange = onTexto,
                    placeholder = { Text(if (modoNota) "Nota interna" else "Mensagem") },
                    maxLines = 5,
                    shape = RoundedCornerShape(24.dp),
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(6.dp))
                // Um botão só, que troca de função com o campo — como no
                // WhatsApp. Campo vazio grava; com texto, envia.
                val vaiEnviarTexto = texto.isNotBlank()
                IconButton(
                    onClick = {
                        if (vaiEnviarTexto) {
                            onEnviar()
                        } else {
                            pedirMicrofone.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    },
                    modifier =
                        Modifier.clip(RoundedCornerShape(24.dp))
                            // Laranja da marca é a ação primária; no modo nota o
                            // botão muda de cor junto com a faixa — o operador
                            // não pode mandar "nota" achando que era mensagem.
                            .background(
                                if (modoNota) MaterialTheme.colorScheme.tertiary
                                else MaterialTheme.colorScheme.primary,
                            ),
                ) {
                    Icon(
                        if (vaiEnviarTexto) Icons.AutoMirrored.Filled.Send else Icons.Filled.Mic,
                        contentDescription =
                            when {
                                vaiEnviarTexto && modoNota -> "Salvar nota interna"
                                vaiEnviarTexto -> "Enviar"
                                else -> "Gravar áudio"
                            },
                        tint =
                            if (modoNota) MaterialTheme.colorScheme.onTertiary
                            else MaterialTheme.colorScheme.onPrimary,
                    )
                }
            }
        }
    }
}

/** Barra que substitui o campo de texto enquanto grava. */
@Composable
private fun LinhaGravando(segundos: Int, onCancelar: () -> Unit, onEnviar: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onCancelar) {
            Icon(
                Icons.Filled.Close,
                contentDescription = "Descartar áudio",
                tint = MaterialTheme.colorScheme.error,
            )
        }
        Text(
            "Gravando  %d:%02d".format(segundos / 60, segundos % 60),
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
        IconButton(
            onClick = onEnviar,
            modifier =
                Modifier.clip(RoundedCornerShape(24.dp))
                    .background(MaterialTheme.colorScheme.primary),
        ) {
            Icon(
                Icons.AutoMirrored.Filled.Send,
                contentDescription = "Enviar áudio",
                tint = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}

private fun rotuloMidia(tipo: String?, entrada: Boolean): String {
    val verbo = if (entrada) "recebid" else "enviad"
    return when {
        tipo == null -> "Anexo"
        tipo.startsWith("audio") -> "Áudio ${verbo}o"
        tipo.startsWith("image") -> "Imagem ${verbo}a"
        tipo.startsWith("video") -> "Vídeo ${verbo}o"
        else -> "Documento ${verbo}o"
    }
}

/** Só a hora, como nas bolhas do WhatsApp. Formato inesperado devolve vazio. */
private fun horaCurta(iso: String?): String =
    if (iso == null || iso.length < 16) "" else runCatching { iso.substring(11, 16) }.getOrDefault("")
