from libretto_printer.parsing import extract_json_object
from libretto_printer.schemas import clean_role, clean_text, normalize_decision


def test_json_is_found_inside_a_fence_and_a_thinking_trace() -> None:
    raw = """<think>je réfléchis</think>
```json
{"needs_glm": false, "number_label": "Air", "verses": [], "corrections": [], "last_system_roles": [], "uncertain": false}
```
"""
    found = extract_json_object(raw)
    assert found["number_label"] == "Air"


def test_long_s_stays_in_the_verse_and_the_role_is_one_line() -> None:
    decision = normalize_decision(
        {
            "needs_glm": False,
            "number_label": "  Prologue  ",
            "verses": [{"role": "Oromazès\n!", "text": "un paſſage\nencore", "used_glm": False}],
            "corrections": [{"verse_id": "pas un id", "role": "Zaïs", "text": "x"}],
            "last_system_roles": ["Zaïs"],
            "uncertain": False,
        }
    )
    assert decision.verses[0].role == "Oromazès"
    assert decision.verses[0].text == "un paſſage encore"
    assert decision.corrections == []
    assert decision.number_label == "Prologue"


def test_role_and_text_cleaners() -> None:
    assert clean_role("Chœur  des  vents") == "Chœur des vents"
    assert "ſ" in clean_text("paſſage")
