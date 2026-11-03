from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from libretto_printer.store import atomic_write

_STRIP = re.compile(r"[\x00-\x1f\\/:*?\"<>|]+")


@dataclass(frozen=True)
class ExtractionSession:
    uuid: str
    root: Path
    pdf_name: str
    title: str
    dpi: int

    @property
    def pages_dir(self) -> Path:
        return self.root / "pages"


def safe_pdf_stem(stem: str) -> str:
    cleaned = _STRIP.sub("_", stem).strip(" ._")
    return cleaned[:80] or "document"


def create_session(out_root: Path, pdf: Path, title: str, dpi: int) -> ExtractionSession:
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
        raise ValueError(f"PDF refusé : {pdf.name}")
    session_id = str(uuid.uuid4())
    folder = out_root / f"{session_id}_{safe_pdf_stem(pdf.stem)}"
    resolved_root = out_root.resolve()
    resolved_folder = folder.resolve()
    if resolved_folder.parent != resolved_root:
        raise ValueError("La session sortirait du dossier out.")
    resolved_folder.mkdir(parents=True, exist_ok=False)
    session = ExtractionSession(
        uuid=session_id,
        root=resolved_folder,
        pdf_name=pdf.name,
        title=title,
        dpi=dpi,
    )
    payload = {
        "uuid": session.uuid,
        "pdf_name": session.pdf_name,
        "dpi": session.dpi,
        "title": session.title,
    }
    atomic_write(
        session.root / "session.json",
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    return session
