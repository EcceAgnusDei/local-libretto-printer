import json
from pathlib import Path

from libretto_printer.schemas import PageDecision
from libretto_printer.store import Store, render_livret


def _decision(**overrides: object) -> PageDecision:
    data: dict[str, object] = {
        "needs_glm": False,
        "number_label": "Prologue",
        "verses": [{"role": "Oromazès", "text": "Les torrents s'ouvrent un paſſage", "used_glm": False}],
        "corrections": [],
        "last_system_roles": ["Oromazès"],
        "uncertain": False,
    }
    data.update(overrides)
    return PageDecision.model_validate(data)


def test_commit_writes_livret_and_roles(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    result = store.commit("page_0015", _decision(), set(), None)
    assert result.added == 1
    assert result.roles == ["Oromazès"]
    verses = store.load_verses()
    assert verses[0].verse_id == "page_0015-001"
    assert "ſ" in verses[0].text
    text = store.livret_path.read_text(encoding="utf-8")
    assert "# Zaïs" in text
    assert "## Prologue" in text
    assert "### page 15" in text
    assert "**Oromazès.**" in text
    note = store.load_roles()
    assert note is not None
    assert note.roles == ["Oromazès"]


def test_rerun_replaces_the_page_and_keeps_the_previous_one(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.commit("page_0015", _decision(), set(), None)
    second = _decision(
        verses=[{"role": "Zaïs", "text": "L'Amour a déjà commencé", "used_glm": True}],
        last_system_roles=["Zaïs"],
        number_label="Zaïs",
    )
    store.commit("page_0016", second, set(), store.load_roles())
    again = _decision(
        verses=[{"role": "Oromazès", "text": "Les torrents s'ouvrent un passage", "used_glm": False}],
    )
    store.commit("page_0015", again, set(), store.load_roles())
    ids = [verse.verse_id for verse in store.load_verses()]
    assert ids == ["page_0016-001", "page_0015-001"]


def test_correction_applies_only_to_an_earlier_verse_in_the_tail(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.commit("page_0015", _decision(), set(), None)
    tail_ids = {verse.verse_id for verse in store.tail(40)}
    corrected = _decision(
        verses=[{"role": "Cindor", "text": "Les charmes d'une amour nouvelle", "used_glm": False}],
        corrections=[
            {"verse_id": "page_0015-001", "role": "Oromazès", "text": "Texte corrigé"},
            {"verse_id": "page_0099-001", "role": "Zaïs", "text": "hors mémoire"},
            {"verse_id": "../secret", "role": "Zaïs", "text": "chemin"},
        ],
        last_system_roles=["Cindor"],
    )
    result = store.commit("page_0016", corrected, tail_ids, store.load_roles())
    assert result.corrected == 1
    stored = {verse.verse_id: verse.text for verse in store.load_verses()}
    assert stored["page_0015-001"] == "Texte corrigé"
    assert "page_0099-001" not in stored


def test_correction_of_the_page_being_replaced_is_ignored(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.commit("page_0015", _decision(), set(), None)
    allowed = {verse.verse_id for verse in store.tail(40)}
    decision = _decision(
        corrections=[{"verse_id": "page_0015-001", "role": "Oromazès", "text": "ne doit pas rester seul"}],
        verses=[{"role": "Oromazès", "text": "Nouvelle lecture", "used_glm": False}],
    )
    store.commit("page_0015", decision, allowed, store.load_roles())
    texts = [verse.text for verse in store.load_verses()]
    assert texts == ["Nouvelle lecture"]


def test_empty_roles_keep_the_cast_of_the_same_number(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.commit("page_0015", _decision(), set(), None)
    instrumental = _decision(verses=[], last_system_roles=[], number_label="Prologue")
    result = store.commit("page_0016", instrumental, set(), store.load_roles())
    assert result.roles == ["Oromazès"]
    assert store.load_verses()[0].page == "page_0015"


def test_empty_roles_clear_the_cast_when_the_number_changes(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.commit("page_0015", _decision(), set(), None)
    new_number = _decision(verses=[], last_system_roles=[], number_label="Air")
    result = store.commit("page_0040", new_number, set(), store.load_roles())
    assert result.roles == []
    note = store.load_roles()
    assert note is not None
    assert note.number_label == "Air"


def test_uncertain_page_is_listed_for_review(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    store.commit("page_0015", _decision(uncertain=True), set(), None)
    lines = store.review_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"page": "page_0015", "reason": "uncertain"}


def test_page_name_cannot_escape_the_output_directory(tmp_path: Path) -> None:
    store = Store(tmp_path, "Zaïs")
    try:
        store.save_glm("../secret", "texte")
    except ValueError:
        return
    raise AssertionError("chemin accepté")


def test_render_groups_numbers() -> None:
    from libretto_printer.schemas import Verse

    verses = [
        Verse(
            verse_id="page_0015-001",
            page="page_0015",
            number_label="Prologue",
            role="Oromazès",
            text="Les torrents",
            used_glm=False,
        ),
        Verse(
            verse_id="page_0036-001",
            page="page_0036",
            number_label="Zaïs",
            role="Cindor",
            text="Les charmes",
            used_glm=True,
        ),
    ]
    text = render_livret("Zaïs", verses)
    assert text.index("## Prologue") < text.index("## Zaïs")
    assert "page 36" in text
