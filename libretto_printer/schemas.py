from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PAGE_NAME = re.compile(r"page_\d{4}")
ROLE_STRIP = re.compile(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿŒœ'’. \-]")
MAX_SYSTEMS = 12
MAX_STAVES = 16
MAX_ITEMS = 48
MAX_OPS = 48
MAX_TEXT = 800
MAX_LYRIC = 2000
_BLANK = {"", "null", "none", "(aucun)", "(sans nom)", "n/a"}
HEADINGS = {"acte", "scene"}
INSERT_KINDS = {"acte", "scene", "didascalie", "vers"}
_HEADING_KIND: dict[str, Literal["acte", "scene", "didascalie"]] = {
    "a": "acte",
    "s": "scene",
    "i": "didascalie",
}


class CastResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    systemes: list[list[str | None]] = Field(default_factory=list)


class ReadingItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["acte", "scene", "didascalie", "dialogue"]
    text: str | None = None
    personnage: str | None = None
    portee: int | None = None


class ReadingResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[ReadingItem] = Field(default_factory=list)


class LivretOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["inserer", "remplacer", "retirer"]
    ligne: int | None = None
    apres: int | None = None
    type: Literal["acte", "scene", "didascalie", "vers"] | None = None
    personnage: str | None = None
    texte: str | None = None


class EditResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    operations: list[LivretOp] = Field(default_factory=list)


class LivretLine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["acte", "scene", "didascalie", "vers"]
    text: str
    personnage: str | None = None
    page: str = ""


class RoleNote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page: str
    last_system: list[str | None] = Field(default_factory=list)
    incoming_last_system: list[str | None] = Field(default_factory=list)

    @property
    def roles(self) -> list[str]:
        return [name for name in self.last_system if name]


def clean_role(value: str) -> str:
    collapsed = " ".join(value.split())
    return ROLE_STRIP.sub("", collapsed).strip()[:80]


def clean_line(value: str) -> str:
    kept = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    visible = "".join(character for character in kept if character >= " ")
    return " ".join(visible.split())[:MAX_TEXT]


def clean_paroles(value: str) -> str:
    kept = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in kept.split("\n"):
        visible = "".join(character for character in line if character >= " ")
        collapsed = " ".join(visible.split())
        if collapsed and collapsed.lower() not in _BLANK:
            lines.append(collapsed)
    return "\n".join(lines)[:MAX_LYRIC]


def _name(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    cleaned = clean_role(value)
    if not cleaned or cleaned.lower() in _BLANK:
        return None
    return cleaned


def normalize_count(data: object) -> list[int]:
    values = _rows(data, "n", MAX_SYSTEMS + 1)
    if not values:
        raise ValueError("Aucun système.")
    numbers = [_whole(value) for value in values]
    systems = numbers[0]
    staves = numbers[1:]
    if not 1 <= systems <= MAX_SYSTEMS or len(staves) != systems:
        raise ValueError("Compte hors limites.")
    if any(not 1 <= number <= MAX_STAVES for number in staves):
        raise ValueError("Compte hors limites.")
    return staves


def match_count(cast: CastResult, counts: list[int]) -> None:
    if len(cast.systemes) != len(counts):
        raise ValueError("Le nombre de systèmes ne correspond pas.")
    for row, count in zip(cast.systemes, counts, strict=True):
        if len(row) != count:
            raise ValueError("Le nombre de portées ne correspond pas.")
        if not any(row):
            raise ValueError("Système vide.")


def normalize_cast(data: object) -> CastResult:
    systems: list[list[str | None]] = []
    for row in _rows(data, "p", MAX_SYSTEMS):
        if not isinstance(row, list) or not row or len(row) > MAX_STAVES:
            raise ValueError("Système illisible.")
        names = [_name(_cell(staff)) for staff in row]
        if not any(names):
            raise ValueError("Système vide.")
        systems.append(names)
    if not systems:
        raise ValueError("Aucun système.")
    return CastResult(systemes=systems)


def normalize_reading(data: object) -> ReadingResult:
    items: list[ReadingItem] = []
    for row in _rows(data, "r", MAX_ITEMS):
        if not isinstance(row, list) or not row or not isinstance(row[0], str):
            raise ValueError("Ligne illisible.")
        if row[0] == "d":
            items.append(_dialogue(row))
            continue
        kind = _HEADING_KIND.get(row[0])
        if kind is None or len(row) != 2 or not isinstance(row[1], str):
            raise ValueError("Titre illisible.")
        text = clean_line(row[1])
        if text:
            items.append(ReadingItem(type=kind, text=text))
    if not items:
        raise ValueError("Relevé vide.")
    return ReadingResult(items=items)


def normalize_edit(data: object) -> EditResult:
    operations: list[LivretOp] = []
    for row in _rows(data, "o", MAX_OPS):
        if not isinstance(row, list) or not row or not isinstance(row[0], str):
            raise ValueError("Opération illisible.")
        if row[0] == "+":
            operations.append(_insert_row(row))
        elif row[0] == "=":
            operations.append(_replace_row(row))
        elif row[0] == "-":
            operations.append(_delete_row(row))
        else:
            raise ValueError("Opération illisible.")
    return EditResult(operations=operations)


def align_reading(cast: CastResult, reading: ReadingResult) -> ReadingResult:
    names = [name for row in cast.systemes for name in row]
    items: list[ReadingItem] = []
    for item in reading.items:
        if item.type != "dialogue":
            items.append(item)
            continue
        if item.portee is None or not 1 <= item.portee <= len(names):
            raise ValueError("Portée hors page.")
        role = names[item.portee - 1]
        if not role:
            raise ValueError("Dialogue sans personnage.")
        items.append(item.model_copy(update={"personnage": role}))
    return ReadingResult(items=items)


def present_names(cast: CastResult) -> set[str]:
    found: set[str] = set()
    for row in cast.systemes:
        for name in row:
            if name:
                found.add(name.casefold())
    return found


def _rows(data: object, key: str, limit: int) -> list[object]:
    if not isinstance(data, dict) or set(data) != {key}:
        raise ValueError("La réponse n'est pas un objet JSON.")
    rows = data[key]
    if not isinstance(rows, list) or len(rows) > limit:
        raise ValueError("La réponse n'est pas un objet JSON.")
    return rows


def _cell(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Case illisible.")
    return value


def _whole(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Numéro illisible.")
    return value


def _insert_row(row: list[object]) -> LivretOp:
    if len(row) < 4 or not isinstance(row[2], str):
        raise ValueError("Opération illisible.")
    after = _whole(row[1])
    if after < 0:
        raise ValueError("Opération illisible.")
    if row[2] == "v":
        if len(row) != 5 or not isinstance(row[3], str) or not isinstance(row[4], str):
            raise ValueError("Opération illisible.")
        built = _insert(
            LivretOp(
                action="inserer",
                apres=after,
                type="vers",
                personnage=row[3],
                texte=row[4],
            )
        )
    else:
        kind = _HEADING_KIND.get(row[2])
        if kind is None or len(row) != 4 or not isinstance(row[3], str):
            raise ValueError("Opération illisible.")
        built = _insert(LivretOp(action="inserer", apres=after, type=kind, texte=row[3]))
    if built is None:
        raise ValueError("Opération illisible.")
    return built


def _replace_row(row: list[object]) -> LivretOp:
    if len(row) != 3 or not isinstance(row[2], str):
        raise ValueError("Opération illisible.")
    line = _whole(row[1])
    text = clean_line(row[2])
    if line <= 0 or not text:
        raise ValueError("Opération illisible.")
    return LivretOp(action="remplacer", ligne=line, texte=text)


def _delete_row(row: list[object]) -> LivretOp:
    if len(row) != 2:
        raise ValueError("Opération illisible.")
    line = _whole(row[1])
    if line <= 0:
        raise ValueError("Opération illisible.")
    return LivretOp(action="retirer", ligne=line)


def _dialogue(row: list[object]) -> ReadingItem:
    if len(row) != 3 or not isinstance(row[2], str):
        raise ValueError("Dialogue illisible.")
    staff = _whole(row[1])
    text = clean_paroles(row[2])
    if staff < 1 or not text:
        raise ValueError("Dialogue illisible.")
    return ReadingItem(type="dialogue", text=text, portee=staff)


def _insert(op: LivretOp) -> LivretOp | None:
    if op.apres is None or op.apres < 0 or op.type not in INSERT_KINDS:
        return None
    text = clean_line(op.texte or "")
    if not text:
        return None
    if op.type == "vers":
        role = clean_role(op.personnage or "")
        if not role:
            return None
        return LivretOp(
            action="inserer",
            apres=op.apres,
            type="vers",
            personnage=role,
            texte=text,
        )
    return LivretOp(action="inserer", apres=op.apres, type=op.type, texte=text)
