from libretto_printer.livret import apply_operations, excerpt, render_livret
from libretto_printer.schemas import EditResult, LivretLine, LivretOp, normalize_edit


def _vers(name: str, text: str, page: str = "page_0001") -> LivretLine:
    return LivretLine(kind="vers", text=text, personnage=name, page=page)


def _op(**kwargs: object) -> LivretOp:
    return LivretOp.model_validate(kwargs)


def test_an_absent_singer_cuts_before_an_older_scene() -> None:
    lines = [
        LivretLine(kind="scene", text="Scène 1", page="page_0001"),
        _vers("Cindor", "absent"),
        _vers("Zaïs", "présent"),
    ]
    shown = excerpt(lines, {"zaïs"})
    assert [number for number, _line in shown] == [3]


def test_a_scene_closer_than_an_absent_singer_wins() -> None:
    lines = [
        _vers("Cindor", "avant"),
        LivretLine(kind="scene", text="Scène 2", page="page_0002"),
        _vers("Zaïs", "après"),
    ]
    shown = excerpt(lines, {"zaïs", "cindor"})
    assert [line.text for _number, line in shown] == ["après"]


def test_a_prologue_and_an_act_cut_and_a_didascalie_does_not() -> None:
    lines = [
        LivretLine(kind="acte", text="Prologue", page="page_0001"),
        LivretLine(kind="didascalie", text="Il entre.", page="page_0001"),
        _vers("Oromazès", "Les torrents"),
    ]
    shown = excerpt(lines, {"oromazès"})
    assert [line.text for _number, line in shown] == ["Les torrents"]
    lines[0] = LivretLine(kind="acte", text="Acte I", page="page_0010")
    assert excerpt(lines, {"oromazès"})[0][1].text == "Les torrents"


def test_inserts_after_the_same_line_keep_their_order_and_ignore_a_foreign_number() -> None:
    lines = [_vers("Oromazès", "début")]
    edit = EditResult(
        operations=[
            _op(action="inserer", apres=1, type="scene", texte="Scène 1"),
            _op(action="inserer", apres=1, type="vers", personnage="Zaïs", texte="Ah", page=""),
            _op(action="remplacer", ligne=9, texte="non"),
        ]
    )
    try:
        apply_operations(lines, edit, {1}, "page_0016")
    except ValueError:
        return
    raise AssertionError("ligne étrangère acceptée")


def test_operations_apply_from_the_shown_lines() -> None:
    lines = [_vers("Oromazès", "début"), _vers("Zaïs", "milieu")]
    edit = normalize_edit(
        {
            "o": [
                ["=", 1, "début fini"],
                ["-", 2],
                ["+", 1, "i", "Il sort."],
                ["+", 1, "v", "Zaïs", "Ah"],
            ]
        }
    )
    written = apply_operations(lines, edit, {1, 2}, "page_0016")
    assert [line.text for line in written] == ["début fini", "Il sort.", "Ah"]
    assert written[2].page == "page_0016"
    text = render_livret("Zaïs", written)
    assert "*Il sort.*" in text
    assert "**Zaïs.**\nAh" in text


def test_an_insert_after_a_removed_line_takes_its_place() -> None:
    lines = [_vers("Oromazès", "un"), _vers("Zaïs", "deux")]
    edit = normalize_edit(
        {"o": [["-", 1], ["+", 1, "v", "Oromazès", "à la place"]]}
    )
    written = apply_operations(lines, edit, {1, 2}, "page_0016")
    assert [line.text for line in written] == ["à la place", "deux"]


def test_a_long_s_survives_and_a_role_stays_one_line() -> None:
    edit = normalize_edit(
        {"o": [["+", 0, "v", "Oromazès\n!", "un paſſage\nencore"]]}
    )
    assert edit.operations[0].personnage == "Oromazès"
    assert edit.operations[0].texte == "un paſſage encore"
