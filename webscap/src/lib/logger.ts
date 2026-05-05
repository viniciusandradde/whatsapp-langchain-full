/**
 * Logger minimalista — sem dep externa. Cada linha JSON com level + msg
 * + extra. Prefere stdout pra fácil grep/jq em CI.
 */

export type LogLevel = "debug" | "info" | "warn" | "error";

const LEVEL_RANK: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

const ENV_LEVEL = (process.env["LOG_LEVEL"] as LogLevel) || "info";
const MIN_RANK = LEVEL_RANK[ENV_LEVEL] ?? 20;

function emit(level: LogLevel, msg: string, extra?: Record<string, unknown>) {
  if (LEVEL_RANK[level] < MIN_RANK) return;
  const entry = {
    ts: new Date().toISOString(),
    level,
    msg,
    ...(extra ?? {}),
  };
  // Pretty pra TTY, JSON pra CI/pipe
  if (process.stdout.isTTY) {
    const color =
      level === "error"
        ? "\x1b[31m"
        : level === "warn"
          ? "\x1b[33m"
          : level === "debug"
            ? "\x1b[90m"
            : "\x1b[36m";
    const reset = "\x1b[0m";
    const extraStr = extra
      ? " " + JSON.stringify(extra).replace(/[{}]/g, "")
      : "";
    console.log(`${color}[${level}]${reset} ${msg}${extraStr}`);
  } else {
    console.log(JSON.stringify(entry));
  }
}

export const log = {
  debug: (msg: string, extra?: Record<string, unknown>) =>
    emit("debug", msg, extra),
  info: (msg: string, extra?: Record<string, unknown>) =>
    emit("info", msg, extra),
  warn: (msg: string, extra?: Record<string, unknown>) =>
    emit("warn", msg, extra),
  error: (msg: string, extra?: Record<string, unknown>) =>
    emit("error", msg, extra),
};
