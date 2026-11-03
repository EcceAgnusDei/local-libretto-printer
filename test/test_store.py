import json
from pathlib import Path

from libretto_printer.schemas import LivretLine, RoleNote
from libretto_printer.store import Store


def test_roles_file_is_rewritten_with_the_last_system(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs", "Zais.pdf")
    store.save_roles(
        RoleNote(page="page_0015", last_system=[None, "Zaïs"], incoming_last_system=[])
    )
    note = store.load_roles()
    assert note is not None
    assert note.last_system == [None, "Zaïs"]
    assert note.roles == ["Zaïs"]


def test_page_name_cannot_escape_the_output_directory(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    try:
        store.save_glm("../secret", "texte")
    except ValueError:
        return
    raise AssertionError("chemin accepté")


def test_a_previous_livret_shape_is_refused(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.livret_lines_path.write_text(
        '{"verse_id": "page_0015-001", "page": "page_0015", "role": "Zaïs", "text": "Ah"}\n',
        encoding="utf-8",
    )
    try:
        store.load_lines()
    except ValueError as error:
        assert "nouvelle session" in str(error)
        return
    raise AssertionError("ancien livret accepté")


def test_review_line_stays_a_reason_code(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.add_review("page_0015", "invalid_response")
    line = json.loads(store.review_path.read_text(encoding="utf-8"))
    assert line == {"page": "page_0015", "reason": "invalid_response"}


def test_render_marks_a_prologue_as_an_act(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs", "Zais.pdf")
    store.save_lines(
        [
            LivretLine(kind="acte", text="Prologue", page="page_0001"),
            LivretLine(kind="vers", text="Ah", personnage="Oromazès", page="page_0001"),
        ]
    )
    text = store.livret_path.read_text(encoding="utf-8")
    assert "Source : Zais.pdf" in text
    assert "## Prologue" in text
    assert "**Oromazès.**\nAh" in text
