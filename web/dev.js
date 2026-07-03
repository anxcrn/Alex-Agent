import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const WORKSPACE_DIR = path.resolve(__dirname, "..");

// Detect Python executable
function getPythonExecutable() {
  const venvPythonWin = path.join(WORKSPACE_DIR, ".venv", "Scripts", "python.exe");
  if (fs.existsSync(venvPythonWin)) {
    return venvPythonWin;
  }
  const venvPythonUnix = path.join(WORKSPACE_DIR, ".venv", "bin", "python");
  if (fs.existsSync(venvPythonUnix)) {
    return venvPythonUnix;
  }
  return "python";
}

const pythonCmd = `"${getPythonExecutable()}"`;
const cliPath = `"${path.join(WORKSPACE_DIR, "cli.py")}"`;

console.log(`🔌 Launching Alex Backend Gateway: ${pythonCmd} cli.py gateway...`);

const backend = spawn(pythonCmd, [cliPath, "gateway"], {
  cwd: WORKSPACE_DIR,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: WORKSPACE_DIR },
  shell: true
});

backend.on("error", (err) => {
  console.error("❌ Failed to start Python backend:", err);
});

// Wait briefly for the backend server to bind, then start Vite
setTimeout(() => {
  console.log("🌐 Starting Vite Dev Server...");
  const npxCmd = process.platform === "win32" ? "npx.cmd" : "npx";
  const frontend = spawn(npxCmd, ["vite"], {
    cwd: __dirname,
    stdio: "inherit",
    shell: true
  });

  frontend.on("error", (err) => {
    console.error("❌ Failed to start Vite frontend:", err);
    backend.kill();
    process.exit(1);
  });

  const cleanExit = () => {
    console.log("\n🛑 Stopping servers...");
    backend.kill("SIGTERM");
    frontend.kill("SIGTERM");
    process.exit(0);
  };

  process.on("SIGINT", cleanExit);
  process.on("SIGTERM", cleanExit);
}, 1500);
