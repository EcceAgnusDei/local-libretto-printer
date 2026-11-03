from __future__ import annotations

import argparse
import signal
import sys
from dataclasses import replace
from pathlib import Path

from libretto_printer.agent import Agent
from libretto_printer.config import load_settings, missing_files
from libretto_printer.journal import Journal
from libretto_printer.render import DPI, render_pdf
from libretto_printer.runtime import GlmReader, ModelSession, QwenReader
from libretto_printer.session import create_session
from libretto_printer.store import Store


def _on_term(signum: int, _frame: object) -> None:
    raise SystemExit(128 + signum)


def _line_buffered(stream: object) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(line_buffering=True)
    except (OSError, ValueError):
        return


def main(argv: list[str] | None = None) -> int:
    _line_buffered(sys.stdout)
    _line_buffered(sys.stderr)
    signal.signal(signal.SIGTERM, _on_term)
    parser = argparse.ArgumentParser(description="Extrait un livret depuis un PDF de partition.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--phase", type=int, default=3)
    parser.add_argument("--refresh-ocr", action="store_true")
    args = parser.parse_args(argv)
    if args.start < 1:
        parser.error("--start commence à 1")
    if args.end and args.end < args.start:
        parser.error("--end est avant --start")
    if args.limit < 0:
        parser.error("--limit est négatif")
    if args.phase not in (1, 2, 3):
        parser.error("--phase vaut 1, 2 ou 3")
    pdf = args.pdf.expanduser().resolve()
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
        print(f"PDF introuvable : {args.pdf}", file=sys.stderr)
        return 1
    settings = load_settings(args.config)
    absent = missing_files(settings)
    if absent:
        for path in absent:
            print(f"Fichier manquant : {path}", file=sys.stderr)
        return 1
    last = _last_page(args.start, args.end, args.limit)
    session_info = create_session(settings.out_dir, pdf, settings.title, DPI)
    print(f"Session {session_info.uuid} : {session_info.pdf_name}")
    print(session_info.root)
    journal = Journal(session_info.root)
    print(f"Journal : {journal.path}")
    print(f"Serveur : {session_info.root / 'logs'}")
    journal.event(f"session {session_info.uuid}")
    models: ModelSession | None = None
    failed = 0
    try:
        try:
            pages = render_pdf(pdf, session_info.pages_dir, args.start, last)
        except (OSError, RuntimeError, ValueError) as error:
            print(str(error), file=sys.stderr)
            journal.event(f"rendu PDF refusé : {error}")
            return 1
        store = Store(session_info.root, session_info.title, session_info.pdf_name)
        if args.refresh_ocr:
            for image in pages:
                ocr = store.ocr_dir / f"{image.stem}.txt"
                if ocr.exists():
                    ocr.unlink()
        run_settings = replace(settings, out_dir=session_info.root)
        models = ModelSession(run_settings, journal)
        agent = Agent(store, QwenReader(models), GlmReader(models), journal)
        journal.event(f"{len(pages)} page(s) à lire")
        for image in pages:
            report = agent.run_page(_inside(session_info.pages_dir, image), args.phase)
            roles = ", ".join(report.roles) if report.roles else "aucun"
            if report.status == "relecture":
                failed += 1
                print(f"{report.page} : relecture")
            elif report.status == "personnages":
                print(f"{report.page} : personnages, rôles {roles}")
            elif report.status == "paroles":
                print(f"{report.page} : paroles, rôles {roles}")
            else:
                print(
                    f"{report.page} : {report.status}, "
                    f"{report.added} vers, rôles {roles}"
                )
    finally:
        if models is not None:
            models.close()
        journal.close()
    return 1 if failed else 0


def _last_page(start: int, end: int, limit: int) -> int | None:
    last = end if end else None
    if limit:
        bounded = start + limit - 1
        last = bounded if last is None else min(last, bounded)
    return last


def _inside(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise ValueError(f"Image hors du dossier des pages : {path.name}")
    return resolved


if __name__ == "__main__":
    raise SystemExit(main())
