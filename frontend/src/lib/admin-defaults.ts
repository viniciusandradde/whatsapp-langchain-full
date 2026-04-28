export const DEFAULT_ADMIN_NAME = "Admin";

function normalize(value: string | undefined): string {
  return (value || "").trim();
}

export function getBootstrapAdminEmail(): string {
  return normalize(process.env.ADMIN_EMAIL).toLowerCase();
}

export function getBootstrapAdminPassword(): string {
  return normalize(process.env.ADMIN_PASSWORD);
}

export function getBootstrapAdminName(): string {
  return normalize(process.env.ADMIN_NAME) || DEFAULT_ADMIN_NAME;
}

export function hasBootstrapAdminCredentials(): boolean {
  return (
    getBootstrapAdminEmail().length > 0 && getBootstrapAdminPassword().length > 0
  );
}
