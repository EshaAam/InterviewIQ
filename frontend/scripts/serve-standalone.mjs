// Serve the production build the way the Docker image does:
// `.next/standalone/server.js`, with the static and public folders copied in
// (standalone output leaves them out). Used by Playwright and `npm run serve`.
// Run `npm run build` first.
import { cpSync, existsSync } from "node:fs";
import { spawn } from "node:child_process";

const out = ".next/standalone";
if (!existsSync(`${out}/server.js`)) {
  console.error("No standalone build found — run `npm run build` first.");
  process.exit(1);
}
cpSync(".next/static", `${out}/.next/static`, { recursive: true });
cpSync("public", `${out}/public`, { recursive: true });

const server = spawn(process.execPath, ["server.js"], {
  cwd: out,
  stdio: "inherit",
  env: { ...process.env, PORT: process.env.PORT ?? "3000", HOSTNAME: "127.0.0.1" },
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
server.on("exit", (code) => process.exit(code ?? 0));
