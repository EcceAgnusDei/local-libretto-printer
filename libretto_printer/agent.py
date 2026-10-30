from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from libretto_printer.parsing import extract_json_object
from libretto_printer.prompts import first_pass_prompt, second_pass_prompt
from libretto_printer.schemas import PAGE_NAME, PageDecision, RoleNote, normalize_decision
from libretto_printer.store import CommitResult, Store


class VisionAsk(Protocol):
    def ask(self, image: Path, prompt: str) -> str: ...


@dataclass
class PageReport:
    page: str
    status: str
    added: int = 0
    corrected: int = 0
    roles: tuple[str, ...] = ()


class Agent:
    def __init__(self, store: Store, qwen: VisionAsk, glm: VisionAsk, tail_verses: int) -> None:
        self.store = store
        self.qwen = qwen
        self.glm = glm
        self.tail_verses = tail_verses

    def run_page(self, image: Path) -> PageReport:
        page = image.stem
        if not PAGE_NAME.fullmatch(page):
            raise ValueError(f"Nom de page refusé : {page}")
        if image.suffix.lower() != ".png":
            raise ValueError(f"Image refusée : {image.name}")
        note = self.store.load_roles()
        if note is None:
            incoming_roles: list[str] = []
            incoming_number = ""
        elif note.page == page:
            incoming_roles = list(note.incoming_roles)
            incoming_number = note.incoming_number
        else:
            incoming_roles = list(note.roles)
            incoming_number = note.number_label
        earlier = [verse for verse in self.store.load_verses() if verse.page != page]
        tail = earlier[-self.tail_verses :] if self.tail_verses > 0 else []
        allowed = {verse.verse_id for verse in tail}
        first = self._decide(image, first_pass_prompt(incoming_roles, tail, incoming_number))
        if first is None:
            self.store.add_review(page, "invalid_response")
            return PageReport(page, "relecture")
        decision = first
        if first.needs_glm:
            glm_text = self.store.load_glm(page)
            if glm_text is None:
                glm_text = self.glm.ask(image, "OCR").strip()
                self.store.save_glm(page, glm_text)
            second = self._decide(
                image,
                second_pass_prompt(incoming_roles, tail, incoming_number, glm_text),
            )
            if second is None:
                self.store.add_review(page, "invalid_response")
                return PageReport(page, "relecture")
            if second.needs_glm:
                self.store.add_review(page, "glm_still_needed")
                return PageReport(page, "relecture")
            decision = second
        if not decision.verses and any(verse.page == page for verse in self.store.load_verses()):
            self.store.add_review(page, "empty_replacement")
            return PageReport(page, "relecture")
        started = RoleNote(
            page=page,
            number_label=incoming_number,
            roles=incoming_roles,
            incoming_roles=incoming_roles,
            incoming_number=incoming_number,
        )
        result = self.store.commit(page, decision, allowed, started)
        return _report(page, result)

    def _decide(self, image: Path, prompt: str) -> PageDecision | None:
        try:
            raw = self.qwen.ask(image, prompt)
            return normalize_decision(extract_json_object(raw))
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError):
            return None


def _report(page: str, result: CommitResult) -> PageReport:
    status = "incertain" if result.uncertain else "écrit"
    return PageReport(
        page=page,
        status=status,
        added=result.added,
        corrected=result.corrected,
        roles=tuple(result.roles),
    )
