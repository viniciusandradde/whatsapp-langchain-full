package com.vsanexus.atendimento.push

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.vsanexus.atendimento.MainActivity
import com.vsanexus.atendimento.R
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Canal único de mensagens — criado on-demand (idempotente). */
private const val CANAL_MENSAGENS = "mensagens"

/**
 * Recebe os data-pushes do backend (mig 168) e monta a notificação.
 *
 * O backend manda SÓ dados (`data`), nunca `notification` — de propósito: é
 * este código que decide exibir, e `tag = atendimento_id` faz várias
 * mensagens da mesma conversa colapsarem num aviso só, atualizado, em vez de
 * empilhar dez.
 */
@AndroidEntryPoint
class PushService : FirebaseMessagingService() {
    @Inject lateinit var pushRepository: PushRepository

    @Inject lateinit var conversaAtual: ConversaAtual

    private val escopo = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /** FCM girou o token do aparelho — re-registra no backend. */
    override fun onNewToken(token: String) {
        escopo.launch { pushRepository.registrarToken(token) }
    }

    override fun onMessageReceived(mensagem: RemoteMessage) {
        val dados = mensagem.data
        val atendimentoId = dados["atendimento_id"]?.toLongOrNull() ?: return
        // A conversa que o operador está LENDO não precisa de notificação —
        // o SSE já mostrou a mensagem na tela.
        if (conversaAtual.id == atendimentoId) return
        // Android 13+ exige a permissão de runtime; sem ela o notify() é
        // engolido em silêncio — melhor nem montar.
        val pode =
            ContextCompat.checkSelfPermission(
                this, Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED ||
                android.os.Build.VERSION.SDK_INT < 33
        if (!pode) return

        val gerente = getSystemService(NotificationManager::class.java)
        gerente.createNotificationChannel(
            NotificationChannel(
                CANAL_MENSAGENS,
                "Mensagens de clientes",
                NotificationManager.IMPORTANCE_HIGH,
            ),
        )

        // Tocar abre DIRETO a conversa: o extra viaja pra MainActivity, que é
        // singleTop — app aberto recebe em onNewIntent, fechado em onCreate.
        val intent =
            Intent(this, MainActivity::class.java).apply {
                putExtra("atendimento_id", atendimentoId)
                putExtra("titulo", dados["titulo"] ?: "")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            }
        val pendente =
            PendingIntent.getActivity(
                this,
                // requestCode por conversa: sem isso o Android reusa o
                // PendingIntent anterior e toda notificação abriria a PRIMEIRA
                // conversa notificada.
                atendimentoId.toInt(),
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )

        val aviso =
            NotificationCompat.Builder(this, CANAL_MENSAGENS)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(dados["titulo"] ?: "Nova mensagem")
                .setContentText(dados["corpo"] ?: "")
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setContentIntent(pendente)
                .build()

        // tag = conversa: a segunda mensagem da mesma conversa SUBSTITUI o
        // aviso, não empilha.
        gerente.notify("atd-$atendimentoId", 1, aviso)
    }
}
