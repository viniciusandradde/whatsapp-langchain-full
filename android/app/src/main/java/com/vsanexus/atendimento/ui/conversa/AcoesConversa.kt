package com.vsanexus.atendimento.ui.conversa

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.vsanexus.atendimento.data.remote.AtendenteDto
import com.vsanexus.atendimento.data.remote.AtendimentoDto
import com.vsanexus.atendimento.data.remote.DepartamentoDto

/**
 * As ações e cartões que dão à conversa do app a paridade com o drawer web:
 * triagem, encerrar, transferir, tags e ficha do cliente.
 *
 * Nota pra quem editar: comentário de bloco em Kotlin ANINHA — nunca termine
 * um caminho com asterisco dentro de KDoc.
 */

/** Converte "#RRGGBB" do catálogo de tags em Color; inválido vira cinza. */
internal fun corDeHex(hex: String?): Color =
    runCatching {
        val s = (hex ?: "").removePrefix("#")
        if (s.length != 6) error("fora do formato")
        Color(0xFF000000 or s.toLong(16))
    }.getOrDefault(Color(0xFF9CA3AF))

/**
 * Cartão de triagem — o que a IA apurou antes de qualquer humano abrir a
 * conversa. Read-only aqui e no web: quem escreve é o agente, via tools.
 *
 * Colapsável porque rouba altura da timeline; começa aberto quando há resumo
 * (é a informação que evita ler a conversa inteira) e lembra a escolha
 * enquanto a tela viver.
 */
