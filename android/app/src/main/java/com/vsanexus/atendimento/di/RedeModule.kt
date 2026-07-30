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
            // SSE fica aberto indefinidamente com heartbeat a cada 25s; sem
            // isto o OkHttp mataria a conexão por inatividade de leitura.
            .pingInterval(20, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

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
