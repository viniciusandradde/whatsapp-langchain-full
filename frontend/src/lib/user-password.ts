import { hashPassword } from "better-auth/crypto";
import { Pool } from "pg";

const passwordPool = new Pool({
  connectionString: process.env.DATABASE_URL,
  options: "-c search_path=auth,public",
});

/**
 * UPSERT da credencial password do user no `auth.account` (providerId='credential').
 *
 * Replica o que `auth.api.setUserPassword` do admin plugin faria, mas sem
 * requerer o plugin. Usado por:
 * - criarUsuarioAction (set inicial após criar user)
 * - resetarSenhaUsuarioAction
 * - members/actions::resetMemberPasswordAction (fallback quando admin plugin
 *   não está disponível)
 *
 * Hash via better-auth/crypto (scrypt, mesma família que o Better Auth usa
 * internamente). Senhas geradas aqui validam em `signIn.email` normalmente.
 */
export async function upsertUserPassword(
  userId: string,
  newPassword: string
): Promise<void> {
  if (!userId || !newPassword) {
    throw new Error("userId e newPassword são obrigatórios");
  }
  const passwordHash = await hashPassword(newPassword);
  const now = new Date();

  const client = await passwordPool.connect();
  try {
    await client.query("BEGIN");

    const existing = await client.query<{ id: string }>(
      `SELECT id FROM auth.account
       WHERE "userId" = $1 AND "providerId" = 'credential'
       LIMIT 1`,
      [userId]
    );

    if (existing.rows.length > 0) {
      await client.query(
        `UPDATE auth.account
         SET password = $1, "updatedAt" = $2
         WHERE id = $3`,
        [passwordHash, now, existing.rows[0].id]
      );
    } else {
      const accountId = crypto.randomUUID();
      await client.query(
        `INSERT INTO auth.account
          (id, "accountId", "providerId", "userId",
           "accessToken", "refreshToken", "idToken",
           "accessTokenExpiresAt", "refreshTokenExpiresAt",
           password, "createdAt", "updatedAt")
         VALUES ($1, $2, 'credential', $3,
                 NULL, NULL, NULL, NULL, NULL,
                 $4, $5, $6)`,
        [accountId, userId, userId, passwordHash, now, now]
      );
    }

    await client.query("COMMIT");
  } catch (e) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw e;
  } finally {
    client.release();
  }
}
