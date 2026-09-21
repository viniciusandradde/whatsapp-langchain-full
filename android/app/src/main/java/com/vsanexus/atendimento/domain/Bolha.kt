package com.vsanexus.atendimento.domain

import com.vsanexus.atendimento.data.remote.MensagemDto

/**
 * Marcadores internos que o worker grava em `response` quando NÃO enviou nada
 * ao cliente.
 *
 * São cinco hoje, e a lista tem que ficar sincronizada com
 * `worker/processor.py`. Se um marcador novo aparecer no backend e não entrar
 * aqui, o operador passa a ver texto interno como se tivesse sido enviado ao
 * cliente — e pode responder por cima achando que a IA já falou.
 *
 * O drawer web repete essa lista em
 * `frontend/src/app/atendimento/atendimento-drawer.tsx`. Duas cópias já é uma
 * demais; a terceira seria pedir divergência. O certo seria o backend expor os
 * marcadores na API — fica anotado como dívida.
 */
val MARCADORES_INTERNOS =
    listOf(
        // Operador assumiu a conversa; a IA saiu de cena.
        "[handoff humano",
        // Conexão em modo manual (mig 132) — IA desligada nela.
        "[modo manual",
        // Número na whitelist (mig 133) — apesar do nome, é lista de BLOQUEIO.
        "[whitelist",
        // IA transferiu e o atendimento aguarda atendente (mig 143).
        "[fila do departamento",
        // Cliente escreveu de novo enquanto o modelo pensava (mig 144).
        "[resposta superada",
        // Conexão em modo IA sem agente cadastrado.
        "[IA sem agente cadastrado",
        // Passou dos atendimentos do mês do plano (ADR-005 D5).
        "[limite de atendimentos do plano",
        // Robô × robô: o outro lado é uma URA e a IA parou de responder.
        "[conversa automática",
    )

/** De quem é a bolha. */
enum class Lado { ENTRADA, SAIDA }

/**
 * Uma bolha na timeline.
 *
 * Uma mensagem da API pode virar DUAS: o texto que o cliente mandou e a
 * resposta que saiu. Modelar como lista evita a UI ter que decidir isso.
 */
sealed interface Bolha {
    val id: String
    val quandoIso: String?

    data class Texto(
        override val id: String,
        override val quandoIso: String?,
        val lado: Lado,
        val texto: String,
        /** Envio ainda não confirmado pelo servidor. */
        val pendente: Boolean = false,
        /**
         * Id da MENSAGEM no servidor (mig 172), pra editar e apagar.
         *
         * O [id] acima é sintético (`"$id-out"`) e serve só de chave da lista —
         * não é endereçável na API. Nulo enquanto a bolha é otimista, quando
         * ainda não existe linha no servidor.
         *
         * Com default e no FIM: `Bolha.Texto` é construída por posição em
         * vários testes, e um parâmetro no meio quebraria todos eles.
         */
        val mensagemId: Long? = null,
        /**
         * O que o menu pode oferecer (mig 172). Quem decide é o servidor — a
         * regra depende da chave do provedor, do canal e das janelas do
         * WhatsApp, coisas que o app não tem como saber.
         */
        val podeEditar: Boolean = false,
        val podeApagar: Boolean = false,
        /** Apagada para todos: a timeline mostra o aviso, não o texto. */
        val apagada: Boolean = false,
    ) : Bolha

    data class Midia(
        override val id: String,
        override val quandoIso: String?,
        /**
         * Id da MENSAGEM no servidor — o conteúdo não vem no payload.
         *
         * A lista é pedida com `incluir_midia=false` porque o banco guarda a
         * mídia como data-URL base64 na própria linha (um PDF de 5 MB, medido em
         * produção); os bytes são buscados em `/mensagens/{id}/midia` quando a
         * bolha aparece na tela.
         */
        val mensagemId: Long,
        val tipo: String?,
        val legenda: String?,
        /**
         * Sem default de propósito: a mídia do operador vem de
         * `response_media_url` e a do cliente de `media_url` (mig 146), e um
         * default silencioso poria a foto que o operador mandou do lado do
         * cliente na timeline.
         */
        val lado: Lado,
        /**
         * Transcrição da nota de voz pro operador (mig 169). Com default e no
         * FIM da lista: só a bolha de entrada de áudio preenche, e call-sites
         * posicionais (testes) continuam válidos.
         */
        val transcricao: String? = null,
    ) : Bolha

