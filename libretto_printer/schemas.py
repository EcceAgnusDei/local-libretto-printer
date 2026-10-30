from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

PAGE_NAME = re.compile(r"page_\d{4}")
VERSE_ID = re.compile(r"page_\d{4}-\d{3}")
ROLE_STRIP = re.compile(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿŒœ'’. \-]")
MAX_VERSES = 40
MAX_CORRECTIONS = 20
MAX_ROLES = 12
MAX_ROLE_LENGTH = 80
MAX_TEXT_LENGTH = 800
MAX_LABEL_LENGTH = 120


class VerseDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    text: str
    used_glm: bool = False


class Correction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verse_id: str
    role: str
    text: str


class PageDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    needs_glm: bool
    number_label: str = ""
    verses: list[VerseDraft] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)
    last_system_roles: list[str] = Field(default_factory=list)
    uncertain: bool = False


class Verse(BaseModel):
    verse_id: str
    page: str
    number_label: str
    role: str
    text: str
    used_glm: bool


class RoleNote(BaseModel):
    page: str
    number_label: str
    roles: list[str]
    incoming_roles: list[str] = Field(default_factory=list)
    incoming_number: str = ""


def clean_role(value: str) -> str:
    collapsed = " ".join(value.split())
    cleaned = ROLE_STRIP.sub("", collapsed).strip()
    return cleaned[:MAX_ROLE_LENGTH]


def clean_text(value: str) -> str:
    flattened = value.replace("\n", " ").replace("\r", " ")
    visible = "".join(character for character in flattened if character >= " ")
    return " ".join(visible.split())[:MAX_TEXT_LENGTH]


def clean_label(value: str) -> str:
    return " ".join(value.split())[:MAX_LABEL_LENGTH]


def normalize_decision(data: object) -> PageDecision:
    if not isinstance(data, dict):
        raise ValueError("La réponse n'est pas un objet JSON.")
    decision = PageDecision.model_validate(data)
    verses: list[VerseDraft] = []
    for draft in decision.verses:
        role = clean_role(draft.role)
        text = clean_text(draft.text)
        if not role or not text:
            continue
        verses.append(VerseDraft(role=role, text=text, used_glm=draft.used_glm))
    corrections: list[Correction] = []
    for item in decision.corrections:
        if not VERSE_ID.fullmatch(item.verse_id):
            continue
        role = clean_role(item.role)
        text = clean_text(item.text)
        if not role or not text:
            continue
        corrections.append(Correction(verse_id=item.verse_id, role=role, text=text))
    roles = [role for role in (clean_role(role) for role in decision.last_system_roles) if role]
    uncertain = decision.uncertain or len(verses) > MAX_VERSES or len(corrections) > MAX_CORRECTIONS
    return PageDecision(
        needs_glm=decision.needs_glm,
        number_label=clean_label(decision.number_label),
        verses=verses[:MAX_VERSES],
        corrections=corrections[:MAX_CORRECTIONS],
        last_system_roles=roles[:MAX_ROLES],
        uncertain=uncertain,
    )
