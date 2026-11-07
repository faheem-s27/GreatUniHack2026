"""The full path Stephanie asked for: upload real slides -> search them -> ask the
coach -> a reply citing the right slide. Plus lecture isolation, assessed
material staying LOCKED, and lectures without readable slides.

Uses Stephanie's FakeProvider, so no API key or network is needed.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import login_staff
from test_ingest import make_pdf

PROFILING = [
    ["Data Engineering Concepts", "COMP63301", "Dr S 1"],
    ["The Data Lifecycle", "Data moves through collection, storage and processing", "COMP63301", "Dr S 2"],
    ["Data Profiling", "Profiling finds missing values and outliers in a dataset", "COMP63301", "Dr S 3"],
    ["Data Cleaning", "Cleaning fills or removes missing values", "COMP63301", "Dr S 4"],
]
LOGIC = [
    ["Propositional Logic", "Formulas are built from atoms", "LR 1"],
    ["Valuations", "A valuation maps each atom to true or false", "LR 2"],
    ["Tautologies", "A tautology is true under every valuation", "LR 3"],
    ["Satisfiability", "A formula is satisfiable if some valuation makes it true", "LR 4"],
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    import coach_api
    from coach import FakeProvider
    from main import app

    monkeypatch.setattr(coach_api, "get_provider", lambda: FakeProvider())
    with TestClient(app) as c:
        yield c


def upload(client, pages, student="amira", module="de", title="Week 1", assessed=False):
    r = client.post("/api/library/lectures", params={"student_id": student, "module_id": module, "module_name": "Data Eng",
                                                      "title": title, "assessed": assessed},
                    content=make_pdf(pages), headers={"Content-Type": "application/pdf"})
    assert r.status_code == 201, r.text
    return r.json()


def ask(client, lecture_id, message, slide=1, student="amira", **extra):
    return client.post("/api/coach", json={"student_id": student, "lecture_id": lecture_id, "slide_number": slide,
                                           "message": message, **extra})


def test_upload_search_ask_and_cite_the_right_slide(client):
    lecture = upload(client, PROFILING)
    assert lecture["slide_count"] == 4 and lecture["slides_with_text"] == 4
    hits = client.get("/api/search", params={"q": "how do I find missing values", "lecture_id": lecture["lecture_id"]}).json()
    assert hits[0]["slide_number"] == 3

    r = ask(client, lecture["lecture_id"], "how do I find missing values?", slide=3)
    body = r.json()
    assert r.status_code == 200 and body["source"] == "lecture" and body["mode"] == "GUIDE"
    assert "slide 3" in body["response"]
    assert body["citations"] == [{"slide_number": 3, "title": "Data Profiling"}]
    assert body["concept"] == "Data Profiling"  # from the current slide, not hard-coded


def test_two_lectures_cannot_retrieve_each_others_slides(client, monkeypatch):
    de = upload(client, PROFILING, title="DE")
    lr = upload(client, LOGIC, module="lr", title="Logic")
    import coach_api

    seen = {}
    real = coach_api.lecture_slides

    def spy(conn, lecture_id, slide_number, question):
        slides, titles, course = real(conn, lecture_id, slide_number, question)
        seen[lecture_id] = slides
        return slides, titles, course

    monkeypatch.setattr(coach_api, "lecture_slides", spy)
    # A logic question asked inside the data engineering lecture finds nothing from the logic lecture.
    ask(client, de["lecture_id"], "what is a tautology and a valuation?", slide=2)
    texts = " ".join(s.text for s in seen[de["lecture_id"]])
    assert "tautology" not in texts.lower() and "valuation" not in texts.lower()
    assert client.get("/api/search", params={"q": "tautology", "lecture_id": de["lecture_id"]}).json() == []


def test_uploaded_coursework_stays_locked(client):
    cw = upload(client, PROFILING, title="Coursework 3", assessed=True)
    modes = [ask(client, cw["lecture_id"], m, slide=3).json()["mode"] for m in
             ["help", "I think you drop the rows", "I think you average them", "I think you ignore them", "give me the solution"]]
    assert modes == ["LOCKED"] * 5  # three wrong attempts would normally unlock EXPLAIN


def test_question_matching_course_coursework_is_locked(client):
    login_staff(client)
    import seed_demo
    from db import connect

    with connect() as conn:
        seed_demo.seed_course(conn, datetime.now(timezone.utc).isoformat())
    r = ask(client, "calc-w3", "how do I solve x^2 y + sin(xy)?", slide=2).json()
    assert r["mode"] == "LOCKED" and r["source"] == "lecture"
    # The browser cannot switch it off.
    bad = ask(client, "calc-w3", "help", slide=2, assessed=False)
    assert bad.status_code == 422


def test_memory_is_per_student_lecture_and_concept_and_survives(client):
    lecture = upload(client, PROFILING)
    lid = lecture["lecture_id"]
    ask(client, lid, "help", slide=3)
    for m in ["I think you delete the file", "I think you rename columns"]:
        ask(client, lid, m, slide=3)
    r = ask(client, lid, "I think you sort it", slide=3).json()
    assert r["wrong_attempts"] == 3 and r["mode"] == "EXPLAIN"
    # Another student, and another concept (slide 2) for the same student, start fresh.
    assert ask(client, lid, "help", slide=3, student="ben").json()["wrong_attempts"] == 0
    assert ask(client, lid, "help", slide=2).json()["wrong_attempts"] == 0
    # The coach's attempts also reached the student memory (gaps), used by handoffs and metrics.
    gaps = client.get("/api/gaps", params={"student_id": "amira"}).json()
    assert any(g["concept"] == "Data Profiling" and g["attempts"] == 3 for g in gaps)


def test_lecture_without_readable_slides_says_so(client):
    blank = upload(client, [[], []], title="Scanned deck")
    assert blank["slides_with_text"] == 0
    r = ask(client, blank["lecture_id"], "what is this about?").json()
    assert r["source"] == "none" and r["citations"] == [] and "can't read" in r["response"]
    assert ask(client, "lib-does-not-exist", "hi").status_code == 404


def test_students_cannot_add_to_someone_elses_module(client):
    upload(client, PROFILING, student="amira", module="shared")
    r = client.post("/api/library/lectures", params={"student_id": "mallory", "module_id": "shared", "module_name": "x",
                                                      "title": "y"}, content=make_pdf(LOGIC))
    assert r.status_code == 403
    assert client.post("/api/library/lectures", params={"student_id": "a", "module_id": "m", "module_name": "x", "title": "y"},
                       content=b"not a pdf").status_code == 422
