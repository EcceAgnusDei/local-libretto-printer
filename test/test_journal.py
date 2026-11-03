import json
from pathlib import Path

from libretto_printer.client import take_delta
from libretto_printer.journal import Journal


def test_text_is_visible_before_the_model_finishes(tmp_path: Path) -> None:
    journal = Journal(tmp_path)
    journal.event("page_0008 : passage paroles")
    journal.model_begin("qwen")
    journal.model("Bon")
    partial = journal.path.read_text(encoding="utf-8")
    journal.model("jour")
    journal.model_end()
    complete = journal.path.read_text(encoding="utf-8")
    journal.close()
    assert "[harnais] page_0008 : passage paroles" in partial
    assert "[modèle:qwen]\nBon" in partial
    assert "jour" not in partial
    assert "Bonjour" in complete
    assert "[modèle:fin]" in complete
    assert "[serveur]" not in complete


def test_a_symlink_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.log"
    outside.write_text("secret", encoding="utf-8")
    session = tmp_path / "session"
    session.mkdir()
    (session / "journal.log").symlink_to(outside)
    try:
        Journal(session)
    except (OSError, ValueError):
        assert outside.read_text(encoding="utf-8") == "secret"
        return
    raise AssertionError("lien accepté")


def test_stream_keeps_the_answer_and_separates_reasoning() -> None:
    content = json.dumps({"choices": [{"delta": {"content": "{\"items\":[]}"}}]})
    reasoning = json.dumps({"choices": [{"delta": {"reasoning_content": "je réfléchis"}}]})
    first = take_delta(f"data: {content}\n")
    second = take_delta(f"data: {reasoning}")
    done = take_delta("data: [DONE]")
    blank = take_delta("\n")
    assert first.content == '{"items":[]}'
    assert first.reasoning == ""
    assert second.reasoning == "je réfléchis"
    assert second.content == ""
    assert done.done is True
    assert blank.content == ""
    try:
        take_delta("pas un flux")
    except ValueError:
        return
    raise AssertionError("flux accepté")
