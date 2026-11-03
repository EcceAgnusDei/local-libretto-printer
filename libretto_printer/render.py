from __future__ import annotations

import subprocess
from pathlib import Path

DPI = 150


def render_pdf(pdf: Path, pages_dir: Path, first: int, last: int | None) -> list[Path]:
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
        raise ValueError(f"PDF refusé : {pdf.name}")
    if first < 1:
        raise ValueError("La première page commence à 1.")
    if last is not None and last < first:
        raise ValueError("La dernière page est avant la première.")
    pages_dir.mkdir(parents=True, exist_ok=True)
    prefix = pages_dir / "sheet"
    command = ["pdftoppm", "-png", "-r", str(DPI), "-f", str(first)]
    if last is not None:
        command.extend(["-l", str(last)])
    command.extend([str(pdf.resolve()), str(prefix)])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-500:]
        raise RuntimeError(f"Le rendu PDF a échoué : {detail}")
    rendered = sorted(pages_dir.glob("sheet-*.png"), key=_sheet_number)
    if not rendered:
        raise RuntimeError("Le PDF n'a produit aucune page.")
    pages: list[Path] = []
    for source in rendered:
        number = _sheet_number(source)
        target = pages_dir / f"page_{number:04d}.png"
        if target.parent.resolve() != pages_dir.resolve():
            raise ValueError(f"Page rendue hors du dossier de session : {source.name}")
        source.replace(target)
        pages.append(target)
    return pages


def _sheet_number(path: Path) -> int:
    return int(path.stem.rsplit("-", 1)[-1])
