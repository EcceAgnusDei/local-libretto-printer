from __future__ import annotations

import argparse
import sys
from pathlib import Path

from libretto_printer.agent import Agent
from libretto_printer.config import load_settings, missing_files
from libretto_printer.runtime import GlmReader, ModelSession, QwenReader
from libretto_printer.schemas import PAGE_NAME
from libretto_printer.store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extrait un livret depuis des pages de partition.")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh-ocr", action="store_true")
    args = parser.parse_args(argv)
    if args.start and not PAGE_NAME.fullmatch(args.start):
        parser.error("--start attend un nom page_0000")
    if args.end and not PAGE_NAME.fullmatch(args.end):
        parser.error("--end attend un nom page_0000")
    settings = load_settings(args.config)
    absent = missing_files(settings)
    if absent:
        for path in absent:
            print(f"Fichier manquant : {path}", file=sys.stderr)
        return 1
    pages = _select_pages(settings.pages_dir, args.start, args.end, args.limit)
    if not pages:
        print("Aucune page à lire.", file=sys.stderr)
        return 1
    store = Store(settings.out_dir, settings.title)
    if args.refresh_ocr:
        for page in pages:
            ocr = store.ocr_dir / f"{page.stem}.txt"
            if ocr.exists():
                ocr.unlink()
    session = ModelSession(settings)
    agent = Agent(store, QwenReader(session), GlmReader(session), settings.tail_verses)
    failed = 0
    try:
        for image in pages:
            report = agent.run_page(_inside(settings.pages_dir, image))
            roles = ", ".join(report.roles) if report.roles else "aucun"
            if report.status == "relecture":
                failed += 1
                print(f"{report.page} : relecture")
            else:
                print(
                    f"{report.page} : {report.status}, "
                    f"{report.added} vers, {report.corrected} correction(s), rôles {roles}"
                )
    finally:
        session.close()
    return 1 if failed else 0


def _inside(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise ValueError(f"Image hors du dossier des pages : {path.name}")
    return resolved


def _select_pages(directory: Path, start: str, end: str, limit: int) -> list[Path]:
    pages = sorted(
        path
        for path in directory.glob("page_*.png")
        if PAGE_NAME.fullmatch(path.stem) and path.is_file()
    )
    if start:
        pages = [path for path in pages if path.stem >= start]
    if end:
        pages = [path for path in pages if path.stem <= end]
    if limit > 0:
        pages = pages[:limit]
    return pages


if __name__ == "__main__":
    raise SystemExit(main())