    /** Nota interna do operador — não foi enviada ao cliente. */
    data class NotaInterna(
        override val id: String,
        override val quandoIso: String?,
        val texto: String,
        val autor: String?,
    ) : Bolha

    /**
     * Falha de processamento.
     *
     * O texto é FIXO. O detalhe técnico (`processing_failed:EvolutionSendError`)
     * nunca é mostrado ao operador — ele não age sobre isso, e expor stack de
     * servidor na tela é ruído e vazamento. Mesma regra do painel web.
     */
    data class Erro(
        override val id: String,
        override val quandoIso: String?,
    ) : Bolha {
        val texto: String get() = "Esta mensagem não pôde ser processada."
    }
}

/** True se o `response` é marcador interno, não mensagem enviada. */
fun ehMarcadorInterno(response: String?): Boolean =
    response != null && MARCADORES_INTERNOS.any { response.startsWith(it) }

/**
 * Converte uma mensagem da API nas bolhas que a timeline mostra.
 *
 * Espelha `atendimento-drawer.tsx` de propósito — divergir faria o app e o
 * painel contarem histórias diferentes sobre a mesma conversa.
 */
fun MensagemDto.paraBolhas(): List<Bolha> {
    val bolhas = mutableListOf<Bolha>()

    // 1. O que o cliente mandou. Mídia absorve o texto como legenda porque o
    //    worker junta os dois numa row só (mig 144).
    // `mediaDisponivel` é o sinal quando a lista vem sem o conteúdo (o caso do
    // app); `mediaUrl` cobre quem pedir com `incluir_midia=true`. Qualquer um dos
    // dois significa "esta mensagem tem anexo".
    if (mediaDisponivel || !mediaUrl.isNullOrBlank()) {
        bolhas +=
            Bolha.Midia(
                id = "$id-in",
                quandoIso = createdAt,
                mensagemId = id,
                tipo = mediaType,
                legenda = incomingMessage?.takeIf { it.isNotBlank() },
                lado = Lado.ENTRADA,
                transcricao = transcricao,
            )
    } else if (!incomingMessage.isNullOrBlank()) {
        bolhas += Bolha.Texto("$id-in", createdAt, Lado.ENTRADA, incomingMessage)
    }

    // 2. Nota interna tem tratamento próprio e NÃO vira bolha de saída — não
    //    foi enviada ao cliente.
    if (interna == true && !response.isNullOrBlank()) {
        bolhas += Bolha.NotaInterna("$id-nota", processedAt ?: createdAt, response, criadoPorUserId)
        return bolhas
    }

    // 3. A resposta, se de fato saiu.
    //
    //    Quando o operador mandou anexo ou nota de voz, `response` guarda a
    //    LEGENDA daquela mídia (mig 146) — então ela entra como legenda da
    //    bolha, não como uma segunda bolha de texto solta.
    if (responseMediaDisponivel || !responseMediaUrl.isNullOrBlank()) {
        bolhas +=
            Bolha.Midia(
                id = "$id-out",
                quandoIso = processedAt ?: createdAt,
                mensagemId = id,
                tipo = responseMediaType,
                legenda = response?.takeIf { it.isNotBlank() && !ehMarcadorInterno(it) },
                lado = Lado.SAIDA,
            )
    } else if (!response.isNullOrBlank() && !ehMarcadorInterno(response)) {
        // Só o lado de SAÍDA leva id e permissões: editar e apagar valem pro
        // que NÓS mandamos. Mexer em mensagem do cliente não existe no WhatsApp.
        bolhas +=
            Bolha.Texto(
                id = "$id-out",
                quandoIso = processedAt ?: createdAt,
                lado = Lado.SAIDA,
                texto = response,
                mensagemId = id,
                podeEditar = podeEditarResposta,
                podeApagar = podeApagarResposta,
                apagada = responseApagada,
            )
    }

    // 4. Falha: frase fixa, nunca o detalhe.
    if (status == "failed") {
        bolhas += Bolha.Erro("$id-erro", processedAt ?: createdAt)
    }

    return bolhas
}