@Composable
fun TriagemCard(detalhe: AtendimentoDto, modifier: Modifier = Modifier) {
    val temConteudo =
        detalhe.resumoIa != null || detalhe.prioridade != null ||
            detalhe.sentimento != null || detalhe.classificacao != null
    if (!temConteudo) return

    var aberto by rememberSaveable(detalhe.id) { mutableStateOf(detalhe.resumoIa != null) }

    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(10.dp),
        modifier = modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp),
    ) {
        Column(Modifier.clickable { aberto = !aberto }.padding(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Triagem da IA",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    if (aberto) "ocultar" else "ver",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            if (aberto) {
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    detalhe.prioridade?.let { ChipTriagem(rotuloPrioridade(it), corPrioridade(it)) }
                    detalhe.sentimento?.let { ChipTriagem(it, corSentimento(it)) }
                    detalhe.classificacao?.let {
                        ChipTriagem(it, MaterialTheme.colorScheme.outline)
                    }
                }
                if (detalhe.resumoIa != null) {
                    Spacer(Modifier.height(6.dp))
                    Text(detalhe.resumoIa, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun ChipTriagem(texto: String, cor: Color) {
    Surface(
        color = cor.copy(alpha = 0.15f),
        shape = RoundedCornerShape(999.dp),
    ) {
        Text(
            texto,
            style = MaterialTheme.typography.labelSmall,
            color = cor,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
        )
    }
}

private fun rotuloPrioridade(p: String) =
    when (p) {
        "urgente" -> "Urgente"
        "alta" -> "Alta"
        "media" -> "Média"
        "baixa" -> "Baixa"
        else -> p
    }

@Composable
private fun corPrioridade(p: String): Color =
    when (p) {
        "urgente" -> MaterialTheme.colorScheme.error
        "alta" -> Color(0xFFD97706)
        else -> MaterialTheme.colorScheme.outline
    }

@Composable
private fun corSentimento(s: String): Color =
    when (s) {
        "negativo", "frustrado" -> MaterialTheme.colorScheme.error
        "positivo" -> Color(0xFF16A34A)
        else -> MaterialTheme.colorScheme.outline
    }

/**
 * Confirmação de encerramento. Resolvido pode disparar a pesquisa de
 * satisfação no WhatsApp do cliente — o texto avisa, porque depois de enviada
 * não há como desenviar.
 */
@Composable
fun DialogoEncerrar(
    statusFinal: String,
    onConfirmar: () -> Unit,
    onCancelar: () -> Unit,
) {
    val resolvido = statusFinal == "resolvido"
    AlertDialog(
        onDismissRequest = onCancelar,
        title = { Text(if (resolvido) "Resolver atendimento?" else "Marcar como abandonado?") },
        text = {
            Text(
                if (resolvido) {
                    "A conversa será encerrada. Se a empresa tiver pesquisa de " +
                        "satisfação ativa, o cliente recebe a pesquisa no WhatsApp."
                } else {
                    "Use quando o cliente parou de responder. A conversa será " +
                        "encerrada sem pesquisa de satisfação."
                },
            )
        },
        confirmButton = {
            TextButton(onClick = onConfirmar) {
                Text(if (resolvido) "Resolver" else "Abandonar")
            }
        },
        dismissButton = { TextButton(onClick = onCancelar) { Text("Cancelar") } },
    )
}

/**
 * Confirmação de "incluir em números sem IA" (whitelist de BLOQUEIO, mig
 * 133): efeito forte — nenhuma conexão da empresa responde automaticamente
 * ao número — então o diálogo explica antes de executar.
 */
@Composable
fun DialogoSemIa(
    telefone: String,
    onConfirmar: () -> Unit,
    onCancelar: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onCancelar,
        title = { Text("Incluir $telefone nos números sem IA?") },
        text = {
            Text(
                "Nenhuma conexão da empresa vai responder automaticamente a " +
                    "esse número (sem agente, menu ou mensagens automáticas) " +
                    "até que ele seja removido na tela Números sem IA do painel.",
            )
        },
        confirmButton = {
            TextButton(onClick = onConfirmar) { Text("Incluir número") }
        },
        dismissButton = { TextButton(onClick = onCancelar) { Text("Cancelar") } },
    )
}

/**
 * Folha de transferência — os dois modos do popover web: departamento (vai
 * pra fila do setor; o cliente é avisado) e atendente online (assume direto,
 * sem aviso). O count de atendimentos abertos ajuda a não sobrecarregar quem
 * já está cheio.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FolhaTransferencia(
    opcoes: OpcoesTransferencia,
    onDepartamento: (DepartamentoDto) -> Unit,
    onAtendente: (AtendenteDto) -> Unit,
    onFechar: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onFechar) {
        Column(Modifier.navigationBarsPadding().padding(bottom = 16.dp)) {
            Text(
                "Transferir para…",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            when {
                opcoes.falhou ->
                    Text(
                        "Não foi possível carregar os destinos. Feche e tente de novo.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(16.dp),
                    )
                opcoes.departamentos == null && opcoes.atendentes == null ->
                    Box(Modifier.fillMaxWidth().padding(24.dp), Alignment.Center) {
                        CircularProgressIndicator()
                    }
                else ->
                    LazyColumn {
                        val deps = opcoes.departamentos.orEmpty()
                        val atds = opcoes.atendentes.orEmpty()
                        if (deps.isNotEmpty()) {
                            item { RotuloSecao("Departamentos") }
                            items(deps, key = { "d${it.id}" }) { dep ->
                                LinhaDestino(
                                    titulo = dep.nome,
                                    subtitulo = "Vai pra fila do setor — o cliente é avisado",
                                    onClick = { onDepartamento(dep) },
                                )
                            }
                        }
                        if (atds.isNotEmpty()) {
                            item { RotuloSecao("Atendentes online") }
                            items(atds, key = { "a${it.userId}" }) { atd ->
                                LinhaDestino(
                                    titulo = atd.nome ?: atd.email ?: atd.userId,
                                    subtitulo =
                                        "${atd.atendimentosAbertos} em atendimento agora",
                                    online = true,
                                    onClick = { onAtendente(atd) },
                                )
                            }
                        }
                        if (deps.isEmpty() && atds.isEmpty()) {
                            item {
                                Text(
                                    "Nenhum destino disponível: sem departamentos " +
                                        "ativos e ninguém online agora.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    modifier = Modifier.padding(16.dp),
                                )
                            }
                        }
                    }
            }
        }
    }
}

@Composable
private fun RotuloSecao(texto: String) {
    Text(
        texto,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
    )
}

@Composable
private fun LinhaDestino(
    titulo: String,
    subtitulo: String,
    online: Boolean = false,
    onClick: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (online) {
            Box(
                Modifier.size(8.dp).background(Color(0xFF16A34A), CircleShape),
            )
            Spacer(Modifier.width(8.dp))
        }
        Column {
            Text(titulo, style = MaterialTheme.typography.bodyLarge)
            Text(
                subtitulo,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * Folha de tags do atendimento. Cada toque salva na hora (delta de um item,
 * otimista com rollback) — sem botão "salvar", igual ao popover web.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FolhaTags(
    estado: EstadoTags,
    onAlternar: (Long) -> Unit,
    onFechar: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onFechar) {
        Column(Modifier.navigationBarsPadding().padding(bottom = 16.dp)) {
            Text(
                "Tags do atendimento",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            when {
                estado.falhou ->
                    Text(
                        "Não foi possível carregar as tags. Feche e tente de novo.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(16.dp),
                    )
                estado.catalogo == null ->
                    Box(Modifier.fillMaxWidth().padding(24.dp), Alignment.Center) {
                        CircularProgressIndicator()
                    }
                estado.catalogo.isEmpty() ->
                    Text(
                        "A empresa ainda não tem tags cadastradas — elas são " +
                            "criadas no painel web.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(16.dp),
                    )
                else ->
                    LazyColumn {
                        items(estado.catalogo, key = { it.id }) { tag ->
                            val marcada = tag.id in estado.aplicadas
                            Row(
                                Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                FilterChip(
                                    selected = marcada,
                                    onClick = { onAlternar(tag.id) },
                                    label = { Text(tag.nome) },
                                    leadingIcon = {
                                        Box(
                                            Modifier.size(10.dp)
                                                .background(corDeHex(tag.cor), CircleShape),
                                        )
                                    },
                                )
                            }
                        }
                    }
            }
        }
    }
}

/**
 * Ficha enxuta do cliente: contato, tags de cliente (toggle) e os últimos
 * atendimentos — o suficiente pra saber com quem se fala sem sair da conversa.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FolhaCliente(
    estado: EstadoCliente,
    onAlternarTag: (String) -> Unit,
    onFechar: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onFechar) {
        Column(Modifier.navigationBarsPadding().padding(bottom = 16.dp)) {
            when {
                estado.carregando ->
                    Box(Modifier.fillMaxWidth().padding(24.dp), Alignment.Center) {
                        CircularProgressIndicator()
                    }
                estado.cliente == null ->
                    Text(
                        "Não foi possível carregar a ficha do cliente.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(16.dp),
                    )
                else -> {
                    val c = estado.cliente
                    Text(
                        c.nome ?: "Sem nome",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(horizontal = 16.dp),
                    )
                    if (c.telefone != null) {
                        Text(
                            c.telefone,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 16.dp),
                        )
                    }
                    if (c.tags.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        RotuloSecao("Tags do cliente — toque para remover")
                        Row(
                            Modifier.padding(horizontal = 16.dp),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            c.tags.take(6).forEach { tag ->
                                FilterChip(
                                    selected = true,
                                    onClick = { onAlternarTag(tag) },
                                    label = { Text(tag) },
                                )
                            }
                        }
                    }
                    if (estado.anteriores.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        HorizontalDivider()
                        RotuloSecao("Atendimentos anteriores")
                        estado.anteriores.forEach { a ->
                            Row(
                                Modifier.fillMaxWidth()
                                    .padding(horizontal = 16.dp, vertical = 6.dp),
                            ) {
                                Column {
                                    Text(
                                        a.protocolo ?: "#${a.id}",
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.Medium,
                                    )
                                    Text(
                                        a.resumoIa ?: a.status,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 2,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
