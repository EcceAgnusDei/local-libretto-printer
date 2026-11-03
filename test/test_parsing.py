from libretto_printer.parsing import extract_json_object
from libretto_printer.schemas import (
    align_reading,
    clean_paroles,
    clean_role,
    normalize_cast,
    normalize_count,
    normalize_reading,
)


def test_json_is_found_inside_a_fence_and_a_thinking_trace() -> None:
    raw = """<think>je réfléchis</think>
```json
{"p": [["Zaïs"]]}
```
"""
    found = extract_json_object(raw)
    assert found["p"] == [["Zaïs"]]


def test_cast_keeps_a_null_staff_and_drops_a_broken_role() -> None:
    parsed = normalize_cast({"p": [["Oromazès\n!", None]]})
    assert parsed.systemes == [["Oromazès", None]]


def test_a_staff_count_outside_the_limit_is_refused() -> None:
    assert normalize_count({"n": [2, 4, 4]}) == [4, 4]
    assert normalize_count({"n": [1, 4]}) == [4]
    for payload in (
        {"n": [4, 4]},
        {"n": [2, 17, 4]},
        {"n": [2, 0, 4]},
        {"n": [17]},
        {"n": [0]},
        {"n": []},
        {"n": [1, True]},
    ):
        try:
            normalize_count(payload)
        except ValueError:
            continue
        raise AssertionError("compte accepté")


def test_an_empty_system_is_refused() -> None:
    try:
        normalize_cast({"p": [[None, None]]})
    except ValueError:
        return
    raise AssertionError("système vide accepté")


def test_a_verbose_answer_is_refused() -> None:
    try:
        normalize_cast({"systemes": [["Zaïs"]]})
    except ValueError:
        return
    raise AssertionError("ancien format accepté")


def test_a_dialogue_points_at_a_staff_number() -> None:
    cast = normalize_cast({"p": [["Flûte", "Oromazès"]]})
    reading = normalize_reading(
        {
            "r": [
                ["a", "PROLOGUE"],
                ["i", "Oromazès sur son Trone."],
                ["d", 2, "Ereillez vous troupe immortelle"],
            ]
        }
    )
    aligned = align_reading(cast, reading)
    assert aligned.items[2].portee == 2
    assert aligned.items[2].personnage == "Oromazès"
    assert aligned.items[2].text == "Ereillez vous troupe immortelle"


def test_a_missing_staff_number_is_refused() -> None:
    cast = normalize_cast({"p": [["Oromazès"]]})
    reading = normalize_reading({"r": [["d", 4, "Ah"]]})
    try:
        align_reading(cast, reading)
    except ValueError:
        return
    raise AssertionError("portée absente acceptée")


def test_role_and_lyric_cleaners_keep_the_long_s() -> None:
    assert clean_role("Chœur  des  vents") == "Chœur des vents"
    assert clean_paroles("paſſage\n\nencore") == "paſſage\nencore"
