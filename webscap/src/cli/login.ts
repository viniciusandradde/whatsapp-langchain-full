/**
 * CLI: npm run login
 */
import { interactiveLogin } from "../auth/login.js";
import { DEFAULT_CONFIG } from "../types.js";

await interactiveLogin({
  baseUrl: process.env["BASE_URL"] ?? DEFAULT_CONFIG.baseUrl,
  storageFile: process.env["AUTH_FILE"] ?? DEFAULT_CONFIG.authStorageFile,
});
