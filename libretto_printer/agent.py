from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import ValidationError

from libretto_printer.journal import Journal
from libretto_printer.livret import apply_operations, excerpt, format_excerpt
from libretto_printer.parsing import extract_json_object
from libretto_printer.prompts import (
    COUNT_SCHEMA,
    EDIT_SCHEMA,
    READING_SCHEMA,
    cast_prompt,
    cast_schema,
    count_prompt,
    edit_prompt,
    format_cast,
    format_previous,
    format_reading,
    reading_prompt,
)
from libretto_printer.schemas import (
    PAGE_NAME,
    CastResult,
    EditResult,
    ReadingResult,
    RoleNote,
    align_reading,
    match_count,
    normalize_cast,
    normalize_count,
    normalize_edit,
    normalize_reading,
    present_names,
)
from libretto_printer.store import Store


class VisionAsk(Protocol):
    def ask(
        self,
        image: Path,
        prompt: str,
        schema: dict[str, object] | None = None,
    ) -> str: ...


class TextAsk(Protocol):
    def ask(
        self,
        image: Path,
        prompt: str,
        schema: dict[str, object] | None = None,
    ) -> str: ...

    def ask_text(self, prompt: str, schema: dict[str, object] | None = None) -> str: ...


Parsed = TypeVar("Parsed")


@dataclass
class PageReport:
    page: str
    status: str
    added: int = 0
    roles: tuple[str, ...] = ()


class Agent:
    def __init__(
        self,
        store: Store,
        qwen: TextAsk,
        glm: VisionAsk,
        journal: Journal | None = None,
    ) -> None:
        self.store = store
        self.qwen = qwen
        self.glm = glm
        self.journal = journal

    def run_page(self, image: Path, phase: int = 3) -> PageReport:
        page = image.stem
        if not PAGE_NAME.fullmatch(page):
            raise ValueError(f"Nom de page refusé : {page}")
        if image.suffix.lower() != ".png":
            raise ValueError(f"Image refusée : {image.name}")
        incoming = _incoming(self.store.load_roles(), page)
        glm_text = self._glm(page, image)
        if glm_text is None:
            return self._review(page, "invalid_response")
        counts = self._ask(
            page,
            "passage comptes",
            lambda: self.qwen.ask(image, count_prompt(incoming), COUNT_SCHEMA),
            normalize_count,
        )
        if not isinstance(counts, list):
            return self._review(page, "invalid_response")
        cast = self._ask(
            page,
            "passage personnages",
            lambda: self.qwen.ask(
                image,
                cast_prompt(format_previous(incoming), glm_text, counts),
                cast_schema(counts),
            ),
            normalize_cast,
        )
        if not isinstance(cast, CastResult):
            return self._review(page, "invalid_response")
        try:
            match_count(cast, counts)
        except ValueError:
            return self._review(page, "invalid_response")
        if phase < 2:
            report = self._roles(page, cast, incoming)
            roles = ", ".join(report.roles) if report.roles else "aucun"
            self._event(f"{page} : personnages, rôles {roles}")
            return report
        reading = self._ask(
            page,
            "passage paroles",
            lambda: self.qwen.ask(
                image,
                reading_prompt(format_cast(cast), glm_text),
                READING_SCHEMA,
            ),
            normalize_reading,
        )
        if not isinstance(reading, ReadingResult):
            return self._review(page, "invalid_response")
        try:
            reading = align_reading(cast, reading)
        except ValueError:
            return self._review(page, "invalid_response")
        if phase < 3:
            report = self._roles(page, cast, incoming)
            roles = ", ".join(report.roles) if report.roles else "aucun"
            self._event(f"{page} : paroles, rôles {roles}")
            return PageReport(page, "paroles", 0, report.roles)
        original = self.store.load_lines()
        base = [line for line in original if line.page != page]
        shown = excerpt(base, present_names(cast))
        allowed = {number for number, _line in shown}
        edit = self._ask(
            page,
            "passage livret",
            lambda: self.qwen.ask_text(
                edit_prompt(format_cast(cast), format_reading(reading), format_excerpt(shown)),
                EDIT_SCHEMA,
            ),
            normalize_edit,
        )
        if not isinstance(edit, EditResult):
            return self._review(page, "invalid_response")
        owned = sum(1 for line in original if line.page == page)
        if not edit.operations and owned:
            return self._review(page, "empty_replacement")
        try:
            written = apply_operations(base, edit, allowed, page)
        except ValueError:
            return self._review(page, "invalid_response")
        self.store.save_lines(written)
        report = self._roles(page, cast, incoming)
        added = sum(1 for op in edit.operations if op.action == "inserer")
        roles = ", ".join(report.roles) if report.roles else "aucun"
        self._event(f"{page} : écrit, {added} vers, rôles {roles}")
        return PageReport(page, "écrit", added, report.roles)

    def _roles(self, page: str, cast: CastResult, incoming: list[str | None]) -> PageReport:
        ending = list(cast.systemes[-1])
        note = RoleNote(page=page, last_system=ending, incoming_last_system=list(incoming))
        self.store.save_roles(note)
        return PageReport(page, "personnages", 0, tuple(note.roles))

    def _glm(self, page: str, image: Path) -> str | None:
        stored = self.store.load_glm(page)
        if stored is not None:
            self._event(f"{page} : OCR GLM relu depuis le fichier")
            return stored
        self._event(f"{page} : OCR GLM")
        try:
            text = self.glm.ask(image, "OCR").strip()
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            reason = " ".join(str(error).split())[:200]
            if reason:
                self._event(f"{page} : OCR GLM refusé, {reason}")
            else:
                self._event(f"{page} : OCR GLM refusé")
            return None
        self.store.save_glm(page, text)
        self._event(f"{page} : OCR GLM reçu, {len(text)} caractères")
        return text

    def _ask(
        self,
        page: str,
        label: str,
        call: Callable[[], str],
        normalize: Callable[[object], Parsed],
    ) -> Parsed | None:
        self._event(f"{page} : {label}")
        try:
            parsed = normalize(extract_json_object(call()))
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError, TimeoutError):
            self._event(f"{page} : {label} refusé")
            return None
        self._event(f"{page} : {label} reçu")
        return parsed

    def _review(self, page: str, reason: str) -> PageReport:
        self._event(f"{page} : relecture, {reason}")
        self.store.add_review(page, reason)
        return PageReport(page, "relecture")

    def _event(self, message: str) -> None:
        if self.journal is not None:
            self.journal.event(message)


def _incoming(note: RoleNote | None, page: str) -> list[str | None]:
    if note is None:
        return []
    if note.page == page:
        return list(note.incoming_last_system)
    return list(note.last_system)
