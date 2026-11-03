const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { execFile, spawn } = require("node:child_process");

const HOST = "127.0.0.1";
const PORT = Number(process.env.LIBRETTO_UI_PORT || 4173);
const UI_DIR = __dirname;
const MAX_BODY = 4096;
const MAX_SLICE = 64 * 1024;
const JOURNAL_WAIT_MS = 15000;

const PHASES = [
  {
    value: 1,
    title: "Phase 1 — personnages",
    detail: "Le programme s’arrête une fois les rôles identifiés.",
    actions: [
      ["OCR GLM", "lecture optique de la page"],
      ["Comptes", "systèmes et portées, de haut en bas"],
      ["Personnages", "rôle de chaque portée"],
    ],
  },
  {
    value: 2,
    title: "Phase 2 — paroles",
    detail: "Le programme s’arrête une fois les paroles relevées.",
    actions: [
      ["OCR GLM", "lecture optique de la page"],
      ["Comptes", "systèmes et portées, de haut en bas"],
      ["Personnages", "rôle de chaque portée"],
      ["Paroles", "acte, scène, didascalies et dialogue"],
    ],
  },
  {
    value: 3,
    title: "Phase 3 — livret",
    detail: "Le programme enchaîne jusqu’à l’écriture des vers.",
    actions: [
      ["OCR GLM", "lecture optique de la page"],
      ["Comptes", "systèmes et portées, de haut en bas"],
      ["Personnages", "rôle de chaque portée"],
      ["Paroles", "acte, scène, didascalies et dialogue"],
      ["Livret", "écriture et correction des vers"],
    ],
  },
];

const FILES = new Map([
  ["/", ["index.html", "text/html; charset=utf-8"]],
  ["/index.html", ["index.html", "text/html; charset=utf-8"]],
  ["/style.css", ["style.css", "text/css; charset=utf-8"]],
  ["/app.js", ["app.js", "text/javascript; charset=utf-8"]],
]);

function fail(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function extractorRoot() {
  if (process.env.LIBRETTO_ROOT) return path.resolve(process.env.LIBRETTO_ROOT);
  const local = path.resolve(UI_DIR, "..");
  if (fs.existsSync(path.join(local, "libretto_printer", "journal.py"))) return local;
  return path.resolve(local, "..", "local-libretto-printer");
}

function resolvePdf(partitionsDir, relativeName) {
  if (typeof relativeName !== "string" || relativeName.includes("\0") || path.isAbsolute(relativeName)) {
    throw fail(400, "PDF refusé.");
  }
  if (relativeName.split(/[\\/]/).includes("..")) throw fail(400, "PDF refusé.");
  const partitions = fs.realpathSync(partitionsDir);
  const candidate = path.resolve(partitions, relativeName);
  const relative = path.relative(partitions, candidate);
  if (relative.startsWith("..") || path.isAbsolute(relative)) throw fail(400, "PDF refusé.");
  const stat = fs.lstatSync(candidate);
  if (!stat.isFile() || stat.isSymbolicLink()) throw fail(400, "PDF refusé.");
  if (path.extname(candidate).toLowerCase() !== ".pdf") throw fail(400, "PDF refusé.");
  return candidate;
}

function assertJournal(outDir, journalPath) {
  if (typeof journalPath !== "string" || journalPath.includes("\0")) {
    throw fail(400, "Journal refusé.");
  }
  const out = fs.realpathSync(outDir);
  const stat = fs.lstatSync(journalPath);
  if (!stat.isFile() || stat.isSymbolicLink()) throw fail(400, "Journal refusé.");
  const resolved = fs.realpathSync(journalPath);
  if (path.basename(resolved) !== "journal.log") throw fail(400, "Journal refusé.");
  if (path.dirname(path.dirname(resolved)) !== out) throw fail(400, "Journal refusé.");
  return resolved;
}

function validateRun(pageCount, start, end, phase) {
  if (!Number.isInteger(pageCount) || pageCount < 1) {
    throw fail(400, "Nombre de pages illisible.");
  }
  if (!Number.isInteger(start) || !Number.isInteger(end)) {
    throw fail(400, "Les pages doivent être des entiers.");
  }
  if (start < 1 || end < start || end > pageCount) {
    throw fail(400, "L’intervalle de pages est hors du PDF.");
  }
  if (phase !== 1 && phase !== 2 && phase !== 3) throw fail(400, "La phase vaut 1, 2 ou 3.");
}

function extractionArgs({ pdf, config, start, end, phase }) {
  return [
    pdf,
    "--config",
    config,
    "--start",
    String(start),
    "--end",
    String(end),
    "--phase",
    String(phase),
  ];
}

function pythonCommand(root) {
  const venv = path.join(root, ".venv", "bin", "python");
  if (fs.existsSync(venv)) return venv;
  return "python3";
}

function listPdfs(partitionsDir) {
  const found = [];
  function walk(dir) {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile() && entry.name.toLowerCase().endsWith(".pdf")) {
        found.push(path.relative(partitionsDir, full));
      }
    }
  }
  walk(partitionsDir);
  found.sort((left, right) => left.localeCompare(right, "fr"));
  return found;
}

