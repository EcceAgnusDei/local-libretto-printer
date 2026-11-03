import json
import uuid
from pathlib import Path

import libretto_printer.render as render_module
from libretto_printer.render import DPI, render_pdf
from libretto_printer.session import create_session, safe_pdf_stem


def test_session_folder_shows_the_uuid_and_the_pdf_name(tmp_path: Path) -> None:
    pdf = tmp_path / "Zaïs_pages_1-40.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    out = tmp_path / "out"
    session = create_session(out, pdf, "Zaïs", DPI)
    parsed = uuid.UUID(session.uuid)
    assert str(parsed) == session.uuid
    assert session.uuid in session.root.name
    assert "Zaïs_pages_1-40" in session.root.name
    meta = json.loads((session.root / "session.json").read_text(encoding="utf-8"))
    assert meta["uuid"] == session.uuid
    assert meta["pdf_name"] == "Zaïs_pages_1-40.pdf"
    assert meta["dpi"] == 150
    assert session.root.parent == out.resolve()


def test_pdf_stem_drops_path_separators() -> None:
    assert "/" not in safe_pdf_stem("a/b")
    assert safe_pdf_stem("..") == "document"


def test_render_renames_sheets_to_pdf_page_numbers(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "score.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    pages = tmp_path / "pages"

    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> object:
        assert command[:4] == ["pdftoppm", "-png", "-r", "150"]
        assert "-f" in command
        prefix = Path(command[-1])
        prefix.parent.mkdir(parents=True, exist_ok=True)
        (prefix.parent / "sheet-2.png").write_bytes(b"png")
        (prefix.parent / "sheet-3.png").write_bytes(b"png")

        class Result:
            returncode = 0
            stderr = ""
            stdout = ""

        return Result()

    monkeypatch.setattr(render_module.subprocess, "run", fake_run)
    rendered = render_pdf(pdf, pages, first=2, last=3)
    assert [path.name for path in rendered] == ["page_0002.png", "page_0003.png"]


def test_render_refuses_a_file_that_is_not_a_pdf(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("non", encoding="utf-8")
    try:
        render_pdf(source, tmp_path / "pages", first=1, last=1)
    except ValueError:
        return
    raise AssertionError("fichier accepté")
