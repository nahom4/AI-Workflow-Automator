import { defineConfig } from "@playwright/test";
import path from "path";
import fs from "fs";

// Load .env.local into process.env so live-Groq tests run without
// manually exporting vars before each `playwright test` invocation.
(function loadLocalEnv() {
  const envFile = path.join(process.cwd(), ".env.local");
  if (!fs.existsSync(envFile)) return;
  for (const line of fs.readFileSync(envFile, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const val = trimmed.slice(eq + 1).trim();
    if (!(key in process.env)) process.env[key] = val;
  }
})();

export default defineConfig({
  testDir: "./tests/integration",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3001",
    // Bypass system SOCKS proxy for local connections
    proxy: { server: "socks5://127.0.0.1:40000", bypass: "localhost,127.0.0.1" },
  },
  projects: [
    {
      name: "api",
      testMatch: /\/api\//,
      // No browser — request fixture only
    },
    {
      name: "ui",
      testMatch: /\/ui\//,
      use: { channel: "chrome" }, // use system Chrome — no Playwright browser download needed
    },
  ],
  webServer: {
    command: "npm run dev -- --port 3001",
    url: "http://localhost:3001",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      DATABASE_PATH: path.join(process.cwd(), "data", "test.db"),
      TURSO_DATABASE_URL: "",
      TURSO_AUTH_TOKEN: "",
      GROQ_API_KEY: process.env.GROQ_API_KEY ?? "",
    },
  },
});
