from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from libretto_printer.livret import render_livret
from libretto_printer.schemas import PAGE_NAME, LivretLine, RoleNote


class CommitResult:
    def __init__(self, added: int, roles: list[str]) -> None:
        self.added = added
        self.roles = roles


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class Store:
    def __init__(self, root: Path, title: str, pdf_name: str = "") -> None:
        self.root = root
        self.title = title
        self.pdf_name = pdf_name
        self.livret_lines_path = root / "livret.jsonl"
        self.roles_path = root / "roles.json"
        self.review_path = root / "relecture.jsonl"
        self.livret_path = root / "livret.md"
        self.ocr_dir = root / "ocr"

    def load_lines(self) -> list[LivretLine]:
        if not self.livret_lines_path.exists():
            return []
        lines: list[LivretLine] = []
        for line in self.livret_lines_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                lines.append(LivretLine.model_validate_json(line))
            except ValidationError as error:
                raise ValueError(
                    "livret.jsonl vient d'une extraction précédente. "
                    "Relancez dans une nouvelle session."
                ) from error
        return lines

    def save_lines(self, lines: list[LivretLine]) -> None:
        payload = [line.model_dump_json() for line in lines]
        content = "\n".join(payload)
        if content:
            content += "\n"
        atomic_write(self.livret_lines_path, content)
        atomic_write(self.livret_path, render_livret(self.title, lines, self.pdf_name))

    def load_roles(self) -> RoleNote | None:
        if not self.roles_path.exists():
            return None
        try:
            return RoleNote.model_validate_json(self.roles_path.read_text(encoding="utf-8"))
        except ValidationError as error:
            raise ValueError(
                "roles.json vient d'une extraction précédente. "
                "Relancez dans une nouvelle session."
            ) from error

    def save_roles(self, note: RoleNote) -> None:
        if not PAGE_NAME.fullmatch(note.page):
            raise ValueError(f"Nom de page refusé : {note.page}")
        atomic_write(self.roles_path, note.model_dump_json(indent=2) + "\n")

    def load_glm(self, page: str) -> str | None:
        path = self._ocr_path(page)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def save_glm(self, page: str, text: str) -> None:
        atomic_write(self._ocr_path(page), text)

    def add_review(self, page: str, reason: str) -> None:
        if not PAGE_NAME.fullmatch(page):
            raise ValueError(f"Nom de page refusé : {page}")
        self.review_path.parent.mkdir(parents=True, exist_ok=True)
        record = json.dumps({"page": page, "reason": reason}, ensure_ascii=False)
        with self.review_path.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")

    def _ocr_path(self, page: str) -> Path:
        if not PAGE_NAME.fullmatch(page):
            raise ValueError(f"Nom de page refusé : {page}")
        return self.ocr_dir / f"{page}.txt"
