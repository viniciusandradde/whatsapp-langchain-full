// Projeto Android do app de atendimento (Nexus Atendimento).
//
// Mora dentro do repo do backend de propósito: o contrato de API vive em
// `src/whatsapp_langchain/server/routes/atendimento.py`, e manter os dois juntos
// evita que uma mudança de endpoint quebre o app sem ninguém perceber. O
// workflow `.github/workflows/android.yml` filtra por `android/**`, então push
// de backend não dispara build de APK e vice-versa.
//
// Single-module por decisão consciente: o app não pode ser compilado na máquina
// de desenvolvimento (aarch64, e o `aapt2` não tem build para Linux ARM64 —
// verificado, o artefato `-linux-arm64.jar` retorna 404). Toda validação
// acontece no CI, a minutos por ciclo. Multi-módulo com convention plugins
// escrito sem compilar seria caça a agulha. A separação por pacote
// (`data/`, `domain/`, `network/`, `ui/`) já espelha as fronteiras pretendidas;
// extrair para módulos Gradle depois é mecânico.

pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "NexusAtendimento"
include(":app")