function pageCount(pdf) {
  return new Promise((resolve, reject) => {
    execFile("pdfinfo", [pdf], { timeout: 10000 }, (error, stdout) => {
      if (error) {
        reject(fail(500, "Impossible de lire le nombre de pages."));
        return;
      }
      const match = String(stdout).match(/^Pages:\s+(\d+)$/m);
      if (!match) {
        reject(fail(500, "Impossible de lire le nombre de pages."));
        return;
      }
      resolve(Number(match[1]));
    });
  });
}

function relativeToRoot(root, file) {
  if (!file) return "";
  const relative = path.relative(root, file);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return "";
  return relative;
}

const clients = new Set();
let run = null;
let currentJournal = null;
let journalFd = null;
let watcher = null;

function sendEvent(response, name, payload) {
  response.write(`event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`);
}

function broadcast(name, payload) {
  for (const client of clients) {
    try {
      sendEvent(client.response, name, payload);
    } catch {
      clients.delete(client);
    }
  }
}

function closeJournal() {
  if (watcher) {
    watcher.close();
    watcher = null;
  }
  if (journalFd !== null) {
    fs.closeSync(journalFd);
    journalFd = null;
  }
}

function pump() {
  if (journalFd === null || clients.size === 0) return;
  let size;
  try {
    size = fs.fstatSync(journalFd).size;
  } catch {
    return;
  }
  const pending = [...clients].filter((client) => client.offset < size);
  if (pending.length === 0) return;
  const start = Math.min(...pending.map((client) => client.offset));
  const length = Math.min(size - start, MAX_SLICE);
  const buffer = Buffer.alloc(length);
  fs.readSync(journalFd, buffer, 0, length, start);
  const end = start + length;
  for (const client of pending) {
    if (client.offset >= end) continue;
    const text = client.decoder.decode(buffer.subarray(client.offset - start), { stream: true });
    client.offset = end;
    if (text) sendEvent(client.response, "chunk", { text });
  }
  if (end < size) setImmediate(pump);
}

function watchJournal(file) {
  closeJournal();
  currentJournal = file;
  for (const client of clients) {
    client.offset = 0;
    client.decoder = new TextDecoder("utf-8");
    sendEvent(client.response, "reset", {});
    sendEvent(client.response, "journal", { path: relativeToRoot(extractorRoot(), file) });
  }
  if (!file) return;
  journalFd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    watcher = fs.watch(file, { persistent: true }, () => pump());
  } catch {
    watcher = null;
  }
  pump();
}

function latestJournal(outDir) {
  let best = null;
  let bestTime = -1;
  let entries;
  try {
    entries = fs.readdirSync(outDir, { withFileTypes: true });
  } catch {
    return null;
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.isSymbolicLink()) continue;
    const candidate = path.join(outDir, entry.name, "journal.log");
    try {
      const safe = assertJournal(outDir, candidate);
      const modified = fs.statSync(safe).mtimeMs;
      if (modified > bestTime) {
        best = safe;
        bestTime = modified;
      }
    } catch {
      continue;
    }
  }
  return best;
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(fail(413, "Requête trop grande."));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    request.on("error", () => reject(fail(400, "Requête illisible.")));
  });
}

function waitForJournal(child) {
  return new Promise((resolve, reject) => {
    let output = "";
    let errors = "";
    let settled = false;
    const timer = setTimeout(() => {
      finish(() => reject(fail(500, "Le journal n’a pas été créé.")));
    }, JOURNAL_WAIT_MS);
    function drain() {}
    function finish(callback) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.stdout.off("data", onOutput);
      child.stderr.off("data", onError);
      child.off("exit", onExit);
      child.off("error", onFailure);
      child.stdout.on("data", drain);
      child.stderr.on("data", drain);
      callback();
    }
    function onOutput(chunk) {
      output += chunk.toString("utf8");
      if (output.length > 20000) output = output.slice(-20000);
      const match = output.match(/Journal : ([^\r\n]+)/);
      if (!match) return;
      finish(() => resolve(match[1].trim()));
    }
    function onError(chunk) {
      errors += chunk.toString("utf8");
      if (errors.length > 4000) errors = errors.slice(-4000);
    }
    function onExit(code) {
      const message = errors.trim() || output.trim() || `Extraction arrêtée (${code ?? 1}).`;
      finish(() => reject(fail(500, message.slice(0, 500))));
    }
    function onFailure() {
      finish(() => reject(fail(500, "Impossible de lancer l’extraction.")));
    }
    child.stdout.on("data", onOutput);
    child.stderr.on("data", onError);
    child.on("exit", onExit);
    child.on("error", onFailure);
  });
}

