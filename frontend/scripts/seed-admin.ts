/**
 * Script para criar o primeiro usuario admin.
 *
 * Em um deploy limpo nao existe usuario — este script cria o admin inicial
 * diretamente no schema auth, usando o mesmo formato de hash do Better Auth.
 *
 * Uso:
 *   npx tsx scripts/seed-admin.ts
 *
 * Variaveis de ambiente necessarias:
 *   ADMIN_EMAIL
 *   ADMIN_PASSWORD
 *   DATABASE_URL
 *
 * Opcionais:
 *   ADMIN_NAME — nome de exibicao (default: "Admin")
 *
 * O script e idempotente: se ja existir pelo menos um usuario, nao cria nada.
 */

import { ensureBootstrapAdmin } from "../src/lib/bootstrap-admin-core";

async function main() {
  console.log("Verificando bootstrap do primeiro admin...");

  try {
    const result = await ensureBootstrapAdmin();

    if (!result.bootstrapConfigured) {
      console.error(
        "Defina ADMIN_EMAIL e ADMIN_PASSWORD antes de rodar o seed."
      );
      process.exit(1);
    }

    if (result.bootstrapped) {
      console.log(`Admin criado com sucesso: ${result.bootstrapEmail}`);
      return;
    }

    console.log("Ja existe pelo menos um usuario em auth.user — nada a fazer.");
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("Erro ao criar admin:", message);
    process.exit(1);
  }
}

main().then(() => process.exit(0));
