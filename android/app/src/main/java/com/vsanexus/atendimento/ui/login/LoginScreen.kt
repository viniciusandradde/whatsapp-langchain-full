package com.vsanexus.atendimento.ui.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.vsanexus.atendimento.data.EmpresaResumo

/**
 * Login e escolha de empresa.
 *
 * Duas etapas na mesma tela em vez de duas rotas: a segunda só aparece quando
 * o usuário tem mais de uma empresa, e navegar pra uma tela que muitas vezes é
 * pulada complica o back sem ganho.
 */
@Composable
fun LoginScreen(vm: LoginViewModel = hiltViewModel()) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val sessao by vm.sessao.collectAsStateWithLifecycle()

    if (sessao.precisaEscolherEmpresa) {
        EscolhaEmpresa(
            empresas = ui.empresas,
            carregando = ui.carregandoEmpresas,
            onEscolher = vm::escolher,
            onRecarregar = vm::carregarEmpresas,
            onSair = vm::sair,
        )
    } else {
        FormularioLogin(ui = ui, onEmail = vm::onEmail, onSenha = vm::onSenha, onEntrar = vm::entrar)
    }
}

@Composable
private fun FormularioLogin(
    ui: LoginUiState,
    onEmail: (String) -> Unit,
    onSenha: (String) -> Unit,
    onEntrar: () -> Unit,
) {
    var senhaVisivel by remember { mutableStateOf(false) }

    Column(
        modifier =
            Modifier.fillMaxSize()
                .verticalScroll(rememberScrollState())
                // imePadding: sem isto o teclado cobre o botão Entrar em
                // aparelho de tela pequena.
                .imePadding()
                .padding(28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Nexus Atendimento", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(4.dp))
        Text(
            "Entre com a mesma conta do painel",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(28.dp))

        OutlinedTextField(
            value = ui.email,
            onValueChange = onEmail,
            label = { Text("E-mail") },
            singleLine = true,
            enabled = !ui.carregando,
            keyboardOptions =
                KeyboardOptions(
                    keyboardType = KeyboardType.Email,
                    imeAction = ImeAction.Next,
                ),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = ui.senha,
            onValueChange = onSenha,
            label = { Text("Senha") },
            singleLine = true,
            enabled = !ui.carregando,
            visualTransformation =
                if (senhaVisivel) {
                    VisualTransformation.None
                } else {
                    PasswordVisualTransformation()
                },
            keyboardOptions =
                KeyboardOptions(
                    keyboardType = KeyboardType.Password,
                    imeAction = ImeAction.Done,
                ),
            keyboardActions = KeyboardActions(onDone = { onEntrar() }),
            trailingIcon = {
                IconButton(onClick = { senhaVisivel = !senhaVisivel }) {
                    Icon(
                        imageVector =
                            if (senhaVisivel) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                        contentDescription = if (senhaVisivel) "Ocultar senha" else "Mostrar senha",
                    )
                }
            },
            modifier = Modifier.fillMaxWidth(),
        )

        if (ui.erro != null) {
            Spacer(Modifier.height(12.dp))
            Text(
                ui.erro,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
            )
        }

        Spacer(Modifier.height(24.dp))
        Button(
            onClick = onEntrar,
            enabled = ui.podeEntrar,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (ui.carregando) {
                CircularProgressIndicator(
                    modifier = Modifier.height(18.dp),
                    strokeWidth = 2.dp,
                    color = MaterialTheme.colorScheme.onPrimary,
                )
            } else {
                Text("Entrar")
            }
        }
    }
}

@Composable
private fun EscolhaEmpresa(
    empresas: List<EmpresaResumo>,
    carregando: Boolean,
    onEscolher: (EmpresaResumo) -> Unit,
    onRecarregar: () -> Unit,
    onSair: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Escolha a empresa", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(16.dp))

        when {
            carregando ->
                CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
            empresas.isEmpty() -> {
                Text(
                    "Não foi possível carregar suas empresas.",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(Modifier.height(12.dp))
                Button(onClick = onRecarregar) { Text("Tentar de novo") }
                Spacer(Modifier.height(8.dp))
                Button(onClick = onSair) { Text("Sair") }
            }
            else ->
                // Um botão por empresa, sem ListItem: em Compose BOM
                // 2024.10.01 o ListItem ainda pede @OptIn, e aqui ele só
                // repetiria o texto que já está no botão.
                empresas.forEach { e ->
                    Button(
                        onClick = { onEscolher(e) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(e.nome)
                    }
                    Spacer(Modifier.height(8.dp))
                }
        }
    }
}