async function startExtract(raw) {
  if (run) throw fail(409, "Une extraction est déjà en cours.");
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    throw fail(400, "Requête illisible.");
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw fail(400, "Requête illisible.");
  }
  run = { child: null };
  let child;
  let root;
  try {
    root = extractorRoot();
    const pdf = resolvePdf(path.join(root, "partitions"), payload.pdf);
    const pages = await pageCount(pdf);
    validateRun(pages, payload.start, payload.end, payload.phase);
    const config = path.join(root, "config.toml");
    if (!fs.statSync(config).isFile()) throw fail(500, "config.toml est introuvable.");
    child = spawn(
      pythonCommand(root),
      ["-u", "-m", "libretto_printer", ...extractionArgs({
        pdf,
        config,
        start: payload.start,
        end: payload.end,
        phase: payload.phase,
      })],
      {
        cwd: root,
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    run.child = child;
  } catch (error) {
    run = null;
    throw error;
  }
  const current = run;
  child.on("exit", (code) => {
    if (run && run.child === child) {
      const stopped = Boolean(run.stopping);
      run = null;
      broadcast("status", { running: false, code: code ?? 1, stopped });
    }
  });
  if (current && current.stopping) child.kill("SIGTERM");
  let journalLine;
  try {
    journalLine = await waitForJournal(child);
  } catch (error) {
    const stopped = Boolean(current && current.stopping);
    if (!stopped) child.kill("SIGTERM");
    if (run && run.child === child) run = null;
    if (stopped) return { stopped: true };
    throw error;
  }
  let journal;
  try {
    journal = assertJournal(path.join(root, "out"), journalLine);
  } catch {
    child.kill("SIGTERM");
    run = null;
    throw fail(500, "Le journal indiqué est refusé.");
  }
  watchJournal(journal);
  broadcast("status", { running: true });
  return { journal: relativeToRoot(root, journal) };
}

function stopExtract() {
  if (!run) throw fail(409, "Aucune extraction en cours.");
  run.stopping = true;
  if (run.child) run.child.kill("SIGTERM");
  return { stopped: true };
}

async function buildState() {
  const root = extractorRoot();
  const pdfs = [];
  for (const relative of listPdfs(path.join(root, "partitions"))) {
    try {
      const full = resolvePdf(path.join(root, "partitions"), relative);
      pdfs.push({ path: relative, pages: await pageCount(full) });
    } catch {
      continue;
    }
  }
  return {
    pdfs,
    phases: PHASES,
    running: Boolean(run),
    journal: relativeToRoot(root, currentJournal),
  };
}

function sendJson(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'",
    "Referrer-Policy": "no-referrer",
  });
  response.end(body);
}

function sendFile(response, fileName, type) {
  const filePath = path.join(UI_DIR, fileName);
  const relative = path.relative(UI_DIR, filePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    sendJson(response, 404, { error: "Introuvable." });
    return;
  }
  let body;
  try {
    body = fs.readFileSync(filePath);
  } catch {
    sendJson(response, 404, { error: "Introuvable." });
    return;
  }
  response.writeHead(200, {
    "Content-Type": type,
    "Content-Length": body.length,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'",
    "Referrer-Policy": "no-referrer",
  });
  response.end(body);
}

function attachEvents(response) {
  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  });
  const client = { response, offset: 0, decoder: new TextDecoder("utf-8") };
  clients.add(client);
  sendEvent(response, "status", { running: Boolean(run) });
  sendEvent(response, "journal", { path: relativeToRoot(extractorRoot(), currentJournal) });
  pump();
  const heartbeat = setInterval(() => {
    try {
      response.write(":\n\n");
    } catch {
      clearInterval(heartbeat);
    }
  }, 15000);
  response.on("close", () => {
    clearInterval(heartbeat);
    clients.delete(client);
  });
}

function createServer() {
  return http.createServer((request, response) => {
    const url = new URL(request.url || "/", `http://${HOST}`);
    if (request.method === "GET" && url.pathname === "/api/state") {
      buildState().then(
        (state) => sendJson(response, 200, state),
        () => sendJson(response, 500, { error: "Impossible de lire les partitions." }),
      );
      return;
    }
    if (request.method === "GET" && url.pathname === "/api/events") {
      attachEvents(response);
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/stop") {
      try {
        sendJson(response, 200, stopExtract());
      } catch (error) {
        sendJson(response, error.status || 500, {
          error: error.status ? error.message : "L’arrêt a échoué.",
        });
      }
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/extract") {
      readBody(request).then(startExtract).then(
        (result) => sendJson(response, 200, result),
        (error) => sendJson(response, error.status || 500, {
          error: error.status ? error.message : "L’extraction n’a pas démarré.",
        }),
      );
      return;
    }
    if (request.method === "GET" && FILES.has(url.pathname)) {
      const [fileName, type] = FILES.get(url.pathname);
      sendFile(response, fileName, type);
      return;
    }
    sendJson(response, 404, { error: "Introuvable." });
  });
}

function main() {
  const root = extractorRoot();
  watchJournal(latestJournal(path.join(root, "out")));
  setInterval(pump, 200).unref();
  const server = createServer();
  server.on("error", (error) => {
    process.stderr.write(`${error.message}\n`);
    process.exit(1);
  });
  server.listen(PORT, HOST, () => {
    process.stdout.write(`Interface : http://${HOST}:${PORT}\n`);
  });
}

module.exports = {
  PHASES,
  assertJournal,
  extractionArgs,
  extractorRoot,
  resolvePdf,
  validateRun,
};

if (require.main === module) main();
