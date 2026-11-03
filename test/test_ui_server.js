const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const ui = require("../ui/server.js");

test("les phases 1, 2 et 3 sont proposées", () => {
  assert.deepEqual(ui.PHASES.map((phase) => phase.value), [1, 2, 3]);
  assert.equal(ui.PHASES[0].actions.some(([name]) => name === "Paroles"), false);
  assert.equal(ui.PHASES[1].actions.some(([name]) => name === "Paroles"), true);
  assert.equal(ui.PHASES[1].actions.some(([name]) => name === "Livret"), false);
  assert.equal(ui.PHASES[2].actions.some(([name]) => name === "Livret"), true);
});

test("l'intervalle de pages et la phase sont contrôlés", () => {
  assert.doesNotThrow(() => ui.validateRun(10, 1, 10, 1));
  assert.doesNotThrow(() => ui.validateRun(10, 2, 4, 2));
  assert.doesNotThrow(() => ui.validateRun(10, 2, 4, 3));
  assert.throws(() => ui.validateRun(10, 1, 2, 4), /phase/);
  assert.throws(() => ui.validateRun(10, 2, 1, 1), /intervalle/);
  assert.throws(() => ui.validateRun(10, 0, 1, 1), /intervalle/);
  assert.throws(() => ui.validateRun(10, 1, 11, 3), /intervalle/);
  assert.throws(() => ui.validateRun(10, 1.5, 2, 1), /entiers/);
});

test("un PDF doit rester dans partitions", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "livret-ui-"));
  const partitions = path.join(root, "partitions");
  fs.mkdirSync(path.join(partitions, "Zais"), { recursive: true });
  const pdf = path.join(partitions, "Zais", "a.pdf");
  fs.writeFileSync(pdf, "%PDF");
  assert.equal(ui.resolvePdf(partitions, "Zais/a.pdf"), pdf);
  assert.throws(() => ui.resolvePdf(partitions, "../secret.pdf"), /PDF/);
  assert.throws(() => ui.resolvePdf(partitions, "/etc/passwd"), /PDF/);
  fs.symlinkSync(pdf, path.join(partitions, "lien.pdf"));
  assert.throws(() => ui.resolvePdf(partitions, "lien.pdf"), /PDF/);
});

test("le journal doit être le fichier direct d'une session", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "livret-journal-"));
  const out = path.join(root, "out");
  const session = path.join(out, "session");
  fs.mkdirSync(session, { recursive: true });
  const journal = path.join(session, "journal.log");
  fs.writeFileSync(journal, "ligne\n");
  assert.equal(ui.assertJournal(out, journal), journal);
  const nested = path.join(session, "logs");
  fs.mkdirSync(nested);
  const nestedJournal = path.join(nested, "journal.log");
  fs.writeFileSync(nestedJournal, "non\n");
  assert.throws(() => ui.assertJournal(out, nestedJournal), /Journal/);
  const note = path.join(session, "notes.txt");
  fs.writeFileSync(note, "non\n");
  assert.throws(() => ui.assertJournal(out, note), /Journal/);
  const outside = path.join(root, "journal.log");
  fs.writeFileSync(outside, "non\n");
  const spoof = path.join(out, "spoof");
  fs.mkdirSync(spoof);
  fs.symlinkSync(outside, path.join(spoof, "journal.log"));
  assert.throws(() => ui.assertJournal(out, path.join(spoof, "journal.log")), /Journal/);
});

test("la commande d'extraction est une liste d'arguments", () => {
  assert.deepEqual(
    ui.extractionArgs({
      pdf: "/tmp/a.pdf",
      config: "/tmp/config.toml",
      start: 2,
      end: 5,
      phase: 1,
    }),
    ["/tmp/a.pdf", "--config", "/tmp/config.toml", "--start", "2", "--end", "5", "--phase", "1"],
  );
});
