const form = document.querySelector("#extract");
const pdfSelect = document.querySelector("#pdf");
const startInput = document.querySelector("#start");
const endInput = document.querySelector("#end");
const pageCountText = document.querySelector("#page-count");
const phasesElement = document.querySelector("#phases");
const launchButton = document.querySelector("#launch");
const stopButton = document.querySelector("#stop");
const statusElement = document.querySelector("#status");
const errorElement = document.querySelector("#error");
const journalPath = document.querySelector("#journal-path");
const logElement = document.querySelector("#log");

let pageCount = 1;
let pendingLine = "";

function nearBottom() {
  return logElement.scrollHeight - logElement.scrollTop - logElement.clientHeight < 48;
}

function lineClass(line) {
  if (line.startsWith("[harnais]")) return "harness";
  if (line.startsWith("[modèle:")) return "marker";
  return "";
}

function appendLine(line) {
  const row = document.createElement("div");
  const kind = lineClass(line);
  row.className = kind ? `log-line ${kind}` : "log-line";
  row.textContent = line;
  logElement.append(row);
}

function appendText(text) {
  const stick = nearBottom();
  pendingLine += text;
  const lines = pendingLine.split("\n");
  pendingLine = lines.pop() ?? "";
  for (const line of lines) appendLine(line);
  if (stick) logElement.scrollTop = logElement.scrollHeight;
}

function clearLog() {
  pendingLine = "";
  logElement.replaceChildren();
}

function setRunning(running) {
  launchButton.disabled = running;
  stopButton.disabled = !running;
  for (const element of form.querySelectorAll("input, select")) {
    element.disabled = running;
  }
  if (running) statusElement.textContent = "Extraction en cours.";
}

function selectedPages() {
  return Number(pdfSelect.selectedOptions[0]?.dataset.pages || 0);
}

function showPdf() {
  const pages = selectedPages();
  pageCount = pages;
  startInput.max = String(pages);
  endInput.max = String(pages);
  startInput.value = "1";
  endInput.value = "1";
  pageCountText.textContent = pages
    ? `Intervalle continu. Ce PDF compte ${pages} pages.`
    : "";
}

function renderPhases(phases) {
  phasesElement.replaceChildren();
  for (const phase of phases) {
    const label = document.createElement("label");
    label.className = "phase";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "phase";
    input.value = String(phase.value);
    input.checked = phase.value === 1;
    const body = document.createElement("span");
    const title = document.createElement("span");
    title.className = "phase-title";
    title.textContent = phase.title;
    const detail = document.createElement("span");
    detail.className = "phase-detail";
    detail.textContent = phase.detail;
    const list = document.createElement("ol");
    for (const [name, action] of phase.actions) {
      const item = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = name;
      item.append(strong, ` — ${action}`);
      list.append(item);
    }
    body.append(title, detail, list);
    label.append(input, body);
    phasesElement.append(label);
  }
}

function renderPdfs(pdfs) {
  pdfSelect.replaceChildren();
  let preferred = 0;
  pdfs.forEach((pdf, index) => {
    const option = document.createElement("option");
    option.value = pdf.path;
    option.dataset.pages = String(pdf.pages);
    option.textContent = `${pdf.path} (${pdf.pages} pages)`;
    if (pdf.path.includes("Zaïs_1748")) preferred = index;
    pdfSelect.append(option);
  });
  pdfSelect.selectedIndex = preferred;
  showPdf();
}

pdfSelect.addEventListener("change", () => {
  showPdf();
});

stopButton.addEventListener("click", async () => {
  errorElement.textContent = "";
  stopButton.disabled = true;
  statusElement.textContent = "Arrêt en cours.";
  try {
    const response = await fetch("/api/stop", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      errorElement.textContent = payload.error || "L’arrêt a échoué.";
      stopButton.disabled = !launchButton.disabled;
      return;
    }
    statusElement.textContent = "Extraction arrêtée.";
  } catch {
    errorElement.textContent = "L’interface n’a pas pu joindre le serveur.";
    stopButton.disabled = false;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorElement.textContent = "";
  const start = Number(startInput.value);
  const end = Number(endInput.value);
  const phase = Number(form.elements.phase.value);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end > pageCount) {
    errorElement.textContent = "L’intervalle de pages est hors du PDF.";
    return;
  }
  if (phase !== 1 && phase !== 2 && phase !== 3) {
    errorElement.textContent = "La phase vaut 1, 2 ou 3.";
    return;
  }
  setRunning(true);
  try {
    const response = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf: pdfSelect.value, start, end, phase }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setRunning(false);
      statusElement.textContent = "";
      errorElement.textContent = payload.error || "L’extraction n’a pas démarré.";
      return;
    }
    if (payload.stopped) {
      setRunning(false);
      statusElement.textContent = "Extraction arrêtée.";
      return;
    }
    statusElement.textContent = "Extraction en cours. Le journal de cette session s’affiche en dessous.";
  } catch {
    setRunning(false);
    statusElement.textContent = "";
    errorElement.textContent = "L’interface n’a pas pu joindre le serveur.";
  }
});

async function loadState() {
  const response = await fetch("/api/state");
  if (!response.ok) throw new Error("state");
  const payload = await response.json();
  renderPdfs(payload.pdfs);
  renderPhases(payload.phases);
  setRunning(payload.running);
  if (payload.journal) journalPath.textContent = payload.journal;
}

const events = new EventSource("/api/events");

events.addEventListener("open", () => {
  clearLog();
});

events.addEventListener("reset", () => {
  clearLog();
});

events.addEventListener("journal", (event) => {
  const payload = JSON.parse(event.data);
  journalPath.textContent = payload.path || "Aucun journal pour l’instant.";
});

events.addEventListener("chunk", (event) => {
  const payload = JSON.parse(event.data);
  if (typeof payload.text === "string") appendText(payload.text);
});

events.addEventListener("status", (event) => {
  const payload = JSON.parse(event.data);
  setRunning(Boolean(payload.running));
  if (payload.running) return;
  if (payload.stopped) {
    statusElement.textContent = "Extraction arrêtée.";
    return;
  }
  if (payload.code === 0) statusElement.textContent = "Extraction terminée.";
  else if (typeof payload.code === "number") {
    statusElement.textContent = `Extraction arrêtée (code ${payload.code}). Le détail est dans le journal.`;
  }
});

events.addEventListener("error", () => {
  if (events.readyState === EventSource.CONNECTING) {
    errorElement.textContent = "Connexion au journal interrompue. Nouvelle tentative.";
  }
});

loadState().catch(() => {
  errorElement.textContent = "Impossible de charger les partitions.";
  launchButton.disabled = true;
});
