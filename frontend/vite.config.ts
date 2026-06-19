import fs from "node:fs";
import path from "node:path";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

function readRepoEnv(envRoot: string): Record<string, string> {
  const envPath = path.join(envRoot, ".env");

  if (!fs.existsSync(envPath)) {
    return {};
  }

  const entries: Record<string, string> = {};

  for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");

    if (separatorIndex === -1) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    let value = trimmed.slice(separatorIndex + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    entries[key] = value;
  }

  return entries;
}

export default defineConfig(({ mode }) => {
  const envRoot = path.resolve(__dirname, "..");
  const env = {
    ...loadEnv(mode, envRoot, ""),
    ...readRepoEnv(envRoot),
  };
  const rawBackendHost = env.BACKEND_HOST?.trim();
  const backendHost =
    rawBackendHost && !["0.0.0.0", "::"].includes(rawBackendHost)
      ? rawBackendHost === "localhost"
        ? "127.0.0.1"
        : rawBackendHost
      : "127.0.0.1";
  const backendPort = env.BACKEND_PORT || "8000";
  const backendTarget = `http://${backendHost}:${backendPort}`;

  console.log(`[vite] proxy target: ${backendTarget}`);

  return {
    envDir: envRoot,
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        "/api": backendTarget,
        "/health": backendTarget,
      },
    },
  };
});
