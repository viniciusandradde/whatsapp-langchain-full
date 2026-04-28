import { hashPassword } from "better-auth/crypto";
import { Pool } from "pg";
import {
  getBootstrapAdminEmail,
  getBootstrapAdminName,
  getBootstrapAdminPassword,
  hasBootstrapAdminCredentials,
} from "./admin-defaults";

const bootstrapPool = new Pool({
  connectionString: process.env.DATABASE_URL,
  options: "-c search_path=auth,public",
});

export interface BootstrapAdminState {
  bootstrapped: boolean;
  bootstrapConfigured: boolean;
  bootstrapEmail: string;
  userCount: number;
}

function isUniqueViolation(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === "23505"
  );
}

async function getUserCount(client?: Pool | import("pg").PoolClient) {
  const countResult = await (client || bootstrapPool).query<{ count: number }>(
    `SELECT COUNT(*)::int AS count FROM auth."user"`
  );

  return countResult.rows[0]?.count ?? 0;
}

async function createBootstrapAdmin(): Promise<boolean> {
  const email = getBootstrapAdminEmail();
  const password = getBootstrapAdminPassword();
  const name = getBootstrapAdminName();

  if (!email || !password) {
    return false;
  }

  const client = await bootstrapPool.connect();

  try {
    await client.query("BEGIN");

    const existingUsers = await getUserCount(client);
    if (existingUsers > 0) {
      await client.query("ROLLBACK");
      return false;
    }

    const userId = crypto.randomUUID();
    const accountId = crypto.randomUUID();
    const now = new Date();
    const passwordHash = await hashPassword(password);

    await client.query(
      `INSERT INTO auth."user"
        (id, name, email, "emailVerified", image, "createdAt", "updatedAt")
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [userId, name, email, false, null, now, now]
    );

    await client.query(
      `INSERT INTO auth.account
        (
          id,
          "accountId",
          "providerId",
          "userId",
          "accessToken",
          "refreshToken",
          "idToken",
          "accessTokenExpiresAt",
          "refreshTokenExpiresAt",
          password,
          "createdAt",
          "updatedAt"
        )
       VALUES
        ($1, $2, $3, $4, NULL, NULL, NULL, NULL, NULL, $5, $6, $7)`,
      [accountId, userId, "credential", userId, passwordHash, now, now]
    );

    await client.query("COMMIT");
    return true;
  } catch (error) {
    await client.query("ROLLBACK").catch(() => undefined);

    if (isUniqueViolation(error)) {
      return false;
    }

    throw error;
  } finally {
    client.release();
  }
}

export async function ensureBootstrapAdmin(): Promise<BootstrapAdminState> {
  const userCount = await getUserCount();
  const bootstrapConfigured = hasBootstrapAdminCredentials();
  const bootstrapEmail = getBootstrapAdminEmail();

  if (userCount > 0) {
    return {
      bootstrapped: false,
      bootstrapConfigured,
      bootstrapEmail,
      userCount,
    };
  }

  if (!bootstrapConfigured) {
    return {
      bootstrapped: false,
      bootstrapConfigured: false,
      bootstrapEmail,
      userCount: 0,
    };
  }

  const bootstrapped = await createBootstrapAdmin();
  const currentUserCount = bootstrapped ? 1 : await getUserCount();

  return {
    bootstrapped,
    bootstrapConfigured: true,
    bootstrapEmail,
    userCount: currentUserCount,
  };
}
