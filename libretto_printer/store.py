from __future__ import annotations

import json
from pathlib import Path

from libretto_printer.schemas import (
    PAGE_NAME,
    Correction,
    PageDecision,
    RoleNote,
    Verse,
    clean_label,
)


class CommitResult:
    def __init__(self, added: int, corrected: int, roles: list[str], uncertain: bool) -> None:
        self.added = added
        self.corrected = corrected
        self.roles = roles
        self.uncertain = uncertain


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def page_heading(stem: str) -> str:
    if not PAGE_NAME.fullmatch(stem):
        raise ValueError(f"Nom de page refusé : {stem}")
    return str(int(stem.removeprefix("page_")))


class Store:
    def __init__(self, root: Path, title: str) -> None:
        self.root = root
        self.title = title
        self.verses_path = root / "livret.jsonl"
        self.roles_path = root / "roles.json"
        self.review_path = root / "relecture.jsonl"
        self.livret_path = root / "livret.md"
        self.ocr_dir = root / "ocr"

    def load_verses(self) -> list[Verse]:
        if not self.verses_path.exists():
            return []
        verses: list[Verse] = []
        for line in self.verses_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                verses.append(Verse.model_validate_json(line))
        return verses

    def load_roles(self) -> RoleNote | None:
        if not self.roles_path.exists():
            return None
        return RoleNote.model_validate_json(self.roles_path.read_text(encoding="utf-8"))

    def tail(self, count: int) -> list[Verse]:
        verses = self.load_verses()
        if count <= 0:
            return []
        return verses[-count:]

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

    def commit(
        self,
        page: str,
        decision: PageDecision,
        allowed_ids: set[str],
        previous: RoleNote | None,
    ) -> CommitResult:
        if not PAGE_NAME.fullmatch(page):
            raise ValueError(f"Nom de page refusé : {page}")
        if decision.needs_glm:
            raise ValueError("Une page qui demande encore GLM n'est pas écrite.")
        verses = self.load_verses()
        corrected = _apply_corrections(verses, decision.corrections, allowed_ids, page)
        kept = [verse for verse in verses if verse.page != page]
        label = decision.number_label or (previous.number_label if previous else "")
        label = clean_label(label) or "Sans titre"
        added = [
            Verse(
                verse_id=f"{page}-{index:03d}",
                page=page,
                number_label=label,
                role=draft.role,
                text=draft.text,
                used_glm=draft.used_glm,
            )
            for index, draft in enumerate(decision.verses, start=1)
        ]
        written = kept + added
        _write_verses(self.verses_path, written)
        roles = _resolve_roles(previous, decision, label)
        incoming_roles = list(previous.roles) if previous is not None else []
        incoming_number = previous.number_label if previous is not None else ""
        note = RoleNote(
            page=page,
            number_label=label,
            roles=roles,
            incoming_roles=incoming_roles,
            incoming_number=incoming_number,
        )
        atomic_write(self.roles_path, note.model_dump_json(indent=2) + "\n")
        atomic_write(self.livret_path, render_livret(self.title, written))
        if decision.uncertain:
            self.add_review(page, "uncertain")
        return CommitResult(
            added=len(added),
            corrected=corrected,
            roles=roles,
            uncertain=decision.uncertain,
        )

    def _ocr_path(self, page: str) -> Path:
        if not PAGE_NAME.fullmatch(page):
            raise ValueError(f"Nom de page refusé : {page}")
        return self.ocr_dir / f"{page}.txt"


def _apply_corrections(
    verses: list[Verse],
    corrections: list[Correction],
    allowed_ids: set[str],
    page: str,
) -> int:
    positions = {verse.verse_id: index for index, verse in enumerate(verses)}
    applied = 0
    for correction in corrections:
        index = positions.get(correction.verse_id)
        if index is None or correction.verse_id not in allowed_ids:
            continue
        current = verses[index]
        if current.page == page:
            continue
        verses[index] = current.model_copy(update={"role": correction.role, "text": correction.text})
        applied += 1
    return applied


def _resolve_roles(
    previous: RoleNote | None,
    decision: PageDecision,
    label: str,
) -> list[str]:
    if decision.last_system_roles:
        return list(decision.last_system_roles)
    if previous is not None and previous.number_label == label:
        return list(previous.roles)
    return []


def _write_verses(path: Path, verses: list[Verse]) -> None:
    lines = [verse.model_dump_json() for verse in verses]
    content = "\n".join(lines)
    if content:
        content += "\n"
    atomic_write(path, content)


def render_livret(title: str, verses: list[Verse]) -> str:
    lines = [f"# {title}", ""]
    number = None
    page = None
    for verse in verses:
        if verse.number_label != number:
            number = verse.number_label
            page = None
            lines.extend((f"## {number}", ""))
        if verse.page != page:
            page = verse.page
            lines.extend((f"### page {page_heading(page)}", ""))
        lines.extend((f"**{verse.role}.** {verse.text}", ""))
    return "\n".join(lines).rstrip() + "\n"
