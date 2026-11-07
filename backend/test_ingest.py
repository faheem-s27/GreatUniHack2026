"""Tests for PDF slide ingest. The test PDF is generated here, so no files are needed."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import login_staff


def make_pdf(pages: list[list[str]]) -> bytes:
    """A minimal valid PDF with one text line per entry, one page per list."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        ops = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(
            "(" + line.replace("\\", "\\\\").replace("(", "\(").replace(")", "\)") + ") Tj T*" for line in lines
        ) + " ET"
        objects.append(f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream")
        content = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


DECK = [
    ["Data Engineering Concepts", "COMP63301", "Sandra Sampaio 1"],
    ["What is the Data Lifecycle?", "Data Lifecycle refers to the phases data moves through", "COMP63301", "Sandra Sampaio 2"],
    ["Data Profiling", "Profiling finds missing values and outliers", "COMP63301", "Sandra Sampaio 3"],
    ["4"],
    ["Summary", "Profiling comes before cleaning", "COMP63301", "Sandra Sampaio 5"],
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    from main import app

    with TestClient(app) as c:
        login_staff(c)
        c.post("/api/courses", json={"id": "de", "title": "Data Engineering"})
        c.post("/api/courses/de/lectures", json={"id": "de-w1", "title": "Week 1", "week": 1})
        yield c


def test_pages_become_clean_slides():
    from ingest import pages_to_slides, read_pdf_pages

    slides = pages_to_slides(read_pdf_pages(make_pdf(DECK)))
    assert [s.slide_number for s in slides] == [1, 2, 3, 4, 5]
    assert slides[1].title == "What is the Data Lifecycle?"
    # Footers repeated on most pages are dropped, even with changing page numbers.
    assert "Sampaio" not in slides[2].body and "COMP63301" not in slides[2].body
    assert "Profiling finds missing values" in slides[2].body
    assert slides[3].title is None and slides[3].body == ""  # page number only: kept, empty


def test_bullet_glyphs_and_hyphenation_are_cleaned():
    from ingest import _clean_lines

    text = "� Data is collected\n then stored\nre-\nused\n12"
    assert _clean_lines(text) == ["• Data is collected", "• then stored", "reused"]
    assert _clean_lines("satisﬁable") == ["satisfiable"]


def test_upload_pdf_route_makes_slides_searchable(client):
    r = client.post("/api/lectures/de-w1/pdf", content=make_pdf(DECK), headers={"Content-Type": "application/pdf"})
    assert r.status_code == 200 and r.json()["ingested_pages"] == 5
    hits = client.get("/api/search", params={"q": "how do I profile missing values", "course_id": "de"}).json()
    assert hits[0]["slide_number"] == 3 and hits[0]["citation"] == "Week 1, slide 3"


def test_upload_rejects_non_pdf_and_unknown_lecture(client):
    assert client.post("/api/lectures/de-w1/pdf", content=b"hello").status_code == 422
    assert client.post("/api/lectures/de-w1/pdf", content=b"%PDF-1.4 broken").status_code == 422
    assert client.post("/api/lectures/nope/pdf", content=make_pdf(DECK)).status_code == 404


def test_command_line_creates_course_lecture_and_coursework(client, tmp_path, capsys):
    import ingest

    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(make_pdf(DECK))
    ingest.main([str(pdf), "--course", "logic", "--course-title", "Logic", "--lecture", "lg-w1", "--week", "1", "--title", "Week 1"])
    assert "Loaded 5 slides into lg-w1" in capsys.readouterr().out
    assert client.get("/api/courses/logic").json()["lectures"][0]["slide_count"] == 5
    ingest.main([str(pdf), "--course", "logic", "--coursework", "lg-cw1", "--title", "CW1", "--keywords", "data lifecycle"])
    check = client.post("/api/coursework/check", json={"course_id": "logic", "text": "explain the data lifecycle"}).json()
    assert check["locked"] is True


def test_ligatures_become_plain_letters_so_search_finds_them():
    from ingest import _clean_lines

    assert _clean_lines("satis\ufb01able formulas") == ["satisfiable formulas"]
