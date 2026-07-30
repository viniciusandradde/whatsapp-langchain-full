plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "com.vsanexus.atendimento"
    compileSdk = 35

    defaultConfig {
        // Fixado no Firebase (projeto `vsanexus`) — o google-services.json só
        // valida se casar exatamente. Trocar aqui exige registrar app novo lá.
        applicationId = "com.vsanexus.atendimento"
        // 26 (Android 8) permite ícone adaptativo sem PNG por densidade e
        // cobre praticamente todo aparelho em uso hoje.
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Dois hosts porque os serviços estão em lugares diferentes: o Better
        // Auth é um handler do Next.js e não existe no FastAPI. Verificado em
        // produção — api.vsanexus.com/health devolve 200 e
        // chat.vsanexus.com/api/auth/sign-in/email devolve 400 (existe, faltou
        // corpo), não 404.
        buildConfigField("String", "API_BASE_URL", "\"https://api.vsanexus.com/\"")
        buildConfigField("String", "AUTH_BASE_URL", "\"https://chat.vsanexus.com/\"")
    }

    signingConfigs {
        // Keystore de RELEASE vindo de secrets do CI. Divergência consciente do
        // launcher-vsa, que assina em debug: no CI o `~/.android/debug.keystore`
        // é gerado a cada run, então a chave MUDA entre builds e o Android
        // recusa atualizar por cima ("assinaturas divergentes") — cada update
        // exigiria desinstalar, perdendo sessão de login e cache do Room.
        // Aqui, chave estável = update instala por cima e preserva os dados.
        //
        // Fora do CI as variáveis não existem e o bloco fica nulo; o
        // `assembleDebug` local (quando houver máquina x86_64) segue no debug
        // keystore padrão.
        create("release") {
            val ksPath = System.getenv("KEYSTORE_PATH")
            if (ksPath != null) {
                storeFile = file(ksPath)
                storePassword = System.getenv("KEYSTORE_PASSWORD")
                // Alias fixo, NÃO secret: nome de alias não é sensível, e como
                // segredo ele piorava tudo — o GitHub censura o valor em todo
                // log, e "nexus" aparece dentro do próprio nome do pacote, o
                // que transformava cada linha em `com.vsa***/atendimento`.
                keyAlias = "nexus"
                keyPassword = System.getenv("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            // Minify desligado por ora: R8 sem regras de keep para Retrofit,
            // kotlinx-serialization e Room quebra em runtime, não em build —
            // e runtime é o que eu não consigo testar aqui. Liga quando o app
            // estiver validado no aparelho.
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig =
                if (System.getenv("KEYSTORE_PATH") != null) {
                    signingConfigs.getByName("release")
                } else {
                    signingConfigs.getByName("debug")
                }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        // buildConfigField exige isto ligado desde o AGP 8.
        buildConfig = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)

    // Hilt. `ksp` em vez de `kapt`: kapt está em modo de manutenção e é
    // sensivelmente mais lento — e cada minuto pesa quando o CI é o único
    // lugar onde este projeto compila.
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.androidx.hilt.navigation.compose)

    // Rede
    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)

    // Persistência de sessão
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.security.crypto)

    // Room (cache local)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    debugImplementation(libs.androidx.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.turbine)
    testImplementation(libs.okhttp.mockwebserver)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
}
