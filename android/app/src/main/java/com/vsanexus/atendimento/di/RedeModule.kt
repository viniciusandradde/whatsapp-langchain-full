package com.vsanexus.atendimento.di

import android.content.Context
import com.vsanexus.atendimento.BuildConfig
import com.vsanexus.atendimento.data.local.SessaoStore
import com.vsanexus.atendimento.data.local.SessaoStoreCriptografado
import com.vsanexus.atendimento.data.remote.AtendimentoApi
import com.vsanexus.atendimento.data.remote.AuthApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Qualifier
import javax.inject.Singleton

/** Retrofit da API de atendimento (FastAPI, api.vsanexus.com). */
@Qualifier @Retention(AnnotationRetention.BINARY) annotation class ApiRetrofit

/** Retrofit do Better Auth (Next.js, chat.vsanexus.com). */
@Qualifier @Retention(AnnotationRetention.BINARY) annotation class AuthRetrofit

/** OkHttp sem timeout de leitura, para streams SSE. */
@Qualifier @Retention(AnnotationRetention.BINARY) annotation class SseClient

@Module
@InstallIn(SingletonComponent::class)
object RedeModule {
    @Provides
    @Singleton
    fun sessaoStore(@ApplicationContext ctx: Context): SessaoStore =
        SessaoStoreCriptografado(ctx)

    @Provides
    @Singleton
    fun json() =
        Json {
            // Campo novo na API não pode derrubar o app. O backend evolui sem
            // versionar payload; sem isto, cada coluna nova viraria crash.
            ignoreUnknownKeys = true
            // Deixa o default do DTO valer quando a chave vem null.
            coerceInputValues = true
            explicitNulls = false
        }

    @Provides
    @Singleton
    fun okHttp(sessao: SessaoStore): OkHttpClient {
        val autenticacao =
            Interceptor { chain ->
                val req = chain.request()
                val token = sessao.token
                val comAuth =
                    if (token == null) {
                        req
                    } else {
                        req.newBuilder()
                            // Token de SESSÃO, não o service token. O backend
                            // resolve o usuário em auth.session e ignora
                            // qualquer header de identidade — por isso o app
                            // não manda, e nem poderia forjar.
                            .header("Authorization", "Bearer $token")
                            .apply {
                                sessao.empresaId?.let { header("X-Empresa-Id", it.toString()) }
                            }
                            .build()
                    }
                val resp = chain.proceed(comAuth)
                // 401 = token morto (expirou ou a sessão foi revogada no
                // servidor). Limpar aqui evita o app insistir para sempre com
                // credencial inválida; a UI observa `estado` e volta ao login.
                if (resp.code == 401 && token != null) sessao.limpar()
                resp
            }

        val log =
            HttpLoggingInterceptor().apply {
                // NUNCA BODY: o corpo do login carrega a senha e o header
                // carrega o token de sessão. Em release, nada.
                level =
                    if (BuildConfig.DEBUG) {
                        HttpLoggingInterceptor.Level.BASIC
                    } else {
                        HttpLoggingInterceptor.Level.NONE
                    }
            }

        return OkHttpClient.Builder()
            .addInterceptor(autenticacao)
            .addInterceptor(log)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    /**
     * Cliente para SSE — o mesmo, só sem timeout de leitura.
     *
     * `readTimeout(0)` é obrigatório: um stream SSE fica minutos sem enviar
     * nada, e com os 30s do cliente normal o OkHttp cortaria a conexão. O
     * heartbeat do servidor é de 25s, o que sobreviveria por 5 segundos de
     * margem — perto o bastante para quebrar no primeiro soluço de rede.
     *
     * `pingInterval` NÃO serve aqui: ping frame é HTTP/2 e WebSocket, e não
     * mantém viva uma resposta SSE em HTTP/1.1.
     *
     * Deriva de `newBuilder()` para herdar os interceptors — é o de
     * autenticação que injeta o Bearer e limpa a sessão no 401.
     */
    @Provides
    @Singleton
    @SseClient
    fun okHttpSse(client: OkHttpClient): OkHttpClient =
        client.newBuilder().readTimeout(0, TimeUnit.MILLISECONDS).build()

    @Provides
    @Singleton
    @ApiRetrofit
    fun apiRetrofit(client: OkHttpClient, json: Json): Retrofit =
        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()

    @Provides
    @Singleton
    @AuthRetrofit
    fun authRetrofit(client: OkHttpClient, json: Json): Retrofit =
        Retrofit.Builder()
            .baseUrl(BuildConfig.AUTH_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()

    @Provides
    @Singleton
    fun atendimentoApi(@ApiRetrofit r: Retrofit): AtendimentoApi = r.create(AtendimentoApi::class.java)

    @Provides
    @Singleton
    fun authApi(@AuthRetrofit r: Retrofit): AuthApi = r.create(AuthApi::class.java)
}
