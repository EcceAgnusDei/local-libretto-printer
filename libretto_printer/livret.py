from __future__ import annotations

from libretto_printer.schemas import HEADINGS, EditResult, LivretLine, LivretOp


def excerpt(lines: list[LivretLine], present: set[str]) -> list[tuple[int, LivretLine]]:
    start = _boundary(lines, present) + 1
    shown: list[tuple[int, LivretLine]] = []
    for index in range(start, len(lines)):
        line = lines[index]
        if line.kind != "vers" or not line.personnage:
            continue
        if line.personnage.casefold() in present:
            shown.append((index + 1, line))
    return shown


def apply_operations(
    lines: list[LivretLine],
    edit: EditResult,
    allowed: set[int],
    page: str,
) -> list[LivretLine]:
    _check_numbers(edit, allowed, empty=not lines)
    replaces: dict[int, str] = {}
    deletes: set[int] = set()
    inserts: dict[int, list[LivretLine]] = {}
    for op in edit.operations:
        if op.action == "remplacer" and op.ligne is not None and op.texte:
            deletes.discard(op.ligne)
            replaces[op.ligne] = op.texte
        elif op.action == "retirer" and op.ligne is not None:
            replaces.pop(op.ligne, None)
            deletes.add(op.ligne)
        elif op.action == "inserer" and op.apres is not None:
            created = _created(op, page)
            if created is not None:
                inserts.setdefault(op.apres, []).append(created)
    result: list[LivretLine] = []
    result.extend(inserts.get(0, []))
    for number, line in enumerate(lines, start=1):
        if number in deletes:
            result.extend(inserts.get(number, []))
            continue
        if number in replaces and line.kind == "vers":
            line = line.model_copy(update={"text": replaces[number]})
        result.append(line)
        result.extend(inserts.get(number, []))
    return result


def render_livret(title: str, lines: list[LivretLine], pdf_name: str = "") -> str:
    output = [f"# {title}", ""]
    if pdf_name:
        output.extend((f"Source : {pdf_name}", ""))
    speaker: str | None = None
    for line in lines:
        if line.kind in HEADINGS:
            level = 2 if line.kind == "acte" else 3
            output.extend(("", f"{'#' * level} {line.text}", ""))
            speaker = None
            continue
        if line.kind == "didascalie":
            text = line.text
            if not (text.startswith("*") and text.endswith("*")):
                text = f"*{text}*"
            output.extend(("", text, ""))
            speaker = None
            continue
        if line.personnage != speaker:
            output.extend(("", f"**{line.personnage}.**"))
            speaker = line.personnage
        output.append(line.text)
    return "\n".join(output).rstrip() + "\n"


def format_excerpt(shown: list[tuple[int, LivretLine]]) -> str:
    if not shown:
        return "Livret vide. La seule insertion permise est apres 0."
    return "\n".join(
        f"{number} | {line.personnage} | {line.text}" for number, line in shown
    )


def _boundary(lines: list[LivretLine], present: set[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if line.kind in HEADINGS:
            return index
        if line.kind == "vers" and line.personnage and line.personnage.casefold() not in present:
            return index
    return -1


def _check_numbers(edit: EditResult, allowed: set[int], *, empty: bool) -> None:
    for op in edit.operations:
        if op.action == "inserer":
            if op.apres == 0 and empty:
                continue
            if op.apres not in allowed:
                raise ValueError("Insertion hors de l'extrait.")
            continue
        if op.ligne not in allowed:
            raise ValueError("Ligne hors de l'extrait.")


def _created(op: LivretOp, page: str) -> LivretLine | None:
    if op.type is None or not op.texte:
        return None
    if op.type == "vers":
        return LivretLine(kind="vers", text=op.texte, personnage=op.personnage, page=page)
    return LivretLine(kind=op.type, text=op.texte, page=page)
