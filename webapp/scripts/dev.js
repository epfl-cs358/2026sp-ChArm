#!/usr/bin/env node

const { execFile, spawn } = require("node:child_process");
const readline = require("node:readline");

const ports = [
  { port: 8765, name: "backend" },
  { port: 3000, name: "frontend" },
];

function execFileText(command, args) {
  return new Promise((resolve) => {
    execFile(command, args, { windowsHide: true }, (error, stdout) => {
      if (error) {
        resolve("");
        return;
      }
      resolve(stdout.trim());
    });
  });
}

async function pidsForPort(port) {
  if (process.platform === "win32") {
    const output = await execFileText("netstat", ["-ano", "-p", "tcp"]);
    const pids = new Set();
    for (const line of output.split(/\r?\n/)) {
      const normalized = line.trim().replace(/\s+/g, " ");
      if (!normalized.includes(`:${port} `) || !normalized.includes("LISTENING")) {
        continue;
      }
      const pid = normalized.split(" ").at(-1);
      if (/^\d+$/.test(pid)) {
        pids.add(pid);
      }
    }
    return [...pids];
  }

  const output = await execFileText("lsof", [
    "-nP",
    `-iTCP:${port}`,
    "-sTCP:LISTEN",
    "-t",
  ]);
  const lsofPids = output.split(/\s+/).filter(Boolean);
  if (lsofPids.length > 0 || process.platform !== "linux") {
    return [...new Set(lsofPids)];
  }

  const ssOutput = await execFileText("ss", ["-ltnp", `sport = :${port}`]);
  const ssPids = [...ssOutput.matchAll(/pid=(\d+)/g)].map((match) => match[1]);
  return [...new Set(ssPids)];
}

function askYesNo(question) {
  if (process.env.CHARM_DEV_KILL_PORTS === "yes") {
    return Promise.resolve(true);
  }

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    rl.question(`${question} [Y/n] `, (answer) => {
      rl.close();
      const normalized = answer.trim().toLowerCase();
      resolve(normalized === "" || normalized === "y" || normalized === "yes");
    });
  });
}

async function killPids(pids) {
  if (pids.length === 0) {
    return;
  }

  if (process.platform === "win32") {
    await Promise.all(
      pids.map((pid) => execFileText("taskkill", ["/PID", pid, "/F"])),
    );
    return;
  }

  try {
    for (const pid of pids) {
      process.kill(Number(pid), "SIGTERM");
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
    for (const pid of pids) {
      try {
        process.kill(Number(pid), 0);
        process.kill(Number(pid), "SIGKILL");
      } catch {
        // Process already exited after SIGTERM.
      }
    }
  } catch (error) {
    console.error(`Failed to kill process on port: ${error.message}`);
  }
}

async function ensurePortsAvailable() {
  for (const { port, name } of ports) {
    const pids = await pidsForPort(port);
    if (pids.length === 0) {
      continue;
    }

    const shouldKill = await askYesNo(
      `Port ${port} (${name}) is already in use by PID(s) ${pids.join(", ")}. Kill them?`,
    );

    if (!shouldKill) {
      console.error(`Cannot start dev server while port ${port} is occupied.`);
      process.exit(1);
    }

    await killPids(pids);
  }
}

function runDevServers() {
  const command = process.platform === "win32" ? "npx.cmd" : "npx";
  const child = spawn(
    command,
    [
      "concurrently",
      "-k",
      "-n",
      "backend,frontend",
      "-c",
      "cyan,magenta",
      "python ../webapp_backend/api_server.py",
      "node -e \"setTimeout(()=>{},1000)\" && next dev",
    ],
    {
      stdio: "inherit",
      shell: process.platform === "win32",
    },
  );

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  });
}

async function main() {
  await ensurePortsAvailable();
  runDevServers();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
